import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import GitlabProject, GitLabEvent, GitlabUser
from app.schemas.enums import TELEGRAM_KINDS, EventKind, Status
from app.schemas.gitlab import ParsedEvent
from app.services.cache import Cache
from app.services.flow import Flow
from app.services.formatter import build_message
from app.services.notify import send_or_edit
from app.telegram.client import TelegramClient

log = logging.getLogger(__name__)


async def get_or_create_project(session: AsyncSession, name: str) -> GitlabProject:
    query = select(GitlabProject).where(GitlabProject.name == name).options(selectinload(GitlabProject.telegram_group))
    project = await session.scalar(query)
    if project:
        return project

    session.add(GitlabProject(name=name))
    try:
        await session.commit()
    except IntegrityError:  # created by a parallel request
        await session.rollback()
    return await session.scalar(query)


# pipeline statuses worth a fresh (notifying) message
NOTIFY_PIPELINE_STATUSES = {Status.SUCCESS, Status.FAILED, Status.CANCELED, Status.MANUAL}


def starts_new_message(event: ParsedEvent) -> bool:
    """A push and a finished pipeline get a new message; the rest edits the current one."""
    return event.kind == EventKind.PUSH or (
        event.kind == EventKind.PIPELINE and event.status in NOTIFY_PIPELINE_STATUSES
    )


async def process_event(session: AsyncSession, tg: TelegramClient, cache: Cache, event: ParsedEvent) -> str:
    """Store the event and forward it to the project's Telegram group. Returns a status string."""
    if not event.project_name:
        return "logged (no project)"
    project = await get_or_create_project(session, event.project_name)

    session.add(
        GitLabEvent(
            gitlab_event=event.kind.value,
            project_id=project.id,
            status=str(event.status)[:50],
            branch=event.branch[:255],
            user_name=(event.user.username or None) and event.user.username[:255],
            duration=event.duration,
        )
    )
    await session.commit()

    if event.kind not in TELEGRAM_KINDS or not event.forward:
        return "stored (not forwarded)"

    group = project.telegram_group
    if group is None or not group.is_active:
        log.warning(
            "project %r: %s", project.name, "no telegram group linked" if group is None else f"group {group} is not active"
        )
        return "stored (no active telegram group)"

    key = f"flow:{project.id}:{event.branch}"
    async with cache.lock(key):
        raw = await cache.get_flow(key)
        flow = Flow.from_json(raw) if raw else Flow(project=project.name, branch=event.branch)
        flow.apply(event, datetime.now(ZoneInfo(get_settings().timezone)))
        if starts_new_message(event):
            # Editing never notifies and does not move a message down the chat: send a fresh one.
            await cache.delete_message_id(key)

        telegram_ids: dict[int, int] = {}
        if flow.user_ids:
            rows = await session.execute(
                select(GitlabUser.gitlab_id, GitlabUser.telegram_id).where(GitlabUser.gitlab_id.in_(flow.user_ids))
            )
            telegram_ids = {gitlab_id: telegram_id for gitlab_id, telegram_id in rows}

        await send_or_edit(
            tg,
            cache,
            chat_id=group.chat_id,
            thread_id=group.message_thread_id,
            text=build_message(flow, project, telegram_ids),
            key=key,
            final=event.is_final,
        )
        if event.is_final:
            await cache.delete_flow(key)
        else:
            await cache.set_flow(key, flow.to_json())
    return "sent"

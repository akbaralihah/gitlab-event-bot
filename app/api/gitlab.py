import logging
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.deps import get_cache, get_telegram
from app.models import WebhookSecret
from app.schemas.common import ErrorResponse, StatusResponse
from app.schemas.gitlab import parse_event
from app.services.cache import Cache
from app.schemas.enums import EventKind
from app.services import signature
from app.services.gitlab_events import process_event
from app.telegram.client import TelegramClient

log = logging.getLogger(__name__)

router = APIRouter(tags=["GitLab"])

# Swagger cannot infer the body (it is read as raw JSON), so the examples are given by hand.
REQUEST_BODY_EXAMPLES = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {"type": "object", "title": "Payload события GitLab"},
                "examples": {
                    "push": {
                        "summary": "Push Hook",
                        "value": {
                            "project": {"name": "demo"},
                            "ref": "refs/heads/main",
                            "user_id": 7,
                            "user_username": "bob",
                            "user_name": "Bob",
                        },
                    },
                    "merge_request": {
                        "summary": "Merge Request Hook",
                        "value": {
                            "project": {"name": "demo"},
                            "user": {"id": 7, "name": "Bob", "username": "bob"},
                            "object_attributes": {
                                "id": 42,
                                "source_branch": "feature",
                                "target_branch": "main",
                                "state": "opened",
                                "action": "open",
                                "url": "https://gitlab.example.com/demo/-/merge_requests/1",
                                "draft": False,
                            },
                            "assignees": [{"id": 8, "name": "Alice", "username": "alice"}],
                            "reviewers": [],
                        },
                    },
                    "pipeline": {
                        "summary": "Pipeline Hook",
                        "value": {
                            "project": {"name": "demo"},
                            "user": {"id": 7, "name": "Bob", "username": "bob"},
                            "object_attributes": {"id": 9, "ref": "main", "status": "running", "duration": 12},
                        },
                    },
                },
            }
        },
    }
}


@router.post(
    "/gitlab/webhook",
    summary="Вебхук GitLab",
    description=(
            "Принимает события GitLab, сохраняет их в базе и отправляет сообщение в Telegram-группу проекта.\n\n"
            "Поддерживаются заголовки `X-Gitlab-Event`: **Push Hook**, **Merge Request Hook**, **Pipeline Hook**. "
            "Остальные события игнорируются.\n\n"
            "Сообщения о merge request и pipeline **редактируются** при смене статуса, а не отправляются заново. "
            "Проект создаётся автоматически при первом событии; привязать его к группе можно в админке.\n\n"
            "Если в админке добавлен активный Signing Token, подпись `webhook-signature` должна ему соответствовать; "
            "без активных токенов проверка отключена.\n\n"
            "**Значения `status` в ответе:**\n"
            "- `sent` — сообщение отправлено или отредактировано;\n"
            "- `stored (no active telegram group)` — событие сохранено, но у проекта нет активной группы "
            "(группа не привязана или выключена командой `/stop`);\n"
            "- `stored (not forwarded)` — событие сохранено, но этот тип в Telegram не отправляется;\n"
        "- `logged (no project)` — в payload нет имени проекта, событие только записано в лог;\n"
            "- `error` — событие сохранено, но отправить сообщение в Telegram не удалось. "
            "Код всё равно 200, чтобы GitLab не отключал вебхук."
    ),
    response_model=StatusResponse,
    responses={
        400: {"model": ErrorResponse,
              "description": "Тело запроса не является корректным JSON или не подходит под тип события"},
        401: {"model": ErrorResponse, "description": "Отсутствует или неверна подпись `webhook-signature`"},
    },
    openapi_extra=REQUEST_BODY_EXAMPLES,
)
async def gitlab_webhook(
        request: Request,
        session: Annotated[AsyncSession, Depends(get_session)],
        tg: Annotated[TelegramClient, Depends(get_telegram)],
        cache: Annotated[Cache, Depends(get_cache)],
        x_gitlab_event: Annotated[
            str | None,
            Header(description="Тип события: `Push Hook`, `Merge Request Hook` или `Pipeline Hook`"),
        ] = None,
        webhook_id: Annotated[str | None, Header(description="ID доставки (подпись)")] = None,
        webhook_timestamp: Annotated[str | None, Header(description="Unix-время доставки (подпись)")] = None,
        webhook_signature: Annotated[
            str | None,
            Header(description="Подпись `v1,<base64>`; проверяется, если в админке есть активный Signing Token"),
        ] = None,
) -> dict:
    body = await request.body()
    tokens = list(await session.scalars(select(WebhookSecret.token).where(WebhookSecret.is_active)))
    if tokens and not signature.verify(tokens, webhook_id, webhook_timestamp, webhook_signature, body):
        raise HTTPException(status_code=401, detail="Неверная подпись webhook-signature")

    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("ожидался JSON-объект")
        event = parse_event(x_gitlab_event or "", data)
    except (ValueError, ValidationError) as e:  # ValueError covers invalid JSON
        raise HTTPException(status_code=400, detail=f"Некорректное тело запроса: {e}")

    log.info(
        "gitlab event: header=%r kind=%s project=%s status=%r branch=%r user=%s",
        event.header, event.kind.name, event.project_name, event.status, event.branch, event.user.username,
    )
    if event.kind == EventKind.UNKNOWN:
        log.warning("unknown gitlab event %r, payload keys: %s", event.header, sorted(data) if isinstance(data, dict) else data)

    try:
        result = await process_event(session, tg, cache, event)
    except Exception:
        # The event is already stored, a Telegram failure must not make GitLab disable the webhook.
        log.exception("failed to forward %s event of %s", event.kind, event.project_name)
        return {"status": "error"}
    return {"status": result}

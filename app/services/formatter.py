from html import escape

from app.models import GitlabProject
from app.schemas.enums import EventKind, Status
from app.schemas.gitlab import GLUser, ParsedEvent

STATUS_EMOJI = {
    Status.PUSHED: "✅",
    Status.DELETED: "🗑",
    Status.OPENED: "✨",
    Status.REOPENED: "🔄",
    Status.UPDATED: "📝",
    Status.MERGED: "🤝",
    Status.CLOSED: "🔒",
    Status.APPROVED: "👍",
    Status.UNAPPROVED: "👎",
    Status.APPROVAL: "✅",
    Status.UNAPPROVAL: "❌",
    Status.CREATED: "🆕",
    Status.PREPARING: "🛠",
    Status.WAITING_FOR_RESOURCE: "⌛",
    Status.PENDING: "⏳",
    Status.RUNNING: "🏃",
    Status.SUCCESS: "🟢",
    Status.FAILED: "🔴",
    Status.CANCELED: "⚪",
    Status.SKIPPED: "⏭️",
    Status.MANUAL: "✋",
    Status.SCHEDULED: "🗓",
    Status.BLOCKED: "⛔",
}


def _code(value: object) -> str:
    return f"<code>{escape(str(value))}</code>"


def mention(user: GLUser, telegram_ids: dict[int, int]) -> str:
    name = escape(user.name or user.username or "unknown")
    telegram_id = telegram_ids.get(user.id) if user.id is not None else None
    if telegram_id:
        return f'<a href="tg://user?id={telegram_id}">{name}</a>'
    return name


MAX_COMMITS = 5


def _push_commits(event: ParsedEvent) -> list[str]:
    lines = [f"📦 <b>Commits:</b> {_code(event.total_commits)}"]
    for c in event.commits[:MAX_COMMITS]:
        title = escape(c.title[:80] + ("…" if len(c.title) > 80 else ""))
        sha = escape(c.id[:8])
        label = f'<a href="{escape(c.url, quote=True)}">{sha}</a>' if c.url else f"<code>{sha}</code>"
        author = f" — {escape(c.author.name)}" if c.author.name else ""
        lines.append(f"  • {label} {title}{author}")
    if event.total_commits > MAX_COMMITS:
        lines.append(f"  … and {event.total_commits - MAX_COMMITS} more")
    return lines


def build_message(event: ParsedEvent, project: GitlabProject, telegram_ids: dict[int, int]) -> str:
    """Render an event as Telegram HTML. `telegram_ids` maps gitlab_id -> telegram_id."""
    lines = [f"🚀 <b>Event Update:</b> {_code(event.header)}"]

    if project.show_project:
        lines.append(f"📣 <b>Project:</b> {_code(project.name)}")
        if event.kind == EventKind.MERGE_REQUEST:
            lines.append(f"📑 <b>Is Draft:</b> {_code(event.draft)}")
    if project.show_status:
        emoji = STATUS_EMOJI.get(event.status, "")
        status = f"{event.status} {emoji}".strip()
        lines.append(f"📌 <b>Status:</b> {_code(status)}")
        if event.kind == EventKind.PUSH and event.protected:
            lines.append(f"🛡 <b>Protected:</b> {_code('yes')}")
    if project.show_branch:
        if event.kind == EventKind.MERGE_REQUEST:
            lines.append(f"🌿 <b>Source:</b> {_code(event.branch)}")
            lines.append(f"🎯 <b>Target:</b> {_code(event.target_branch)}")
        else:
            lines.append(f"🌿 <b>Branch:</b> {_code(event.branch)}")
    if project.show_user:
        lines.append(f"👤 <b>User:</b> {mention(event.user, telegram_ids)}")
        if event.assignees:
            lines.append("👥 <b>Assignees:</b>")
            lines += [f"  • {mention(u, telegram_ids)}" for u in event.assignees]
        if event.reviewers:
            lines.append("👁 <b>Reviewers:</b>")
            lines += [f"  • {mention(u, telegram_ids)}" for u in event.reviewers]
    if event.kind == EventKind.PUSH and event.commits:
        lines += _push_commits(event)
    if event.url:
        lines.append(f'🔗 <b>Link:</b> <a href="{escape(event.url, quote=True)}">tap to view</a>')
    if event.kind == EventKind.PUSH:
        links = [
            f'<a href="{escape(url, quote=True)}">{label}</a>'
            for label, url in (("branch", event.branch_url), ("compare", event.compare_url))
            if url
        ]
        if links:
            lines.append(f"🔗 <b>Links:</b> {' · '.join(links)}")
    if project.show_duration and event.kind == EventKind.PIPELINE and event.duration is not None:
        lines.append(f"⏳ <b>Duration:</b> {_code(f'{event.duration}s')}")

    return "\n".join(lines)

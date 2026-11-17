from html import escape

from app.models import GitlabProject
from app.schemas.enums import STATUS_EMOJI
from app.schemas.gitlab import GLUser
from app.services.flow import Flow

TELEGRAM_LIMIT = 4096
SAFE_LIMIT = 3900  # leave room for the tags


def _code(value: object) -> str:
    return f"<code>{escape(str(value))}</code>"


def _link(url: str, label: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'


def _status(status: str) -> str:
    return f"{status} {STATUS_EMOJI.get(status, '')}".strip()


def mention(user: GLUser | dict, telegram_ids: dict[int, int]) -> str:
    user = user if isinstance(user, GLUser) else GLUser(**user)
    name = escape(user.name or user.username or "unknown")
    telegram_id = telegram_ids.get(user.id) if user.id is not None else None
    if telegram_id:
        return f'<a href="tg://user?id={telegram_id}">{name}</a>'
    return name


def _render(flow: Flow, project: GitlabProject, telegram_ids: dict[int, int], history: list[str]) -> str:
    if flow.iid is not None or flow.mr_status:
        head = f"🔀 <b>Merge Request{f' !{flow.iid}' if flow.iid else ''}</b>"
        if project.show_status and flow.mr_status:
            head += f" · {_code(_status(flow.mr_status))}"
        if flow.draft:
            head += " · 🚧 <b>Draft</b>"
    else:
        head = "🌿 <b>Branch</b>"
        if project.show_status and flow.status:
            head += f" · {_code(_status(flow.status))}"
    lines = [head]

    if project.show_project:
        lines.append(f"📣 {_code(flow.project)}")
    if flow.title:
        lines.append(f"📝 {_link(flow.url, flow.title) if flow.url else f'<b>{escape(flow.title)}</b>'}")
    if project.show_branch:
        branch = _code(flow.branch)
        lines.append(f"🌿 {branch} → {_code(flow.target_branch)}" if flow.target_branch else f"🌿 {branch}")
        if flow.protected:
            lines[-1] += " 🛡"
    if project.show_user and flow.user:
        lines.append(f"👤 {mention(flow.user, telegram_ids)}")
        if flow.assignees:
            lines.append("👥 <b>Assignees:</b> " + ", ".join(mention(u, telegram_ids) for u in flow.assignees))
        if flow.reviewers:
            lines.append("👁 <b>Reviewers:</b> " + ", ".join(mention(u, telegram_ids) for u in flow.reviewers))
    if flow.labels:
        lines.append("🏷 " + " ".join(_code(label) for label in flow.labels))

    if flow.pipeline_id is not None:
        pipeline = f"🏗 <b>Pipeline #{flow.pipeline_id}</b>"
        if project.show_status and flow.pipeline_status:
            pipeline += f" · {_code(_status(flow.pipeline_status))}"
        if project.show_duration and flow.pipeline_duration is not None:
            pipeline += f" · ⏳ {_code(f'{flow.pipeline_duration}s')}"
        lines.append(pipeline)

    if flow.commits:
        lines.append(f"📦 <b>Commits:</b> {_code(flow.total_commits)}")
        commits = []
        for c in flow.commits:
            title = escape(c["title"][:80] + ("…" if len(c["title"]) > 80 else ""))
            sha = c["id"][:8]
            label = _link(c["url"], sha) if c.get("url") else _code(sha)
            author = (c.get("author") or {}).get("name")
            commits.append(f"{label} {title}" + (f" — {escape(author)}" if author else ""))
        lines.append("<blockquote expandable>" + "\n".join(commits) + "</blockquote>")

    if flow.comments:
        rows = []
        for c in flow.comments:
            text = escape(c["text"]) or "…"
            rows.append(f"<b>{escape(c['author'])}:</b> " + (_link(c["url"], c["text"] or "…") if c.get("url") else text))
        lines.append(f"💬 <b>Comments:</b> {_code(flow.total_comments)}")
        lines.append("<blockquote expandable>" + "\n".join(rows) + "</blockquote>")

    links = [_link(url, label) for label, url in (("branch", flow.branch_url), ("compare", flow.compare_url)) if url]
    if links:
        lines.append("🔗 " + " · ".join(links))

    if history:
        lines.append("📜 <b>History</b>\n<blockquote expandable>" + "\n".join(escape(h) for h in history) + "</blockquote>")
    return "\n".join(lines)


def build_message(flow: Flow, project: GitlabProject, telegram_ids: dict[int, int]) -> str:
    """Render the state of a branch as Telegram HTML. `telegram_ids` maps gitlab_id -> telegram_id.
    The oldest history lines are dropped until the text fits into a Telegram message."""
    history = list(flow.history)
    text = _render(flow, project, telegram_ids, history)
    while len(text) > SAFE_LIMIT and history:
        history.pop(0)
        text = _render(flow, project, telegram_ids, history)
    return text[:TELEGRAM_LIMIT]

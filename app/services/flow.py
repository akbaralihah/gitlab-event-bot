"""One Telegram message per branch: push, merge request and pipeline events of the same branch
are folded into a single state (`Flow`) that is re-rendered and edited on every event."""
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime

from app.schemas.enums import EventKind, Status
from app.schemas.gitlab import ParsedEvent

MAX_COMMITS = 5
MAX_HISTORY = 20
MAX_COMMENTS = 10
COMMENT_LENGTH = 200


@dataclass
class Flow:
    project: str
    branch: str
    target_branch: str | None = None
    # merge request
    iid: int | None = None
    title: str | None = None
    url: str | None = None
    draft: bool = False
    mr_status: str | None = None
    assignees: list[dict] = field(default_factory=list)
    reviewers: list[dict] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    # last actor
    user: dict = field(default_factory=dict)
    # push
    status: str | None = None  # last push status, shown while there is no merge request
    commits: list[dict] = field(default_factory=list)
    total_commits: int = 0
    compare_url: str | None = None
    branch_url: str | None = None
    protected: bool = False
    # pipeline
    pipeline_id: int | None = None
    pipeline_status: str | None = None
    pipeline_duration: int | None = None
    # comments on the merge request
    comments: list[dict] = field(default_factory=list)
    total_comments: int = 0
    history: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "Flow":
        return cls(**json.loads(raw))

    @property
    def user_ids(self) -> set[int]:
        return {u["id"] for u in [self.user, *self.assignees, *self.reviewers] if u.get("id") is not None}

    def apply(self, event: ParsedEvent, now: datetime) -> None:
        if event.kind != EventKind.NOTE and (event.user.id is not None or event.user.username or event.user.name):
            self.user = event.user.model_dump()
        note = self._apply_kind(event)
        stamp = now.strftime("%d.%m %H:%M")
        self.history.append(f"{stamp} {note}")
        del self.history[:-MAX_HISTORY]

    def _apply_kind(self, event: ParsedEvent) -> str:
        if event.kind == EventKind.MERGE_REQUEST:
            self.iid, self.title, self.url, self.draft = event.iid, event.title, event.url, event.draft
            self.target_branch = event.target_branch
            self.mr_status = event.status
            self.assignees = [u.model_dump() for u in event.assignees]
            self.reviewers = [u.model_dump() for u in event.reviewers]
            self.labels = event.labels
            return f"{_emoji(event.status)} MR {event.status}"

        if event.kind == EventKind.NOTE:
            return self._apply_note(event)

        if event.kind == EventKind.PIPELINE:
            self.pipeline_id, self.pipeline_status = event.pipeline_id, event.status
            self.pipeline_duration = event.duration
            return f"{_emoji(event.status)} pipeline #{event.pipeline_id} {event.status}"

        # push
        self.status = event.status
        self.protected = event.protected
        self.branch_url, self.compare_url = event.branch_url, event.compare_url
        # every push is shown as its own message: its commits, a fresh pipeline
        self.commits = [c.model_dump() for c in event.commits][-MAX_COMMITS:]
        self.total_commits = event.total_commits
        self.pipeline_id = self.pipeline_status = self.pipeline_duration = None
        who = event.user.username or event.user.name or "?"
        if event.status == Status.CREATED:
            return f"{_emoji(event.status)} branch created by {who}"
        if event.status == Status.DELETED:
            return f"{_emoji(event.status)} branch deleted by {who}"
        return f"📦 push by {who}: {event.total_commits} commit(s)"


def _apply_note(self: Flow, event: ParsedEvent) -> str:
    # the merge request itself may be unknown yet (a comment arrived first): fill what the note carries
    self.iid = self.iid or event.iid
    self.title = self.title or event.title
    self.url = self.url or event.url
    self.target_branch = self.target_branch or event.target_branch
    self.mr_status = self.mr_status or event.status or None
    who = event.user.name or event.user.username or "?"
    text = " ".join((event.note or "").split())
    comment = {
        "id": event.note_id,
        "author": who,
        "text": text[:COMMENT_LENGTH] + ("…" if len(text) > COMMENT_LENGTH else ""),
        "url": event.note_url,
    }
    for i, old in enumerate(self.comments):
        if event.note_id is not None and old["id"] == event.note_id:
            self.comments[i] = comment
            return f"💬 {who} edited a comment"
    self.comments.append(comment)
    del self.comments[:-MAX_COMMENTS]
    self.total_comments += 1
    return f"💬 {who} commented"


Flow._apply_note = _apply_note


def _emoji(status: str) -> str:
    from app.services.formatter import STATUS_EMOJI

    return STATUS_EMOJI.get(status, "•")

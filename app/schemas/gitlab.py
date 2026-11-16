"""Pydantic models of the GitLab webhook payloads (only the fields we use)
and the normalized `ParsedEvent` the rest of the app works with."""
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.schemas.enums import EVENT_HEADERS, OBJECT_KINDS, EventKind, Status

APPROVAL_ACTIONS = {Status.APPROVED, Status.UNAPPROVED, Status.APPROVAL, Status.UNAPPROVAL}
MR_ACTION_LABELS = {"update": Status.UPDATED, "reopen": Status.REOPENED}
MR_FINAL_STATES = {Status.MERGED, Status.CLOSED}


class GLProject(BaseModel):
    name: str


class GLUser(BaseModel):
    id: int | None = None
    name: str | None = None
    username: str | None = None


class PushPayload(BaseModel):
    project: GLProject
    ref: str = ""
    user_id: int | None = None
    user_username: str | None = None
    user_name: str | None = None


class MergeAttrs(BaseModel):
    id: int
    source_branch: str = ""
    target_branch: str = ""
    state: str = ""
    action: str | None = None
    url: str | None = None
    draft: bool = False


class MergePayload(BaseModel):
    project: GLProject
    user: GLUser = Field(default_factory=GLUser)
    object_attributes: MergeAttrs
    assignees: list[GLUser] = []
    reviewers: list[GLUser] = []


class PipelineAttrs(BaseModel):
    id: int
    ref: str | None = None
    status: str = ""
    duration: int | None = None


class PipelinePayload(BaseModel):
    project: GLProject
    user: GLUser | None = None
    object_attributes: PipelineAttrs


@dataclass
class ParsedEvent:
    kind: EventKind
    header: str  # original X-Gitlab-Event value, shown in the message
    project_name: str | None
    status: str
    branch: str
    user: GLUser
    duration: int | None = None
    target_branch: str | None = None
    url: str | None = None
    draft: bool = False
    assignees: list[GLUser] = field(default_factory=list)
    reviewers: list[GLUser] = field(default_factory=list)
    # Merge requests and pipelines are one Telegram message that gets edited.
    tracking_key: str | None = None
    # After a final event the message is not edited anymore.
    is_final: bool = False

    @property
    def gitlab_ids(self) -> set[int]:
        users = [self.user, *self.assignees, *self.reviewers]
        return {u.id for u in users if u.id is not None}


def _short_ref(ref: str | None) -> str:
    ref = ref or ""
    for prefix in ("refs/heads/", "refs/tags/"):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    return ref


def _first(*values: object) -> str:
    for value in values:
        if value not in (None, ""):
            return str(value)
    return ""


def _detect_kind(header: str, data: dict) -> EventKind:
    return EVENT_HEADERS.get(header) or OBJECT_KINDS.get(str(data.get("object_kind") or "")) or EventKind.UNKNOWN


def _generic_user(data: dict) -> GLUser:
    user = data.get("user")
    if isinstance(user, dict):
        return GLUser(id=user.get("id"), name=user.get("name"), username=user.get("username"))
    return GLUser(id=data.get("user_id"), name=data.get("user_name"), username=data.get("user_username"))


def _generic_project_name(data: dict) -> str | None:
    project = data.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    return _first(name, data.get("project_name"), data.get("group_name"), data.get("full_path")) or None


def _generic_status(kind: EventKind, data: dict, attrs: dict) -> str:
    if kind == EventKind.TAG_PUSH:
        return Status.PUSHED
    if kind == EventKind.JOB:
        return _first(data.get("build_status"), data.get("status"))
    if kind == EventKind.NOTE:
        return _first(attrs.get("noteable_type"), attrs.get("action"), "commented").lower()
    if kind == EventKind.FEATURE_FLAG:
        return "enabled" if attrs.get("active") else "disabled"
    return _first(
        data.get("action"),
        attrs.get("action"),
        data.get("status"),
        attrs.get("status"),
        attrs.get("state"),
        data.get("event_name"),
        data.get("event_type"),
    )


def _parse_generic(kind: EventKind, header: str, data: dict) -> ParsedEvent:
    """Tolerant parsing for the events we only store and log: nothing here may raise on a missing field."""
    attrs = data.get("object_attributes")
    attrs = attrs if isinstance(attrs, dict) else {}
    return ParsedEvent(
        kind=kind,
        header=header,
        project_name=_generic_project_name(data),
        status=_generic_status(kind, data, attrs),
        branch=_short_ref(_first(data.get("ref"), attrs.get("ref"))),
        user=_generic_user(data),
        duration=attrs.get("duration") if isinstance(attrs.get("duration"), int) else None,
        url=_first(attrs.get("url"), data.get("url")) or None,
    )


def parse_event(header: str, data: dict) -> ParsedEvent:
    """Never returns None: every event is accepted. Raises pydantic.ValidationError only for the three
    events that are forwarded to Telegram when their payload is malformed."""
    kind = _detect_kind(header, data)

    if kind == EventKind.PUSH:
        p = PushPayload.model_validate(data)
        return ParsedEvent(
            kind=kind,
            header=header,
            project_name=p.project.name,
            status=Status.PUSHED,
            branch=_short_ref(p.ref),
            user=GLUser(id=p.user_id, name=p.user_name, username=p.user_username),
        )

    if kind == EventKind.MERGE_REQUEST:
        p = MergePayload.model_validate(data)
        a = p.object_attributes
        if a.action in APPROVAL_ACTIONS:
            status = a.action
        else:
            status = MR_ACTION_LABELS.get(a.action or "") or a.state
        return ParsedEvent(
            kind=kind,
            header=header,
            project_name=p.project.name,
            status=status,
            branch=a.source_branch,
            target_branch=a.target_branch,
            user=p.user,
            url=a.url,
            draft=a.draft,
            assignees=p.assignees,
            reviewers=p.reviewers,
            tracking_key=f"merge:{a.id}:{a.source_branch}",
            is_final=a.state in MR_FINAL_STATES or a.action == "merge",
        )

    if kind == EventKind.PIPELINE:
        p = PipelinePayload.model_validate(data)
        a = p.object_attributes
        return ParsedEvent(
            kind=kind,
            header=header,
            project_name=p.project.name,
            status=a.status,
            branch=_short_ref(a.ref),
            user=p.user or GLUser(),
            duration=a.duration,
            tracking_key=f"pipeline:{a.id}:{a.ref}",
        )

    return _parse_generic(kind, header, data)

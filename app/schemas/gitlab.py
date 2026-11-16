"""Pydantic models of the GitLab webhook payloads (only the fields we use)
and the normalized `ParsedEvent` the rest of the app works with."""
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

EventKind = Literal["push", "merge", "pipeline"]

# value of the X-Gitlab-Event header -> kind
EVENT_HEADERS: dict[str, EventKind] = {
    "Push Hook": "push",
    "Merge Request Hook": "merge",
    "Pipeline Hook": "pipeline",
}

APPROVAL_ACTIONS = {"approved", "unapproved", "approval", "unapproval"}
MR_ACTION_LABELS = {"update": "updated", "reopen": "reopened"}
MR_FINAL_STATES = {"merged", "closed"}


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
    project_name: str
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


def parse_event(header: str, data: dict) -> ParsedEvent | None:
    """Return None for unsupported events. Raises pydantic.ValidationError on a bad payload."""
    kind = EVENT_HEADERS.get(header)

    if kind == "push":
        p = PushPayload.model_validate(data)
        return ParsedEvent(
            kind=kind,
            header=header,
            project_name=p.project.name,
            status="pushed",
            branch=p.ref.split("/")[-1],
            user=GLUser(id=p.user_id, name=p.user_name, username=p.user_username),
        )

    if kind == "merge":
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

    if kind == "pipeline":
        p = PipelinePayload.model_validate(data)
        a = p.object_attributes
        return ParsedEvent(
            kind=kind,
            header=header,
            project_name=p.project.name,
            status=a.status,
            branch=(a.ref or "").split("/")[-1],
            user=p.user or GLUser(),
            duration=a.duration,
            tracking_key=f"pipeline:{a.id}:{a.ref}",
        )

    return None

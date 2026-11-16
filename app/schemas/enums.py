from enum import StrEnum


class EventKind(StrEnum):
    """Kind of a GitLab webhook event. The value is what is stored in `gitlab_events.gitlab_event`."""

    PUSH = "push"
    TAG_PUSH = "tag_push"
    ISSUE = "issue"
    NOTE = "note"
    MERGE_REQUEST = "merge"
    WIKI_PAGE = "wiki_page"
    PIPELINE = "pipeline"
    JOB = "job"
    DEPLOYMENT = "deployment"
    FEATURE_FLAG = "feature_flag"
    RELEASE = "release"
    EMOJI = "emoji"
    ACCESS_TOKEN = "access_token"
    MEMBER = "member"
    SUBGROUP = "subgroup"
    VULNERABILITY = "vulnerability"
    WORK_ITEM = "work_item"
    UNKNOWN = "unknown"


class Status(StrEnum):
    """Statuses we know (merge request actions, pipeline/job/deployment statuses).
    GitLab may send others: they are kept as the raw string."""

    PUSHED = "pushed"
    # merge request / issue
    OPENED = "opened"
    REOPENED = "reopened"
    UPDATED = "updated"
    MERGED = "merged"
    CLOSED = "closed"
    APPROVED = "approved"
    UNAPPROVED = "unapproved"
    APPROVAL = "approval"
    UNAPPROVAL = "unapproval"
    # pipeline / job / deployment
    CREATED = "created"
    PREPARING = "preparing"
    WAITING_FOR_RESOURCE = "waiting_for_resource"
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    SKIPPED = "skipped"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    BLOCKED = "blocked"


# Kinds that are forwarded to Telegram; the rest are stored and logged only.
TELEGRAM_KINDS = frozenset({EventKind.PUSH, EventKind.MERGE_REQUEST, EventKind.PIPELINE})

# value of the X-Gitlab-Event header -> kind
EVENT_HEADERS: dict[str, EventKind] = {
    "Push Hook": EventKind.PUSH,
    "Tag Push Hook": EventKind.TAG_PUSH,
    "Issue Hook": EventKind.ISSUE,
    "Confidential Issue Hook": EventKind.ISSUE,
    "Note Hook": EventKind.NOTE,
    "Confidential Note Hook": EventKind.NOTE,
    "Merge Request Hook": EventKind.MERGE_REQUEST,
    "Wiki Page Hook": EventKind.WIKI_PAGE,
    "Pipeline Hook": EventKind.PIPELINE,
    "Job Hook": EventKind.JOB,
    "Deployment Hook": EventKind.DEPLOYMENT,
    "Feature Flag Hook": EventKind.FEATURE_FLAG,
    "Release Hook": EventKind.RELEASE,
    "Emoji Hook": EventKind.EMOJI,
    "Resource Access Token Hook": EventKind.ACCESS_TOKEN,
    "Project Access Token Hook": EventKind.ACCESS_TOKEN,
    "Group Access Token Hook": EventKind.ACCESS_TOKEN,
    "Member Hook": EventKind.MEMBER,
    "Subgroup Hook": EventKind.SUBGROUP,
    "Vulnerability Hook": EventKind.VULNERABILITY,
    "Work Item Hook": EventKind.WORK_ITEM,
}

# fallback when the X-Gitlab-Event header is missing: the payload's `object_kind`
OBJECT_KINDS: dict[str, EventKind] = {
    "push": EventKind.PUSH,
    "tag_push": EventKind.TAG_PUSH,
    "issue": EventKind.ISSUE,
    "note": EventKind.NOTE,
    "merge_request": EventKind.MERGE_REQUEST,
    "wiki_page": EventKind.WIKI_PAGE,
    "pipeline": EventKind.PIPELINE,
    "build": EventKind.JOB,
    "deployment": EventKind.DEPLOYMENT,
    "feature_flag": EventKind.FEATURE_FLAG,
    "release": EventKind.RELEASE,
    "emoji": EventKind.EMOJI,
    "access_token": EventKind.ACCESS_TOKEN,
    "project_member": EventKind.MEMBER,
    "group_member": EventKind.MEMBER,
    "subgroup": EventKind.SUBGROUP,
    "vulnerability": EventKind.VULNERABILITY,
    "work_item": EventKind.WORK_ITEM,
}

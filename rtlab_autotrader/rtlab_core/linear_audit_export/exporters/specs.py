from __future__ import annotations

from ..schema import SelectionSpec


USER_REF = SelectionSpec(
    scalars=("id", "name", "displayName", "email", "avatarUrl", "active", "url"),
)
TEAM_REF = SelectionSpec(
    scalars=("id", "key", "name", "description", "private", "archivedAt", "createdAt", "updatedAt"),
)
WORKFLOW_STATE_REF = SelectionSpec(
    scalars=("id", "name", "description", "type", "position", "createdAt", "updatedAt", "archivedAt"),
)
LABEL_REF = SelectionSpec(
    scalars=("id", "name", "color", "description", "isGroup", "createdAt", "updatedAt"),
)
PROJECT_STATUS_REF = SelectionSpec(
    scalars=("id", "name", "type", "description", "position", "createdAt", "updatedAt"),
)
PROJECT_MILESTONE_REF = SelectionSpec(
    scalars=("id", "name", "description", "targetDate", "createdAt", "updatedAt"),
)
PROJECT_REF = SelectionSpec(
    scalars=(
        "id",
        "name",
        "summary",
        "description",
        "slugId",
        "priority",
        "url",
        "createdAt",
        "startedAt",
        "targetDate",
        "completedAt",
        "canceledAt",
        "updatedAt",
    ),
    objects={"status": PROJECT_STATUS_REF, "lead": USER_REF, "creator": USER_REF},
)
INITIATIVE_REF = SelectionSpec(
    scalars=(
        "id",
        "name",
        "summary",
        "description",
        "url",
        "createdAt",
        "startedAt",
        "targetDate",
        "completedAt",
        "updatedAt",
    ),
    objects={"creator": USER_REF, "owner": USER_REF},
)
CYCLE_REF = SelectionSpec(
    scalars=("id", "number", "name", "startsAt", "endsAt", "completedAt", "createdAt", "updatedAt"),
)
ISSUE_REF = SelectionSpec(
    scalars=("id", "identifier", "title", "url", "createdAt", "updatedAt", "archivedAt"),
    objects={"team": TEAM_REF, "state": WORKFLOW_STATE_REF},
)
CUSTOMER_STATUS_REF = SelectionSpec(
    scalars=("id", "name", "color", "description", "position", "createdAt", "updatedAt"),
)
CUSTOMER_TIER_REF = SelectionSpec(
    scalars=("id", "name", "color", "description", "position", "createdAt", "updatedAt"),
)
CUSTOMER_REF = SelectionSpec(
    scalars=("id", "name", "domains", "externalIds", "revenue", "size", "url", "createdAt", "updatedAt"),
    objects={"owner": USER_REF, "status": CUSTOMER_STATUS_REF, "tier": CUSTOMER_TIER_REF},
)
ATTACHMENT_REF = SelectionSpec(
    scalars=("id", "title", "subtitle", "url", "metadata", "source", "sourceType", "createdAt", "updatedAt"),
)
COMMENT_REF = SelectionSpec(
    scalars=("id", "body", "bodyData", "quotedText", "resolvedAt", "createdAt", "updatedAt", "url"),
    objects={"user": USER_REF},
)
DOCUMENT_REF = SelectionSpec(
    scalars=("id", "title", "summary", "content", "contentState", "documentContentId", "url", "createdAt", "updatedAt"),
)

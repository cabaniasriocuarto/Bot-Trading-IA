from __future__ import annotations

from typing import Any

from ..graphql import GraphQLExecutionError
from ..schema import SelectionSpec
from ..session import ExportSession
from ..utils import detect_upload_urls, normalize_filename, write_json
from .common import paginate_issue_connection, paginate_root_connection
from .specs import (
    ATTACHMENT_REF,
    COMMENT_REF,
    CUSTOMER_REF,
    DOCUMENT_REF,
    CYCLE_REF,
    INITIATIVE_REF,
    ISSUE_REF,
    LABEL_REF,
    PROJECT_MILESTONE_REF,
    PROJECT_REF,
    TEAM_REF,
    USER_REF,
    WORKFLOW_STATE_REF,
)


ISSUE_BASE_REF = SelectionSpec(
    scalars=(
        "id",
        "identifier",
        "title",
        "description",
        "descriptionState",
        "priority",
        "estimate",
        "sortOrder",
        "branchName",
        "createdAt",
        "updatedAt",
        "startedAt",
        "triagedAt",
        "completedAt",
        "canceledAt",
        "archivedAt",
        "dueDate",
        "slaStartedAt",
        "slaBreachesAt",
        "url",
    ),
    objects={
        "team": TEAM_REF,
        "state": WORKFLOW_STATE_REF,
        "creator": USER_REF,
        "assignee": USER_REF,
        "delegate": USER_REF,
        "project": PROJECT_REF,
        "projectMilestone": PROJECT_MILESTONE_REF,
        "initiative": INITIATIVE_REF,
        "cycle": CYCLE_REF,
        "parent": ISSUE_REF,
    },
)
ISSUE_RELATION_REF = SelectionSpec(
    scalars=("id", "type", "createdAt", "updatedAt"),
    objects={"issue": ISSUE_REF, "relatedIssue": ISSUE_REF},
)
ISSUE_CHILD_REF = SelectionSpec(
    scalars=("id", "identifier", "title", "description", "priority", "createdAt", "updatedAt", "url"),
    objects={"team": TEAM_REF, "state": WORKFLOW_STATE_REF, "assignee": USER_REF},
)
ISSUE_CUSTOMER_NEED_REF = SelectionSpec(
    scalars=("id", "body", "bodyData", "priority", "url", "createdAt", "updatedAt", "archivedAt"),
    objects={"customer": CUSTOMER_REF, "creator": USER_REF},
)


def _issue_labels_block(session: ExportSession, indent: int = 6) -> str:
    label_selection = session.catalog.render_selection("IssueLabel", LABEL_REF, indent=indent + 4)
    if not session.catalog.has_field("Issue", "labels") or not label_selection.strip():
        return ""
    return f"""
      labels {{
        nodes {{
{label_selection}
        }}
      }}
"""


def _comment_query(selection: str) -> str:
    return f"""
query IssueComments($id: String!, $first: Int!, $after: String) {{
  issue(id: $id) {{
    comments(first: $first, after: $after) {{
      nodes {{
{selection}
        parent {{ id }}
      }}
      pageInfo {{ hasNextPage endCursor }}
    }}
  }}
}}
"""


def _relation_query(selection: str) -> str:
    return f"""
query IssueRelations($id: String!, $first: Int!, $after: String) {{
  issue(id: $id) {{
    relations(first: $first, after: $after) {{
      nodes {{
{selection}
      }}
      pageInfo {{ hasNextPage endCursor }}
    }}
  }}
}}
"""


def _attachments_query(selection: str) -> str:
    return f"""
query IssueAttachments($id: String!, $first: Int!, $after: String) {{
  issue(id: $id) {{
    attachments(first: $first, after: $after) {{
      nodes {{
{selection}
      }}
      pageInfo {{ hasNextPage endCursor }}
    }}
  }}
}}
"""


def _documents_query(selection: str) -> str:
    return f"""
query IssueDocuments($id: String!, $first: Int!, $after: String) {{
  issue(id: $id) {{
    documents(first: $first, after: $after) {{
      nodes {{
{selection}
      }}
      pageInfo {{ hasNextPage endCursor }}
    }}
  }}
}}
"""


def _needs_query(selection: str) -> str:
    return f"""
query IssueNeeds($id: String!, $first: Int!, $after: String) {{
  issue(id: $id) {{
    needs(first: $first, after: $after) {{
      nodes {{
{selection}
      }}
      pageInfo {{ hasNextPage endCursor }}
    }}
  }}
}}
"""


def _subscribers_query(selection: str) -> str:
    return f"""
query IssueSubscribers($id: String!, $first: Int!, $after: String) {{
  issue(id: $id) {{
    subscribers(first: $first, after: $after) {{
      nodes {{
{selection}
      }}
      pageInfo {{ hasNextPage endCursor }}
    }}
  }}
}}
"""


def _children_query(selection: str) -> str:
    return f"""
query IssueChildren($id: String!, $first: Int!, $after: String) {{
  issue(id: $id) {{
    children(first: $first, after: $after) {{
      nodes {{
{selection}
      }}
      pageInfo {{ hasNextPage endCursor }}
    }}
  }}
}}
"""


def _issue_lookup_id(issue: dict[str, Any]) -> str:
    return str(issue.get("identifier") or issue.get("id") or "").strip()


def _record_text_candidates(session: ExportSession, entity_type: str, entity: dict[str, Any], identifier: str | None = None) -> None:
    entity_id = str(entity.get("id") or "")
    urls = detect_upload_urls(entity)
    for url in urls:
        session.add_attachment_candidate(
            {
                "source_entity_type": entity_type,
                "source_entity_id": entity_id,
                "source_entity_identifier": identifier or str(entity.get("identifier") or ""),
                "original_url": url,
                "status": "pending",
            }
        )


def export_issues(session: ExportSession) -> None:
    catalog = session.catalog
    issue_selection = catalog.render_selection("Issue", ISSUE_BASE_REF, indent=6)
    labels_block = _issue_labels_block(session)
    issues_query = f"""
query Issues($first: Int!, $after: String) {{
  issues(first: $first, after: $after, includeArchived: true, orderBy: updatedAt) {{
    nodes {{
{issue_selection}
{labels_block.rstrip()}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""

    limit = session.context.settings.max_issues or session.context.settings.test_limit
    issues = paginate_root_connection(
        session,
        checkpoint_key="issues.base",
        root_field="issues",
        query=issues_query,
        item_limit=limit,
    )
    session.context.stats.total_issues = len(issues)

    comment_selection = catalog.render_selection("Comment", COMMENT_REF, indent=8)
    relation_selection = catalog.render_selection("IssueRelation", ISSUE_RELATION_REF, indent=8)
    attachment_selection = catalog.render_selection("Attachment", ATTACHMENT_REF, indent=8)
    document_selection = catalog.render_selection("Document", DOCUMENT_REF, indent=8)
    need_selection = catalog.render_selection("CustomerNeed", ISSUE_CUSTOMER_NEED_REF, indent=8)
    subscriber_selection = catalog.render_selection("User", USER_REF, indent=8)
    child_selection = catalog.render_selection("Issue", ISSUE_CHILD_REF, indent=8)

    comments_query = _comment_query(comment_selection)
    relations_query = _relation_query(relation_selection)
    attachments_query = _attachments_query(attachment_selection)
    documents_query = _documents_query(document_selection)
    needs_query = _needs_query(need_selection)
    subscribers_query = _subscribers_query(subscriber_selection)
    children_query = _children_query(child_selection)

    index_rows: list[dict[str, Any]] = []
    for issue in issues:
        lookup_id = _issue_lookup_id(issue)
        if not lookup_id:
            session.context.stats.warn("Se encontro una issue sin id ni identifier util para detail fetch.")
            continue
        issue_key = normalize_filename(str(issue.get("identifier") or issue.get("id") or "issue"))
        comments: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        needs: list[dict[str, Any]] = []
        subscribers: list[dict[str, Any]] = []
        children: list[dict[str, Any]] = []

        try:
            comments = paginate_issue_connection(
                session,
                issue_id=lookup_id,
                checkpoint_key=f"issues.comments.{issue_key}",
                issue_field="comments",
                query=comments_query,
            )
            relations = paginate_issue_connection(
                session,
                issue_id=lookup_id,
                checkpoint_key=f"issues.relations.{issue_key}",
                issue_field="relations",
                query=relations_query,
            )
            attachments = paginate_issue_connection(
                session,
                issue_id=lookup_id,
                checkpoint_key=f"issues.attachments.{issue_key}",
                issue_field="attachments",
                query=attachments_query,
            )
            documents = paginate_issue_connection(
                session,
                issue_id=lookup_id,
                checkpoint_key=f"issues.documents.{issue_key}",
                issue_field="documents",
                query=documents_query,
            )
            needs = paginate_issue_connection(
                session,
                issue_id=lookup_id,
                checkpoint_key=f"issues.needs.{issue_key}",
                issue_field="needs",
                query=needs_query,
            )
            subscribers = paginate_issue_connection(
                session,
                issue_id=lookup_id,
                checkpoint_key=f"issues.subscribers.{issue_key}",
                issue_field="subscribers",
                query=subscribers_query,
            )
            children = paginate_issue_connection(
                session,
                issue_id=lookup_id,
                checkpoint_key=f"issues.children.{issue_key}",
                issue_field="children",
                query=children_query,
            )
        except GraphQLExecutionError as exc:
            session.context.stats.warn(f"Issue detail parcial para {lookup_id}: {exc}")

        payload = {
            **issue,
            "subscribers": subscribers,
            "children": children,
            "attachments_export": attachments,
            "documents_export": documents,
            "customer_requests_export": needs,
        }
        write_json(session.context.paths.issues_by_identifier / f"{issue_key}.json", payload)
        write_json(
            session.context.paths.issues_comments / f"{issue_key}.comments.json",
            {"issue_id": issue.get("id"), "issue_identifier": issue.get("identifier"), "comments": comments},
        )
        write_json(
            session.context.paths.issues_relations / f"{issue_key}.relations.json",
            {"issue_id": issue.get("id"), "issue_identifier": issue.get("identifier"), "relations": relations},
        )

        _record_text_candidates(session, "issue", payload, str(issue.get("identifier") or ""))
        for comment in comments:
            _record_text_candidates(session, "issue_comment", comment, str(issue.get("identifier") or ""))
        for document in documents:
            _record_text_candidates(session, "issue_document", document, str(issue.get("identifier") or ""))
        for attachment in attachments:
            url = str(attachment.get("url") or "").strip()
            if url:
                session.add_attachment_candidate(
                    {
                        "source_entity_type": "issue_attachment",
                        "source_entity_id": str(attachment.get("id") or ""),
                        "source_entity_identifier": str(issue.get("identifier") or ""),
                        "original_url": url,
                        "status": "pending",
                    }
                )

        index_rows.append(
            {
                "id": issue.get("id"),
                "identifier": issue.get("identifier"),
                "title": issue.get("title"),
                "path": f"issues/by_identifier/{issue_key}.json",
                "comments_path": f"issues/comments/{issue_key}.comments.json",
                "relations_path": f"issues/relations/{issue_key}.relations.json",
            }
        )
        session.context.stats.total_issue_comments += len(comments)
        session.context.stats.total_issue_relations += len(relations)

    write_json(session.context.paths.issues / "index.json", index_rows)

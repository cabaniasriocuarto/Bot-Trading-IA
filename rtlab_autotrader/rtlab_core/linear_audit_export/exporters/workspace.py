from __future__ import annotations

from typing import Any

from ..schema import SelectionSpec
from ..session import ExportSession
from ..utils import write_json
from .common import paginate_root_connection
from .specs import CUSTOMER_STATUS_REF, CUSTOMER_TIER_REF, LABEL_REF, PROJECT_STATUS_REF, TEAM_REF, USER_REF, WORKFLOW_STATE_REF


ORGANIZATION_REF = SelectionSpec(
    scalars=("id", "name", "urlKey", "logoUrl", "createdAt", "updatedAt"),
)
CUSTOM_VIEW_REF = SelectionSpec(
    scalars=(
        "id",
        "name",
        "description",
        "icon",
        "color",
        "slugId",
        "shared",
        "modelName",
        "filterData",
        "projectFilterData",
        "initiativeFilterData",
        "createdAt",
        "updatedAt",
    ),
    objects={"creator": USER_REF, "team": TEAM_REF},
)
TEMPLATE_REF = SelectionSpec(
    scalars=("id", "name", "description", "templateData", "createdAt", "updatedAt", "archivedAt"),
    objects={"creator": USER_REF, "team": TEAM_REF},
)


def export_workspace_core(session: ExportSession) -> dict[str, Any]:
    catalog = session.catalog
    viewer_selection = catalog.render_selection("User", USER_REF, indent=4)
    organization_selection = catalog.render_selection("Organization", ORGANIZATION_REF, indent=4)
    viewer_query = f"query Viewer {{ viewer {{\n{viewer_selection}\n  }} }}"
    org_query = f"query Organization {{ organization {{\n{organization_selection}\n  }} }}"
    viewer_exec = session.client.execute(viewer_query)
    organization_exec = session.client.execute(org_query)
    viewer = viewer_exec.data.get("viewer") if isinstance(viewer_exec.data.get("viewer"), dict) else {}
    organization = organization_exec.data.get("organization") if isinstance(organization_exec.data.get("organization"), dict) else {}
    session.viewer = viewer
    session.organization = organization
    write_json(session.context.paths.workspace / "viewer.json", viewer)
    write_json(session.context.paths.workspace / "organization.json", organization)
    return {"viewer": viewer, "organization": organization}


def export_workspace_collections(session: ExportSession) -> None:
    catalog = session.catalog

    teams_selection = catalog.render_selection("Team", TEAM_REF, indent=6)
    users_selection = catalog.render_selection("User", USER_REF, indent=6)
    states_selection = catalog.render_selection("WorkflowState", WORKFLOW_STATE_REF, indent=6)
    labels_selection = catalog.render_selection("IssueLabel", LABEL_REF, indent=6)
    views_selection = catalog.render_selection("CustomView", CUSTOM_VIEW_REF, indent=6)
    project_status_selection = catalog.render_selection("ProjectStatus", PROJECT_STATUS_REF, indent=6)
    customer_status_selection = catalog.render_selection("CustomerStatus", CUSTOMER_STATUS_REF, indent=6)
    customer_tier_selection = catalog.render_selection("CustomerTier", CUSTOMER_TIER_REF, indent=6)
    templates_selection = catalog.render_selection("Template", TEMPLATE_REF, indent=4)

    teams_query = f"""
query Teams($first: Int!, $after: String) {{
  teams(first: $first, after: $after, includeArchived: true) {{
    nodes {{
{teams_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    users_query = f"""
query Users($first: Int!, $after: String) {{
  users(first: $first, after: $after) {{
    nodes {{
{users_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    states_query = f"""
query WorkflowStates($first: Int!, $after: String) {{
  workflowStates(first: $first, after: $after) {{
    nodes {{
{states_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    labels_query = f"""
query IssueLabels($first: Int!, $after: String) {{
  issueLabels(first: $first, after: $after) {{
    nodes {{
{labels_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    views_query = f"""
query CustomViews($first: Int!, $after: String) {{
  customViews(first: $first, after: $after) {{
    nodes {{
{views_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    project_status_query = f"""
query ProjectStatuses($first: Int!, $after: String) {{
  projectStatuses(first: $first, after: $after) {{
    nodes {{
{project_status_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    customer_status_query = f"""
query CustomerStatuses($first: Int!, $after: String) {{
  customerStatuses(first: $first, after: $after) {{
    nodes {{
{customer_status_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    customer_tier_query = f"""
query CustomerTiers($first: Int!, $after: String) {{
  customerTiers(first: $first, after: $after) {{
    nodes {{
{customer_tier_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    templates_query = f"query Templates {{ templates {{\n{templates_selection}\n  }} }}"

    teams = paginate_root_connection(session, checkpoint_key="workspace.teams", root_field="teams", query=teams_query)
    users = paginate_root_connection(session, checkpoint_key="workspace.users", root_field="users", query=users_query)
    states = paginate_root_connection(
        session,
        checkpoint_key="workspace.workflow_states",
        root_field="workflowStates",
        query=states_query,
    )
    labels = paginate_root_connection(session, checkpoint_key="workspace.issue_labels", root_field="issueLabels", query=labels_query)
    views = paginate_root_connection(session, checkpoint_key="workspace.custom_views", root_field="customViews", query=views_query)
    project_statuses = paginate_root_connection(
        session,
        checkpoint_key="workspace.project_statuses",
        root_field="projectStatuses",
        query=project_status_query,
    )
    templates_exec = session.client.execute(templates_query)
    templates = templates_exec.data.get("templates") if isinstance(templates_exec.data.get("templates"), list) else []

    write_json(session.context.paths.workspace / "teams.json", teams)
    write_json(session.context.paths.workspace / "users.json", users)
    write_json(session.context.paths.workspace / "states.json", states)
    write_json(session.context.paths.workspace / "labels.json", labels)
    write_json(session.context.paths.workspace / "views.json", views)
    write_json(session.context.paths.workspace / "project_statuses.json", project_statuses)
    write_json(session.context.paths.workspace / "templates.json", templates)

    session.context.stats.total_teams = len(teams)
    session.context.stats.total_users = len(users)
    session.context.stats.total_states = len(states)
    session.context.stats.total_labels = len(labels)
    session.context.stats.total_views = len(views)
    session.context.stats.total_templates = len(templates)

    if session.context.settings.include_customers:
        customer_statuses = paginate_root_connection(
            session,
            checkpoint_key="workspace.customer_statuses",
            root_field="customerStatuses",
            query=customer_status_query,
        )
        customer_tiers = paginate_root_connection(
            session,
            checkpoint_key="workspace.customer_tiers",
            root_field="customerTiers",
            query=customer_tier_query,
        )
        write_json(session.context.paths.customers / "customer_statuses.json", customer_statuses)
        write_json(session.context.paths.customers / "customer_tiers.json", customer_tiers)
        session.context.stats.total_customer_statuses = len(customer_statuses)
        session.context.stats.total_customer_tiers = len(customer_tiers)

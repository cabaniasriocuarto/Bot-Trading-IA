from __future__ import annotations

from ..schema import SelectionSpec
from ..session import ExportSession
from ..utils import write_json
from .common import paginate_root_connection
from .specs import CYCLE_REF, DOCUMENT_REF, INITIATIVE_REF, ISSUE_REF, PROJECT_MILESTONE_REF, PROJECT_REF, TEAM_REF, USER_REF


PROJECT_UPDATE_REF = SelectionSpec(
    scalars=("id", "body", "bodyData", "health", "createdAt", "updatedAt"),
    objects={"user": USER_REF, "project": PROJECT_REF},
)
INITIATIVE_UPDATE_REF = SelectionSpec(
    scalars=("id", "body", "bodyData", "health", "createdAt", "updatedAt"),
    objects={"user": USER_REF, "initiative": INITIATIVE_REF},
)
DOCUMENT_TOP_REF = SelectionSpec(
    scalars=("id", "title", "summary", "content", "contentState", "documentContentId", "url", "createdAt", "updatedAt"),
    objects={
        "creator": USER_REF,
        "project": PROJECT_REF,
        "initiative": INITIATIVE_REF,
        "issue": ISSUE_REF,
        "team": TEAM_REF,
        "cycle": CYCLE_REF,
    },
)


def export_delivery(session: ExportSession) -> None:
    catalog = session.catalog
    projects_selection = catalog.render_selection("Project", PROJECT_REF, indent=6)
    milestones_selection = catalog.render_selection("ProjectMilestone", PROJECT_MILESTONE_REF, indent=6)
    project_updates_selection = catalog.render_selection("ProjectUpdate", PROJECT_UPDATE_REF, indent=6)
    initiatives_selection = catalog.render_selection("Initiative", INITIATIVE_REF, indent=6)
    initiative_updates_selection = catalog.render_selection("InitiativeUpdate", INITIATIVE_UPDATE_REF, indent=6)
    cycles_selection = catalog.render_selection("Cycle", CYCLE_REF, indent=6)
    documents_selection = catalog.render_selection("Document", DOCUMENT_TOP_REF, indent=6)

    projects_query = f"""
query Projects($first: Int!, $after: String) {{
  projects(first: $first, after: $after, includeArchived: true) {{
    nodes {{
{projects_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    milestones_query = f"""
query ProjectMilestones($first: Int!, $after: String) {{
  projectMilestones(first: $first, after: $after) {{
    nodes {{
{milestones_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    project_updates_query = f"""
query ProjectUpdates($first: Int!, $after: String) {{
  projectUpdates(first: $first, after: $after, includeArchived: true) {{
    nodes {{
{project_updates_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    initiatives_query = f"""
query Initiatives($first: Int!, $after: String) {{
  initiatives(first: $first, after: $after, includeArchived: true) {{
    nodes {{
{initiatives_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    initiative_updates_query = f"""
query InitiativeUpdates($first: Int!, $after: String) {{
  initiativeUpdates(first: $first, after: $after, includeArchived: true) {{
    nodes {{
{initiative_updates_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    cycles_query = f"""
query Cycles($first: Int!, $after: String) {{
  cycles(first: $first, after: $after) {{
    nodes {{
{cycles_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    documents_query = f"""
query Documents($first: Int!, $after: String) {{
  documents(first: $first, after: $after) {{
    nodes {{
{documents_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""

    projects = paginate_root_connection(session, checkpoint_key="delivery.projects", root_field="projects", query=projects_query)
    milestones = paginate_root_connection(
        session,
        checkpoint_key="delivery.project_milestones",
        root_field="projectMilestones",
        query=milestones_query,
    )
    project_updates = paginate_root_connection(
        session,
        checkpoint_key="delivery.project_updates",
        root_field="projectUpdates",
        query=project_updates_query,
    )
    initiatives = paginate_root_connection(
        session,
        checkpoint_key="delivery.initiatives",
        root_field="initiatives",
        query=initiatives_query,
    )
    initiative_updates = paginate_root_connection(
        session,
        checkpoint_key="delivery.initiative_updates",
        root_field="initiativeUpdates",
        query=initiative_updates_query,
    )
    cycles = paginate_root_connection(session, checkpoint_key="delivery.cycles", root_field="cycles", query=cycles_query)
    documents = paginate_root_connection(
        session,
        checkpoint_key="delivery.documents",
        root_field="documents",
        query=documents_query,
    )

    write_json(session.context.paths.delivery / "projects.json", projects)
    write_json(session.context.paths.delivery / "project_milestones.json", milestones)
    write_json(session.context.paths.delivery / "project_updates.json", project_updates)
    write_json(session.context.paths.delivery / "initiatives.json", initiatives)
    write_json(session.context.paths.delivery / "initiative_updates.json", initiative_updates)
    write_json(session.context.paths.delivery / "cycles.json", cycles)
    write_json(session.context.paths.delivery / "documents.json", documents)

    session.context.stats.total_projects = len(projects)
    session.context.stats.total_project_milestones = len(milestones)
    session.context.stats.total_project_updates = len(project_updates)
    session.context.stats.total_initiatives = len(initiatives)
    session.context.stats.total_initiative_updates = len(initiative_updates)
    session.context.stats.total_cycles = len(cycles)
    session.context.stats.total_documents = len(documents)

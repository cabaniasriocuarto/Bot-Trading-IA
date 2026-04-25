from __future__ import annotations

from ..schema import SelectionSpec
from ..session import ExportSession
from ..utils import write_json
from .common import paginate_root_connection
from .specs import USER_REF


AUDIT_ENTRY_REF = SelectionSpec(
    scalars=("id", "type", "actorId", "ip", "countryCode", "metadata", "requestInformation", "createdAt", "updatedAt"),
    objects={"actor": USER_REF},
)


def export_audit(session: ExportSession) -> None:
    catalog = session.catalog
    selection = catalog.render_selection("AuditEntry", AUDIT_ENTRY_REF, indent=6)
    query = f"""
query AuditEntries($first: Int!, $after: String) {{
  auditEntries(first: $first, after: $after) {{
    nodes {{
{selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    rows = paginate_root_connection(session, checkpoint_key="audit.entries", root_field="auditEntries", query=query)
    write_json(session.context.paths.audit / "audit_entries.json", rows)
    session.context.stats.total_audit_entries = len(rows)

from __future__ import annotations

from ..schema import SelectionSpec
from ..session import ExportSession
from ..utils import write_json
from .common import paginate_root_connection
from .specs import ATTACHMENT_REF, COMMENT_REF, CUSTOMER_REF, ISSUE_REF, PROJECT_REF, USER_REF


CUSTOMER_NEED_REF = SelectionSpec(
    scalars=("id", "body", "bodyData", "priority", "url", "createdAt", "updatedAt", "archivedAt"),
    objects={
        "customer": CUSTOMER_REF,
        "issue": ISSUE_REF,
        "project": PROJECT_REF,
        "comment": COMMENT_REF,
        "attachment": ATTACHMENT_REF,
        "creator": USER_REF,
        "originalIssue": ISSUE_REF,
    },
)


def export_customers(session: ExportSession) -> None:
    catalog = session.catalog
    customers_selection = catalog.render_selection("Customer", CUSTOMER_REF, indent=6)
    customer_needs_selection = catalog.render_selection("CustomerNeed", CUSTOMER_NEED_REF, indent=6)

    customers_query = f"""
query Customers($first: Int!, $after: String) {{
  customers(first: $first, after: $after, includeArchived: true) {{
    nodes {{
{customers_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    customer_needs_query = f"""
query CustomerNeeds($first: Int!, $after: String) {{
  customerNeeds(first: $first, after: $after) {{
    nodes {{
{customer_needs_selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""

    customers = paginate_root_connection(
        session,
        checkpoint_key="customers.customers",
        root_field="customers",
        query=customers_query,
    )
    customer_needs = paginate_root_connection(
        session,
        checkpoint_key="customers.customer_needs",
        root_field="customerNeeds",
        query=customer_needs_query,
    )

    write_json(session.context.paths.customers / "customers.json", customers)
    write_json(session.context.paths.customers / "customer_requests.json", customer_needs)

    session.context.stats.total_customers = len(customers)
    session.context.stats.total_customer_requests = len(customer_needs)

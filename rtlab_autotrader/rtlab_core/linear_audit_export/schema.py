from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .graphql import GraphQLClient
from .utils import write_json


ROOT_FIELDS_QUERY = "query { __schema { queryType { fields { name } } } }"
ROOT_ARGS_QUERY = """
query {
  __type(name: "Query") {
    fields(includeDeprecated: true) {
      name
      args {
        name
        defaultValue
        type {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }
  }
}
"""
TYPE_QUERY = """
query TypeDefinition($name: String!) {
  __type(name: $name) {
    name
    kind
    fields(includeDeprecated: true) {
      name
      isDeprecated
      deprecationReason
      type {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
            }
          }
        }
      }
    }
  }
}
"""

RELEVANT_TYPES = [
    "Organization",
    "User",
    "Team",
    "WorkflowState",
    "IssueLabel",
    "CustomView",
    "Template",
    "Project",
    "ProjectMilestone",
    "ProjectUpdate",
    "ProjectStatus",
    "Document",
    "Initiative",
    "InitiativeUpdate",
    "Cycle",
    "Issue",
    "Comment",
    "IssueRelation",
    "Attachment",
    "Customer",
    "CustomerNeed",
    "CustomerStatus",
    "CustomerTier",
    "AuditEntry",
]

QUERY_PROBES = {
    "viewer": "query { viewer { id name email } }",
    "organization": "query { organization { id name } }",
    "teams": "query { teams(first: 1, includeArchived: true) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "users": "query { users(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "workflowStates": "query { workflowStates(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "issueLabels": "query { issueLabels(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "customViews": "query { customViews(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "templates": "query { templates { id name } }",
    "projects": "query { projects(first: 1, includeArchived: true) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "projectMilestones": "query { projectMilestones(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "projectUpdates": "query { projectUpdates(first: 1, includeArchived: true) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "projectStatuses": "query { projectStatuses(first: 1) { pageInfo { hasNextPage endCursor } nodes { id name } } }",
    "documents": "query { documents(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "initiatives": "query { initiatives(first: 1, includeArchived: true) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "initiativeUpdates": "query { initiativeUpdates(first: 1, includeArchived: true) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "cycles": "query { cycles(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "issues": "query { issues(first: 1, includeArchived: true, orderBy: updatedAt) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "issue": "query { issue(id: \"ABC-1\") { id } }",
    "comments": "query { comments(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "issueRelations": "query { issueRelations(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "attachments": "query { attachments(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "customers": "query { customers(first: 1, includeArchived: true) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "customerNeeds": "query { customerNeeds(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
    "customerStatuses": "query { customerStatuses(first: 1) { pageInfo { hasNextPage endCursor } nodes { id name } } }",
    "customerTiers": "query { customerTiers(first: 1) { pageInfo { hasNextPage endCursor } nodes { id name } } }",
    "auditEntries": "query { auditEntries(first: 1) { pageInfo { hasNextPage endCursor } nodes { id } } }",
}


def _unwrap_type(type_ref: dict[str, Any] | None) -> dict[str, Any]:
    chain: list[str] = []
    current = type_ref or {}
    while current:
        kind = current.get("kind")
        if kind:
            chain.append(str(kind))
        if current.get("ofType"):
            current = current["ofType"]
            continue
        return {"kind_chain": chain, "named_type": current.get("name"), "terminal_kind": current.get("kind")}
    return {"kind_chain": chain, "named_type": None, "terminal_kind": None}


@dataclass(slots=True)
class SelectionSpec:
    scalars: tuple[str, ...] = ()
    objects: dict[str, "SelectionSpec"] = field(default_factory=dict)
    include_typename: bool = False


class SchemaCatalog:
    def __init__(self, summary: dict[str, Any]) -> None:
        self.summary = summary
        self.type_fields: dict[str, dict[str, dict[str, Any]]] = {}
        raw_types = summary.get("types") if isinstance(summary.get("types"), dict) else {}
        for type_name, payload in raw_types.items():
            fields = payload.get("fields") if isinstance(payload, dict) else {}
            if isinstance(fields, dict):
                self.type_fields[type_name] = fields

    def has_field(self, type_name: str, field_name: str) -> bool:
        return field_name in self.type_fields.get(type_name, {})

    def field_named_type(self, type_name: str, field_name: str) -> str | None:
        field = self.type_fields.get(type_name, {}).get(field_name) or {}
        return str(field.get("named_type")) if field.get("named_type") else None

    def render_selection(self, type_name: str, spec: SelectionSpec, *, indent: int = 0) -> str:
        if type_name not in self.type_fields:
            return ""
        spacing = " " * indent
        lines: list[str] = []
        if spec.include_typename:
            lines.append(f"{spacing}__typename")
        for field_name in spec.scalars:
            if self.has_field(type_name, field_name):
                lines.append(f"{spacing}{field_name}")
        for field_name, nested in spec.objects.items():
            target_type = self.field_named_type(type_name, field_name)
            if not target_type or not self.has_field(type_name, field_name):
                continue
            rendered = self.render_selection(target_type, nested, indent=indent + 2)
            if not rendered.strip():
                continue
            lines.append(f"{spacing}{field_name} {{")
            lines.append(rendered)
            lines.append(f"{spacing}}}")
        return "\n".join(lines)


def _classify_probe(status_code: int, errors: list[dict[str, Any]]) -> str:
    if status_code == 401:
        return "valid_requires_auth"
    if not errors:
        return "confirmed"
    for item in errors:
        extensions = item.get("extensions") if isinstance(item, dict) else {}
        code = str((extensions or {}).get("code") or "").upper()
        if code == "GRAPHQL_VALIDATION_FAILED":
            return "invalid"
    return "error"


def discover_schema(client: GraphQLClient, output_path: Any) -> dict[str, Any]:
    root_exec = client.execute(ROOT_FIELDS_QUERY, allow_unauthenticated=True)
    root_fields = sorted(
        field.get("name")
        for field in (((root_exec.data or {}).get("__schema") or {}).get("queryType") or {}).get("fields", [])
        if isinstance(field, dict) and field.get("name")
    )

    root_args_exec = client.execute(ROOT_ARGS_QUERY, allow_unauthenticated=True)
    root_arg_notes: list[str] = []
    if root_args_exec.errors:
        root_arg_notes.append("La introspeccion completa de args del tipo Query no entro en un request unico.")
        root_arg_notes.append("El exportador compensa esto con probes de queries minimas por dominio.")

    types: dict[str, Any] = {}
    for type_name in RELEVANT_TYPES:
        exec_result = client.execute(TYPE_QUERY, variables={"name": type_name}, allow_unauthenticated=True)
        current_type = (exec_result.data or {}).get("__type") or {}
        fields_map: dict[str, Any] = {}
        for field in current_type.get("fields") or []:
            if not isinstance(field, dict) or not field.get("name"):
                continue
            unwrapped = _unwrap_type(field.get("type"))
            fields_map[field["name"]] = {
                "kind_chain": unwrapped["kind_chain"],
                "named_type": unwrapped["named_type"],
                "terminal_kind": unwrapped["terminal_kind"],
                "is_deprecated": bool(field.get("isDeprecated")),
                "deprecation_reason": field.get("deprecationReason"),
            }
        types[type_name] = {
            "kind": current_type.get("kind"),
            "fields": fields_map,
        }

    probes: dict[str, Any] = {}
    for name, query in QUERY_PROBES.items():
        execution = client.execute(query, allow_unauthenticated=True)
        probes[name] = {
            "status": _classify_probe(execution.status_code, execution.errors),
            "status_code": execution.status_code,
            "errors": execution.errors,
        }

    summary = {
        "endpoint": client.settings.base_url,
        "introspection_supported": bool(root_fields),
        "root_fields": root_fields,
        "root_argument_discovery_notes": root_arg_notes,
        "types": types,
        "query_probes": probes,
        "notes": [
            "El schema se introspecto en vivo contra https://api.linear.app/graphql.",
            "Linear valida la query antes de exigir auth, por eso los probes diferencian entre 'valid_requires_auth' e 'invalid'.",
        ],
    }
    write_json(output_path, summary)
    return summary

from __future__ import annotations

from typing import Any

from ..session import ExportSession


def nodes_from_connection(connection: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(connection, dict):
        return []
    if isinstance(connection.get("nodes"), list):
        return [node for node in connection["nodes"] if isinstance(node, dict)]
    edges = connection.get("edges")
    if not isinstance(edges, list):
        return []
    nodes: list[dict[str, Any]] = []
    for edge in edges:
        if isinstance(edge, dict) and isinstance(edge.get("node"), dict):
            nodes.append(edge["node"])
    return nodes


def paginate_root_connection(
    session: ExportSession,
    *,
    checkpoint_key: str,
    root_field: str,
    query: str,
    variables: dict[str, Any] | None = None,
    item_limit: int = 0,
) -> list[dict[str, Any]]:
    cursor = session.checkpoint.get_cursor(checkpoint_key) if session.context.settings.resume else None
    collected: list[dict[str, Any]] = []
    while True:
        request_variables = dict(variables or {})
        request_variables.setdefault("first", session.context.settings.page_size)
        request_variables["after"] = cursor
        execution = session.client.execute(query, variables=request_variables)
        connection = execution.data.get(root_field)
        if not isinstance(connection, dict):
            break
        page_nodes = nodes_from_connection(connection)
        collected.extend(page_nodes)
        page_info = connection.get("pageInfo") if isinstance(connection.get("pageInfo"), dict) else {}
        cursor = page_info.get("endCursor")
        session.checkpoint.set_cursor(checkpoint_key, cursor if page_info.get("hasNextPage") else None)
        if item_limit and len(collected) >= item_limit:
            return collected[:item_limit]
        if not page_info.get("hasNextPage"):
            break
    return collected


def paginate_issue_connection(
    session: ExportSession,
    *,
    issue_id: str,
    checkpoint_key: str,
    issue_field: str,
    query: str,
) -> list[dict[str, Any]]:
    cursor = session.checkpoint.get_cursor(checkpoint_key) if session.context.settings.resume else None
    collected: list[dict[str, Any]] = []
    while True:
        execution = session.client.execute(
            query,
            variables={
                "id": issue_id,
                "first": session.context.settings.page_size,
                "after": cursor,
            },
        )
        issue_payload = execution.data.get("issue")
        if not isinstance(issue_payload, dict):
            break
        connection = issue_payload.get(issue_field)
        if not isinstance(connection, dict):
            break
        collected.extend(nodes_from_connection(connection))
        page_info = connection.get("pageInfo") if isinstance(connection.get("pageInfo"), dict) else {}
        cursor = page_info.get("endCursor")
        session.checkpoint.set_cursor(checkpoint_key, cursor if page_info.get("hasNextPage") else None)
        if not page_info.get("hasNextPage"):
            break
    return collected

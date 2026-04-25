from __future__ import annotations

from pathlib import Path
from typing import Any

from .manual_imports import build_manual_import_manifest
from .runtime import SnapshotPaths
from .utils import read_json, write_text


def render_issue_markdown(issue: dict[str, Any], comments: list[dict[str, Any]], relations: list[dict[str, Any]]) -> str:
    lines = [
        f"# {issue.get('identifier') or issue.get('id')}: {issue.get('title') or ''}",
        "",
        "## Metadata",
        f"- id: `{issue.get('id')}`",
        f"- identifier: `{issue.get('identifier')}`",
        f"- url: `{issue.get('url')}`",
        f"- priority: `{issue.get('priority')}`",
        f"- estimate: `{issue.get('estimate')}`",
        f"- dueDate: `{issue.get('dueDate')}`",
        f"- createdAt: `{issue.get('createdAt')}`",
        f"- updatedAt: `{issue.get('updatedAt')}`",
        "",
        "## Description",
        issue.get("description") or "",
        "",
    ]
    if issue.get("documentContent"):
        lines.extend(["## Document Content", issue.get("documentContent") or "", ""])
    if issue.get("attachments_export"):
        lines.append("## Attachments")
        for row in issue.get("attachments_export") or []:
            lines.append(f"- `{row.get('id')}` {row.get('title') or row.get('subtitle') or ''} -> {row.get('url')}")
        lines.append("")
    if issue.get("customer_requests_export"):
        lines.append("## Customer Requests")
        for row in issue.get("customer_requests_export") or []:
            lines.append(f"### Need {row.get('id')}")
            lines.append(row.get("body") or "")
            lines.append("")
    lines.append("## Comments")
    if not comments:
        lines.append("- none")
    else:
        for row in comments:
            lines.extend(
                [
                    f"### Comment {row.get('id')}",
                    f"- createdAt: `{row.get('createdAt')}`",
                    f"- updatedAt: `{row.get('updatedAt')}`",
                    f"- url: `{row.get('url')}`",
                    row.get("body") or "",
                    "",
                ]
            )
    lines.append("## Relations")
    if not relations:
        lines.append("- none")
    else:
        for row in relations:
            related = row.get("relatedIssue") if isinstance(row.get("relatedIssue"), dict) else {}
            lines.append(
                f"- `{row.get('type')}` -> `{related.get('identifier') or related.get('id')}` {related.get('title') or ''}"
            )
    lines.append("")
    return "\n".join(lines)


def render_project_markdown(project: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {project.get('name') or project.get('id')}",
            "",
            "## Metadata",
            f"- id: `{project.get('id')}`",
            f"- slugId: `{project.get('slugId')}`",
            f"- status: `{((project.get('status') or {}) if isinstance(project.get('status'), dict) else {}).get('name')}`",
            f"- targetDate: `{project.get('targetDate')}`",
            f"- completedAt: `{project.get('completedAt')}`",
            "",
            "## Summary",
            project.get("summary") or "",
            "",
            "## Description",
            project.get("description") or "",
            "",
        ]
    )


def render_initiative_markdown(initiative: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {initiative.get('name') or initiative.get('id')}",
            "",
            "## Metadata",
            f"- id: `{initiative.get('id')}`",
            f"- targetDate: `{initiative.get('targetDate')}`",
            f"- completedAt: `{initiative.get('completedAt')}`",
            "",
            "## Summary",
            initiative.get("summary") or "",
            "",
            "## Description",
            initiative.get("description") or "",
            "",
        ]
    )


def render_customer_markdown(customer: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {customer.get('name') or customer.get('id')}",
            "",
            f"- id: `{customer.get('id')}`",
            f"- domains: `{customer.get('domains')}`",
            f"- externalIds: `{customer.get('externalIds')}`",
            f"- url: `{customer.get('url')}`",
            "",
        ]
    )


def render_audit_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Audit Log", ""]
    for row in rows:
        lines.extend(
            [
                f"## {row.get('type')} {row.get('id')}",
                f"- createdAt: `{row.get('createdAt')}`",
                f"- actorId: `{row.get('actorId')}`",
                f"- ip: `{row.get('ip')}`",
                f"- countryCode: `{row.get('countryCode')}`",
                "",
                "```json",
                str(row.get("metadata") or {}),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def render_gaps_markdown(gaps_payload: dict[str, Any]) -> str:
    confirmed = gaps_payload.get("confirmado") if isinstance(gaps_payload.get("confirmado"), list) else []
    inferred = gaps_payload.get("inferido") if isinstance(gaps_payload.get("inferido"), list) else []
    pending = gaps_payload.get("pendiente_de_validar") if isinstance(gaps_payload.get("pendiente_de_validar"), list) else []
    lines = ["# GAPS AND LIMITATIONS", "", "## Confirmado"]
    if confirmed:
        lines.extend(f"- {item}" for item in confirmed)
    else:
        lines.append("- none")
    lines.extend(["", "## Inferido"])
    if inferred:
        lines.extend(f"- {item}" for item in inferred)
    else:
        lines.append("- none")
    lines.extend(["", "## Pendiente de validar"])
    if pending:
        lines.extend(f"- {item}" for item in pending)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def build_handoff_prompt() -> str:
    return """# AUDIT HANDOFF PROMPT

## Orden sugerido de lectura
1. `snapshot_meta/manifest.json`
2. `snapshot_meta/schema_summary.json`
3. `snapshot_meta/permissions_and_gaps.json`
4. `llm/EXPORT_SUMMARY.md`
5. `issues/index.json`
6. `llm/issues/*.md`
7. `delivery/projects.json`, `delivery/initiatives.json`, `delivery/project_updates.json`
8. `audit/audit_entries.json`

## Diferencia entre raw y llm
- `raw` preserva JSON canónico sin resumir.
- `llm` reordena el mismo contenido para auditoría humana/IA sin reemplazar el texto real.

## Cómo validar consistencia
- Cruza `issue.project.id` con `delivery/projects.json`.
- Cruza `issue.initiative.id` con `delivery/initiatives.json`.
- Cruza `issues/comments/*.json` y `issues/relations/*.json` contra `issues/index.json`.
- Usa `identifier`, `id` y `url` como claves de reconstrucción histórica.
- Revisa `attachments/metadata.json` para distinguir detectado vs descargado vs fallido.

## Cómo detectar contradicciones
- Busca project status vs issues reales.
- Busca issues con parent/sub-issues inconsistentes.
- Busca comments que cierren un bloque sin issue/project status equivalente.
- Busca entidades en raw sin render equivalente en llm.

## Cómo no inventar
- Si el dato no está en raw, no asumirlo.
- Si un campo falta en schema o por permisos, confirmar en `GAPS_AND_LIMITATIONS.md`.
- Diferenciar siempre dato exportado vs inferencia del auditor.
"""


def render_llm(paths: SnapshotPaths) -> None:
    manifest = read_json(paths.snapshot_meta / "manifest.json") or {}
    gaps = read_json(paths.snapshot_meta / "permissions_and_gaps.json") or {}
    manual_manifest = build_manual_import_manifest(paths.manual_imports)

    issues_index = read_json(paths.issues / "index.json") or []
    for row in issues_index:
        issue = read_json(paths.root / str(row.get("path"))) or {}
        comments_file = paths.root / str(row.get("comments_path"))
        relations_file = paths.root / str(row.get("relations_path"))
        comments = ((read_json(comments_file) or {}).get("comments")) if comments_file.exists() else []
        relations = ((read_json(relations_file) or {}).get("relations")) if relations_file.exists() else []
        issue_key = Path(str(row.get("path"))).stem
        write_text(paths.llm_issues / f"{issue_key}.md", render_issue_markdown(issue, comments or [], relations or []))

    for project in read_json(paths.delivery / "projects.json") or []:
        slug = project.get("slugId") or project.get("id")
        write_text(paths.llm_projects / f"{slug}.md", render_project_markdown(project))

    for initiative in read_json(paths.delivery / "initiatives.json") or []:
        slug = initiative.get("id")
        write_text(paths.llm_initiatives / f"{slug}.md", render_initiative_markdown(initiative))

    for customer in read_json(paths.customers / "customers.json") or []:
        slug = customer.get("id")
        write_text(paths.llm_customers / f"{slug}.md", render_customer_markdown(customer))

    audit_rows = read_json(paths.audit / "audit_entries.json") or []
    if audit_rows:
        write_text(paths.llm_audit / "audit_log.md", render_audit_markdown(audit_rows))

    summary_lines = [
        "# EXPORT SUMMARY",
        "",
        "## Manifest",
        f"- workspace: `{manifest.get('workspace_name')}`",
        f"- viewer: `{manifest.get('viewer_email')}`",
        f"- total_projects: `{manifest.get('total_projects')}`",
        f"- total_issues: `{manifest.get('total_issues')}`",
        f"- total_issue_comments: `{manifest.get('total_issue_comments')}`",
        f"- total_attachments_detected: `{manifest.get('total_attachments_detected')}`",
        f"- total_attachments_downloaded: `{manifest.get('total_attachments_downloaded')}`",
        "",
        "## Manual imports",
        f"- folders: `{manual_manifest.get('folders')}`",
        "",
    ]
    write_text(paths.llm / "EXPORT_SUMMARY.md", "\n".join(summary_lines))
    index_lines = [
        "# INDEX",
        "",
        "- `snapshot_meta/manifest.json`",
        "- `snapshot_meta/schema_summary.json`",
        "- `snapshot_meta/permissions_and_gaps.json`",
        "- `workspace/`",
        "- `delivery/`",
        "- `issues/index.json`",
        "- `attachments/metadata.json`",
        "- `manual_imports/manual_import_manifest.json`",
        "",
    ]
    write_text(paths.llm / "INDEX.md", "\n".join(index_lines))
    write_text(paths.llm / "GAPS_AND_LIMITATIONS.md", render_gaps_markdown(gaps))
    write_text(paths.llm / "AUDIT_HANDOFF_PROMPT.md", build_handoff_prompt())

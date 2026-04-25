from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from .attachments import download_attachments, export_attachment_entities
from .checkpoint import CheckpointStore
from .exporters.audit import export_audit
from .exporters.customers import export_customers
from .exporters.delivery import export_delivery
from .exporters.issues import export_issues
from .exporters.workspace import export_workspace_collections, export_workspace_core
from .graphql import GraphQLClient
from .manifest import build_manifest
from .render import render_llm
from .runtime import SnapshotContext, SnapshotPaths
from .schema import SchemaCatalog, discover_schema
from .session import ExportSession
from .settings import ExporterSettings
from .utils import now_utc_iso, write_json
from .validate import validate_snapshot


LOGGER = logging.getLogger("linear_export")


def _scope_includes(scope: str, candidate: str) -> bool:
    return scope == "all" or scope == candidate


def _build_gaps_payload(session: ExportSession, schema_summary: dict[str, Any]) -> dict[str, Any]:
    confirmed = [
        "Endpoint GraphQL configurado en https://api.linear.app/graphql.",
        "La introspeccion del schema esta soportada por el endpoint.",
        "La paginacion confirmada en probes usa modelo cursor-based Relay con first/after.",
        "La query issue exige id:String! y acepta identifier estilo TEAM-1 como valor del argumento id.",
    ]
    inferred: list[str] = []
    pending: list[str] = []

    if not session.context.settings.auth_headers():
        pending.append("No habia API key/access token disponible en entorno para ejecutar snapshot autenticado real.")
    if session.context.settings.include_audit:
        pending.append("Audit log puede depender de rol owner y del plan/permisos del workspace.")
    if session.context.settings.include_attachments:
        inferred.append("uploads.linear.app requiere autenticacion o URLs firmadas; la descarga puede fallar por permisos o plan.")
    root_notes = schema_summary.get("root_argument_discovery_notes") if isinstance(schema_summary.get("root_argument_discovery_notes"), list) else []
    pending.extend(str(item) for item in root_notes)
    pending.extend(session.context.stats.unresolved_gaps)
    inferred.extend(session.context.stats.permissions_notes)
    confirmed.extend(session.context.stats.schema_notes)
    return {
        "confirmado": sorted(dict.fromkeys(confirmed)),
        "inferido": sorted(dict.fromkeys(inferred)),
        "pendiente_de_validar": sorted(dict.fromkeys(pending)),
    }


def _prepare_session(settings: ExporterSettings) -> tuple[ExportSession, dict[str, Any]]:
    paths = SnapshotPaths.build(settings.output_dir)
    paths.ensure()
    context = SnapshotContext(settings=settings, paths=paths)
    checkpoint = CheckpointStore.load(paths.snapshot_meta / "checkpoint.json")
    client = GraphQLClient(settings)
    schema_summary = discover_schema(client, paths.snapshot_meta / "schema_summary.json")
    catalog = SchemaCatalog(schema_summary)
    session = ExportSession(context=context, client=client, catalog=catalog, checkpoint=checkpoint)
    if schema_summary.get("introspection_supported"):
        context.stats.note_schema("La introspeccion del schema funciono contra el endpoint oficial.")
    if schema_summary.get("root_argument_discovery_notes"):
        for note in schema_summary["root_argument_discovery_notes"]:
            context.stats.note_schema(str(note))
    return session, schema_summary


def run_discovery(settings: ExporterSettings) -> dict[str, Any]:
    session, schema_summary = _prepare_session(settings)
    gaps = _build_gaps_payload(session, schema_summary)
    write_json(session.context.paths.snapshot_meta / "permissions_and_gaps.json", gaps)
    session.client.export_log(session.context.paths.snapshot_meta / "export_log.json")
    return {
        "schema_summary": schema_summary,
        "permissions_and_gaps": gaps,
        "output_dir": str(session.context.paths.root),
    }


def run_snapshot(settings: ExporterSettings) -> dict[str, Any]:
    settings.require_auth()
    export_started_at = now_utc_iso()
    started = time.monotonic()
    session, schema_summary = _prepare_session(settings)
    session.context.stats.note_plan(f"scope={settings.scope}")
    session.context.stats.note_plan("Snapshot modular por dominios; no se usan megaqueries.")

    workspace_core = export_workspace_core(session)
    if _scope_includes(settings.scope, "workspace") or settings.scope == "all":
        export_workspace_collections(session)
    if _scope_includes(settings.scope, "delivery") or settings.scope == "all":
        export_delivery(session)
    if (settings.scope == "all" or settings.scope == "customers") and settings.include_customers:
        export_customers(session)
    elif settings.scope in {"all", "customers"} and not settings.include_customers:
        session.context.stats.note_permissions("Customer export deshabilitado por configuracion.")
    if _scope_includes(settings.scope, "issues") or settings.scope == "all":
        export_issues(session)
    if (settings.scope == "all" or settings.scope == "audit") and settings.include_audit:
        export_audit(session)
    elif settings.scope in {"all", "audit"} and not settings.include_audit:
        session.context.stats.note_permissions("Audit export deshabilitado por configuracion.")
    if settings.include_attachments and (settings.scope == "all" or settings.scope == "attachments"):
        export_attachment_entities(session)
        download_attachments(session)
    elif settings.scope in {"all", "attachments"} and not settings.include_attachments:
        session.context.stats.note_permissions("Attachments export deshabilitado por configuracion.")

    gaps = _build_gaps_payload(session, schema_summary)
    write_json(session.context.paths.snapshot_meta / "permissions_and_gaps.json", gaps)
    session.client.export_log(session.context.paths.snapshot_meta / "export_log.json")

    export_finished_at = now_utc_iso()
    manifest = build_manifest(
        session.context,
        export_started_at=export_started_at,
        export_finished_at=export_finished_at,
        duration_seconds=time.monotonic() - started,
        viewer=workspace_core.get("viewer"),
        organization=workspace_core.get("organization"),
        file_hashes=settings.hash_files,
    )
    write_json(session.context.paths.snapshot_meta / "manifest.json", manifest)
    render_llm(session.context.paths)
    validation = validate_snapshot(session.context.paths)
    return {
        "manifest": manifest,
        "validation": validation,
        "output_dir": str(session.context.paths.root),
    }


def run_attachment_download(settings: ExporterSettings) -> dict[str, Any]:
    settings.require_auth()
    session, schema_summary = _prepare_session(settings)
    export_attachment_entities(session)
    metadata = download_attachments(session)
    gaps = _build_gaps_payload(session, schema_summary)
    write_json(session.context.paths.snapshot_meta / "permissions_and_gaps.json", gaps)
    session.client.export_log(session.context.paths.snapshot_meta / "export_log.json")
    return {"attachments": metadata, "output_dir": str(session.context.paths.root)}


def run_render_llm(settings: ExporterSettings) -> dict[str, Any]:
    paths = SnapshotPaths.build(settings.output_dir)
    paths.ensure()
    render_llm(paths)
    return {"output_dir": str(paths.root)}


def run_validate(settings: ExporterSettings) -> dict[str, Any]:
    paths = SnapshotPaths.build(settings.output_dir)
    paths.ensure()
    report = validate_snapshot(paths)
    return {"validation": report, "output_dir": str(paths.root)}

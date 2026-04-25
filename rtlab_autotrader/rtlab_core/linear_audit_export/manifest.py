from __future__ import annotations

from pathlib import Path
from typing import Any

from . import EXPORTER_VERSION
from .runtime import SnapshotContext
from .utils import git_context, relative_to, sha256_file


def build_manifest(
    context: SnapshotContext,
    *,
    export_started_at: str,
    export_finished_at: str,
    duration_seconds: float,
    viewer: dict[str, Any] | None,
    organization: dict[str, Any] | None,
    file_hashes: bool = False,
) -> dict[str, Any]:
    git_info = git_context(Path(__file__).resolve().parents[3])
    manifest: dict[str, Any] = {
        "export_started_at": export_started_at,
        "export_finished_at": export_finished_at,
        "duration_seconds": round(duration_seconds, 3),
        "exporter_version": EXPORTER_VERSION,
        "git_branch": git_info.get("branch", ""),
        "git_commit": git_info.get("commit", ""),
        "workspace_name": (organization or {}).get("name"),
        "workspace_id": (organization or {}).get("id"),
        "viewer_name": (viewer or {}).get("name"),
        "viewer_id": (viewer or {}).get("id"),
        "viewer_email": (viewer or {}).get("email"),
        "page_size": context.settings.page_size,
        "include_attachments": context.settings.include_attachments,
        "include_audit": context.settings.include_audit,
        "include_customers": context.settings.include_customers,
        "total_teams": context.stats.total_teams,
        "total_users": context.stats.total_users,
        "total_states": context.stats.total_states,
        "total_labels": context.stats.total_labels,
        "total_projects": context.stats.total_projects,
        "total_project_milestones": context.stats.total_project_milestones,
        "total_project_updates": context.stats.total_project_updates,
        "total_initiatives": context.stats.total_initiatives,
        "total_initiative_updates": context.stats.total_initiative_updates,
        "total_cycles": context.stats.total_cycles,
        "total_issues": context.stats.total_issues,
        "total_issue_comments": context.stats.total_issue_comments,
        "total_issue_relations": context.stats.total_issue_relations,
        "total_customers": context.stats.total_customers,
        "total_customer_requests": context.stats.total_customer_requests,
        "total_audit_entries": context.stats.total_audit_entries,
        "total_attachments_detected": context.stats.total_attachments_detected,
        "total_attachments_downloaded": context.stats.total_attachments_downloaded,
        "total_attachments_failed": context.stats.total_attachments_failed,
        "total_errors": len(context.stats.errors),
        "total_warnings": len(context.stats.warnings),
        "schema_notes": context.stats.schema_notes,
        "permissions_notes": context.stats.permissions_notes,
        "plan_notes": context.stats.plan_notes,
        "unresolved_gaps": context.stats.unresolved_gaps,
    }
    if file_hashes:
        hashes: dict[str, str] = {}
        for path in sorted(context.paths.root.rglob("*")):
            if path.is_file():
                hashes[relative_to(path, context.paths.root)] = sha256_file(path)
        manifest["file_hashes"] = hashes
    return manifest

from __future__ import annotations

from pathlib import Path
from typing import Any

from .manual_imports import write_manual_import_manifest
from .runtime import SnapshotPaths
from .utils import read_json, write_json


def validate_snapshot(paths: SnapshotPaths) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    manifest = read_json(paths.snapshot_meta / "manifest.json")
    if not isinstance(manifest, dict):
        errors.append("Falta snapshot_meta/manifest.json")
        manifest = {}

    schema_summary = read_json(paths.snapshot_meta / "schema_summary.json")
    if not isinstance(schema_summary, dict):
        errors.append("Falta snapshot_meta/schema_summary.json")

    issues_index = read_json(paths.issues / "index.json")
    if not isinstance(issues_index, list):
        warnings.append("Falta issues/index.json o no es lista.")
        issues_index = []

    for row in issues_index:
        issue_path = paths.root / str(row.get("path") or "")
        comments_path = paths.root / str(row.get("comments_path") or "")
        relations_path = paths.root / str(row.get("relations_path") or "")
        if not issue_path.exists():
            errors.append(f"Falta issue raw: {issue_path}")
        if not comments_path.exists():
            errors.append(f"Falta issue comments: {comments_path}")
        if not relations_path.exists():
            errors.append(f"Falta issue relations: {relations_path}")

    if manifest.get("total_issues") and int(manifest["total_issues"]) != len(issues_index):
        warnings.append("total_issues del manifest no coincide con issues/index.json")

    attachments_meta = read_json(paths.attachments / "metadata.json")
    if attachments_meta is None:
        warnings.append("No existe attachments/metadata.json")

    manual_manifest = write_manual_import_manifest(paths.manual_imports)

    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "manual_imports": manual_manifest,
    }
    write_json(paths.snapshot_meta / "validation_report.json", report)
    return report

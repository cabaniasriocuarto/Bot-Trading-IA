from __future__ import annotations

from pathlib import Path
from typing import Any

from .utils import write_json


def build_manual_import_manifest(root: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {"folders": {}}
    for folder in (
        "issues_csv",
        "projects_csv",
        "initiatives_csv",
        "members_csv",
        "customer_requests_csv",
        "markdown_copies",
        "pdfs",
    ):
        base = root / folder
        files = [str(path.relative_to(root)) for path in sorted(base.rglob("*")) if path.is_file()] if base.exists() else []
        payload["folders"][folder] = {"count": len(files), "files": files}
    return payload


def write_manual_import_manifest(root: Path) -> dict[str, Any]:
    payload = build_manual_import_manifest(root)
    write_json(root / "manual_import_manifest.json", payload)
    return payload


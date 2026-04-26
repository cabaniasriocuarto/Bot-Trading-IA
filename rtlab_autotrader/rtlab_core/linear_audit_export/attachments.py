from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .session import ExportSession
from .utils import detect_upload_urls, normalize_filename, write_json
from .exporters.common import paginate_root_connection
from .exporters.specs import ATTACHMENT_REF, ISSUE_REF
from .schema import SelectionSpec


ATTACHMENT_TOP_REF = SelectionSpec(
    scalars=("id", "title", "subtitle", "url", "metadata", "source", "sourceType", "createdAt", "updatedAt"),
    objects={"issue": ISSUE_REF},
)


def export_attachment_entities(session: ExportSession) -> list[dict[str, Any]]:
    selection = session.catalog.render_selection("Attachment", ATTACHMENT_TOP_REF, indent=6)
    query = f"""
query Attachments($first: Int!, $after: String) {{
  attachments(first: $first, after: $after) {{
    nodes {{
{selection}
    }}
    pageInfo {{ hasNextPage endCursor }}
  }}
}}
"""
    rows = paginate_root_connection(
        session,
        checkpoint_key="attachments.entities",
        root_field="attachments",
        query=query,
    )
    write_json(session.context.paths.attachments / "entities.json", rows)
    for row in rows:
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        session.add_attachment_candidate(
            {
                "source_entity_type": "attachment",
                "source_entity_id": str(row.get("id") or ""),
                "source_entity_identifier": str((((row.get("issue") or {}) if isinstance(row.get("issue"), dict) else {}).get("identifier")) or ""),
                "original_url": url,
                "status": "pending",
            }
        )
    return rows


def _scan_snapshot_for_uploads(root: Path) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        if path.name in {"metadata.json", "manifest.json", "checkpoint.json", "export_log.json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for url in detect_upload_urls(text):
            candidates.append(
                {
                    "source_entity_type": "snapshot_scan",
                    "source_entity_id": "",
                    "source_entity_identifier": "",
                    "source_file": str(path.relative_to(root)),
                    "original_url": url,
                    "status": "pending",
                }
            )
    return candidates


def _build_local_filename(url: str, *, source_identifier: str, source_entity_id: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name or "attachment"
    safe = normalize_filename(name, max_length=80)
    digest = hashlib.sha1(f"{source_entity_id}:{url}".encode("utf-8")).hexdigest()[:10]
    prefix = normalize_filename(source_identifier or source_entity_id or "linear", max_length=30)
    return f"{prefix}_{digest}_{safe}"


def download_attachments(session: ExportSession) -> list[dict[str, Any]]:
    explicit = list(session.attachment_candidates)
    scanned = _scan_snapshot_for_uploads(session.context.paths.root)
    combined: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in explicit + scanned:
        key = (
            str(row.get("source_entity_id") or ""),
            str(row.get("original_url") or ""),
            str(row.get("source_file") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        combined.append(dict(row))

    results: list[dict[str, Any]] = []
    for candidate in combined:
        url = str(candidate.get("original_url") or "").strip()
        if not url:
            continue
        session.context.stats.total_attachments_detected += 1
        if "uploads.linear.app" not in url.lower():
            result = {
                **candidate,
                "local_path": "",
                "mime_type": "",
                "size_bytes": 0,
                "status": "skipped",
                "error_message": "external_or_unsupported_url",
            }
            results.append(result)
            continue
        local_name = _build_local_filename(
            url,
            source_identifier=str(candidate.get("source_entity_identifier") or ""),
            source_entity_id=str(candidate.get("source_entity_id") or ""),
        )
        target = session.context.paths.attachments_files / local_name
        download = session.client.download_file(url, target)
        result = {
            **candidate,
            "local_path": str(target.relative_to(session.context.paths.root)) if target.exists() else "",
            "mime_type": download.get("mime_type", ""),
            "size_bytes": int(download.get("size_bytes") or 0),
            "status": download.get("status"),
            "error_message": download.get("error_message", ""),
        }
        if download.get("status") == "downloaded":
            session.context.stats.total_attachments_downloaded += 1
        elif download.get("status") == "failed":
            session.context.stats.total_attachments_failed += 1
        results.append(result)

    write_json(session.context.paths.attachments / "metadata.json", results)
    return results

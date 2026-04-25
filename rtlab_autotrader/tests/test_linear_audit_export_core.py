from __future__ import annotations

from pathlib import Path

import pytest

from rtlab_core.linear_audit_export.checkpoint import CheckpointStore
from rtlab_core.linear_audit_export.graphql import GraphQLClient, GraphQLExecution, GraphQLExecutionError
from rtlab_core.linear_audit_export.manifest import build_manifest
from rtlab_core.linear_audit_export.runtime import SnapshotContext, SnapshotPaths
from rtlab_core.linear_audit_export.settings import ExporterSettings
from rtlab_core.linear_audit_export.session import ExportSession
from rtlab_core.linear_audit_export.utils import detect_upload_urls, normalize_filename, write_json
from rtlab_core.linear_audit_export.validate import validate_snapshot


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> dict:
        return self._payload


def _settings(tmp_path: Path) -> ExporterSettings:
    return ExporterSettings(
        base_url="https://api.linear.app/graphql",
        output_dir=tmp_path / "linear_export",
        include_attachments=True,
        include_audit=True,
        include_customers=True,
        page_size=50,
        timeout_seconds=5.0,
        retry_max=2,
        resume=True,
        max_issues=0,
        log_level="INFO",
        scope="all",
        api_key="test-token",
        access_token="",
    )


def test_normalize_filename_for_windows() -> None:
    assert normalize_filename('CON: bad/name?.json').startswith("CON_ bad_name_")
    assert normalize_filename("   ") == "untitled"


def test_detect_upload_urls() -> None:
    payload = {"body": "see https://uploads.linear.app/a/b/file.png and https://uploads.linear.app/a/b/file.png"}
    assert detect_upload_urls(payload) == ["https://uploads.linear.app/a/b/file.png"]


def test_checkpoint_roundtrip(tmp_path: Path) -> None:
    store = CheckpointStore.load(tmp_path / "checkpoint.json")
    store.set_cursor("issues.base", "abc")
    store.mark_done("issues", "LIN-1")
    reloaded = CheckpointStore.load(tmp_path / "checkpoint.json")
    assert reloaded.get_cursor("issues.base") == "abc"
    assert reloaded.is_done("issues", "LIN-1") is True


def test_graphql_client_retries_on_429(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = GraphQLClient(_settings(tmp_path))
    responses = iter(
        [
            _FakeResponse(429, {"errors": [{"message": "rate", "extensions": {"http": {"status": 429}}}]}, {"Retry-After": "0"}),
            _FakeResponse(200, {"data": {"viewer": {"id": "1"}}}),
        ]
    )
    monkeypatch.setattr(client.session, "post", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("time.sleep", lambda *_args, **_kwargs: None)
    result = client.execute("query { viewer { id } }")
    assert result.data["viewer"]["id"] == "1"
    assert len(client.request_log) == 2


def test_graphql_client_raises_on_validation_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = GraphQLClient(_settings(tmp_path))
    response = _FakeResponse(
        400,
        {"errors": [{"message": "invalid", "extensions": {"code": "GRAPHQL_VALIDATION_FAILED", "http": {"status": 400}}}]},
    )
    monkeypatch.setattr(client.session, "post", lambda *args, **kwargs: response)
    with pytest.raises(GraphQLExecutionError):
        client.execute("query { nope }")


def test_build_manifest_serializes_counts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    paths = SnapshotPaths.build(settings.output_dir)
    paths.ensure()
    context = SnapshotContext(settings=settings, paths=paths)
    context.stats.total_projects = 2
    context.stats.total_issues = 3
    manifest = build_manifest(
        context,
        export_started_at="2026-04-14T00:00:00+00:00",
        export_finished_at="2026-04-14T00:01:00+00:00",
        duration_seconds=60.0,
        viewer={"id": "viewer-1", "name": "Test", "email": "test@example.com"},
        organization={"id": "org-1", "name": "Workspace"},
    )
    assert manifest["total_projects"] == 2
    assert manifest["viewer_email"] == "test@example.com"


def test_validate_snapshot_basic(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    paths = SnapshotPaths.build(settings.output_dir)
    paths.ensure()
    write_json(paths.snapshot_meta / "manifest.json", {"total_issues": 1})
    write_json(paths.snapshot_meta / "schema_summary.json", {"ok": True})
    write_json(
        paths.issues / "index.json",
        [
            {
                "path": "issues/by_identifier/LIN-1.json",
                "comments_path": "issues/comments/LIN-1.comments.json",
                "relations_path": "issues/relations/LIN-1.relations.json",
            }
        ],
    )
    write_json(paths.issues_by_identifier / "LIN-1.json", {"id": "1"})
    write_json(paths.issues_comments / "LIN-1.comments.json", {"comments": []})
    write_json(paths.issues_relations / "LIN-1.relations.json", {"relations": []})
    report = validate_snapshot(paths)
    assert report["ok"] is True


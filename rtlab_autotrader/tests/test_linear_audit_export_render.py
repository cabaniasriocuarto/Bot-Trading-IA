from __future__ import annotations

from pathlib import Path

from rtlab_core.linear_audit_export.manual_imports import build_manual_import_manifest
from rtlab_core.linear_audit_export.render import (
    render_customer_markdown,
    render_initiative_markdown,
    render_issue_markdown,
    render_project_markdown,
)
from rtlab_core.linear_audit_export.runtime import SnapshotPaths


def test_render_issue_markdown_contains_full_sections() -> None:
    issue = {
        "id": "1",
        "identifier": "LIN-1",
        "title": "Issue title",
        "description": "full description",
        "attachments_export": [{"id": "a1", "title": "img", "url": "https://uploads.linear.app/file.png"}],
        "customer_requests_export": [{"id": "n1", "body": "Need body"}],
    }
    comments = [{"id": "c1", "body": "Comment body", "createdAt": "x", "updatedAt": "y", "url": "u"}]
    relations = [{"type": "blocks", "relatedIssue": {"identifier": "LIN-2", "title": "Other"}}]
    rendered = render_issue_markdown(issue, comments, relations)
    assert "full description" in rendered
    assert "Comment body" in rendered
    assert "LIN-2" in rendered


def test_render_project_and_initiative_markdown() -> None:
    project = render_project_markdown({"id": "p1", "name": "Project", "summary": "S", "description": "D"})
    initiative = render_initiative_markdown({"id": "i1", "name": "Initiative", "summary": "S2", "description": "D2"})
    customer = render_customer_markdown({"id": "c1", "name": "Customer"})
    assert "Project" in project
    assert "Initiative" in initiative
    assert "Customer" in customer


def test_manual_import_manifest_lists_files(tmp_path: Path) -> None:
    paths = SnapshotPaths.build(tmp_path / "linear_export")
    paths.ensure()
    sample = paths.manual_issues_csv / "issues.csv"
    sample.write_text("id\n1\n", encoding="utf-8")
    manifest = build_manual_import_manifest(paths.manual_imports)
    assert manifest["folders"]["issues_csv"]["count"] == 1

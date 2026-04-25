from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .settings import ExporterSettings
from .utils import ensure_dir


@dataclass(slots=True)
class SnapshotPaths:
    root: Path
    snapshot_meta: Path
    workspace: Path
    delivery: Path
    customers: Path
    audit: Path
    issues: Path
    issues_by_identifier: Path
    issues_comments: Path
    issues_relations: Path
    attachments: Path
    attachments_files: Path
    llm: Path
    llm_issues: Path
    llm_projects: Path
    llm_initiatives: Path
    llm_customers: Path
    llm_audit: Path
    manual_imports: Path
    manual_issues_csv: Path
    manual_projects_csv: Path
    manual_initiatives_csv: Path
    manual_members_csv: Path
    manual_customer_requests_csv: Path
    manual_markdown_copies: Path
    manual_pdfs: Path

    @classmethod
    def build(cls, root: Path) -> "SnapshotPaths":
        return cls(
            root=root,
            snapshot_meta=root / "snapshot_meta",
            workspace=root / "workspace",
            delivery=root / "delivery",
            customers=root / "customers",
            audit=root / "audit",
            issues=root / "issues",
            issues_by_identifier=root / "issues" / "by_identifier",
            issues_comments=root / "issues" / "comments",
            issues_relations=root / "issues" / "relations",
            attachments=root / "attachments",
            attachments_files=root / "attachments" / "files",
            llm=root / "llm",
            llm_issues=root / "llm" / "issues",
            llm_projects=root / "llm" / "projects",
            llm_initiatives=root / "llm" / "initiatives",
            llm_customers=root / "llm" / "customers",
            llm_audit=root / "llm" / "audit",
            manual_imports=root / "manual_imports",
            manual_issues_csv=root / "manual_imports" / "issues_csv",
            manual_projects_csv=root / "manual_imports" / "projects_csv",
            manual_initiatives_csv=root / "manual_imports" / "initiatives_csv",
            manual_members_csv=root / "manual_imports" / "members_csv",
            manual_customer_requests_csv=root / "manual_imports" / "customer_requests_csv",
            manual_markdown_copies=root / "manual_imports" / "markdown_copies",
            manual_pdfs=root / "manual_imports" / "pdfs",
        )

    def ensure(self) -> None:
        for path in (
            self.root,
            self.snapshot_meta,
            self.workspace,
            self.delivery,
            self.customers,
            self.audit,
            self.issues,
            self.issues_by_identifier,
            self.issues_comments,
            self.issues_relations,
            self.attachments,
            self.attachments_files,
            self.llm,
            self.llm_issues,
            self.llm_projects,
            self.llm_initiatives,
            self.llm_customers,
            self.llm_audit,
            self.manual_imports,
            self.manual_issues_csv,
            self.manual_projects_csv,
            self.manual_initiatives_csv,
            self.manual_members_csv,
            self.manual_customer_requests_csv,
            self.manual_markdown_copies,
            self.manual_pdfs,
        ):
            ensure_dir(path)


@dataclass(slots=True)
class SnapshotStats:
    total_teams: int = 0
    total_users: int = 0
    total_states: int = 0
    total_labels: int = 0
    total_views: int = 0
    total_templates: int = 0
    total_projects: int = 0
    total_project_milestones: int = 0
    total_project_updates: int = 0
    total_project_statuses: int = 0
    total_documents: int = 0
    total_initiatives: int = 0
    total_initiative_updates: int = 0
    total_cycles: int = 0
    total_issues: int = 0
    total_issue_comments: int = 0
    total_issue_relations: int = 0
    total_customers: int = 0
    total_customer_requests: int = 0
    total_customer_statuses: int = 0
    total_customer_tiers: int = 0
    total_audit_entries: int = 0
    total_attachments_detected: int = 0
    total_attachments_downloaded: int = 0
    total_attachments_failed: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    schema_notes: list[str] = field(default_factory=list)
    permissions_notes: list[str] = field(default_factory=list)
    plan_notes: list[str] = field(default_factory=list)
    unresolved_gaps: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def error(self, message: str) -> None:
        if message not in self.errors:
            self.errors.append(message)

    def note_schema(self, message: str) -> None:
        if message not in self.schema_notes:
            self.schema_notes.append(message)

    def note_permissions(self, message: str) -> None:
        if message not in self.permissions_notes:
            self.permissions_notes.append(message)

    def note_plan(self, message: str) -> None:
        if message not in self.plan_notes:
            self.plan_notes.append(message)

    def gap(self, message: str) -> None:
        if message not in self.unresolved_gaps:
            self.unresolved_gaps.append(message)


@dataclass(slots=True)
class SnapshotContext:
    settings: ExporterSettings
    paths: SnapshotPaths
    stats: SnapshotStats = field(default_factory=SnapshotStats)


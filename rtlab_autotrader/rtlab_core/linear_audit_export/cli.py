from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from .orchestrator import run_attachment_download, run_discovery, run_render_llm, run_snapshot, run_validate
from .settings import DEFAULT_OUTPUT_DIR, ExporterSettings, Scope


app = typer.Typer(help="Linear snapshot export para auditoria profunda.")
attachments_app = typer.Typer(help="Operaciones de descarga de adjuntos.")
app.add_typer(attachments_app, name="attachments")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _settings(
    *,
    scope: Scope,
    output_dir: Path,
    include_attachments: bool,
    include_audit: bool,
    include_customers: bool,
    page_size: int,
    timeout_seconds: float,
    retry_max: int,
    resume: bool,
    max_issues: int,
    log_level: str,
    hash_files: bool,
    test_limit: int,
) -> ExporterSettings:
    return ExporterSettings.from_env(
        scope=scope,
        output_dir=output_dir,
        include_attachments=include_attachments,
        include_audit=include_audit,
        include_customers=include_customers,
        page_size=page_size,
        timeout_seconds=timeout_seconds,
        retry_max=retry_max,
        resume=resume,
        max_issues=max_issues,
        log_level=log_level,
        hash_files=hash_files,
        test_limit=test_limit,
    )


@app.command("discover")
def discover(
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    _configure_logging(log_level)
    settings = ExporterSettings.from_env(scope="all", output_dir=output_dir, log_level=log_level)
    result = run_discovery(settings)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("snapshot")
def snapshot(
    scope: Scope = typer.Option("all", "--scope"),
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
    include_attachments: bool = typer.Option(True, "--include-attachments/--skip-attachments"),
    include_audit: bool = typer.Option(True, "--include-audit/--skip-audit"),
    include_customers: bool = typer.Option(True, "--include-customers/--skip-customers"),
    page_size: int = typer.Option(50, "--page-size"),
    timeout_seconds: float = typer.Option(60.0, "--timeout-seconds"),
    retry_max: int = typer.Option(5, "--retry-max"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    max_issues: int = typer.Option(0, "--max-issues"),
    log_level: str = typer.Option("INFO", "--log-level"),
    hash_files: bool = typer.Option(False, "--hash-files/--no-hash-files"),
    test_limit: int = typer.Option(0, "--test-limit"),
) -> None:
    _configure_logging(log_level)
    settings = _settings(
        scope=scope,
        output_dir=output_dir,
        include_attachments=include_attachments,
        include_audit=include_audit,
        include_customers=include_customers,
        page_size=page_size,
        timeout_seconds=timeout_seconds,
        retry_max=retry_max,
        resume=resume,
        max_issues=max_issues,
        log_level=log_level,
        hash_files=hash_files,
        test_limit=test_limit,
    )
    result = run_snapshot(settings)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@attachments_app.command("download")
def attachments_download(
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
    page_size: int = typer.Option(50, "--page-size"),
    timeout_seconds: float = typer.Option(60.0, "--timeout-seconds"),
    retry_max: int = typer.Option(5, "--retry-max"),
    resume: bool = typer.Option(True, "--resume/--no-resume"),
    log_level: str = typer.Option("INFO", "--log-level"),
) -> None:
    _configure_logging(log_level)
    settings = _settings(
        scope="attachments",
        output_dir=output_dir,
        include_attachments=True,
        include_audit=False,
        include_customers=False,
        page_size=page_size,
        timeout_seconds=timeout_seconds,
        retry_max=retry_max,
        resume=resume,
        max_issues=0,
        log_level=log_level,
        hash_files=False,
        test_limit=0,
    )
    result = run_attachment_download(settings)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("render-llm")
def render_llm_command(
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
) -> None:
    settings = ExporterSettings.from_env(scope="all", output_dir=output_dir)
    result = run_render_llm(settings)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("validate")
def validate_command(
    output_dir: Path = typer.Option(DEFAULT_OUTPUT_DIR, "--output-dir"),
) -> None:
    settings = ExporterSettings.from_env(scope="all", output_dir=output_dir)
    result = run_validate(settings)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()

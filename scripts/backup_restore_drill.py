#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"


def _utc_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")


def _default_user_data_dir(repo_root: Path) -> Path:
    explicit = str(os.getenv("RTLAB_USER_DATA_DIR", "")).strip()
    if explicit:
        return Path(explicit).resolve()
    preferred = (repo_root / "rtlab_autotrader" / "user_data").resolve()
    if preferred.exists():
        return preferred
    return (repo_root / "user_data").resolve()


def _iter_files(root: Path) -> list[Path]:
    rows: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix().lower()
        if rel.endswith(".pyc"):
            continue
        if "/__pycache__/" in f"/{rel}/":
            continue
        rows.append(p)
    rows.sort()
    return rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in _iter_files(root):
        rel = p.relative_to(root).as_posix()
        out[rel] = {"sha256": _sha256_file(p), "bytes": int(p.stat().st_size)}
    return out


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=False)


def _parse_json_from_stdout(stdout: str) -> dict[str, Any]:
    raw = str(stdout or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _build_md(report: dict[str, Any]) -> str:
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    diff = report.get("diff") if isinstance(report.get("diff"), dict) else {}
    lines = [
        "# Backup/Restore Drill",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- source_dir: `{report.get('source_dir')}`",
        f"- archive_path: `{report.get('archive_path')}`",
        "",
        "## Checks",
        f"- backup_ok: `{checks.get('backup_ok')}`",
        f"- restore_ok: `{checks.get('restore_ok')}`",
        f"- manifest_match: `{checks.get('manifest_match')}`",
        "",
        "## Diff",
        f"- missing_in_restore: `{len(diff.get('missing_in_restore') or [])}`",
        f"- extra_in_restore: `{len(diff.get('extra_in_restore') or [])}`",
        f"- hash_mismatch: `{len(diff.get('hash_mismatch') or [])}`",
        "",
        "## Notes",
    ]
    notes = report.get("notes") if isinstance(report.get("notes"), list) else []
    if notes:
        for row in notes:
            lines.append(f"- {row}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ejecuta backup+restore drill y valida integridad por hash.")
    p.add_argument("--source-dir", default="", help="user_data origen. Default: RTLAB_USER_DATA_DIR o auto-detect repo.")
    p.add_argument("--label", default="backup_restore_drill")
    p.add_argument("--keep-workdir", action="store_true", help="No borra carpeta temporal del drill.")
    return p


def main() -> int:
    args = _parser().parse_args()
    source_dir = Path(args.source_dir).resolve() if str(args.source_dir).strip() else _default_user_data_dir(REPO_ROOT)
    if not source_dir.exists() or not source_dir.is_dir():
        raise RuntimeError(f"source-dir invalido: {source_dir}")

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    workdir = ARTIFACTS_DIR / f"_backup_restore_drill_work_{stamp}"
    backups_dir = (REPO_ROOT / "backups").resolve()
    restored_dir = workdir / "restored_user_data"
    workdir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []

    backup_cmd = [
        sys.executable,
        "scripts/backup_user_data.py",
        "--source-dir",
        str(source_dir),
        "--output-dir",
        str(backups_dir),
        "--prefix",
        "user_data_backup_drill",
    ]
    backup_run = _run(backup_cmd, REPO_ROOT)
    backup_payload = _parse_json_from_stdout(backup_run.stdout)
    backup_ok = backup_run.returncode == 0 and bool(backup_payload.get("archive"))
    if not backup_ok:
        notes.append(f"backup_failed_rc={backup_run.returncode}")
        if backup_run.stderr.strip():
            notes.append(f"backup_stderr={backup_run.stderr.strip()[:300]}")
        raise RuntimeError("backup_user_data.py fallo durante drill.")

    archive_path = Path(str(backup_payload.get("archive") or "")).resolve()
    if not archive_path.exists():
        raise RuntimeError(f"archive no encontrado: {archive_path}")

    restore_cmd = [
        sys.executable,
        "scripts/restore_user_data.py",
        "--archive",
        str(archive_path),
        "--target-dir",
        str(restored_dir),
    ]
    restore_run = _run(restore_cmd, REPO_ROOT)
    restore_ok = restore_run.returncode == 0
    if not restore_ok:
        notes.append(f"restore_failed_rc={restore_run.returncode}")
        if restore_run.stderr.strip():
            notes.append(f"restore_stderr={restore_run.stderr.strip()[:300]}")
        raise RuntimeError("restore_user_data.py fallo durante drill.")

    source_manifest = _manifest(source_dir)
    restored_manifest = _manifest(restored_dir)

    source_keys = set(source_manifest.keys())
    restored_keys = set(restored_manifest.keys())
    missing = sorted(source_keys - restored_keys)
    extra = sorted(restored_keys - source_keys)
    mismatched = sorted(
        key
        for key in sorted(source_keys & restored_keys)
        if source_manifest[key].get("sha256") != restored_manifest[key].get("sha256")
    )
    manifest_match = not missing and not extra and not mismatched

    checks = {"backup_ok": backup_ok, "restore_ok": restore_ok, "manifest_match": manifest_match}
    report = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_dir": str(source_dir),
        "archive_path": str(archive_path),
        "archive_sha256": str(backup_payload.get("archive_sha256") or ""),
        "checks": checks,
        "counts": {
            "source_files": len(source_manifest),
            "restored_files": len(restored_manifest),
        },
        "diff": {
            "missing_in_restore": missing,
            "extra_in_restore": extra,
            "hash_mismatch": mismatched,
        },
        "notes": notes,
    }

    json_out = ARTIFACTS_DIR / f"{args.label}_{stamp}.json"
    md_out = ARTIFACTS_DIR / f"{args.label}_{stamp}.md"
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_build_md(report), encoding="utf-8")

    if not args.keep_workdir:
        shutil.rmtree(workdir, ignore_errors=True)
    else:
        report["workdir"] = str(workdir)

    exit_code = 0 if manifest_match else 2
    print(
        json.dumps(
            {
                "json_report": str(json_out),
                "md_report": str(md_out),
                "checks": checks,
                "exit_code": exit_code,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

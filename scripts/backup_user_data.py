#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _default_user_data_dir(repo_root: Path) -> Path:
    explicit = str(os.getenv("RTLAB_USER_DATA_DIR", "")).strip()
    if explicit:
        return Path(explicit).resolve()
    preferred = (repo_root / "rtlab_autotrader" / "user_data").resolve()
    if preferred.exists():
        return preferred
    return (repo_root / "user_data").resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix().lower()
        if rel.endswith(".pyc"):
            continue
        if "/__pycache__/" in f"/{rel}/":
            continue
        files.append(p)
    files.sort()
    return files


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crea backup zip de user_data con hash SHA256.")
    parser.add_argument(
        "--source-dir",
        default="",
        help="Directorio user_data origen. Default: RTLAB_USER_DATA_DIR o auto-detect en repo.",
    )
    parser.add_argument(
        "--output-dir",
        default="backups",
        help="Carpeta destino de backups zip. Default: backups/",
    )
    parser.add_argument(
        "--prefix",
        default="user_data_backup",
        help="Prefijo del nombre del zip. Default: user_data_backup.",
    )
    return parser


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    args = _build_parser().parse_args()
    source_dir = Path(args.source_dir).resolve() if str(args.source_dir).strip() else _default_user_data_dir(repo_root)
    output_dir = Path(args.output_dir).resolve()
    prefix = str(args.prefix or "user_data_backup").strip() or "user_data_backup"

    if not source_dir.exists() or not source_dir.is_dir():
        raise RuntimeError(f"source-dir invalido: {source_dir}")

    files = _iter_files(source_dir)
    if not files:
        raise RuntimeError(f"source-dir sin archivos: {source_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"{prefix}_{_utc_stamp()}.zip"
    archive_path = output_dir / archive_name

    file_count = 0
    total_bytes = 0
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as zipf:
        for file_path in files:
            rel = file_path.relative_to(source_dir).as_posix()
            zipf.write(file_path, arcname=rel)
            file_count += 1
            total_bytes += file_path.stat().st_size

    report = {
        "ok": True,
        "archive": str(archive_path),
        "archive_sha256": _sha256_file(archive_path),
        "source_dir": str(source_dir),
        "files": int(file_count),
        "bytes_uncompressed": int(total_bytes),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

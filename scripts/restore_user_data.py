#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from zipfile import ZipFile


def _default_user_data_dir(repo_root: Path) -> Path:
    explicit = str(os.getenv("RTLAB_USER_DATA_DIR", "")).strip()
    if explicit:
        return Path(explicit).resolve()
    preferred = (repo_root / "rtlab_autotrader" / "user_data").resolve()
    if preferred.exists():
        return preferred
    return (repo_root / "user_data").resolve()


def _is_safe_member(name: str) -> bool:
    normalized = str(name or "").replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        return False
    parts = [p for p in normalized.split("/") if p]
    if not parts:
        return False
    return all(part not in {".", ".."} for part in parts)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restaura backup zip de user_data.")
    parser.add_argument("--archive", required=True, help="Archivo zip de backup.")
    parser.add_argument(
        "--target-dir",
        default="",
        help="Destino user_data. Default: RTLAB_USER_DATA_DIR o auto-detect en repo.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permite restaurar sobre directorio no vacio (se borra antes de extraer).",
    )
    return parser


def _clear_dir(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    args = _build_parser().parse_args()

    archive_path = Path(args.archive).resolve()
    if not archive_path.exists() or not archive_path.is_file():
        raise RuntimeError(f"archive invalido: {archive_path}")

    target_dir = Path(args.target_dir).resolve() if str(args.target_dir).strip() else _default_user_data_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)

    has_existing = any(target_dir.iterdir())
    if has_existing and not args.force:
        raise RuntimeError(
            f"target-dir no vacio: {target_dir}. Usa --force para reemplazar contenido."
        )
    if has_existing and args.force:
        _clear_dir(target_dir)

    extracted = 0
    with ZipFile(archive_path, "r") as zipf:
        names = zipf.namelist()
        if not names:
            raise RuntimeError("archive sin contenido.")
        for name in names:
            if not _is_safe_member(name):
                raise RuntimeError(f"Entrada insegura en zip: {name}")
        zipf.extractall(target_dir)
        extracted = len([n for n in names if not n.endswith("/")])

    print(
        f"OK: restore completado. archive={archive_path} target_dir={target_dir} files={extracted}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

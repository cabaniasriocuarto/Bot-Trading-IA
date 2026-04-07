from __future__ import annotations

import os
import posixpath
from pathlib import Path


def normalize_runtime_path_str(value: str | Path) -> str:
    raw = os.fspath(value)
    posix_raw = str(raw or "").replace("\\", "/").strip()
    if posix_raw.startswith("/"):
        normalized = posixpath.normpath(posix_raw)
        return normalized if normalized.startswith("/") else f"/{normalized.lstrip('/')}"
    return str(Path(os.path.abspath(raw)))


def runtime_path(value: str | Path) -> Path:
    return Path(normalize_runtime_path_str(value))

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


UPLOADS_RE = re.compile(r"https://uploads\.linear\.app/[^\s)\]>\"']+", re.IGNORECASE)
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_filename(value: str, *, max_length: int = 120) -> str:
    cleaned = re.sub(r"[<>:\"/\\\\|?*\x00-\x1f]+", "_", str(value or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    cleaned = cleaned or "untitled"
    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_file"
    if len(cleaned) > max_length:
        stem = cleaned[: max_length - 9].rstrip(" .")
        digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:8]
        cleaned = f"{stem}_{digest}"
    return cleaned


def iter_text_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_text_values(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from iter_text_values(child)


def detect_upload_urls(value: Any) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for text in iter_text_values(value):
        for match in UPLOADS_RE.findall(text):
            if match not in seen:
                seen.add(match)
                matches.append(match)
    return matches


def nested_get(payload: dict[str, Any], path: list[str]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def git_context(repo_root: Path) -> dict[str, str]:
    def _run(args: list[str]) -> str:
        try:
            result = subprocess.run(
                args,
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except Exception:
            return ""
        return result.stdout.strip()

    return {
        "branch": _run(["git", "branch", "--show-current"]),
        "commit": _run(["git", "rev-parse", "HEAD"]),
    }


def bool_note(value: bool) -> str:
    return "si" if value else "no"


def relative_to(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return os.fspath(path)


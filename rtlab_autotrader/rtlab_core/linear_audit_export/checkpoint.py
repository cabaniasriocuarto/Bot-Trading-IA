from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import now_utc_iso, read_json, write_json


@dataclass(slots=True)
class CheckpointStore:
    path: Path
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "CheckpointStore":
        payload = read_json(path)
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("cursors", {})
        payload.setdefault("completed", {})
        payload.setdefault("meta", {})
        return cls(path=path, data=payload)

    def save(self) -> None:
        meta = self.data.setdefault("meta", {})
        meta["updated_at"] = now_utc_iso()
        write_json(self.path, self.data)

    def get_cursor(self, key: str) -> str | None:
        value = self.data.setdefault("cursors", {}).get(key)
        return str(value) if value else None

    def set_cursor(self, key: str, cursor: str | None) -> None:
        cursors = self.data.setdefault("cursors", {})
        if cursor:
            cursors[key] = cursor
        else:
            cursors.pop(key, None)
        self.save()

    def mark_done(self, section: str, item_key: str) -> None:
        completed = self.data.setdefault("completed", {})
        bucket = completed.setdefault(section, {})
        bucket[item_key] = now_utc_iso()
        self.save()

    def is_done(self, section: str, item_key: str) -> bool:
        completed = self.data.setdefault("completed", {})
        return item_key in completed.get(section, {})


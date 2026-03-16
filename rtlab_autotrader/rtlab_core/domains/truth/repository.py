from __future__ import annotations

from pathlib import Path
from typing import Any

from rtlab_core.domains.common import json_load, json_save


class StrategyTruthRepository:
    def __init__(self, *, meta_path: Path) -> None:
        self.meta_path = Path(meta_path)

    def load_meta(self) -> dict[str, dict[str, Any]]:
        payload = json_load(self.meta_path, {})
        if not isinstance(payload, dict):
            return {}
        return payload

    def save_meta(self, payload: dict[str, dict[str, Any]]) -> None:
        json_save(self.meta_path, payload if isinstance(payload, dict) else {})

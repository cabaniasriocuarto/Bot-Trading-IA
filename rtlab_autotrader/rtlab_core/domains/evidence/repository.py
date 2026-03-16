from __future__ import annotations

from pathlib import Path
from typing import Any

from rtlab_core.domains.common import json_load, json_save
from rtlab_core.learning.experience_store import ExperienceStore


class StrategyEvidenceRepository:
    def __init__(self, *, runs_path: Path, experience_store: ExperienceStore) -> None:
        self.runs_path = Path(runs_path)
        self.experience_store = experience_store

    def record_run(
        self,
        run: dict[str, Any],
        *,
        source_override: str | None = None,
        bot_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(run, dict):
            return None
        return self.experience_store.record_run(run, source_override=source_override, bot_id=bot_id)

    def load_runs(self) -> list[dict[str, Any]]:
        payload = json_load(self.runs_path, [])
        if not isinstance(payload, list):
            return []
        return payload

    def save_runs(self, rows: list[dict[str, Any]]) -> None:
        json_save(self.runs_path, rows if isinstance(rows, list) else [])

    def latest_run_for_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        rows = [row for row in self.load_runs() if isinstance(row, dict) and row.get("strategy_id") == strategy_id]
        if not rows:
            return None
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows[0]

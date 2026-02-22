from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any


def _to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


class ReportEngine:
    def __init__(self, user_data_dir: Path) -> None:
        self.user_data_dir = user_data_dir.resolve()

    def write_backtest_artifacts(self, run_id: str, run_payload: dict[str, Any]) -> dict[str, str]:
        base = self.user_data_dir / "backtests" / "artifacts" / run_id
        base.mkdir(parents=True, exist_ok=True)

        report_json = base / "report.json"
        trades_csv = base / "trades.csv"
        equity_csv = base / "equity_curve.csv"

        report_json.write_text(json.dumps(run_payload, indent=2), encoding="utf-8")
        trades_csv.write_text(_to_csv(run_payload.get("trades", [])), encoding="utf-8")
        equity_csv.write_text(_to_csv(run_payload.get("equity_curve", [])), encoding="utf-8")

        return {
            "report_json_local": str(report_json),
            "trades_csv_local": str(trades_csv),
            "equity_curve_csv_local": str(equity_csv),
        }


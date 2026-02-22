from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_OFFLINE_GATES: dict[str, float] = {
    "min_trades_oos": 150,
    "min_winrate": 0.45,
    "min_profit_factor": 1.20,
    "min_sharpe_oos": 1.20,
    "min_sortino_oos": 1.50,
    "min_calmar_oos": 1.00,
    "max_drawdown_oos_pct": 18.0,
    "max_dd_duration_days": 30.0,
    "costs_ratio_max": 0.55,
    "pbo_max": 0.20,
    "dsr_min": 1.00,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _timeframe_minutes(tf: str | None) -> float:
    raw = str(tf or "").strip().lower()
    if raw.endswith("m"):
        return max(1.0, _safe_float(raw[:-1], 1.0))
    if raw.endswith("h"):
        return max(1.0, _safe_float(raw[:-1], 1.0) * 60.0)
    if raw.endswith("d"):
        return max(1.0, _safe_float(raw[:-1], 1.0) * 1440.0)
    return 5.0


class GateEvaluator:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.gates_path = (self.repo_root / "knowledge" / "policies" / "gates.yaml").resolve()

    def _load_thresholds(self) -> dict[str, float]:
        payload: dict[str, Any] = {}
        if self.gates_path.exists():
            try:
                raw = yaml.safe_load(self.gates_path.read_text(encoding="utf-8")) or {}
            except Exception:
                raw = {}
            if isinstance(raw, dict):
                payload = raw
        offline = payload.get("offline_rollout") if isinstance(payload.get("offline_rollout"), dict) else {}
        merged = {**DEFAULT_OFFLINE_GATES, **{k: _safe_float(v, DEFAULT_OFFLINE_GATES.get(k, 0.0)) for k, v in offline.items()}}
        return merged

    def evaluate(self, candidate_report: dict[str, Any]) -> dict[str, Any]:
        thresholds = self._load_thresholds()
        metrics = candidate_report.get("metrics") if isinstance(candidate_report.get("metrics"), dict) else {}
        costs = candidate_report.get("costs_breakdown") if isinstance(candidate_report.get("costs_breakdown"), dict) else {}
        checks: list[dict[str, Any]] = []

        def check(check_id: str, ok: bool, reason: str, **details: Any) -> None:
            checks.append({"id": check_id, "ok": bool(ok), "reason": reason, "details": details})

        data_source = str(candidate_report.get("data_source") or "")
        dataset_hash = str(candidate_report.get("dataset_hash") or "")
        check("real_data", data_source.lower() not in {"", "synthetic"}, "Datos reales requeridos", data_source=data_source)
        check("dataset_hash", bool(dataset_hash), "dataset_hash no vacio", dataset_hash=dataset_hash)

        has_costs = bool(costs) and all(
            key in costs for key in ("fees_total", "spread_total", "slippage_total", "funding_total", "total_cost", "gross_pnl_total")
        )
        check("cost_breakdown", has_costs, "Cost breakdown completo", keys=list(costs.keys()))

        validation_summary = candidate_report.get("validation_summary") if isinstance(candidate_report.get("validation_summary"), dict) else {}
        wf_ok = str(validation_summary.get("mode") or candidate_report.get("validation_mode") or "").lower() == "walk-forward"
        check("walk_forward_oos", wf_ok, "Walk-forward OOS obligatorio", validation_summary=validation_summary)

        trade_count = int(_safe_float(metrics.get("trade_count"), 0))
        check("min_trades_oos", trade_count >= int(thresholds["min_trades_oos"]), "Min trades OOS", actual=trade_count, threshold=thresholds["min_trades_oos"])

        winrate = _safe_float(metrics.get("winrate"))
        check("min_winrate", winrate >= thresholds["min_winrate"], "Winrate minimo", actual=winrate, threshold=thresholds["min_winrate"])

        profit_factor = _safe_float(metrics.get("profit_factor"))
        check(
            "min_profit_factor",
            profit_factor >= thresholds["min_profit_factor"],
            "Profit factor minimo",
            actual=profit_factor,
            threshold=thresholds["min_profit_factor"],
        )

        sharpe = _safe_float(metrics.get("sharpe"))
        sortino = _safe_float(metrics.get("sortino"))
        calmar = _safe_float(metrics.get("calmar"))
        check("min_sharpe_oos", sharpe >= thresholds["min_sharpe_oos"], "Sharpe OOS minimo", actual=sharpe, threshold=thresholds["min_sharpe_oos"])
        check("min_sortino_oos", sortino >= thresholds["min_sortino_oos"], "Sortino OOS minimo", actual=sortino, threshold=thresholds["min_sortino_oos"])
        check("min_calmar_oos", calmar >= thresholds["min_calmar_oos"], "Calmar OOS minimo", actual=calmar, threshold=thresholds["min_calmar_oos"])

        max_dd = abs(_safe_float(metrics.get("max_dd"))) * 100.0
        check(
            "max_drawdown_oos_pct",
            max_dd <= thresholds["max_drawdown_oos_pct"],
            "Max drawdown OOS",
            actual_pct=max_dd,
            threshold_pct=thresholds["max_drawdown_oos_pct"],
        )

        dd_duration_bars = _safe_float(metrics.get("max_dd_duration_bars"))
        tf_minutes = _timeframe_minutes(candidate_report.get("timeframe"))
        dd_duration_days = (dd_duration_bars * tf_minutes) / (60.0 * 24.0)
        check(
            "max_dd_duration_days",
            dd_duration_days <= thresholds["max_dd_duration_days"],
            "Duracion maxima de drawdown",
            actual_days=round(dd_duration_days, 4),
            threshold_days=thresholds["max_dd_duration_days"],
            bars=dd_duration_bars,
            timeframe=str(candidate_report.get("timeframe") or ""),
        )

        gross_abs = abs(_safe_float(costs.get("gross_pnl_total")))
        total_cost = _safe_float(costs.get("total_cost"))
        costs_ratio = (total_cost / gross_abs) if gross_abs > 0 else 0.0
        check(
            "costs_ratio_max",
            costs_ratio <= thresholds["costs_ratio_max"],
            "Ratio de costos sobre PnL bruto",
            actual=round(costs_ratio, 6),
            threshold=thresholds["costs_ratio_max"],
            gross_pnl_total=_safe_float(costs.get("gross_pnl_total")),
            total_cost=total_cost,
        )

        pbo_val = metrics.get("pbo")
        if isinstance(pbo_val, (int, float)):
            check("pbo_max", float(pbo_val) <= thresholds["pbo_max"], "PBO maximo", actual=float(pbo_val), threshold=thresholds["pbo_max"])
        else:
            check("pbo_max", True, "PBO no disponible (skip)", actual=None, threshold=thresholds["pbo_max"], skipped=True)

        dsr_val = metrics.get("dsr")
        if isinstance(dsr_val, (int, float)):
            check("dsr_min", float(dsr_val) >= thresholds["dsr_min"], "DSR minimo", actual=float(dsr_val), threshold=thresholds["dsr_min"])
        else:
            check("dsr_min", True, "DSR no disponible (skip)", actual=None, threshold=thresholds["dsr_min"], skipped=True)

        passed = all(bool(row["ok"]) for row in checks)
        failed_ids = [row["id"] for row in checks if not row["ok"]]
        return {
            "passed": passed,
            "failed_ids": failed_ids,
            "checks": checks,
            "thresholds": thresholds,
            "summary": "PASS" if passed else f"FAIL ({', '.join(failed_ids)})",
        }

from __future__ import annotations

from typing import Any


DEFAULT_COMPARE_THRESHOLDS: dict[str, float] = {
    "min_expectancy_gain_pct": 5.0,
    "min_net_pnl_gain_pct": 3.0,
    "max_dd_worsen_pct": 2.0,
    "max_costs_increase_pct": 10.0,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _normalize_orderflow_feature_set(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"orderflow_on", "on", "enabled", "true", "1"}:
        return "orderflow_on"
    if text in {"orderflow_off", "off", "disabled", "false", "0", "ohlc_only"}:
        return "orderflow_off"
    return "orderflow_unknown"


def _extract_orderflow_feature_set(report: dict[str, Any]) -> tuple[str, str]:
    direct = _normalize_orderflow_feature_set(report.get("orderflow_feature_set") or report.get("feature_set"))
    if direct != "orderflow_unknown":
        return direct, "report_field"

    if isinstance(report.get("use_orderflow_data"), bool):
        return ("orderflow_on" if bool(report.get("use_orderflow_data")) else "orderflow_off"), "report_flag"

    params = report.get("params") if isinstance(report.get("params"), dict) else {}
    if isinstance(params.get("use_orderflow_data"), bool):
        return ("orderflow_on" if bool(params.get("use_orderflow_data")) else "orderflow_off"), "params"

    params_json = report.get("params_json") if isinstance(report.get("params_json"), dict) else {}
    if isinstance(params_json.get("use_orderflow_data"), bool):
        return ("orderflow_on" if bool(params_json.get("use_orderflow_data")) else "orderflow_off"), "params_json"

    metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    mset = _normalize_orderflow_feature_set(metadata.get("orderflow_feature_set"))
    if mset != "orderflow_unknown":
        return mset, "metadata"
    if isinstance(metadata.get("use_orderflow_data"), bool):
        return ("orderflow_on" if bool(metadata.get("use_orderflow_data")) else "orderflow_off"), "metadata_flag"

    flags = report.get("flags") if isinstance(report.get("flags"), dict) else {}
    fset = _normalize_orderflow_feature_set(flags.get("ORDERFLOW_FEATURE_SET"))
    if fset != "orderflow_unknown":
        return fset, "flags"
    if isinstance(flags.get("ORDERFLOW_ENABLED"), bool):
        return ("orderflow_on" if bool(flags.get("ORDERFLOW_ENABLED")) else "orderflow_off"), "flags_bool"

    tags = report.get("tags") if isinstance(report.get("tags"), list) else []
    tag_values = {str(x).strip().lower() for x in tags if str(x).strip()}
    if "feature_set:orderflow_off" in tag_values:
        return "orderflow_off", "tags"
    if "feature_set:orderflow_on" in tag_values:
        return "orderflow_on", "tags"

    # Backward compatibility: historic runs assumed order flow ON when missing.
    return "orderflow_on", "default_backward_compat"


class CompareEngine:
    def __init__(self, thresholds: dict[str, Any] | None = None) -> None:
        incoming = thresholds or {}
        self.thresholds = {**DEFAULT_COMPARE_THRESHOLDS, **{k: _safe_float(v, DEFAULT_COMPARE_THRESHOLDS.get(k, 0.0)) for k, v in incoming.items()}}

    def compare(self, baseline_report: dict[str, Any], candidate_report: dict[str, Any]) -> dict[str, Any]:
        b_metrics = baseline_report.get("metrics") if isinstance(baseline_report.get("metrics"), dict) else {}
        c_metrics = candidate_report.get("metrics") if isinstance(candidate_report.get("metrics"), dict) else {}
        b_costs = baseline_report.get("costs_breakdown") if isinstance(baseline_report.get("costs_breakdown"), dict) else {}
        c_costs = candidate_report.get("costs_breakdown") if isinstance(candidate_report.get("costs_breakdown"), dict) else {}
        checks: list[dict[str, Any]] = []

        def check(check_id: str, ok: bool, reason: str, **details: Any) -> None:
            checks.append({"id": check_id, "ok": bool(ok), "reason": reason, "details": details})

        b_feature_set, b_feature_source = _extract_orderflow_feature_set(baseline_report)
        c_feature_set, c_feature_source = _extract_orderflow_feature_set(candidate_report)
        check(
            "same_feature_set",
            b_feature_set == c_feature_set,
            "Baseline y candidato deben usar el mismo set de features (order flow ON/OFF)",
            baseline=b_feature_set,
            candidate=c_feature_set,
            baseline_source=b_feature_source,
            candidate_source=c_feature_source,
        )

        same_dataset_hash = str(candidate_report.get("dataset_hash") or "") == str(baseline_report.get("dataset_hash") or "")
        check(
            "same_dataset_hash",
            same_dataset_hash,
            "Baseline y candidato deben usar mismo dataset_hash",
            baseline=baseline_report.get("dataset_hash"),
            candidate=candidate_report.get("dataset_hash"),
        )

        same_period = (baseline_report.get("period") or {}) == (candidate_report.get("period") or {})
        check(
            "same_oos_period",
            same_period,
            "Baseline y candidato deben usar mismo periodo/OOS",
            baseline=baseline_report.get("period"),
            candidate=candidate_report.get("period"),
        )

        b_expectancy = _safe_float(b_metrics.get("expectancy_usd_per_trade", b_metrics.get("expectancy")))
        c_expectancy = _safe_float(c_metrics.get("expectancy_usd_per_trade", c_metrics.get("expectancy")))
        b_net = _safe_float(b_costs.get("net_pnl_total", _safe_float(b_costs.get("gross_pnl_total")) - _safe_float(b_costs.get("total_cost"))))
        c_net = _safe_float(c_costs.get("net_pnl_total", _safe_float(c_costs.get("gross_pnl_total")) - _safe_float(c_costs.get("total_cost"))))

        exp_threshold = b_expectancy * (1.0 + self.thresholds["min_expectancy_gain_pct"] / 100.0)
        net_threshold = b_net * (1.0 + self.thresholds["min_net_pnl_gain_pct"] / 100.0)
        expectancy_gain_ok = c_expectancy >= exp_threshold
        net_gain_ok = c_net >= net_threshold
        check(
            "improve_expectancy_or_net_pnl",
            expectancy_gain_ok or net_gain_ok,
            "Mejora minima vs baseline (expectancy o net_pnl)",
            baseline_expectancy=b_expectancy,
            candidate_expectancy=c_expectancy,
            expectancy_threshold=exp_threshold,
            baseline_net_pnl=b_net,
            candidate_net_pnl=c_net,
            net_pnl_threshold=net_threshold,
        )

        b_dd = abs(_safe_float(b_metrics.get("max_dd"))) * 100.0
        c_dd = abs(_safe_float(c_metrics.get("max_dd"))) * 100.0
        max_dd_allowed = b_dd + self.thresholds["max_dd_worsen_pct"]
        check(
            "max_dd_worsen_limit",
            c_dd <= max_dd_allowed,
            "DD candidato no debe empeorar mas del umbral",
            baseline_max_dd_pct=b_dd,
            candidate_max_dd_pct=c_dd,
            allowed_pct=max_dd_allowed,
        )

        b_cost_total = _safe_float(b_costs.get("total_cost"))
        c_cost_total = _safe_float(c_costs.get("total_cost"))
        cost_increase_limit = b_cost_total * (1.0 + self.thresholds["max_costs_increase_pct"] / 100.0)
        net_gain_pct = 0.0
        if abs(b_net) > 1e-9:
            net_gain_pct = ((c_net - b_net) / abs(b_net)) * 100.0
        cost_ok = c_cost_total <= cost_increase_limit or net_gain_pct >= 8.0
        check(
            "cost_increase_limit",
            cost_ok,
            "Costos no deben subir demasiado salvo mejora neta >= 8%",
            baseline_costs_total=b_cost_total,
            candidate_costs_total=c_cost_total,
            allowed_total=cost_increase_limit,
            net_pnl_gain_pct=round(net_gain_pct, 4),
        )

        passed = all(bool(row["ok"]) for row in checks)
        return {
            "passed": passed,
            "failed_ids": [row["id"] for row in checks if not row["ok"]],
            "checks": checks,
            "thresholds": self.thresholds,
            "summary": "PASS" if passed else "FAIL",
        }

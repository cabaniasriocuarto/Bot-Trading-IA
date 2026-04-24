from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from rtlab_core.learning import deflated_sharpe_ratio, probabilistic_sharpe_ratio


DEFAULT_INDEPENDENT_VALIDATION_POLICY: dict[str, Any] = {
    "pbo": {
        "enabled": True,
        "reject_if_gt": 0.05,
        "source": "config/policies/gates.yaml:gates.pbo.reject_if_gt",
    },
    "dsr": {
        "enabled": True,
        "min_required": 0.95,
        "source": "config/policies/gates.yaml:gates.dsr.min_dsr",
    },
    "psr": {
        "enabled": True,
        "review_if_gte": 0.80,
        "favorable_if_gte": 0.95,
        "source": "config/policies/gates.yaml:gates.psr",
    },
    "eligible_promotion_stages": ["paper", "testnet"],
    "source_path": "config/policies/gates.yaml",
}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _extract_returns(run_payload: dict[str, Any]) -> list[float]:
    trades = run_payload.get("trades") if isinstance(run_payload.get("trades"), list) else []
    returns: list[float] = []
    for row in trades:
        if not isinstance(row, dict):
            continue
        for key in ("pnl_net", "realized_pnl_net", "net_pnl", "pnl"):
            value = _safe_float(row.get(key))
            if value is not None:
                returns.append(float(value))
                break
    if returns:
        return returns

    curve = run_payload.get("equity_curve") if isinstance(run_payload.get("equity_curve"), list) else []
    equity_values: list[float] = []
    for row in curve:
        if not isinstance(row, dict):
            continue
        value = _safe_float(row.get("equity"))
        if value is not None:
            equity_values.append(float(value))
    if len(equity_values) < 2:
        return []
    return [round(equity_values[idx] - equity_values[idx - 1], 8) for idx in range(1, len(equity_values))]


def _load_policy(repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[3]).resolve()
    path = root / "config" / "policies" / "gates.yaml"
    policy: dict[str, Any] = {
        "pbo": dict(DEFAULT_INDEPENDENT_VALIDATION_POLICY["pbo"]),
        "dsr": dict(DEFAULT_INDEPENDENT_VALIDATION_POLICY["dsr"]),
        "psr": dict(DEFAULT_INDEPENDENT_VALIDATION_POLICY["psr"]),
        "eligible_promotion_stages": list(DEFAULT_INDEPENDENT_VALIDATION_POLICY["eligible_promotion_stages"]),
        "source_path": str(path),
    }
    if not path.exists():
        return policy

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        raw = {}
    gates = raw.get("gates") if isinstance(raw, dict) and isinstance(raw.get("gates"), dict) else {}
    pbo_cfg = gates.get("pbo") if isinstance(gates.get("pbo"), dict) else {}
    dsr_cfg = gates.get("dsr") if isinstance(gates.get("dsr"), dict) else {}
    psr_cfg = gates.get("psr") if isinstance(gates.get("psr"), dict) else {}

    if isinstance(pbo_cfg.get("enabled"), bool):
        policy["pbo"]["enabled"] = bool(pbo_cfg.get("enabled"))
    if _is_numeric(pbo_cfg.get("reject_if_gt")):
        policy["pbo"]["reject_if_gt"] = float(pbo_cfg.get("reject_if_gt"))
    if isinstance(dsr_cfg.get("enabled"), bool):
        policy["dsr"]["enabled"] = bool(dsr_cfg.get("enabled"))
    if _is_numeric(dsr_cfg.get("min_dsr")):
        policy["dsr"]["min_required"] = float(dsr_cfg.get("min_dsr"))
    if isinstance(psr_cfg.get("enabled"), bool):
        policy["psr"]["enabled"] = bool(psr_cfg.get("enabled"))
    if _is_numeric(psr_cfg.get("review_if_gte")):
        policy["psr"]["review_if_gte"] = float(psr_cfg.get("review_if_gte"))
    if _is_numeric(psr_cfg.get("favorable_if_gte")):
        policy["psr"]["favorable_if_gte"] = float(psr_cfg.get("favorable_if_gte"))
    reject_if_lt = psr_cfg.get("reject_if_lt")
    if _is_numeric(reject_if_lt):
        policy["psr"]["reject_if_lt"] = float(reject_if_lt)
    else:
        policy["psr"]["reject_if_lt"] = min(
            float(policy["psr"]["review_if_gte"]),
            0.80,
        )
    return policy


def build_independent_validation_contract(
    *,
    run_payload: dict[str, Any],
    repo_root: Path | None = None,
) -> dict[str, Any]:
    policy = _load_policy(repo_root=repo_root)
    metrics = run_payload.get("metrics") if isinstance(run_payload.get("metrics"), dict) else {}
    provenance = run_payload.get("provenance") if isinstance(run_payload.get("provenance"), dict) else {}
    validation_summary = run_payload.get("validation_summary") if isinstance(run_payload.get("validation_summary"), dict) else {}
    params_json = run_payload.get("params_json") if isinstance(run_payload.get("params_json"), dict) else {}

    run_id = _first_text(run_payload.get("run_id"), run_payload.get("catalog_run_id"), run_payload.get("id"))
    strategy_id = _first_text(run_payload.get("strategy_id"), provenance.get("strategy_id"))
    strategy_version = _first_text(run_payload.get("strategy_version"), provenance.get("strategy_version"))
    strategy_config_hash = _first_text(run_payload.get("strategy_config_hash"), provenance.get("strategy_config_hash"))
    dataset_source = _first_text(run_payload.get("dataset_source"), run_payload.get("data_source"), provenance.get("dataset_source"))
    dataset_hash = _first_text(run_payload.get("dataset_hash"), provenance.get("dataset_hash"))
    validation_mode = _first_text(
        run_payload.get("validation_mode"),
        validation_summary.get("mode"),
        params_json.get("validation_mode"),
    ).lower() or "unknown"

    returns = _extract_returns(run_payload)
    dsr_payload = deflated_sharpe_ratio(returns, trials=max(1, len(returns))) if returns else {}
    computed_psr = probabilistic_sharpe_ratio(returns) if returns else None

    explicit_pbo_value = _safe_float(metrics.get("pbo"))
    explicit_dsr_value = _safe_float(metrics.get("dsr"))
    explicit_psr_value = _safe_float(metrics.get("psr"))
    pbo_value = explicit_pbo_value
    dsr_value = explicit_dsr_value
    psr_value = explicit_psr_value
    sharpe_observed = _safe_float(metrics.get("sharpe"))

    if dsr_value is None and dsr_payload:
        dsr_value = _safe_float(dsr_payload.get("dsr"))
    if psr_value is None:
        psr_value = _safe_float(computed_psr)
    if sharpe_observed is None and dsr_payload:
        sharpe_observed = _safe_float(dsr_payload.get("sharpe"))

    metric_assessment: dict[str, Any] = {}
    rejection_reasons: list[str] = []
    review_reasons: list[str] = []

    if not run_id:
        rejection_reasons.append("missing_run_id")
    if not strategy_id:
        rejection_reasons.append("missing_strategy_id")
    if not dataset_hash:
        rejection_reasons.append("missing_dataset_hash")
    if not strategy_config_hash:
        rejection_reasons.append("missing_strategy_config_hash")

    pbo_threshold = float(policy["pbo"]["reject_if_gt"])
    if pbo_value is None:
        metric_assessment["pbo"] = {"status": "missing", "value": None, "reject_if_gt": pbo_threshold, "source": "missing"}
        review_reasons.append("missing_pbo")
    else:
        pbo_ok = (not bool(policy["pbo"]["enabled"])) or float(pbo_value) <= pbo_threshold
        metric_assessment["pbo"] = {
            "status": "favorable" if pbo_ok else "reject",
            "value": float(pbo_value),
            "reject_if_gt": pbo_threshold,
            "source": "metrics",
        }
        if not pbo_ok:
            rejection_reasons.append("pbo_above_policy_threshold")

    dsr_threshold = float(policy["dsr"]["min_required"])
    if dsr_value is None:
        metric_assessment["dsr"] = {"status": "missing", "value": None, "min_required": dsr_threshold, "source": "missing"}
        review_reasons.append("missing_dsr")
    elif explicit_dsr_value is None:
        metric_assessment["dsr"] = {
            "status": "review",
            "value": float(dsr_value),
            "min_required": dsr_threshold,
            "source": "derived_from_returns",
        }
        review_reasons.append("dsr_derived_from_returns_only")
    else:
        dsr_ok = (not bool(policy["dsr"]["enabled"])) or float(dsr_value) >= dsr_threshold
        metric_assessment["dsr"] = {
            "status": "favorable" if dsr_ok else "reject",
            "value": float(dsr_value),
            "min_required": dsr_threshold,
            "source": "metrics",
        }
        if not dsr_ok:
            rejection_reasons.append("dsr_below_policy_threshold")

    psr_review_if_gte = float(policy["psr"]["review_if_gte"])
    psr_favorable_if_gte = float(policy["psr"]["favorable_if_gte"])
    psr_reject_if_lt = float(policy["psr"]["reject_if_lt"])
    if psr_value is None:
        metric_assessment["psr"] = {
            "status": "missing",
            "value": None,
            "reject_if_lt": psr_reject_if_lt,
            "review_if_gte": psr_review_if_gte,
            "favorable_if_gte": psr_favorable_if_gte,
            "source": "missing",
        }
        review_reasons.append("missing_psr")
    elif explicit_psr_value is None:
        metric_assessment["psr"] = {
            "status": "review",
            "value": float(psr_value),
            "reject_if_lt": psr_reject_if_lt,
            "review_if_gte": psr_review_if_gte,
            "favorable_if_gte": psr_favorable_if_gte,
            "source": "derived_from_returns",
        }
        review_reasons.append("psr_derived_from_returns_only")
    elif float(psr_value) >= psr_favorable_if_gte:
        metric_assessment["psr"] = {
            "status": "favorable",
            "value": float(psr_value),
            "reject_if_lt": psr_reject_if_lt,
            "review_if_gte": psr_review_if_gte,
            "favorable_if_gte": psr_favorable_if_gte,
            "source": "metrics",
        }
    elif float(psr_value) >= psr_review_if_gte:
        metric_assessment["psr"] = {
            "status": "review",
            "value": float(psr_value),
            "reject_if_lt": psr_reject_if_lt,
            "review_if_gte": psr_review_if_gte,
            "favorable_if_gte": psr_favorable_if_gte,
            "source": "metrics",
        }
        review_reasons.append("psr_requires_manual_review")
    elif float(psr_value) < psr_reject_if_lt:
        metric_assessment["psr"] = {
            "status": "reject",
            "value": float(psr_value),
            "reject_if_lt": psr_reject_if_lt,
            "review_if_gte": psr_review_if_gte,
            "favorable_if_gte": psr_favorable_if_gte,
            "source": "metrics",
        }
        rejection_reasons.append("psr_below_reject_threshold")
    else:
        metric_assessment["psr"] = {
            "status": "review",
            "value": float(psr_value),
            "reject_if_lt": psr_reject_if_lt,
            "review_if_gte": psr_review_if_gte,
            "favorable_if_gte": psr_favorable_if_gte,
            "source": "metrics",
        }
        review_reasons.append("psr_requires_manual_review")

    evidence_window = {
        "validation_mode": validation_mode,
        "timerange_from": _first_text((run_payload.get("period") or {}).get("start"), run_payload.get("timerange_from"), provenance.get("from")),
        "timerange_to": _first_text((run_payload.get("period") or {}).get("end"), run_payload.get("timerange_to"), provenance.get("to")),
        "dataset_range": run_payload.get("dataset_range") if isinstance(run_payload.get("dataset_range"), dict) else {},
        "cpcv_slices_count": int(validation_summary.get("n_splits") or validation_summary.get("folds") or 0),
        "cpcv_paths_evaluated": int(validation_summary.get("paths_evaluated") or 0),
    }
    validation_scope = "independent_validation_per_run"
    if validation_mode in {"walk-forward", "purged-cv", "cpcv"}:
        validation_scope = f"independent_validation_per_run:{validation_mode}"

    oos_ready = validation_mode in {"walk-forward", "purged-cv", "cpcv"}
    if not oos_ready:
        review_reasons.append("validation_mode_not_reusable_for_promotion")

    status = "REJECT" if rejection_reasons else ("REVIEW" if review_reasons else "PASS")
    promotion_stage_eligible = list(policy["eligible_promotion_stages"]) if status == "PASS" and oos_ready else []

    return {
        "contract_version": "rtlrese32/v1",
        "validation_scope": validation_scope,
        "run_id": run_id,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version or None,
        "dataset_source": dataset_source,
        "dataset_hash": dataset_hash,
        "params_hash": strategy_config_hash,
        "sharpe_observed": sharpe_observed,
        "pbo": pbo_value,
        "cscv_slices_count": evidence_window["cpcv_slices_count"] or None,
        "cscv_paths_evaluated": evidence_window["cpcv_paths_evaluated"] or None,
        "psr": psr_value,
        "dsr": dsr_value,
        "metric_assessment": metric_assessment,
        "rejection_reasons": rejection_reasons,
        "review_reasons": review_reasons,
        "pass_fail_status": status,
        "reusable_for_promotion": bool(status == "PASS"),
        "promotion_stage_eligible": promotion_stage_eligible,
        "computed_at": _utc_iso(),
        "evidence_window": evidence_window,
        "provenance": {
            "code_commit_hash": _first_text(run_payload.get("git_commit"), run_payload.get("code_commit_hash"), provenance.get("commit_hash")) or None,
            "strategy_config_hash": strategy_config_hash or None,
            "dataset_hash": dataset_hash or None,
            "source_path": str(policy.get("source_path") or DEFAULT_INDEPENDENT_VALIDATION_POLICY["source_path"]),
        },
        "thresholds": {
            "pbo_policy_reject_if_gt": pbo_threshold,
            "dsr_policy_min_required": dsr_threshold,
            "psr_review_if_gte": psr_review_if_gte,
            "psr_favorable_if_gte": psr_favorable_if_gte,
            "psr_reject_if_lt": psr_reject_if_lt,
        },
    }

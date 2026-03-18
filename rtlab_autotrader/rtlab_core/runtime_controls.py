from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from rtlab_core.policy_paths import resolve_policy_root


RUNTIME_CONTROLS_FILENAME = "runtime_controls.yaml"

DEFAULT_RUNTIME_CONTROLS: dict[str, Any] = {
    "execution_modes": {
        "default_global_runtime_mode": "paper",
        "global_runtime_modes": ["paper", "testnet", "live"],
        "bot_policy_modes": ["shadow", "paper", "testnet", "live"],
        "research_evidence_modes": ["backtest", "shadow", "paper", "testnet"],
        "shadow": {
            "counts_as_real_runtime": False,
            "allowed_global_runtimes": ["paper", "testnet", "live"],
            "requires_bot_mode": "shadow",
        },
        "legacy_aliases": {
            "mock": {
                "canonical_category": "local_frontend_alias",
                "counts_as_real_runtime": False,
            },
            "demo": {
                "canonical_category": "research_legacy_context",
                "counts_as_real_runtime": False,
            },
        },
    },
    "observability": {
        "runtime_telemetry": {
            "real_source": "runtime_loop_v1",
            "synthetic_source": "synthetic_v1",
            "fail_closed_when_not_real": True,
        },
        "logging": {
            "security_internal_header_alert_throttle_sec": 60,
        },
    },
    "drift": {
        "default_algorithm": "adwin",
        "min_points": 20,
        "trigger_votes_required": 2,
        "metrics": [
            "returns",
            "realized_vol",
            "atr",
            "spread_bps",
            "slippage_bps",
            "expectancy_usd",
            "max_dd",
        ],
        "adwin": {
            "mean_shift_zscore_threshold": 1.1,
        },
        "page_hinkley": {
            "delta": 0.01,
            "lambda": 5.0,
        },
    },
    "health_scoring": {
        "circuit_breakers": {
            "max_error_streak": 3,
            "max_ws_lag_ms": 5000,
            "max_desync_count": 2,
            "max_spread_spike_bps": 25.0,
            "max_vpin_percentile": 90.0,
        },
        "execution_guard": {
            "critical_error_limit": 5,
        },
    },
    "alert_thresholds": {
        "breaker_integrity": {
            "integrity_window_hours": 24,
            "unknown_ratio_warn": 0.10,
            "min_events_warn": 10,
        },
        "operations": {
            "drift_enabled": True,
            "slippage_p95_warn_bps": 8.0,
            "api_errors_warn": 1,
            "breaker_window_hours": 24,
        },
    },
}


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@lru_cache(maxsize=8)
def _load_runtime_controls_bundle_cached(repo_root_str: str, explicit_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    selected_root = resolve_policy_root(repo_root, explicit=explicit_root).resolve()
    policy_path = (selected_root / RUNTIME_CONTROLS_FILENAME).resolve()

    payload: dict[str, Any] = {}
    valid = False
    if policy_path.exists():
        try:
            raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
            candidate = raw.get("runtime_controls") if isinstance(raw.get("runtime_controls"), dict) else {}
            if isinstance(candidate, dict) and candidate:
                payload = candidate
                valid = True
        except Exception:
            payload = {}
            valid = False

    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "source": "config/policies/runtime_controls.yaml" if valid else "default_fail_closed",
        "runtime_controls": _deep_merge(DEFAULT_RUNTIME_CONTROLS, payload),
    }


def load_runtime_controls_bundle(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(_load_runtime_controls_bundle_cached(str(resolved_repo_root), explicit_root_str))


def runtime_controls_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_runtime_controls_bundle(repo_root, explicit_root=explicit_root)
    controls = bundle.get("runtime_controls")
    return controls if isinstance(controls, dict) else copy.deepcopy(DEFAULT_RUNTIME_CONTROLS)


def execution_modes_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    section = controls.get("execution_modes")
    return section if isinstance(section, dict) else copy.deepcopy(DEFAULT_RUNTIME_CONTROLS["execution_modes"])


def observability_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    section = controls.get("observability")
    return section if isinstance(section, dict) else copy.deepcopy(DEFAULT_RUNTIME_CONTROLS["observability"])


def drift_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    section = controls.get("drift")
    return section if isinstance(section, dict) else copy.deepcopy(DEFAULT_RUNTIME_CONTROLS["drift"])


def health_scoring_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    section = controls.get("health_scoring")
    return section if isinstance(section, dict) else copy.deepcopy(DEFAULT_RUNTIME_CONTROLS["health_scoring"])


def alert_thresholds_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    section = controls.get("alert_thresholds")
    return section if isinstance(section, dict) else copy.deepcopy(DEFAULT_RUNTIME_CONTROLS["alert_thresholds"])


def default_global_runtime_mode(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> str:
    cfg = execution_modes_policy(repo_root, explicit_root=explicit_root)
    modes = [str(row).strip().lower() for row in (cfg.get("global_runtime_modes") or []) if str(row).strip()]
    default_mode = str(cfg.get("default_global_runtime_mode") or "").strip().lower()
    if default_mode in modes:
        return default_mode
    return modes[0] if modes else "paper"


def default_drift_algorithm(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> str:
    cfg = drift_policy(repo_root, explicit_root=explicit_root)
    algo = str(cfg.get("default_algorithm") or "").strip().lower()
    return algo if algo in {"adwin", "page_hinkley"} else "adwin"

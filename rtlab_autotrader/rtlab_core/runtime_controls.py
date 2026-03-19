from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from rtlab_core.policy_paths import resolve_policy_root


RUNTIME_CONTROLS_FILENAME = "runtime_controls.yaml"

RUNTIME_CONTROL_GROUPS: tuple[str, ...] = (
    "execution_modes",
    "observability",
    "drift",
    "health_scoring",
    "alert_thresholds",
)

FAIL_CLOSED_MINIMAL_RUNTIME_CONTROLS: dict[str, Any] = {
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
        "min_points": 1000000,
        "trigger_votes_required": 1000000,
        "metrics": [],
        "adwin": {
            "mean_shift_zscore_threshold": 1000000.0,
        },
        "page_hinkley": {
            "delta": 1.0,
            "lambda": 1000000.0,
        },
    },
    "health_scoring": {
        "circuit_breakers": {
            "max_error_streak": 1,
            "max_ws_lag_ms": 1,
            "max_desync_count": 0,
            "max_spread_spike_bps": 0.0,
            "max_vpin_percentile": 0.0,
        },
        "execution_guard": {
            "critical_error_limit": 1,
        },
    },
    "alert_thresholds": {
        "breaker_integrity": {
            "integrity_window_hours": 1,
            "unknown_ratio_warn": 0.0,
            "min_events_warn": 1,
        },
        "operations": {
            "drift_enabled": True,
            "slippage_p95_warn_bps": 0.0,
            "api_errors_warn": 1,
            "breaker_window_hours": 1,
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


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_controls_source_label(repo_root: Path, policy_path: Path) -> str:
    try:
        return str(policy_path.relative_to(repo_root).as_posix())
    except Exception:
        return str(policy_path)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_dict(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{path}.{key} debe ser dict")
        return {}
    return value


def _require_list(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list) or not value:
        errors.append(f"{path}.{key} debe ser lista no vacia")
        return []
    return value


def _require_str(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} debe ser string no vacio")
        return ""
    return value.strip()


def _require_bool(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        errors.append(f"{path}.{key} debe ser bool")
        return False
    return value


def _require_number(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> float:
    value = parent.get(key)
    if not _is_number(value):
        errors.append(f"{path}.{key} debe ser numero")
        return 0.0
    return float(value)


def _validate_runtime_controls(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return ["runtime_controls debe ser dict"]

    for group in RUNTIME_CONTROL_GROUPS:
        if not isinstance(candidate.get(group), dict):
            errors.append(f"runtime_controls.{group} debe ser dict")

    execution_modes = _require_dict(candidate, "execution_modes", errors=errors, path="runtime_controls")
    _require_str(execution_modes, "default_global_runtime_mode", errors=errors, path="runtime_controls.execution_modes")
    _require_list(execution_modes, "global_runtime_modes", errors=errors, path="runtime_controls.execution_modes")
    _require_list(execution_modes, "bot_policy_modes", errors=errors, path="runtime_controls.execution_modes")
    _require_list(execution_modes, "research_evidence_modes", errors=errors, path="runtime_controls.execution_modes")
    shadow = _require_dict(execution_modes, "shadow", errors=errors, path="runtime_controls.execution_modes")
    _require_bool(shadow, "counts_as_real_runtime", errors=errors, path="runtime_controls.execution_modes.shadow")
    _require_list(shadow, "allowed_global_runtimes", errors=errors, path="runtime_controls.execution_modes.shadow")
    _require_str(shadow, "requires_bot_mode", errors=errors, path="runtime_controls.execution_modes.shadow")
    legacy_aliases = _require_dict(execution_modes, "legacy_aliases", errors=errors, path="runtime_controls.execution_modes")
    for alias, payload in legacy_aliases.items():
        alias_payload = payload if isinstance(payload, dict) else {}
        if not isinstance(payload, dict):
            errors.append(f"runtime_controls.execution_modes.legacy_aliases.{alias} debe ser dict")
            continue
        _require_str(
            alias_payload,
            "canonical_category",
            errors=errors,
            path=f"runtime_controls.execution_modes.legacy_aliases.{alias}",
        )
        _require_bool(
            alias_payload,
            "counts_as_real_runtime",
            errors=errors,
            path=f"runtime_controls.execution_modes.legacy_aliases.{alias}",
        )

    observability = _require_dict(candidate, "observability", errors=errors, path="runtime_controls")
    runtime_telemetry = _require_dict(observability, "runtime_telemetry", errors=errors, path="runtime_controls.observability")
    _require_str(runtime_telemetry, "real_source", errors=errors, path="runtime_controls.observability.runtime_telemetry")
    _require_str(runtime_telemetry, "synthetic_source", errors=errors, path="runtime_controls.observability.runtime_telemetry")
    _require_bool(
        runtime_telemetry,
        "fail_closed_when_not_real",
        errors=errors,
        path="runtime_controls.observability.runtime_telemetry",
    )
    logging_cfg = _require_dict(observability, "logging", errors=errors, path="runtime_controls.observability")
    _require_number(
        logging_cfg,
        "security_internal_header_alert_throttle_sec",
        errors=errors,
        path="runtime_controls.observability.logging",
    )

    drift = _require_dict(candidate, "drift", errors=errors, path="runtime_controls")
    _require_str(drift, "default_algorithm", errors=errors, path="runtime_controls.drift")
    _require_number(drift, "min_points", errors=errors, path="runtime_controls.drift")
    _require_number(drift, "trigger_votes_required", errors=errors, path="runtime_controls.drift")
    _require_list(drift, "metrics", errors=errors, path="runtime_controls.drift")
    adwin_cfg = _require_dict(drift, "adwin", errors=errors, path="runtime_controls.drift")
    _require_number(adwin_cfg, "mean_shift_zscore_threshold", errors=errors, path="runtime_controls.drift.adwin")
    page_hinkley_cfg = _require_dict(drift, "page_hinkley", errors=errors, path="runtime_controls.drift")
    _require_number(page_hinkley_cfg, "delta", errors=errors, path="runtime_controls.drift.page_hinkley")
    _require_number(page_hinkley_cfg, "lambda", errors=errors, path="runtime_controls.drift.page_hinkley")

    health_scoring = _require_dict(candidate, "health_scoring", errors=errors, path="runtime_controls")
    circuit_breakers = _require_dict(
        health_scoring,
        "circuit_breakers",
        errors=errors,
        path="runtime_controls.health_scoring",
    )
    _require_number(circuit_breakers, "max_error_streak", errors=errors, path="runtime_controls.health_scoring.circuit_breakers")
    _require_number(circuit_breakers, "max_ws_lag_ms", errors=errors, path="runtime_controls.health_scoring.circuit_breakers")
    _require_number(circuit_breakers, "max_desync_count", errors=errors, path="runtime_controls.health_scoring.circuit_breakers")
    _require_number(
        circuit_breakers,
        "max_spread_spike_bps",
        errors=errors,
        path="runtime_controls.health_scoring.circuit_breakers",
    )
    _require_number(
        circuit_breakers,
        "max_vpin_percentile",
        errors=errors,
        path="runtime_controls.health_scoring.circuit_breakers",
    )
    execution_guard = _require_dict(health_scoring, "execution_guard", errors=errors, path="runtime_controls.health_scoring")
    _require_number(
        execution_guard,
        "critical_error_limit",
        errors=errors,
        path="runtime_controls.health_scoring.execution_guard",
    )

    alert_thresholds = _require_dict(candidate, "alert_thresholds", errors=errors, path="runtime_controls")
    breaker_integrity = _require_dict(
        alert_thresholds,
        "breaker_integrity",
        errors=errors,
        path="runtime_controls.alert_thresholds",
    )
    _require_number(
        breaker_integrity,
        "integrity_window_hours",
        errors=errors,
        path="runtime_controls.alert_thresholds.breaker_integrity",
    )
    _require_number(
        breaker_integrity,
        "unknown_ratio_warn",
        errors=errors,
        path="runtime_controls.alert_thresholds.breaker_integrity",
    )
    _require_number(
        breaker_integrity,
        "min_events_warn",
        errors=errors,
        path="runtime_controls.alert_thresholds.breaker_integrity",
    )
    operations = _require_dict(alert_thresholds, "operations", errors=errors, path="runtime_controls.alert_thresholds")
    _require_bool(operations, "drift_enabled", errors=errors, path="runtime_controls.alert_thresholds.operations")
    _require_number(
        operations,
        "slippage_p95_warn_bps",
        errors=errors,
        path="runtime_controls.alert_thresholds.operations",
    )
    _require_number(operations, "api_errors_warn", errors=errors, path="runtime_controls.alert_thresholds.operations")
    _require_number(
        operations,
        "breaker_window_hours",
        errors=errors,
        path="runtime_controls.alert_thresholds.operations",
    )
    return errors


def clear_runtime_controls_cache() -> None:
    _load_runtime_controls_bundle_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_runtime_controls_bundle_cached(repo_root_str: str, explicit_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    selected_root = resolve_policy_root(repo_root, explicit=explicit_root).resolve()
    policy_path = (selected_root / RUNTIME_CONTROLS_FILENAME).resolve()

    source_hash = _file_sha256(policy_path)
    payload: dict[str, Any] = {}
    errors: list[str] = []
    valid = False
    if policy_path.exists():
        try:
            raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
            candidate = raw.get("runtime_controls") if isinstance(raw.get("runtime_controls"), dict) else {}
            validation_errors = _validate_runtime_controls(candidate) if isinstance(candidate, dict) and candidate else ["runtime_controls vacio o ausente"]
            if isinstance(candidate, dict) and candidate and not validation_errors:
                payload = candidate
                valid = True
            else:
                errors.extend(validation_errors)
        except Exception:
            payload = {}
            valid = False
            errors.append("runtime_controls no pudo parsearse como YAML valido")
    else:
        errors.append("runtime_controls.yaml no existe en la raiz seleccionada")

    active_policy = copy.deepcopy(payload if valid else FAIL_CLOSED_MINIMAL_RUNTIME_CONTROLS)
    policy_hash = _stable_payload_hash(active_policy)

    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "source": _runtime_controls_source_label(repo_root, policy_path) if valid else "default_fail_closed_minimal",
        "source_hash": source_hash,
        "policy_hash": policy_hash,
        "errors": errors,
        "runtime_controls": active_policy,
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
    return controls if isinstance(controls, dict) else copy.deepcopy(FAIL_CLOSED_MINIMAL_RUNTIME_CONTROLS)


def execution_modes_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    return copy.deepcopy(controls["execution_modes"])


def observability_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    return copy.deepcopy(controls["observability"])


def drift_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    return copy.deepcopy(controls["drift"])


def health_scoring_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    return copy.deepcopy(controls["health_scoring"])


def alert_thresholds_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    controls = runtime_controls_policy(repo_root, explicit_root=explicit_root)
    return copy.deepcopy(controls["alert_thresholds"])


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

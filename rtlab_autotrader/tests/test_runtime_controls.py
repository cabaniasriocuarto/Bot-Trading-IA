from __future__ import annotations

import copy
import hashlib
import importlib
from pathlib import Path

import yaml

import rtlab_core.execution.exec_guard as exec_guard_module
import rtlab_core.learning.brain as brain_module
import rtlab_core.risk.circuit_breakers as circuit_breakers_module
import rtlab_core.runtime_controls as runtime_controls_module
from rtlab_core.mode_taxonomy import BOT_POLICY_MODES, GLOBAL_RUNTIME_MODES, RESEARCH_EVIDENCE_MODES, mode_taxonomy_payload
from rtlab_core.policy_paths import EXPECTED_POLICY_FILENAMES
from rtlab_core.runtime_controls import (
    alert_thresholds_policy,
    default_drift_algorithm,
    execution_modes_policy,
    health_scoring_policy,
    load_runtime_controls_bundle,
    observability_policy,
)


def _canonical_runtime_controls() -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    payload = yaml.safe_load((root / "config" / "policies" / "runtime_controls.yaml").read_text(encoding="utf-8")) or {}
    runtime_controls = payload.get("runtime_controls")
    assert isinstance(runtime_controls, dict)
    return runtime_controls


def _seed_policy_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED_POLICY_FILENAMES:
        target = root / name
        if not target.exists():
            target.write_text("placeholder: true\n", encoding="utf-8")


def _write_runtime_controls(root: Path, payload: dict[str, object]) -> Path:
    _seed_policy_tree(root)
    target = root / "runtime_controls.yaml"
    target.write_text(yaml.safe_dump({"runtime_controls": payload}, sort_keys=False), encoding="utf-8")
    return target


def test_runtime_controls_bundle_loads_canonical_policy_groups() -> None:
    bundle = load_runtime_controls_bundle()

    assert bundle["exists"] is True
    assert bundle["valid"] is True
    assert bundle["source"] == "config/policies/runtime_controls.yaml"

    execution_modes = execution_modes_policy()
    observability = observability_policy()
    health = health_scoring_policy()
    alerts = alert_thresholds_policy()

    assert execution_modes["global_runtime_modes"] == ["paper", "testnet", "live"]
    assert execution_modes["bot_policy_modes"] == ["shadow", "paper", "testnet", "live"]
    assert execution_modes["legacy_aliases"]["mock"]["counts_as_real_runtime"] is False
    assert observability["runtime_telemetry"]["real_source"] == "runtime_loop_v1"
    assert observability["logging"]["security_internal_header_alert_throttle_sec"] == 60
    assert default_drift_algorithm() == "adwin"
    assert health["circuit_breakers"]["max_ws_lag_ms"] == 5000
    assert health["execution_guard"]["critical_error_limit"] == 5
    assert alerts["operations"]["slippage_p95_warn_bps"] == 8.0
    assert alerts["breaker_integrity"]["unknown_ratio_warn"] == 0.10


def test_mode_taxonomy_payload_uses_runtime_controls_canonical_modes() -> None:
    payload = mode_taxonomy_payload()

    assert GLOBAL_RUNTIME_MODES == ("paper", "testnet", "live")
    assert BOT_POLICY_MODES == ("shadow", "paper", "testnet", "live")
    assert RESEARCH_EVIDENCE_MODES == ("backtest", "shadow", "paper", "testnet")
    assert payload["default_global_runtime_mode"] == "PAPER"
    assert payload["shadow_runtime_relation"]["counts_as_real_runtime"] is False
    assert payload["shadow_runtime_relation"]["allowed_global_runtimes"] == ["PAPER", "TESTNET", "LIVE"]
    assert payload["legacy_aliases_detail"]["MOCK"]["counts_as_real_runtime"] is False
    assert payload["legacy_aliases_detail"]["demo"]["canonical_category"] == "research_legacy_context"


def test_runtime_controls_bundle_exposes_source_hash_and_policy_hash() -> None:
    bundle = load_runtime_controls_bundle()
    source_path = Path(bundle["path"])
    expected_source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()

    assert bundle["source_hash"] == expected_source_hash
    assert isinstance(bundle["policy_hash"], str) and len(bundle["policy_hash"]) == 64
    assert bundle["errors"] == []


def test_runtime_controls_bundle_fails_closed_when_runtime_controls_yaml_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies = repo_root / "config" / "policies"
    root_policies.mkdir(parents=True, exist_ok=True)

    bundle = load_runtime_controls_bundle(repo_root=repo_root, explicit_root=root_policies)

    assert bundle["exists"] is False
    assert bundle["valid"] is False
    assert bundle["source"] == "default_fail_closed_minimal"
    assert bundle["source_hash"] == ""
    assert isinstance(bundle["policy_hash"], str) and len(bundle["policy_hash"]) == 64
    assert "no existe" in " ".join(bundle["errors"]).lower()
    assert bundle["runtime_controls"]["health_scoring"]["execution_guard"]["critical_error_limit"] == 1


def test_runtime_controls_bundle_uses_selected_canonical_yaml_hash_when_nested_diverges(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies = repo_root / "config" / "policies"
    nested_policies = repo_root / "rtlab_autotrader" / "config" / "policies"
    canonical_payload = copy.deepcopy(_canonical_runtime_controls())
    nested_payload = copy.deepcopy(canonical_payload)
    canonical_payload["drift"]["min_points"] = 33
    nested_payload["drift"]["min_points"] = 777

    root_path = _write_runtime_controls(root_policies, canonical_payload)
    _write_runtime_controls(nested_policies, nested_payload)

    bundle = load_runtime_controls_bundle(repo_root=repo_root, explicit_root=root_policies)

    assert bundle["path"] == str(root_path.resolve())
    assert bundle["source_hash"] == hashlib.sha256(root_path.read_bytes()).hexdigest()
    assert bundle["runtime_controls"]["drift"]["min_points"] == 33


def test_runtime_controls_consumers_follow_yaml_without_local_numeric_fallbacks(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    root_policies = repo_root / "config" / "policies"
    custom_payload = copy.deepcopy(_canonical_runtime_controls())
    custom_payload["drift"]["min_points"] = 37
    custom_payload["drift"]["trigger_votes_required"] = 4
    custom_payload["drift"]["adwin"]["mean_shift_zscore_threshold"] = 2.75
    custom_payload["health_scoring"]["circuit_breakers"]["max_ws_lag_ms"] = 4321
    custom_payload["health_scoring"]["execution_guard"]["critical_error_limit"] = 9
    _write_runtime_controls(root_policies, custom_payload)

    original_resolver = runtime_controls_module._resolve_repo_root_for_policy
    monkeypatch.setattr(runtime_controls_module, "_resolve_repo_root_for_policy", lambda: repo_root)
    runtime_controls_module.clear_runtime_controls_cache()
    try:
        brain = importlib.reload(brain_module)
        circuit_breakers = importlib.reload(circuit_breakers_module)
        exec_guard = importlib.reload(exec_guard_module)

        drift_payload = brain.detect_drift({"returns": [0.1, 0.2, 0.3], "spread_bps": [1.0, 1.1, 1.2]})
        assert drift_payload["trigger_votes_required"] == 4

        thresholds = circuit_breakers.CircuitBreakerThresholds()
        assert thresholds.max_ws_lag_ms == 4321

        class _SafeMode:
            def enable(self, _reason: str) -> None:
                return None

        class _KillSwitch:
            def trigger(self, _reason: str) -> None:
                return None

        guard = exec_guard.ExecutionGuard(
            circuit_breakers=circuit_breakers.CircuitBreakers(thresholds=thresholds),
            safe_mode=_SafeMode(),
            kill_switch=_KillSwitch(),
        )
        assert guard.critical_error_limit == 9
    finally:
        runtime_controls_module._resolve_repo_root_for_policy = original_resolver
        runtime_controls_module.clear_runtime_controls_cache()
        importlib.reload(brain_module)
        importlib.reload(circuit_breakers_module)
        importlib.reload(exec_guard_module)

from __future__ import annotations

from rtlab_core.mode_taxonomy import BOT_POLICY_MODES, GLOBAL_RUNTIME_MODES, RESEARCH_EVIDENCE_MODES, mode_taxonomy_payload
from rtlab_core.runtime_controls import (
  alert_thresholds_policy,
  default_drift_algorithm,
  execution_modes_policy,
  health_scoring_policy,
  load_runtime_controls_bundle,
  observability_policy,
)


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

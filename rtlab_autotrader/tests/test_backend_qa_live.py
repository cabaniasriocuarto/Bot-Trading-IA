from __future__ import annotations

from pathlib import Path

from test_rollout_safe_update import _force_runtime_contract_live_ready
from test_web_live_ready import _auth_headers, _build_app, _login, _mock_exchange_ok


def _enable_binance_testnet_env(monkeypatch) -> None:
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")


def _set_primary_strategy_live(client, headers: dict[str, str]) -> str:
  strategies = client.get("/api/v1/strategies", headers=headers)
  assert strategies.status_code == 200, strategies.text
  strategy_id = strategies.json()[0]["id"]
  set_live_primary = client.post(f"/api/v1/strategies/{strategy_id}/primary", headers=headers, json={"mode": "live"})
  assert set_live_primary.status_code == 200, set_live_primary.text
  return str(strategy_id)


def test_live_backend_qa_smoke_critical_fail_closed_surfaces(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  _enable_binance_testnet_env(monkeypatch)
  _mock_exchange_ok(module, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  _set_primary_strategy_live(client, headers)

  state = module.store.load_bot_state()
  state["runtime_engine"] = "real"
  module.store.save_bot_state(state)

  gates_payload = module.evaluate_gates("live", force_exchange_check=True)
  g9 = {row["id"]: row for row in gates_payload["gates"]}["G9_RUNTIME_ENGINE_REAL"]
  assert g9["status"] == "FAIL"
  runtime_contract = (g9.get("details") or {}).get("runtime_contract") or {}
  assert runtime_contract.get("ready_for_live") is False
  assert runtime_contract.get("missing_checks")

  policies = client.get("/api/v1/config/policies", headers=headers)
  assert policies.status_code == 200, policies.text
  policies_payload = policies.json()
  assert policies_payload["ok"] is True
  assert policies_payload["summary"]["execution_alerting_severity_rank"] == ["CRITICAL", "WARN", "INFO"]
  assert policies_payload["summary"]["ops_alert_slippage_p95_warn_bps"] == 8.0

  gates = client.get("/api/v1/gates", headers=headers)
  assert gates.status_code == 200, gates.text
  gates_payload_endpoint = gates.json()
  gate_rows = {row["id"]: row for row in gates_payload_endpoint.get("gates") or []}
  assert gate_rows["G9_RUNTIME_ENGINE_REAL"]["status"] in {"WARN", "FAIL"}

  live_safety = client.get("/api/v1/execution/live-safety/summary", headers=headers)
  assert live_safety.status_code == 200, live_safety.text
  live_safety_payload = live_safety.json()
  assert set(live_safety_payload.keys()) >= {
    "overall_status",
    "live_parity_base_ready",
    "market_stream_runtime",
    "reconciliation_engine",
    "safety_blockers",
  }
  assert live_safety_payload["live_parity_base_ready"] is False

  reconcile = client.get("/api/v1/execution/reconcile/summary", headers=headers)
  assert reconcile.status_code == 200, reconcile.text
  reconcile_payload = reconcile.json()
  assert set(reconcile_payload.keys()) >= {"ack_missing", "unresolved_count", "reconciliation_run", "policy_source"}

  market_streams = client.get("/api/v1/execution/market-streams/summary", headers=headers)
  assert market_streams.status_code == 200, market_streams.text
  market_streams_payload = market_streams.json()
  assert set(market_streams_payload.keys()) >= {"live_blocked", "live_degraded", "running_sessions", "runtime_guardrails"}

  readiness = client.get("/api/v1/validation/readiness", headers=headers)
  assert readiness.status_code == 200, readiness.text
  readiness_payload = readiness.json()
  readiness_by_stage = readiness_payload.get("readiness_by_stage") or {}
  assert {"paper", "testnet", "canary", "live_serio"} <= set(readiness_by_stage)
  assert readiness_payload["live_serio_ready"] is False


def test_live_backend_qa_policy_contracts_bundle_and_endpoint_shapes(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  policies = client.get("/api/v1/config/policies", headers=headers)
  assert policies.status_code == 200, policies.text
  policies_payload = policies.json()
  summary = policies_payload["summary"]
  assert summary["execution_alerting_severity_rank"] == ["CRITICAL", "WARN", "INFO"]
  assert summary["execution_alerting_severity_source_precedence"] == ["SAFETY", "HEALTH", "RAW"]
  assert summary["ops_alert_drift_enabled"] is True
  assert summary["ops_alert_api_errors_warn"] == 1
  assert policies_payload["authority"]["canonical_role"] == "monorepo_root"

  rollout = client.get("/api/v1/rollout/status", headers=headers)
  assert rollout.status_code == 200, rollout.text
  rollout_payload = rollout.json()
  assert isinstance(rollout_payload.get("phase_evaluations"), dict)
  assert isinstance(rollout_payload.get("live_signal_telemetry"), dict)
  assert isinstance(rollout_payload.get("routing"), dict)
  assert "readiness_by_stage" not in rollout_payload

  readiness = client.get("/api/v1/validation/readiness", headers=headers)
  assert readiness.status_code == 200, readiness.text
  readiness_payload = readiness.json()
  assert {"readiness_by_stage", "live_serio_ready", "policy_source", "policy_hash"} <= set(readiness_payload)
  assert {"paper", "testnet", "canary", "live_serio"} <= set(readiness_payload["readiness_by_stage"])

  live_safety = client.get("/api/v1/execution/live-safety/summary", headers=headers)
  assert live_safety.status_code == 200, live_safety.text
  live_safety_payload = live_safety.json()
  assert isinstance(live_safety_payload.get("market_stream_runtime"), dict)
  assert isinstance(live_safety_payload.get("reconciliation_engine"), dict)

  reconcile = client.get("/api/v1/execution/reconcile/summary", headers=headers)
  assert reconcile.status_code == 200, reconcile.text
  assert reconcile.json()["policy_source"]["execution_safety"]["source_hash"]


def test_live_backend_qa_compat_runtime_ready_surfaces_stay_coherent(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  _enable_binance_testnet_env(monkeypatch)
  _mock_exchange_ok(module, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  _set_primary_strategy_live(client, headers)

  _force_runtime_contract_live_ready(module)
  monkeypatch.setattr(module.runtime_bridge, "sync_runtime_state", lambda state, settings, event=None: False)

  runtime_state = module.store.load_bot_state()
  gates_payload = module.evaluate_gates("live", force_exchange_check=True, runtime_state=runtime_state)
  g9 = {row["id"]: row for row in gates_payload["gates"]}["G9_RUNTIME_ENGINE_REAL"]
  assert g9["status"] == "PASS"

  rollout = client.get("/api/v1/rollout/status", headers=headers)
  assert rollout.status_code == 200, rollout.text
  rollout_payload = rollout.json()
  assert isinstance(rollout_payload.get("phase_evaluations"), dict)
  assert isinstance(rollout_payload.get("live_signal_telemetry"), dict)
  assert "readiness_by_stage" not in rollout_payload

  readiness = client.get("/api/v1/validation/readiness", headers=headers)
  assert readiness.status_code == 200, readiness.text
  readiness_payload = readiness.json()
  readiness_by_stage = readiness_payload.get("readiness_by_stage") or {}
  assert {"paper", "testnet", "canary", "live_serio"} <= set(readiness_by_stage)
  assert isinstance(readiness_by_stage["live_serio"].get("blocking_reasons"), list)
  assert readiness_payload["live_serio_ready"] is False

  market_streams = client.get("/api/v1/execution/market-streams/summary", headers=headers)
  assert market_streams.status_code == 200, market_streams.text
  assert isinstance((market_streams.json().get("runtime_guardrails") or {}), dict)

  live_safety = client.get("/api/v1/execution/live-safety/summary", headers=headers)
  assert live_safety.status_code == 200, live_safety.text
  assert isinstance((live_safety.json().get("market_stream_runtime") or {}), dict)

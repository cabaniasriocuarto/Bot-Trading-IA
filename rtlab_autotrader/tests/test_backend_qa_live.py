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

  health = client.get("/api/v1/execution/health/summary", headers=headers)
  assert health.status_code == 200, health.text
  health_payload = health.json()
  assert set(health_payload.keys()) >= {"state", "reason_codes", "component_status", "scope_status"}

  alerts = client.get("/api/v1/execution/alerts/open", headers=headers)
  assert alerts.status_code == 200, alerts.text
  assert isinstance(alerts.json().get("items"), list)

  canary = client.get("/api/v1/execution/canary/status", headers=headers)
  assert canary.status_code == 200, canary.text
  canary_payload = canary.json()
  assert set(canary_payload.keys()) >= {"scope", "policy", "current_evaluation", "history"}

  shadow = client.get("/api/v1/rollout/shadow/status", headers=headers)
  assert shadow.status_code == 200, shadow.text
  shadow_payload = shadow.json()
  assert shadow_payload["active"] is False
  assert shadow_payload["operational"] is False
  assert "rollout_not_in_live_shadow" in set(shadow_payload.get("reasons") or [])

  rollout = client.get("/api/v1/rollout/status", headers=headers)
  assert rollout.status_code == 200, rollout.text
  readiness = (rollout.json().get("readiness_by_stage") or {}).get("items") or []
  readiness_by_stage = {str(row.get("stage") or ""): row for row in readiness}
  assert {"PAPER", "TESTNET", "CANARY", "LIVE_SERIO"} <= set(readiness_by_stage)
  assert readiness_by_stage["LIVE_SERIO"]["ready_bool"] is False


def test_live_backend_qa_policy_contracts_bundle_and_endpoint_shapes(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  policies = client.get("/api/v1/config/policies", headers=headers)
  assert policies.status_code == 200, policies.text
  policies_payload = policies.json()
  assert policies_payload["summary"]["execution_alerting_severity_rank"] == ["CRITICAL", "WARN", "INFO"]
  assert policies_payload["summary"]["execution_alerting_severity_source_precedence"] == ["SAFETY", "HEALTH", "RAW"]
  assert policies_payload["authority"]["canonical_role"] == "monorepo_root"

  health = client.get("/api/v1/execution/health/summary", headers=headers)
  assert health.status_code == 200, health.text
  health_payload = health.json()
  assert isinstance(health_payload.get("component_status"), dict)
  assert isinstance(health_payload.get("scope_status"), list)

  alerts_catalog = client.get("/api/v1/execution/alerts/catalog", headers=headers)
  assert alerts_catalog.status_code == 200, alerts_catalog.text
  assert isinstance(alerts_catalog.json().get("items"), list)

  alerts_history = client.get("/api/v1/execution/alerts/history", headers=headers)
  assert alerts_history.status_code == 200, alerts_history.text
  alerts_history_payload = alerts_history.json()
  assert isinstance(alerts_history_payload.get("items"), list)
  assert isinstance(alerts_history_payload.get("events"), list)


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
  readiness = (rollout.json().get("readiness_by_stage") or {}).get("items") or []
  readiness_by_stage = {str(row.get("stage") or ""): row for row in readiness}
  assert {"PAPER", "TESTNET", "CANARY", "LIVE_SERIO"} <= set(readiness_by_stage)
  assert isinstance(readiness_by_stage["LIVE_SERIO"].get("reasons"), list)

  canary = client.get("/api/v1/execution/canary/status", headers=headers)
  assert canary.status_code == 200, canary.text
  assert isinstance((canary.json().get("current_evaluation") or {}).get("blocking_sources"), list)

  shadow = client.get("/api/v1/rollout/shadow/status", headers=headers)
  assert shadow.status_code == 200, shadow.text
  shadow_payload = shadow.json()
  assert shadow_payload["runtime_contract"]["ready_for_live"] is True
  assert shadow_payload["telemetry_guard"]["ok"] is True

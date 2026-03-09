from __future__ import annotations

import importlib
import io
import json
import time
import zipfile
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient


CONFIG_YAML = """
mode: paper
universe:
  exchange: binance
  market_type: spot
  whitelist: ["BTC/USDT", "ETH/USDT"]
  min_volume_24h_usd: 1000000
  max_spread_bps: 12
  max_pairs: 20
timeframes:
  regime: "1h"
  signal: "15m"
  trigger: "5m"
  execution: "1m"
strategy:
  name: "MicrostructureTrendPullbackStrategy"
  params: {}
microstructure:
  enable_vpin: true
  enable_obi: true
  enable_cvd: true
  orderflow_gating_enabled: true
exits:
  stop_atr_mult: 1.8
  tp_atr_mult: 2.7
  trail_trigger_atr: 1.3
  trail_atr_mult: 1.1
  time_stop_bars: 30
risk:
  starting_equity: 10000
  risk_per_trade: 0.005
  daily_loss_limit_pct: 0.05
  max_drawdown_pct: 0.22
  max_positions: 20
  max_total_exposure_pct: 1.0
  max_asset_exposure_pct: 0.2
  confidence_multiplier_enabled: true
correlation:
  enabled: true
  lookback: 250
  cluster_threshold: 0.7
  max_positions_per_cluster: 4
  btc_beta_limit: 1.2
execution:
  post_only: true
  order_timeout_sec: 45
  max_requotes: 2
  maker_fee_bps: 2.0
  taker_fee_bps: 5.5
  slippage_base_bps: 3.0
  slippage_vol_k: 0.8
  funding_proxy_bps: 1.0
  spread_proxy_bps: 4.0
safety:
  safe_mode_enabled: true
  safe_factor: 0.5
  safe_max_positions: 5
  safe_vpin_max_percentile: 70.0
  safe_adx_min: 20.0
  safe_spread_max_bps: 8.0
  kill_on_max_dd: true
  kill_on_critical_errors: 5
notifications:
  telegram_enabled: false
  bot_token: ""
  chat_id: ""
backtest:
  realism_gate: true
  stress_fees_mult: 2.0
  stress_slippage_mult: 2.0
  stress_param_variation_pct: 0.15
  min_oos_segments: 2
  reports_dir: "user_data/logs/reports"
""".strip()


def _build_app(tmp_path: Path, monkeypatch, mode: str = "paper", seed_settings: dict | None = None):
  data_dir = tmp_path / "user_data"
  config_path = tmp_path / "rtlab_config.yaml"
  config_path.write_text(CONFIG_YAML, encoding="utf-8")
  if seed_settings is not None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "console_settings.json").write_text(json.dumps(seed_settings), encoding="utf-8")

  monkeypatch.setenv("RTLAB_USER_DATA_DIR", str(data_dir))
  monkeypatch.setenv("RTLAB_CONFIG_PATH", str(config_path))
  monkeypatch.setenv("AUTH_SECRET", "x" * 40)
  monkeypatch.setenv("ADMIN_USERNAME", "Wadmin")
  monkeypatch.setenv("ADMIN_PASSWORD", "moroco123")
  monkeypatch.setenv("VIEWER_USERNAME", "viewer")
  monkeypatch.setenv("VIEWER_PASSWORD", "viewer123")
  monkeypatch.setenv("MODE", mode)
  monkeypatch.setenv("EXCHANGE_NAME", "binance")
  monkeypatch.setenv("TELEGRAM_ENABLED", "false")
  monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
  monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)
  monkeypatch.delenv("BINANCE_SPOT_TESTNET_BASE_URL", raising=False)
  monkeypatch.delenv("BINANCE_SPOT_TESTNET_WS_URL", raising=False)
  monkeypatch.delenv("BINANCE_API_KEY", raising=False)
  monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
  monkeypatch.delenv("API_KEY", raising=False)
  monkeypatch.delenv("API_SECRET", raising=False)
  monkeypatch.delenv("TESTNET_API_KEY", raising=False)
  monkeypatch.delenv("TESTNET_API_SECRET", raising=False)

  module = importlib.import_module("rtlab_core.web.app")
  module = importlib.reload(module)
  return module, TestClient(module.app)


def _auth_headers(token: str) -> dict[str, str]:
  return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, username: str, password: str) -> str:
  res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
  assert res.status_code == 200, res.text
  token = res.json()["token"]
  assert isinstance(token, str) and token
  return token


def _make_zip(files: dict[str, str]) -> bytes:
  buffer = io.BytesIO()
  with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name, content in files.items():
      archive.writestr(name, content)
  return buffer.getvalue()


def test_auth_and_admin_protection(tmp_path: Path, monkeypatch) -> None:
  _, client = _build_app(tmp_path, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  viewer_token = _login(client, "viewer", "viewer123")

  me_admin = client.get("/api/v1/me", headers=_auth_headers(admin_token))
  assert me_admin.status_code == 200
  assert me_admin.json()["role"] == "admin"

  me_viewer = client.get("/api/v1/me", headers=_auth_headers(viewer_token))
  assert me_viewer.status_code == 200
  assert me_viewer.json()["role"] == "viewer"

  forbidden = client.post("/api/v1/bot/stop", headers=_auth_headers(viewer_token))
  assert forbidden.status_code == 403

  unauthorized = client.get("/api/v1/strategies")
  assert unauthorized.status_code == 401


def test_gates_requires_auth(tmp_path: Path, monkeypatch) -> None:
  _, client = _build_app(tmp_path, monkeypatch)
  unauthorized = client.get("/api/v1/gates")
  assert unauthorized.status_code == 401

  admin_token = _login(client, "Wadmin", "moroco123")
  authorized = client.get("/api/v1/gates", headers=_auth_headers(admin_token))
  assert authorized.status_code == 200


def test_internal_headers_require_proxy_token(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  spoof_headers = {"x-rtlab-role": "admin", "x-rtlab-user": "spoof"}

  blocked_no_token = client.get("/api/v1/me", headers=spoof_headers)
  assert blocked_no_token.status_code == 401

  monkeypatch.setenv("INTERNAL_PROXY_TOKEN", "proxy-secret-123")
  blocked_wrong_token = client.get(
    "/api/v1/me",
    headers={**spoof_headers, "x-rtlab-proxy-token": "wrong-token"},
  )
  assert blocked_wrong_token.status_code == 401

  allowed = client.get(
    "/api/v1/me",
    headers={**spoof_headers, "x-rtlab-proxy-token": "proxy-secret-123"},
  )
  assert allowed.status_code == 200
  assert allowed.json()["role"] == "admin"

  logs_payload = module.store.list_logs(severity="warn", module="auth", since=None, until=None, page=1, page_size=200)
  items = logs_payload.get("items") or []
  security_logs = [row for row in items if str(row.get("type") or "") == "security_auth"]
  assert security_logs
  reasons = {str((row.get("payload") or {}).get("reason") or "") for row in security_logs}
  assert "missing_proxy_token" in reasons
  assert "invalid_proxy_token" in reasons


def test_internal_proxy_allows_previous_token_with_future_expiry(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  monkeypatch.setenv("INTERNAL_PROXY_TOKEN", "proxy-new")
  monkeypatch.setenv("INTERNAL_PROXY_TOKEN_PREVIOUS", "proxy-old")
  future_expiry = (module.utc_now() + module.timedelta(minutes=30)).isoformat()
  monkeypatch.setenv("INTERNAL_PROXY_TOKEN_PREVIOUS_EXPIRES_AT", future_expiry)

  headers = {
    "x-rtlab-role": "admin",
    "x-rtlab-user": "spoof",
    "x-rtlab-proxy-token": "proxy-old",
  }
  allowed = client.get("/api/v1/me", headers=headers)
  assert allowed.status_code == 200, allowed.text
  assert allowed.json()["role"] == "admin"

  status = client.get("/api/v1/auth/internal-proxy/status", headers=headers)
  assert status.status_code == 200, status.text
  payload = status.json()
  assert payload["ok"] is True
  assert payload["active_token_configured"] is True
  assert payload["previous_token_configured"] is True
  assert payload["previous_token_enabled"] is True
  assert payload["rotation_ready"] is True
  assert isinstance(payload.get("previous_token_seconds_remaining"), int)
  assert payload["previous_token_seconds_remaining"] > 0


def test_internal_proxy_rejects_previous_token_when_expired(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  monkeypatch.setenv("INTERNAL_PROXY_TOKEN", "proxy-new")
  monkeypatch.setenv("INTERNAL_PROXY_TOKEN_PREVIOUS", "proxy-old")
  expired_at = (module.utc_now() - module.timedelta(minutes=2)).isoformat()
  monkeypatch.setenv("INTERNAL_PROXY_TOKEN_PREVIOUS_EXPIRES_AT", expired_at)

  headers = {
    "x-rtlab-role": "admin",
    "x-rtlab-user": "spoof",
    "x-rtlab-proxy-token": "proxy-old",
  }
  blocked = client.get("/api/v1/me", headers=headers)
  assert blocked.status_code == 401

  status_headers = {
    "x-rtlab-role": "admin",
    "x-rtlab-user": "spoof",
    "x-rtlab-proxy-token": "proxy-new",
  }
  status = client.get("/api/v1/auth/internal-proxy/status", headers=status_headers)
  assert status.status_code == 200, status.text
  payload = status.json()
  assert payload["previous_token_configured"] is True
  assert payload["previous_token_enabled"] is False
  assert payload["rotation_ready"] is False
  warnings = payload.get("warnings") or []
  assert any("expirado" in str(msg).lower() for msg in warnings)

  logs_payload = module.store.list_logs(severity="warn", module="auth", since=None, until=None, page=1, page_size=200)
  items = logs_payload.get("items") or []
  security_logs = [row for row in items if str(row.get("type") or "") == "security_auth"]
  assert any(str((row.get("payload") or {}).get("reason") or "") == "expired_previous_token" for row in security_logs)


def test_auth_login_rate_limit_and_lock_guard(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  module.LOGIN_RATE_LIMITER = module.LoginRateLimiter(
    attempts_per_window=10,
    window_minutes=10,
    lockout_minutes=30,
    lockout_after_failures=20,
    backend="memory",
  )

  for _ in range(10):
    res = client.post("/api/v1/auth/login", json={"username": "Wadmin", "password": "invalid"})
    assert res.status_code == 401

  limited = client.post("/api/v1/auth/login", json={"username": "Wadmin", "password": "invalid"})
  assert limited.status_code == 429
  assert "Demasiados intentos" in str(limited.json().get("detail") or "")


def test_auth_login_rate_limit_shared_sqlite_backend_across_instances(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch)
  sqlite_path = tmp_path / "shared_login_limiter.sqlite3"
  limiter_a = module.LoginRateLimiter(
    attempts_per_window=2,
    window_minutes=10,
    lockout_minutes=30,
    lockout_after_failures=3,
    backend="sqlite",
    sqlite_path=sqlite_path,
  )
  limiter_b = module.LoginRateLimiter(
    attempts_per_window=2,
    window_minutes=10,
    lockout_minutes=30,
    lockout_after_failures=3,
    backend="sqlite",
    sqlite_path=sqlite_path,
  )

  key = "127.0.0.1:wadmin"
  limiter_a.register_failure(key)
  limiter_a.register_failure(key)
  allowed, retry_after_sec, reason = limiter_b.check(key)
  assert allowed is False
  assert retry_after_sec > 0
  assert reason == "rate_limit"

  limiter_b.register_failure(key)
  lock_allowed, lock_retry_after_sec, lock_reason = limiter_a.check(key)
  assert lock_allowed is False
  assert lock_retry_after_sec > 0
  assert lock_reason == "lockout"

  limiter_a.register_success(key)
  reset_allowed, reset_retry_after_sec, reset_reason = limiter_b.check(key)
  assert reset_allowed is True
  assert reset_retry_after_sec == 0
  assert reset_reason == ""


def test_api_general_rate_limit_guard(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  module.API_RATE_LIMITER = module.ApiRateLimiter(
    enabled=True,
    general_per_minute=2,
    expensive_per_minute=10,
    window_seconds=60,
  )
  token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(token)

  assert client.get("/api/v1/me", headers=headers).status_code == 200
  assert client.get("/api/v1/me", headers=headers).status_code == 200
  limited = client.get("/api/v1/me", headers=headers)
  assert limited.status_code == 429
  assert limited.headers.get("X-RTLAB-RateLimit-Bucket") == "general"
  assert "rate limit general" in str(limited.json().get("detail") or "").lower()


def test_api_expensive_rate_limit_guard(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  module.API_RATE_LIMITER = module.ApiRateLimiter(
    enabled=True,
    general_per_minute=100,
    expensive_per_minute=1,
    window_seconds=60,
  )
  token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(token)

  strategies = client.get("/api/v1/strategies", headers=headers).json()
  pool_ids = [row["id"] for row in strategies if row.get("id")]
  payload = {
    "name": "rate-limit-expensive-1",
    "engine": "bandit_thompson",
    "mode": "paper",
    "status": "active",
    "pool_strategy_ids": pool_ids[:1],
    "universe": ["BTCUSDT"],
    "notes": "rate limit test",
  }

  first = client.post("/api/v1/bots", headers=headers, json=payload)
  assert first.status_code == 200, first.text
  payload["name"] = "rate-limit-expensive-2"
  limited = client.post("/api/v1/bots", headers=headers, json=payload)
  assert limited.status_code == 429
  assert limited.headers.get("X-RTLAB-RateLimit-Bucket") == "expensive"
  assert "endpoint costoso" in str(limited.json().get("detail") or "").lower()


def test_api_bots_overview_uses_general_bucket(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  module.API_RATE_LIMITER = module.ApiRateLimiter(
    enabled=True,
    general_per_minute=1,
    expensive_per_minute=1,
    window_seconds=60,
  )
  token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(token)

  first = client.get("/api/v1/bots", headers=headers)
  assert first.status_code == 200, first.text
  limited = client.get("/api/v1/bots", headers=headers)
  assert limited.status_code == 429
  assert limited.headers.get("X-RTLAB-RateLimit-Bucket") == "general"
  assert "rate limit general" in str(limited.json().get("detail") or "").lower()


def test_api_research_readonly_endpoints_use_general_bucket(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  module.API_RATE_LIMITER = module.ApiRateLimiter(
    enabled=True,
    general_per_minute=1,
    expensive_per_minute=1,
    window_seconds=60,
  )
  token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(token)

  first = client.get("/api/v1/research/beast/status", headers=headers)
  assert first.status_code == 200, first.text
  limited = client.get("/api/v1/research/beast/status", headers=headers)
  assert limited.status_code == 429
  assert limited.headers.get("X-RTLAB-RateLimit-Bucket") == "general"
  assert "rate limit general" in str(limited.json().get("detail") or "").lower()


def test_auth_validation_fails_in_production_with_default_credentials(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch)
  monkeypatch.setenv("NODE_ENV", "production")
  monkeypatch.setenv("AUTH_SECRET", "x" * 40)
  monkeypatch.setenv("ADMIN_USERNAME", "admin")
  monkeypatch.setenv("ADMIN_PASSWORD", "admin123!")
  monkeypatch.setenv("VIEWER_USERNAME", "viewer")
  monkeypatch.setenv("VIEWER_PASSWORD", "viewer123!")

  with pytest.raises(RuntimeError, match="credenciales por defecto"):
    module._validate_auth_config_for_production()


def test_default_principal_bootstrap_and_start(tmp_path: Path, monkeypatch) -> None:
  _, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  strategies_res = client.get("/api/v1/strategies", headers=headers)
  assert strategies_res.status_code == 200
  strategies = strategies_res.json()
  default_row = next(row for row in strategies if row["id"] == "trend_pullback_orderflow_confirm_v1")
  assert default_row["enabled"] is True
  assert set(default_row["primary_for_modes"]) >= {"paper", "testnet"}

  start_res = client.post("/api/v1/bot/start", headers=headers)
  assert start_res.status_code == 200, start_res.text
  assert start_res.json()["state"] == "RUNNING"

  trades_res = client.get("/api/v1/trades", headers=headers)
  assert trades_res.status_code == 200
  trades = trades_res.json()
  assert trades
  trade_detail = client.get(f"/api/v1/trades/{trades[0]['id']}", headers=headers)
  assert trade_detail.status_code == 200
  assert trade_detail.json()["id"] == trades[0]["id"]


def test_trades_summary_with_environment_filter(tmp_path: Path, monkeypatch) -> None:
  _, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  start_res = client.post("/api/v1/bot/start", headers=headers)
  assert start_res.status_code == 200, start_res.text

  summary = client.get("/api/v1/trades/summary", headers=headers)
  assert summary.status_code == 200, summary.text
  payload = summary.json()
  assert "totals" in payload
  assert "by_environment" in payload
  assert "by_strategy" in payload
  assert payload["totals"]["trades"] >= 1

  only_test = client.get("/api/v1/trades/summary?environment=prueba", headers=headers)
  assert only_test.status_code == 200, only_test.text
  test_payload = only_test.json()
  assert test_payload["totals"]["trades"] >= 1

  only_real = client.get("/api/v1/trades/summary?environment=real", headers=headers)
  assert only_real.status_code == 200, only_real.text
  real_payload = only_real.json()
  assert real_payload["totals"]["trades"] <= payload["totals"]["trades"]


def test_live_blocked_by_gates_when_requirements_fail(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  gates_live = module.evaluate_gates("live")
  gate_by_id = {row["id"]: row for row in gates_live["gates"]}
  assert gate_by_id["G4_EXCHANGE_CONNECTOR_READY"]["status"] == "FAIL"
  assert gate_by_id["G7_ORDER_SIM_OR_PAPER_OK"]["status"] == "FAIL"

  enable_live = client.post("/api/v1/bot/mode", json={"mode": "live", "confirm": "ENABLE_LIVE"}, headers=headers)
  assert enable_live.status_code == 400
  detail = str(enable_live.json().get("detail") or "").lower()
  assert "live bloqueado" in detail or "live blocked by gates" in detail


def test_live_mode_blocked_when_runtime_engine_is_simulated(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  strategies = client.get("/api/v1/strategies", headers=headers)
  assert strategies.status_code == 200, strategies.text
  strategy_id = strategies.json()[0]["id"]
  set_live_primary = client.post(f"/api/v1/strategies/{strategy_id}/primary", headers=headers, json={"mode": "live"})
  assert set_live_primary.status_code == 200, set_live_primary.text

  state = module.store.load_bot_state()
  state["runtime_engine"] = "simulated"
  module.store.save_bot_state(state)

  gates_live = module.evaluate_gates("live", force_exchange_check=True)
  gate_by_id = {row["id"]: row for row in gates_live["gates"]}
  assert gate_by_id["G9_RUNTIME_ENGINE_REAL"]["status"] == "FAIL"

  enable_live = client.post("/api/v1/bot/mode", json={"mode": "live", "confirm": "ENABLE_LIVE"}, headers=headers)
  assert enable_live.status_code == 400
  assert "runtime simulado" in str(enable_live.json().get("detail") or "").lower()


def test_runtime_sync_testnet_mirrors_open_orders_without_synthetic_fill_progression(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    if path == "/api/v3/openOrders":
      return True, {
        "status_code": 200,
        "payload": [
          {
            "clientOrderId": "oid-rt-sync-1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "origQty": "2.0",
            "executedQty": "0.5",
          }
        ],
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["running"] = True
  state["killed"] = False
  state["runtime_engine"] = "real"

  synced_1 = module._sync_runtime_state(state, persist=False)
  order_1 = module.runtime_bridge._oms.orders.get("oid-rt-sync-1")
  assert order_1 is not None
  assert float(order_1.qty) == pytest.approx(2.0)
  assert float(order_1.filled_qty) == pytest.approx(0.5)
  assert synced_1["runtime_telemetry_source"] == module.RUNTIME_TELEMETRY_SOURCE_REAL
  assert bool(synced_1.get("runtime_reconciliation_ok")) is True

  synced_2 = module._sync_runtime_state(synced_1, persist=False)
  order_2 = module.runtime_bridge._oms.orders.get("oid-rt-sync-1")
  assert order_2 is not None
  # En testnet/live no debe avanzar fills por simulacion local.
  assert float(order_2.filled_qty) == pytest.approx(0.5)
  assert synced_2["runtime_telemetry_source"] == module.RUNTIME_TELEMETRY_SOURCE_REAL
  assert bool(synced_2.get("runtime_reconciliation_ok")) is True


def test_runtime_sync_testnet_ignores_filled_local_orders_in_open_orders_reconciliation(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-filled-local-1", symbol="BTCUSDT", side=module.Side.LONG, qty=1.0)
  )
  module.runtime_bridge._oms.apply_fill("oid-filled-local-1", 1.0)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert bool(synced.get("runtime_reconciliation_ok")) is True
  assert synced["runtime_telemetry_source"] == module.RUNTIME_TELEMETRY_SOURCE_REAL
  reconcile = module.runtime_bridge._last_reconcile
  assert list(reconcile.get("missing_exchange") or []) == []


def test_runtime_sync_testnet_keeps_absent_local_open_order_when_order_status_fetch_fails(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  old_order = module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-open-stale-1", symbol="BTCUSDT", side=module.Side.LONG, qty=1.0)
  )
  old_order.updated_at = old_order.updated_at - timedelta(seconds=10)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert bool(synced.get("runtime_reconciliation_ok")) is False
  closed = module.runtime_bridge._oms.orders.get("oid-open-stale-1")
  assert closed is not None
  assert closed.status in {module.OrderStatus.SUBMITTED, module.OrderStatus.PARTIALLY_FILLED}


def test_runtime_sync_testnet_marks_absent_open_order_filled_from_order_status(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"order_status_get": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "GET":
      calls["order_status_get"] += 1
      return True, {
        "status_code": 200,
        "payload": {
          "symbol": "BTCUSDT",
          "status": "FILLED",
          "origQty": "1.0",
          "executedQty": "1.0",
          "clientOrderId": "oid-open-status-filled-1",
          "orderId": 123456,
          "side": "BUY",
        },
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  old_order = module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-open-status-filled-1", symbol="BTCUSDT", side=module.Side.LONG, qty=1.0)
  )
  old_order.updated_at = old_order.updated_at - timedelta(seconds=10)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_status_get"] >= 1
  assert bool(synced.get("runtime_reconciliation_ok")) is True
  closed = module.runtime_bridge._oms.orders.get("oid-open-status-filled-1")
  assert closed is not None
  assert closed.status == module.OrderStatus.FILLED
  assert float(closed.filled_qty) == 1.0


def test_runtime_sync_testnet_keeps_absent_open_order_open_when_order_status_is_new(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"order_status_get": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "GET":
      calls["order_status_get"] += 1
      return True, {
        "status_code": 200,
        "payload": {
          "symbol": "BTCUSDT",
          "status": "NEW",
          "origQty": "1.0",
          "executedQty": "0.0",
          "clientOrderId": "oid-open-status-new-1",
          "orderId": 334455,
          "side": "BUY",
        },
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  old_order = module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-open-status-new-1", symbol="BTCUSDT", side=module.Side.LONG, qty=1.0)
  )
  old_order.updated_at = old_order.updated_at - timedelta(seconds=10)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_status_get"] >= 1
  assert bool(synced.get("runtime_reconciliation_ok")) is True
  still_open = module.runtime_bridge._oms.orders.get("oid-open-status-new-1")
  assert still_open is not None
  assert still_open.status == module.OrderStatus.SUBMITTED
  assert float(still_open.filled_qty) == 0.0


def test_runtime_sync_testnet_keeps_partial_state_when_order_status_is_pending_cancel(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"order_status_get": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "GET":
      calls["order_status_get"] += 1
      return True, {
        "status_code": 200,
        "payload": {
          "symbol": "BTCUSDT",
          "status": "PENDING_CANCEL",
          "origQty": "1.0",
          "executedQty": "0.4",
          "clientOrderId": "oid-open-status-pending-cancel-1",
          "orderId": 445566,
          "side": "BUY",
        },
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  old_order = module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-open-status-pending-cancel-1", symbol="BTCUSDT", side=module.Side.LONG, qty=1.0)
  )
  old_order.updated_at = old_order.updated_at - timedelta(seconds=10)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_status_get"] >= 1
  assert bool(synced.get("runtime_reconciliation_ok")) is True
  pending_cancel = module.runtime_bridge._oms.orders.get("oid-open-status-pending-cancel-1")
  assert pending_cancel is not None
  assert pending_cancel.status == module.OrderStatus.PARTIALLY_FILLED
  assert float(pending_cancel.filled_qty) == 0.4


def test_runtime_sync_testnet_updates_absent_open_order_partial_fill_from_order_status(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"order_status_get": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "GET":
      calls["order_status_get"] += 1
      return True, {
        "status_code": 200,
        "payload": {
          "symbol": "BTCUSDT",
          "status": "PARTIALLY_FILLED",
          "origQty": "1.0",
          "executedQty": "0.4",
          "clientOrderId": "oid-open-status-partial-1",
          "orderId": 556677,
          "side": "BUY",
        },
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  old_order = module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-open-status-partial-1", symbol="BTCUSDT", side=module.Side.LONG, qty=1.0)
  )
  old_order.updated_at = old_order.updated_at - timedelta(seconds=10)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_status_get"] >= 1
  assert bool(synced.get("runtime_reconciliation_ok")) is True
  partial = module.runtime_bridge._oms.orders.get("oid-open-status-partial-1")
  assert partial is not None
  assert partial.status == module.OrderStatus.PARTIALLY_FILLED
  assert float(partial.filled_qty) == 0.4


def test_runtime_sync_testnet_marks_absent_open_order_expired_in_match_terminal(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"order_status_get": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "GET":
      calls["order_status_get"] += 1
      return True, {
        "status_code": 200,
        "payload": {
          "symbol": "BTCUSDT",
          "status": "EXPIRED_IN_MATCH",
          "origQty": "1.0",
          "executedQty": "0.4",
          "clientOrderId": "oid-open-status-expired-match-1",
          "orderId": 776655,
          "side": "BUY",
        },
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  old_order = module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-open-status-expired-match-1", symbol="BTCUSDT", side=module.Side.LONG, qty=1.0)
  )
  old_order.updated_at = old_order.updated_at - timedelta(seconds=10)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_status_get"] >= 1
  assert bool(synced.get("runtime_reconciliation_ok")) is True
  expired = module.runtime_bridge._oms.orders.get("oid-open-status-expired-match-1")
  assert expired is not None
  assert expired.status == module.OrderStatus.CANCELED
  assert float(expired.filled_qty) == 0.4


def test_runtime_sync_testnet_marks_absent_open_order_rejected_from_order_status(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"order_status_get": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "GET":
      calls["order_status_get"] += 1
      return True, {
        "status_code": 200,
        "payload": {
          "symbol": "BTCUSDT",
          "status": "REJECTED",
          "origQty": "1.0",
          "executedQty": "0.0",
          "clientOrderId": "oid-open-status-rejected-1",
          "orderId": 889900,
          "side": "BUY",
        },
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  old_order = module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-open-status-rejected-1", symbol="BTCUSDT", side=module.Side.LONG, qty=1.0)
  )
  old_order.updated_at = old_order.updated_at - timedelta(seconds=10)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_status_get"] >= 1
  assert bool(synced.get("runtime_reconciliation_ok")) is True
  rejected = module.runtime_bridge._oms.orders.get("oid-open-status-rejected-1")
  assert rejected is not None
  assert rejected.status == module.OrderStatus.REJECTED
  assert float(rejected.filled_qty) == 0.0


def test_runtime_stop_testnet_cancels_remote_open_orders_idempotently(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")

  calls = {"open_orders_get": 0, "cancel_delete": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    if path == "/api/v3/openOrders" and str(method).upper() == "GET":
      calls["open_orders_get"] += 1
      return True, {
        "status_code": 200,
        "payload": [
          {
            "clientOrderId": "oid-cancel-idem-1",
            "orderId": 112233,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "origQty": "1.0",
            "executedQty": "0.0",
          }
        ],
      }
    if path == "/api/v3/order" and str(method).upper() == "DELETE":
      calls["cancel_delete"] += 1
      return True, {"status_code": 200, "payload": {"status": "CANCELED"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = False
  state["killed"] = False

  stopped_1 = module._sync_runtime_state(state, event="stop", persist=False)
  stopped_2 = module._sync_runtime_state(stopped_1, event="stop", persist=False)

  assert calls["open_orders_get"] >= 1
  # Segundo stop inmediato no debe duplicar cancel remoto por misma client_order_id.
  assert calls["cancel_delete"] == 1
  assert stopped_2["runtime_telemetry_source"] == module.RUNTIME_TELEMETRY_SOURCE_SYNTHETIC
  assert bool(stopped_2.get("running")) is False


def test_runtime_sync_testnet_does_not_submit_remote_orders_when_feature_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"open_orders_get": 0, "account_get": 0, "order_post": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    if path == "/api/v3/openOrders" and str(method).upper() == "GET":
      calls["open_orders_get"] += 1
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/order" and str(method).upper() == "POST":
      calls["order_post"] += 1
      return True, {"status_code": 200, "payload": {"clientOrderId": "unexpected", "orderId": 1, "origQty": "0.001", "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["open_orders_get"] >= 1
  assert calls["order_post"] == 0
  assert str(synced.get("runtime_last_remote_submit_at") or "") == ""
  assert str(synced.get("runtime_last_remote_client_order_id") or "") == ""
  assert str(synced.get("runtime_last_remote_submit_error") or "") == ""


def test_runtime_sync_testnet_skips_submit_when_local_open_orders_remain_unverified(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", "1")
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  monkeypatch.setattr(
    module.runtime_bridge,
    "_runtime_order_intent",
    lambda mode: {
      "action": "trade",
      "strategy_id": "mean_reversion",
      "symbol": "BTCUSDT",
      "side": "BUY",
      "notional_usd": 25.0,
      "reason": "test_intent",
    },
  )

  calls = {"open_orders_get": 0, "account_get": 0, "order_status_get": 0, "order_post": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      calls["account_get"] += 1
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "GET":
      calls["order_status_get"] += 1
      return False, {"status_code": 502, "payload": {"msg": "upstream timeout"}}
    if path == "/api/v3/order" and method_u == "POST":
      calls["order_post"] += 1
      return True, {"status_code": 200, "payload": {"clientOrderId": "unexpected", "orderId": 1, "origQty": "0.001", "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()
  stale_local = module.runtime_bridge._oms.submit(
    module.Order(order_id="oid-open-unverified-1", symbol="BTCUSDT", side=module.Side.LONG, qty=0.001)
  )
  stale_local.updated_at = stale_local.updated_at - timedelta(seconds=10)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_status_get"] >= 1
  assert calls["order_post"] == 0
  assert str(synced.get("runtime_last_remote_submit_reason") or "") == "reconciliation_not_ok"
  assert bool(synced.get("runtime_reconciliation_ok")) is False
  kept = module.runtime_bridge._oms.orders.get("oid-open-unverified-1")
  assert kept is not None
  assert kept.status in {module.OrderStatus.SUBMITTED, module.OrderStatus.PARTIALLY_FILLED}


def test_runtime_sync_testnet_submits_remote_seed_order_once_with_idempotency(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"open_orders_get": 0, "account_get": 0, "order_post": 0}
  open_orders_payload: list[dict[str, object]] = []

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      return True, {"status_code": 200, "payload": list(open_orders_payload)}
    if path == "/api/v3/account" and method_u == "GET":
      calls["account_get"] += 1
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "POST":
      calls["order_post"] += 1
      client_order_id = str((params or {}).get("newClientOrderId") or "")
      qty = str((params or {}).get("quantity") or "0.001")
      symbol = str((params or {}).get("symbol") or "BTCUSDT")
      side = str((params or {}).get("side") or "BUY")
      assert client_order_id
      open_orders_payload[:] = [
        {
          "clientOrderId": client_order_id,
          "orderId": 998877,
          "symbol": symbol,
          "side": side,
          "origQty": qty,
          "executedQty": "0.0",
        }
      ]
      return True, {
        "status_code": 200,
        "payload": {
          "clientOrderId": client_order_id,
          "orderId": 998877,
          "origQty": qty,
          "executedQty": "0.0",
        },
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced_1 = module._sync_runtime_state(state, persist=False)
  assert calls["order_post"] == 1
  first_client_order_id = str(synced_1.get("runtime_last_remote_client_order_id") or "")
  assert first_client_order_id
  assert str(synced_1.get("runtime_last_remote_submit_at") or "")
  assert str(synced_1.get("runtime_last_remote_submit_error") or "") == ""

  synced_2 = module._sync_runtime_state(synced_1, persist=False)
  assert calls["order_post"] == 1
  assert str(synced_2.get("runtime_last_remote_client_order_id") or "") == first_client_order_id
  assert str(synced_2.get("runtime_last_remote_submit_error") or "") == ""


def test_runtime_sync_testnet_strategy_signal_flat_skips_remote_submit(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )
  monkeypatch.setattr(module.store.registry, "get_principal", lambda mode: {"name": "defensive_runtime_v2"})
  monkeypatch.setattr(
    module.store,
    "strategy_or_404",
    lambda strategy_id: {
      "id": strategy_id,
      "enabled_for_trading": True,
      "params": {"runtime_symbol": "BTCUSDT"},
      "tags": ["defensive", "liquidity"],
    },
  )

  calls = {"open_orders_get": 0, "account_get": 0, "order_post": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "POST":
      calls["order_post"] += 1
      return True, {"status_code": 200, "payload": {"clientOrderId": "unexpected", "orderId": 1, "origQty": "0.001", "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_post"] == 0
  assert str(synced.get("runtime_last_signal_action") or "") == "flat"
  assert str(synced.get("runtime_last_signal_strategy_id") or "") == "defensive_runtime_v2"
  assert str(synced.get("runtime_last_signal_reason") or "").strip() != ""


def test_runtime_sync_testnet_strategy_signal_meanreversion_submits_sell(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )
  monkeypatch.setattr(module.store.registry, "get_principal", lambda mode: {"name": "meanreversion_runtime_v2"})
  monkeypatch.setattr(
    module.store,
    "strategy_or_404",
    lambda strategy_id: {
      "id": strategy_id,
      "enabled_for_trading": True,
      "params": {"runtime_symbol": "ETHUSDT"},
      "tags": ["mean_reversion", "range"],
    },
  )

  calls = {"open_orders_get": 0, "account_get": 0, "order_post": 0}
  observed: dict[str, str] = {"side": "", "symbol": ""}
  open_orders_payload: list[dict[str, object]] = []

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      return True, {"status_code": 200, "payload": list(open_orders_payload)}
    if path == "/api/v3/account" and method_u == "GET":
      calls["account_get"] += 1
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "POST":
      calls["order_post"] += 1
      observed["side"] = str((params or {}).get("side") or "")
      observed["symbol"] = str((params or {}).get("symbol") or "")
      client_order_id = str((params or {}).get("newClientOrderId") or "")
      qty = str((params or {}).get("quantity") or "0.001")
      open_orders_payload[:] = [
        {
          "clientOrderId": client_order_id,
          "orderId": 332211,
          "symbol": observed["symbol"],
          "side": observed["side"],
          "origQty": qty,
          "executedQty": "0.0",
        }
      ]
      return True, {"status_code": 200, "payload": {"clientOrderId": client_order_id, "orderId": 332211, "origQty": qty, "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_post"] == 1
  assert calls["account_get"] == 1
  assert observed["side"] == "SELL"
  assert observed["symbol"] == "ETHUSDT"
  assert str(synced.get("runtime_last_signal_action") or "") == "trade"
  assert str(synced.get("runtime_last_signal_side") or "") == "SELL"
  assert str(synced.get("runtime_last_signal_strategy_id") or "") == "meanreversion_runtime_v2"
  assert str(synced.get("runtime_last_remote_submit_reason") or "") == "submitted"


def test_runtime_sync_testnet_skips_submit_when_risk_blocks_current_cycle(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )
  monkeypatch.setattr(module.store.registry, "get_principal", lambda mode: {"name": "meanreversion_runtime_v2"})
  monkeypatch.setattr(
    module.store,
    "strategy_or_404",
    lambda strategy_id: {
      "id": strategy_id,
      "enabled_for_trading": True,
      "params": {"runtime_symbol": "ETHUSDT"},
      "tags": ["mean_reversion", "range"],
    },
  )

  calls = {"open_orders_get": 0, "order_post": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "POST":
      calls["order_post"] += 1
      return True, {"status_code": 200, "payload": {"clientOrderId": "unexpected", "orderId": 11, "origQty": "0.001", "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False
  state["equity"] = 10_000.0
  state["daily_pnl"] = -700.0

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_post"] == 0
  assert bool(synced.get("runtime_risk_allow_new_positions")) is False


def test_runtime_sync_testnet_skips_submit_when_account_positions_fetch_fails(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )
  monkeypatch.setattr(module.store.registry, "get_principal", lambda mode: {"name": "meanreversion_runtime_v2"})
  monkeypatch.setattr(
    module.store,
    "strategy_or_404",
    lambda strategy_id: {
      "id": strategy_id,
      "enabled_for_trading": True,
      "params": {"runtime_symbol": "ETHUSDT"},
      "tags": ["mean_reversion", "range"],
    },
  )

  calls = {"open_orders_get": 0, "account_get": 0, "order_post": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      calls["account_get"] += 1
      return False, {"status_code": 503, "payload": {"msg": "account unavailable"}}
    if path == "/api/v3/order" and method_u == "POST":
      calls["order_post"] += 1
      return True, {"status_code": 200, "payload": {"clientOrderId": "unexpected", "orderId": 777, "origQty": "0.001", "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["account_get"] >= 1
  assert calls["order_post"] == 0
  assert str(synced.get("runtime_last_remote_submit_reason") or "") == "account_positions_fetch_failed"
  assert str(synced.get("runtime_last_remote_submit_error") or "").strip() != ""


def test_runtime_sync_testnet_skips_submit_when_reconciliation_not_ok(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )
  monkeypatch.setattr(module.store.registry, "get_principal", lambda mode: {"name": "meanreversion_runtime_v2"})
  monkeypatch.setattr(
    module.store,
    "strategy_or_404",
    lambda strategy_id: {
      "id": strategy_id,
      "enabled_for_trading": True,
      "params": {"runtime_symbol": "ETHUSDT"},
      "tags": ["mean_reversion", "range"],
    },
  )

  calls = {"open_orders_get": 0, "account_get": 0, "order_post": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      return False, {"status_code": 503, "payload": {"msg": "open orders unavailable"}}
    if path == "/api/v3/account" and method_u == "GET":
      calls["account_get"] += 1
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "POST":
      calls["order_post"] += 1
      return True, {"status_code": 200, "payload": {"clientOrderId": "unexpected", "orderId": 888, "origQty": "0.001", "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["open_orders_get"] >= 1
  assert calls["order_post"] == 0
  assert bool(synced.get("runtime_reconciliation_ok")) is False
  assert str(synced.get("runtime_last_remote_submit_reason") or "") == "reconciliation_not_ok"


def test_runtime_sync_live_skips_submit_when_live_trading_disabled(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  monkeypatch.setenv("LIVE_TRADING_ENABLED", "0")
  module, _client = _build_app(tmp_path, monkeypatch, mode="live")
  monkeypatch.setenv("BINANCE_API_KEY", "live-key")
  monkeypatch.setenv("BINANCE_API_SECRET", "live-secret")
  monkeypatch.setenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com")
  monkeypatch.setenv("BINANCE_SPOT_WS_URL", "wss://stream.binance.com:9443/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )
  monkeypatch.setattr(module.store.registry, "get_principal", lambda mode: {"name": "meanreversion_runtime_v2"})
  monkeypatch.setattr(
    module.store,
    "strategy_or_404",
    lambda strategy_id: {
      "id": strategy_id,
      "enabled_for_trading": True,
      "params": {"runtime_symbol": "BTCUSDT"},
      "tags": ["mean_reversion", "range"],
    },
  )

  calls = {"open_orders_get": 0, "account_get": 0, "order_post": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      calls["account_get"] += 1
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "POST":
      calls["order_post"] += 1
      return True, {"status_code": 200, "payload": {"clientOrderId": "unexpected-live", "orderId": 1, "origQty": "0.001", "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "live"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert calls["order_post"] == 0
  assert str(synced.get("runtime_last_signal_action") or "") == "trade"
  assert str(synced.get("runtime_last_remote_submit_reason") or "") == "live_trading_disabled"
  assert str(synced.get("runtime_last_remote_submit_error") or "") == "LIVE_TRADING_ENABLED=false"


def test_runtime_sync_clears_submit_reason_when_runtime_exits_real_mode(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RUNTIME_REMOTE_ORDERS_ENABLED", "1")
  monkeypatch.setenv("LIVE_TRADING_ENABLED", "0")
  module, _client = _build_app(tmp_path, monkeypatch, mode="live")
  monkeypatch.setenv("BINANCE_API_KEY", "live-key")
  monkeypatch.setenv("BINANCE_API_SECRET", "live-secret")
  monkeypatch.setenv("BINANCE_SPOT_BASE_URL", "https://api.binance.com")
  monkeypatch.setenv("BINANCE_SPOT_WS_URL", "wss://stream.binance.com:9443/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )
  monkeypatch.setattr(module.store.registry, "get_principal", lambda mode: {"name": "meanreversion_runtime_v2"})
  monkeypatch.setattr(
    module.store,
    "strategy_or_404",
    lambda strategy_id: {
      "id": strategy_id,
      "enabled_for_trading": True,
      "params": {"runtime_symbol": "BTCUSDT"},
      "tags": ["mean_reversion", "range"],
    },
  )

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    if path == "/api/v3/order" and method_u == "POST":
      return True, {"status_code": 200, "payload": {"clientOrderId": "unexpected-live", "orderId": 1, "origQty": "0.001", "executedQty": "0.0"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "live"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced_live = module._sync_runtime_state(state, persist=False)
  assert str(synced_live.get("runtime_last_remote_submit_reason") or "") == "live_trading_disabled"

  synced_live["runtime_engine"] = "simulated"
  synced_live["running"] = False
  synced_off = module._sync_runtime_state(synced_live, persist=False)
  assert str(synced_off.get("runtime_last_remote_submit_reason") or "") == ""
  assert str(synced_off.get("runtime_last_remote_submit_error") or "") == ""


def test_runtime_exchange_ready_forces_refresh_after_cached_failure(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  calls: list[bool] = []

  def _fake_diagnose(mode: str | None = None, *, force_refresh: bool = False):
    calls.append(bool(force_refresh))
    if not force_refresh:
      return {
        "connector_ok": False,
        "order_ok": False,
        "connector_reason": "cached_fail",
        "order_reason": "cached_fail",
        "last_error": "cached_fail",
      }
    return {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "fresh_ok",
      "order_reason": "fresh_ok",
      "last_error": "",
    }

  monkeypatch.setattr(module, "diagnose_exchange", _fake_diagnose)
  ready = module.runtime_bridge._runtime_exchange_ready(mode="testnet")
  assert calls == [False, True]
  assert ready["ok"] is True
  assert ready["connector_ok"] is True
  assert ready["order_ok"] is True


def test_runtime_exchange_ready_uses_cached_success_without_forced_refresh(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  calls: list[bool] = []

  def _fake_diagnose(mode: str | None = None, *, force_refresh: bool = False):
    calls.append(bool(force_refresh))
    return {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "cached_ok",
      "order_reason": "cached_ok",
      "last_error": "",
    }

  monkeypatch.setattr(module, "diagnose_exchange", _fake_diagnose)
  ready = module.runtime_bridge._runtime_exchange_ready(mode="testnet")
  assert calls == [False]
  assert ready["ok"] is True
  assert ready["connector_ok"] is True
  assert ready["order_ok"] is True


def test_runtime_sync_testnet_reconciles_positions_from_exchange_account_snapshot(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {"status_code": 200, "payload": []}
    if path == "/api/v3/account" and method_u == "GET":
      return True, {
        "status_code": 200,
        "payload": {
          "balances": [
            {"asset": "BTC", "free": "0.25", "locked": "0.05"},
            {"asset": "USDT", "free": "500.0", "locked": "0.0"},
          ]
        },
      }
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert bool(synced.get("runtime_account_positions_ok")) is True
  assert str(synced.get("runtime_account_positions_verified_at") or "")
  assert str(synced.get("runtime_account_positions_reason") or "") == "exchange_api"

  positions = module.runtime_bridge.positions()
  btc = next((row for row in positions if row.get("symbol") == "BTCUSDT"), None)
  assert btc is not None
  assert float(btc["qty"]) == pytest.approx(0.30, rel=1e-4)
  assert str(btc["side"]) == "long"
  assert float(btc["exposure_usd"]) > 0.0


def test_runtime_sync_testnet_account_positions_failure_falls_back_to_open_orders_positions(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      return True, {
        "status_code": 200,
        "payload": [
          {
            "clientOrderId": "oid-pos-fallback-1",
            "orderId": 445566,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "origQty": "1.0",
            "executedQty": "0.4",
          }
        ],
      }
    if path == "/api/v3/account" and method_u == "GET":
      return False, {"status_code": 503, "payload": {"code": -1000, "msg": "exchange down"}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced = module._sync_runtime_state(state, persist=False)
  assert bool(synced.get("runtime_account_positions_ok")) is False
  assert str(synced.get("runtime_account_positions_reason") or "").strip() != ""

  positions = module.runtime_bridge.positions()
  assert any(str(row.get("order_id") or "") == "oid-pos-fallback-1" for row in positions)


def test_runtime_execution_metrics_accumulate_costs_from_fill_deltas(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "connector_ok": True,
      "order_ok": True,
      "connector_reason": "",
      "order_reason": "",
      "last_error": "",
    },
  )

  calls = {"open_orders_get": 0}

  def _fake_signed_request(*, method, base_url, path, api_key, api_secret, params=None, timeout_sec=8):
    method_u = str(method).upper()
    if path == "/api/v3/openOrders" and method_u == "GET":
      calls["open_orders_get"] += 1
      executed_qty = "0.2" if calls["open_orders_get"] <= 1 else "0.5"
      return True, {
        "status_code": 200,
        "payload": [
          {
            "clientOrderId": "oid-costs-1",
            "orderId": 778899,
            "symbol": "BTCUSDT",
            "side": "BUY",
            "origQty": "1.0",
            "executedQty": executed_qty,
          }
        ],
      }
    if path == "/api/v3/account" and method_u == "GET":
      return True, {"status_code": 200, "payload": {"balances": []}}
    return False, {"status_code": 404, "payload": {"msg": "not mocked"}}

  monkeypatch.setattr(module, "_binance_signed_request", _fake_signed_request)
  module.runtime_bridge._oms.orders.clear()

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  state["running"] = True
  state["killed"] = False

  synced_1 = module._sync_runtime_state(state, persist=False)
  metrics_1 = module.runtime_bridge.execution_metrics_snapshot()
  assert bool(synced_1.get("runtime_reconciliation_ok")) is True
  assert int(metrics_1.get("fills_count_runtime") or 0) >= 1
  first_total_cost = float(metrics_1.get("total_cost_runtime_usd") or 0.0)
  assert first_total_cost > 0.0

  synced_2 = module._sync_runtime_state(synced_1, persist=False)
  metrics_2 = module.runtime_bridge.execution_metrics_snapshot()
  assert bool(synced_2.get("runtime_reconciliation_ok")) is True
  assert int(metrics_2.get("fills_count_runtime") or 0) >= int(metrics_1.get("fills_count_runtime") or 0)
  assert float(metrics_2.get("total_cost_runtime_usd") or 0.0) > first_total_cost


def test_runtime_contract_snapshot_defaults_are_exposed_in_status(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="paper")

  status = module.build_status_payload()
  runtime_snapshot = status.get("runtime_snapshot") or {}
  runtime = status.get("runtime") or {}
  telemetry_guard = status.get("runtime_telemetry_guard") or {}

  assert runtime_snapshot.get("contract_version") == "runtime_snapshot_v1"
  assert runtime_snapshot.get("telemetry_source") == "synthetic_v1"
  assert runtime_snapshot.get("ready_for_live") is False
  assert runtime.get("contract_version") == "runtime_snapshot_v1"
  assert runtime.get("telemetry_source") == "synthetic_v1"
  assert runtime.get("ready_for_live") is False
  assert runtime.get("telemetry_fail_closed") is True
  assert telemetry_guard.get("fail_closed") is True


def test_g9_live_passes_only_when_runtime_contract_is_fully_ready(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  strategies = client.get("/api/v1/strategies", headers=headers)
  strategy_id = strategies.json()[0]["id"]
  set_live_primary = client.post(f"/api/v1/strategies/{strategy_id}/primary", headers=headers, json={"mode": "live"})
  assert set_live_primary.status_code == 200, set_live_primary.text

  state = module.store.load_bot_state()
  state["runtime_engine"] = "real"
  module.store.save_bot_state(state)

  gates_live_fail = module.evaluate_gates("live", force_exchange_check=True)
  g9_fail = {row["id"]: row for row in gates_live_fail["gates"]}["G9_RUNTIME_ENGINE_REAL"]
  assert g9_fail["status"] == "FAIL"
  runtime_contract_fail = (g9_fail.get("details") or {}).get("runtime_contract") or {}
  assert runtime_contract_fail.get("ready_for_live") is False
  assert runtime_contract_fail.get("missing_checks")

  state = module.store.load_bot_state()
  state.update(
    {
      "runtime_engine": "real",
      "runtime_contract_version": "runtime_snapshot_v1",
      "runtime_telemetry_source": "runtime_loop_v1",
      "runtime_loop_alive": True,
      "runtime_executor_connected": True,
      "runtime_reconciliation_ok": True,
      "runtime_exchange_connector_ok": True,
      "runtime_exchange_order_ok": True,
      "runtime_exchange_mode": "live",
      "runtime_exchange_verified_at": module.utc_now_iso(),
      "runtime_heartbeat_at": module.utc_now_iso(),
      "runtime_last_reconcile_at": module.utc_now_iso(),
    }
  )
  module.store.save_bot_state(state)

  gates_live_pass = module.evaluate_gates("live", force_exchange_check=True, runtime_state=state)
  g9_pass = {row["id"]: row for row in gates_live_pass["gates"]}["G9_RUNTIME_ENGINE_REAL"]
  assert g9_pass["status"] == "PASS"
  runtime_contract_pass = (g9_pass.get("details") or {}).get("runtime_contract") or {}
  assert runtime_contract_pass.get("ready_for_live") is True
  checks = runtime_contract_pass.get("checks") or {}
  assert all(bool(v) for v in checks.values())


def test_g9_live_fails_when_runtime_exchange_mode_does_not_match_target_mode(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  strategy_id = client.get("/api/v1/strategies", headers=headers).json()[0]["id"]
  set_live_primary = client.post(f"/api/v1/strategies/{strategy_id}/primary", headers=headers, json={"mode": "live"})
  assert set_live_primary.status_code == 200, set_live_primary.text

  state = module.store.load_bot_state()
  state.update(
    {
      "runtime_engine": "real",
      "runtime_contract_version": "runtime_snapshot_v1",
      "runtime_telemetry_source": "runtime_loop_v1",
      "runtime_loop_alive": True,
      "runtime_executor_connected": True,
      "runtime_reconciliation_ok": True,
      "runtime_exchange_connector_ok": True,
      "runtime_exchange_order_ok": True,
      "runtime_exchange_mode": "testnet",
      "runtime_exchange_verified_at": module.utc_now_iso(),
      "runtime_heartbeat_at": module.utc_now_iso(),
      "runtime_last_reconcile_at": module.utc_now_iso(),
    }
  )
  module.store.save_bot_state(state)

  gates_live = module.evaluate_gates("live", force_exchange_check=True, runtime_state=state)
  g9 = {row["id"]: row for row in gates_live["gates"]}["G9_RUNTIME_ENGINE_REAL"]
  assert g9["status"] == "FAIL"
  runtime_contract = (g9.get("details") or {}).get("runtime_contract") or {}
  missing_checks = set(str(x) for x in (runtime_contract.get("missing_checks") or []))
  assert "exchange_mode_match" in missing_checks


def test_g9_live_fails_when_runtime_heartbeat_is_stale(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  strategies = client.get("/api/v1/strategies", headers=headers)
  strategy_id = strategies.json()[0]["id"]
  set_live_primary = client.post(f"/api/v1/strategies/{strategy_id}/primary", headers=headers, json={"mode": "live"})
  assert set_live_primary.status_code == 200, set_live_primary.text

  stale_heartbeat = (module.utc_now() - module.timedelta(seconds=int(module.RUNTIME_HEARTBEAT_MAX_AGE_SEC) + 15)).isoformat()
  state = module.store.load_bot_state()
  state.update(
    {
      "runtime_engine": "real",
      "runtime_contract_version": "runtime_snapshot_v1",
      "runtime_telemetry_source": "runtime_loop_v1",
      "runtime_loop_alive": True,
      "runtime_executor_connected": True,
      "runtime_reconciliation_ok": True,
      "runtime_heartbeat_at": stale_heartbeat,
      "runtime_last_reconcile_at": module.utc_now_iso(),
    }
  )
  module.store.save_bot_state(state)

  gates_live = module.evaluate_gates("live", force_exchange_check=True)
  g9 = {row["id"]: row for row in gates_live["gates"]}["G9_RUNTIME_ENGINE_REAL"]
  assert g9["status"] == "FAIL"
  runtime_contract = (g9.get("details") or {}).get("runtime_contract") or {}
  missing_checks = set(str(x) for x in (runtime_contract.get("missing_checks") or []))
  assert "heartbeat_fresh" in missing_checks


def test_g9_live_fails_when_runtime_reconciliation_is_stale_and_recovers(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  strategy_id = client.get("/api/v1/strategies", headers=headers).json()[0]["id"]
  set_live_primary = client.post(f"/api/v1/strategies/{strategy_id}/primary", headers=headers, json={"mode": "live"})
  assert set_live_primary.status_code == 200, set_live_primary.text

  stale_reconcile = (
    module.utc_now() - module.timedelta(seconds=int(module.RUNTIME_RECONCILIATION_MAX_AGE_SEC) + 20)
  ).isoformat()
  state = module.store.load_bot_state()
  state.update(
    {
      "runtime_engine": "real",
      "runtime_contract_version": "runtime_snapshot_v1",
      "runtime_telemetry_source": "runtime_loop_v1",
      "runtime_loop_alive": True,
      "runtime_executor_connected": True,
      "runtime_reconciliation_ok": True,
      "runtime_exchange_connector_ok": True,
      "runtime_exchange_order_ok": True,
      "runtime_exchange_mode": "live",
      "runtime_exchange_verified_at": module.utc_now_iso(),
      "runtime_heartbeat_at": module.utc_now_iso(),
      "runtime_last_reconcile_at": stale_reconcile,
    }
  )
  module.store.save_bot_state(state)

  gates_fail = module.evaluate_gates("live", force_exchange_check=True, runtime_state=state)
  g9_fail = {row["id"]: row for row in gates_fail["gates"]}["G9_RUNTIME_ENGINE_REAL"]
  assert g9_fail["status"] == "FAIL"
  runtime_contract_fail = (g9_fail.get("details") or {}).get("runtime_contract") or {}
  missing_checks = set(str(x) for x in (runtime_contract_fail.get("missing_checks") or []))
  assert "reconciliation_fresh" in missing_checks

  refreshed = module.store.load_bot_state()
  refreshed["runtime_last_reconcile_at"] = module.utc_now_iso()
  module.store.save_bot_state(refreshed)

  gates_pass = module.evaluate_gates("live", force_exchange_check=True, runtime_state=refreshed)
  g9_pass = {row["id"]: row for row in gates_pass["gates"]}["G9_RUNTIME_ENGINE_REAL"]
  assert g9_pass["status"] == "PASS"


def test_evaluate_gates_does_not_persist_runtime_state_side_effects(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)

  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  strategy_id = client.get("/api/v1/strategies", headers=headers).json()[0]["id"]
  set_live_primary = client.post(f"/api/v1/strategies/{strategy_id}/primary", headers=headers, json={"mode": "live"})
  assert set_live_primary.status_code == 200, set_live_primary.text

  initial_state = module.store.load_bot_state()
  initial_state.update(
    {
      "running": True,
      "killed": False,
      "runtime_engine": "real",
      "runtime_telemetry_source": "runtime_loop_v1",
      "runtime_loop_alive": True,
      "runtime_executor_connected": True,
      "runtime_reconciliation_ok": True,
      "runtime_exchange_connector_ok": True,
      "runtime_exchange_order_ok": True,
      "runtime_exchange_mode": "live",
      "runtime_exchange_verified_at": module.utc_now_iso(),
      "runtime_heartbeat_at": module.utc_now_iso(),
      "runtime_last_reconcile_at": module.utc_now_iso(),
    }
  )
  module.store.save_bot_state(initial_state)
  before = module.store.load_bot_state()

  gates_live = module.evaluate_gates("live", force_exchange_check=True)
  assert gates_live.get("mode") == "live"

  after = module.store.load_bot_state()
  assert after == before


def test_runtime_real_start_wires_runtime_bridge_into_status_execution_and_risk(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  module.store.save_bot_state(state)

  start_res = client.post("/api/v1/bot/start", headers=headers)
  assert start_res.status_code == 200, start_res.text

  status_res = client.get("/api/v1/status", headers=headers)
  assert status_res.status_code == 200, status_res.text
  status_payload = status_res.json()
  runtime = status_payload.get("runtime") or {}
  runtime_snapshot = status_payload.get("runtime_snapshot") or {}
  assert runtime.get("telemetry_source") == "runtime_loop_v1"
  assert runtime.get("telemetry_fail_closed") is False
  assert runtime_snapshot.get("runtime_loop_alive") is True
  assert runtime_snapshot.get("executor_connected") is True
  assert runtime_snapshot.get("reconciliation_ok") is True
  assert isinstance(status_payload.get("positions"), list)

  execution_res = client.get("/api/v1/execution/metrics", headers=headers)
  assert execution_res.status_code == 200, execution_res.text
  execution_payload = execution_res.json()
  assert execution_payload.get("runtime_telemetry_source") == "runtime_loop_v1"
  assert execution_payload.get("runtime_telemetry_fail_closed") is False
  assert execution_payload.get("runtime_telemetry_ok") is True
  assert isinstance(execution_payload.get("series"), list)
  assert execution_payload.get("series")

  risk_res = client.get("/api/v1/risk", headers=headers)
  assert risk_res.status_code == 200, risk_res.text
  risk_payload = risk_res.json()
  assert isinstance(risk_payload.get("runtime_risk_decision"), dict)
  assert isinstance(risk_payload.get("reconciliation"), dict)
  assert risk_payload.get("runtime_telemetry_fail_closed") is False
  assert "gate_checklist" in risk_payload


def test_execution_metrics_fail_closed_when_telemetry_source_is_synthetic(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch, mode="paper")
  payload = module.build_execution_metrics_payload()
  assert payload.get("runtime_telemetry_source") == "synthetic_v1"
  assert payload.get("runtime_telemetry_fail_closed") is True
  assert payload.get("runtime_telemetry_ok") is False
  assert float(payload.get("fill_ratio") or 0.0) == 0.0
  assert float(payload.get("maker_ratio") or 0.0) == 0.0
  assert float(payload.get("latency_ms_p95") or 0.0) >= 999.0
  assert int(payload.get("api_errors") or 0) >= 1
  assert int(payload.get("fills_count_runtime") or 0) == 0
  assert float(payload.get("total_cost_runtime_usd") or 0.0) == 0.0
  runtime_costs = payload.get("runtime_costs") if isinstance(payload.get("runtime_costs"), dict) else {}
  assert float(runtime_costs.get("total_cost_usd") or 0.0) == 0.0


def test_runtime_stop_and_killswitch_force_runtime_contract_back_to_non_live(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  state = module.store.load_bot_state()
  state["mode"] = "testnet"
  state["runtime_engine"] = "real"
  module.store.save_bot_state(state)

  started = client.post("/api/v1/bot/start", headers=headers)
  assert started.status_code == 200, started.text

  stopped = client.post("/api/v1/bot/stop", headers=headers)
  assert stopped.status_code == 200, stopped.text
  status_after_stop = client.get("/api/v1/status", headers=headers).json()
  snap_stop = status_after_stop.get("runtime_snapshot") or {}
  assert snap_stop.get("runtime_loop_alive") is False
  assert snap_stop.get("executor_connected") is False
  assert snap_stop.get("telemetry_source") == "synthetic_v1"
  assert bool((snap_stop.get("missing_checks") or []))

  started_again = client.post("/api/v1/bot/start", headers=headers)
  assert started_again.status_code == 200, started_again.text

  killed = client.post("/api/v1/bot/killswitch", headers=headers)
  assert killed.status_code == 200, killed.text
  status_after_kill = client.get("/api/v1/status", headers=headers).json()
  snap_kill = status_after_kill.get("runtime_snapshot") or {}
  assert status_after_kill.get("bot_status") == "KILLED"
  assert bool((status_after_kill.get("risk_flags") or {}).get("killed")) is True
  assert snap_kill.get("runtime_loop_alive") is False
  assert snap_kill.get("executor_connected") is False
  assert snap_kill.get("telemetry_source") == "synthetic_v1"

  risk_after_kill = client.get("/api/v1/risk", headers=headers)
  assert risk_after_kill.status_code == 200, risk_after_kill.text
  breakers = risk_after_kill.json().get("circuit_breakers") or []
  assert "kill_switch" in breakers


def test_health_reports_storage_persistence_status(tmp_path: Path, monkeypatch) -> None:
  _, client = _build_app(tmp_path, monkeypatch)
  res = client.get("/api/v1/health")
  assert res.status_code == 200, res.text
  body = res.json()
  storage = body.get("storage") or {}
  assert "user_data_dir" in storage
  assert "storage_ephemeral" in storage
  assert "persistent_storage" in storage
  assert isinstance(storage.get("persistent_storage"), bool)


def test_storage_gate_blocks_live_when_user_data_is_ephemeral(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch)
  monkeypatch.setattr(module, "USER_DATA_DIR", Path("/tmp/rtlab_user_data"))

  gates_live = module.evaluate_gates("live")
  gate_by_id = {row["id"]: row for row in gates_live["gates"]}
  assert gate_by_id["G10_STORAGE_PERSISTENCE"]["status"] == "FAIL"
  assert "efimero" in str(gate_by_id["G10_STORAGE_PERSISTENCE"].get("reason") or "").lower()

  can_live, reason = module.live_can_be_enabled(gates_live)
  assert can_live is False


def test_strategy_upload_validation_and_primary_assignment(tmp_path: Path, monkeypatch) -> None:
  _, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  bad_zip = _make_zip(
    {
      "strategy.yaml": "id: bad_strategy\nname: bad\nversion: \"1.0.0\"\n",
      "strategy.py": "def generate_signals(ctx):\n  return {}\n",
    }
  )
  bad_upload = client.post(
    "/api/v1/strategies/upload",
    headers=headers,
    files={"file": ("bad_strategy.zip", bad_zip, "application/zip")},
  )
  assert bad_upload.status_code == 400
  assert "Missing required hooks" in bad_upload.json()["detail"]

  good_yaml = """
id: uploaded_strategy_v1
name: Uploaded Strategy
version: 1.0.0
description: Upload test strategy
parameters_schema:
  type: object
  properties:
    risk_per_trade_pct:
      type: number
defaults:
  risk_per_trade_pct: 0.8
""".strip()
  good_code = """
def generate_signals(context):
    return {"action": "flat"}

def on_bar(context):
    return None

def on_trade(context):
    return None

def risk_hooks(context):
    return {"allowed": True}
""".strip()
  good_zip = _make_zip({"strategy.yaml": good_yaml, "strategy.py": good_code})
  good_upload = client.post(
    "/api/v1/strategies/upload",
    headers=headers,
    files={"file": ("uploaded_strategy_v1.zip", good_zip, "application/zip")},
  )
  assert good_upload.status_code == 200, good_upload.text

  set_live_primary = client.post("/api/v1/strategies/uploaded_strategy_v1/primary", headers=headers, json={"mode": "live"})
  assert set_live_primary.status_code == 200
  assert "live" in set_live_primary.json()["strategy"]["primary_for_modes"]


def test_strategy_yaml_upload_supported(tmp_path: Path, monkeypatch) -> None:
  _, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  yaml_payload = """
id: yaml_uploaded_strategy
name: YAML Uploaded Strategy
version: 1.2.3
description: Strategy uploaded as YAML only
parameters_schema:
  type: object
defaults:
  risk_per_trade_pct: 0.5
tags: [upload, yaml]
""".strip()

  res = client.post(
    "/api/v1/strategies/upload",
    headers=headers,
    files={"file": ("yaml_uploaded_strategy.yaml", yaml_payload.encode("utf-8"), "application/x-yaml")},
  )
  assert res.status_code == 200, res.text
  body = res.json()
  assert body["ok"] is True
  assert body["strategy"]["id"] == "yaml_uploaded_strategy"
  assert body["strategy"]["version"] == "1.2.3"


def test_settings_endpoint_recovers_legacy_settings_shape(tmp_path: Path, monkeypatch) -> None:
  legacy_settings = {
    "mode": "PAPER",
    "exchange": "binance",
    "learning": {"enabled": True, "mode": "RESEARCH"},
  }
  _, client = _build_app(tmp_path, monkeypatch, seed_settings=legacy_settings)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.get("/api/v1/settings", headers=headers)
  assert res.status_code == 200, res.text
  body = res.json()
  assert body["mode"] == "PAPER"
  assert isinstance(body.get("credentials"), dict)
  assert isinstance(body.get("telegram"), dict)
  assert isinstance(body.get("risk_defaults"), dict)
  assert isinstance(body.get("execution"), dict)
  assert isinstance(body.get("feature_flags"), dict)
  assert isinstance(body.get("rollout"), dict)
  assert isinstance(body.get("blending"), dict)
  assert isinstance(body["rollout"].get("testnet_checks"), dict)


def test_learning_research_loop_and_adopt_option_b(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  def _fake_learning_eval_candidate(_candidate: dict[str, object]) -> dict[str, object]:
    return {
      "metrics": {
        "max_dd": 0.08,
        "sortino": 1.25,
        "expectancy": 0.07,
        "sharpe": 1.10,
      },
      "costs_breakdown": {
        "gross_pnl_total": 140.0,
        "total_cost": 18.0,
      },
      "equity_curve": [
        {"t": "2024-01-01T00:00:00+00:00", "equity": 1000.0},
        {"t": "2024-01-02T00:00:00+00:00", "equity": 1012.0},
        {"t": "2024-01-03T00:00:00+00:00", "equity": 1024.0},
      ],
      "data_source": "dataset",
      "dataset_hash": "test_dataset_hash",
      "costs_model": {
        "fees_bps": 5.5,
        "spread_bps": 4.0,
        "slippage_bps": 3.0,
        "funding_bps": 1.0,
        "rollover_bps": 0.0,
      },
    }

  monkeypatch.setattr(module, "_learning_eval_candidate", _fake_learning_eval_candidate)

  settings_get = client.get("/api/v1/settings", headers=headers)
  assert settings_get.status_code == 200, settings_get.text
  settings = settings_get.json()
  settings["learning"]["enabled"] = True
  settings["learning"]["mode"] = "RESEARCH"
  settings["learning"]["validation"]["enforce_pbo"] = False
  settings["learning"]["validation"]["enforce_dsr"] = False

  settings_put = client.put("/api/v1/settings", headers=headers, json=settings)
  assert settings_put.status_code == 200, settings_put.text
  assert settings_put.json()["settings"]["learning"]["promotion"]["allow_live"] is False
  assert settings_put.json()["settings"]["learning"]["promotion"]["allow_auto_apply"] is False

  status_res = client.get("/api/v1/learning/status", headers=headers)
  assert status_res.status_code == 200, status_res.text
  status_payload = status_res.json()
  assert status_payload["option_b"]["allow_live"] is False
  assert "selector" in status_payload
  assert "drift" in status_payload

  drift_res = client.get("/api/v1/learning/drift", headers=headers)
  assert drift_res.status_code == 200, drift_res.text
  assert drift_res.json()["algo"] in {"adwin", "page_hinkley"}

  run_res = client.post("/api/v1/learning/run-now", headers=headers)
  assert run_res.status_code == 200, run_res.text
  run_payload = run_res.json()
  assert run_payload["ok"] is True
  assert run_payload["option_b"]["allow_live"] is False

  recs_res = client.get("/api/v1/learning/recommendations", headers=headers)
  assert recs_res.status_code == 200, recs_res.text
  recs = recs_res.json()
  assert isinstance(recs, list) and recs
  rec = recs[0]
  assert rec["adoptable_modes"] == ["paper", "testnet"]
  assert rec["option_b"]["requires_admin_adoption"] is True
  assert bool(((rec.get("validation") or {}).get("purged_cv") or {}).get("implemented")) is True
  assert bool(((rec.get("validation") or {}).get("cpcv") or {}).get("implemented")) is True

  rec_detail = client.get(f"/api/v1/learning/recommendations/{rec['id']}", headers=headers)
  assert rec_detail.status_code == 200, rec_detail.text
  assert rec_detail.json()["id"] == rec["id"]

  adopt = client.post("/api/v1/learning/adopt", headers=headers, json={"candidate_id": rec["id"], "mode": "paper"})
  assert adopt.status_code == 200, adopt.text
  adopt_body = adopt.json()
  assert adopt_body["ok"] is True
  assert adopt_body["mode"] == "paper"
  assert adopt_body["applied_live"] is False


def test_learning_run_now_fails_closed_when_real_dataset_missing(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  settings_get = client.get("/api/v1/settings", headers=headers)
  assert settings_get.status_code == 200, settings_get.text
  settings = settings_get.json()
  settings["learning"]["enabled"] = True
  settings["learning"]["mode"] = "RESEARCH"
  settings["learning"]["validation"]["enforce_pbo"] = False
  settings["learning"]["validation"]["enforce_dsr"] = False
  settings_put = client.put("/api/v1/settings", headers=headers, json=settings)
  assert settings_put.status_code == 200, settings_put.text

  def _raise_missing_dataset(*_args, **_kwargs):
    raise FileNotFoundError("dataset real ausente para test")

  monkeypatch.setattr(module.DataLoader, "load_resampled", _raise_missing_dataset)

  run_res = client.post("/api/v1/learning/run-now", headers=headers)
  assert run_res.status_code == 400, run_res.text
  detail = str((run_res.json() or {}).get("detail") or "").lower()
  assert "fail-closed" in detail
  assert "dataset real" in detail


def test_learning_eval_candidate_uses_purged_cv_when_walk_forward_disabled(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")

  strategy_id = client.get("/api/v1/strategies", headers=headers).json()[0]["id"]
  base_run = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={
      "strategy_id": strategy_id,
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-01-06",
      "validation_mode": "walk-forward",
    },
  )
  assert base_run.status_code == 200, base_run.text

  settings = client.get("/api/v1/settings", headers=headers).json()
  settings["learning"]["validation"]["walk_forward"] = False
  put_res = client.put("/api/v1/settings", headers=headers, json=settings)
  assert put_res.status_code == 200, put_res.text

  result = module._learning_eval_candidate({"base_strategy_id": strategy_id})
  summary = result.get("validation_summary") or {}
  assert summary.get("mode") == "purged-cv"
  assert bool(summary.get("implemented")) is True
  assert int(summary.get("oos_bars") or 0) > 0


def test_learning_eval_candidate_supports_cpcv_mode_from_settings(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")

  strategy_id = client.get("/api/v1/strategies", headers=headers).json()[0]["id"]
  base_run = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={
      "strategy_id": strategy_id,
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-01-10",
      "validation_mode": "walk-forward",
    },
  )
  assert base_run.status_code == 200, base_run.text

  settings = client.get("/api/v1/settings", headers=headers).json()
  settings["learning"]["validation"]["validation_mode"] = "cpcv"
  settings["learning"]["validation"]["cpcv_n_splits"] = 6
  settings["learning"]["validation"]["cpcv_k_test_groups"] = 2
  settings["learning"]["validation"]["cpcv_max_paths"] = 6
  put_res = client.put("/api/v1/settings", headers=headers, json=settings)
  assert put_res.status_code == 200, put_res.text

  result = module._learning_eval_candidate({"base_strategy_id": strategy_id})
  summary = result.get("validation_summary") or {}
  assert summary.get("mode") == "cpcv"
  assert bool(summary.get("implemented")) is True
  assert int(summary.get("paths_evaluated") or 0) >= 1
  assert int(summary.get("oos_bars") or 0) > 0


class _DummyResponse:
  def __init__(self, status_code: int, payload: dict):
    self.status_code = status_code
    self._payload = payload
    self.text = str(payload)

  @property
  def ok(self) -> bool:
    return 200 <= self.status_code < 300

  def json(self):
    return self._payload


class _DummySocket:
  def __enter__(self):
    return self

  def __exit__(self, exc_type, exc, tb):
    return False


def _mock_exchange_ok(module, monkeypatch) -> None:
  def fake_get(url, timeout=0, **kwargs):
    if "/api/v3/time" in url:
      return _DummyResponse(200, {"serverTime": 1730000000000})
    return _DummyResponse(404, {"code": -1, "msg": "not found"})

  def fake_request(method, url, headers=None, timeout=0, **kwargs):
    if "/api/v3/account" in url:
      return _DummyResponse(200, {"balances": []})
    if "/api/v3/order/test" in url:
      return _DummyResponse(200, {})
    if "/api/v3/openOrders" in url:
      return _DummyResponse(200, [])
    return _DummyResponse(404, {"code": -1, "msg": "not found"})

  monkeypatch.setattr(module.requests, "get", fake_get)
  monkeypatch.setattr(module.requests, "request", fake_request)
  monkeypatch.setattr(module.socket, "create_connection", lambda *args, **kwargs: _DummySocket())


def _mock_exchange_down(module, monkeypatch) -> None:
  def fake_get(url, timeout=0, **kwargs):
    return _DummyResponse(503, {"code": -1000, "msg": "exchange down"})

  def fake_request(method, url, headers=None, timeout=0, **kwargs):
    return _DummyResponse(503, {"code": -1000, "msg": "exchange down"})

  def fake_socket(*args, **kwargs):
    raise OSError("network down")

  monkeypatch.setattr(module.requests, "get", fake_get)
  monkeypatch.setattr(module.requests, "request", fake_request)
  monkeypatch.setattr(module.socket, "create_connection", fake_socket)


def test_exchange_diagnose_reports_missing_env_vars_for_testnet(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  diagnose = client.get("/api/v1/exchange/diagnose?mode=testnet&force=true", headers=headers)
  assert diagnose.status_code == 200, diagnose.text
  payload = diagnose.json()
  assert payload["ok"] is False
  assert payload["key_source"] == "none"
  assert "BINANCE_TESTNET_API_KEY" in payload["missing"]
  assert "BINANCE_TESTNET_API_SECRET" in payload["missing"]
  assert "Railway" in payload["last_error"]

  gates = module.evaluate_gates("testnet", force_exchange_check=True)
  gate_by_id = {row["id"]: row for row in gates["gates"]}
  assert gate_by_id["G4_EXCHANGE_CONNECTOR_READY"]["status"] == "FAIL"
  assert "BINANCE_TESTNET_API_KEY" in gate_by_id["G4_EXCHANGE_CONNECTOR_READY"]["details"]["missing_env_vars"]
  assert gate_by_id["G7_ORDER_SIM_OR_PAPER_OK"]["status"] == "FAIL"


def test_exchange_diagnose_passes_with_env_keys_and_mocked_exchange(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  diagnose = client.get("/api/v1/exchange/diagnose?mode=testnet&force=true", headers=headers)
  assert diagnose.status_code == 200, diagnose.text
  payload = diagnose.json()
  assert payload["ok"] is True
  assert payload["key_source"] == "env"
  assert payload["connector_ok"] is True
  assert payload["order_ok"] is True
  assert payload["base_url"] == "https://testnet.binance.vision"

  gates = module.evaluate_gates("testnet", force_exchange_check=True)
  gate_by_id = {row["id"]: row for row in gates["gates"]}
  assert gate_by_id["G4_EXCHANGE_CONNECTOR_READY"]["status"] == "PASS"
  assert gate_by_id["G7_ORDER_SIM_OR_PAPER_OK"]["status"] == "PASS"


def test_exchange_diagnose_degrades_when_exchange_is_down_and_recovers_after_reconnect(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.vision")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_down(module, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  down = client.get("/api/v1/exchange/diagnose?mode=testnet&force=true", headers=headers)
  assert down.status_code == 200, down.text
  down_payload = down.json()
  assert down_payload["ok"] is False
  assert down_payload["connector_ok"] is False
  assert down_payload["order_ok"] is False

  gates_down = module.evaluate_gates("testnet", force_exchange_check=True)
  gates_down_by_id = {row["id"]: row for row in gates_down["gates"]}
  assert gates_down_by_id["G4_EXCHANGE_CONNECTOR_READY"]["status"] == "FAIL"
  assert gates_down_by_id["G7_ORDER_SIM_OR_PAPER_OK"]["status"] == "FAIL"

  _mock_exchange_ok(module, monkeypatch)
  up = client.get("/api/v1/exchange/diagnose?mode=testnet&force=true", headers=headers)
  assert up.status_code == 200, up.text
  up_payload = up.json()
  assert up_payload["ok"] is True
  assert up_payload["connector_ok"] is True
  assert up_payload["order_ok"] is True

  gates_up = module.evaluate_gates("testnet", force_exchange_check=True)
  gates_up_by_id = {row["id"]: row for row in gates_up["gates"]}
  assert gates_up_by_id["G4_EXCHANGE_CONNECTOR_READY"]["status"] == "PASS"
  assert gates_up_by_id["G7_ORDER_SIM_OR_PAPER_OK"]["status"] == "PASS"


def test_exchange_diagnose_autocorrects_common_binance_testnet_url_typo(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "test-key")
  monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "test-secret")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_BASE_URL", "https://testnet.binance.visio")
  monkeypatch.setenv("BINANCE_SPOT_TESTNET_WS_URL", "wss://testnet.binance.vision/ws")
  _mock_exchange_ok(module, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  diagnose = client.get("/api/v1/exchange/diagnose?mode=testnet&force=true", headers=headers)
  assert diagnose.status_code == 200, diagnose.text
  payload = diagnose.json()
  assert payload["ok"] is True
  assert payload["base_url"] == "https://testnet.binance.vision"
  assert any("corregida autom" in str(msg).lower() for msg in (payload.get("diagnostics") or []))


def test_exchange_diagnose_uses_json_only_in_local_dev(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="testnet")
  cfg_dir = Path(module.USER_DATA_DIR) / "config"
  cfg_dir.mkdir(parents=True, exist_ok=True)
  (cfg_dir / "exchange_binance_spot.json").write_text(
    '{"testnet":{"api_key":"json-key","api_secret":"json-secret"}}',
    encoding="utf-8",
  )
  _mock_exchange_ok(module, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  diagnose = client.get("/api/v1/exchange/diagnose?mode=testnet&force=true", headers=headers)
  assert diagnose.status_code == 200, diagnose.text
  payload = diagnose.json()
  assert payload["has_keys"] is True
  assert payload["key_source"] == "json"


def test_backtest_costs_and_entry_metrics_are_exposed(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")

  strategies = client.get("/api/v1/strategies", headers=headers).json()
  strategy_id = strategies[0]["id"]
  payload_common = {
    "strategy_id": strategy_id,
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "start": "2024-01-01",
    "end": "2024-03-31",
    "validation_mode": "walk-forward",
  }

  low_cost = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={**payload_common, "costs_model": {"fees_bps": 0.0, "spread_bps": 0.0, "slippage_bps": 0.0, "funding_bps": 0.0}},
  )
  assert low_cost.status_code == 200, low_cost.text
  low_run = low_cost.json()["run"]

  high_cost = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={**payload_common, "costs_model": {"fees_bps": 20.0, "spread_bps": 20.0, "slippage_bps": 20.0, "funding_bps": 20.0}},
  )
  assert high_cost.status_code == 200, high_cost.text
  high_run = high_cost.json()["run"]

  for field in ["total_entries", "total_exits", "total_roundtrips", "trade_count"]:
    assert field in high_run["metrics"]
    assert isinstance(high_run["metrics"][field], int)
    assert high_run["metrics"][field] >= 0

  for field in ["fees_total", "spread_total", "slippage_total", "funding_total", "total_cost"]:
    assert field in high_run["costs_breakdown"]

  assert float(high_run["costs_model"]["fees_bps"]) > float(low_run["costs_model"]["fees_bps"])
  if int(high_run["metrics"].get("trade_count", 0)) > 0 and int(low_run["metrics"].get("trade_count", 0)) > 0:
    assert high_run["costs_breakdown"]["total_cost"] > low_run["costs_breakdown"]["total_cost"]
    assert high_run["metrics"]["expectancy"] < low_run["metrics"]["expectancy"]


def test_backtests_run_rejects_synthetic_source(tmp_path: Path, monkeypatch) -> None:
  _, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={
      "strategy_id": "trend_pullback_orderflow_confirm_v1",
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-01-31",
      "data_source": "synthetic",
    },
  )
  assert res.status_code == 400
  assert "no permite resultados sint" in res.json()["detail"].lower()


def test_backtests_run_supports_purged_cv_and_cpcv(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")

  strategy_id = client.get("/api/v1/strategies", headers=headers).json()[0]["id"]
  payload = {
    "strategy_id": strategy_id,
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "start": "2024-01-01",
    "end": "2024-03-31",
    "costs_model": {"fees_bps": 5.0, "spread_bps": 4.0, "slippage_bps": 3.0, "funding_bps": 0.0},
  }

  purged = client.post("/api/v1/backtests/run", headers=headers, json={**payload, "validation_mode": "purged-cv"})
  assert purged.status_code == 200, purged.text
  purged_run = purged.json()["run"]
  assert purged_run["validation_mode"] == "purged-cv"
  summary = purged_run.get("validation_summary") or {}
  assert summary.get("mode") == "purged-cv"
  assert bool(summary.get("implemented")) is True
  assert int(summary.get("oos_bars") or 0) > 0
  assert int(summary.get("purge_bars") or 0) >= 0
  assert int(summary.get("embargo_bars") or 0) >= 0

  cpcv = client.post("/api/v1/backtests/run", headers=headers, json={**payload, "validation_mode": "cpcv"})
  assert cpcv.status_code == 200, cpcv.text
  cpcv_run = cpcv.json()["run"]
  assert cpcv_run["validation_mode"] == "cpcv"
  cpcv_summary = cpcv_run.get("validation_summary") or {}
  assert cpcv_summary.get("mode") == "cpcv"
  assert bool(cpcv_summary.get("implemented")) is True
  assert int(cpcv_summary.get("paths_evaluated") or 0) >= 1
  assert int(cpcv_summary.get("oos_bars") or 0) > 0


def test_backtests_run_forwards_strict_strategy_id_flag(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  captured: dict[str, object] = {}

  def _fake_event_backtest_run(**kwargs):
    captured.update(kwargs)
    return {"id": "BT-STRICT-FLAG"}

  monkeypatch.setattr(module.store, "create_event_backtest_run", _fake_event_backtest_run)

  payload = {
    "strategy_id": "trend_pullback_orderflow_confirm_v1",
    "bot_id": "BOT-TEST-STRICT",
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "start": "2024-01-01",
    "end": "2024-01-31",
    "strict_strategy_id": True,
  }
  res = client.post("/api/v1/backtests/run", headers=headers, json=payload)
  assert res.status_code == 200, res.text
  assert res.json()["run_id"] == "BT-STRICT-FLAG"
  assert captured.get("strict_strategy_id") is True
  assert captured.get("bot_id") == "BOT-TEST-STRICT"


def test_runs_catalog_preserves_explicit_bot_link_after_pool_change(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")

  bot_items = client.get("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0", headers=headers).json()["items"]
  assert bot_items
  bot_id = str(bot_items[0]["id"])

  strategies = client.get("/api/v1/strategies", headers=headers).json()
  assert strategies
  strategy_id = str(strategies[0]["id"])
  other_strategy_ids = [str(row["id"]) for row in strategies[1:] if str(row.get("id") or "").strip()]

  run_res = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={
      "strategy_id": strategy_id,
      "bot_id": bot_id,
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-03-31",
      "validation_mode": "walk-forward",
    },
  )
  assert run_res.status_code == 200, run_res.text
  run_id = str(run_res.json()["run_id"])

  patch_res = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"pool_strategy_ids": other_strategy_ids[:1]},
  )
  assert patch_res.status_code == 200, patch_res.text

  bot_runs = client.get(f"/api/v1/runs?bot_id={bot_id}", headers=headers)
  assert bot_runs.status_code == 200, bot_runs.text
  rows = bot_runs.json()["items"]
  match = next((row for row in rows if str(row.get("run_id") or "") == run_id), None)
  assert match is not None, rows
  assert bot_id in (match.get("related_bot_ids") or [])
  assert any(str(tag or "") == f"bot:{bot_id}" for tag in (match.get("tags") or []))
  assert str(((match.get("params_json") or {}).get("bot_id") or "")) == bot_id


def test_validate_promotion_blocks_mixed_orderflow_feature_set(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(_module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")

  strategy_id = client.get("/api/v1/strategies", headers=headers).json()[0]["id"]
  payload_common = {
    "strategy_id": strategy_id,
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "start": "2024-01-01",
    "end": "2024-03-31",
    "validation_mode": "walk-forward",
    "costs_model": {"fees_bps": 5.0, "spread_bps": 4.0, "slippage_bps": 2.0, "funding_bps": 1.0},
  }

  run_on_res = client.post("/api/v1/backtests/run", headers=headers, json={**payload_common, "use_orderflow_data": True})
  assert run_on_res.status_code == 200, run_on_res.text
  run_on_id = str(run_on_res.json()["run"]["id"])

  run_off_res = client.post("/api/v1/backtests/run", headers=headers, json={**payload_common, "use_orderflow_data": False})
  assert run_off_res.status_code == 200, run_off_res.text
  run_off_id = str(run_off_res.json()["run"]["id"])

  validate_res = client.post(
    f"/api/v1/runs/{run_off_id}/validate_promotion",
    headers=headers,
    json={"target_mode": "paper", "baseline_run_id": run_on_id},
  )
  assert validate_res.status_code == 200, validate_res.text
  payload = validate_res.json()
  compare_failed = set(((payload.get("compare_vs_baseline") or {}).get("failed_ids") or []))
  assert "same_feature_set" in compare_failed
  checks = (payload.get("constraints") or {}).get("checks") or []
  same_feature_check = next(row for row in checks if row.get("id") == "same_feature_set")
  assert bool(same_feature_check.get("ok")) is False
  assert payload.get("rollout_ready") is False


def _seed_local_backtest_dataset(user_data_dir: Path, market: str, symbol: str, *, source: str, include_bid_ask: bool = False) -> None:
  import json

  data_root = user_data_dir / "data" / market
  processed_dir = data_root / "processed"
  manifests_dir = data_root / "manifests"
  processed_dir.mkdir(parents=True, exist_ok=True)
  manifests_dir.mkdir(parents=True, exist_ok=True)

  idx = pd.date_range("2024-01-01T00:00:00Z", periods=12000, freq="1min")
  # Deterministic synthetic-realistic path for integration tests (not production dataset).
  base = 100 + np.linspace(0, 8, len(idx)) + np.sin(np.linspace(0, 40, len(idx))) * 1.5
  close = pd.Series(base, index=idx)
  open_ = close.shift(1).fillna(close.iloc[0])
  spread = 0.15 + (np.sin(np.linspace(0, 70, len(idx))) + 1) * 0.02
  high = np.maximum(open_.to_numpy(), close.to_numpy()) + spread
  low = np.minimum(open_.to_numpy(), close.to_numpy()) - spread
  volume = 1000 + (np.cos(np.linspace(0, 20, len(idx))) + 1) * 250
  df = pd.DataFrame(
    {
      "timestamp": idx,
      "open": open_.to_numpy(),
      "high": high,
      "low": low,
      "close": close.to_numpy(),
      "volume": volume,
    }
  )
  if include_bid_ask:
    # Small spread around mid to let forex cost model derive dynamic spread.
    df["bid_open"] = df["open"] - 0.00015
    df["bid_high"] = df["high"] - 0.00010
    df["bid_low"] = df["low"] - 0.00020
    df["bid_close"] = df["close"] - 0.00015
    df["ask_open"] = df["open"] + 0.00015
    df["ask_high"] = df["high"] + 0.00020
    df["ask_low"] = df["low"] + 0.00010
    df["ask_close"] = df["close"] + 0.00015

  csv_path = processed_dir / f"{symbol}_1m.csv"
  df.to_csv(csv_path, index=False)

  import hashlib
  digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
  manifest_path = manifests_dir / f"{symbol}_1m.json"
  manifest = {
    "market": market,
    "symbol": symbol,
    "timeframe": "1m",
    "source": source,
    "start": str(df["timestamp"].min().isoformat()),
    "end": str(df["timestamp"].max().isoformat()),
    "files": [str(csv_path.resolve())],
    "processed_path": str(csv_path.resolve()),
    "dataset_hash": digest,
  }
  manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _force_runs_rollout_ready(candidate_run: dict, baseline_run: dict) -> None:
  shared_hash = str(candidate_run.get("dataset_hash") or baseline_run.get("dataset_hash") or "e2e-shared-hash")
  shared_period = candidate_run.get("period") if isinstance(candidate_run.get("period"), dict) else (
    baseline_run.get("period") if isinstance(baseline_run.get("period"), dict) else {"start": "2024-01-01", "end": "2024-03-31"}
  )
  for row in [candidate_run, baseline_run]:
    row["status"] = "completed"
    row["data_source"] = "binance_public"
    row["dataset_hash"] = shared_hash
    row["period"] = dict(shared_period)
    row["use_orderflow_data"] = True
    row["orderflow_feature_set"] = "orderflow_on"
    row["feature_set"] = "orderflow_on"
    row["fee_snapshot_id"] = row.get("fee_snapshot_id") or "fee-e2e"
    row["funding_snapshot_id"] = row.get("funding_snapshot_id") or "funding-e2e"
    row["fund_allow_trade"] = True
    row["fund_status"] = "ok"
    row["fund_promotion_blocked"] = False

    flags = row.get("flags") if isinstance(row.get("flags"), dict) else {}
    flags["OOS"] = True
    flags["WFA"] = True
    flags["ORDERFLOW_ENABLED"] = True
    flags["ORDERFLOW_FEATURE_SET"] = "orderflow_on"
    flags["FUNDAMENTALS_PROMOTION_BLOCKED"] = False
    row["flags"] = flags

    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    metadata["strict_strategy_id"] = True
    metadata["orderflow_feature_set"] = "orderflow_on"
    metadata["use_orderflow_data"] = True
    row["metadata"] = metadata

    params_json = row.get("params_json") if isinstance(row.get("params_json"), dict) else {}
    params_json["strict_strategy_id"] = True
    params_json["execution_mode"] = "paper"
    params_json["use_orderflow_data"] = True
    params_json["orderflow_feature_set"] = "orderflow_on"
    row["params_json"] = params_json

    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    provenance["strict_strategy_id"] = True
    provenance["orderflow_feature_set"] = "orderflow_on"
    row["provenance"] = provenance

  baseline_metrics = baseline_run.get("metrics") if isinstance(baseline_run.get("metrics"), dict) else {}
  baseline_metrics["trade_count"] = 220
  baseline_metrics["expectancy"] = 10.0
  baseline_metrics["expectancy_usd_per_trade"] = 10.0
  baseline_metrics["max_dd"] = 0.12
  baseline_metrics["winrate"] = 0.53
  baseline_metrics["profit_factor"] = 1.25
  baseline_metrics["sortino"] = 1.95
  baseline_metrics["calmar"] = 1.05
  baseline_metrics["sharpe"] = 1.2
  baseline_metrics["pbo"] = 0.02
  baseline_metrics["dsr"] = 1.0
  baseline_run["metrics"] = baseline_metrics

  baseline_costs = baseline_run.get("costs_breakdown") if isinstance(baseline_run.get("costs_breakdown"), dict) else {}
  baseline_costs["gross_pnl_total"] = 2000.0
  baseline_costs["total_cost"] = 520.0
  baseline_costs["net_pnl_total"] = 1480.0
  baseline_costs["net_pnl"] = 1480.0
  baseline_run["costs_breakdown"] = baseline_costs

  candidate_metrics = candidate_run.get("metrics") if isinstance(candidate_run.get("metrics"), dict) else {}
  candidate_metrics["trade_count"] = 240
  candidate_metrics["expectancy"] = 12.0
  candidate_metrics["expectancy_usd_per_trade"] = 12.0
  candidate_metrics["max_dd"] = 0.11
  candidate_metrics["winrate"] = 0.56
  candidate_metrics["profit_factor"] = 1.45
  candidate_metrics["sortino"] = 2.35
  candidate_metrics["calmar"] = 1.35
  candidate_metrics["sharpe"] = 1.45
  candidate_metrics["pbo"] = 0.02
  candidate_metrics["dsr"] = 1.08
  candidate_run["metrics"] = candidate_metrics

  candidate_costs = candidate_run.get("costs_breakdown") if isinstance(candidate_run.get("costs_breakdown"), dict) else {}
  candidate_costs["gross_pnl_total"] = 2200.0
  candidate_costs["total_cost"] = 480.0
  candidate_costs["net_pnl_total"] = 1720.0
  candidate_costs["net_pnl"] = 1720.0
  candidate_run["costs_breakdown"] = candidate_costs


def test_event_backtest_engine_runs_for_crypto_forex_equities(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  user_data_dir = Path(module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")
  _seed_local_backtest_dataset(user_data_dir, "forex", "EURUSD", source="dukascopy", include_bid_ask=True)
  _seed_local_backtest_dataset(user_data_dir, "equities", "AAPL", source="alpaca")

  runs_to_launch = [
    {"market": "crypto", "symbol": "BTCUSDT", "timeframe": "5m"},
    {"market": "forex", "symbol": "EURUSD", "timeframe": "10m"},
    {"market": "equities", "symbol": "AAPL", "timeframe": "15m"},
  ]

  for cfg in runs_to_launch:
    res = client.post(
      "/api/v1/backtests/run",
      headers=headers,
      json={
        "strategy_id": "trend_pullback_orderflow_confirm_v1",
        "market": cfg["market"],
        "symbol": cfg["symbol"],
        "timeframe": cfg["timeframe"],
        "start": "2024-01-01",
        "end": "2024-01-06",
        "costs": {
          "fees_bps": 5.0,
          "spread_bps": 4.0,
          "slippage_bps": 2.0,
          "funding_bps": 1.0,
          "rollover_bps": 0.5,
        },
        "validation_mode": "walk-forward",
      },
    )
    assert res.status_code == 200, res.text
    run = res.json()["run"]
    assert run["market"] == cfg["market"]
    assert run["symbol"] == cfg["symbol"]
    assert run["timeframe"] == cfg["timeframe"]
    assert run["data_source"] in {"binance_public", "dukascopy", "alpaca"}
    assert run["dataset_hash"]
    assert "costs_breakdown" in run
    assert "total_entries" in run["metrics"]
    assert run["artifacts_local"]["report_json_local"].endswith(".json")
    if cfg["market"] == "equities":
      assert run["fund_allow_trade"] is True
      assert run["fund_status"] == "UNKNOWN"
      assert run["fund_promotion_blocked"] is True
      assert run["fundamentals_quality"] == "ohlc_only"
      assert "fundamentals_missing" in list((run.get("metadata") or {}).get("warnings") or [])

  status = client.get("/api/v1/data/status", headers=headers)
  assert status.status_code == 200
  payload = status.json()
  assert "available" in payload and "missing" in payload


def test_strategy_registry_seeds_knowledge_pack_and_patch_flags(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.get("/api/v1/strategies", headers=headers)
  assert res.status_code == 200, res.text
  rows = res.json()
  ids = {row["id"] for row in rows}
  assert {"trend_pullback_orderflow_v2", "breakout_volatility_v2", "meanreversion_range_v2", "trend_scanning_regime_v2", "defensive_liquidity_v2"} <= ids

  krow = next(row for row in rows if row["id"] == "trend_pullback_orderflow_v2")
  assert krow["source"] == "knowledge"
  assert isinstance(krow["allow_learning"], bool)
  assert isinstance(krow["enabled_for_trading"], bool)

  patch_res = client.patch(
    "/api/v1/strategies/trend_pullback_orderflow_v2",
    headers=headers,
    json={"allow_learning": False, "enabled_for_trading": True, "is_primary": True},
  )
  assert patch_res.status_code == 200, patch_res.text
  patched = patch_res.json()["strategy"]
  assert patched["allow_learning"] is False
  assert patched["is_primary"] is True

  patch_other = client.patch(
    "/api/v1/strategies/breakout_volatility_v2",
    headers=headers,
    json={"is_primary": True, "enabled_for_trading": True},
  )
  assert patch_other.status_code == 200, patch_other.text
  rows2 = client.get("/api/v1/strategies", headers=headers).json()
  primary_rows = [row for row in rows2 if row.get("is_primary")]
  assert len(primary_rows) == 1
  assert primary_rows[0]["id"] == "breakout_volatility_v2"

  enabled_ids = [row["id"] for row in rows2 if row.get("enabled_for_trading")]
  assert enabled_ids
  for sid in enabled_ids[:-1]:
    r = client.patch(f"/api/v1/strategies/{sid}", headers=headers, json={"enabled_for_trading": False, "status": "disabled"})
    assert r.status_code == 200, r.text
  last_disable = client.patch(
    f"/api/v1/strategies/{enabled_ids[-1]}",
    headers=headers,
    json={"enabled_for_trading": False, "status": "disabled"},
  )
  assert last_disable.status_code == 400
  assert "al menos 1 estrategia activa" in last_disable.json()["detail"]


def test_strategy_kpis_endpoints_and_run_provenance(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  runs_res = client.get("/api/v1/backtests/runs", headers=headers)
  assert runs_res.status_code == 200
  runs = runs_res.json()
  assert runs
  first_run = runs[0]
  assert "provenance" in first_run
  assert first_run["provenance"]["dataset_hash"]
  assert "costs_used" in first_run["provenance"]
  prov_rows = module.store.registry.list_run_provenance(first_run["strategy_id"])
  assert any(row["run_id"] == first_run["id"] for row in prov_rows)

  table_res = client.get("/api/v1/strategies/kpis?mode=backtest&from=2024-01-01&to=2026-12-31", headers=headers)
  assert table_res.status_code == 200, table_res.text
  table = table_res.json()
  assert table["items"]
  match = next(item for item in table["items"] if item["strategy_id"] == first_run["strategy_id"])
  assert "kpis" in match and "trade_count" in match["kpis"]
  assert "expectancy_unit" in match["kpis"]

  single_res = client.get(f"/api/v1/strategies/{first_run['strategy_id']}/kpis?mode=backtest", headers=headers)
  assert single_res.status_code == 200, single_res.text
  assert "kpis" in single_res.json()

  regime_res = client.get(f"/api/v1/strategies/{first_run['strategy_id']}/kpis_by_regime?mode=backtest", headers=headers)
  assert regime_res.status_code == 200, regime_res.text
  regimes = regime_res.json()["regimes"]
  assert {"trend", "range", "high_vol", "toxic"} <= set(regimes.keys())


def test_runs_batches_catalog_endpoints_smoke(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  _seed_local_backtest_dataset(Path(module.USER_DATA_DIR), "crypto", "BTCUSDT", source="binance_public")

  bots_res = client.get("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0", headers=headers)
  assert bots_res.status_code == 200, bots_res.text
  bot_items = bots_res.json()["items"]
  assert bot_items
  first_bot_id = str(bot_items[0]["id"])

  runs_list = client.get("/api/v1/runs", headers=headers)
  assert runs_list.status_code == 200, runs_list.text
  items = runs_list.json()["items"]
  assert items
  first = items[0]
  assert str(first["run_id"]).startswith("BT-")
  assert "related_bot_ids" in first
  assert "related_bots" in first

  bot_runs = client.get(f"/api/v1/runs?bot_id={first_bot_id}", headers=headers)
  assert bot_runs.status_code == 200, bot_runs.text
  bot_runs_payload = bot_runs.json()
  assert isinstance(bot_runs_payload["items"], list)
  assert bot_runs_payload["count"] >= len(bot_runs_payload["items"])
  for row in bot_runs_payload["items"]:
    assert first_bot_id in row.get("related_bot_ids", [])

  detail = client.get(f"/api/v1/runs/{first['run_id']}", headers=headers)
  assert detail.status_code == 200, detail.text
  detail_payload = detail.json()
  assert detail_payload["run_id"] == first["run_id"]
  assert "related_bot_ids" in detail_payload
  assert "title_structured" in detail_payload
  assert "fee_snapshot_id" in detail_payload
  assert "funding_snapshot_id" in detail_payload
  assert isinstance(detail_payload.get("slippage_model_params"), dict)
  assert isinstance(detail_payload.get("spread_model_params"), dict)

  patched = client.patch(
    f"/api/v1/runs/{first['run_id']}",
    headers=headers,
    json={"alias": "favorito test", "tags": ["test", "wfa"], "pinned": True},
  )
  assert patched.status_code == 200, patched.text
  assert patched.json()["run"]["alias"] == "favorito test"

  compare = client.get(f"/api/v1/compare?r={first['run_id']}", headers=headers)
  assert compare.status_code == 200, compare.text
  assert compare.json()["count"] >= 1

  rankings = client.get("/api/v1/rankings?preset=balanceado&min_trades=1&limit=20", headers=headers)
  assert rankings.status_code == 200, rankings.text
  assert isinstance(rankings.json()["items"], list)

  bulk_archive = client.post(
    "/api/v1/runs/bulk",
    headers=headers,
    json={"action": "archive", "run_ids": [first["run_id"]]},
  )
  assert bulk_archive.status_code == 200, bulk_archive.text
  assert bulk_archive.json()["count"] >= 1

  bulk_delete = client.post(
    "/api/v1/runs/bulk",
    headers=headers,
    json={"action": "delete", "run_ids": [first["run_id"]]},
  )
  assert bulk_delete.status_code == 200, bulk_delete.text
  assert bulk_delete.json()["deleted_count"] >= 1

  after_delete = client.get("/api/v1/runs", headers=headers)
  assert after_delete.status_code == 200
  assert all(row["run_id"] != first["run_id"] for row in after_delete.json()["items"])

  batch_create_reject = client.post(
    "/api/v1/batches",
    headers=headers,
    json={
      "objective": "Smoke batch",
      "dataset_source": "synthetic",
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-06-01",
      "max_variants_per_strategy": 1,
      "max_folds": 1,
      "train_days": 60,
      "test_days": 30,
      "top_n": 1,
      "seed": 7,
    },
  )
  assert batch_create_reject.status_code == 400
  assert "solo acepta datos reales" in batch_create_reject.json()["detail"].lower()

  batch_create = client.post(
    "/api/v1/batches",
    headers=headers,
    json={
      "objective": "Smoke batch",
      "dataset_source": "auto",
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-06-01",
      "max_variants_per_strategy": 1,
      "max_folds": 1,
      "train_days": 60,
      "test_days": 30,
      "top_n": 1,
      "seed": 7,
    },
  )
  assert batch_create.status_code == 200, batch_create.text
  batch_id = batch_create.json()["batch_id"]
  assert str(batch_id).startswith("BX-")

  batch_detail = client.get(f"/api/v1/batches/{batch_id}", headers=headers)
  assert batch_detail.status_code == 200, batch_detail.text
  assert batch_detail.json()["batch_id"] == batch_id
  cfg_snapshot = (batch_detail.json().get("config") or {})
  assert isinstance(cfg_snapshot.get("policy_snapshot_summary"), dict)
  assert cfg_snapshot["policy_snapshot_summary"].get("pbo_reject_if_gt") == 0.05


def test_runs_validate_and_promote_endpoints_smoke(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  runs_res = client.get("/api/v1/runs?limit=20", headers=headers)
  assert runs_res.status_code == 200, runs_res.text
  items = runs_res.json()["items"]
  assert items
  candidate_id = str(items[0]["run_id"])

  validate_res = client.post(
    f"/api/v1/runs/{candidate_id}/validate_promotion",
    headers=headers,
    json={"target_mode": "paper"},
  )
  assert validate_res.status_code == 200, validate_res.text
  validate_payload = validate_res.json()
  assert "constraints" in validate_payload
  assert "offline_gates" in validate_payload
  assert "compare_vs_baseline" in validate_payload
  assert "rollout_ready" in validate_payload
  checks = validate_payload["constraints"]["checks"]
  check_ids = {row["id"] for row in checks}
  assert "cost_snapshots_present" in check_ids
  assert "fundamentals_allow_trade" in check_ids
  assert "strict_strategy_id_non_demo" in check_ids

  promote_res = client.post(
    f"/api/v1/runs/{candidate_id}/promote",
    headers=headers,
    json={"target_mode": "paper", "note": "smoke"},
  )
  assert promote_res.status_code in {200, 400}, promote_res.text
  promote_payload = promote_res.json()
  if promote_res.status_code == 200:
    assert promote_payload.get("promoted") is True
    assert isinstance((promote_payload.get("rollout") or {}).get("state"), dict)
  else:
    assert promote_payload.get("ok") is False


def test_e2e_critical_flow_login_backtest_validate_promote_rollout(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")

  strategy_id = client.get("/api/v1/strategies", headers=headers).json()[0]["id"]
  common_payload = {
    "strategy_id": strategy_id,
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "start": "2024-01-01",
    "end": "2024-03-31",
    "validation_mode": "walk-forward",
    "use_orderflow_data": True,
    "strict_strategy_id": True,
  }

  baseline_res = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={**common_payload, "costs_model": {"fees_bps": 18.0, "spread_bps": 14.0, "slippage_bps": 10.0, "funding_bps": 1.0}},
  )
  assert baseline_res.status_code == 200, baseline_res.text
  baseline_id = str(baseline_res.json()["run_id"])

  candidate_res = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={**common_payload, "costs_model": {"fees_bps": 5.0, "spread_bps": 4.0, "slippage_bps": 3.0, "funding_bps": 0.5}},
  )
  assert candidate_res.status_code == 200, candidate_res.text
  candidate_id = str(candidate_res.json()["run_id"])

  runs = module.store.load_runs()
  run_by_id = {str(row.get("id") or ""): row for row in runs if isinstance(row, dict)}
  assert candidate_id in run_by_id
  assert baseline_id in run_by_id
  _force_runs_rollout_ready(run_by_id[candidate_id], run_by_id[baseline_id])
  module.store.save_runs(runs)

  validate_res = client.post(
    f"/api/v1/runs/{candidate_id}/validate_promotion",
    headers=headers,
    json={"target_mode": "paper", "baseline_run_id": baseline_id},
  )
  assert validate_res.status_code == 200, validate_res.text
  validate_payload = validate_res.json()
  assert validate_payload.get("rollout_ready") is True

  promote_res = client.post(
    f"/api/v1/runs/{candidate_id}/promote",
    headers=headers,
    json={"target_mode": "paper", "baseline_run_id": baseline_id, "note": "e2e critical flow"},
  )
  assert promote_res.status_code == 200, promote_res.text
  promote_payload = promote_res.json()
  assert promote_payload.get("promoted") is True
  rollout_state = (promote_payload.get("rollout") or {}).get("state") or {}
  assert str(rollout_state.get("state") or "") == "OFFLINE_GATES_PASSED"

  advance_res = client.post("/api/v1/rollout/advance", headers=headers, json={"note": "e2e advance"})
  assert advance_res.status_code == 200, advance_res.text
  assert str(((advance_res.json().get("state") or {}).get("state") or "")) == "PAPER_SOAK"


def test_learning_recommend_uses_only_allow_learning_pool(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  settings = module.store.load_settings()
  settings["learning"]["enabled"] = True
  module.store.save_settings(settings)

  rows = client.get("/api/v1/strategies", headers=headers).json()
  target_id = "defensive_liquidity_v2"
  for row in rows:
    patch_res = client.patch(
      f"/api/v1/strategies/{row['id']}",
      headers=headers,
      json={"allow_learning": row["id"] == target_id},
    )
    assert patch_res.status_code == 200, patch_res.text

  rec_res = client.post("/api/v1/learning/recommend", headers=headers, json={"mode": "paper"})
  assert rec_res.status_code == 200, rec_res.text
  rec = rec_res.json()
  assert rec["active_strategy_id"] == target_id

  empty_pool = client.patch(f"/api/v1/strategies/{target_id}", headers=headers, json={"allow_learning": False})
  assert empty_pool.status_code == 200, empty_pool.text
  rec_fail = client.post("/api/v1/learning/recommend", headers=headers, json={"mode": "paper"})
  assert rec_fail.status_code == 400
  assert "Pool de aprendizaje vacio" in rec_fail.json()["detail"]


def test_runtime_recommendations_are_visible_in_listing_endpoint(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  settings = module.store.load_settings()
  settings["learning"]["enabled"] = True
  module.store.save_settings(settings)

  rec_res = client.post("/api/v1/learning/recommend", headers=headers, json={"mode": "paper"})
  assert rec_res.status_code == 200, rec_res.text
  rec_id = rec_res.json()["id"]

  listing = client.get("/api/v1/learning/recommendations", headers=headers)
  assert listing.status_code == 200, listing.text
  items = listing.json()
  row = next((item for item in items if item["id"] == rec_id), None)
  assert row is not None
  assert row.get("recommendation_source") == "runtime"

  detail = client.get(f"/api/v1/learning/recommendations/{rec_id}", headers=headers)
  assert detail.status_code == 200, detail.text
  assert detail.json()["id"] == rec_id


def test_bots_multi_instance_endpoints(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  list_res = client.get("/api/v1/bots", headers=headers)
  assert list_res.status_code == 200, list_res.text
  payload = list_res.json()
  assert isinstance(payload.get("items"), list)
  assert payload["items"]
  assert payload["items"][0]["id"].startswith("BOT-")
  assert "metrics" in payload["items"][0]
  initial_total = int(payload.get("total") or 0)

  strategies = client.get("/api/v1/strategies", headers=headers).json()
  pool_ids = [row["id"] for row in strategies[:2]]
  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "name": "AutoBot Testnet",
      "engine": "bandit_ucb1",
      "mode": "testnet",
      "status": "paused",
      "pool_strategy_ids": pool_ids,
      "universe": ["BTCUSDT"],
    },
  )
  assert create_res.status_code == 200, create_res.text
  bot = create_res.json()["bot"]
  assert bot["mode"] == "testnet"
  assert bot["status"] == "paused"
  assert bot["id"].startswith("BOT-")

  patch_res = client.patch(
    f"/api/v1/bots/{bot['id']}",
    headers=headers,
    json={"status": "active", "mode": "shadow", "pool_strategy_ids": pool_ids[:1]},
  )
  assert patch_res.status_code == 200, patch_res.text
  patched = patch_res.json()["bot"]
  assert patched["status"] == "active"
  assert patched["mode"] == "shadow"
  assert len(patched["pool_strategy_ids"]) == 1

  bulk_res = client.post(
    "/api/v1/bots/bulk-patch",
    headers=headers,
    json={"ids": [bot["id"]], "mode": "paper", "status": "paused"},
  )
  assert bulk_res.status_code == 200, bulk_res.text
  bulk_payload = bulk_res.json()
  assert bulk_payload["updated_count"] == 1
  assert bulk_payload["error_count"] == 0
  updated_bot = next((row for row in bulk_payload["updated"] if row["id"] == bot["id"]), None)
  assert updated_bot is not None
  assert updated_bot["mode"] == "paper"
  assert updated_bot["status"] == "paused"

  delete_res = client.delete(f"/api/v1/bots/{bot['id']}", headers=headers)
  assert delete_res.status_code == 200, delete_res.text
  delete_payload = delete_res.json()
  assert delete_payload["ok"] is True
  assert str((delete_payload.get("deleted") or {}).get("id") or "") == bot["id"]
  assert int(delete_payload.get("remaining") or 0) == initial_total


def test_bots_overview_cache_hit_and_invalidation_on_create(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  call_counter = {"n": 0}
  original = module.store.list_bot_instances

  def _wrapped_list_bot_instances(*, recommendations=None, include_recent_logs=None, recent_logs_per_bot=None, overview_perf=None):
    call_counter["n"] += 1
    return original(
      recommendations=recommendations,
      include_recent_logs=include_recent_logs,
      recent_logs_per_bot=recent_logs_per_bot,
      overview_perf=overview_perf,
    )

  monkeypatch.setattr(module.store, "list_bot_instances", _wrapped_list_bot_instances)

  first = client.get("/api/v1/bots", headers=headers)
  assert first.status_code == 200, first.text
  first_total = int(first.json().get("total") or 0)
  assert call_counter["n"] == 1

  second = client.get("/api/v1/bots", headers=headers)
  assert second.status_code == 200, second.text
  assert int(second.json().get("total") or 0) == first_total
  assert call_counter["n"] == 1

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={"name": "AutoBot Cache", "mode": "paper", "status": "active"},
  )
  assert create_res.status_code == 200, create_res.text
  assert call_counter["n"] == 2

  third = client.get("/api/v1/bots", headers=headers)
  assert third.status_code == 200, third.text
  assert int(third.json().get("total") or 0) == first_total + 1
  assert call_counter["n"] == 3


def test_bots_overview_perf_headers_and_debug_payload(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  first = client.get("/api/v1/bots?debug_perf=true", headers=headers)
  assert first.status_code == 200, first.text
  perf = first.json().get("perf") or {}
  assert perf.get("cache") in {"hit", "miss"}
  assert isinstance(perf.get("latency_ms"), (int, float))
  overview_perf = perf.get("overview") or {}
  assert isinstance(overview_perf, dict)
  assert isinstance(overview_perf.get("total_ms"), (int, float))
  assert "X-RTLAB-Bots-Overview-Cache" in first.headers
  assert "X-RTLAB-Bots-Overview-MS" in first.headers
  assert "X-RTLAB-Bots-Count" in first.headers
  assert first.headers.get("X-RTLAB-Bots-Recent-Logs") in {"enabled", "disabled"}

  second = client.get("/api/v1/bots?debug_perf=true", headers=headers)
  assert second.status_code == 200, second.text
  assert (second.json().get("perf") or {}).get("cache") == "hit"


def test_bots_overview_supports_recent_logs_query_overrides_and_cache_key(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  call_counter = {"n": 0}
  original = module.store.list_bot_instances

  def _wrapped_list_bot_instances(*, recommendations=None, include_recent_logs=None, recent_logs_per_bot=None, overview_perf=None):
    call_counter["n"] += 1
    return original(
      recommendations=recommendations,
      include_recent_logs=include_recent_logs,
      recent_logs_per_bot=recent_logs_per_bot,
      overview_perf=overview_perf,
    )

  monkeypatch.setattr(module.store, "list_bot_instances", _wrapped_list_bot_instances)

  first = client.get("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0&debug_perf=true", headers=headers)
  assert first.status_code == 200, first.text
  assert call_counter["n"] == 1
  assert first.headers.get("X-RTLAB-Bots-Recent-Logs") == "disabled"
  assert first.headers.get("X-RTLAB-Bots-Recent-Logs-Per-Bot") == "0"
  assert (first.json().get("perf") or {}).get("cache") == "miss"

  second = client.get("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0&debug_perf=true", headers=headers)
  assert second.status_code == 200, second.text
  assert call_counter["n"] == 1
  assert (second.json().get("perf") or {}).get("cache") == "hit"

  third = client.get("/api/v1/bots?recent_logs=true&recent_logs_per_bot=1&debug_perf=true", headers=headers)
  assert third.status_code == 200, third.text
  assert call_counter["n"] == 2
  assert third.headers.get("X-RTLAB-Bots-Recent-Logs") == "enabled"
  assert third.headers.get("X-RTLAB-Bots-Recent-Logs-Per-Bot") == "1"
  assert (third.json().get("perf") or {}).get("cache") == "miss"


def test_bots_overview_auto_disables_recent_logs_for_large_default_polling_but_keeps_explicit_override(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT", "1")
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  strategies = client.get("/api/v1/strategies", headers=headers)
  assert strategies.status_code == 200, strategies.text
  strategy_id = str(strategies.json()[0]["id"])
  create = client.post(
    "/api/v1/bots",
    headers=headers,
    json={
      "name": "bot-auto-disable-logs",
      "engine": "bandit_thompson",
      "mode": "paper",
      "status": "active",
      "pool_strategy_ids": [strategy_id],
      "universe": ["BTCUSDT"],
      "notes": "auto-disable logs test",
    },
  )
  assert create.status_code == 200, create.text

  module._invalidate_bots_overview_cache()
  default_poll = client.get("/api/v1/bots?debug_perf=true", headers=headers)
  assert default_poll.status_code == 200, default_poll.text
  assert default_poll.headers.get("X-RTLAB-Bots-Recent-Logs") == "disabled"
  default_perf = default_poll.json().get("perf") or {}
  assert bool(default_perf.get("logs_auto_disabled")) is True
  assert int(default_perf.get("bots_count") or 0) >= 2

  module._invalidate_bots_overview_cache()
  explicit = client.get("/api/v1/bots?recent_logs=true&debug_perf=true", headers=headers)
  assert explicit.status_code == 200, explicit.text
  assert explicit.headers.get("X-RTLAB-Bots-Recent-Logs") == "enabled"
  explicit_perf = explicit.json().get("perf") or {}
  assert bool(explicit_perf.get("logs_auto_disabled")) is False


def test_bots_overview_only_computes_kpis_for_strategies_in_pool(tmp_path: Path, monkeypatch) -> None:
  module, _client = _build_app(tmp_path, monkeypatch)
  call_counter = {"n": 0}
  original = module.store._aggregate_strategy_kpis

  def _wrapped_aggregate_strategy_kpis(runs):
    call_counter["n"] += 1
    return original(runs)

  monkeypatch.setattr(module.store, "_aggregate_strategy_kpis", _wrapped_aggregate_strategy_kpis)

  bots = [
    {"id": "BOT-A", "mode": "paper", "pool_strategy_ids": ["S1"]},
    {"id": "BOT-B", "mode": "testnet", "pool_strategy_ids": ["S2"]},
  ]
  strategies = [
    {"id": "S1"},
    {"id": "S2"},
    {"id": "S3"},  # not referenced by any bot pool
  ]
  perf: dict = {}

  overview = module.store.get_bots_overview(
    bots=bots,
    strategies=strategies,
    runs=[],
    recommendations=[],
    include_recent_logs=False,
    perf=perf,
  )
  assert "BOT-A" in overview
  assert "BOT-B" in overview
  assert call_counter["n"] == 8  # 2 strategies in pool * 4 modes
  stage = (perf.get("overview") or {})
  assert stage.get("strategies_in_pool_count") == 2


def test_logs_has_bot_ref_materialized_and_bots_recent_logs_ignore_unrelated(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  bots_payload = client.get("/api/v1/bots", headers=headers)
  assert bots_payload.status_code == 200, bots_payload.text
  bot_id = str((bots_payload.json().get("items") or [])[0]["id"])

  log_unrelated = module.store.add_log(
    event_type="health",
    severity="info",
    module="tests",
    message="MARK_UNRELATED_NO_BOT_REF",
    related_ids=[],
    payload={"probe": "x"},
  )
  log_related_by_related_ids = module.store.add_log(
    event_type="status",
    severity="info",
    module="tests",
    message="MARK_RELATED_IDS_BOT_REF",
    related_ids=[bot_id],
    payload={"probe": "y"},
  )
  log_related_by_payload = module.store.add_log(
    event_type="status",
    severity="info",
    module="tests",
    message="MARK_PAYLOAD_BOT_REF",
    related_ids=[],
    payload={"bot_id": bot_id},
  )

  with module.store._connect() as conn:
    rows = conn.execute(
      "SELECT id, has_bot_ref FROM logs WHERE id IN (?, ?, ?)",
      (log_unrelated, log_related_by_related_ids, log_related_by_payload),
    ).fetchall()
  has_by_id = {int(row["id"]): int(row["has_bot_ref"]) for row in rows}
  assert has_by_id[log_unrelated] == 0
  assert has_by_id[log_related_by_related_ids] == 1
  assert has_by_id[log_related_by_payload] == 1

  module._invalidate_bots_overview_cache()
  overview_res = client.get("/api/v1/bots?debug_perf=true", headers=headers)
  assert overview_res.status_code == 200, overview_res.text
  payload = overview_res.json()
  stage = (((payload.get("perf") or {}).get("overview")) or {})
  assert stage.get("logs_prefilter_has_bot_ref") is True

  row = next(item for item in (payload.get("items") or []) if str(item.get("id")) == bot_id)
  messages = [str(entry.get("message") or "") for entry in (row.get("recent_logs") or [])]
  assert "MARK_RELATED_IDS_BOT_REF" in messages
  assert "MARK_PAYLOAD_BOT_REF" in messages
  assert "MARK_UNRELATED_NO_BOT_REF" not in messages


def test_log_bot_refs_table_is_populated_and_used_in_overview(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  first_list = client.get("/api/v1/bots", headers=headers)
  assert first_list.status_code == 200, first_list.text
  bot1_id = str((first_list.json().get("items") or [])[0]["id"])

  create_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={"name": "AutoBot RefTable", "mode": "paper", "status": "active"},
  )
  assert create_res.status_code == 200, create_res.text
  bot2_id = str((create_res.json().get("bot") or {}).get("id") or "")
  assert bot2_id

  log_multi = module.store.add_log(
    event_type="status",
    severity="info",
    module="tests",
    message="MARK_MULTI_BOT_REFS",
    related_ids=[bot1_id],
    payload={"bot_ids": [bot2_id]},
  )

  with module.store._connect() as conn:
    ref_rows = conn.execute(
      "SELECT bot_id FROM log_bot_refs WHERE log_id = ? ORDER BY bot_id ASC",
      (log_multi,),
    ).fetchall()
  refs = [str(row["bot_id"] or "") for row in ref_rows]
  assert bot1_id in refs
  assert bot2_id in refs

  module._invalidate_bots_overview_cache()
  overview_res = client.get("/api/v1/bots?debug_perf=true", headers=headers)
  assert overview_res.status_code == 200, overview_res.text
  payload = overview_res.json()
  stage = (((payload.get("perf") or {}).get("overview")) or {})
  assert stage.get("logs_prefilter_mode") == "log_bot_refs"

  items = payload.get("items") or []
  row1 = next(item for item in items if str(item.get("id")) == bot1_id)
  row2 = next(item for item in items if str(item.get("id")) == bot2_id)
  msgs1 = [str(entry.get("message") or "") for entry in (row1.get("recent_logs") or [])]
  msgs2 = [str(entry.get("message") or "") for entry in (row2.get("recent_logs") or [])]
  assert "MARK_MULTI_BOT_REFS" in msgs1
  assert "MARK_MULTI_BOT_REFS" in msgs2


def test_bots_overview_prefers_exact_bot_experience_over_current_pool(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(module.USER_DATA_DIR)
  _seed_local_backtest_dataset(user_data_dir, "crypto", "BTCUSDT", source="binance_public")

  bots_payload = client.get("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0", headers=headers)
  assert bots_payload.status_code == 200, bots_payload.text
  bot_id = str((bots_payload.json().get("items") or [])[0]["id"])

  strategies = client.get("/api/v1/strategies", headers=headers).json()
  assert strategies
  strategy_id = str(strategies[0]["id"])
  other_strategy_ids = [str(row["id"]) for row in strategies[1:] if str(row.get("id") or "").strip()]

  run_res = client.post(
    "/api/v1/backtests/run",
    headers=headers,
    json={
      "strategy_id": strategy_id,
      "bot_id": bot_id,
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-03-31",
      "validation_mode": "walk-forward",
    },
  )
  assert run_res.status_code == 200, run_res.text

  patch_res = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"pool_strategy_ids": other_strategy_ids[:1]},
  )
  assert patch_res.status_code == 200, patch_res.text

  overview_res = client.get("/api/v1/bots?recent_logs=false&recent_logs_per_bot=0", headers=headers)
  assert overview_res.status_code == 200, overview_res.text
  row = next(item for item in (overview_res.json().get("items") or []) if str(item.get("id") or "") == bot_id)
  metrics = row.get("metrics") or {}
  exp = (metrics.get("experience_by_source") or {}).get("backtest") or {}
  assert metrics.get("experience_history_scope") == "exact_bot_history"
  assert int(exp.get("episode_count") or 0) >= 1
  assert int(exp.get("run_count") or 0) >= 1


def test_bots_overview_scopes_kills_by_bot_and_mode(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  bot1_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={"name": "AutoBot Scope 1", "mode": "paper", "status": "active"},
  )
  assert bot1_res.status_code == 200, bot1_res.text
  bot1_id = bot1_res.json()["bot"]["id"]

  bot2_res = client.post(
    "/api/v1/bots",
    headers=headers,
    json={"name": "AutoBot Scope 2", "mode": "paper", "status": "active"},
  )
  assert bot2_res.status_code == 200, bot2_res.text
  bot2_id = bot2_res.json()["bot"]["id"]

  module.store.add_log(
    event_type="breaker_triggered",
    severity="warn",
    module="risk",
    message="kill bot1 paper",
    related_ids=[bot1_id],
    payload={"bot_id": bot1_id, "mode": "paper", "reason": "test", "symbol": "BTCUSDT"},
  )
  module.store.add_log(
    event_type="breaker_triggered",
    severity="warn",
    module="risk",
    message="kill bot1 unknown",
    related_ids=[bot1_id],
    payload={"bot_id": bot1_id, "reason": "missing_mode"},
  )
  module.store.add_log(
    event_type="breaker_triggered",
    severity="warn",
    module="risk",
    message="kill bot2 testnet",
    related_ids=[bot2_id],
    payload={"bot_id": bot2_id, "mode": "testnet", "reason": "test"},
  )

  list_res = client.get("/api/v1/bots", headers=headers)
  assert list_res.status_code == 200, list_res.text
  items = list_res.json()["items"]
  row1 = next(row for row in items if row["id"] == bot1_id)
  row2 = next(row for row in items if row["id"] == bot2_id)

  assert row1["metrics"]["kills_by_mode"]["paper"] == 1
  assert row1["metrics"]["kills_by_mode"]["unknown"] == 1
  assert row1["metrics"]["kills_total"] == 1
  assert row1["metrics"]["kills_by_mode_24h"]["paper"] == 1
  assert row1["metrics"]["kills_by_mode_24h"]["unknown"] == 1
  assert row1["metrics"]["kills_by_mode_24h"]["testnet"] == 0

  assert row2["metrics"]["kills_by_mode"]["paper"] == 0
  assert row2["metrics"]["kills_by_mode"]["testnet"] == 1
  assert row2["metrics"]["kills_by_mode"]["unknown"] == 0


def test_breaker_events_integrity_endpoint_pass(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS", "24")
  monkeypatch.setenv("BREAKER_EVENTS_UNKNOWN_RATIO_WARN", "0.40")
  monkeypatch.setenv("BREAKER_EVENTS_UNKNOWN_MIN_EVENTS", "4")
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  for _ in range(5):
    module.store.add_log(
      event_type="breaker_triggered",
      severity="warn",
      module="risk",
      message="breaker known",
      related_ids=[],
      payload={"bot_id": "BOT-KNOWN", "mode": "paper", "reason": "test"},
    )
  module.store.add_log(
    event_type="breaker_triggered",
    severity="warn",
    module="risk",
    message="breaker unknown mode",
    related_ids=[],
    payload={"bot_id": "BOT-KNOWN", "reason": "missing_mode"},
  )

  res = client.get("/api/v1/diagnostics/breaker-events?window_hours=24", headers=headers)
  assert res.status_code == 200, res.text
  payload = res.json()

  assert payload["status"] == "PASS"
  assert payload["ok"] is True
  assert payload["window_hours"] == 24
  assert (payload.get("thresholds") or {}).get("unknown_ratio_warn") == 0.4
  assert (payload.get("thresholds") or {}).get("min_events_warn") == 4
  assert int((payload.get("overall") or {}).get("total") or 0) >= 6
  assert int((payload.get("overall") or {}).get("unknown_any_total") or 0) >= 1
  assert float((payload.get("overall") or {}).get("unknown_any_ratio") or 0.0) < 0.4
  assert payload.get("warnings") == []


def test_breaker_events_integrity_endpoint_no_data_non_strict_ok(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS", "24")
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.get("/api/v1/diagnostics/breaker-events?window_hours=24&strict=false", headers=headers)
  assert res.status_code == 200, res.text
  payload = res.json()
  assert payload["status"] == "NO_DATA"
  assert payload["strict_mode"] is False
  assert payload["ok"] is True


def test_breaker_events_integrity_endpoint_no_data_strict_fail_closed_by_default(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS", "24")
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.get("/api/v1/diagnostics/breaker-events?window_hours=24", headers=headers)
  assert res.status_code == 200, res.text
  payload = res.json()
  assert payload["status"] == "NO_DATA"
  assert payload["strict_mode"] is True
  assert payload["ok"] is False


def test_breaker_events_integrity_endpoint_warn_when_unknown_ratio_high(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS", "24")
  monkeypatch.setenv("BREAKER_EVENTS_UNKNOWN_RATIO_WARN", "0.20")
  monkeypatch.setenv("BREAKER_EVENTS_UNKNOWN_MIN_EVENTS", "4")
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  for _ in range(3):
    module.store.add_log(
      event_type="breaker_triggered",
      severity="warn",
      module="risk",
      message="breaker known",
      related_ids=[],
      payload={"bot_id": "BOT-KNOWN", "mode": "paper", "reason": "test"},
    )
  for _ in range(3):
    module.store.add_log(
      event_type="breaker_triggered",
      severity="warn",
      module="risk",
      message="breaker unknown",
      related_ids=[],
      payload={"reason": "missing_bot_and_mode"},
    )

  res = client.get("/api/v1/diagnostics/breaker-events?window_hours=24", headers=headers)
  assert res.status_code == 200, res.text
  payload = res.json()

  assert payload["status"] == "WARN"
  assert payload["ok"] is False
  assert int((payload.get("overall") or {}).get("total") or 0) >= 6
  assert float((payload.get("overall") or {}).get("unknown_any_ratio") or 0.0) > 0.2
  warnings = payload.get("warnings") or []
  assert warnings
  assert any("overall:" in str(msg) for msg in warnings)


def test_alerts_include_operational_alerts_for_drift_slippage_api_and_breaker(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  monkeypatch.setattr(
    module.learning_service,
    "compute_drift",
    lambda *, settings, runs: {"drift": True, "algo": "adwin", "research_loop_triggered": True},
  )
  monkeypatch.setattr(
    module.runtime_bridge,
    "execution_metrics_snapshot",
    lambda: {
      "series": [],
      "maker_ratio": 0.4,
      "fill_ratio": 0.65,
      "latency_ms_p95": 120.0,
      "rate_limit_hits": 2,
      "api_errors": 4,
      "avg_slippage": 11.5,
      "p95_slippage": 14.2,
      "notes": [],
    },
  )

  res = client.get("/api/v1/alerts", headers=headers)
  assert res.status_code == 200, res.text
  items = res.json()
  ops_types = {str(row.get("type") or "") for row in items if str(row.get("id") or "").startswith("ops_")}
  assert "ops_drift" in ops_types
  assert "ops_slippage_anomaly" in ops_types
  assert "ops_api_errors" in ops_types
  assert "ops_breaker_integrity" in ops_types


def test_alerts_operational_alerts_clear_when_runtime_recovers(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  state = module.store.load_bot_state()
  state.update(
    {
      "runtime_engine": "real",
      "running": True,
      "killed": False,
      "bot_status": "RUNNING",
      "runtime_contract_version": "runtime_snapshot_v1",
      "runtime_telemetry_source": "runtime_loop_v1",
      "runtime_loop_alive": True,
      "runtime_executor_connected": True,
      "runtime_reconciliation_ok": True,
      "runtime_heartbeat_at": module.utc_now_iso(),
      "runtime_last_reconcile_at": module.utc_now_iso(),
    }
  )
  module.store.save_bot_state(state)

  monkeypatch.setattr(
    module.learning_service,
    "compute_drift",
    lambda *, settings, runs: {"drift": False, "algo": "adwin", "research_loop_triggered": False},
  )
  monkeypatch.setattr(
    module.runtime_bridge,
    "execution_metrics_snapshot",
    lambda: {
      "series": [],
      "maker_ratio": 0.55,
      "fill_ratio": 0.8,
      "latency_ms_p95": 45.0,
      "rate_limit_hits": 0,
      "api_errors": 0,
      "avg_slippage": 1.2,
      "p95_slippage": 1.8,
      "notes": [],
    },
  )

  module.store.add_log(
    event_type="breaker_triggered",
    severity="warn",
    module="risk",
    message="breaker known",
    related_ids=["BOT-ALERT-OK"],
    payload={"bot_id": "BOT-ALERT-OK", "mode": "paper", "reason": "test"},
  )

  res = client.get("/api/v1/alerts", headers=headers)
  assert res.status_code == 200, res.text
  items = res.json()
  ops_types = {str(row.get("type") or "") for row in items if str(row.get("id") or "").startswith("ops_")}
  assert "ops_drift" not in ops_types
  assert "ops_slippage_anomaly" not in ops_types
  assert "ops_api_errors" not in ops_types
  assert "ops_breaker_integrity" not in ops_types


def test_bots_live_mode_blocked_by_gates(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  # En entorno de tests no hay keys live/testnet, por lo que LIVE debe quedar bloqueado por gates.
  create_live = client.post(
    "/api/v1/bots",
    headers=headers,
    json={"name": "AutoBot Live", "mode": "live", "status": "active"},
  )
  assert create_live.status_code == 400, create_live.text
  assert "LIVE" in str(create_live.json().get("detail") or "")

  create_paper = client.post(
    "/api/v1/bots",
    headers=headers,
    json={"name": "AutoBot Base", "mode": "paper", "status": "active"},
  )
  assert create_paper.status_code == 200, create_paper.text
  bot_id = create_paper.json()["bot"]["id"]

  patch_live = client.patch(
    f"/api/v1/bots/{bot_id}",
    headers=headers,
    json={"mode": "live"},
  )
  assert patch_live.status_code == 400, patch_live.text
  assert "LIVE" in str(patch_live.json().get("detail") or "")

  bulk_live = client.post(
    "/api/v1/bots/bulk-patch",
    headers=headers,
    json={"ids": [bot_id], "mode": "live"},
  )
  assert bulk_live.status_code == 400, bulk_live.text
  assert "LIVE" in str(bulk_live.json().get("detail") or "")


def test_bots_creation_respects_max_instances_limit(tmp_path: Path, monkeypatch) -> None:
  monkeypatch.setenv("BOTS_MAX_INSTANCES", "2")
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  create_1 = client.post(
    "/api/v1/bots",
    headers=headers,
    json={"name": "Cap 1", "mode": "paper", "status": "active"},
  )
  assert create_1.status_code == 200, create_1.text

  create_2 = client.post(
    "/api/v1/bots",
    headers=headers,
    json={"name": "Cap 2", "mode": "paper", "status": "active"},
  )
  assert create_2.status_code == 400
  detail = str(create_2.json().get("detail") or "")
  assert "Limite maximo de bots alcanzado (2)" in detail


def test_archiving_primary_reassigns_valid_primary(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  rows = client.get("/api/v1/strategies", headers=headers).json()
  primary = next((row for row in rows if row.get("is_primary")), None)
  assert primary is not None

  # Ensure another tradable strategy exists, then archive current primary.
  backup = next(row for row in rows if row["id"] != primary["id"])
  res_enable = client.patch(
    f"/api/v1/strategies/{backup['id']}",
    headers=headers,
    json={"enabled_for_trading": True, "status": "active"},
  )
  assert res_enable.status_code == 200, res_enable.text

  res_archive = client.patch(
    f"/api/v1/strategies/{primary['id']}",
    headers=headers,
    json={"status": "archived"},
  )
  assert res_archive.status_code == 200, res_archive.text
  assert res_archive.json()["strategy"]["status"] == "archived"
  assert res_archive.json()["strategy"]["is_primary"] is False

  rows2 = client.get("/api/v1/strategies", headers=headers).json()
  primaries = [row for row in rows2 if row.get("is_primary")]
  assert len(primaries) == 1
  assert primaries[0]["status"] != "archived"
  assert primaries[0]["enabled_for_trading"] is True


def test_patch_strategy_backfills_missing_strategy_registry_row(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  # Simulate legacy row: delete sqlite registry entry but keep strategy_meta.
  with module.store.registry._connect() as conn:  # test-only use of private helper
    conn.execute("DELETE FROM strategy_registry WHERE id=?", ("trend_pullback_orderflow_confirm_v1",))
    conn.commit()

  patch_res = client.patch(
    "/api/v1/strategies/trend_pullback_orderflow_confirm_v1",
    headers=headers,
    json={"allow_learning": False},
  )
  assert patch_res.status_code == 200, patch_res.text
  body = patch_res.json()["strategy"]
  assert body["allow_learning"] is False

  sqlite_row = module.store.registry.get_strategy_registry("trend_pullback_orderflow_confirm_v1")
  assert sqlite_row is not None
  assert sqlite_row["allow_learning"] is False


def test_config_learning_endpoint_reads_yaml_and_exposes_capabilities(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.get("/api/v1/config/learning", headers=headers)
  assert res.status_code == 200, res.text
  body = res.json()
  assert body["ok"] is True
  assert "engines" in body and isinstance(body["engines"], list) and body["engines"]
  assert any(engine["id"] == "bandit_thompson" for engine in body["engines"])
  bandit = next(engine for engine in body["engines"] if engine["id"] == "bandit_thompson")
  assert "capabilities" in bandit and "bandit_weights_history" in bandit["capabilities"]
  assert "capabilities_registry" in body and "offline_change_points" in body["capabilities_registry"]
  assert "safe_update" in body and isinstance(body["safe_update"].get("canary_schedule_pct"), list)
  assert "numeric_policies_summary" in body and isinstance(body["numeric_policies_summary"], dict)
  assert body["numeric_policies_summary"].get("pbo_reject_if_gt") == 0.05
  assert (body.get("gates_summary") or {}).get("source") == "config/policies/gates.yaml"
  assert (body.get("safe_update") or {}).get("gates_file") == "config/policies/gates.yaml"


def test_config_policies_endpoint_exposes_numeric_policy_bundle(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.get("/api/v1/config/policies", headers=headers)
  assert res.status_code == 200, res.text
  body = res.json()
  assert body["ok"] is True
  assert "policies" in body and isinstance(body["policies"], dict)
  assert "gates" in body["policies"] and "microstructure" in body["policies"]
  assert body["summary"]["pbo_reject_if_gt"] == 0.05
  assert body["summary"]["vpin_soft_kill_cdf"] == 0.9


def test_learning_default_risk_profile_prefers_policy_yaml(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  settings_res = client.get("/api/v1/settings", headers=headers)
  assert settings_res.status_code == 200, settings_res.text
  learning = (settings_res.json().get("learning") or {})
  risk_profile = learning.get("risk_profile") or {}

  assert risk_profile.get("source") == "config/policies/risk_policy.yaml"
  paper = risk_profile.get("paper") or {}
  live_initial = risk_profile.get("live_initial") or {}
  assert float(paper.get("max_daily_loss_pct") or 0.0) == pytest.approx(1.0)
  assert float(paper.get("max_drawdown_pct") or 0.0) == pytest.approx(8.0)
  assert float(live_initial.get("max_daily_loss_pct") or 0.0) == pytest.approx(1.5)
  assert float(live_initial.get("max_drawdown_pct") or 0.0) == pytest.approx(8.0)


def test_change_points_smoke_endpoint_returns_breakpoints_or_segments(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  series = ([0.01] * 40) + ([0.20] * 40) + ([0.03] * 40)
  res = client.post(
    "/api/v1/research/change-points",
    headers=headers,
    json={
      "signal_name": "returns",
      "series": series,
      "max_breakpoints": 4,
      "period": {"from": "2024-01-01", "to": "2024-03-31"},
    },
  )
  assert res.status_code == 200, res.text
  body = res.json()
  assert body["ok"] is True
  assert "capability" in body
  assert isinstance(body.get("segments"), list) and body["segments"]
  # Con ruptures o con fallback heuristico debe detectar al menos un corte en una serie con saltos.
  assert isinstance(body.get("breakpoints"), list)
  assert body["breakpoints"] or len(body["segments"]) >= 2


def test_thompson_respects_max_switch_per_day_and_weights_history(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  settings = module.store.load_settings()
  settings["learning"]["enabled"] = True
  settings["learning"]["engine_id"] = "bandit_thompson"
  settings["learning"]["selector_algo"] = "thompson"
  module.store.save_settings(settings)

  # Force different recommendations by restricting the learning pool to one strategy at a time.
  strategy_ids = [
    "trend_pullback_orderflow_v2",
    "breakout_volatility_v2",
    "meanreversion_range_v2",
    "defensive_liquidity_v2",
  ]
  for sid in strategy_ids:
    rows = client.get("/api/v1/strategies", headers=headers).json()
    for row in rows:
      pr = client.patch(f"/api/v1/strategies/{row['id']}", headers=headers, json={"allow_learning": row["id"] == sid})
      assert pr.status_code == 200, pr.text
    rr = client.post("/api/v1/learning/recommend", headers=headers, json={"mode": "paper"})
    if sid != strategy_ids[-1]:
      assert rr.status_code == 200, rr.text
      assert rr.json()["active_strategy_id"] == sid
    else:
      # max_switch_per_day=2 en YAML -> al cuarto cambio en el dÃ­a debe bloquear.
      assert rr.status_code == 400
      assert "max_switch_per_day" in rr.json()["detail"]

  hist = client.get("/api/v1/learning/weights-history?mode=paper", headers=headers)
  assert hist.status_code == 200, hist.text
  items = hist.json()["items"]
  assert items
  assert all("strategy_id" in row and "weight" in row for row in items)


def test_mass_backtest_research_endpoints_and_mark_candidate(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  user_data_dir = Path(module.USER_DATA_DIR)

  dataset_dir = user_data_dir / "datasets" / "binance_public" / "crypto" / "BTCUSDT" / "5m"
  dataset_dir.mkdir(parents=True, exist_ok=True)
  dummy_file = dataset_dir / "chunk_2024-01.parquet"
  dummy_file.write_bytes(b"stub")
  manifest = {
    "provider": "binance_public",
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "dataset_source": "binance_public",
    "dataset_hash": "ds_test_mass_001",
    "start": "2024-01-01",
    "end": "2024-06-30",
    "files": [str(dummy_file.resolve())],
  }
  (dataset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

  def _fake_event_backtest_run(**kwargs):
    strict_strategy_id = bool(kwargs.get("strict_strategy_id", False))
    run = module.store.create_backtest_run(
      strategy_id=str(kwargs.get("strategy_id") or "trend_pullback_orderflow_confirm_v1"),
      start=str(kwargs.get("start") or "2024-01-01"),
      end=str(kwargs.get("end") or "2024-01-31"),
      universe=[str(kwargs.get("symbol") or "BTCUSDT")],
      fees_bps=float(kwargs.get("fees_bps", 5.5)),
      spread_bps=float(kwargs.get("spread_bps", 4.0)),
      slippage_bps=float(kwargs.get("slippage_bps", 3.0)),
      funding_bps=float(kwargs.get("funding_bps", 1.0)),
      validation_mode=str(kwargs.get("validation_mode") or "walk-forward"),
    )
    run["market"] = str(kwargs.get("market") or "crypto")
    run["symbol"] = str(kwargs.get("symbol") or "BTCUSDT")
    run["timeframe"] = str(kwargs.get("timeframe") or "5m")
    run["data_source"] = "binance_public"
    run["dataset_hash"] = "ds_test_mass_001"
    run["provenance"] = {
      **dict(run.get("provenance") or {}),
      "dataset_source": "binance_public",
      "dataset_hash": "ds_test_mass_001",
      "strict_strategy_id": strict_strategy_id,
    }
    run["strict_strategy_id"] = strict_strategy_id
    # Fuerza mÃ©tricas suficientemente robustas para testear el flujo "mark candidate" con gates PASS.
    run.setdefault("metrics", {})
    run["metrics"].update(
      {
        "sharpe": 1.9,
        "sortino": 2.4,
        "calmar": 1.5,
        "max_dd": 0.08,
        "winrate": 0.63,
        "profit_factor": 1.8,
        "expectancy": 12.0,
        "expectancy_usd_per_trade": 12.0,
        "trade_count": 240,
        "roundtrips": 240,
        "robustness_score": 78.0,
      }
    )
    run.setdefault("costs_breakdown", {})
    run["costs_breakdown"].update(
      {
        "gross_pnl_total": 6000.0,
        "gross_pnl": 6000.0,
        "net_pnl_total": 4800.0,
        "net_pnl": 4800.0,
        "total_cost": 1200.0,
        "total_cost_pct_of_gross_pnl": 0.20,
      }
    )
    return run

  monkeypatch.setattr(module.store, "create_event_backtest_run", _fake_event_backtest_run)
  monkeypatch.setattr(
    module,
    "load_numeric_policies_bundle",
    lambda: {
      "available": True,
      "source_root": str(tmp_path),
      "warnings": [],
      "summary": {},
      "files": {},
      "policies": {
        "gates": {
          "pbo": {"enabled": False},
          "dsr": {"enabled": False},
          "walk_forward": {
            "enabled": True,
            "folds": 5,
            "pass_if_positive_folds_at_least": 4,
            "max_is_to_oos_degradation": 0.30,
          },
          "cost_stress": {
            "enabled": True,
            "multipliers": [1.5, 2.0],
            "must_remain_profitable_at_1_5x": True,
            "max_score_drop_at_2_0x": 0.50,
          },
          "min_trade_quality": {"enabled": True, "min_trades_per_run": 150, "min_trades_per_symbol": 30},
        },
        "microstructure": {},
        "risk_policy": {},
        "beast_mode": {},
        "fees": {},
      },
    },
  )
  _orig_apply_advanced_gates = module.mass_backtest_coordinator.engine._apply_advanced_gates
  def _force_pass_advanced_gates(*, rows, cfg):
    summary = _orig_apply_advanced_gates(rows=rows, cfg=cfg)
    for row in rows:
      if not isinstance(row, dict):
        continue
      row["gates_eval"] = {
        "passed": True,
        "fail_reasons": [],
        "checks": dict(((row.get("gates_eval") or {}).get("checks") or {})),
        "summary": {"forced_for_test": True},
      }
      row["recommendable_option_b"] = True
      anti = row.get("anti_overfitting") if isinstance(row.get("anti_overfitting"), dict) else {}
      anti["promotion_blocked"] = False
      row["anti_overfitting"] = anti
    if isinstance(summary, dict):
      summary["gates_pass_count"] = len([r for r in rows if isinstance(r, dict)])
    return summary
  monkeypatch.setattr(module.mass_backtest_coordinator.engine, "_apply_advanced_gates", _force_pass_advanced_gates)

  strategies = client.get("/api/v1/strategies", headers=headers).json()
  strategy_ids = [row["id"] for row in strategies[:2]]
  reject_synth = client.post(
    "/api/v1/research/mass-backtest/start",
    headers=headers,
    json={
      "strategy_ids": strategy_ids,
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-06-30",
      "dataset_source": "synthetic",
      "max_variants_per_strategy": 1,
      "max_folds": 5,
      "train_days": 30,
      "test_days": 30,
      "top_n": 3,
      "seed": 11,
    },
  )
  assert reject_synth.status_code == 400
  assert "solo acepta datos reales" in reject_synth.json()["detail"].lower()
  start = client.post(
    "/api/v1/research/mass-backtest/start",
    headers=headers,
    json={
      "strategy_ids": strategy_ids,
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-06-30",
      "dataset_source": "auto",
      "max_variants_per_strategy": 1,
      "max_folds": 5,
      "train_days": 30,
      "test_days": 30,
      "top_n": 3,
      "seed": 11,
    },
  )
  assert start.status_code == 200, start.text
  run_id = start.json()["run_id"]

  status_payload = None
  for _ in range(200):
    st = client.get(f"/api/v1/research/mass-backtest/status?run_id={run_id}", headers=headers)
    assert st.status_code == 200, st.text
    status_payload = st.json()
    if status_payload["state"] in {"COMPLETED", "FAILED"}:
      break
    time.sleep(0.1)
  assert status_payload is not None
  assert status_payload["state"] == "COMPLETED", status_payload.get("error")

  results = client.get(f"/api/v1/research/mass-backtest/results?run_id={run_id}&limit=20", headers=headers)
  assert results.status_code == 200, results.text
  results_payload = results.json()
  assert isinstance(results_payload.get("results"), list) and results_payload["results"]
  top = results_payload["results"][0]
  assert "score" in top and "regime_metrics" in top and "summary" in top
  assert "gates_eval" in top and isinstance(top["gates_eval"], dict)
  assert bool(top.get("strict_strategy_id")) is True
  assert bool((top.get("summary") or {}).get("strict_strategy_id")) is True
  passing = next((row for row in results_payload["results"] if isinstance(row, dict) and bool((row.get("gates_eval") or {}).get("passed"))), None)
  assert passing is not None, results_payload["results"]

  artifacts = client.get(f"/api/v1/research/mass-backtest/artifacts?run_id={run_id}", headers=headers)
  assert artifacts.status_code == 200, artifacts.text
  assert any(item["name"] == "index.html" for item in artifacts.json()["items"])

  mark = client.post(
    "/api/v1/research/mass-backtest/mark-candidate",
    headers=headers,
    json={"run_id": run_id, "variant_id": passing["variant_id"], "note": "draft desde e2e"},
  )
  assert mark.status_code == 200, mark.text
  draft = mark.json()["recommendation_draft"]
  assert draft["status"] == "DRAFT_MASS_BACKTEST"
  assert draft["mass_backtest"]["strict_strategy_id"] is True
  assert draft["option_b"]["allow_live"] is False

  recs = client.get("/api/v1/learning/recommendations", headers=headers)
  assert recs.status_code == 200, recs.text
  assert any(row["id"] == draft["id"] for row in recs.json())


def test_research_mass_backtest_start_rejects_missing_dataset(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  strategies = client.get("/api/v1/strategies", headers=headers)
  assert strategies.status_code == 200, strategies.text
  strategy_ids = [row["id"] for row in strategies.json()[:2]]

  start = client.post(
    "/api/v1/research/mass-backtest/start",
    headers=headers,
    json={
      "strategy_ids": strategy_ids,
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-03-31",
      "dataset_source": "auto",
      "data_mode": "dataset",
      "max_variants_per_strategy": 1,
      "max_folds": 2,
      "train_days": 30,
      "test_days": 30,
      "top_n": 2,
      "seed": 7,
    },
  )
  assert start.status_code == 400, start.text
  assert "no hay dataset real disponible" in str((start.json() or {}).get("detail") or "").lower()


def test_research_mass_backtest_start_forwards_bot_id(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  captured: dict[str, object] = {}

  def _fake_start_async(**kwargs):
    captured["config"] = kwargs.get("config")
    return {"ok": True, "run_id": "BX-TEST-BOT", "state": "QUEUED"}

  monkeypatch.setattr(module.mass_backtest_coordinator, "start_async", _fake_start_async)

  start = client.post(
    "/api/v1/research/mass-backtest/start",
    headers=headers,
    json={
      "strategy_ids": ["trend_pullback_orderflow_confirm_v1"],
      "bot_id": "BOT-TEST-MASS",
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-03-31",
      "dataset_source": "auto",
      "validation_mode": "walk-forward",
      "max_variants_per_strategy": 1,
      "max_folds": 2,
      "train_days": 30,
      "test_days": 30,
      "top_n": 2,
      "seed": 7,
    },
  )
  assert start.status_code == 200, start.text
  assert start.json()["ok"] is True
  assert isinstance(captured.get("config"), dict)
  assert str((captured["config"] or {}).get("bot_id") or "") == "BOT-TEST-MASS"


def test_mass_backtest_mark_candidate_requires_strict_strategy_id_non_demo(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  monkeypatch.setattr(
    module.mass_backtest_coordinator,
    "results",
    lambda run_id, limit=5000, strategy_id=None, only_pass=False: {
      "run_id": run_id,
      "config": {"execution_mode": "research"},
      "results": [
        {
          "variant_id": "v_strict_missing",
          "strategy_id": "trend_pullback_orderflow_confirm_v1",
          "score": 1.23,
          "summary": {"trade_count_oos": 220, "expectancy_net_usd": 8.0, "sharpe_oos": 1.4, "calmar_oos": 1.1, "max_dd_oos_pct": 10.0},
          "regime_metrics": {},
          "hard_filters_pass": True,
          "recommendable_option_b": True,
          "gates_eval": {"passed": True, "fail_reasons": [], "checks": {}},
          "strict_strategy_id": False,
        }
      ],
    },
  )

  mark = client.post(
    "/api/v1/research/mass-backtest/mark-candidate",
    headers=headers,
    json={"run_id": "RBX-1", "variant_id": "v_strict_missing", "note": "strict missing"},
  )
  assert mark.status_code == 400, mark.text
  assert "strict_strategy_id" in str(mark.json().get("detail") or "")


def test_research_beast_endpoints_smoke(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  _seed_local_backtest_dataset(tmp_path / "user_data", "crypto", "BTCUSDT", source="binance_public")
  monkeypatch.setattr(
    module.mass_backtest_coordinator,
    "_beast_policy",
    lambda cfg=None: {
      "enabled": True,
      "requires_postgres": True,
      "max_trials_per_batch": 5000,
      "max_concurrent_jobs": 2,
      "rate_limit_enabled": True,
      "max_requests_per_minute": 1200,
      "budget_governor_enabled": True,
      "daily_job_cap_hobby": 200,
      "daily_job_cap_pro": 800,
      "stop_at_budget_pct": 80,
    },
  )

  strategies = client.get("/api/v1/strategies", headers=headers)
  assert strategies.status_code == 200, strategies.text
  strategy_id = strategies.json()[0]["id"]

  start = client.post(
    "/api/v1/research/beast/start",
    headers=headers,
    json={
      "strategy_ids": [strategy_id],
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-03-31",
      "dataset_source": "auto",
      "max_variants_per_strategy": 1,
      "max_folds": 2,
      "train_days": 30,
      "test_days": 30,
      "top_n": 2,
      "seed": 7,
      "tier": "hobby",
    },
  )
  assert start.status_code == 200, start.text
  payload = start.json()
  assert payload["ok"] is True
  assert payload["mode"] == "beast"
  assert str(payload["run_id"]).startswith("BX-")

  status = client.get("/api/v1/research/beast/status", headers=headers)
  assert status.status_code == 200, status.text
  status_payload = status.json()
  assert "scheduler" in status_payload and "budget" in status_payload

  jobs = client.get("/api/v1/research/beast/jobs?limit=5", headers=headers)
  assert jobs.status_code == 200, jobs.text
  jobs_payload = jobs.json()
  assert isinstance(jobs_payload.get("items"), list)
  assert any(item.get("run_id") == payload["run_id"] for item in jobs_payload["items"])

  stop = client.post("/api/v1/research/beast/stop-all", headers=headers, json={"reason": "test"})
  assert stop.status_code == 200, stop.text
  assert stop.json()["ok"] is True

  resume = client.post("/api/v1/research/beast/resume", headers=headers, json={})
  assert resume.status_code == 200, resume.text
  assert resume.json()["ok"] is True


def test_research_beast_start_rejects_missing_dataset(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  monkeypatch.setattr(
    module.mass_backtest_coordinator,
    "_beast_policy",
    lambda cfg=None: {
      "enabled": True,
      "requires_postgres": False,
      "max_trials_per_batch": 5000,
      "max_concurrent_jobs": 2,
      "rate_limit_enabled": False,
      "max_requests_per_minute": 1200,
      "budget_governor_enabled": False,
      "daily_job_cap_hobby": 200,
      "daily_job_cap_pro": 800,
      "stop_at_budget_pct": 80,
    },
  )

  start = client.post(
    "/api/v1/research/beast/start",
    headers=headers,
    json={
      "strategy_ids": ["trend_pullback_orderflow_confirm_v1"],
      "bot_id": "BOT-TEST-BEAST",
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-03-31",
      "dataset_source": "auto",
      "data_mode": "dataset",
      "max_variants_per_strategy": 1,
      "max_folds": 2,
      "train_days": 30,
      "test_days": 30,
      "top_n": 2,
      "seed": 7,
      "tier": "hobby",
    },
  )
  assert start.status_code == 400, start.text
  assert "no hay dataset real disponible" in str((start.json() or {}).get("detail") or "").lower()


def test_research_beast_status_distinguishes_missing_runtime_policy_root(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  monkeypatch.setattr(
    module.mass_backtest_coordinator,
    "beast_status",
    lambda: {
      "enabled": True,
      "enqueue_ready": True,
      "operational_state": "ready",
      "blockers": [],
      "scheduler": {"stop_requested": False, "queue_depth": 0, "workers_active": 0},
      "budget": {"tier": "hobby", "daily_cap": 200, "stop_at_budget_pct": 80.0},
      "counts": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
      "recent_history": [],
      "requires_postgres": True,
      "mode": "local_scheduler_phase1",
    },
  )
  monkeypatch.setattr(
    module,
    "load_numeric_policies_bundle",
    lambda: {
      "available": False,
      "source_root": "",
      "warnings": ["runtime_policy_root_missing"],
      "files": {},
      "policies": {},
    },
  )

  status = client.get("/api/v1/research/beast/status", headers=headers)
  assert status.status_code == 200, status.text
  payload = status.json()
  assert payload["policy_state"] == "missing_root"
  assert payload["enqueue_ready"] is False
  assert "runtime_policy_root_missing" in (payload.get("blockers") or [])
  assert "config/policies" in str(payload.get("operator_hint") or "")


def test_research_beast_status_distinguishes_disabled_policy(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  monkeypatch.setattr(
    module.mass_backtest_coordinator,
    "beast_status",
    lambda: {
      "enabled": False,
      "enqueue_ready": False,
      "operational_state": "disabled",
      "blockers": ["policy_disabled"],
      "scheduler": {"stop_requested": False, "queue_depth": 0, "workers_active": 0},
      "budget": {"tier": "hobby", "daily_cap": 200, "stop_at_budget_pct": 80.0},
      "counts": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
      "recent_history": [],
      "requires_postgres": True,
      "mode": "local_scheduler_phase1",
    },
  )
  monkeypatch.setattr(
    module,
    "load_numeric_policies_bundle",
    lambda: {
      "available": True,
      "source_root": "C:/repo/config/policies",
      "warnings": [],
      "files": {"beast_mode": {"path": "C:/repo/config/policies/beast_mode.yaml", "exists": True, "valid": True}},
      "policies": {"beast_mode": {"beast_mode": {"enabled": False}}},
    },
  )

  status = client.get("/api/v1/research/beast/status", headers=headers)
  assert status.status_code == 200, status.text
  payload = status.json()
  assert payload["policy_state"] == "disabled"
  assert payload["enqueue_ready"] is False
  assert "policy_disabled" in (payload.get("blockers") or [])
  assert "enabled=false" in str(payload.get("operator_hint") or "")


def test_research_beast_status_distinguishes_missing_beast_file(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)
  monkeypatch.setattr(
    module.mass_backtest_coordinator,
    "beast_status",
    lambda: {
      "enabled": True,
      "enqueue_ready": True,
      "operational_state": "ready",
      "blockers": [],
      "scheduler": {"stop_requested": False, "queue_depth": 0, "workers_active": 0},
      "budget": {"tier": "hobby", "daily_cap": 200, "stop_at_budget_pct": 80.0},
      "counts": {"queued": 0, "running": 0, "completed": 0, "failed": 0},
      "recent_history": [],
      "requires_postgres": True,
      "mode": "local_scheduler_phase1",
    },
  )
  monkeypatch.setattr(
    module,
    "load_numeric_policies_bundle",
    lambda: {
      "available": True,
      "source_root": "C:/repo/config/policies",
      "warnings": [],
      "files": {"beast_mode": {"path": "C:/repo/config/policies/beast_mode.yaml", "exists": False, "valid": False}},
      "policies": {},
    },
  )

  status = client.get("/api/v1/research/beast/status", headers=headers)
  assert status.status_code == 200, status.text
  payload = status.json()
  assert payload["policy_state"] == "missing_file"
  assert payload["enqueue_ready"] is False
  assert "beast_mode_yaml_missing" in (payload.get("blockers") or [])
  assert "beast_mode.yaml" in str(payload.get("operator_hint") or "")


def test_research_beast_start_accepts_orderflow_toggle(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  captured: dict[str, object] = {}

  def _fake_start_beast_async(**kwargs):
    captured["config"] = kwargs.get("config")
    return {
      "ok": True,
      "run_id": "BX-TEST-OFLOW",
      "state": "QUEUED",
      "mode": "beast",
      "queue_position": 1,
      "estimated_trial_units": 10,
    }

  monkeypatch.setattr(module.mass_backtest_coordinator, "start_beast_async", _fake_start_beast_async)

  start = client.post(
    "/api/v1/research/beast/start",
    headers=headers,
    json={
      "bot_id": "BOT-TEST-BEAST",
      "strategy_ids": ["trend_pullback_orderflow_confirm_v1"],
      "market": "crypto",
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "start": "2024-01-01",
      "end": "2024-03-31",
      "dataset_source": "auto",
      "validation_mode": "walk-forward",
      "max_variants_per_strategy": 1,
      "max_folds": 2,
      "train_days": 30,
      "test_days": 30,
      "top_n": 2,
      "seed": 7,
      "tier": "hobby",
      "use_orderflow_data": False,
    },
  )
  assert start.status_code == 200, start.text
  assert start.json()["ok"] is True
  assert isinstance(captured.get("config"), dict)
  assert bool((captured["config"] or {}).get("use_orderflow_data")) is False
  assert str((captured["config"] or {}).get("bot_id") or "") == "BOT-TEST-BEAST"


def test_batch_shortlist_save_and_load(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  module.store.backtest_catalog.upsert_backtest_batch(
    {
      "batch_id": "BX-001111",
      "objective": "Batch test shortlist",
      "status": "completed",
      "run_count_total": 10,
      "run_count_done": 10,
      "run_count_failed": 0,
    }
  )

  save = client.post(
    "/api/v1/batches/BX-001111/shortlist",
    headers=headers,
    json={
      "source": "test_suite",
      "note": "guardado desde test",
      "items": [
        {
          "variant_id": "trend_pullback__v001",
          "run_id": "BT-000123",
          "strategy_id": "trend_pullback_orderflow_v2",
          "strategy_name": "Trend Pullback OF",
          "score": 0.58,
          "winrate_oos": 0.57,
        },
        {
          "variant_id": "breakout__v007",
          "run_id": "BT-000124",
          "strategy_id": "breakout_volatility_v2",
          "strategy_name": "Breakout Vol",
          "score": 0.52,
          "winrate_oos": 0.54,
        },
      ],
    },
  )
  assert save.status_code == 200, save.text
  payload = save.json()
  assert payload["ok"] is True
  assert payload["saved_count"] == 2

  detail = client.get("/api/v1/batches/BX-001111", headers=headers)
  assert detail.status_code == 200, detail.text
  detail_payload = detail.json()
  assert isinstance(detail_payload.get("best_runs_cache"), list)
  assert len(detail_payload["best_runs_cache"]) == 2
  assert detail_payload["best_runs_cache"][0]["run_id"] == "BT-000123"


def test_monitoring_health_endpoint_returns_scores(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  res = client.get("/api/v1/monitoring/health", headers=headers)
  assert res.status_code == 200, res.text
  payload = res.json()

  for key in [
    "global_health_score",
    "data_health_score",
    "research_health_score",
    "brain_health_score",
    "execution_health_score",
    "live_health_score",
    "risk_health_score",
    "observability_health_score",
  ]:
    assert key in payload
    assert isinstance(payload[key], (int, float))

  summary = payload.get("summary") or {}
  assert isinstance(summary.get("status"), dict)
  assert isinstance(summary.get("data_health"), dict)
  assert isinstance(payload.get("reasons"), list)
  assert isinstance(payload.get("suggested_actions"), list)


def test_monitoring_kill_switches_endpoint_exposes_recent_breakers(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  module.store.add_log(
    event_type="breaker_triggered",
    severity="warn",
    module="risk",
    message="kill bot paper",
    related_ids=["BOT-MONITORING"],
    payload={"bot_id": "BOT-MONITORING", "mode": "paper", "reason": "drawdown", "symbol": "BTCUSDT"},
  )

  res = client.get("/api/v1/monitoring/kill-switches", headers=headers)
  assert res.status_code == 200, res.text
  payload = res.json()
  assert isinstance(payload.get("recent_events"), list)
  assert payload["recent_events"]
  first = payload["recent_events"][0]
  assert first["bot_id"] == "BOT-MONITORING"
  assert first["mode"] == "paper"
  assert first["reason"] == "drawdown"


def test_monitoring_endpoints_degrade_cleanly_when_drift_fails(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  def _boom(*, settings, runs):
    raise RuntimeError("drift_down")

  monkeypatch.setattr(module.learning_service, "compute_drift", _boom)

  drift_res = client.get("/api/v1/monitoring/drift", headers=headers)
  assert drift_res.status_code == 200, drift_res.text
  drift_payload = drift_res.json()
  assert drift_payload["status"] == "DEGRADED"
  assert drift_payload["algo"] == "error"
  assert drift_payload["error"] == "drift_down"

  summary_res = client.get("/api/v1/monitoring/metrics-summary", headers=headers)
  assert summary_res.status_code == 200, summary_res.text
  summary = summary_res.json()
  assert (summary.get("brain_health") or {}).get("drift_algo") == "error"


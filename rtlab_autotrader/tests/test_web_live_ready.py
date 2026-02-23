from __future__ import annotations

import importlib
import io
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
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
  assert "LIVE blocked by gates" in enable_live.json()["detail"]


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
  _, client = _build_app(tmp_path, monkeypatch)
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

  rec_detail = client.get(f"/api/v1/learning/recommendations/{rec['id']}", headers=headers)
  assert rec_detail.status_code == 200, rec_detail.text
  assert rec_detail.json()["id"] == rec["id"]

  adopt = client.post("/api/v1/learning/adopt", headers=headers, json={"candidate_id": rec["id"], "mode": "paper"})
  assert adopt.status_code == 200, adopt.text
  adopt_body = adopt.json()
  assert adopt_body["ok"] is True
  assert adopt_body["mode"] == "paper"
  assert adopt_body["applied_live"] is False


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
    return _DummyResponse(404, {"code": -1, "msg": "not found"})

  monkeypatch.setattr(module.requests, "get", fake_get)
  monkeypatch.setattr(module.requests, "request", fake_request)
  monkeypatch.setattr(module.socket, "create_connection", lambda *args, **kwargs: _DummySocket())


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
  assert any("corregida automáticamente" in msg for msg in (payload.get("diagnostics") or []))


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
  _, client = _build_app(tmp_path, monkeypatch, mode="paper")
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  strategies = client.get("/api/v1/strategies", headers=headers).json()
  strategy_id = strategies[0]["id"]
  payload_common = {
    "strategy_id": strategy_id,
    "period": {"start": "2024-01-01", "end": "2024-03-31"},
    "universe": ["BTC/USDT", "ETH/USDT"],
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

  assert high_run["costs_breakdown"]["total_cost"] > low_run["costs_breakdown"]["total_cost"]
  assert high_run["metrics"]["expectancy"] < low_run["metrics"]["expectancy"]


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
      # max_switch_per_day=2 en YAML -> al cuarto cambio en el día debe bloquear.
      assert rr.status_code == 400
      assert "max_switch_per_day" in rr.json()["detail"]

  hist = client.get("/api/v1/learning/weights-history?mode=paper", headers=headers)
  assert hist.status_code == 200, hist.text
  items = hist.json()["items"]
  assert items
  assert all("strategy_id" in row and "weight" in row for row in items)


def test_mass_backtest_research_endpoints_and_mark_candidate(tmp_path: Path, monkeypatch) -> None:
  _module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  strategies = client.get("/api/v1/strategies", headers=headers).json()
  strategy_ids = [row["id"] for row in strategies[:2]]
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
      "dataset_source": "synthetic",
      "max_variants_per_strategy": 1,
      "max_folds": 1,
      "train_days": 30,
      "test_days": 30,
      "top_n": 3,
      "seed": 11,
    },
  )
  assert start.status_code == 200, start.text
  run_id = start.json()["run_id"]

  status_payload = None
  for _ in range(40):
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

  artifacts = client.get(f"/api/v1/research/mass-backtest/artifacts?run_id={run_id}", headers=headers)
  assert artifacts.status_code == 200, artifacts.text
  assert any(item["name"] == "index.html" for item in artifacts.json()["items"])

  mark = client.post(
    "/api/v1/research/mass-backtest/mark-candidate",
    headers=headers,
    json={"run_id": run_id, "variant_id": top["variant_id"], "note": "draft desde e2e"},
  )
  assert mark.status_code == 200, mark.text
  draft = mark.json()["recommendation_draft"]
  assert draft["status"] == "DRAFT_MASS_BACKTEST"
  assert draft["option_b"]["allow_live"] is False

  recs = client.get("/api/v1/learning/recommendations", headers=headers)
  assert recs.status_code == 200, recs.text
  assert any(row["id"] == draft["id"] for row in recs.json())

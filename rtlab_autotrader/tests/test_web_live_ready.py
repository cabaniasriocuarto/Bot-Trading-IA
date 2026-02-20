from __future__ import annotations

import importlib
import io
import zipfile
from pathlib import Path

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


def _build_app(tmp_path: Path, monkeypatch):
  data_dir = tmp_path / "user_data"
  config_path = tmp_path / "rtlab_config.yaml"
  config_path.write_text(CONFIG_YAML, encoding="utf-8")

  monkeypatch.setenv("RTLAB_USER_DATA_DIR", str(data_dir))
  monkeypatch.setenv("RTLAB_CONFIG_PATH", str(config_path))
  monkeypatch.setenv("AUTH_SECRET", "x" * 40)
  monkeypatch.setenv("ADMIN_USERNAME", "Wadmin")
  monkeypatch.setenv("ADMIN_PASSWORD", "moroco123")
  monkeypatch.setenv("VIEWER_USERNAME", "viewer")
  monkeypatch.setenv("VIEWER_PASSWORD", "viewer123")
  monkeypatch.setenv("MODE", "paper")
  monkeypatch.setenv("EXCHANGE_NAME", "binance")
  monkeypatch.setenv("TELEGRAM_ENABLED", "false")
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

from __future__ import annotations

import importlib
import json
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
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "console_settings.json").write_text(json.dumps({}), encoding="utf-8")

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


def test_compare_feature_set_is_fail_closed_when_orderflow_evidence_is_missing(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    token = _login(client, "Wadmin", "moroco123")
    headers = _auth_headers(token)

    rows = [
        {
            "run_id": "BT-LEG-1",
            "legacy_json_id": "BT-LEG-1",
            "status": "completed",
            "dataset_hash": "ds_same",
            "timerange_from": "2024-01-01",
            "timerange_to": "2024-01-31",
            "market": "crypto",
            "flags": {},
        },
        {
            "run_id": "BT-LEG-2",
            "legacy_json_id": "BT-LEG-2",
            "status": "completed",
            "dataset_hash": "ds_same",
            "timerange_from": "2024-01-01",
            "timerange_to": "2024-01-31",
            "market": "crypto",
            "flags": {},
        },
    ]
    monkeypatch.setattr(module.store.backtest_catalog, "compare_runs", lambda run_ids: rows)

    res = client.get("/api/v1/compare?r=BT-LEG-1&r=BT-LEG-2", headers=headers)
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["feature_sets"] == ["orderflow_unknown"]

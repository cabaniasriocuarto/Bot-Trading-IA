from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


CONFIG_YAML = """
mode: paper
universe:
  exchange: binance
  market_type: spot
  whitelist: ["BTC/USDT"]
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


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400

    @property
    def content(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeBinanceHTTP:
    def __init__(self) -> None:
        self.spot_payload = {
            "timezone": "UTC",
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "permissions": ["SPOT", "MARGIN"],
                    "permissionSets": [["SPOT", "MARGIN"]],
                    "isSpotTradingAllowed": True,
                    "isMarginTradingAllowed": True,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                        {"filterType": "LOT_SIZE", "minQty": "0.0001", "maxQty": "1000", "stepSize": "0.0001"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "10.0", "applyToMarket": True, "avgPriceMins": 5},
                    ],
                }
            ],
        }
        self.usdm_payload = {
            "timezone": "UTC",
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "marginAsset": "USDT",
                    "contractType": "PERPETUAL",
                    "triggerProtect": "0.0500",
                    "deliveryDate": 4133404800000,
                    "onboardDate": 1704067200000,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
                        {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                        {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "maxQty": "1500", "stepSize": "0.001"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ],
                }
            ],
        }
        self.coinm_payload = {
            "timezone": "UTC",
            "symbols": [
                {
                    "symbol": "BTCUSD_PERP",
                    "pair": "BTCUSD",
                    "status": "TRADING",
                    "contractStatus": "TRADING",
                    "baseAsset": "BTC",
                    "quoteAsset": "USD",
                    "marginAsset": "BTC",
                    "contractType": "PERPETUAL",
                    "triggerProtect": "0.0500",
                    "deliveryDate": 4133404800000,
                    "onboardDate": 1704067200000,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
                        {"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "100000", "stepSize": "1"},
                        {"filterType": "MARKET_LOT_SIZE", "minQty": "1", "maxQty": "100000", "stepSize": "1"},
                    ],
                }
            ],
        }

    def get(self, url: str, headers=None, timeout=None, params=None):  # noqa: ANN001
        if "/api/v3/exchangeInfo" in url:
            return _FakeResponse(self.spot_payload)
        if "/fapi/v1/exchangeInfo" in url:
            return _FakeResponse(self.usdm_payload)
        if "/dapi/v1/exchangeInfo" in url:
            return _FakeResponse(self.coinm_payload)
        if "/api/v3/account" in url:
            return _FakeResponse({"canTrade": True})
        if "/sapi/v1/margin/account" in url:
            return _FakeResponse({"created": True, "borrowEnabled": True, "tradeEnabled": True})
        if "/fapi/v2/account" in url:
            return _FakeResponse({"canTrade": True, "assets": [{"asset": "USDT", "marginAvailable": True}]})
        if "/dapi/v1/account" in url:
            return _FakeResponse({"canTrade": True, "assets": [{"asset": "BTC", "walletBalance": "1"}]})
        raise AssertionError(f"Unexpected Binance URL: {url}")


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

    fake_http = FakeBinanceHTTP()
    monkeypatch.setattr("requests.get", fake_http.get)

    module = importlib.import_module("rtlab_core.web.app")
    module = importlib.reload(module)
    return module, TestClient(module.app)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return str(res.json()["token"])


def _seed_validation_stage(module, *, stage: str = "PAPER", count: int = 30) -> None:  # noqa: ANN001
    execution = module.store.execution_reality
    family = "spot"
    symbol = "BTCUSDT"
    environment = {"PAPER": "paper", "TESTNET": "testnet", "CANARY": "live"}[stage]
    now = datetime.now(timezone.utc) - timedelta(days=4)
    step_hours = 12 if stage != "CANARY" else 1
    for index in range(count):
        when = now + timedelta(hours=index * step_hours)
        created_at = when.isoformat()
        intent = execution.db.insert_intent(
            {
                "created_at": created_at,
                "submitted_at": created_at,
                "venue": "binance",
                "family": family,
                "environment": environment,
                "mode": environment if environment != "paper" else "paper",
                "symbol": symbol,
                "side": "BUY",
                "order_type": "LIMIT",
                "client_order_id": f"CID-{uuid4().hex[:12]}",
                "preflight_status": "submitted",
                "estimated_total_cost": 5.0,
                "estimated_fee": 1.0,
                "estimated_slippage_bps": 2.0,
                "policy_hash": execution.policy_hash(),
                "raw_request_json": {"seeded": True},
            }
        )
        order = execution.db.upsert_order(
            {
                "execution_intent_id": intent["execution_intent_id"],
                "client_order_id": intent["client_order_id"],
                "venue_order_id": f"OID-{uuid4().hex[:12]}",
                "symbol": symbol,
                "family": family,
                "environment": environment,
                "order_status": "FILLED",
                "submitted_at": created_at,
                "acknowledged_at": created_at,
                "price": 50000.0,
                "orig_qty": 0.01,
                "executed_qty": 0.01,
                "cum_quote_qty": 500.0,
                "avg_fill_price": 50000.0,
                "raw_ack_json": {"seeded": True},
                "raw_last_status_json": {"status": "FILLED"},
            }
        )
        fill = execution.db.insert_fill(
            {
                "execution_order_id": order["execution_order_id"],
                "venue_trade_id": f"TID-{uuid4().hex[:10]}",
                "fill_time": created_at,
                "symbol": symbol,
                "family": family,
                "price": 50000.0,
                "qty": 0.01,
                "quote_qty": 500.0,
                "commission": 1.0,
                "commission_asset": "USDT",
                "spread_realized": 2.0,
                "slippage_realized": 2.0,
                "gross_pnl": 100.0,
                "net_pnl": 95.0,
                "cost_source_json": {"source_kind": "execution_reality_fill"},
                "provenance_json": {"trade_ref": "", "source_kind": "execution_reality_fill"},
                "raw_fill_json": {"seeded": True},
            }
        )
        execution._sync_fills_to_reporting_bridge(order=order, intent=intent, fills=[fill])

    snapshot = {
        "bid": 50000.0,
        "ask": 50001.0,
        "quote_ts_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "orderbook_ts_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "source": "seeded",
    }
    execution.set_market_snapshot(family=family, environment="live", symbol=symbol, **snapshot)
    execution.set_market_snapshot(family=family, environment="testnet", symbol=symbol, **snapshot)
    execution.mark_user_stream_status(family=family, environment="testnet", available=True)
    execution.mark_user_stream_status(family=family, environment="live", available=True)
    module.store.instrument_registry.sync(startup=False)


def test_validation_summary_and_readiness_endpoints(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    token = _login(client, "Wadmin", "moroco123")

    summary_res = client.get("/api/v1/validation/summary", headers=_auth_headers(token))
    readiness_res = client.get("/api/v1/validation/readiness", headers=_auth_headers(token))

    assert summary_res.status_code == 200, summary_res.text
    assert readiness_res.status_code == 200, readiness_res.text
    assert summary_res.json()["stage_actual"] == "PAPER"
    assert readiness_res.json()["live_serio_ready"] is False
    assert readiness_res.json()["policy_source"]["valid"] is True


def test_validation_evaluate_runs_and_detail_endpoints(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    token = _login(client, "Wadmin", "moroco123")
    _seed_validation_stage(module, stage="PAPER", count=30)

    evaluate_res = client.post(
        "/api/v1/validation/evaluate",
        headers=_auth_headers(token),
        json={"stage": "PAPER", "family": "spot", "venue": "binance"},
    )
    assert evaluate_res.status_code == 200, evaluate_res.text
    payload = evaluate_res.json()
    validation_run_id = str(payload["validation_run"]["validation_run_id"])

    runs_res = client.get("/api/v1/validation/runs", headers=_auth_headers(token))
    detail_res = client.get(f"/api/v1/validation/runs/{validation_run_id}", headers=_auth_headers(token))
    readiness_res = client.get("/api/v1/validation/readiness", headers=_auth_headers(token))

    assert payload["validation_run"]["result"] == "PASS"
    assert runs_res.status_code == 200, runs_res.text
    assert detail_res.status_code == 200, detail_res.text
    assert readiness_res.status_code == 200, readiness_res.text
    assert runs_res.json()["items"][0]["validation_run_id"] == validation_run_id
    assert detail_res.json()["gate_results"]
    assert detail_res.json()["stage_evidence"]
    assert readiness_res.json()["readiness_by_stage"]["paper"]["ready"] is True
    assert readiness_res.json()["live_serio_ready"] is False

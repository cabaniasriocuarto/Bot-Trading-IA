from __future__ import annotations

import importlib
import json
from datetime import timedelta
from pathlib import Path

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
    def __init__(self, payload, status_code: int = 200) -> None:  # noqa: ANN001
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):  # noqa: ANN001
        return self._payload


class FakeBinanceExecutionHTTP:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
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
        if "/myTrades" in url or "/userTrades" in url or "/income" in url:
            return _FakeResponse([])
        return _FakeResponse({})

    def request(self, method: str, url: str, params=None, headers=None, timeout=None):  # noqa: ANN001
        params = params or {}
        self.requests.append({"method": method, "url": url, "params": dict(params)})
        if "countdownCancelAll" in url:
            return _FakeResponse({"symbol": params.get("symbol"), "countdownTime": params.get("countdownTime")})
        if method.upper() == "DELETE" and url.endswith("/order"):
            return _FakeResponse({"status": "CANCELED", "symbol": params.get("symbol"), "orderId": params.get("orderId") or 12345})
        if method.upper() == "POST" and url.endswith("/order"):
            qty = float(params.get("quantity") or 0.0)
            price = float(params.get("price") or 50010.0)
            order_type = str(params.get("type") or "").upper()
            status = "FILLED" if order_type == "MARKET" else "NEW"
            payload = {
                "symbol": params.get("symbol"),
                "orderId": 12345,
                "clientOrderId": params.get("newClientOrderId"),
                "status": status,
                "type": order_type,
                "price": str(price),
                "avgPrice": str(price),
                "executedQty": str(qty if status == "FILLED" else 0.0),
                "cummulativeQuoteQty": str(price * qty if status == "FILLED" else 0.0),
            }
            if status == "FILLED":
                payload["fills"] = [
                    {
                        "price": str(price),
                        "qty": str(qty),
                        "commission": "0.25",
                        "commissionAsset": "USDT",
                        "tradeId": 999,
                    }
                ]
            return _FakeResponse(payload)
        if method.upper() == "GET" and "openOrders" in url:
            return _FakeResponse([])
        return _FakeResponse({})


def _build_app(tmp_path: Path, monkeypatch, fake_http: FakeBinanceExecutionHTTP):
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
    monkeypatch.setenv("BINANCE_API_KEY", "spot-live")
    monkeypatch.setenv("BINANCE_API_SECRET", "spot-live-secret")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "spot-testnet")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "spot-testnet-secret")
    monkeypatch.setenv("BINANCE_USDM_API_KEY", "usdm-live")
    monkeypatch.setenv("BINANCE_USDM_API_SECRET", "usdm-live-secret")
    monkeypatch.setenv("BINANCE_USDM_TESTNET_API_KEY", "usdm-testnet")
    monkeypatch.setenv("BINANCE_USDM_TESTNET_API_SECRET", "usdm-testnet-secret")
    monkeypatch.setenv("BINANCE_COINM_API_KEY", "coinm-live")
    monkeypatch.setenv("BINANCE_COINM_API_SECRET", "coinm-live-secret")
    monkeypatch.setenv("BINANCE_COINM_TESTNET_API_KEY", "coinm-testnet")
    monkeypatch.setenv("BINANCE_COINM_TESTNET_API_SECRET", "coinm-testnet-secret")
    monkeypatch.setattr("requests.get", fake_http.get)
    monkeypatch.setattr("requests.request", fake_http.request)
    module = importlib.import_module("rtlab_core.web.app")
    module = importlib.reload(module)
    return module, TestClient(module.app)


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_execution_endpoints_work_end_to_end(tmp_path: Path, monkeypatch) -> None:
    fake_http = FakeBinanceExecutionHTTP()
    module, client = _build_app(tmp_path, monkeypatch, fake_http)
    admin_token = _login(client, "Wadmin", "moroco123")
    viewer_token = _login(client, "viewer", "viewer123")
    admin_headers = _headers(admin_token)
    viewer_headers = _headers(viewer_token)

    sync = client.post("/api/v1/instruments/registry/sync", headers=admin_headers, json={})
    assert sync.status_code == 200, sync.text
    module.store.execution_reality.refresh_reporting_views(module.store.load_runs())
    module.store.execution_reality.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50010.0)

    preflight = client.post(
        "/api/v1/execution/preflight",
        headers=viewer_headers,
        json={
            "family": "spot",
            "environment": "live",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "market_snapshot": {"bid": 50000.0, "ask": 50010.0, "quote_ts_ms": 9999999999999, "orderbook_ts_ms": 9999999999999},
        },
    )
    assert preflight.status_code == 200, preflight.text
    assert preflight.json()["allowed"] is True

    order = client.post(
        "/api/v1/execution/orders",
        headers=admin_headers,
        json={
            "family": "spot",
            "environment": "live",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "market_snapshot": {"bid": 50000.0, "ask": 50010.0, "quote_ts_ms": 9999999999999, "orderbook_ts_ms": 9999999999999},
        },
    )
    assert order.status_code == 200, order.text
    order_payload = order.json()
    assert order_payload["order_status"] == "FILLED"

    detail = client.get(f"/api/v1/execution/orders/{order_payload['execution_order_id']}", headers=viewer_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["fills"]

    limit_order = client.post(
        "/api/v1/execution/orders",
        headers=admin_headers,
        json={
            "family": "spot",
            "environment": "live",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": {"bid": 50000.0, "ask": 50010.0, "quote_ts_ms": 9999999999999, "orderbook_ts_ms": 9999999999999},
        },
    )
    limit_payload = limit_order.json()
    cancel = client.post(f"/api/v1/execution/orders/{limit_payload['execution_order_id']}/cancel", headers=admin_headers)
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["order"]["order_status"] == "CANCELED"

    module.store.execution_reality.db.upsert_intent(
        {
            "execution_intent_id": "API-ACK",
            "created_at": module.utc_now_iso(),
            "venue": "binance",
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "client_order_id": "api-ack",
            "preflight_status": "ALLOWED",
            "policy_hash": "x",
        }
    )
    module.store.execution_reality.db.upsert_order(
        {
            "execution_order_id": "API-ORDER",
            "execution_intent_id": "API-ACK",
            "client_order_id": "api-ack",
            "symbol": "BTCUSDT",
            "family": "spot",
            "environment": "live",
            "order_status": "NEW",
            "submitted_at": (module.utc_now() - timedelta(seconds=30)).isoformat(),
            "raw_ack": {},
            "raw_last_status": {},
        }
    )
    reconcile = client.get("/api/v1/execution/reconcile/summary", headers=viewer_headers)
    assert reconcile.status_code == 200, reconcile.text
    assert reconcile.json()["ack_missing"] >= 1

    ks_trip = client.post("/api/v1/execution/kill-switch/trip", headers=admin_headers, json={"reason": "api_test"})
    assert ks_trip.status_code == 200, ks_trip.text
    assert ks_trip.json()["armed"] is True

    with module.store.execution_reality.db._connect() as conn:
        conn.execute(
            "UPDATE kill_switch_events SET created_at = ? WHERE cleared_at IS NULL",
            ((module.utc_now() - timedelta(seconds=400)).isoformat(),),
        )
        conn.commit()

    ks_reset = client.post("/api/v1/execution/kill-switch/reset", headers=admin_headers)
    assert ks_reset.status_code == 200, ks_reset.text
    assert ks_reset.json()["armed"] is False

    live_safety = client.get("/api/v1/execution/live-safety/summary", headers=viewer_headers)
    assert live_safety.status_code == 200, live_safety.text
    assert live_safety.json()["overall_status"] in {"OK", "WARN", "BLOCK"}


def test_execution_preflight_live_blocks_when_real_fee_source_missing(tmp_path: Path, monkeypatch) -> None:
    fake_http = FakeBinanceExecutionHTTP()
    module, client = _build_app(tmp_path, monkeypatch, fake_http)
    admin_headers = _headers(_login(client, "Wadmin", "moroco123"))
    viewer_headers = _headers(_login(client, "viewer", "viewer123"))
    sync = client.post("/api/v1/instruments/registry/sync", headers=admin_headers, json={})
    assert sync.status_code == 200, sync.text
    module.store.reporting_bridge.db.replace_cost_source_snapshots([])
    blocked = client.post(
        "/api/v1/execution/preflight",
        headers=viewer_headers,
        json={
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "market_snapshot": {"bid": 50000.0, "ask": 50010.0, "quote_ts_ms": 9999999999999, "orderbook_ts_ms": 9999999999999},
        },
    )
    assert blocked.status_code == 200, blocked.text
    payload = blocked.json()
    assert payload["allowed"] is False
    assert "fee_source_missing_in_live" in payload["blocking_reasons"]
    assert payload["fail_closed"] is True

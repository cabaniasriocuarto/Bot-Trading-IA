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


def _ensure_execution_prereqs(module) -> None:  # noqa: ANN001
    module.store.instrument_registry.sync(startup=False)
    module.store.reporting_bridge.refresh_materialized_views(module.store.load_runs())


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return str(res.json()["token"])


def _paper_execution_payload(*, order_type: str = "LIMIT", price: float | None = 50000.0, quantity: float = 0.01) -> dict[str, object]:
    payload: dict[str, object] = {
        "family": "spot",
        "environment": "paper",
        "mode": "paper",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": order_type,
        "quantity": quantity,
    }
    if price is not None:
        payload["price"] = price
    return payload


def test_config_policies_exposes_execution_bootstrap_metadata(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")

    res = client.get("/api/v1/config/policies", headers=_auth_headers(token))
    assert res.status_code == 200, res.text
    payload = res.json()
    summary = payload["summary"]
    files = payload["files"]

    assert summary["execution_allow_live"] is True
    assert summary["execution_quote_stale_block_ms"] == 3000
    assert "spot" in summary["execution_router_families_enabled"]
    assert summary["execution_router_supported_order_types"]["spot"] == ["MARKET", "LIMIT"]
    assert files["execution_safety"]["valid"] is True
    assert files["execution_router"]["valid"] is True
    assert files["execution_safety"]["source_hash"]
    assert files["execution_router"]["source_hash"]
    assert files["execution_safety"]["policy_hash"]
    assert files["execution_router"]["policy_hash"]
    assert files["execution_safety"]["source_hash"] != files["execution_safety"]["policy_hash"]

    bootstrap = module.store.execution_reality.bootstrap_summary()
    assert bootstrap["policy_loaded"] is True
    assert bootstrap["policy_hash"]
    assert bootstrap["policy_source"]["execution_safety"]["source_hash"]
    assert bootstrap["policy_source"]["execution_safety"]["policy_hash"]
    assert "execution_intents" in bootstrap["tables"]
    assert bootstrap["dependencies"]["instrument_registry_service"] is True


def test_execution_preflight_endpoint_accepts_paper_order(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")

    module.store.execution_reality.set_market_snapshot(
        family="spot",
        environment="paper",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
    )

    res = client.post(
        "/api/v1/execution/preflight",
        headers=_auth_headers(token),
        json={
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.001234,
            "price": 50000.129,
        },
    )

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["allowed"] is True
    assert payload["fail_closed"] is False
    assert payload["normalized_order_preview"]["quantity"] == 0.0012
    assert payload["normalized_order_preview"]["limit_price"] == 50000.12


def test_execution_preflight_endpoint_blocks_live_without_fee_source(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")

    module.store.execution_reality.set_market_snapshot(
        family="spot",
        environment="live",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
    )
    module.store.execution_reality._fee_source_state = lambda family, environment: {  # type: ignore[method-assign]
        "available": False,
        "fresh": False,
        "latest": None,
    }

    res = client.post(
        "/api/v1/execution/preflight",
        headers=_auth_headers(token),
        json={
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
        },
    )

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["allowed"] is False
    assert payload["fail_closed"] is True
    assert "fee_source_missing_in_live" in payload["blocking_reasons"]


def test_execution_live_safety_summary_endpoint_reports_preflight_state(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")

    module.store.execution_reality.set_market_snapshot(
        family="spot",
        environment="live",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
    )
    module.store.execution_reality.mark_user_stream_status(
        family="spot",
        environment="live",
        available=False,
        degraded_reason="rest_fallback",
    )
    module.store.execution_reality._fee_source_state = lambda family, environment: {  # type: ignore[method-assign]
        "available": True,
        "fresh": True,
        "latest": {"family": family, "environment": environment},
    }

    res = client.get("/api/v1/execution/live-safety/summary", headers=_auth_headers(token))
    assert res.status_code == 200, res.text
    payload = res.json()

    assert payload["execution_policy_loaded"] is True
    assert payload["policy_hash"]
    assert payload["policy_source"]["execution_router"]["source_hash"]
    assert payload["policy_source"]["execution_router"]["policy_hash"]
    assert payload["degraded_mode"] is True
    assert payload["capabilities_known"] is True
    assert "spot" in payload["supported_families"]
    assert payload["overall_status"] == "WARN"


def test_execution_orders_create_endpoint_persists_paper_order(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    module.store.execution_reality.set_market_snapshot(
        family="spot",
        environment="paper",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
    )

    res = client.post("/api/v1/execution/orders", headers=_auth_headers(token), json=_paper_execution_payload())

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["order_status"] == "NEW"
    assert payload["execution_intent_id"]
    assert payload["execution_order_id"]
    assert payload["estimated_costs"]["total_cost_estimated"] > 0


def test_execution_orders_list_and_detail_endpoints_return_created_order(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    module.store.execution_reality.set_market_snapshot(
        family="spot",
        environment="paper",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
    )
    created = client.post("/api/v1/execution/orders", headers=_auth_headers(token), json=_paper_execution_payload()).json()

    listed = client.get(
        "/api/v1/execution/orders?family=spot&environment=paper&symbol=BTCUSDT&status=OPEN",
        headers=_auth_headers(token),
    )
    detail = client.get(
        f"/api/v1/execution/orders/{created['execution_order_id']}",
        headers=_auth_headers(token),
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["count"] == 1
    assert detail.status_code == 200, detail.text
    assert detail.json()["order"]["execution_order_id"] == created["execution_order_id"]
    assert detail.json()["intent"]["execution_intent_id"] == created["execution_intent_id"]


def test_execution_orders_cancel_endpoint_cancels_single_order(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    module.store.execution_reality.set_market_snapshot(
        family="spot",
        environment="paper",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
    )
    created = client.post("/api/v1/execution/orders", headers=_auth_headers(token), json=_paper_execution_payload()).json()

    res = client.post(
        f"/api/v1/execution/orders/{created['execution_order_id']}/cancel",
        headers=_auth_headers(token),
    )

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["order_status"] == "CANCELED"


def test_execution_orders_cancel_all_endpoint_cancels_symbol_orders(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    module.store.execution_reality.set_market_snapshot(
        family="spot",
        environment="paper",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
    )
    client.post("/api/v1/execution/orders", headers=_auth_headers(token), json=_paper_execution_payload(price=50000.0))
    client.post("/api/v1/execution/orders", headers=_auth_headers(token), json=_paper_execution_payload(price=50010.0))

    res = client.post(
        "/api/v1/execution/orders/cancel-all",
        headers=_auth_headers(token),
        json={"family": "spot", "environment": "paper", "symbol": "BTCUSDT"},
    )

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["canceled_count"] == 2

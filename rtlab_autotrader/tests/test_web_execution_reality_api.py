from __future__ import annotations

import asyncio
import importlib
import json
import time
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


class _FakeWebSocket:
    def __init__(self, messages: list[object]) -> None:
        self._messages = list(messages)
        self.sent: list[str] = []

    async def __aenter__(self) -> "_FakeWebSocket":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False

    async def recv(self) -> object:
        if self._messages:
            return self._messages.pop(0)
        await asyncio.sleep(3600)
        return ""

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        return None


class _FailingAsyncContextManager:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __aenter__(self):  # noqa: ANN204
        raise self._exc

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False


class _FakeConnectFactory:
    def __init__(self, sessions: list[object]) -> None:
        self._sessions = list(sessions)
        self.calls: list[dict[str, object]] = []

    def __call__(self, url: str, **kwargs):  # noqa: ANN001, ANN204
        self.calls.append({"url": url, "kwargs": kwargs})
        if not self._sessions:
            return _FailingAsyncContextManager(RuntimeError("no_fake_session"))
        next_item = self._sessions.pop(0)
        if isinstance(next_item, Exception):
            return _FailingAsyncContextManager(next_item)
        return next_item


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


def _live_execution_payload(*, price: float = 50000.0, quantity: float = 0.01, bot_id: str = "bot-live-api") -> dict[str, object]:
    return {
        "family": "spot",
        "environment": "live",
        "mode": "live",
        "bot_id": bot_id,
        "strategy_id": "strat-live-api",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "quantity": quantity,
        "price": price,
        "market_snapshot": {
            "bid": 50000.0,
            "ask": 50001.0,
            "quote_ts_ms": int(time.time() * 1000),
            "orderbook_ts_ms": int(time.time() * 1000),
        },
    }


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
    assert summary["execution_exchange_filters_max_age_ms"] == 300000
    assert summary["execution_exchange_filters_missing_symbol_filters"] == "block"
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
    assert payload["allowed"] is False
    assert payload["fail_closed"] is False
    assert "invalid_step_alignment" in payload["blocking_reasons"]
    assert "invalid_tick_alignment" in payload["blocking_reasons"]
    assert payload["normalized_order_preview"]["quantity"] == 0.0012
    assert payload["normalized_order_preview"]["limit_price"] == 50000.12
    assert payload["filter_validation"]["status"] == "BLOCK"


def test_execution_filter_rules_endpoint_returns_family_specific_filters(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")

    res = client.get(
        "/api/v1/execution/filter-rules",
        headers=_auth_headers(token),
        params={"family": "usdm_futures", "environment": "live", "symbol": "BTCUSDT"},
    )

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["family"] == "usdm_futures"
    assert payload["market_family"] == "um_futures"
    assert payload["execution_connector"] == "binance_um_futures"
    assert payload["filter_source"] == "um_futures_exchange_info"
    assert payload["filter_summary"]["market_lot_size"]["step_size"] == "0.001"
    assert payload["max_age_ms"] == 300000


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
    module.store.execution_reality.set_margin_level(environment="live", level=2.0)
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
    assert payload["exchange_filters_fresh"] is True
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
    assert detail.json()["filter_validation"]["status"] == "PASS"
    assert detail.json()["normalized_order_preview"]["quantity"] == 0.01
    assert isinstance(detail.json()["timeline"], list)
    assert detail.json()["current_local_state"] in {"ACKED", "WORKING", "FILLED"}


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


def test_execution_order_detail_endpoint_exposes_fills_and_realized_costs(tmp_path: Path, monkeypatch) -> None:
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

    created = client.post(
        "/api/v1/execution/orders",
        headers=_auth_headers(token),
        json=_paper_execution_payload(order_type="MARKET", price=None),
    ).json()

    detail = client.get(
        f"/api/v1/execution/orders/{created['execution_order_id']}",
        headers=_auth_headers(token),
    )

    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["intent"]["execution_intent_id"] == created["execution_intent_id"]
    assert payload["order"]["execution_order_id"] == created["execution_order_id"]
    assert len(payload["fills"]) == 1
    assert isinstance(payload["reconcile_events"], list)
    assert payload["estimated_costs"]["total_cost_estimated"] > 0
    assert payload["realized_costs"]["cost_classification"] == "mixed"
    assert payload["degraded_mode"] is False


def test_execution_live_orders_endpoints_expose_state_machine_and_timeline(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    module.store.execution_reality._capability_snapshot = lambda family, environment: {  # type: ignore[method-assign]
        "capability_snapshot_id": "CAP-LIVE-OK",
        "capability_source": "test_override",
        "can_trade": True,
    }
    module.store.execution_reality._signed_request = lambda method, endpoint, **kwargs: (  # type: ignore[method-assign]
        {
            "symbol": "BTCUSDT",
            "orderId": 991001,
            "clientOrderId": str((kwargs.get("params") or {}).get("newClientOrderId") or ""),
            "transactTime": int(time.time() * 1000),
            "price": "50000.00",
            "origQty": "0.01000000",
            "executedQty": "0.00000000",
            "cummulativeQuoteQty": "0.00000000",
            "status": "NEW",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "BUY",
        },
        {"ok": True, "reason": "ok"},
    )

    created = client.post("/api/v1/execution/orders", headers=_auth_headers(token), json=_live_execution_payload()).json()
    listed = client.get("/api/v1/execution/live-orders?family=spot&environment=live", headers=_auth_headers(token))
    detail = client.get(f"/api/v1/execution/live-orders/{created['execution_order_id']}", headers=_auth_headers(token))
    timeline = client.get(
        f"/api/v1/execution/live-orders/timeline/{created['execution_order_id']}",
        headers=_auth_headers(token),
    )

    assert listed.status_code == 200, listed.text
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["current_local_state"] == "ACKED"
    assert detail.status_code == 200, detail.text
    assert detail.json()["current_local_state"] in {"ACKED", "WORKING"}
    assert timeline.status_code == 200, timeline.text
    assert len(timeline.json()["timeline"]) >= 4


def test_execution_live_orders_unresolved_and_reconcile_endpoints(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    service = module.store.execution_reality

    intent = service.db.insert_intent(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "strategy_id": "strat-live-api",
            "bot_id": "bot-live-api",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "limit_price": 50000.0,
            "preflight_status": "submitted",
            "submitted_at": "2026-03-20T00:00:00+00:00",
            "policy_hash": service.policy_hash(),
            "raw_request_json": {"market_snapshot": {"bid": 50000.0, "ask": 50001.0}},
        }
    )
    order = service.db.upsert_order(
        {
            "execution_intent_id": intent["execution_intent_id"],
            "bot_id": intent["bot_id"],
            "strategy_id": intent["strategy_id"],
            "client_order_id": intent["client_order_id"],
            "symbol": "BTCUSDT",
            "family": "spot",
            "environment": "live",
            "order_status": "NEW",
            "current_local_state": "UNKNOWN_PENDING_RECONCILIATION",
            "submitted_at": "2026-03-20T00:00:00+00:00",
            "last_event_at": "2026-03-20T00:00:00+00:00",
            "price": 50000.0,
            "orig_qty": 0.01,
            "unresolved_reason": "timeout_unknown",
            "reconciliation_status": "UNRESOLVED",
            "raw_ack_json": {"symbol": "BTCUSDT", "clientOrderId": intent["client_order_id"]},
            "raw_last_status_json": {"status": "NEW", "symbol": "BTCUSDT"},
        }
    )
    service._signed_request = lambda method, endpoint, **kwargs: (  # type: ignore[method-assign]
        {
            "symbol": "BTCUSDT",
            "orderId": 991002,
            "clientOrderId": str((kwargs.get("params") or {}).get("origClientOrderId") or order["client_order_id"]),
            "transactTime": int(time.time() * 1000),
            "price": "50000.00",
            "origQty": "0.01000000",
            "executedQty": "0.00000000",
            "cummulativeQuoteQty": "0.00000000",
            "status": "NEW",
            "timeInForce": "GTC",
            "type": "LIMIT",
            "side": "BUY",
        },
        {"ok": True, "reason": "ok"},
    )

    unresolved = client.get("/api/v1/execution/live-orders/unresolved?environment=live", headers=_auth_headers(token))
    reconcile = client.post(
        "/api/v1/execution/live-orders/reconcile",
        headers=_auth_headers(token),
        json={"execution_order_id": order["execution_order_id"], "environment": "live", "trigger": "MANUAL"},
    )
    detail = client.get(f"/api/v1/execution/live-orders/{order['execution_order_id']}", headers=_auth_headers(token))

    assert unresolved.status_code == 200, unresolved.text
    assert unresolved.json()["count"] == 1
    assert reconcile.status_code == 200, reconcile.text
    assert reconcile.json()["reconciliation_run"]["trigger"] == "MANUAL"
    assert detail.status_code == 200, detail.text
    assert detail.json()["current_local_state"] in {"RECOVERED_OPEN", "WORKING"}


def test_execution_reconcile_summary_endpoint_reports_degraded_mode(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")

    service = module.store.execution_reality
    intent = service.db.insert_intent(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "limit_price": 50000.0,
            "requested_notional": 500.0,
            "estimated_fee": 0.25,
            "estimated_slippage_bps": 6.0,
            "estimated_total_cost": 0.75,
            "preflight_status": "submitted",
            "submitted_at": "2026-03-19T10:00:00+00:00",
            "policy_hash": service.policy_hash(),
            "raw_request_json": {"market_snapshot": {"bid": 50000.0, "ask": 50001.0}},
        }
    )
    service.db.upsert_order(
        {
            "execution_intent_id": intent["execution_intent_id"],
            "client_order_id": intent["client_order_id"],
            "venue_order_id": "123456",
            "symbol": "BTCUSDT",
            "family": "spot",
            "environment": "live",
            "order_status": "NEW",
            "submitted_at": "2026-03-19T10:00:00+00:00",
            "acknowledged_at": None,
            "price": 50000.0,
            "orig_qty": 0.01,
            "raw_ack_json": {"side": "BUY", "type": "LIMIT", "symbol": "BTCUSDT", "price": 50000.0, "origQty": 0.01},
            "raw_last_status_json": {"status": "NEW", "symbol": "BTCUSDT"},
        }
    )
    service.mark_user_stream_status(family="spot", environment="live", available=False, degraded_reason="rest_fallback")
    service._signed_request = lambda *args, **kwargs: (None, {"ok": False, "reason": "missing_credentials"})  # type: ignore[method-assign]

    res = client.get("/api/v1/execution/reconcile/summary", headers=_auth_headers(token))

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["degraded_mode"] is True
    assert payload["ack_missing"] == 1
    assert payload["policy_source"]["execution_safety"]["source_hash"]


def test_execution_kill_switch_trip_status_reset_endpoints(tmp_path: Path, monkeypatch) -> None:
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

    tripped = client.post(
        "/api/v1/execution/kill-switch/trip",
        headers=_auth_headers(token),
        json={"reason": "manual_trip", "trigger_type": "manual", "severity": "BLOCK", "family": "spot", "symbol": "BTCUSDT"},
    )
    status = client.get("/api/v1/execution/kill-switch/status", headers=_auth_headers(token))
    blocked = client.post("/api/v1/execution/orders", headers=_auth_headers(token), json=_paper_execution_payload())
    reset = client.post(
        "/api/v1/execution/kill-switch/reset",
        headers=_auth_headers(token),
        json={"reason": "operator_reset"},
    )

    assert tripped.status_code == 200, tripped.text
    assert tripped.json()["active"] is True
    assert tripped.json()["auto_actions"][0]["canceled_count"] == 2
    assert status.status_code == 200, status.text
    assert status.json()["active"] is True
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["order_status"] == "BLOCKED"
    assert "kill_switch_active" in blocked.json()["blocking_reasons"]
    assert reset.status_code == 200, reset.text
    assert reset.json()["active"] is False
    assert reset.json()["cooldown_active"] is True
    assert reset.json()["last_event"]["cleared_reason"] == "operator_reset"


def test_execution_market_stream_endpoints_start_summary_stop(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    fake_ws = _FakeWebSocket(
        [
            json.dumps(
                {
                    "stream": "btcusdt@bookTicker",
                    "data": {
                        "e": "bookTicker",
                        "E": int(__import__("time").time() * 1000),
                        "s": "BTCUSDT",
                        "b": "50000.10",
                        "a": "50000.20",
                    },
                }
            )
        ]
    )
    module.store.execution_reality._market_ws_runtime._connect_factory = _FakeConnectFactory([fake_ws])  # type: ignore[attr-defined]

    started = client.post(
        "/api/v1/execution/market-streams/start",
        headers=_auth_headers(token),
        json={
            "execution_connector": "binance_spot",
            "environment": "live",
            "symbols": ["BTCUSDT"],
            "transport_mode": "combined",
        },
    )
    deadline = time.time() + 3.0
    summary = None
    while time.time() < deadline:
        res = client.get("/api/v1/execution/market-streams/summary", headers=_auth_headers(token))
        if res.status_code == 200 and (res.json().get("sessions") or []):
            summary = res.json()
            break
        time.sleep(0.05)
    stopped = client.post(
        "/api/v1/execution/market-streams/stop",
        headers=_auth_headers(token),
        json={"execution_connector": "binance_spot", "environment": "live"},
    )
    safety = client.get("/api/v1/execution/live-safety/summary", headers=_auth_headers(token))

    assert started.status_code == 200, started.text
    assert summary is not None
    assert summary["policy_loaded"] is True
    assert summary["family_split"]["binance_spot"]["repo_family"] == "spot"
    assert summary["sessions"][0]["execution_connector"] == "binance_spot"
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["reason"] == "stopped_by_operator"
    assert safety.status_code == 200, safety.text
    assert safety.json()["market_stream_runtime"]["policy_source"]["source_hash"]


def test_execution_user_stream_endpoints_start_summary_stop(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    module.store.execution_reality._binance_adapter.signed_websocket_params = lambda **kwargs: (  # type: ignore[attr-defined,method-assign]
        {
            "apiKey": "spot-key",
            "timestamp": int(time.time() * 1000),
            "recvWindow": 5000,
            "signature": "deadbeef",
        },
        {"ok": True, "reason": "ok"},
    )
    fake_ws = _FakeWebSocket(
        [
            json.dumps({"id": "sub-1", "status": 200, "result": {"subscriptionId": 3}}),
            json.dumps(
                {
                    "subscriptionId": 3,
                    "event": {
                        "e": "outboundAccountPosition",
                        "E": int(time.time() * 1000),
                        "u": int(time.time() * 1000),
                        "B": [{"a": "USDT", "f": "100.0", "l": "0.0"}],
                    },
                }
            ),
        ]
    )
    module.store.execution_reality._user_stream_runtime._connect_factory = _FakeConnectFactory([fake_ws])  # type: ignore[attr-defined]

    started = client.post(
        "/api/v1/execution/user-streams/start",
        headers=_auth_headers(token),
        json={
            "execution_connector": "binance_spot",
            "environment": "live",
            "user_stream_mode": "websocket_api_spot",
        },
    )
    deadline = time.time() + 3.0
    summary = None
    while time.time() < deadline:
        res = client.get("/api/v1/execution/user-streams/summary", headers=_auth_headers(token))
        if res.status_code == 200 and (res.json().get("sessions") or []):
            summary = res.json()
            break
        time.sleep(0.05)
    stopped = client.post(
        "/api/v1/execution/user-streams/stop",
        headers=_auth_headers(token),
        json={"execution_connector": "binance_spot", "environment": "live"},
    )
    safety = client.get("/api/v1/execution/live-safety/summary", headers=_auth_headers(token))

    assert started.status_code == 200, started.text
    assert summary is not None
    assert summary["policy_loaded"] is True
    assert summary["family_split"]["binance_spot"]["user_stream_default_mode"] == "websocket_api_spot"
    assert summary["sessions"][0]["subscription_id"] == 3
    assert stopped.status_code == 200, stopped.text
    assert stopped.json()["reason"] == "stopped_by_operator"
    assert safety.status_code == 200, safety.text
    assert safety.json()["user_stream_runtime"]["policy_source"]["source_hash"]


def test_execution_live_safety_summary_endpoint_reports_final_guardrails(tmp_path: Path, monkeypatch) -> None:
    module, client = _build_app(tmp_path, monkeypatch)
    _ensure_execution_prereqs(module)
    token = _login(client, "Wadmin", "moroco123")
    old_ms = int(__import__("time").time() * 1000) - 10000
    module.store.execution_reality.set_market_snapshot(
        family="spot",
        environment="live",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
        quote_ts_ms=old_ms,
        orderbook_ts_ms=old_ms,
    )
    module.store.execution_reality.mark_user_stream_status(
        family="spot",
        environment="live",
        available=False,
        degraded_reason="rest_fallback",
    )
    module.store.execution_reality._fee_source_state = lambda family, environment: {  # type: ignore[method-assign]
        "available": False,
        "fresh": False,
        "latest": {"family": family, "environment": environment},
    }
    module.store.execution_reality.trip_kill_switch(
        trigger_type="manual",
        severity="BLOCK",
        family="spot",
        symbol="BTCUSDT",
        reason="manual_trip",
    )

    res = client.get("/api/v1/execution/live-safety/summary", headers=_auth_headers(token))

    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["kill_switch_active"] is True
    assert payload["stale_market_data"] is True
    assert payload["fee_source_fresh"] is False
    assert payload["degraded_mode"] is True
    assert payload["overall_status"] == "BLOCK"
    assert "kill_switch_active" in payload["safety_blockers"]
    assert "cost_source_missing_blocker" in payload["safety_blockers"]

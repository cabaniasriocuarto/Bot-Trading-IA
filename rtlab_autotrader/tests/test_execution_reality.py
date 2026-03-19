from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rtlab_core.execution.reality import ExecutionRealityService, utc_now_iso
from rtlab_core.instruments import BinanceInstrumentRegistryService
from rtlab_core.reporting import ReportingBridgeService
from rtlab_core.universe import InstrumentUniverseService


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
        if "/myTrades" in url or "/userTrades" in url:
            return _FakeResponse([])
        if "/income" in url:
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
            price = float(params.get("price") or (50010.0 if str(params.get("symbol")) == "BTCUSDT" else 68000.0))
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


def _seed_credentials(monkeypatch) -> None:  # noqa: ANN001
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


def _build_services(tmp_path: Path, monkeypatch, *, seed_cost_sources: bool = True):  # noqa: ANN001
    repo_root = Path(__file__).resolve().parents[2]
    fake_http = FakeBinanceExecutionHTTP()
    _seed_credentials(monkeypatch)
    monkeypatch.setattr("requests.get", fake_http.get)
    monkeypatch.setattr("requests.request", fake_http.request)
    user_data_dir = tmp_path / "user_data"
    runs_path = user_data_dir / "backtests" / "runs.json"
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    runs_path.write_text("[]", encoding="utf-8")

    registry = BinanceInstrumentRegistryService(
        db_path=user_data_dir / "instruments" / "registry.sqlite3",
        repo_root=repo_root,
        explicit_policy_root=repo_root / "config" / "policies",
    )
    registry.sync()
    universes = InstrumentUniverseService(registry)
    reporting = ReportingBridgeService(
        user_data_dir=user_data_dir,
        repo_root=repo_root,
        explicit_policy_root=repo_root / "config" / "policies",
        instrument_registry_service=registry,
        runs_path=runs_path,
    )
    execution = ExecutionRealityService(
        user_data_dir=user_data_dir,
        repo_root=repo_root,
        explicit_policy_root=repo_root / "config" / "policies",
        instrument_registry_service=registry,
        universe_service=universes,
        reporting_bridge_service=reporting,
        runs_loader=lambda: [],
    )
    if seed_cost_sources:
        execution.refresh_reporting_views([])
    execution.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50010.0)
    execution.set_market_snapshot(family="usdm_futures", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50010.0)
    execution.set_margin_level(environment="live", level=2.0)
    return execution, reporting, registry, fake_http


def test_preflight_valid_order_normalizes_filters_and_warns_slippage(tmp_path: Path, monkeypatch) -> None:
    execution, _, _, _ = _build_services(tmp_path, monkeypatch)
    payload = execution.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.0123456,
            "price": 50000.127,
            "slippage_bps": 12.0,
        }
    )
    assert payload["allowed"] is True
    assert payload["normalized_order_preview"]["quantity"] == 0.0123
    assert payload["normalized_order_preview"]["limit_price"] == 50000.12
    assert "slippage_warn_threshold" in payload["warnings"]


def test_preflight_blocks_stale_market_data_and_missing_fee_source_live(tmp_path: Path, monkeypatch) -> None:
    execution, _, _, _ = _build_services(tmp_path, monkeypatch, seed_cost_sources=False)
    stale_ms = int(time.time() * 1000) - 10_000
    payload = execution.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "market_snapshot": {
                "bid": 50000.0,
                "ask": 50010.0,
                "quote_ts_ms": stale_ms,
                "orderbook_ts_ms": stale_ms,
            },
        }
    )
    assert payload["allowed"] is False
    assert "quote_stale" in payload["blocking_reasons"]
    assert "fee_source_missing_in_live" in payload["blocking_reasons"]
    assert payload["fail_closed"] is True


def test_preflight_blocks_max_notional_and_open_order_limit(tmp_path: Path, monkeypatch) -> None:
    execution, _, _, _ = _build_services(tmp_path, monkeypatch)
    too_big = execution.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 1.0,
        }
    )
    assert "max_notional_per_order_exceeded" in too_big["blocking_reasons"]

    for idx in range(6):
        execution.db.upsert_intent(
            {
                "execution_intent_id": f"OPEN-{idx}",
                "created_at": utc_now_iso(),
                "venue": "binance",
                "family": "spot",
                "environment": "live",
                "mode": "paper",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "client_order_id": f"open-{idx}",
                "preflight_status": "ALLOWED",
                "policy_hash": "x",
            }
        )
        execution.db.upsert_order(
            {
                "execution_order_id": f"OPEN-ORDER-{idx}",
                "execution_intent_id": f"OPEN-{idx}",
                "client_order_id": f"open-{idx}",
                "symbol": "BTCUSDT",
                "family": "spot",
                "environment": "live",
                "order_status": "NEW",
                "submitted_at": utc_now_iso(),
                "raw_ack": {},
                "raw_last_status": {},
            }
        )
    execution.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50010.0)
    blocked = execution.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
        }
    )
    assert "max_open_orders_per_symbol_reached" in blocked["blocking_reasons"]


def test_kill_switch_trip_reset_and_reconcile_detection(tmp_path: Path, monkeypatch) -> None:
    execution, _, _, _ = _build_services(tmp_path, monkeypatch)
    trip = execution.trip_kill_switch(trigger_type="manual_trip", reason="test")
    assert trip["armed"] is True

    with execution.db._connect() as conn:
        conn.execute(
            "UPDATE kill_switch_events SET created_at = ? WHERE cleared_at IS NULL",
            ((datetime.now(timezone.utc) - timedelta(seconds=400)).isoformat(),),
        )
        conn.commit()

    reset = execution.reset_kill_switch()
    assert reset["armed"] is False

    intent = execution.db.upsert_intent(
        {
            "execution_intent_id": "XIN-ACK",
            "created_at": utc_now_iso(),
            "venue": "binance",
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "client_order_id": "ack-missing",
            "preflight_status": "ALLOWED",
            "policy_hash": "x",
        }
    )
    execution.db.upsert_order(
        {
            "execution_order_id": "XOR-ACK",
            "execution_intent_id": intent["execution_intent_id"],
            "client_order_id": "ack-missing",
            "symbol": "BTCUSDT",
            "family": "spot",
            "environment": "live",
            "order_status": "NEW",
            "submitted_at": (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat(),
            "raw_ack": {},
            "raw_last_status": {},
        }
    )
    execution.db.upsert_order(
        {
            "execution_order_id": "XOR-FILL",
            "execution_intent_id": intent["execution_intent_id"],
            "client_order_id": "fill-missing",
            "symbol": "BTCUSDT",
            "family": "spot",
            "environment": "live",
            "order_status": "FILLED",
            "submitted_at": utc_now_iso(),
            "acknowledged_at": utc_now_iso(),
            "raw_ack": {},
            "raw_last_status": {},
        }
    )
    summary = execution.reconcile_orders()
    assert summary["ack_missing"] >= 1
    assert summary["fill_missing"] >= 1


def test_paper_fill_materializes_reporting_rows_and_gross_net_consistency(tmp_path: Path, monkeypatch) -> None:
    execution, reporting, _, _ = _build_services(tmp_path, monkeypatch)
    created = execution.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
        }
    )
    assert created["order_status"] == "FILLED"
    detail = execution.order_detail(created["execution_order_id"])
    assert detail is not None
    assert detail["fills"]
    trades = reporting.db.trade_rows()
    execution_rows = [row for row in trades if str((row.get("provenance") or {}).get("source_kind") or "") == "execution_reality_fill"]
    assert execution_rows
    row = execution_rows[-1]
    effective_total = float(row["total_cost_realized"] or row["total_cost_estimated"])
    assert round(row["gross_pnl"] - effective_total, 8) == round(row["net_pnl"], 8)
    assert (row["cost_source"] or {}).get("cost_classification") in {"estimated_only", "realized"}


def test_live_futures_arms_auto_cancel_and_degraded_mode_fallback(tmp_path: Path, monkeypatch) -> None:
    execution, _, _, fake_http = _build_services(tmp_path, monkeypatch)
    created = execution.create_order(
        {
            "family": "usdm_futures",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
        }
    )
    assert created["order_status"] == "NEW"
    assert any("countdownCancelAll" in str(row["url"]) for row in fake_http.requests)
    summary = execution.reconcile_orders()
    assert summary["unresolved_count"] >= 0
    safety = execution.live_safety_summary()
    assert safety["degraded_mode"] is True

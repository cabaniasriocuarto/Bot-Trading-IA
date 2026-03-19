from __future__ import annotations

import importlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
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
                },
                {
                    "symbol": "ETHUPUSDT",
                    "status": "TRADING",
                    "baseAsset": "ETHUP",
                    "quoteAsset": "USDT",
                    "permissions": ["SPOT"],
                    "permissionSets": [["SPOT"]],
                    "isSpotTradingAllowed": True,
                    "isMarginTradingAllowed": False,
                    "filters": [
                        {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                        {"filterType": "LOT_SIZE", "minQty": "0.01", "maxQty": "100000", "stepSize": "0.01"},
                    ],
                },
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

    def remove_primary_spot_symbol(self) -> None:
        self.spot_payload = {
            **self.spot_payload,
            "symbols": [row for row in self.spot_payload["symbols"] if row["symbol"] != "BTCUSDT"],
        }

    def get(self, url: str, headers=None, timeout=None):  # noqa: ANN001
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


def _build_app(tmp_path: Path, monkeypatch, fake_http: FakeBinanceHTTP):
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

    module = importlib.import_module("rtlab_core.web.app")
    module = importlib.reload(module)
    return module, TestClient(module.app)


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient) -> str:
    response = client.post("/api/v1/auth/login", json={"username": "Wadmin", "password": "moroco123"})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def test_registry_summary_universes_and_capabilities_endpoints_expose_counts(tmp_path: Path, monkeypatch) -> None:
    fake_http = FakeBinanceHTTP()
    _module, client = _build_app(tmp_path, monkeypatch, fake_http)
    token = _login(client)
    headers = _auth_headers(token)

    sync = client.post("/api/v1/instruments/registry/sync", headers=headers, json={})
    assert sync.status_code == 200, sync.text
    assert sync.json()["ok"] is True

    summary = client.get("/api/v1/instruments/registry/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    summary_payload = summary.json()
    assert summary_payload["total_instruments"] == 5
    assert summary_payload["by_family"]["spot"] == 2
    assert summary_payload["by_family"]["margin"] == 1
    assert summary_payload["live_parity_base_ready"]["spot"]["live"]["live_parity_base_ready"] is True

    universes = client.get("/api/v1/instruments/universes", headers=headers)
    assert universes.status_code == 200, universes.text
    universe_items = {row["name"]: row for row in universes.json()["items"]}
    assert universe_items["core_spot_usdt"]["size"] == 1
    assert universe_items["core_margin_usdt"]["size"] == 1
    assert universe_items["core_usdm_perps"]["size"] == 1

    capabilities = client.get("/api/v1/account/capabilities/summary", headers=headers)
    assert capabilities.status_code == 200, capabilities.text
    capability_payload = capabilities.json()["families"]
    assert capability_payload["margin"]["live"]["can_margin"] is True
    assert capability_payload["spot"]["can_testnet"] is True
    assert capability_payload["margin"]["can_testnet"] is False


def test_sync_endpoint_registers_snapshot_and_diff(tmp_path: Path, monkeypatch) -> None:
    fake_http = FakeBinanceHTTP()
    _module, client = _build_app(tmp_path, monkeypatch, fake_http)
    token = _login(client)
    headers = _auth_headers(token)

    first_sync = client.post(
        "/api/v1/instruments/registry/sync",
        headers=headers,
        json={"family": "spot", "environment": "live"},
    )
    assert first_sync.status_code == 200, first_sync.text
    assert first_sync.json()["ok"] is True

    fake_http.remove_primary_spot_symbol()
    second_sync = client.post(
        "/api/v1/instruments/registry/sync",
        headers=headers,
        json={"family": "spot", "environment": "live"},
    )
    assert second_sync.status_code == 200, second_sync.text
    assert second_sync.json()["ok"] is True

    snapshots = client.get(
        "/api/v1/instruments/registry/snapshots?family=spot&environment=live",
        headers=headers,
    )
    assert snapshots.status_code == 200, snapshots.text
    latest = snapshots.json()["items"][0]
    assert latest["diff_summary"]["symbol_count_before"] == 2
    assert latest["diff_summary"]["symbol_count_after"] == 1
    assert latest["diff_summary"]["removed_live_eligible_count"] == 1
    assert latest["diff_severity"] == "BLOCK"


def test_startup_sync_force_and_stale_snapshot_blocks_live_parity(tmp_path: Path, monkeypatch) -> None:
    fake_http = FakeBinanceHTTP()
    module, client = _build_app(tmp_path, monkeypatch, fake_http)
    token = _login(client)
    headers = _auth_headers(token)

    startup_result = module.store.instrument_registry.sync_on_startup(force=True)
    assert startup_result["ok"] is True

    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=100)).isoformat()
    db_path = module.store.instrument_registry.db.db_path
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE instrument_catalog_snapshots
            SET fetched_at = ?
            WHERE family = 'spot'
              AND environment = 'live'
              AND success = 1
            """,
            (stale_ts,),
        )
        conn.commit()

    summary = client.get("/api/v1/instruments/registry/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    spot_live = summary.json()["live_parity_base_ready"]["spot"]["live"]
    assert spot_live["snapshot_fresh"] is False
    assert spot_live["live_parity_base_ready"] is False

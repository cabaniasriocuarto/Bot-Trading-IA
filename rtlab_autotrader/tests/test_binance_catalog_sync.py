from __future__ import annotations

from pathlib import Path

from rtlab_core.brokers.binance.catalog import BinanceCatalogSyncService, diff_instrument_snapshots
from rtlab_core.strategy_packs.registry_db import RegistryDB


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.text = str(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeSession:
    def __init__(self, mapping: dict[str, dict]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    def get(self, url: str, timeout: int = 20):  # noqa: ARG002
        self.calls.append(url)
        for key, payload in self.mapping.items():
            if url.endswith(key):
                return _FakeResponse(payload)
        raise AssertionError(f"URL no esperada: {url}")


def _spot_payload() -> dict:
    return {
        "timezone": "UTC",
        "serverTime": 0,
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "baseAssetPrecision": 8,
                "quotePrecision": 8,
                "orderTypes": ["LIMIT", "MARKET"],
                "isSpotTradingAllowed": True,
                "isMarginTradingAllowed": True,
                "permissions": ["SPOT", "MARGIN"],
                "permissionSets": [["SPOT", "MARGIN"]],
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.00010000", "maxQty": "9000.00000000", "stepSize": "0.00010000"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"},
                ],
            },
            {
                "symbol": "ETHUSDT",
                "status": "TRADING",
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "baseAssetPrecision": 8,
                "quotePrecision": 8,
                "orderTypes": ["LIMIT", "MARKET"],
                "isSpotTradingAllowed": True,
                "isMarginTradingAllowed": False,
                "permissions": ["SPOT"],
                "permissionSets": [["SPOT"]],
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "0.00100000", "maxQty": "9000.00000000", "stepSize": "0.00100000"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"},
                ],
            },
        ],
    }


def _usdm_payload() -> dict:
    return {
        "timezone": "UTC",
        "serverTime": 0,
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "marginAsset": "USDT",
                "pricePrecision": 2,
                "quantityPrecision": 3,
                "onboardDate": 1700000000000,
                "deliveryDate": 4133404800000,
                "orderTypes": ["LIMIT", "MARKET", "STOP"],
                "timeInForce": ["GTC", "IOC"],
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "maxQty": "1000", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            }
        ],
    }


def _coinm_payload() -> dict:
    return {
        "timezone": "UTC",
        "serverTime": 0,
        "symbols": [
            {
                "symbol": "BTCUSD_PERP",
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "baseAsset": "BTC",
                "quoteAsset": "USD",
                "marginAsset": "BTC",
                "pricePrecision": 1,
                "quantityPrecision": 0,
                "onboardDate": 1700000000000,
                "deliveryDate": 4133404800000,
                "orderTypes": ["LIMIT", "MARKET", "STOP"],
                "timeInForce": ["GTC", "IOC"],
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                    {"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "10000", "stepSize": "1"},
                    {"filterType": "MIN_NOTIONAL", "notional": "100"},
                ],
            }
        ],
    }


def test_binance_catalog_sync_persists_four_market_families(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite3")
    service = BinanceCatalogSyncService(
        registry,
        policies_root=Path("config/policies"),
        session=_FakeSession(
            {
                "/api/v3/exchangeInfo": _spot_payload(),
                "/fapi/v1/exchangeInfo": _usdm_payload(),
                "/dapi/v1/exchangeInfo": _coinm_payload(),
            }
        ),
    )

    payload = service.sync_all(reason="test")

    assert payload["ok"] is True
    assert payload["results"]["spot"]["instrument_count"] == 2
    assert payload["results"]["margin"]["instrument_count"] == 1
    assert payload["results"]["usdm_futures"]["instrument_count"] == 1
    assert payload["results"]["coinm_futures"]["instrument_count"] == 1

    spot_items = service.list_instruments(provider_market="spot", tradable=True)
    assert {item["provider_symbol"] for item in spot_items} == {"BTCUSDT", "ETHUSDT"}

    margin_items = service.list_instruments(provider_market="margin", tradable=True)
    assert len(margin_items) == 1
    assert margin_items[0]["provider_symbol"] == "BTCUSDT"
    assert "MARGIN" in margin_items[0]["permissions"]

    usdm = service.list_instruments(provider_market="usdm_futures")[0]
    assert usdm["normalized_symbol"] == "BTCUSDT-PERP"
    assert usdm["margin_asset"] == "USDT"

    coinm = service.list_instruments(provider_market="coinm_futures")[0]
    assert coinm["provider_symbol"] == "BTCUSD_PERP"
    assert coinm["margin_asset"] == "BTC"


def test_diff_instrument_snapshots_detects_added_removed_and_changed() -> None:
    previous = [
        {"instrument_id": "binance:spot:BTCUSDT", "normalized_symbol": "BTCUSDT", "status": "TRADING"},
        {"instrument_id": "binance:spot:ETHUSDT", "normalized_symbol": "ETHUSDT", "status": "TRADING"},
    ]
    current = [
        {"instrument_id": "binance:spot:BTCUSDT", "normalized_symbol": "BTCUSDT", "status": "BREAK"},
        {"instrument_id": "binance:spot:BNBUSDT", "normalized_symbol": "BNBUSDT", "status": "TRADING"},
    ]

    diff = diff_instrument_snapshots(previous, current)

    assert diff["added"] == ["binance:spot:BNBUSDT"]
    assert diff["removed"] == ["binance:spot:ETHUSDT"]
    assert diff["changed"] == ["binance:spot:BTCUSDT"]

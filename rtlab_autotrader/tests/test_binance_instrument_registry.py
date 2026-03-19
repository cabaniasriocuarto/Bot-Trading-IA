from __future__ import annotations

from pathlib import Path

from rtlab_core.instruments.registry import (
    BinanceInstrumentRegistryService,
    derive_margin_catalog_from_spot,
    diff_snapshot_items,
    instrument_registry_policy,
    parse_coinm_exchange_info,
    parse_spot_exchange_info,
    parse_usdm_exchange_info,
)
from rtlab_core.universe.service import InstrumentUniverseService


def _spot_exchange_info() -> dict:
    return {
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


def _usdm_exchange_info() -> dict:
    return {
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


def _coinm_exchange_info(*, delivery_ms: int = 4133404800000, contract_type: str = "PERPETUAL") -> dict:
    return {
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
                "contractType": contract_type,
                "triggerProtect": "0.0500",
                "deliveryDate": delivery_ms,
                "onboardDate": 1704067200000,
                "filters": [
                    {"filterType": "PRICE_FILTER", "minPrice": "0.1", "maxPrice": "1000000", "tickSize": "0.1"},
                    {"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "100000", "stepSize": "1"},
                    {"filterType": "MARKET_LOT_SIZE", "minQty": "1", "maxQty": "100000", "stepSize": "1"},
                ],
            }
        ],
    }


def test_parse_spot_exchange_info_extracts_filters_permissions_and_eligibility() -> None:
    items = parse_spot_exchange_info(_spot_exchange_info(), environment="live", policy=instrument_registry_policy())

    assert len(items) == 2
    btc = next(item for item in items if item["symbol"] == "BTCUSDT")
    assert btc["live_eligible"] is True
    assert btc["paper_eligible"] is True
    assert btc["filter_summary"]["price_filter"]["tick_size"] == "0.01"
    assert btc["filter_summary"]["min_notional"]["min_notional"] == "10.0"
    assert btc["permission_summary"]["permissions"] == ["SPOT", "MARGIN"]
    assert btc["permission_summary"]["permission_sets"] == [["SPOT", "MARGIN"]]


def test_parse_usdm_and_coinm_exchange_info_extract_metadata() -> None:
    usdm_items = parse_usdm_exchange_info(_usdm_exchange_info(), environment="testnet", policy=instrument_registry_policy())
    coinm_items = parse_coinm_exchange_info(_coinm_exchange_info(), environment="testnet", policy=instrument_registry_policy())

    assert usdm_items[0]["contract_type"] == "PERPETUAL"
    assert usdm_items[0]["filter_summary"]["market_lot_size"]["step_size"] == "0.001"
    assert usdm_items[0]["testnet_eligible"] is True
    assert coinm_items[0]["margin_asset"] == "BTC"
    assert coinm_items[0]["filter_summary"]["trigger_protect"]["value"] == "0.0500"
    assert coinm_items[0]["testnet_eligible"] is True


def test_derive_margin_from_spot_permissions_and_capability() -> None:
    spot_items = parse_spot_exchange_info(_spot_exchange_info(), environment="live", policy=instrument_registry_policy())
    margin_items = derive_margin_catalog_from_spot(
        spot_items,
        environment="live",
        policy=instrument_registry_policy(),
        account_capability={"can_margin": True},
    )

    assert [item["symbol"] for item in margin_items] == ["BTCUSDT"]
    assert margin_items[0]["permission_summary"]["account_margin_capable"] is True
    assert margin_items[0]["live_eligible"] is True


def test_coinm_delivery_contract_near_expiry_not_live_eligible() -> None:
    near_expiry_payload = _coinm_exchange_info(delivery_ms=1, contract_type="CURRENT_QUARTER")
    items = parse_coinm_exchange_info(near_expiry_payload, environment="live", policy=instrument_registry_policy())

    assert items[0]["live_eligible"] is False
    assert "delivery_too_close_or_expired" in items[0]["consistency_errors"]


def test_diff_snapshot_items_detects_blocking_removals() -> None:
    before = parse_spot_exchange_info(_spot_exchange_info(), environment="live", policy=instrument_registry_policy())
    after = [before[1]]

    diff = diff_snapshot_items(before, after, policy=instrument_registry_policy())

    assert diff["symbols_removed"] == 1
    assert diff["removed_live_eligible_count"] == 1
    assert diff["severity"] == "BLOCK"


def test_universe_service_filters_by_family_and_excludes_leveraged_tokens(tmp_path: Path) -> None:
    service = BinanceInstrumentRegistryService(db_path=tmp_path / "instrument_registry.sqlite3")
    policy_hash = str(service.policy_source().get("hash") or "")

    spot_items = parse_spot_exchange_info(_spot_exchange_info(), environment="live", policy=instrument_registry_policy())
    margin_items = derive_margin_catalog_from_spot(
        spot_items,
        environment="live",
        policy=instrument_registry_policy(),
        account_capability={"can_margin": True},
    )
    usdm_items = parse_usdm_exchange_info(_usdm_exchange_info(), environment="live", policy=instrument_registry_policy())
    coinm_items = parse_coinm_exchange_info(_coinm_exchange_info(), environment="live", policy=instrument_registry_policy())

    service.db.save_snapshot(
        family="spot",
        environment="live",
        source_endpoint="https://api.binance.com/api/v3/exchangeInfo",
        raw_payload=_spot_exchange_info(),
        items=spot_items,
        policy_hash=policy_hash,
    )
    service.db.save_snapshot(
        family="margin",
        environment="live",
        source_endpoint="derived:spot:/api/v3/exchangeInfo",
        raw_payload={"derived": True},
        items=margin_items,
        policy_hash=policy_hash,
    )
    service.db.save_snapshot(
        family="usdm_futures",
        environment="live",
        source_endpoint="https://fapi.binance.com/fapi/v1/exchangeInfo",
        raw_payload=_usdm_exchange_info(),
        items=usdm_items,
        policy_hash=policy_hash,
    )
    service.db.save_snapshot(
        family="coinm_futures",
        environment="live",
        source_endpoint="https://dapi.binance.com/dapi/v1/exchangeInfo",
        raw_payload=_coinm_exchange_info(),
        items=coinm_items,
        policy_hash=policy_hash,
    )
    service.db.save_capability_snapshot(
        family="margin",
        environment="live",
        can_read_market_data=True,
        can_trade=True,
        can_margin=True,
        can_user_data=True,
        can_testnet=False,
        capability_source="test",
        notes={},
    )

    universes = InstrumentUniverseService(service).summary()["items"]
    spot_universe = next(item for item in universes if item["name"] == "core_spot_usdt")
    margin_universe = next(item for item in universes if item["name"] == "core_margin_usdt")
    usdm_universe = next(item for item in universes if item["name"] == "core_usdm_perps")

    assert spot_universe["size"] == 1
    assert spot_universe["sample_symbols"] == ["BTCUSDT"]
    assert margin_universe["size"] == 1
    assert usdm_universe["size"] == 1

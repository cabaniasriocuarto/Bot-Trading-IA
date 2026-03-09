from __future__ import annotations

from pathlib import Path

from rtlab_core.instruments.registry import InstrumentCatalogStore, build_instrument_id
from rtlab_core.strategy_packs.registry_db import RegistryDB


def test_instrument_registry_persists_records_and_catalog_snapshots(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite3")
    store = InstrumentCatalogStore(registry)

    btc_spot = {
        "provider": "binance",
        "provider_market": "spot",
        "provider_symbol": "BTCUSDT",
        "normalized_symbol": "BTCUSDT",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "asset_class": "crypto",
        "instrument_type": "spot",
        "status": "TRADING",
        "tradable": True,
        "backtestable": True,
        "paper_enabled": True,
        "test_enabled": True,
        "demo_enabled": True,
        "live_enabled": True,
        "permissions": ["SPOT"],
        "order_types": ["LIMIT", "MARKET"],
        "time_in_force": ["GTC", "IOC"],
        "tick_size": 0.01,
        "step_size": 0.00001,
        "min_qty": 0.0001,
        "min_notional": 10.0,
        "price_precision": 2,
        "qty_precision": 5,
        "exchange_filters": {"minNotional": 10.0},
        "symbol_filters": {"lotSize": 0.00001},
        "account_eligibility": {"live_enabled_reason": "permisos_ok"},
    }
    btc_usdm = {
        "provider": "binance",
        "provider_market": "usdm_futures",
        "provider_symbol": "BTCUSDT",
        "normalized_symbol": "BTCUSDT-PERP",
        "base_asset": "BTC",
        "quote_asset": "USDT",
        "settle_asset": "USDT",
        "margin_asset": "USDT",
        "asset_class": "crypto",
        "contract_type": "PERPETUAL",
        "instrument_type": "future",
        "status": "TRADING",
        "tradable": True,
        "backtestable": True,
        "paper_enabled": True,
        "test_enabled": True,
        "demo_enabled": True,
        "live_enabled": True,
        "permissions": ["USDⓈ-M"],
        "order_types": ["LIMIT", "MARKET", "STOP"],
        "time_in_force": ["GTC", "IOC", "FOK"],
        "tick_size": 0.1,
        "step_size": 0.001,
        "min_qty": 0.001,
        "min_notional": 5.0,
        "price_precision": 1,
        "qty_precision": 3,
        "funding_interval_hours": 8.0,
        "exchange_filters": {"minNotional": 5.0},
        "symbol_filters": {"lotSize": 0.001},
        "account_eligibility": {"live_enabled_reason": "futures_ok"},
    }

    spot_id = store.upsert_instrument(btc_spot)
    usdm_id = store.upsert_instrument(btc_usdm)

    assert spot_id == build_instrument_id("binance", "spot", "BTCUSDT")
    assert usdm_id == build_instrument_id("binance", "usdm_futures", "BTCUSDT")

    all_rows = registry.list_instrument_registry(provider="binance")
    assert len(all_rows) == 2
    assert any(row["live_enabled"] for row in all_rows)

    spot_rows = registry.list_instrument_registry(provider_market="spot", tradable=True)
    assert len(spot_rows) == 1
    assert spot_rows[0]["permissions"] == ["SPOT"]

    catalog_hash = store.snapshot_catalog(
        snapshot_id="cat-spot-001",
        provider="binance",
        provider_market="spot",
        items=[{**btc_spot, "instrument_id": spot_id}],
        metadata={"origin": "test"},
    )
    assert catalog_hash

    snapshots = registry.list_instrument_catalog_snapshots(provider="binance", provider_market="spot")
    assert len(snapshots) == 1
    assert snapshots[0]["catalog_hash"] == catalog_hash
    assert snapshots[0]["metadata"]["origin"] == "test"

    snapshot_items = registry.list_instrument_catalog_snapshot_items("cat-spot-001")
    assert len(snapshot_items) == 1
    assert snapshot_items[0]["instrument_id"] == spot_id
    assert snapshot_items[0]["tradable"] is True

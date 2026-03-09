from __future__ import annotations

from rtlab_core.strategy_packs.registry_db import RegistryDB
from rtlab_core.universe.service import UniverseService


def _seed_instrument(registry: RegistryDB, *, instrument_id: str, provider_market: str, symbol: str) -> None:
    registry.upsert_instrument_registry(
        instrument_id=instrument_id,
        provider="binance",
        provider_market=provider_market,
        provider_symbol=symbol,
        normalized_symbol=symbol,
        base_asset=symbol[:-4],
        quote_asset=symbol[-4:],
        asset_class="crypto",
        status="TRADING",
        tradable=True,
        backtestable=True,
        paper_enabled=True,
        test_enabled=True,
        demo_enabled=True,
        live_enabled=provider_market != "coinm_futures",
        tick_size=0.01,
        step_size=0.001,
        min_qty=0.001,
        min_notional=5.0,
        source_hash=f"hash-{instrument_id}",
    )


def test_universe_service_creates_registry_snapshot_and_items(tmp_path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    _seed_instrument(registry, instrument_id="inst-btc-spot", provider_market="spot", symbol="BTCUSDT")
    _seed_instrument(registry, instrument_id="inst-eth-spot", provider_market="spot", symbol="ETHUSDT")
    registry.upsert_instrument_catalog_snapshot(
        snapshot_id="snap-spot-001",
        provider="binance",
        provider_market="spot",
        catalog_hash="catalog-hash-001",
        items=registry.list_instrument_registry(provider="binance", provider_market="spot"),
        metadata={"reason": "test"},
    )

    service = UniverseService(registry)
    payload = service.upsert_universe(
        name="Top spot",
        provider="binance",
        provider_market="spot",
        market="crypto",
        asset_class="crypto",
        symbols=["BTCUSDT", "ETHUSDT"],
        definition={"source_kind": "manual"},
        metadata={"owner": "pytest"},
    )

    rows = registry.list_universe_registry(provider_market="spot")
    assert len(rows) == 1
    assert rows[0]["name"] == "Top spot"
    assert rows[0]["catalog_snapshot_id"] == "snap-spot-001"

    snapshots = registry.list_universe_snapshots(universe_id=str(payload["universe_id"]))
    assert len(snapshots) == 1
    assert snapshots[0]["catalog_snapshot_id"] == "snap-spot-001"

    items = registry.list_universe_snapshot_items(str(payload["snapshot_id"]))
    assert [item["normalized_symbol"] for item in items] == ["BTCUSDT", "ETHUSDT"]
    assert items[0]["payload"]["tradable"] is True


def test_run_universe_link_roundtrip_preserves_snapshot_and_missing_symbol_marker(tmp_path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    _seed_instrument(registry, instrument_id="inst-btc-usdm", provider_market="usdm_futures", symbol="BTCUSDT")
    registry.upsert_instrument_catalog_snapshot(
        snapshot_id="snap-usdm-001",
        provider="binance",
        provider_market="usdm_futures",
        catalog_hash="catalog-hash-usdm-001",
        items=registry.list_instrument_registry(provider="binance", provider_market="usdm_futures"),
        metadata={"reason": "test-usdm"},
    )

    service = UniverseService(registry)
    payload = service.upsert_universe(
        name="Futures test",
        provider="binance",
        provider_market="usdm_futures",
        market="crypto",
        asset_class="crypto",
        symbols=["BTCUSDT", "ETHUSDT"],
        definition={"source_kind": "run_snapshot"},
        metadata={"run_id": "RUN-UNI-001"},
        status="generated",
    )
    registry.upsert_run_universe_link(
        run_id="RUN-UNI-001",
        universe_id=str(payload["universe_id"]),
        snapshot_id=str(payload["snapshot_id"]),
        provider="binance",
        provider_market="usdm_futures",
        market="crypto",
        asset_class="crypto",
        symbol_count=int(payload["symbol_count"]),
        metadata={"dataset_hash": "ds-001", "bot_id": "BOT-42"},
    )

    links = registry.list_run_universe_links(run_id="RUN-UNI-001")
    assert len(links) == 1
    assert links[0]["snapshot_id"] == payload["snapshot_id"]
    assert links[0]["metadata"]["bot_id"] == "BOT-42"

    items = registry.list_universe_snapshot_items(str(payload["snapshot_id"]))
    missing = next(item for item in items if item["normalized_symbol"] == "ETHUSDT")
    assert missing["payload"]["snapshot_gap"] == "instrument_missing_from_catalog"
    assert missing["payload"]["live_enabled"] is False

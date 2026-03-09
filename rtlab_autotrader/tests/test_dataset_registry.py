from __future__ import annotations

import json
from pathlib import Path

from rtlab_core.src.data.catalog import DataCatalog
from rtlab_core.src.research.data_provider import build_data_provider


def _seed_manifest_file(tmp_path: Path, *, market: str = "crypto", symbol: str = "BTCUSDT", timeframe: str = "5m") -> Path:
    data_file = tmp_path / "raw" / market / f"{symbol}_{timeframe}.parquet"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_bytes(b"stub-data")
    return data_file


def test_catalog_write_manifest_syncs_dataset_registry(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    data_file = _seed_manifest_file(tmp_path)
    payload = catalog.write_manifest(
        market="crypto",
        symbol="BTCUSDT",
        timeframe="5m",
        source="binance_public",
        start="2024-01-01T00:00:00+00:00",
        end="2024-01-31T23:59:00+00:00",
        files=[data_file],
        processed_path=data_file,
        extra={"provider": "binance_public", "provider_market": "spot"},
    )
    row = catalog.registry.get_dataset_registry(
        provider="binance_public",
        market="crypto",
        symbol="BTCUSDT",
        timeframe="5m",
        dataset_hash=str(payload.get("dataset_hash") or ""),
    )
    assert row is not None
    assert row["provider_market"] == "spot"
    assert row["dataset_source"] == "binance_public"
    assert row["ready"] is True
    assert row["files"]


def test_dataset_provider_catalog_fallback_persists_standard_manifest_and_registry(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    data_file = _seed_manifest_file(tmp_path)
    catalog.write_manifest(
        market="crypto",
        symbol="BTCUSDT",
        timeframe="1m",
        source="binance_public",
        start="2024-01-01T00:00:00+00:00",
        end="2024-01-31T23:59:00+00:00",
        files=[data_file],
        processed_path=data_file,
        extra={"provider": "binance_public", "provider_market": "spot"},
    )

    provider = build_data_provider(mode="dataset", user_data_dir=tmp_path, catalog=catalog)
    resolved = provider.resolve(market="crypto", symbol="BTCUSDT", timeframe="5m", start="2024-01-01", end="2024-01-31")
    target_manifest = tmp_path / "datasets" / "binance_public" / "crypto" / "BTCUSDT" / "5m" / "manifest.json"

    assert resolved.ready is True
    assert target_manifest.exists()
    persisted = json.loads(target_manifest.read_text(encoding="utf-8"))
    row = catalog.registry.get_dataset_registry(
        provider="binance_public",
        market="crypto",
        symbol="BTCUSDT",
        timeframe="5m",
        dataset_hash=str(persisted.get("dataset_hash") or ""),
    )
    assert row is not None
    assert row["dataset_source"] == "binance_public"
    assert row["metadata"]["provider_market"] == "spot"


def test_run_dataset_link_roundtrip_uses_registry_dataset_id(tmp_path: Path) -> None:
    catalog = DataCatalog(tmp_path)
    data_file = _seed_manifest_file(tmp_path)
    payload = catalog.write_manifest(
        market="crypto",
        symbol="BTCUSDT",
        timeframe="5m",
        source="binance_public",
        start="2024-01-01T00:00:00+00:00",
        end="2024-01-31T23:59:00+00:00",
        files=[data_file],
        processed_path=data_file,
        extra={"provider": "binance_public", "provider_market": "spot"},
    )
    row = catalog.registry.get_dataset_registry(
        provider="binance_public",
        market="crypto",
        symbol="BTCUSDT",
        timeframe="5m",
        dataset_hash=str(payload.get("dataset_hash") or ""),
    )
    assert row is not None

    catalog.registry.upsert_run_dataset_link(
        run_id="RUN-001",
        dataset_id=str(row["dataset_id"]),
        dataset_hash=str(row["dataset_hash"]),
        dataset_source=str(row["dataset_source"]),
        provider="binance_public",
        provider_market="spot",
        market="crypto",
        symbol="BTCUSDT",
        timeframe="5m",
        metadata={"mode": "backtest", "strategy_id": "trend_pullback_orderflow_v2"},
    )
    links = catalog.registry.list_run_dataset_links(run_id="RUN-001")
    assert len(links) == 1
    assert links[0]["dataset_id"] == row["dataset_id"]
    assert links[0]["metadata"]["mode"] == "backtest"

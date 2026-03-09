from __future__ import annotations

import hashlib
import json
from typing import Any

from rtlab_core.strategy_packs.registry_db import RegistryDB
from rtlab_core.src.data.universes import normalize_market, normalize_symbol


def _stable_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class UniverseService:
    def __init__(self, registry: RegistryDB) -> None:
        self.registry = registry

    def _latest_catalog_snapshot_id(self, *, provider: str, provider_market: str) -> str | None:
        rows = self.registry.list_instrument_catalog_snapshots(provider=provider, provider_market=provider_market, limit=1)
        return str(rows[0].get("snapshot_id") or "") if rows else None

    def _items_for_symbols(
        self,
        *,
        provider: str,
        provider_market: str,
        normalized_symbols: list[str],
        catalog_snapshot_id: str | None,
    ) -> list[dict[str, Any]]:
        by_symbol: dict[str, dict[str, Any]] = {}
        if catalog_snapshot_id:
            for row in self.registry.list_instrument_catalog_snapshot_items(catalog_snapshot_id):
                payload = row.get("snapshot_payload") if isinstance(row.get("snapshot_payload"), dict) else {}
                by_symbol[str(row.get("normalized_symbol") or "").upper()] = {
                    "normalized_symbol": str(row.get("normalized_symbol") or "").upper(),
                    "provider_symbol": str(row.get("provider_symbol") or ""),
                    "instrument_id": str(row.get("instrument_id") or ""),
                    **payload,
                }
        if not by_symbol:
            for row in self.registry.list_instrument_registry(provider=provider, provider_market=provider_market):
                by_symbol[str(row.get("normalized_symbol") or "").upper()] = dict(row)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for symbol in normalized_symbols:
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            payload = dict(by_symbol.get(symbol) or {})
            if not payload:
                payload = {
                    "normalized_symbol": symbol,
                    "provider_symbol": symbol,
                    "provider": provider,
                    "provider_market": provider_market,
                    "status": "unknown",
                    "tradable": False,
                    "backtestable": False,
                    "paper_enabled": False,
                    "test_enabled": False,
                    "demo_enabled": False,
                    "live_enabled": False,
                    "snapshot_gap": "instrument_missing_from_catalog",
                }
            payload["normalized_symbol"] = str(payload.get("normalized_symbol") or symbol).upper()
            payload["provider_symbol"] = str(payload.get("provider_symbol") or symbol)
            items.append(payload)
        return items

    def upsert_universe(
        self,
        *,
        name: str,
        provider: str,
        provider_market: str,
        market: str,
        asset_class: str,
        symbols: list[str],
        definition: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        status: str = "active",
    ) -> dict[str, Any]:
        normalized_symbols = [normalize_symbol(str(symbol)) for symbol in symbols if str(symbol).strip()]
        normalized_symbols = [symbol for symbol in normalized_symbols if symbol]
        normalized_market = normalize_market(market)
        clean_definition = {
            **(definition or {}),
            "symbols": normalized_symbols,
            "market": normalized_market,
            "provider": provider,
            "provider_market": provider_market,
            "asset_class": asset_class,
        }
        source_hash = _stable_hash(clean_definition)
        universe_id = str((definition or {}).get("universe_id") or f"uni-{source_hash[:12]}")
        catalog_snapshot_id = str((definition or {}).get("catalog_snapshot_id") or "") or self._latest_catalog_snapshot_id(
            provider=provider,
            provider_market=provider_market,
        )
        self.registry.upsert_universe_registry(
            universe_id=universe_id,
            name=name,
            provider=provider,
            provider_market=provider_market,
            market=normalized_market,
            asset_class=asset_class,
            definition=clean_definition,
            symbol_count=len(normalized_symbols),
            catalog_snapshot_id=catalog_snapshot_id,
            source_hash=source_hash,
            status=status,
        )
        snapshot_payload = {
            "universe_id": universe_id,
            "symbols": normalized_symbols,
            "catalog_snapshot_id": catalog_snapshot_id or "",
            "source_hash": source_hash,
        }
        snapshot_id = f"usnap-{_stable_hash(snapshot_payload)[:18]}"
        items = self._items_for_symbols(
            provider=provider,
            provider_market=provider_market,
            normalized_symbols=normalized_symbols,
            catalog_snapshot_id=catalog_snapshot_id,
        )
        self.registry.upsert_universe_snapshot(
            snapshot_id=snapshot_id,
            universe_id=universe_id,
            provider=provider,
            provider_market=provider_market,
            market=normalized_market,
            asset_class=asset_class,
            catalog_snapshot_id=catalog_snapshot_id,
            definition=clean_definition,
            metadata=metadata or {},
            items=items,
            source_hash=source_hash,
        )
        return {
            "universe_id": universe_id,
            "snapshot_id": snapshot_id,
            "catalog_snapshot_id": catalog_snapshot_id,
            "source_hash": source_hash,
            "symbol_count": len(normalized_symbols),
            "items": items,
        }

    def list_universes(self, *, provider_market: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return self.registry.list_universe_registry(provider_market=provider_market, limit=limit)

    def list_run_links(self, *, run_id: str) -> list[dict[str, Any]]:
        return self.registry.list_run_universe_links(run_id=run_id)

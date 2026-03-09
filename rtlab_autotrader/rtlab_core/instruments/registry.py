from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from rtlab_core.strategy_packs.registry_db import RegistryDB


def build_instrument_id(provider: str, provider_market: str, provider_symbol: str) -> str:
    provider_clean = str(provider or "").strip().lower()
    market_clean = str(provider_market or "").strip().lower()
    symbol_clean = str(provider_symbol or "").strip().upper()
    return f"{provider_clean}:{market_clean}:{symbol_clean}"


def _catalog_hash(items: list[dict[str, Any]]) -> str:
    normalized = json.dumps(items, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class InstrumentCatalogStore:
    registry: RegistryDB

    def upsert_instrument(self, payload: dict[str, Any]) -> str:
        instrument_id = str(
            payload.get("instrument_id")
            or build_instrument_id(
                str(payload.get("provider") or ""),
                str(payload.get("provider_market") or ""),
                str(payload.get("provider_symbol") or payload.get("normalized_symbol") or ""),
            )
        )
        self.registry.upsert_instrument_registry(
            instrument_id=instrument_id,
            provider=str(payload.get("provider") or ""),
            provider_market=str(payload.get("provider_market") or ""),
            provider_symbol=str(payload.get("provider_symbol") or ""),
            normalized_symbol=str(payload.get("normalized_symbol") or payload.get("provider_symbol") or ""),
            base_asset=payload.get("base_asset"),
            quote_asset=payload.get("quote_asset"),
            settle_asset=payload.get("settle_asset"),
            margin_asset=payload.get("margin_asset"),
            asset_class=str(payload.get("asset_class") or "unknown"),
            contract_type=payload.get("contract_type"),
            instrument_type=payload.get("instrument_type"),
            status=str(payload.get("status") or "unknown"),
            tradable=bool(payload.get("tradable")),
            backtestable=bool(payload.get("backtestable")),
            mock_enabled=bool(payload.get("mock_enabled")),
            paper_enabled=bool(payload.get("paper_enabled")),
            test_enabled=bool(payload.get("test_enabled")),
            demo_enabled=bool(payload.get("demo_enabled")),
            live_enabled=bool(payload.get("live_enabled")),
            permissions=list(payload.get("permissions") or []),
            order_types=list(payload.get("order_types") or []),
            time_in_force=list(payload.get("time_in_force") or []),
            tick_size=payload.get("tick_size"),
            step_size=payload.get("step_size"),
            min_qty=payload.get("min_qty"),
            max_qty=payload.get("max_qty"),
            min_notional=payload.get("min_notional"),
            price_precision=payload.get("price_precision"),
            qty_precision=payload.get("qty_precision"),
            maker_fee_bps=payload.get("maker_fee_bps"),
            taker_fee_bps=payload.get("taker_fee_bps"),
            funding_interval_hours=payload.get("funding_interval_hours"),
            onboard_date=payload.get("onboard_date"),
            delivery_date=payload.get("delivery_date"),
            exchange_filters=dict(payload.get("exchange_filters") or {}),
            symbol_filters=dict(payload.get("symbol_filters") or {}),
            raw_exchange_payload=dict(payload.get("raw_exchange_payload") or {}),
            account_eligibility=dict(payload.get("account_eligibility") or {}),
            source_hash=payload.get("source_hash"),
            is_active_snapshot=bool(payload.get("is_active_snapshot", True)),
            first_seen_at=payload.get("first_seen_at"),
            last_seen_at=payload.get("last_seen_at"),
            delisted_at=payload.get("delisted_at"),
        )
        return instrument_id

    def snapshot_catalog(
        self,
        *,
        snapshot_id: str,
        provider: str,
        provider_market: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> str:
        normalized_items: list[dict[str, Any]] = []
        for raw in items:
            item = dict(raw)
            item["instrument_id"] = str(
                item.get("instrument_id")
                or build_instrument_id(
                    str(item.get("provider") or provider),
                    str(item.get("provider_market") or provider_market),
                    str(item.get("provider_symbol") or item.get("normalized_symbol") or ""),
                )
            )
            item["provider_symbol"] = str(item.get("provider_symbol") or "")
            item["normalized_symbol"] = str(item.get("normalized_symbol") or item["provider_symbol"])
            item["status"] = str(item.get("status") or "unknown")
            normalized_items.append(item)
        catalog_hash = _catalog_hash(normalized_items)
        self.registry.upsert_instrument_catalog_snapshot(
            snapshot_id=snapshot_id,
            provider=provider,
            provider_market=provider_market,
            catalog_hash=catalog_hash,
            items=normalized_items,
            metadata=metadata,
            created_at=created_at,
        )
        return catalog_hash

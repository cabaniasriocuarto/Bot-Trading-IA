from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

from rtlab_core.instruments.registry import InstrumentCatalogStore, build_instrument_id
from rtlab_core.strategy_packs.registry_db import RegistryDB

BINANCE_SPOT_BASE_URL_DEFAULT = "https://api.binance.com"
BINANCE_USDM_BASE_URL_DEFAULT = "https://fapi.binance.com"
BINANCE_COINM_BASE_URL_DEFAULT = "https://dapi.binance.com"

_SPOT_EXCHANGE_INFO_PATH = "/api/v3/exchangeInfo"
_USDM_EXCHANGE_INFO_PATH = "/fapi/v1/exchangeInfo"
_COINM_EXCHANGE_INFO_PATH = "/dapi/v1/exchangeInfo"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_bundle(policies_root: Path) -> dict[str, Any]:
    gates_path = Path(policies_root).resolve() / "gates.yaml"
    if not gates_path.exists():
        return {}
    try:
        payload = yaml.safe_load(gates_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _market_catalog_policy(policies_root: Path) -> dict[str, Any]:
    gates_root = _policy_bundle(policies_root).get("gates")
    if not isinstance(gates_root, dict):
        return {}
    market_catalog = gates_root.get("market_catalog")
    return market_catalog if isinstance(market_catalog, dict) else {}


def _binance_market_policy(policies_root: Path) -> dict[str, Any]:
    market_catalog = _market_catalog_policy(policies_root)
    providers = market_catalog.get("providers")
    if not isinstance(providers, dict):
        return {}
    binance = providers.get("binance")
    return binance if isinstance(binance, dict) else {}


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _float(value: Any) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _int(value: Any) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _source_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _symbol_filters(symbol_payload: dict[str, Any]) -> tuple[dict[str, Any], float | None, float | None, float | None, float | None, float | None]:
    filters = symbol_payload.get("filters")
    items = filters if isinstance(filters, list) else []
    mapped: dict[str, Any] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        filter_type = str(raw.get("filterType") or "").strip()
        if filter_type:
            mapped[filter_type] = raw
    price_filter = mapped.get("PRICE_FILTER") or {}
    lot_filter = mapped.get("LOT_SIZE") or mapped.get("MARKET_LOT_SIZE") or {}
    notional_filter = mapped.get("NOTIONAL") or mapped.get("MIN_NOTIONAL") or {}
    tick_size = _float(price_filter.get("tickSize"))
    step_size = _float(lot_filter.get("stepSize"))
    min_qty = _float(lot_filter.get("minQty"))
    max_qty = _float(lot_filter.get("maxQty"))
    min_notional = _float(notional_filter.get("minNotional") or notional_filter.get("notional"))
    return mapped, tick_size, step_size, min_qty, max_qty, min_notional


def _normalize_permissions(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, list):
                out.extend([str(x).strip().upper() for x in item if str(x).strip()])
            elif str(item).strip():
                out.append(str(item).strip().upper())
    elif value and str(value).strip():
        out.append(str(value).strip().upper())
    deduped: list[str] = []
    for item in out:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _spot_payload_to_instrument(
    *,
    symbol_payload: dict[str, Any],
    provider_market: str,
    source_hash: str,
    live_enabled: bool,
    tradable: bool,
) -> dict[str, Any]:
    mapped_filters, tick_size, step_size, min_qty, max_qty, min_notional = _symbol_filters(symbol_payload)
    base_asset = str(symbol_payload.get("baseAsset") or "")
    quote_asset = str(symbol_payload.get("quoteAsset") or "")
    provider_symbol = str(symbol_payload.get("symbol") or "")
    permission_sets = symbol_payload.get("permissionSets") if isinstance(symbol_payload.get("permissionSets"), list) else []
    permissions = _normalize_permissions(symbol_payload.get("permissions"))
    if provider_market == "margin":
        permissions = sorted({*permissions, "MARGIN"})
    return {
        "provider": "binance",
        "provider_market": provider_market,
        "provider_symbol": provider_symbol,
        "normalized_symbol": provider_symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "asset_class": "crypto",
        "instrument_type": "margin_spot" if provider_market == "margin" else "spot",
        "status": str(symbol_payload.get("status") or "unknown"),
        "tradable": tradable,
        "backtestable": tradable,
        "mock_enabled": tradable,
        "paper_enabled": tradable,
        "test_enabled": tradable,
        "demo_enabled": tradable,
        "live_enabled": live_enabled,
        "permissions": permissions,
        "order_types": [str(x) for x in (symbol_payload.get("orderTypes") or []) if str(x).strip()],
        "time_in_force": [str(x) for x in (symbol_payload.get("timeInForce") or []) if str(x).strip()],
        "tick_size": tick_size,
        "step_size": step_size,
        "min_qty": min_qty,
        "max_qty": max_qty,
        "min_notional": min_notional,
        "price_precision": _int(symbol_payload.get("quotePrecision") or symbol_payload.get("quoteAssetPrecision")),
        "qty_precision": _int(symbol_payload.get("baseAssetPrecision")),
        "exchange_filters": {"permissionSets": permission_sets},
        "symbol_filters": mapped_filters,
        "raw_exchange_payload": symbol_payload,
        "account_eligibility": {
            "requires_account_validation": True,
            "market_family": provider_market,
            "is_spot_trading_allowed": _bool(symbol_payload.get("isSpotTradingAllowed"), default=(provider_market == "spot")),
            "is_margin_trading_allowed": _bool(symbol_payload.get("isMarginTradingAllowed")),
            "permission_sets": permission_sets,
            "live_enabled_reason": (
                "metadata_ok_pending_account_validation"
                if live_enabled
                else "metadata_not_tradable_or_missing_permission"
            ),
        },
        "source_hash": source_hash,
        "is_active_snapshot": True,
        "last_seen_at": _utc_now_iso(),
    }


def _futures_payload_to_instrument(
    *,
    symbol_payload: dict[str, Any],
    provider_market: str,
    source_hash: str,
) -> dict[str, Any]:
    mapped_filters, tick_size, step_size, min_qty, max_qty, min_notional = _symbol_filters(symbol_payload)
    provider_symbol = str(symbol_payload.get("symbol") or "")
    contract_type = str(symbol_payload.get("contractType") or "")
    tradable = str(symbol_payload.get("status") or "").upper() == "TRADING"
    normalized_symbol = provider_symbol
    if provider_market == "usdm_futures" and contract_type.upper() == "PERPETUAL" and provider_symbol:
        normalized_symbol = f"{provider_symbol}-PERP"
    return {
        "provider": "binance",
        "provider_market": provider_market,
        "provider_symbol": provider_symbol,
        "normalized_symbol": normalized_symbol,
        "base_asset": str(symbol_payload.get("baseAsset") or ""),
        "quote_asset": str(symbol_payload.get("quoteAsset") or ""),
        "settle_asset": str(symbol_payload.get("marginAsset") or symbol_payload.get("quoteAsset") or ""),
        "margin_asset": str(symbol_payload.get("marginAsset") or symbol_payload.get("quoteAsset") or ""),
        "asset_class": "crypto",
        "contract_type": contract_type or None,
        "instrument_type": "future",
        "status": str(symbol_payload.get("status") or "unknown"),
        "tradable": tradable,
        "backtestable": tradable,
        "mock_enabled": tradable,
        "paper_enabled": tradable,
        "test_enabled": tradable,
        "demo_enabled": tradable,
        "live_enabled": tradable,
        "permissions": [provider_market.upper()],
        "order_types": [str(x) for x in (symbol_payload.get("orderTypes") or []) if str(x).strip()],
        "time_in_force": [str(x) for x in (symbol_payload.get("timeInForce") or []) if str(x).strip()],
        "tick_size": tick_size,
        "step_size": step_size,
        "min_qty": min_qty,
        "max_qty": max_qty,
        "min_notional": min_notional,
        "price_precision": _int(symbol_payload.get("pricePrecision")),
        "qty_precision": _int(symbol_payload.get("quantityPrecision")),
        "funding_interval_hours": None,
        "onboard_date": str(symbol_payload.get("onboardDate") or "") or None,
        "delivery_date": str(symbol_payload.get("deliveryDate") or "") or None,
        "exchange_filters": {},
        "symbol_filters": mapped_filters,
        "raw_exchange_payload": symbol_payload,
        "account_eligibility": {
            "requires_account_validation": True,
            "market_family": provider_market,
            "contract_type": contract_type or None,
            "live_enabled_reason": "metadata_ok_pending_account_validation" if tradable else "metadata_not_tradable",
        },
        "source_hash": source_hash,
        "is_active_snapshot": True,
        "last_seen_at": _utc_now_iso(),
    }


def diff_instrument_snapshots(previous_items: list[dict[str, Any]], current_items: list[dict[str, Any]]) -> dict[str, Any]:
    previous = {str(item.get("instrument_id") or ""): item for item in previous_items if str(item.get("instrument_id") or "")}
    current = {str(item.get("instrument_id") or ""): item for item in current_items if str(item.get("instrument_id") or "")}
    added = sorted([key for key in current.keys() if key not in previous])
    removed = sorted([key for key in previous.keys() if key not in current])
    changed: list[str] = []
    for key in sorted(set(previous.keys()) & set(current.keys())):
        left = dict(previous[key])
        right = dict(current[key])
        left.pop("last_seen_at", None)
        right.pop("last_seen_at", None)
        if json.dumps(left, ensure_ascii=True, sort_keys=True, default=str) != json.dumps(right, ensure_ascii=True, sort_keys=True, default=str):
            changed.append(key)
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)},
    }


@dataclass(slots=True)
class BinanceCatalogSyncService:
    registry: RegistryDB
    policies_root: Path
    session: requests.Session | None = None
    request_timeout_sec: int = 20
    _store: InstrumentCatalogStore = field(init=False, repr=False)
    _lock: threading.Lock = field(init=False, repr=False)
    _session: requests.Session = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._store = InstrumentCatalogStore(self.registry)
        self._lock = threading.Lock()
        self._session = self.session or requests.Session()

    def sync_all(self, *, reason: str = "manual") -> dict[str, Any]:
        with self._lock:
            policy = _binance_market_policy(self.policies_root)
            families = policy.get("families") if isinstance(policy.get("families"), dict) else {}
            enabled = _bool(policy.get("enabled"), default=True)
            if not enabled:
                return {"ok": False, "reason": "binance catalog disabled by policy", "results": {}}
            spot_payload = self._fetch_json("spot")
            results: dict[str, Any] = {}
            if _bool(families.get("spot"), default=True):
                results["spot"] = self._sync_spot_like_market("spot", spot_payload, reason=reason)
            if _bool(families.get("margin"), default=True):
                results["margin"] = self._sync_spot_like_market("margin", spot_payload, reason=reason)
            if _bool(families.get("usdm_futures"), default=True):
                results["usdm_futures"] = self._sync_futures_market("usdm_futures", self._fetch_json("usdm_futures"), reason=reason)
            if _bool(families.get("coinm_futures"), default=True):
                results["coinm_futures"] = self._sync_futures_market("coinm_futures", self._fetch_json("coinm_futures"), reason=reason)
            return {"ok": True, "reason": reason, "results": results}

    def scheduled_sync_loop(self, *, stop_event: threading.Event, interval_minutes: int) -> None:
        sleep_seconds = max(60, int(interval_minutes) * 60)
        while not stop_event.wait(sleep_seconds):
            try:
                self.sync_all(reason="scheduled")
            except Exception:
                continue

    def list_instruments(
        self,
        *,
        provider_market: str | None = None,
        status: str | None = None,
        tradable: bool | None = None,
        live_enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        return self.registry.list_instrument_registry(
            provider="binance",
            provider_market=provider_market,
            status=status,
            tradable=tradable,
            live_enabled=live_enabled,
        )

    def get_instrument(self, instrument_id: str) -> dict[str, Any] | None:
        item = self.registry.get_instrument_registry(instrument_id)
        if item and str(item.get("provider") or "").strip().lower() == "binance":
            return item
        return None

    def _fetch_json(self, provider_market: str) -> dict[str, Any]:
        base_url, endpoint = self._market_url(provider_market)
        response = self._session.get(f"{base_url}{endpoint}", timeout=self.request_timeout_sec)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"exchangeInfo invalido para {provider_market}")
        return payload

    def _market_url(self, provider_market: str) -> tuple[str, str]:
        normalized = str(provider_market or "").strip().lower()
        if normalized == "spot" or normalized == "margin":
            base = str(os.getenv("BINANCE_CATALOG_SPOT_BASE_URL", BINANCE_SPOT_BASE_URL_DEFAULT)).strip() or BINANCE_SPOT_BASE_URL_DEFAULT
            return base.rstrip("/"), _SPOT_EXCHANGE_INFO_PATH
        if normalized == "usdm_futures":
            base = str(os.getenv("BINANCE_CATALOG_USDM_BASE_URL", BINANCE_USDM_BASE_URL_DEFAULT)).strip() or BINANCE_USDM_BASE_URL_DEFAULT
            return base.rstrip("/"), _USDM_EXCHANGE_INFO_PATH
        if normalized == "coinm_futures":
            base = str(os.getenv("BINANCE_CATALOG_COINM_BASE_URL", BINANCE_COINM_BASE_URL_DEFAULT)).strip() or BINANCE_COINM_BASE_URL_DEFAULT
            return base.rstrip("/"), _COINM_EXCHANGE_INFO_PATH
        raise ValueError(f"provider_market no soportado: {provider_market}")

    def _sync_spot_like_market(self, provider_market: str, payload: dict[str, Any], *, reason: str) -> dict[str, Any]:
        symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
        source_hash = _source_hash(payload)
        current_items: list[dict[str, Any]] = []
        for raw in symbols:
            if not isinstance(raw, dict):
                continue
            is_spot_allowed = _bool(raw.get("isSpotTradingAllowed"), default=True)
            is_margin_allowed = _bool(raw.get("isMarginTradingAllowed"))
            tradable = str(raw.get("status") or "").upper() == "TRADING"
            if provider_market == "margin" and not is_margin_allowed:
                continue
            live_enabled = tradable and (is_margin_allowed if provider_market == "margin" else is_spot_allowed)
            item = _spot_payload_to_instrument(
                symbol_payload=raw,
                provider_market=provider_market,
                source_hash=source_hash,
                live_enabled=live_enabled,
                tradable=tradable,
            )
            item["instrument_id"] = build_instrument_id("binance", provider_market, str(item.get("provider_symbol") or ""))
            self._store.upsert_instrument(item)
            current_items.append(item)
        return self._persist_snapshot(provider_market=provider_market, items=current_items, reason=reason)

    def _sync_futures_market(self, provider_market: str, payload: dict[str, Any], *, reason: str) -> dict[str, Any]:
        symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
        source_hash = _source_hash(payload)
        current_items: list[dict[str, Any]] = []
        for raw in symbols:
            if not isinstance(raw, dict):
                continue
            item = _futures_payload_to_instrument(
                symbol_payload=raw,
                provider_market=provider_market,
                source_hash=source_hash,
            )
            item["instrument_id"] = build_instrument_id("binance", provider_market, str(item.get("provider_symbol") or ""))
            self._store.upsert_instrument(item)
            current_items.append(item)
        return self._persist_snapshot(provider_market=provider_market, items=current_items, reason=reason)

    def _persist_snapshot(self, *, provider_market: str, items: list[dict[str, Any]], reason: str) -> dict[str, Any]:
        previous_snapshots = self.registry.list_instrument_catalog_snapshots(provider="binance", provider_market=provider_market, limit=1)
        previous_snapshot_id = str(previous_snapshots[0]["snapshot_id"]) if previous_snapshots else None
        previous_items = (
            self.registry.list_instrument_catalog_snapshot_items(previous_snapshot_id)
            if previous_snapshot_id
            else []
        )
        snapshot_id = f"binance-{provider_market}-{int(time.time())}"
        diff = diff_instrument_snapshots(previous_items, items)
        catalog_hash = self._store.snapshot_catalog(
            snapshot_id=snapshot_id,
            provider="binance",
            provider_market=provider_market,
            items=items,
            metadata={
                "reason": reason,
                "previous_snapshot_id": previous_snapshot_id,
                "diff": diff,
            },
            created_at=_utc_now_iso(),
        )
        return {
            "provider": "binance",
            "provider_market": provider_market,
            "snapshot_id": snapshot_id,
            "previous_snapshot_id": previous_snapshot_id,
            "catalog_hash": catalog_hash,
            "instrument_count": len(items),
            "diff": diff,
        }

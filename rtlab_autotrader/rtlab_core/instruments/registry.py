from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests
import yaml

from rtlab_core.policy_paths import describe_policy_root_resolution


VENUE_BINANCE = "binance"
FAMILIES: tuple[str, ...] = ("spot", "margin", "usdm_futures", "coinm_futures")
ENVIRONMENTS: tuple[str, ...] = ("live", "testnet")
PARSER_VERSION = "binance_catalog_v1"
INSTRUMENT_REGISTRY_FILENAME = "instrument_registry.yaml"
POLICY_EXPECTED_FILES: tuple[str, ...] = ("instrument_registry.yaml", "universes.yaml")

FAIL_CLOSED_MINIMAL_INSTRUMENT_REGISTRY_POLICY: dict[str, Any] = {
    "sync": {
        "manual_enabled": False,
        "startup_enabled": False,
        "startup_timeout_sec": 5,
        "request_timeout_sec": 5,
        "retries": 0,
        "retry_backoff_sec": [0.0],
    },
    "freshness": {
        "warn_if_snapshot_older_than_hours": 1,
        "block_if_snapshot_older_than_hours": 1,
    },
    "diffing": {
        "enabled": True,
        "symbol_count_warn_delta_pct": 0.0,
        "symbol_count_block_delta_pct": 0.0,
        "removed_live_eligible_warn_count": 1,
        "removed_live_eligible_block_count": 1,
    },
    "eligibility": {
        "require_status_active": True,
        "require_basic_filters": True,
        "require_permission_metadata_for_margin": True,
        "delivery_block_if_hours_to_expiry_lt": 72,
    },
    "environments": {
        "spot": {"live": False, "testnet": False},
        "margin": {"live": False, "testnet": False},
        "usdm_futures": {"live": False, "testnet": False},
        "coinm_futures": {"live": False, "testnet": False},
    },
    "endpoints": {
        "spot": {
            "live": "",
            "testnet": "",
            "account": "/api/v3/account",
        },
        "margin": {
            "live_catalog_from": "spot",
            "live_account": "",
            "testnet_account": None,
        },
        "usdm_futures": {
            "live": "",
            "testnet": "",
            "account_live": "",
            "account_testnet": "",
        },
        "coinm_futures": {
            "live": "",
            "testnet": "",
            "account_live": "",
            "account_testnet": "",
        },
    },
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return _utc_now().isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: Any, default: Any) -> Any:
    if value in {None, ""}:
        return copy.deepcopy(default)
    try:
        return json.loads(str(value))
    except Exception:
        return copy.deepcopy(default)


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_json_dumps(value).encode("utf-8"))


def _stable_payload_hash(value: Any) -> str:
    return _sha256_json(value)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_dict(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{path}.{key} debe ser dict")
        return {}
    return value


def _require_str(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} debe ser string no vacio")
        return ""
    return value.strip()


def _require_bool(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        errors.append(f"{path}.{key} debe ser bool")
        return False
    return value


def _require_number(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> float:
    value = parent.get(key)
    if not _is_number(value):
        errors.append(f"{path}.{key} debe ser numero")
        return 0.0
    return float(value)


def _require_list(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list) or not value:
        errors.append(f"{path}.{key} debe ser lista no vacia")
        return []
    return value


def _require_optional_str_or_none(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> str | None:
    value = parent.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} debe ser string no vacio o null")
        return None
    return value.strip()


def _validate_instrument_registry_policy(candidate: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return ["instrument_registry debe ser dict"]

    sync_cfg = _require_dict(candidate, "sync", errors=errors, path="instrument_registry")
    _require_bool(sync_cfg, "manual_enabled", errors=errors, path="instrument_registry.sync")
    _require_bool(sync_cfg, "startup_enabled", errors=errors, path="instrument_registry.sync")
    _require_number(sync_cfg, "startup_timeout_sec", errors=errors, path="instrument_registry.sync")
    _require_number(sync_cfg, "request_timeout_sec", errors=errors, path="instrument_registry.sync")
    _require_number(sync_cfg, "retries", errors=errors, path="instrument_registry.sync")
    retry_backoff = _require_list(sync_cfg, "retry_backoff_sec", errors=errors, path="instrument_registry.sync")
    if retry_backoff and not all(_is_number(item) for item in retry_backoff):
        errors.append("instrument_registry.sync.retry_backoff_sec debe contener solo numeros")

    freshness_cfg = _require_dict(candidate, "freshness", errors=errors, path="instrument_registry")
    _require_number(freshness_cfg, "warn_if_snapshot_older_than_hours", errors=errors, path="instrument_registry.freshness")
    _require_number(freshness_cfg, "block_if_snapshot_older_than_hours", errors=errors, path="instrument_registry.freshness")

    diff_cfg = _require_dict(candidate, "diffing", errors=errors, path="instrument_registry")
    _require_bool(diff_cfg, "enabled", errors=errors, path="instrument_registry.diffing")
    _require_number(diff_cfg, "symbol_count_warn_delta_pct", errors=errors, path="instrument_registry.diffing")
    _require_number(diff_cfg, "symbol_count_block_delta_pct", errors=errors, path="instrument_registry.diffing")
    _require_number(diff_cfg, "removed_live_eligible_warn_count", errors=errors, path="instrument_registry.diffing")
    _require_number(diff_cfg, "removed_live_eligible_block_count", errors=errors, path="instrument_registry.diffing")

    eligibility_cfg = _require_dict(candidate, "eligibility", errors=errors, path="instrument_registry")
    _require_bool(eligibility_cfg, "require_status_active", errors=errors, path="instrument_registry.eligibility")
    _require_bool(eligibility_cfg, "require_basic_filters", errors=errors, path="instrument_registry.eligibility")
    _require_bool(eligibility_cfg, "require_permission_metadata_for_margin", errors=errors, path="instrument_registry.eligibility")
    _require_number(eligibility_cfg, "delivery_block_if_hours_to_expiry_lt", errors=errors, path="instrument_registry.eligibility")

    environments_cfg = _require_dict(candidate, "environments", errors=errors, path="instrument_registry")
    for family in FAMILIES:
        family_cfg = _require_dict(environments_cfg, family, errors=errors, path="instrument_registry.environments")
        _require_bool(family_cfg, "live", errors=errors, path=f"instrument_registry.environments.{family}")
        _require_bool(family_cfg, "testnet", errors=errors, path=f"instrument_registry.environments.{family}")

    endpoints_cfg = _require_dict(candidate, "endpoints", errors=errors, path="instrument_registry")
    spot_cfg = _require_dict(endpoints_cfg, "spot", errors=errors, path="instrument_registry.endpoints")
    _require_str(spot_cfg, "live", errors=errors, path="instrument_registry.endpoints.spot")
    _require_str(spot_cfg, "testnet", errors=errors, path="instrument_registry.endpoints.spot")
    _require_str(spot_cfg, "account", errors=errors, path="instrument_registry.endpoints.spot")

    margin_cfg = _require_dict(endpoints_cfg, "margin", errors=errors, path="instrument_registry.endpoints")
    _require_str(margin_cfg, "live_catalog_from", errors=errors, path="instrument_registry.endpoints.margin")
    _require_str(margin_cfg, "live_account", errors=errors, path="instrument_registry.endpoints.margin")
    _require_optional_str_or_none(margin_cfg, "testnet_account", errors=errors, path="instrument_registry.endpoints.margin")

    for family in ("usdm_futures", "coinm_futures"):
        family_cfg = _require_dict(endpoints_cfg, family, errors=errors, path="instrument_registry.endpoints")
        _require_str(family_cfg, "live", errors=errors, path=f"instrument_registry.endpoints.{family}")
        _require_str(family_cfg, "testnet", errors=errors, path=f"instrument_registry.endpoints.{family}")
        _require_str(family_cfg, "account_live", errors=errors, path=f"instrument_registry.endpoints.{family}")
        _require_str(family_cfg, "account_testnet", errors=errors, path=f"instrument_registry.endpoints.{family}")

    return errors


def clear_instrument_registry_policy_cache() -> None:
    _load_instrument_registry_bundle_cached.cache_clear()


def _instrument_registry_source_label(repo_root: Path, policy_path: Path) -> str:
    try:
        return str(policy_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(policy_path.resolve())


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


@lru_cache(maxsize=8)
def _load_instrument_registry_bundle_cached(repo_root_str: str, explicit_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    resolution = describe_policy_root_resolution(
        repo_root,
        explicit=explicit_root,
        expected_files=POLICY_EXPECTED_FILES,
    )
    selected_root = Path(resolution["selected_root"]).resolve()
    policy_path = (selected_root / INSTRUMENT_REGISTRY_FILENAME).resolve()

    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    errors: list[str] = []
    warnings = list(resolution.get("warnings") or [])
    if policy_path.exists():
        try:
            raw_bytes = policy_path.read_bytes()
            raw_text = raw_bytes.decode("utf-8")
            source_hash = _sha256_bytes(raw_bytes)
            raw = yaml.safe_load(raw_text) or {}
            candidate = raw.get("instrument_registry") if isinstance(raw.get("instrument_registry"), dict) else {}
            validation_errors = _validate_instrument_registry_policy(candidate) if isinstance(candidate, dict) and candidate else ["instrument_registry vacio o ausente"]
            if isinstance(candidate, dict) and candidate and not validation_errors:
                payload = candidate
                valid = True
            else:
                errors.extend(validation_errors)
        except Exception:
            payload = {}
            valid = False
            errors.append("instrument_registry.yaml no pudo parsearse como YAML valido")
    else:
        errors.append("instrument_registry.yaml no existe en la raiz seleccionada")

    active_policy = copy.deepcopy(payload if valid else FAIL_CLOSED_MINIMAL_INSTRUMENT_REGISTRY_POLICY)
    policy_hash = _stable_payload_hash(active_policy)
    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "fallback_used": bool(resolution.get("fallback_used")),
        "selected_role": resolution.get("selected_role"),
        "canonical_root": resolution.get("canonical_root"),
        "canonical_role": resolution.get("canonical_role"),
        "divergent_candidates": copy.deepcopy(resolution.get("divergent_candidates") or []),
        "source_hash": source_hash,
        "policy_hash": policy_hash,
        "source": _instrument_registry_source_label(repo_root, policy_path) if valid else "default_fail_closed_minimal",
        "errors": errors,
        "warnings": warnings,
        "instrument_registry": active_policy,
    }


def load_instrument_registry_bundle(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(_load_instrument_registry_bundle_cached(str(resolved_repo_root), explicit_root_str))


def instrument_registry_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_instrument_registry_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("instrument_registry")
    return payload if isinstance(payload, dict) else copy.deepcopy(FAIL_CLOSED_MINIMAL_INSTRUMENT_REGISTRY_POLICY)


def _coerce_instrument_registry_policy(policy: dict[str, Any] | None) -> dict[str, Any]:
    return copy.deepcopy(policy) if isinstance(policy, dict) else copy.deepcopy(FAIL_CLOSED_MINIMAL_INSTRUMENT_REGISTRY_POLICY)


def _normalize_family(value: str | None) -> str:
    family = str(value or "").strip().lower()
    if family not in FAMILIES:
        raise ValueError(f"Unsupported family: {value}")
    return family


def _normalize_environment(value: str | None) -> str:
    env = str(value or "").strip().lower()
    if env not in ENVIRONMENTS:
        raise ValueError(f"Unsupported environment: {value}")
    return env


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().upper()


def _list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text.upper())
    return out


def _list_of_string_lists(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    out: list[list[str]] = []
    for group in value:
        if not isinstance(group, list):
            continue
        parsed = _list_of_strings(group)
        if parsed:
            out.append(parsed)
    return out


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _filters_index(filters: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(filters, list):
        return out
    for row in filters:
        if not isinstance(row, dict):
            continue
        key = str(row.get("filterType") or "").strip().upper()
        if key:
            out[key] = row
    return out


def _price_filter_summary(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    min_price = str(raw.get("minPrice") or "").strip()
    max_price = str(raw.get("maxPrice") or "").strip()
    tick_size = str(raw.get("tickSize") or "").strip()
    if not (min_price and max_price and tick_size):
        return None
    return {
        "min_price": min_price,
        "max_price": max_price,
        "tick_size": tick_size,
    }


def _lot_size_summary(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    min_qty = str(raw.get("minQty") or "").strip()
    max_qty = str(raw.get("maxQty") or "").strip()
    step_size = str(raw.get("stepSize") or "").strip()
    if not (min_qty and max_qty and step_size):
        return None
    return {
        "min_qty": min_qty,
        "max_qty": max_qty,
        "step_size": step_size,
    }


def _notional_summary(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    min_notional = str(
        raw.get("minNotional")
        or raw.get("notional")
        or raw.get("min_notional")
        or ""
    ).strip()
    max_notional = str(raw.get("maxNotional") or "").strip()
    avg_price_mins = raw.get("avgPriceMins")
    if not min_notional and not max_notional:
        return None
    payload: dict[str, Any] = {}
    if min_notional:
        payload["min_notional"] = min_notional
    if max_notional:
        payload["max_notional"] = max_notional
    if avg_price_mins not in {None, ""}:
        payload["avg_price_mins"] = avg_price_mins
    if "applyToMarket" in raw:
        payload["apply_to_market"] = _bool(raw.get("applyToMarket"))
    if "applyMinToMarket" in raw:
        payload["apply_min_to_market"] = _bool(raw.get("applyMinToMarket"))
    if "applyMaxToMarket" in raw:
        payload["apply_max_to_market"] = _bool(raw.get("applyMaxToMarket"))
    return payload or None


def _percent_price_summary(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    payload: dict[str, Any] = {}
    for key, target in (
        ("multiplierUp", "multiplier_up"),
        ("multiplierDown", "multiplier_down"),
        ("multiplierDecimal", "multiplier_decimal"),
        ("avgPriceMins", "avg_price_mins"),
    ):
        value = raw.get(key)
        if value not in {None, ""}:
            payload[target] = value
    return payload or None


def _percent_price_by_side_summary(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    payload: dict[str, Any] = {}
    for key, target in (
        ("bidMultiplierUp", "bid_multiplier_up"),
        ("bidMultiplierDown", "bid_multiplier_down"),
        ("askMultiplierUp", "ask_multiplier_up"),
        ("askMultiplierDown", "ask_multiplier_down"),
        ("avgPriceMins", "avg_price_mins"),
    ):
        value = raw.get(key)
        if value not in {None, ""}:
            payload[target] = value
    return payload or None


def _limit_filter_summary(raw: dict[str, Any] | None, *, target_key: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("maxNumOrders")
    if value in {None, ""}:
        value = raw.get("maxNumAlgoOrders")
    if value in {None, ""}:
        value = raw.get("limit")
    if value in {None, ""}:
        return None
    return {target_key: value, "limit": value}


def _trailing_delta_summary(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    payload: dict[str, Any] = {}
    for key, target in (
        ("minTrailingAboveDelta", "min_trailing_above_delta"),
        ("maxTrailingAboveDelta", "max_trailing_above_delta"),
        ("minTrailingBelowDelta", "min_trailing_below_delta"),
        ("maxTrailingBelowDelta", "max_trailing_below_delta"),
    ):
        value = raw.get(key)
        if value not in {None, ""}:
            payload[target] = value
    return payload or None


def _extract_filter_summary(
    filters: Any,
    *,
    family: str,
    trigger_protect: Any = None,
) -> dict[str, Any]:
    indexed = _filters_index(filters)
    summary: dict[str, Any] = {}
    price_filter = _price_filter_summary(indexed.get("PRICE_FILTER"))
    lot_size = _lot_size_summary(indexed.get("LOT_SIZE"))
    market_lot_size = _lot_size_summary(indexed.get("MARKET_LOT_SIZE"))
    min_notional = _notional_summary(indexed.get("MIN_NOTIONAL"))
    notional = _notional_summary(indexed.get("NOTIONAL"))
    percent_price = _percent_price_summary(indexed.get("PERCENT_PRICE"))
    percent_price_by_side = _percent_price_by_side_summary(indexed.get("PERCENT_PRICE_BY_SIDE"))
    max_num_orders = _limit_filter_summary(indexed.get("MAX_NUM_ORDERS"), target_key="max_num_orders")
    max_num_algo_orders = _limit_filter_summary(indexed.get("MAX_NUM_ALGO_ORDERS"), target_key="max_num_algo_orders")
    trailing_delta = _trailing_delta_summary(indexed.get("TRAILING_DELTA"))
    if price_filter is not None:
        summary["price_filter"] = price_filter
    if lot_size is not None:
        summary["lot_size"] = lot_size
    if market_lot_size is not None:
        summary["market_lot_size"] = market_lot_size
    if min_notional is not None:
        summary["min_notional"] = min_notional
    if notional is not None:
        summary["notional"] = notional
    if percent_price is not None:
        summary["percent_price"] = percent_price
    if percent_price_by_side is not None:
        summary["percent_price_by_side"] = percent_price_by_side
    if max_num_orders is not None:
        summary["max_num_orders"] = max_num_orders
    if max_num_algo_orders is not None:
        summary["max_num_algo_orders"] = max_num_algo_orders
    if trailing_delta is not None:
        summary["trailing_delta"] = trailing_delta
    summary["filter_types_present"] = sorted(indexed.keys())
    if family in {"usdm_futures", "coinm_futures"}:
        trigger = str(trigger_protect or "").strip()
        if trigger:
            summary["trigger_protect"] = {"value": trigger}
    return summary


def _has_basic_filters(item: dict[str, Any]) -> bool:
    filters = item.get("filter_summary")
    if not isinstance(filters, dict):
        return False
    return isinstance(filters.get("price_filter"), dict) and isinstance(filters.get("lot_size"), dict)


def _permission_summary_from_spot_symbol(symbol_row: dict[str, Any]) -> dict[str, Any]:
    permissions = _list_of_strings(symbol_row.get("permissions"))
    permission_sets = _list_of_string_lists(symbol_row.get("permissionSets"))
    return {
        "permissions": permissions,
        "permission_sets": permission_sets,
        "is_spot_trading_allowed": _bool(symbol_row.get("isSpotTradingAllowed")),
        "is_margin_trading_allowed": _bool(symbol_row.get("isMarginTradingAllowed")),
        "has_permission_metadata": bool(
            permissions
            or permission_sets
            or "isMarginTradingAllowed" in symbol_row
            or "isSpotTradingAllowed" in symbol_row
        ),
    }


def _permission_summary_contains(permission_summary: dict[str, Any], token: str) -> bool:
    target = str(token or "").strip().upper()
    permissions = _list_of_strings(permission_summary.get("permissions"))
    permission_sets = _list_of_string_lists(permission_summary.get("permission_sets"))
    if target in permissions:
        return True
    return any(target in group for group in permission_sets)


def _margin_symbol_supported(permission_summary: dict[str, Any]) -> bool:
    return _bool(permission_summary.get("is_margin_trading_allowed")) or _permission_summary_contains(permission_summary, "MARGIN")


def _status_is_operational(status: str) -> bool:
    return status == "TRADING"


def _delivery_is_blocked(item: dict[str, Any], policy: dict[str, Any]) -> bool:
    if item.get("family") not in {"usdm_futures", "coinm_futures"}:
        return False
    policy_map = _coerce_instrument_registry_policy(policy)
    contract_type = str(item.get("contract_type") or "").strip().upper()
    if contract_type == "PERPETUAL":
        return False
    raw_delivery = item.get("delivery_date")
    if raw_delivery in {None, "", 0, "0"}:
        return False
    try:
        delivery_ms = int(raw_delivery)
    except Exception:
        return True
    hours_threshold = float(policy_map["eligibility"]["delivery_block_if_hours_to_expiry_lt"])
    hours_to_expiry = (delivery_ms / 1000.0 - time.time()) / 3600.0
    return hours_to_expiry < hours_threshold


def evaluate_item_eligibility(
    item: dict[str, Any],
    *,
    environment: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    environment = _normalize_environment(environment)
    family = _normalize_family(item.get("family"))
    status = _normalize_status(item.get("status"))
    policy_map = _coerce_instrument_registry_policy(policy)
    elig_cfg = policy_map["eligibility"]
    family_env = policy_map["environments"][family]
    require_status_active = bool(elig_cfg["require_status_active"])
    require_basic_filters = bool(elig_cfg["require_basic_filters"])
    require_margin_metadata = bool(elig_cfg["require_permission_metadata_for_margin"])

    consistency_errors: list[str] = []
    if not _normalize_symbol(item.get("symbol")):
        consistency_errors.append("missing_symbol")
    if not str(item.get("base_asset") or "").strip():
        consistency_errors.append("missing_base_asset")
    if not str(item.get("quote_asset") or "").strip():
        consistency_errors.append("missing_quote_asset")
    if not status:
        consistency_errors.append("missing_status")

    has_basic_filters = _has_basic_filters(item)
    if require_basic_filters and not has_basic_filters:
        consistency_errors.append("missing_basic_filters")

    if require_status_active and not _status_is_operational(status):
        consistency_errors.append("status_not_operational")

    delivery_blocked = _delivery_is_blocked(item, policy_map)
    if delivery_blocked:
        consistency_errors.append("delivery_too_close_or_expired")

    permission_summary = item.get("permission_summary") if isinstance(item.get("permission_summary"), dict) else {}
    if family == "margin":
        if require_margin_metadata and not _bool(permission_summary.get("has_permission_metadata")):
            consistency_errors.append("missing_margin_permission_metadata")
        if not _margin_symbol_supported(permission_summary):
            consistency_errors.append("margin_not_supported_for_symbol")

    manually_excluded = _bool(item.get("manual_excluded"))
    if manually_excluded:
        consistency_errors.append("manual_excluded")

    paper_eligible = bool(
        not {
            "missing_symbol",
            "missing_base_asset",
            "missing_quote_asset",
            "missing_status",
            "missing_basic_filters",
        }
        & set(consistency_errors)
    )
    live_eligible = bool(
        paper_eligible
        and (not require_status_active or "status_not_operational" not in consistency_errors)
        and "delivery_too_close_or_expired" not in consistency_errors
        and "manual_excluded" not in consistency_errors
        and "missing_margin_permission_metadata" not in consistency_errors
        and "margin_not_supported_for_symbol" not in consistency_errors
    )
    env_supported = bool(family_env[environment])
    testnet_eligible = bool(environment == "testnet" and env_supported and live_eligible)

    return {
        "paper_eligible": paper_eligible,
        "live_eligible": live_eligible,
        "testnet_eligible": testnet_eligible,
        "consistency_errors": consistency_errors,
    }


def _base_item(
    *,
    family: str,
    environment: str,
    symbol: str,
    base_asset: str,
    quote_asset: str,
    status: str,
    contract_type: str | None,
    margin_asset: str | None,
    filter_summary: dict[str, Any],
    permission_summary: dict[str, Any],
    catalog_source: str,
    raw_payload: dict[str, Any],
    delivery_date: int | None = None,
    onboard_date: int | None = None,
) -> dict[str, Any]:
    return {
        "instrument_id": f"{VENUE_BINANCE}:{family}:{symbol}",
        "venue": VENUE_BINANCE,
        "family": family,
        "environment": environment,
        "symbol": symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "contract_type": contract_type,
        "margin_asset": margin_asset,
        "status": status,
        "catalog_source": catalog_source,
        "filter_summary": filter_summary,
        "permission_summary": permission_summary,
        "raw_payload": raw_payload,
        "raw_hash": _sha256_json(raw_payload),
        "delivery_date": delivery_date,
        "onboard_date": onboard_date,
        "manual_excluded": False,
    }


def parse_spot_exchange_info(
    payload: dict[str, Any],
    *,
    environment: str,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    environment = _normalize_environment(environment)
    policy_map = _coerce_instrument_registry_policy(policy)
    symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
    items: list[dict[str, Any]] = []
    for row in symbols:
        if not isinstance(row, dict):
            continue
        symbol = _normalize_symbol(row.get("symbol"))
        base_asset = str(row.get("baseAsset") or "").strip().upper()
        quote_asset = str(row.get("quoteAsset") or "").strip().upper()
        status = _normalize_status(row.get("status"))
        filter_summary = _extract_filter_summary(row.get("filters"), family="spot")
        permission_summary = _permission_summary_from_spot_symbol(row)
        item = _base_item(
            family="spot",
            environment=environment,
            symbol=symbol,
            base_asset=base_asset,
            quote_asset=quote_asset,
            status=status,
            contract_type=None,
            margin_asset=None,
            filter_summary=filter_summary,
            permission_summary=permission_summary,
            catalog_source="binance_spot_exchangeInfo",
            raw_payload=row,
        )
        item.update(evaluate_item_eligibility(item, environment=environment, policy=policy_map))
        items.append(item)
    return items


def parse_usdm_exchange_info(
    payload: dict[str, Any],
    *,
    environment: str,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    environment = _normalize_environment(environment)
    policy_map = _coerce_instrument_registry_policy(policy)
    symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
    items: list[dict[str, Any]] = []
    for row in symbols:
        if not isinstance(row, dict):
            continue
        item = _base_item(
            family="usdm_futures",
            environment=environment,
            symbol=_normalize_symbol(row.get("symbol")),
            base_asset=str(row.get("baseAsset") or "").strip().upper(),
            quote_asset=str(row.get("quoteAsset") or "").strip().upper(),
            status=_normalize_status(row.get("status")),
            contract_type=str(row.get("contractType") or "").strip().upper() or None,
            margin_asset=str(row.get("marginAsset") or "").strip().upper() or None,
            filter_summary=_extract_filter_summary(
                row.get("filters"),
                family="usdm_futures",
                trigger_protect=row.get("triggerProtect"),
            ),
            permission_summary={},
            catalog_source="binance_usdm_exchangeInfo",
            raw_payload=row,
            delivery_date=int(row.get("deliveryDate")) if str(row.get("deliveryDate") or "").strip().isdigit() else None,
            onboard_date=int(row.get("onboardDate")) if str(row.get("onboardDate") or "").strip().isdigit() else None,
        )
        item.update(evaluate_item_eligibility(item, environment=environment, policy=policy_map))
        items.append(item)
    return items


def parse_coinm_exchange_info(
    payload: dict[str, Any],
    *,
    environment: str,
    policy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    environment = _normalize_environment(environment)
    policy_map = _coerce_instrument_registry_policy(policy)
    symbols = payload.get("symbols") if isinstance(payload.get("symbols"), list) else []
    items: list[dict[str, Any]] = []
    for row in symbols:
        if not isinstance(row, dict):
            continue
        item = _base_item(
            family="coinm_futures",
            environment=environment,
            symbol=_normalize_symbol(row.get("symbol")),
            base_asset=str(row.get("baseAsset") or "").strip().upper(),
            quote_asset=str(row.get("quoteAsset") or row.get("pair") or "").strip().upper(),
            status=_normalize_status(row.get("status") or row.get("contractStatus")),
            contract_type=str(row.get("contractType") or "").strip().upper() or None,
            margin_asset=str(row.get("marginAsset") or "").strip().upper() or None,
            filter_summary=_extract_filter_summary(
                row.get("filters"),
                family="coinm_futures",
                trigger_protect=row.get("triggerProtect"),
            ),
            permission_summary={},
            catalog_source="binance_coinm_exchangeInfo",
            raw_payload=row,
            delivery_date=int(row.get("deliveryDate")) if str(row.get("deliveryDate") or "").strip().isdigit() else None,
            onboard_date=int(row.get("onboardDate")) if str(row.get("onboardDate") or "").strip().isdigit() else None,
        )
        item.update(evaluate_item_eligibility(item, environment=environment, policy=policy_map))
        items.append(item)
    return items


def derive_margin_catalog_from_spot(
    spot_items: list[dict[str, Any]],
    *,
    environment: str,
    policy: dict[str, Any] | None = None,
    account_capability: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    environment = _normalize_environment(environment)
    policy_map = _coerce_instrument_registry_policy(policy)
    account_capability = account_capability if isinstance(account_capability, dict) else {}
    items: list[dict[str, Any]] = []
    for spot_item in spot_items:
        permission_summary = (
            spot_item.get("permission_summary")
            if isinstance(spot_item.get("permission_summary"), dict)
            else {}
        )
        if not _margin_symbol_supported(permission_summary):
            continue
        derived_permission_summary = {
            **copy.deepcopy(permission_summary),
            "derived_from_family": "spot",
            "account_margin_capable": _bool(account_capability.get("can_margin")),
        }
        item = _base_item(
            family="margin",
            environment=environment,
            symbol=_normalize_symbol(spot_item.get("symbol")),
            base_asset=str(spot_item.get("base_asset") or "").strip().upper(),
            quote_asset=str(spot_item.get("quote_asset") or "").strip().upper(),
            status=_normalize_status(spot_item.get("status")),
            contract_type=None,
            margin_asset=str(spot_item.get("quote_asset") or "").strip().upper() or None,
            filter_summary=copy.deepcopy(
                spot_item.get("filter_summary") if isinstance(spot_item.get("filter_summary"), dict) else {}
            ),
            permission_summary=derived_permission_summary,
            catalog_source="binance_margin_from_spot_permissions",
            raw_payload=copy.deepcopy(
                spot_item.get("raw_payload") if isinstance(spot_item.get("raw_payload"), dict) else {}
            ),
        )
        item.update(evaluate_item_eligibility(item, environment=environment, policy=policy_map))
        item["testnet_eligible"] = False
        items.append(item)
    return items


def diff_snapshot_items(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    *,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy_map = _coerce_instrument_registry_policy(policy)
    diff_cfg = policy_map["diffing"]

    before_map = {str(item.get("instrument_id")): item for item in before if item.get("instrument_id")}
    after_map = {str(item.get("instrument_id")): item for item in after if item.get("instrument_id")}
    before_ids = set(before_map)
    after_ids = set(after_map)
    added = sorted(after_ids - before_ids)
    removed = sorted(before_ids - after_ids)
    common = before_ids & after_ids

    changed_filters = 0
    changed_permissions = 0
    changed_status = 0
    changed_any = 0
    removed_live_eligible = 0

    for instrument_id in sorted(common):
        previous = before_map[instrument_id]
        current = after_map[instrument_id]
        filters_changed = _json_dumps(previous.get("filter_summary") or {}) != _json_dumps(current.get("filter_summary") or {})
        permissions_changed = _json_dumps(previous.get("permission_summary") or {}) != _json_dumps(current.get("permission_summary") or {})
        status_changed = str(previous.get("status") or "") != str(current.get("status") or "")
        live_before = _bool(previous.get("live_eligible"))
        live_after = _bool(current.get("live_eligible"))
        if filters_changed:
            changed_filters += 1
        if permissions_changed:
            changed_permissions += 1
        if status_changed:
            changed_status += 1
        if filters_changed or permissions_changed or status_changed or live_before != live_after:
            changed_any += 1
        if live_before and not live_after:
            removed_live_eligible += 1

    for instrument_id in removed:
        if _bool(before_map[instrument_id].get("live_eligible")):
            removed_live_eligible += 1

    before_count = len(before_map)
    after_count = len(after_map)
    live_before_count = sum(1 for row in before_map.values() if _bool(row.get("live_eligible")))
    live_after_count = sum(1 for row in after_map.values() if _bool(row.get("live_eligible")))
    delta_pct = 0.0 if before_count <= 0 else abs(after_count - before_count) * 100.0 / float(before_count)

    severity = "OK"
    blockers: list[str] = []
    if bool(diff_cfg["enabled"]) and before_count > 0:
        if delta_pct >= float(diff_cfg["symbol_count_block_delta_pct"]):
            severity = "BLOCK"
            blockers.append("symbol_count_block_delta_pct")
        elif delta_pct >= float(diff_cfg["symbol_count_warn_delta_pct"]):
            severity = "WARN"
        if removed_live_eligible >= int(diff_cfg["removed_live_eligible_block_count"]):
            severity = "BLOCK"
            blockers.append("removed_live_eligible_block_count")
        elif severity != "BLOCK" and removed_live_eligible >= int(diff_cfg["removed_live_eligible_warn_count"]):
            severity = "WARN"

    return {
        "first_snapshot": before_count == 0,
        "symbols_added": len(added),
        "symbols_removed": len(removed),
        "symbols_changed": changed_any,
        "symbol_count_before": before_count,
        "symbol_count_after": after_count,
        "live_eligible_before": live_before_count,
        "live_eligible_after": live_after_count,
        "changed_filters_count": changed_filters,
        "changed_permissions_count": changed_permissions,
        "changed_status_count": changed_status,
        "removed_live_eligible_count": removed_live_eligible,
        "symbol_count_delta_pct": round(delta_pct, 4),
        "severity": severity,
        "blockers": blockers,
    }


def _freshness_payload(fetched_at: str | None, policy: dict[str, Any]) -> dict[str, Any]:
    policy_map = _coerce_instrument_registry_policy(policy)
    freshness_cfg = policy_map["freshness"]
    warn_hours = float(freshness_cfg["warn_if_snapshot_older_than_hours"])
    block_hours = float(freshness_cfg["block_if_snapshot_older_than_hours"])
    if not fetched_at:
        return {
            "status": "missing",
            "age_hours": None,
            "warn_after_hours": warn_hours,
            "block_after_hours": block_hours,
        }
    try:
        dt = datetime.fromisoformat(str(fetched_at))
    except Exception:
        return {
            "status": "missing",
            "age_hours": None,
            "warn_after_hours": warn_hours,
            "block_after_hours": block_hours,
        }
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (_utc_now() - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
    status = "fresh"
    if age_hours >= block_hours:
        status = "block"
    elif age_hours >= warn_hours:
        status = "warn"
    return {
        "status": status,
        "age_hours": round(age_hours, 4),
        "warn_after_hours": warn_hours,
        "block_after_hours": block_hours,
    }


def _url_root(url: str) -> str:
    parts = urlsplit(str(url or "").strip())
    return f"{parts.scheme}://{parts.netloc}".rstrip("/")


def _url_path(url: str) -> str:
    return urlsplit(str(url or "").strip()).path


def _apply_base_override(endpoint_url: str, override: str | None) -> str:
    raw_override = str(override or "").strip()
    if not raw_override:
        return endpoint_url
    base = raw_override.rstrip("/")
    path = _url_path(endpoint_url)
    return f"{base}{path}"


def _first_env_pair(pairs: list[tuple[str, str]]) -> tuple[str, str, list[str]]:
    tried: list[str] = []
    for key_name, secret_name in pairs:
        tried.extend([key_name, secret_name])
        key = str(os.getenv(key_name, "")).strip()
        secret = str(os.getenv(secret_name, "")).strip()
        if key and secret:
            return key, secret, tried
    return "", "", tried


def _credentials_for_family(family: str, environment: str) -> tuple[str, str, list[str]]:
    family = _normalize_family(family)
    environment = _normalize_environment(environment)
    mapping: dict[tuple[str, str], list[tuple[str, str]]] = {
        ("spot", "live"): [("BINANCE_API_KEY", "BINANCE_API_SECRET")],
        ("spot", "testnet"): [("BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET")],
        ("margin", "live"): [("BINANCE_API_KEY", "BINANCE_API_SECRET")],
        ("usdm_futures", "live"): [
            ("BINANCE_USDM_API_KEY", "BINANCE_USDM_API_SECRET"),
            ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_API_SECRET"),
            ("BINANCE_API_KEY", "BINANCE_API_SECRET"),
        ],
        ("usdm_futures", "testnet"): [
            ("BINANCE_USDM_TESTNET_API_KEY", "BINANCE_USDM_TESTNET_API_SECRET"),
            ("BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"),
        ],
        ("coinm_futures", "live"): [
            ("BINANCE_COINM_API_KEY", "BINANCE_COINM_API_SECRET"),
            ("BINANCE_FUTURES_API_KEY", "BINANCE_FUTURES_API_SECRET"),
            ("BINANCE_API_KEY", "BINANCE_API_SECRET"),
        ],
        ("coinm_futures", "testnet"): [
            ("BINANCE_COINM_TESTNET_API_KEY", "BINANCE_COINM_TESTNET_API_SECRET"),
            ("BINANCE_FUTURES_TESTNET_API_KEY", "BINANCE_FUTURES_TESTNET_API_SECRET"),
        ],
    }
    return _first_env_pair(mapping.get((family, environment), []))


class BinanceInstrumentRegistryDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS id_sequences (
                  prefix TEXT PRIMARY KEY,
                  next_value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS instrument_registry (
                  instrument_id TEXT PRIMARY KEY,
                  venue TEXT NOT NULL,
                  family TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  base_asset TEXT NOT NULL,
                  quote_asset TEXT NOT NULL,
                  contract_type TEXT,
                  margin_asset TEXT,
                  status TEXT,
                  is_active INTEGER NOT NULL DEFAULT 0,
                  live_eligible INTEGER NOT NULL DEFAULT 0,
                  paper_eligible INTEGER NOT NULL DEFAULT 0,
                  testnet_eligible INTEGER NOT NULL DEFAULT 0,
                  manual_excluded INTEGER NOT NULL DEFAULT 0,
                  catalog_source TEXT NOT NULL,
                  first_seen_at TEXT NOT NULL,
                  last_seen_at TEXT NOT NULL,
                  last_snapshot_id TEXT,
                  raw_hash TEXT NOT NULL,
                  raw_payload_json TEXT NOT NULL DEFAULT '{}',
                  archived_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_instrument_registry_family ON instrument_registry(family, is_active, symbol);
                CREATE INDEX IF NOT EXISTS idx_instrument_registry_symbol ON instrument_registry(symbol);

                CREATE TABLE IF NOT EXISTS instrument_catalog_snapshots (
                  snapshot_id TEXT PRIMARY KEY,
                  venue TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  fetched_at TEXT NOT NULL,
                  source_endpoint TEXT NOT NULL,
                  source_hash TEXT NOT NULL,
                  symbol_count INTEGER NOT NULL,
                  raw_payload_json TEXT,
                  success INTEGER NOT NULL DEFAULT 1,
                  error_message TEXT,
                  parser_version TEXT NOT NULL,
                  policy_hash TEXT NOT NULL,
                  first_snapshot INTEGER NOT NULL DEFAULT 0,
                  diff_severity TEXT NOT NULL DEFAULT 'OK',
                  diff_summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_catalog_snapshots_family_env ON instrument_catalog_snapshots(family, environment, fetched_at DESC);

                CREATE TABLE IF NOT EXISTS instrument_catalog_snapshot_items (
                  snapshot_id TEXT NOT NULL,
                  instrument_id TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  status TEXT,
                  base_asset TEXT NOT NULL,
                  quote_asset TEXT NOT NULL,
                  contract_type TEXT,
                  margin_asset TEXT,
                  catalog_source TEXT NOT NULL,
                  filter_summary_json TEXT NOT NULL,
                  permission_summary_json TEXT NOT NULL,
                  live_eligible INTEGER NOT NULL DEFAULT 0,
                  testnet_eligible INTEGER NOT NULL DEFAULT 0,
                  paper_eligible INTEGER NOT NULL DEFAULT 0,
                  raw_hash TEXT NOT NULL,
                  raw_payload_json TEXT NOT NULL DEFAULT '{}',
                  PRIMARY KEY (snapshot_id, instrument_id)
                );
                CREATE INDEX IF NOT EXISTS idx_snapshot_items_family_env ON instrument_catalog_snapshot_items(family, environment, symbol);

                CREATE TABLE IF NOT EXISTS account_capability_snapshots (
                  capability_snapshot_id TEXT PRIMARY KEY,
                  venue TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  fetched_at TEXT NOT NULL,
                  can_read_market_data INTEGER NOT NULL DEFAULT 0,
                  can_trade INTEGER NOT NULL DEFAULT 0,
                  can_margin INTEGER NOT NULL DEFAULT 0,
                  can_user_data INTEGER NOT NULL DEFAULT 0,
                  can_testnet INTEGER NOT NULL DEFAULT 0,
                  capability_source TEXT NOT NULL,
                  notes_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_capability_snapshots_family_env ON account_capability_snapshots(family, environment, fetched_at DESC);
                """
            )
            conn.commit()

    def next_formatted_id(self, prefix: str, *, width: int = 6) -> str:
        px = str(prefix).upper()
        with self._connect() as conn:
            row = conn.execute("SELECT next_value FROM id_sequences WHERE prefix = ?", (px,)).fetchone()
            if row is None:
                next_val = 1
                conn.execute("INSERT INTO id_sequences (prefix, next_value) VALUES (?, ?)", (px, 2))
            else:
                next_val = int(row["next_value"])
                conn.execute("UPDATE id_sequences SET next_value = ? WHERE prefix = ?", (next_val + 1, px))
            conn.commit()
        return f"{px}-{next_val:0{width}d}"

    @staticmethod
    def _snapshot_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "snapshot_id": str(row["snapshot_id"]),
            "venue": str(row["venue"]),
            "family": str(row["family"]),
            "environment": str(row["environment"]),
            "fetched_at": str(row["fetched_at"]),
            "source_endpoint": str(row["source_endpoint"]),
            "source_hash": str(row["source_hash"] or ""),
            "symbol_count": int(row["symbol_count"] or 0),
            "raw_payload_json": _json_loads(row["raw_payload_json"], {}),
            "success": _bool(row["success"]),
            "error_message": str(row["error_message"] or "") or None,
            "parser_version": str(row["parser_version"] or ""),
            "policy_hash": str(row["policy_hash"] or ""),
            "first_snapshot": _bool(row["first_snapshot"]),
            "diff_severity": str(row["diff_severity"] or "OK"),
            "diff_summary": _json_loads(row["diff_summary_json"], {}),
        }

    @staticmethod
    def _capability_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "capability_snapshot_id": str(row["capability_snapshot_id"]),
            "venue": str(row["venue"]),
            "family": str(row["family"]),
            "environment": str(row["environment"]),
            "fetched_at": str(row["fetched_at"]),
            "can_read_market_data": _bool(row["can_read_market_data"]),
            "can_trade": _bool(row["can_trade"]),
            "can_margin": _bool(row["can_margin"]),
            "can_user_data": _bool(row["can_user_data"]),
            "can_testnet": _bool(row["can_testnet"]),
            "capability_source": str(row["capability_source"] or ""),
            "notes": _json_loads(row["notes_json"], {}),
        }

    def latest_snapshot(
        self,
        family: str,
        environment: str,
        *,
        success_only: bool = False,
    ) -> dict[str, Any] | None:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        sql = """
            SELECT *
            FROM instrument_catalog_snapshots
            WHERE family = ?
              AND environment = ?
        """
        params: list[Any] = [family, environment]
        if success_only:
            sql += " AND success = 1"
        sql += " ORDER BY fetched_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return self._snapshot_row_to_dict(row) if row is not None else None

    def latest_snapshots_by_family(self, family: str) -> dict[str, dict[str, Any]]:
        family = _normalize_family(family)
        out: dict[str, dict[str, Any]] = {}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM instrument_catalog_snapshots
                WHERE family = ?
                ORDER BY fetched_at DESC
                """,
                (family,),
            ).fetchall()
        for row in rows:
            env = str(row["environment"] or "").strip().lower()
            if env and env not in out:
                out[env] = self._snapshot_row_to_dict(row)
        return out

    def latest_successful_snapshots_by_family(self, family: str) -> dict[str, dict[str, Any]]:
        family = _normalize_family(family)
        out: dict[str, dict[str, Any]] = {}
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM instrument_catalog_snapshots
                WHERE family = ?
                  AND success = 1
                ORDER BY fetched_at DESC
                """,
                (family,),
            ).fetchall()
        for row in rows:
            env = str(row["environment"] or "").strip().lower()
            if env and env not in out:
                out[env] = self._snapshot_row_to_dict(row)
        return out

    def snapshot_items(self, snapshot_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM instrument_catalog_snapshot_items
                WHERE snapshot_id = ?
                ORDER BY symbol ASC
                """,
                (str(snapshot_id),),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "snapshot_id": str(row["snapshot_id"]),
                    "instrument_id": str(row["instrument_id"]),
                    "symbol": str(row["symbol"]),
                    "family": str(row["family"]),
                    "environment": str(row["environment"]),
                    "status": str(row["status"] or ""),
                    "base_asset": str(row["base_asset"] or ""),
                    "quote_asset": str(row["quote_asset"] or ""),
                    "contract_type": str(row["contract_type"] or "") or None,
                    "margin_asset": str(row["margin_asset"] or "") or None,
                    "catalog_source": str(row["catalog_source"] or ""),
                    "filter_summary": _json_loads(row["filter_summary_json"], {}),
                    "permission_summary": _json_loads(row["permission_summary_json"], {}),
                    "live_eligible": _bool(row["live_eligible"]),
                    "testnet_eligible": _bool(row["testnet_eligible"]),
                    "paper_eligible": _bool(row["paper_eligible"]),
                    "raw_hash": str(row["raw_hash"] or ""),
                    "raw_payload": _json_loads(row["raw_payload_json"], {}),
                }
            )
        return items

    def save_snapshot(
        self,
        *,
        family: str,
        environment: str,
        source_endpoint: str,
        raw_payload: dict[str, Any],
        items: list[dict[str, Any]],
        policy_hash: str,
    ) -> dict[str, Any]:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        previous = self.latest_snapshot(family, environment, success_only=True)
        previous_items = self.snapshot_items(previous["snapshot_id"]) if previous else []
        diff_summary = diff_snapshot_items(previous_items, items, policy=instrument_registry_policy())
        snapshot_id = self.next_formatted_id("CAT")
        fetched_at = utc_now_iso()
        source_hash = _sha256_json(raw_payload)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO instrument_catalog_snapshots (
                  snapshot_id, venue, family, environment, fetched_at,
                  source_endpoint, source_hash, symbol_count, raw_payload_json,
                  success, error_message, parser_version, policy_hash,
                  first_snapshot, diff_severity, diff_summary_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    VENUE_BINANCE,
                    family,
                    environment,
                    fetched_at,
                    str(source_endpoint),
                    source_hash,
                    len(items),
                    _json_dumps(raw_payload),
                    PARSER_VERSION,
                    str(policy_hash),
                    1 if diff_summary["first_snapshot"] else 0,
                    str(diff_summary["severity"]),
                    _json_dumps(diff_summary),
                ),
            )
            for item in items:
                conn.execute(
                    """
                    INSERT INTO instrument_catalog_snapshot_items (
                      snapshot_id, instrument_id, symbol, family, environment,
                      status, base_asset, quote_asset, contract_type, margin_asset,
                      catalog_source, filter_summary_json, permission_summary_json,
                      live_eligible, testnet_eligible, paper_eligible,
                      raw_hash, raw_payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        str(item.get("instrument_id")),
                        str(item.get("symbol")),
                        family,
                        environment,
                        str(item.get("status") or ""),
                        str(item.get("base_asset") or ""),
                        str(item.get("quote_asset") or ""),
                        str(item.get("contract_type") or "") or None,
                        str(item.get("margin_asset") or "") or None,
                        str(item.get("catalog_source") or ""),
                        _json_dumps(item.get("filter_summary") or {}),
                        _json_dumps(item.get("permission_summary") or {}),
                        1 if _bool(item.get("live_eligible")) else 0,
                        1 if _bool(item.get("testnet_eligible")) else 0,
                        1 if _bool(item.get("paper_eligible")) else 0,
                        str(item.get("raw_hash") or _sha256_json(item)),
                        _json_dumps(item.get("raw_payload") or {}),
                    ),
                )
            conn.commit()
        self._rebuild_family_registry(family)
        return self.latest_snapshot(family, environment, success_only=False) or {
            "snapshot_id": snapshot_id,
            "diff_summary": diff_summary,
        }

    def save_failed_snapshot(
        self,
        *,
        family: str,
        environment: str,
        source_endpoint: str,
        error_message: str,
        policy_hash: str,
    ) -> dict[str, Any]:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        snapshot_id = self.next_formatted_id("CAT")
        fetched_at = utc_now_iso()
        first_snapshot = self.latest_snapshot(family, environment, success_only=True) is None
        diff_summary = {
            "first_snapshot": first_snapshot,
            "symbols_added": 0,
            "symbols_removed": 0,
            "symbols_changed": 0,
            "symbol_count_before": 0,
            "symbol_count_after": 0,
            "live_eligible_before": 0,
            "live_eligible_after": 0,
            "changed_filters_count": 0,
            "changed_permissions_count": 0,
            "changed_status_count": 0,
            "removed_live_eligible_count": 0,
            "symbol_count_delta_pct": 0.0,
            "severity": "BLOCK",
            "blockers": ["snapshot_fetch_failed"],
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO instrument_catalog_snapshots (
                  snapshot_id, venue, family, environment, fetched_at,
                  source_endpoint, source_hash, symbol_count, raw_payload_json,
                  success, error_message, parser_version, policy_hash,
                  first_snapshot, diff_severity, diff_summary_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, 0, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    VENUE_BINANCE,
                    family,
                    environment,
                    fetched_at,
                    str(source_endpoint),
                    "",
                    str(error_message or "snapshot_fetch_failed"),
                    PARSER_VERSION,
                    str(policy_hash),
                    1 if first_snapshot else 0,
                    "BLOCK",
                    _json_dumps(diff_summary),
                ),
            )
            conn.commit()
        return self.latest_snapshot(family, environment, success_only=False) or {
            "snapshot_id": snapshot_id,
            "success": False,
            "error_message": error_message,
        }

    def save_capability_snapshot(
        self,
        *,
        family: str,
        environment: str,
        can_read_market_data: bool,
        can_trade: bool,
        can_margin: bool,
        can_user_data: bool,
        can_testnet: bool,
        capability_source: str,
        notes: dict[str, Any],
    ) -> dict[str, Any]:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        capability_snapshot_id = self.next_formatted_id("CAP")
        fetched_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO account_capability_snapshots (
                  capability_snapshot_id, venue, family, environment, fetched_at,
                  can_read_market_data, can_trade, can_margin, can_user_data, can_testnet,
                  capability_source, notes_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    capability_snapshot_id,
                    VENUE_BINANCE,
                    family,
                    environment,
                    fetched_at,
                    1 if can_read_market_data else 0,
                    1 if can_trade else 0,
                    1 if can_margin else 0,
                    1 if can_user_data else 0,
                    1 if can_testnet else 0,
                    str(capability_source or "unknown"),
                    _json_dumps(notes or {}),
                ),
            )
            conn.commit()
        return self.latest_capability_snapshot(family, environment) or {}

    def latest_capability_snapshot(self, family: str, environment: str) -> dict[str, Any] | None:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM account_capability_snapshots
                WHERE family = ?
                  AND environment = ?
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (family, environment),
            ).fetchone()
        return self._capability_row_to_dict(row) if row is not None else None

    def list_snapshots(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if family is not None:
            clauses.append("family = ?")
            params.append(_normalize_family(family))
        if environment is not None:
            clauses.append("environment = ?")
            params.append(_normalize_environment(environment))
        sql = "SELECT * FROM instrument_catalog_snapshots"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(max(1, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._snapshot_row_to_dict(row) for row in rows]

    def registry_rows(self, *, family: str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if family is not None:
            clauses.append("family = ?")
            params.append(_normalize_family(family))
        if active_only:
            clauses.append("is_active = 1")
        sql = "SELECT * FROM instrument_registry"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY family ASC, symbol ASC"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "instrument_id": str(row["instrument_id"]),
                    "venue": str(row["venue"]),
                    "family": str(row["family"]),
                    "symbol": str(row["symbol"]),
                    "base_asset": str(row["base_asset"]),
                    "quote_asset": str(row["quote_asset"]),
                    "contract_type": str(row["contract_type"] or "") or None,
                    "margin_asset": str(row["margin_asset"] or "") or None,
                    "status": str(row["status"] or ""),
                    "is_active": _bool(row["is_active"]),
                    "live_eligible": _bool(row["live_eligible"]),
                    "paper_eligible": _bool(row["paper_eligible"]),
                    "testnet_eligible": _bool(row["testnet_eligible"]),
                    "manual_excluded": _bool(row["manual_excluded"]),
                    "catalog_source": str(row["catalog_source"]),
                    "first_seen_at": str(row["first_seen_at"]),
                    "last_seen_at": str(row["last_seen_at"]),
                    "last_snapshot_id": str(row["last_snapshot_id"] or "") or None,
                    "raw_hash": str(row["raw_hash"]),
                    "raw_payload": _json_loads(row["raw_payload_json"], {}),
                    "archived_at": str(row["archived_at"] or "") or None,
                }
            )
        return out

    def _rebuild_family_registry(self, family: str) -> None:
        family = _normalize_family(family)
        latest_success = self.latest_successful_snapshots_by_family(family)
        existing_rows = {row["instrument_id"]: row for row in self.registry_rows(family=family, active_only=False)}
        live_items = self.snapshot_items(latest_success["live"]["snapshot_id"]) if "live" in latest_success else []
        testnet_items = self.snapshot_items(latest_success["testnet"]["snapshot_id"]) if "testnet" in latest_success else []

        union_map: dict[str, dict[str, Any]] = {}
        for env_name, items in (("live", live_items), ("testnet", testnet_items)):
            for item in items:
                record = union_map.setdefault(str(item["instrument_id"]), {})
                record[env_name] = item

        now_iso = utc_now_iso()
        with self._connect() as conn:
            for instrument_id, env_items in union_map.items():
                live_item = env_items.get("live")
                testnet_item = env_items.get("testnet")
                preferred = live_item or testnet_item
                if not preferred:
                    continue
                existing = existing_rows.get(instrument_id) or {}
                manual_excluded = _bool(existing.get("manual_excluded"))
                live_eligible = _bool(live_item.get("live_eligible")) if isinstance(live_item, dict) else False
                testnet_eligible = _bool(testnet_item.get("testnet_eligible")) if isinstance(testnet_item, dict) else False
                paper_eligible = bool(
                    (isinstance(live_item, dict) and _bool(live_item.get("paper_eligible")))
                    or (isinstance(testnet_item, dict) and _bool(testnet_item.get("paper_eligible")))
                )
                if manual_excluded:
                    live_eligible = False
                first_seen_at = str(existing.get("first_seen_at") or now_iso)
                last_snapshot_id = (
                    str((live_item or testnet_item).get("snapshot_id") or "")
                    or str((preferred or {}).get("snapshot_id") or "")
                    or None
                )
                conn.execute(
                    """
                    INSERT INTO instrument_registry (
                      instrument_id, venue, family, symbol, base_asset, quote_asset,
                      contract_type, margin_asset, status, is_active,
                      live_eligible, paper_eligible, testnet_eligible, manual_excluded,
                      catalog_source, first_seen_at, last_seen_at, last_snapshot_id,
                      raw_hash, raw_payload_json, archived_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(instrument_id) DO UPDATE SET
                      venue = excluded.venue,
                      family = excluded.family,
                      symbol = excluded.symbol,
                      base_asset = excluded.base_asset,
                      quote_asset = excluded.quote_asset,
                      contract_type = excluded.contract_type,
                      margin_asset = excluded.margin_asset,
                      status = excluded.status,
                      is_active = excluded.is_active,
                      live_eligible = excluded.live_eligible,
                      paper_eligible = excluded.paper_eligible,
                      testnet_eligible = excluded.testnet_eligible,
                      catalog_source = excluded.catalog_source,
                      last_seen_at = excluded.last_seen_at,
                      last_snapshot_id = excluded.last_snapshot_id,
                      raw_hash = excluded.raw_hash,
                      raw_payload_json = excluded.raw_payload_json,
                      archived_at = NULL
                    """,
                    (
                        instrument_id,
                        VENUE_BINANCE,
                        family,
                        str(preferred.get("symbol") or ""),
                        str(preferred.get("base_asset") or ""),
                        str(preferred.get("quote_asset") or ""),
                        str(preferred.get("contract_type") or "") or None,
                        str(preferred.get("margin_asset") or "") or None,
                        str(preferred.get("status") or ""),
                        1,
                        1 if live_eligible else 0,
                        1 if paper_eligible else 0,
                        1 if testnet_eligible else 0,
                        1 if manual_excluded else 0,
                        str(preferred.get("catalog_source") or ""),
                        first_seen_at,
                        now_iso,
                        last_snapshot_id,
                        str(preferred.get("raw_hash") or _sha256_json(preferred)),
                        _json_dumps(preferred.get("raw_payload") or {}),
                    ),
                )
            missing_ids = set(existing_rows) - set(union_map)
            for instrument_id in missing_ids:
                conn.execute(
                    """
                    UPDATE instrument_registry
                    SET is_active = 0,
                        live_eligible = 0,
                        paper_eligible = 0,
                        testnet_eligible = 0,
                        last_seen_at = ?,
                        archived_at = COALESCE(archived_at, ?)
                    WHERE instrument_id = ?
                    """,
                    (now_iso, now_iso, instrument_id),
                )
            conn.commit()


class BinanceInstrumentRegistryService:
    def __init__(
        self,
        *,
        db_path: Path,
        repo_root: Path | None = None,
        explicit_policy_root: Path | None = None,
    ) -> None:
        self.repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
        self.explicit_policy_root = explicit_policy_root.resolve() if explicit_policy_root is not None else None
        self.db = BinanceInstrumentRegistryDB(db_path)

    def policy_bundle(self) -> dict[str, Any]:
        return load_instrument_registry_bundle(self.repo_root, explicit_root=self.explicit_policy_root)

    def policy(self) -> dict[str, Any]:
        return instrument_registry_policy(self.repo_root, explicit_root=self.explicit_policy_root)

    def policy_source(self) -> dict[str, Any]:
        bundle = self.policy_bundle()
        return {
            "path": bundle.get("path"),
            "source_root": bundle.get("source_root"),
            "source_hash": bundle.get("source_hash"),
            "policy_hash": bundle.get("policy_hash"),
            "valid": bool(bundle.get("valid")),
            "source": bundle.get("source"),
            "errors": list(bundle.get("errors") or []),
            "warnings": list(bundle.get("warnings") or []),
            "fallback_used": bool(bundle.get("fallback_used")),
            "selected_role": bundle.get("selected_role"),
            "canonical_root": bundle.get("canonical_root"),
            "canonical_role": bundle.get("canonical_role"),
            "divergent_candidates": copy.deepcopy(bundle.get("divergent_candidates") or []),
        }

    def _family_environment_supported(self, family: str, environment: str) -> bool:
        policy_map = self.policy()
        family_name = _normalize_family(family)
        environment_name = _normalize_environment(environment)
        return bool(policy_map["environments"][family_name][environment_name])

    def _public_exchange_endpoint(self, family: str, environment: str) -> str:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        endpoints = self.policy()["endpoints"]
        family_cfg = endpoints[family]
        endpoint = str(family_cfg[environment] or "").strip()
        if family == "spot":
            override = os.getenv("BINANCE_SPOT_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_SPOT_BASE_URL")
            return _apply_base_override(endpoint, override)
        if family == "usdm_futures":
            override = os.getenv("BINANCE_USDM_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_USDM_BASE_URL")
            return _apply_base_override(endpoint, override)
        if family == "coinm_futures":
            override = os.getenv("BINANCE_COINM_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_COINM_BASE_URL")
            return _apply_base_override(endpoint, override)
        raise ValueError(f"Unsupported public endpoint family: {family}")

    def _account_endpoint(self, family: str, environment: str) -> str:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        endpoints = self.policy()["endpoints"]
        if family == "spot":
            spot_cfg = endpoints["spot"]
            exchange_endpoint = str(spot_cfg[environment] or "").strip()
            root = _url_root(self._public_exchange_endpoint("spot", environment) or exchange_endpoint)
            return f"{root}{str(spot_cfg['account']).strip()}"
        if family == "margin":
            margin_cfg = endpoints["margin"]
            if environment == "testnet":
                return str(margin_cfg["testnet_account"] or "").strip()
            return str(margin_cfg["live_account"] or "").strip()
        if family == "usdm_futures":
            futures_cfg = endpoints["usdm_futures"]
            endpoint = str(futures_cfg["account_testnet" if environment == "testnet" else "account_live"] or "").strip()
            override = os.getenv("BINANCE_USDM_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_USDM_BASE_URL")
            return _apply_base_override(endpoint, override)
        if family == "coinm_futures":
            futures_cfg = endpoints["coinm_futures"]
            endpoint = str(futures_cfg["account_testnet" if environment == "testnet" else "account_live"] or "").strip()
            override = os.getenv("BINANCE_COINM_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_COINM_BASE_URL")
            return _apply_base_override(endpoint, override)
        raise ValueError(f"Unsupported account endpoint family: {family}")

    def _request_json(self, url: str) -> dict[str, Any]:
        sync_cfg = self.policy()["sync"]
        timeout = float(sync_cfg["request_timeout_sec"])
        retries = int(sync_cfg["retries"])
        backoff = list(sync_cfg["retry_backoff_sec"])
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = requests.get(url, timeout=timeout)
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else {"data": payload}
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    break
                sleep_for = float(backoff[min(attempt, len(backoff) - 1)] if backoff else 0.5)
                time.sleep(max(0.0, sleep_for))
        raise RuntimeError(f"Binance request failed for {url}: {last_error}") from last_error

    def _request_signed_json(self, endpoint_url: str, *, family: str, environment: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        api_key, api_secret, env_names = _credentials_for_family(family, environment)
        if not api_key or not api_secret or not endpoint_url:
            return None, {
                "credentials_present": False,
                "credential_envs_tried": env_names,
                "endpoint": endpoint_url,
                "reason": "missing_credentials",
            }
        sync_cfg = self.policy()["sync"]
        timeout = float(sync_cfg["request_timeout_sec"])
        params = {
            "timestamp": int(time.time() * 1000),
            "recvWindow": 5000,
        }
        query = urlencode(params)
        signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        url = f"{endpoint_url}?{query}&signature={signature}"
        headers = {"X-MBX-APIKEY": api_key}
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            return (
                payload if isinstance(payload, dict) else {"data": payload},
                {
                    "credentials_present": True,
                    "credential_envs_tried": env_names,
                    "endpoint": endpoint_url,
                    "reason": "ok",
                },
            )
        except Exception as exc:
            return None, {
                "credentials_present": True,
                "credential_envs_tried": env_names,
                "endpoint": endpoint_url,
                "reason": "signed_request_failed",
                "error": str(exc),
            }

    def _build_capability_snapshot(self, family: str, environment: str, *, catalog_success: bool) -> dict[str, Any]:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        supported = self._family_environment_supported(family, environment)
        if not supported:
            return self.db.save_capability_snapshot(
                family=family,
                environment=environment,
                can_read_market_data=False,
                can_trade=False,
                can_margin=False,
                can_user_data=False,
                can_testnet=False,
                capability_source="unsupported_environment",
                notes={"supported": False, "environment": environment},
            )

        endpoint = self._account_endpoint(family, environment)
        if family == "margin" and environment == "testnet":
            return self.db.save_capability_snapshot(
                family=family,
                environment=environment,
                can_read_market_data=False,
                can_trade=False,
                can_margin=False,
                can_user_data=False,
                can_testnet=False,
                capability_source="margin_testnet_unsupported",
                notes={"supported": False, "endpoint": endpoint},
            )

        payload, meta = self._request_signed_json(endpoint, family=family, environment=environment)
        if payload is None:
            return self.db.save_capability_snapshot(
                family=family,
                environment=environment,
                can_read_market_data=catalog_success,
                can_trade=False,
                can_margin=False,
                can_user_data=False,
                can_testnet=environment == "testnet" and supported and catalog_success,
                capability_source="signed_request_unavailable",
                notes=meta,
            )

        can_trade = _bool(payload.get("canTrade") or payload.get("tradeEnabled"))
        can_user_data = True
        can_margin = False
        if family == "margin":
            can_margin = _bool(payload.get("borrowEnabled")) or _bool(payload.get("created"))
            can_trade = _bool(payload.get("tradeEnabled"))
        elif family == "usdm_futures":
            can_margin = any(_bool(row.get("marginAvailable")) for row in (payload.get("assets") or []) if isinstance(row, dict))
        elif family == "coinm_futures":
            can_margin = bool(payload.get("assets"))
        notes = {**meta, "verified": True}
        return self.db.save_capability_snapshot(
            family=family,
            environment=environment,
            can_read_market_data=catalog_success,
            can_trade=can_trade,
            can_margin=can_margin,
            can_user_data=can_user_data,
            can_testnet=environment == "testnet" and supported,
            capability_source=f"binance_{family}_account",
            notes=notes,
        )

    def _catalog_payload_for_family(self, family: str, environment: str) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        policy_map = self.policy()
        if family == "spot":
            endpoint = self._public_exchange_endpoint("spot", environment)
            payload = self._request_json(endpoint)
            return endpoint, payload, parse_spot_exchange_info(payload, environment=environment, policy=policy_map)
        if family == "usdm_futures":
            endpoint = self._public_exchange_endpoint("usdm_futures", environment)
            payload = self._request_json(endpoint)
            return endpoint, payload, parse_usdm_exchange_info(payload, environment=environment, policy=policy_map)
        if family == "coinm_futures":
            endpoint = self._public_exchange_endpoint("coinm_futures", environment)
            payload = self._request_json(endpoint)
            return endpoint, payload, parse_coinm_exchange_info(payload, environment=environment, policy=policy_map)
        if family == "margin":
            spot_endpoint = self._public_exchange_endpoint("spot", "live")
            spot_payload = self._request_json(spot_endpoint)
            spot_items = parse_spot_exchange_info(spot_payload, environment="live", policy=policy_map)
            capability = self._build_capability_snapshot("margin", "live", catalog_success=True)
            items = derive_margin_catalog_from_spot(
                spot_items,
                environment="live",
                policy=policy_map,
                account_capability=capability,
            )
            raw_payload = {
                "derived_from": "spot_exchangeInfo",
                "source_endpoint": spot_endpoint,
                "source_hash": _sha256_json(spot_payload),
                "symbol_count": len(items),
            }
            return "derived:spot:/api/v3/exchangeInfo", raw_payload, items
        raise ValueError(f"Unsupported family: {family}")

    def sync(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        startup: bool = False,
    ) -> dict[str, Any]:
        policy_map = self.policy()
        sync_cfg = policy_map["sync"]
        if not startup and not bool(sync_cfg["manual_enabled"]):
            raise RuntimeError("Manual instrument sync disabled by policy")

        families = [_normalize_family(family)] if family else list(FAMILIES)
        envs = [_normalize_environment(environment)] if environment else list(ENVIRONMENTS)
        deadline = time.time() + float(sync_cfg["startup_timeout_sec"]) if startup else None

        results: list[dict[str, Any]] = []
        for family_name in families:
            for env_name in envs:
                if not self._family_environment_supported(family_name, env_name):
                    continue
                if startup and deadline is not None and time.time() > deadline:
                    results.append(
                        {
                            "family": family_name,
                            "environment": env_name,
                            "ok": False,
                            "skipped": True,
                            "reason": "startup_timeout_exceeded",
                        }
                    )
                    continue
                try:
                    endpoint, raw_payload, items = self._catalog_payload_for_family(family_name, env_name)
                    snapshot = self.db.save_snapshot(
                        family=family_name,
                        environment=env_name,
                        source_endpoint=endpoint,
                        raw_payload=raw_payload,
                        items=items,
                        policy_hash=str(self.policy_source().get("policy_hash") or ""),
                    )
                    capability = self._build_capability_snapshot(family_name, env_name, catalog_success=True)
                    results.append(
                        {
                            "family": family_name,
                            "environment": env_name,
                            "ok": True,
                            "snapshot": snapshot,
                            "capability": capability,
                        }
                    )
                except Exception as exc:
                    source_endpoint = (
                        self._account_endpoint(family_name, env_name)
                        if family_name == "margin"
                        else self._public_exchange_endpoint(family_name, env_name)
                    )
                    snapshot = self.db.save_failed_snapshot(
                        family=family_name,
                        environment=env_name,
                        source_endpoint=source_endpoint,
                        error_message=str(exc),
                        policy_hash=str(self.policy_source().get("policy_hash") or ""),
                    )
                    capability = self._build_capability_snapshot(family_name, env_name, catalog_success=False)
                    results.append(
                        {
                            "family": family_name,
                            "environment": env_name,
                            "ok": False,
                            "snapshot": snapshot,
                            "capability": capability,
                            "error": str(exc),
                        }
                    )
        return {
            "ok": all(_bool(row.get("ok")) for row in results) if results else True,
            "startup": startup,
            "results": results,
            "policy_source": self.policy_source(),
        }

    def sync_on_startup(self, *, force: bool = False) -> dict[str, Any]:
        policy_map = self.policy()
        sync_cfg = policy_map["sync"]
        if not bool(sync_cfg["startup_enabled"]):
            return {"ok": True, "startup": True, "skipped": True, "reason": "startup_disabled_by_policy"}
        if not force and ("pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST")):
            return {"ok": True, "startup": True, "skipped": True, "reason": "pytest_harness"}
        return self.sync(startup=True)

    def live_parity_matrix(self) -> dict[str, dict[str, Any]]:
        policy_map = self.policy()
        matrix: dict[str, dict[str, Any]] = {}
        for family in FAMILIES:
            matrix[family] = {}
            for environment in ENVIRONMENTS:
                supported = self._family_environment_supported(family, environment)
                latest_success = self.db.latest_snapshot(family, environment, success_only=True)
                latest_any = self.db.latest_snapshot(family, environment, success_only=False)
                capability = self.db.latest_capability_snapshot(family, environment)
                freshness = _freshness_payload(
                    latest_success.get("fetched_at") if isinstance(latest_success, dict) else None,
                    policy_map,
                )
                diff_severity = str((latest_success or {}).get("diff_severity") or "OK")
                catalog_ready = bool(latest_success and _bool(latest_success.get("success")))
                snapshot_fresh = freshness["status"] == "fresh"
                policy_loaded = bool(self.policy_source().get("valid"))
                capabilities_known = capability is not None
                diff_blocked = diff_severity == "BLOCK"
                live_ready = bool(
                    supported
                    and catalog_ready
                    and snapshot_fresh
                    and policy_loaded
                    and capabilities_known
                    and not diff_blocked
                )
                matrix[family][environment] = {
                    "supported": supported,
                    "catalog_ready": catalog_ready,
                    "snapshot_fresh": snapshot_fresh,
                    "policy_loaded": policy_loaded,
                    "capabilities_known": capabilities_known,
                    "live_parity_base_ready": live_ready,
                    "diff_severity": diff_severity,
                    "freshness": freshness,
                    "last_snapshot_at": (latest_any or {}).get("fetched_at"),
                    "snapshot_id": (latest_any or {}).get("snapshot_id"),
                }
        return matrix

    def capabilities_summary(self) -> dict[str, Any]:
        families_payload: dict[str, Any] = {}
        policy_map = self.policy()
        for family in FAMILIES:
            live_cap = self.db.latest_capability_snapshot(family, "live")
            testnet_cap = self.db.latest_capability_snapshot(family, "testnet")
            families_payload[family] = {
                "live": live_cap
                or {
                    "family": family,
                    "environment": "live",
                    "can_read_market_data": False,
                    "can_trade": False,
                    "can_margin": False,
                    "can_user_data": False,
                    "can_testnet": False,
                    "capability_source": "missing",
                    "notes": {},
                    "fetched_at": None,
                },
                "testnet": testnet_cap
                or {
                    "family": family,
                    "environment": "testnet",
                    "can_read_market_data": False,
                    "can_trade": False,
                    "can_margin": False,
                    "can_user_data": False,
                    "can_testnet": False,
                    "capability_source": "missing",
                    "notes": {},
                    "fetched_at": None,
                },
                "can_trade": bool(_bool((live_cap or {}).get("can_trade")) or _bool((testnet_cap or {}).get("can_trade"))),
                "can_testnet": bool(
                    self._family_environment_supported(family, "testnet")
                    and (
                        _bool((testnet_cap or {}).get("can_trade"))
                        or _bool((testnet_cap or {}).get("can_read_market_data"))
                        or _bool((testnet_cap or {}).get("can_testnet"))
                    )
                ),
                "can_user_data": bool(_bool((live_cap or {}).get("can_user_data")) or _bool((testnet_cap or {}).get("can_user_data"))),
                "capability_freshness": {
                    "live": _freshness_payload((live_cap or {}).get("fetched_at"), policy_map),
                    "testnet": _freshness_payload((testnet_cap or {}).get("fetched_at"), policy_map),
                },
                "source": sorted(
                    {
                        str((live_cap or {}).get("capability_source") or "").strip(),
                        str((testnet_cap or {}).get("capability_source") or "").strip(),
                    }
                    - {""}
                ),
            }
        return {
            "venue": VENUE_BINANCE,
            "families": families_payload,
            "policy_source": self.policy_source(),
        }

    def registry_summary(self) -> dict[str, Any]:
        rows = self.db.registry_rows(active_only=True)
        by_family = {family: 0 for family in FAMILIES}
        live_counts = {family: 0 for family in FAMILIES}
        paper_counts = {family: 0 for family in FAMILIES}
        testnet_counts = {family: 0 for family in FAMILIES}
        for row in rows:
            family = str(row.get("family"))
            by_family[family] = by_family.get(family, 0) + 1
            if _bool(row.get("live_eligible")):
                live_counts[family] = live_counts.get(family, 0) + 1
            if _bool(row.get("paper_eligible")):
                paper_counts[family] = paper_counts.get(family, 0) + 1
            if _bool(row.get("testnet_eligible")):
                testnet_counts[family] = testnet_counts.get(family, 0) + 1

        environment_counts = {env: 0 for env in ENVIRONMENTS}
        last_snapshot_at: dict[str, dict[str, str | None]] = {}
        freshness_status: dict[str, dict[str, Any]] = {}
        for family in FAMILIES:
            last_snapshot_at[family] = {}
            freshness_status[family] = {}
            for env in ENVIRONMENTS:
                latest = self.db.latest_snapshot(family, env, success_only=False)
                latest_success = self.db.latest_snapshot(family, env, success_only=True)
                if latest and _bool(latest.get("success")):
                    environment_counts[env] += int(latest.get("symbol_count") or 0)
                last_snapshot_at[family][env] = (latest or {}).get("fetched_at")
                freshness_status[family][env] = _freshness_payload((latest_success or {}).get("fetched_at"), self.policy())

        live_parity = self.live_parity_matrix()
        overall_freshness = "fresh"
        for family_payload in freshness_status.values():
            for env_payload in family_payload.values():
                status = str(env_payload.get("status") or "missing")
                if status == "block":
                    overall_freshness = "block"
                elif overall_freshness != "block" and status in {"warn", "missing"}:
                    overall_freshness = "warn"

        return {
            "venue": VENUE_BINANCE,
            "total_instruments": len(rows),
            "by_family": by_family,
            "by_environment": environment_counts,
            "live_eligible_counts": live_counts,
            "paper_eligible_counts": paper_counts,
            "testnet_eligible_counts": testnet_counts,
            "last_snapshot_at": last_snapshot_at,
            "freshness_status": {
                "overall": overall_freshness,
                "by_family_environment": freshness_status,
            },
            "live_parity_base_ready": live_parity,
            "policy_source": self.policy_source(),
        }

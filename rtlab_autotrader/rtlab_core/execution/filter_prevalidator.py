from __future__ import annotations

import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any


ALGO_ORDER_TYPES = {
    "STOP",
    "STOP_MARKET",
    "STOP_LOSS",
    "STOP_LOSS_LIMIT",
    "TAKE_PROFIT",
    "TAKE_PROFIT_MARKET",
    "TAKE_PROFIT_LIMIT",
    "TRAILING_STOP_MARKET",
}


def _normalize_family(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"spot", "margin", "usdm_futures", "coinm_futures"} else ""


def _normalize_environment(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"live", "testnet", "paper", "shadow"} else "paper"


def _canonical_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _to_decimal(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _parse_iso(ts: Any) -> datetime | None:
    text = str(ts or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _price_alignment_base(family: str, minimum: Decimal | None) -> Decimal:
    if _normalize_family(family) in {"usdm_futures", "coinm_futures"} and minimum is not None:
        return minimum
    return Decimal("0")


def _qty_alignment_base(family: str, minimum: Decimal | None) -> Decimal:
    if _normalize_family(family) in {"usdm_futures", "coinm_futures"} and minimum is not None:
        return minimum
    return Decimal("0")


def _align_down(value: Decimal, step: Decimal | None, *, base: Decimal | None = None) -> Decimal:
    if step is None or step <= 0:
        return value
    anchor = base if base is not None else Decimal("0")
    if value < anchor:
        return value
    units = ((value - anchor) / step).to_integral_value(rounding=ROUND_DOWN)
    return anchor + (units * step)


def _is_aligned(value: Decimal, step: Decimal | None, *, base: Decimal | None = None) -> bool:
    if step is None or step <= 0:
        return True
    anchor = base if base is not None else Decimal("0")
    if value < anchor:
        return False
    return _align_down(value, step, base=anchor) == value


def _market_family(value: str) -> str:
    family = _normalize_family(value)
    if family in {"spot", "margin"}:
        return "spot"
    if family == "usdm_futures":
        return "um_futures"
    if family == "coinm_futures":
        return "coinm_futures"
    return family


def _execution_connector(value: str) -> str:
    family = _normalize_family(value)
    if family in {"spot", "margin"}:
        return "binance_spot"
    if family == "usdm_futures":
        return "binance_um_futures"
    if family == "coinm_futures":
        return "binance_coinm_futures"
    return ""


def _account_scope(value: str) -> str:
    family = _normalize_family(value)
    if family in {"spot", "margin"}:
        return "spot_wallet"
    if family in {"usdm_futures", "coinm_futures"}:
        return "futures_wallet"
    return ""


def _filter_source(value: str) -> str:
    family = _normalize_family(value)
    if family in {"spot", "margin"}:
        return "spot_exchange_info"
    if family == "usdm_futures":
        return "um_futures_exchange_info"
    if family == "coinm_futures":
        return "coinm_futures_exchange_info"
    return ""


def _validation_scope(mode: Any) -> str:
    text = str(mode or "").strip().lower()
    if text == "live":
        return "live_submit"
    if text == "testnet":
        return "exchange_test"
    return "client_precheck"


def _policy_action_blocks(policy: dict[str, Any], key: str) -> bool:
    return str(policy.get(key) or "").strip().lower() == "block"


def _percent_filter_warning_codes(filter_summary: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if isinstance(filter_summary.get("percent_price"), dict):
        warnings.append("percent_price_requires_exchange_reference")
    if isinstance(filter_summary.get("percent_price_by_side"), dict):
        warnings.append("percent_price_by_side_requires_exchange_reference")
    if isinstance(filter_summary.get("trailing_delta"), dict):
        warnings.append("trailing_delta_requires_conditional_order_support")
    return warnings


def _normalized_values_payload(
    *,
    quantity: Decimal | None,
    quote_quantity: Decimal | None,
    limit_price: Decimal | None,
    stop_price: Decimal | None,
    requested_notional: Decimal | None,
) -> dict[str, Any]:
    return {
        "quantity": _to_float(quantity),
        "quote_quantity": _to_float(quote_quantity),
        "limit_price": _to_float(limit_price),
        "stop_price": _to_float(stop_price),
        "requested_notional": _to_float(requested_notional),
    }


def evaluate_prevalidator(
    *,
    family: str,
    environment: str,
    mode: str,
    symbol: str,
    side: str,
    order_type: str,
    request: dict[str, Any],
    instrument: dict[str, Any] | None,
    filter_summary: dict[str, Any] | None,
    snapshot_fetched_at: str | None,
    filter_policy: dict[str, Any],
    quote_reference: dict[str, Any] | None,
    open_symbol_orders_count: int,
) -> dict[str, Any]:
    normalized_family = _normalize_family(family)
    normalized_environment = _normalize_environment(environment)
    normalized_symbol = _canonical_symbol(symbol or request.get("symbol"))
    normalized_side = str(side or request.get("side") or "").upper()
    normalized_order_type = str(order_type or request.get("order_type") or "").upper()
    active_filters = copy.deepcopy(filter_summary if isinstance(filter_summary, dict) else {})
    instrument_row = copy.deepcopy(instrument if isinstance(instrument, dict) else {})
    quote = quote_reference if isinstance(quote_reference, dict) else {}

    blockers: list[str] = []
    warnings: list[str] = []

    requested_quantity = _to_decimal(request.get("quantity"))
    requested_quote_quantity = _to_decimal(request.get("quote_quantity"))
    requested_price = _to_decimal(request.get("price"))
    requested_stop_price = _to_decimal(request.get("stopPrice") if request.get("stopPrice") is not None else request.get("stop_price"))

    price_filter = active_filters.get("price_filter") if isinstance(active_filters.get("price_filter"), dict) else {}
    lot_size = active_filters.get("lot_size") if isinstance(active_filters.get("lot_size"), dict) else {}
    market_lot_size = active_filters.get("market_lot_size") if isinstance(active_filters.get("market_lot_size"), dict) else {}
    min_notional = active_filters.get("min_notional") if isinstance(active_filters.get("min_notional"), dict) else {}
    notional = active_filters.get("notional") if isinstance(active_filters.get("notional"), dict) else {}
    max_num_orders = active_filters.get("max_num_orders") if isinstance(active_filters.get("max_num_orders"), dict) else {}
    max_num_algo_orders = active_filters.get("max_num_algo_orders") if isinstance(active_filters.get("max_num_algo_orders"), dict) else {}

    snapshot_dt = _parse_iso(snapshot_fetched_at)
    snapshot_age_ms = None if snapshot_dt is None else max(0, int((datetime.now(timezone.utc) - snapshot_dt).total_seconds() * 1000))
    max_age_ms = max(0, int(_safe_float(filter_policy.get("max_age_ms"), 300000.0)))

    expected_filter_source = _filter_source(normalized_family)
    catalog_source = str(instrument_row.get("catalog_source") or "").strip()
    source_mismatch = False
    if normalized_family == "spot" and catalog_source and "spot" not in catalog_source.lower():
        source_mismatch = True
    elif normalized_family == "usdm_futures" and catalog_source and "usdm" not in catalog_source.lower():
        source_mismatch = True

    if snapshot_dt is None and _policy_action_blocks(filter_policy, "missing_exchange_info"):
        blockers.append("missing_exchange_info")
    elif snapshot_age_ms is not None and max_age_ms > 0 and snapshot_age_ms > max_age_ms:
        blockers.append("exchange_filters_stale")

    if not active_filters and _policy_action_blocks(filter_policy, "missing_symbol_filters"):
        blockers.append("missing_symbol_filters")

    if source_mismatch and _policy_action_blocks(filter_policy, "filter_source_mismatch"):
        blockers.append("filter_source_mismatch")

    if not normalized_family:
        blockers.append("unsupported_family_filter_combo")

    price_min = _to_decimal(price_filter.get("min_price"))
    price_max = _to_decimal(price_filter.get("max_price"))
    tick_size = _to_decimal(price_filter.get("tick_size"))
    qty_filter = market_lot_size if normalized_order_type == "MARKET" and isinstance(market_lot_size, dict) and market_lot_size else lot_size
    qty_min = _to_decimal((qty_filter or {}).get("min_qty"))
    qty_max = _to_decimal((qty_filter or {}).get("max_qty"))
    step_size = _to_decimal((qty_filter or {}).get("step_size"))

    normalized_quantity = requested_quantity
    normalized_price = requested_price
    normalized_stop_price = requested_stop_price

    skip_qty_alignment = normalized_family == "spot" and normalized_order_type == "MARKET" and requested_quantity is None and requested_quote_quantity is not None
    if skip_qty_alignment:
        warnings.append("spot_quote_order_qty_path")

    if requested_price is not None and tick_size is not None and tick_size > 0:
        normalized_price = _align_down(
            requested_price,
            tick_size,
            base=_price_alignment_base(normalized_family, price_min),
        )
        if normalized_price != requested_price and _policy_action_blocks(filter_policy, "invalid_tick_alignment"):
            blockers.append("invalid_tick_alignment")
    if requested_stop_price is not None and tick_size is not None and tick_size > 0:
        normalized_stop_price = _align_down(
            requested_stop_price,
            tick_size,
            base=_price_alignment_base(normalized_family, price_min),
        )
        if normalized_stop_price != requested_stop_price and _policy_action_blocks(filter_policy, "invalid_tick_alignment"):
            blockers.append("invalid_stop_tick_alignment")

    if requested_quantity is not None and not skip_qty_alignment and step_size is not None and step_size > 0:
        normalized_quantity = _align_down(
            requested_quantity,
            step_size,
            base=_qty_alignment_base(normalized_family, qty_min),
        )
        if normalized_quantity != requested_quantity and _policy_action_blocks(filter_policy, "invalid_step_alignment"):
            blockers.append("invalid_step_alignment")

    if normalized_order_type == "LIMIT" and requested_price is None:
        blockers.append("limit_price_required")

    if normalized_order_type == "LIMIT" and requested_quantity is None and requested_quote_quantity is None:
        blockers.append("quantity_required_for_limit")

    if normalized_family in {"usdm_futures", "coinm_futures"} and requested_quantity is None:
        blockers.append("quantity_required_for_futures")

    if normalized_quantity is None and requested_quote_quantity is None:
        blockers.append("quantity_or_quote_quantity_required")

    price_candidates = [
        normalized_price,
        _to_decimal(quote.get("mark_price")),
        _to_decimal(quote.get("best_quote")),
        _to_decimal(quote.get("mid")),
        _to_decimal(quote.get("ask") if normalized_side == "BUY" else quote.get("bid")),
    ]
    reference_price = next((item for item in price_candidates if item is not None and item > 0), None)

    if requested_price is not None:
        if price_min is not None and price_min > 0 and requested_price < price_min:
            blockers.append("price_below_min_price")
        if price_max is not None and price_max > 0 and requested_price > price_max:
            blockers.append("price_above_max_price")
        if tick_size is not None and tick_size > 0 and not _is_aligned(
            requested_price,
            tick_size,
            base=_price_alignment_base(normalized_family, price_min),
        ) and _policy_action_blocks(filter_policy, "invalid_tick_alignment"):
            if "invalid_tick_alignment" not in blockers:
                blockers.append("invalid_tick_alignment")

    if requested_stop_price is not None:
        if price_min is not None and price_min > 0 and requested_stop_price < price_min:
            blockers.append("stop_price_below_min_price")
        if price_max is not None and price_max > 0 and requested_stop_price > price_max:
            blockers.append("stop_price_above_max_price")
        if tick_size is not None and tick_size > 0 and not _is_aligned(
            requested_stop_price,
            tick_size,
            base=_price_alignment_base(normalized_family, price_min),
        ) and _policy_action_blocks(filter_policy, "invalid_tick_alignment"):
            if "invalid_stop_tick_alignment" not in blockers:
                blockers.append("invalid_stop_tick_alignment")

    if requested_quantity is not None and not skip_qty_alignment:
        if qty_min is not None and qty_min > 0 and requested_quantity < qty_min:
            blockers.append("quantity_below_min_qty")
        if qty_max is not None and qty_max > 0 and requested_quantity > qty_max:
            blockers.append("quantity_above_max_qty")
        if step_size is not None and step_size > 0 and not _is_aligned(
            requested_quantity,
            step_size,
            base=_qty_alignment_base(normalized_family, qty_min),
        ) and _policy_action_blocks(filter_policy, "invalid_step_alignment"):
            if "invalid_step_alignment" not in blockers:
                blockers.append("invalid_step_alignment")

    notional_filter = notional or min_notional
    min_notional_value = _to_decimal(notional_filter.get("min_notional")) if isinstance(notional_filter, dict) else None
    max_notional_value = _to_decimal(notional_filter.get("max_notional")) if isinstance(notional_filter, dict) else None
    apply_min_market = _bool(notional_filter.get("apply_to_market")) or _bool(notional_filter.get("apply_min_to_market")) if isinstance(notional_filter, dict) else False
    apply_max_market = _bool(notional_filter.get("apply_max_to_market")) if isinstance(notional_filter, dict) else False
    if isinstance(notional_filter, dict) and normalized_family in {"usdm_futures", "coinm_futures"} and "apply_to_market" not in notional_filter and "apply_min_to_market" not in notional_filter:
        apply_min_market = True

    requested_notional = _to_decimal(request.get("requested_notional"))
    computed_notional = requested_notional
    if computed_notional is None or computed_notional <= 0:
        if requested_quote_quantity is not None:
            computed_notional = requested_quote_quantity
        elif normalized_quantity is not None and reference_price is not None:
            computed_notional = normalized_quantity * reference_price

    if normalized_order_type == "MARKET" and normalized_family == "spot" and requested_quote_quantity is not None:
        computed_notional = requested_quote_quantity

    if normalized_order_type == "MARKET" and computed_notional is None and (
        (min_notional_value is not None and apply_min_market)
        or (max_notional_value is not None and apply_max_market)
    ):
        blockers.append("missing_market_reference_price")

    if min_notional_value is not None:
        applies = normalized_order_type != "MARKET" or apply_min_market or normalized_family in {"usdm_futures", "coinm_futures"}
        if applies and computed_notional is not None and computed_notional < min_notional_value and _policy_action_blocks(filter_policy, "invalid_min_notional"):
            blockers.append("invalid_min_notional")
    if max_notional_value is not None:
        applies = normalized_order_type != "MARKET" or apply_max_market
        if applies and computed_notional is not None and computed_notional > max_notional_value:
            blockers.append("invalid_max_notional")

    symbol_order_limit = int(_safe_float(max_num_orders.get("limit"), 0.0)) if isinstance(max_num_orders, dict) else 0
    if symbol_order_limit > 0 and open_symbol_orders_count >= symbol_order_limit:
        blockers.append("exchange_symbol_max_num_orders_exceeded")

    if normalized_order_type in ALGO_ORDER_TYPES and isinstance(max_num_algo_orders, dict):
        warnings.append("max_num_algo_orders_requires_algo_open_order_counter")

    warnings.extend(_percent_filter_warning_codes(active_filters))

    normalized_payload = _normalized_values_payload(
        quantity=normalized_quantity,
        quote_quantity=requested_quote_quantity,
        limit_price=normalized_price,
        stop_price=normalized_stop_price,
        requested_notional=computed_notional,
    )
    requested_payload = _normalized_values_payload(
        quantity=requested_quantity,
        quote_quantity=requested_quote_quantity,
        limit_price=requested_price,
        stop_price=requested_stop_price,
        requested_notional=requested_notional or computed_notional,
    )
    changed_fields = sorted(
        key
        for key in ("quantity", "limit_price", "stop_price")
        if requested_payload.get(key) is not None and normalized_payload.get(key) is not None and requested_payload.get(key) != normalized_payload.get(key)
    )

    status = "BLOCK" if blockers else "WARN" if warnings else "PASS"
    return {
        "status": status,
        "pass": not blockers,
        "warn": bool(warnings) and not blockers,
        "block": bool(blockers),
        "reason_codes": list(dict.fromkeys([*blockers, *warnings])),
        "blocking_reasons": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "changed_fields": changed_fields,
        "requested_values": requested_payload,
        "normalized_values": normalized_payload,
        "market_family": _market_family(normalized_family),
        "execution_connector": _execution_connector(normalized_family),
        "account_scope": _account_scope(normalized_family),
        "filter_source": expected_filter_source,
        "validation_scope": _validation_scope(mode),
        "filter_snapshot_source": {
            "catalog_source": catalog_source,
            "snapshot_id": instrument_row.get("last_snapshot_id"),
            "snapshot_timestamp": snapshot_fetched_at,
            "snapshot_age_ms": snapshot_age_ms,
            "max_age_ms": max_age_ms,
            "source_kind": expected_filter_source,
        },
        "applied_filters": copy.deepcopy(active_filters),
        "symbol": normalized_symbol,
        "family": normalized_family,
        "environment": normalized_environment,
        "side": normalized_side,
        "order_type": normalized_order_type,
        "open_symbol_orders_count": int(open_symbol_orders_count),
    }


def describe_filter_rules(
    *,
    family: str,
    environment: str,
    symbol: str,
    instrument: dict[str, Any] | None,
    snapshot_fetched_at: str | None,
    filter_policy: dict[str, Any],
) -> dict[str, Any]:
    normalized_family = _normalize_family(family)
    instrument_row = copy.deepcopy(instrument if isinstance(instrument, dict) else {})
    filter_summary = instrument_row.get("filter_summary") if isinstance(instrument_row.get("filter_summary"), dict) else {}
    snapshot_dt = _parse_iso(snapshot_fetched_at)
    snapshot_age_ms = None if snapshot_dt is None else max(0, int((datetime.now(timezone.utc) - snapshot_dt).total_seconds() * 1000))
    max_age_ms = max(0, int(_safe_float(filter_policy.get("max_age_ms"), 300000.0)))
    freshness_status = "missing" if snapshot_dt is None else "block" if snapshot_age_ms is not None and snapshot_age_ms > max_age_ms else "fresh"
    return {
        "family": normalized_family,
        "market_family": _market_family(normalized_family),
        "execution_connector": _execution_connector(normalized_family),
        "account_scope": _account_scope(normalized_family),
        "filter_source": _filter_source(normalized_family),
        "symbol": _canonical_symbol(symbol),
        "environment": _normalize_environment(environment),
        "catalog_source": instrument_row.get("catalog_source"),
        "snapshot_id": instrument_row.get("last_snapshot_id"),
        "snapshot_timestamp": snapshot_fetched_at,
        "snapshot_age_ms": snapshot_age_ms,
        "freshness_status": freshness_status,
        "max_age_ms": max_age_ms,
        "filter_summary": copy.deepcopy(filter_summary),
        "policy": copy.deepcopy(filter_policy),
        "warnings": _percent_filter_warning_codes(filter_summary),
    }

from __future__ import annotations

import hashlib
from typing import Any


LIVE_FILL_SOURCE_TYPES = {
    "WS_EXECUTION_REPORT",
    "REST_MYTRADES",
    "REST_CREATE_FULL",
    "REST_QUERY_ORDER",
    "RECOVERY",
    "PAPER_LOCAL_FILL",
}

LIVE_FILL_RECONCILIATION_STATUSES = {
    "PENDING",
    "WS_ONLY",
    "REST_BACKFILL",
    "REST_CREATE_ONLY",
    "RECONCILED",
    "DISCREPANCY",
    "LOCAL_SIMULATED",
}


def _clean_text(value: Any, *, upper: bool = False) -> str:
    text = str(value or "").strip()
    return text.upper() if upper else text


def _missing_identifier(value: Any) -> bool:
    text = _clean_text(value)
    return text in {"", "-1", "NONE", "NULL"}


def normalize_fill_source_type(value: Any) -> str:
    text = _clean_text(value, upper=True)
    aliases = {
        "EXECUTIONREPORT_STREAM": "WS_EXECUTION_REPORT",
        "WS_EXECUTION_REPORT": "WS_EXECUTION_REPORT",
        "ORDER_TRADE_UPDATE_STREAM": "WS_EXECUTION_REPORT",
        "MY_TRADES_REST": "REST_MYTRADES",
        "REST_MYTRADES": "REST_MYTRADES",
        "CREATE_FULL_REST": "REST_CREATE_FULL",
        "REST_CREATE_FULL": "REST_CREATE_FULL",
        "QUERY_ORDER_REST": "REST_QUERY_ORDER",
        "REST_QUERY_ORDER": "REST_QUERY_ORDER",
        "RECOVERY": "RECOVERY",
        "PAPER_LOCAL_FILL": "PAPER_LOCAL_FILL",
    }
    return aliases.get(text, text or "UNKNOWN")


def build_live_fill_dedup_key(
    *,
    symbol: Any,
    exchange_order_id: Any,
    trade_id: Any,
    execution_id: Any,
    client_order_id: Any,
    execution_type: Any,
    transaction_time: Any,
    last_executed_qty: Any,
    last_executed_price: Any,
    cumulative_filled_qty_after: Any,
) -> str:
    symbol_text = _clean_text(symbol, upper=True) or "UNKNOWN"
    exchange_order_text = _clean_text(exchange_order_id) or "UNKNOWN"
    if not _missing_identifier(trade_id):
        return f"fill_trade:{symbol_text}:{exchange_order_text}:{_clean_text(trade_id)}"
    if not _missing_identifier(execution_id):
        return f"fill_exec:{symbol_text}:{exchange_order_text}:{_clean_text(execution_id)}"
    return ":".join(
        [
            "fill_fallback",
            symbol_text,
            _clean_text(client_order_id) or "UNKNOWN",
            _clean_text(execution_type, upper=True) or "UNKNOWN",
            _clean_text(transaction_time) or "0",
            _clean_text(last_executed_qty) or "0",
            _clean_text(last_executed_price) or "0",
            _clean_text(cumulative_filled_qty_after) or "0",
        ]
    )


def build_live_fill_id(dedup_key: str) -> str:
    digest = hashlib.sha256(str(dedup_key).encode("utf-8")).hexdigest()[:16].upper()
    return f"FILL-{digest}"


def fill_reconciliation_status(
    *,
    source_types: set[str],
    has_discrepancy: bool,
) -> str:
    normalized = {normalize_fill_source_type(item) for item in source_types if str(item or "").strip()}
    if has_discrepancy:
        return "DISCREPANCY"
    if normalized == {"PAPER_LOCAL_FILL"}:
        return "LOCAL_SIMULATED"
    if "WS_EXECUTION_REPORT" in normalized and "REST_MYTRADES" in normalized:
        return "RECONCILED"
    if normalized == {"REST_MYTRADES"}:
        return "REST_BACKFILL"
    if normalized == {"REST_CREATE_FULL"}:
        return "REST_CREATE_ONLY"
    if normalized == {"WS_EXECUTION_REPORT"}:
        return "WS_ONLY"
    if normalized:
        return "PENDING"
    return "PENDING"

from __future__ import annotations

from typing import Any


LOCAL_ORDER_STATES = {
    "INTENT_CREATED",
    "PRECHECK_PASSED",
    "SUBMITTING",
    "UNKNOWN_PENDING_RECONCILIATION",
    "ACKED",
    "WORKING",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_REQUESTED",
    "CANCELED",
    "REJECTED",
    "EXPIRED",
    "EXPIRED_STP",
    "RECOVERED_OPEN",
    "RECOVERED_TERMINAL",
    "MANUAL_REVIEW_REQUIRED",
}

TERMINAL_LOCAL_ORDER_STATES = {
    "FILLED",
    "CANCELED",
    "REJECTED",
    "EXPIRED",
    "EXPIRED_STP",
    "RECOVERED_TERMINAL",
}

AMBIGUOUS_LOCAL_ORDER_STATES = {
    "UNKNOWN_PENDING_RECONCILIATION",
    "MANUAL_REVIEW_REQUIRED",
}

BLOCKING_LOCAL_ORDER_STATES = {
    "SUBMITTING",
    "UNKNOWN_PENDING_RECONCILIATION",
    "CANCEL_REQUESTED",
    "MANUAL_REVIEW_REQUIRED",
}

OPENISH_EXCHANGE_ORDER_STATUSES = {
    "NEW",
    "PARTIALLY_FILLED",
    "PENDING_NEW",
}


def normalize_local_state(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in LOCAL_ORDER_STATES else "MANUAL_REVIEW_REQUIRED"


def is_terminal_local_state(value: Any) -> bool:
    return normalize_local_state(value) in TERMINAL_LOCAL_ORDER_STATES


def is_ambiguous_local_state(value: Any) -> bool:
    return normalize_local_state(value) in AMBIGUOUS_LOCAL_ORDER_STATES


def blocks_new_submits(value: Any) -> bool:
    return normalize_local_state(value) in BLOCKING_LOCAL_ORDER_STATES


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def map_exchange_event_to_local_state(
    *,
    current_local_state: Any,
    source_type: str,
    exchange_order_status: Any,
    execution_type: Any,
    cumulative_filled_qty: Any,
    orig_qty: Any,
) -> str:
    current = normalize_local_state(current_local_state) if str(current_local_state or "").strip() else ""
    source = str(source_type or "").strip().upper()
    status = str(exchange_order_status or "").strip().upper()
    exec_type = str(execution_type or "").strip().upper()
    filled = max(0.0, _safe_float(cumulative_filled_qty, 0.0))
    requested = max(0.0, _safe_float(orig_qty, 0.0))

    if exec_type == "TRADE_PREVENTION" or status == "EXPIRED_IN_MATCH":
        return "EXPIRED_STP"
    if exec_type == "REJECTED" or status == "REJECTED":
        return "REJECTED"
    if exec_type == "CANCELED" or status == "CANCELED":
        return "CANCELED"
    if exec_type == "EXPIRED" or status == "EXPIRED":
        return "EXPIRED"

    if exec_type == "TRADE" or status in {"PARTIALLY_FILLED", "FILLED"}:
        if requested > 0.0 and filled + 1e-12 >= requested:
            return "FILLED"
        return "PARTIALLY_FILLED"

    if status == "PENDING_NEW":
        return "ACKED"

    if status in OPENISH_EXCHANGE_ORDER_STATUSES or exec_type == "NEW":
        if source in {"REST_OPEN_ORDERS_SNAPSHOT", "REST_QUERY_ORDER", "RECOVERY"}:
            return "RECOVERED_OPEN" if current in AMBIGUOUS_LOCAL_ORDER_STATES else "WORKING"
        if source == "REST_CREATE_RESPONSE":
            return "ACKED"
        if current in {"SUBMITTING", "UNKNOWN_PENDING_RECONCILIATION", "ACKED"}:
            return "WORKING"
        if current == "RECOVERED_OPEN":
            return "RECOVERED_OPEN"
        return "WORKING"

    if source in {"REST_QUERY_ORDER", "REST_OPEN_ORDERS_SNAPSHOT", "RECOVERY"} and status in {
        "FILLED",
        "CANCELED",
        "REJECTED",
        "EXPIRED",
        "EXPIRED_IN_MATCH",
    }:
        return "RECOVERED_TERMINAL" if status != "EXPIRED_IN_MATCH" else "EXPIRED_STP"

    return "MANUAL_REVIEW_REQUIRED"


def execution_report_dedup_key(
    *,
    symbol: Any,
    exchange_order_id: Any,
    exchange_execution_id: Any,
    client_order_id: Any,
    execution_type: Any,
    exchange_order_status: Any,
    transaction_time: Any,
    cumulative_filled_qty: Any,
) -> str:
    symbol_text = str(symbol or "").strip().upper()
    order_text = str(exchange_order_id or "").strip()
    execution_text = str(exchange_execution_id or "").strip()
    if symbol_text and order_text and execution_text:
        return f"ws_exec:{symbol_text}:{order_text}:{execution_text}"
    return ":".join(
        [
            "ws_exec_fallback",
            symbol_text or "UNKNOWN",
            str(client_order_id or "").strip() or "UNKNOWN",
            str(execution_type or "").strip().upper() or "UNKNOWN",
            str(exchange_order_status or "").strip().upper() or "UNKNOWN",
            str(transaction_time or "").strip() or "0",
            str(cumulative_filled_qty or "").strip() or "0",
        ]
    )

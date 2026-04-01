from __future__ import annotations

from typing import Any


SAFETY_SCOPE_TYPES = {"GLOBAL", "BOT", "BOT_SYMBOL", "SYMBOL"}
SAFETY_EVENT_SEVERITIES = {"INFO", "WARN", "CRITICAL"}
SAFETY_BREAKER_STATES = {"CLOSED", "OPEN", "COOLDOWN", "MANUAL_LOCK"}
SAFETY_MANUAL_ACTION_TYPES = {
    "FREEZE_SYMBOL",
    "FREEZE_BOT",
    "FREEZE_GLOBAL",
    "UNFREEZE",
    "EMERGENCY_CANCEL_SYMBOL",
    "ACK_ALERT",
}
SAFETY_BREAKER_ACTIONS = {
    "WARN_ONLY",
    "BLOCK_NEW_SUBMITS",
    "FREEZE_SYMBOL",
    "FREEZE_BOT",
    "FREEZE_GLOBAL",
    "FORCE_RECONCILE",
    "EMERGENCY_CANCEL_SYMBOL",
    "REQUIRE_MANUAL_ACK",
}
SAFETY_TRIGGER_CODES = {
    "STREAM_HEALTH_DEGRADED",
    "STREAM_TERMINATED",
    "RECONCILIATION_DESYNC_BLOCKING",
    "RECONCILIATION_MANUAL_REVIEW_BLOCKING",
    "UNKNOWN_TIMEOUT_STUCK",
    "TOO_MANY_REQUESTS_PRESSURE",
    "HTTP_418_BAN_RISK",
    "TOO_MANY_OPEN_ORDERS",
    "REMOTE_OPEN_ORDER_WITHOUT_LOCAL_REPRESENTATION",
    "EXCESSIVE_CANCEL_FAILS",
    "EXCESSIVE_REJECTS",
    "STP_EXPIRED_CLUSTER",
    "PRESTART_GUARDRAIL_FAIL",
    "PREFLIGHT_EXPIRED_OR_FAIL",
    "SAFETY_POLICY_VIOLATION",
}


def _normalize_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_safety_scope_type(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in SAFETY_SCOPE_TYPES else "GLOBAL"


def normalize_safety_event_severity(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in SAFETY_EVENT_SEVERITIES else "WARN"


def normalize_safety_breaker_state(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in SAFETY_BREAKER_STATES else "CLOSED"


def normalize_safety_manual_action_type(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in SAFETY_MANUAL_ACTION_TYPES else "ACK_ALERT"


def normalize_safety_breaker_action(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in SAFETY_BREAKER_ACTIONS else "WARN_ONLY"


def normalize_safety_trigger_code(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in SAFETY_TRIGGER_CODES else "SAFETY_POLICY_VIOLATION"


def safety_severity_rank(value: Any) -> int:
    normalized = normalize_safety_event_severity(value)
    order = {"INFO": 0, "WARN": 1, "CRITICAL": 2}
    return order.get(normalized, 1)


def safety_breaker_blocks_live(state: Any, blocking: Any) -> bool:
    normalized = normalize_safety_breaker_state(state)
    if normalized == "MANUAL_LOCK":
        return True
    if normalized in {"OPEN", "COOLDOWN"}:
        return bool(blocking)
    return False


def safety_scope_matches(
    *,
    row_scope_type: Any,
    row_bot_id: Any,
    row_symbol: Any,
    bot_id: str | None = None,
    symbol: str | None = None,
) -> bool:
    scope_type = normalize_safety_scope_type(row_scope_type)
    normalized_bot = str(bot_id or "").strip()
    normalized_symbol = str(symbol or "").strip().upper()
    row_bot = str(row_bot_id or "").strip()
    row_symbol_norm = str(row_symbol or "").strip().upper()
    if scope_type == "GLOBAL":
        return True
    if scope_type == "BOT":
        return bool(normalized_bot) and normalized_bot == row_bot
    if scope_type == "SYMBOL":
        return bool(normalized_symbol) and normalized_symbol == row_symbol_norm
    if scope_type == "BOT_SYMBOL":
        return bool(normalized_bot and normalized_symbol) and normalized_bot == row_bot and normalized_symbol == row_symbol_norm
    return False

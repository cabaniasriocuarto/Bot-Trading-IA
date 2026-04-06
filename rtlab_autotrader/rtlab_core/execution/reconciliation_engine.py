from __future__ import annotations

from typing import Any


RECONCILIATION_CASE_STATUSES = {
    "CLEAN",
    "RESOLVED",
    "DESYNC",
    "MANUAL_REVIEW_REQUIRED",
    "FAILED",
}

RECONCILIATION_CASE_SEVERITIES = {
    "INFO",
    "WARN",
    "CRITICAL",
}

RECONCILIATION_TRIGGER_TYPES = {
    "STARTUP",
    "PERIODIC",
    "MANUAL",
    "UNKNOWN_TIMEOUT",
    "STREAM_GAP",
    "PRESTART_LIVE",
    "POST_TERMINAL_AUDIT",
}

RECONCILIATION_CASE_EVENT_SOURCES = {
    "LOCAL_STATE",
    "WS_EVENT",
    "REST_QUERY_ORDER",
    "REST_OPEN_ORDERS",
    "REST_MYTRADES",
    "RECOVERY",
    "POLICY",
    "MANUAL",
}

RECONCILIATION_SNAPSHOT_TYPES = {
    "LOCAL_ORDER",
    "REMOTE_ORDER",
    "OPEN_ORDERS",
    "TRADE_LIST",
    "LOCAL_FILLS",
    "POLICY_CONTEXT",
    "STREAM_HEALTH",
}

RECONCILIATION_DISCREPANCY_CODES = {
    "ORDER_MISSING_LOCALLY_BUT_REMOTE_OPEN",
    "ORDER_LOCAL_OPEN_BUT_REMOTE_MISSING",
    "ORDER_LOCAL_TERMINAL_BUT_REMOTE_OPEN",
    "ORDER_REMOTE_TERMINAL_BUT_LOCAL_OPEN",
    "FILLS_REMOTE_NOT_IN_LOCAL",
    "FILLS_LOCAL_NOT_CONFIRMED_REMOTE",
    "COMMISSION_MISMATCH",
    "CUM_QTY_MISMATCH",
    "CUM_QUOTE_MISMATCH",
    "CLIENT_ORDER_LINK_MISMATCH",
    "STREAM_GAP_WITH_PENDING_OPEN_ORDERS",
    "UNKNOWN_TIMEOUT_UNRESOLVED",
    "STP_PREVENTED_MATCH_NEEDS_RECLASSIFICATION",
    "DUPLICATE_LOCAL_EVENT_COLLISION",
    "SNAPSHOT_STALENESS_TOO_HIGH",
}

RECONCILIATION_BLOCKING_STATUSES = {
    "DESYNC",
    "MANUAL_REVIEW_REQUIRED",
    "FAILED",
}


def _clean_text(value: Any, *, upper: bool = True) -> str:
    text = str(value or "").strip()
    return text.upper() if upper else text


def normalize_reconciliation_case_status(value: Any) -> str:
    text = _clean_text(value)
    return text if text in RECONCILIATION_CASE_STATUSES else "FAILED"


def normalize_reconciliation_case_severity(value: Any) -> str:
    text = _clean_text(value)
    return text if text in RECONCILIATION_CASE_SEVERITIES else "WARN"


def normalize_reconciliation_trigger(value: Any) -> str:
    text = _clean_text(value)
    return text if text in RECONCILIATION_TRIGGER_TYPES else "MANUAL"


def normalize_reconciliation_case_event_source(value: Any) -> str:
    text = _clean_text(value)
    return text if text in RECONCILIATION_CASE_EVENT_SOURCES else "MANUAL"


def normalize_reconciliation_snapshot_type(value: Any) -> str:
    text = _clean_text(value)
    return text if text in RECONCILIATION_SNAPSHOT_TYPES else "LOCAL_ORDER"


def normalize_reconciliation_discrepancy_code(value: Any) -> str:
    text = _clean_text(value)
    return text if text in RECONCILIATION_DISCREPANCY_CODES else "UNKNOWN_TIMEOUT_UNRESOLVED"


def reconciliation_case_blocks_live(status: Any, blocking_bool: Any) -> bool:
    if bool(blocking_bool):
        return True
    return normalize_reconciliation_case_status(status) in RECONCILIATION_BLOCKING_STATUSES


def reconciliation_severity_rank(value: Any) -> int:
    severity = normalize_reconciliation_case_severity(value)
    if severity == "CRITICAL":
        return 3
    if severity == "WARN":
        return 2
    return 1


def discrepancy_payload(
    *,
    code: Any,
    severity: Any,
    entity_scope: str,
    local_value: Any,
    remote_value: Any,
    auto_resolvable_bool: bool,
    proposed_action: str,
    final_action: str,
) -> dict[str, Any]:
    return {
        "code": normalize_reconciliation_discrepancy_code(code),
        "severity": normalize_reconciliation_case_severity(severity),
        "entity_scope": str(entity_scope or "order"),
        "local_value": local_value,
        "remote_value": remote_value,
        "auto_resolvable_bool": bool(auto_resolvable_bool),
        "proposed_action": str(proposed_action or ""),
        "final_action": str(final_action or ""),
    }

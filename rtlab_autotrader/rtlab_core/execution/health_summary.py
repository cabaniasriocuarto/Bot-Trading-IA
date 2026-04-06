from __future__ import annotations

from typing import Any


HEALTH_STATES = {"HEALTHY", "DEGRADED", "BLOCKED", "MANUAL_REVIEW_REQUIRED"}
HEALTH_SEVERITIES = {"INFO", "WARN", "CRITICAL"}
HEALTH_SCOPE_TYPES = {"GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"}

HEALTH_REASON_CODES = {
    "PREFLIGHT_FAIL",
    "PREFLIGHT_EXPIRED",
    "PREFLIGHT_STALE",
    "RECONCILIATION_DESYNC",
    "RECONCILIATION_MANUAL_REVIEW",
    "BREAKER_OPEN",
    "MANUAL_LOCK_ACTIVE",
    "STREAM_HEALTH_DEGRADED",
    "STREAM_TERMINATED",
    "UNKNOWN_TIMEOUT_STUCK",
    "RATE_LIMIT_PRESSURE",
    "HTTP_418_BAN_RISK",
    "OPEN_ORDER_PRESSURE",
    "SNAPSHOT_STALE",
    "EMERGENCY_ACTION_ACTIVE",
    "FREEZE_SYMBOL_ACTIVE",
    "FREEZE_BOT_ACTIVE",
    "FREEZE_GLOBAL_ACTIVE",
    "SAFETY_POLICY_VIOLATION",
}

HEALTH_REASON_PRIORITY = {
    "PREFLIGHT_FAIL": "P1",
    "PREFLIGHT_EXPIRED": "P1",
    "RECONCILIATION_DESYNC": "P1",
    "RECONCILIATION_MANUAL_REVIEW": "P1",
    "BREAKER_OPEN": "P1",
    "MANUAL_LOCK_ACTIVE": "P1",
    "STREAM_TERMINATED": "P1",
    "UNKNOWN_TIMEOUT_STUCK": "P1",
    "FREEZE_GLOBAL_ACTIVE": "P1",
    "RATE_LIMIT_PRESSURE": "P2",
    "HTTP_418_BAN_RISK": "P2",
    "OPEN_ORDER_PRESSURE": "P2",
    "STREAM_HEALTH_DEGRADED": "P2",
    "EMERGENCY_ACTION_ACTIVE": "P2",
    "FREEZE_SYMBOL_ACTIVE": "P2",
    "FREEZE_BOT_ACTIVE": "P2",
    "PREFLIGHT_STALE": "P3",
    "SNAPSHOT_STALE": "P3",
    "SAFETY_POLICY_VIOLATION": "P2",
}

HEALTH_REASON_PENALTIES = {
    "PREFLIGHT_STALE": 10,
    "STREAM_HEALTH_DEGRADED": 15,
    "RATE_LIMIT_PRESSURE": 15,
    "HTTP_418_BAN_RISK": 25,
    "OPEN_ORDER_PRESSURE": 10,
    "RECONCILIATION_DESYNC": 20,
    "RECONCILIATION_MANUAL_REVIEW": 20,
    "EMERGENCY_ACTION_ACTIVE": 15,
    "SNAPSHOT_STALE": 10,
    "FREEZE_SYMBOL_ACTIVE": 20,
    "FREEZE_BOT_ACTIVE": 20,
}

HARD_BLOCK_REASON_CODES = {
    "PREFLIGHT_FAIL",
    "PREFLIGHT_EXPIRED",
    "RECONCILIATION_DESYNC",
    "BREAKER_OPEN",
    "MANUAL_LOCK_ACTIVE",
    "STREAM_TERMINATED",
    "UNKNOWN_TIMEOUT_STUCK",
    "FREEZE_GLOBAL_ACTIVE",
}

MANUAL_REVIEW_REASON_CODES = {"RECONCILIATION_MANUAL_REVIEW"}


def _normalize_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_health_state(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in HEALTH_STATES else "DEGRADED"


def normalize_health_severity(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in HEALTH_SEVERITIES else "WARN"


def normalize_health_scope_type(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in HEALTH_SCOPE_TYPES else "GLOBAL"


def normalize_health_reason_code(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in HEALTH_REASON_CODES else "SAFETY_POLICY_VIOLATION"


def health_priority_rank(value: Any) -> int:
    priority = HEALTH_REASON_PRIORITY.get(normalize_health_reason_code(value), "P3")
    return {"P1": 0, "P2": 1, "P3": 2}.get(priority, 2)


def health_severity_rank(value: Any) -> int:
    severity = normalize_health_severity(value)
    return {"CRITICAL": 2, "WARN": 1, "INFO": 0}.get(severity, 1)


def health_scope_key(scope_type: Any, bot_id: Any = None, symbol: Any = None) -> str:
    scope_type_n = normalize_health_scope_type(scope_type)
    bot_id_n = str(bot_id or "").strip()
    symbol_n = str(symbol or "").strip().upper()
    if scope_type_n == "GLOBAL":
        return "GLOBAL"
    if scope_type_n == "BOT":
        return f"BOT:{bot_id_n}"
    if scope_type_n == "SYMBOL":
        return f"SYMBOL:{symbol_n}"
    return f"BOT_SYMBOL:{bot_id_n}:{symbol_n}"


def health_scope_matches(
    *,
    row_scope_type: Any,
    row_bot_id: Any,
    row_symbol: Any,
    bot_id: str | None = None,
    symbol: str | None = None,
) -> bool:
    scope_type = normalize_health_scope_type(row_scope_type)
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


def build_health_reason(
    *,
    reason_code: str,
    severity: str | None = None,
    blocking_bool: bool | None = None,
    scope_type: str = "GLOBAL",
    bot_id: str | None = None,
    symbol: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    code = normalize_health_reason_code(reason_code)
    priority = HEALTH_REASON_PRIORITY.get(code, "P3")
    severity_n = normalize_health_severity(
        severity
        or ("CRITICAL" if priority == "P1" else "WARN" if priority == "P2" else "INFO")
    )
    blocking = bool(blocking_bool) if blocking_bool is not None else code in HARD_BLOCK_REASON_CODES | MANUAL_REVIEW_REASON_CODES
    return {
        "reason_code": code,
        "priority": priority,
        "priority_rank": health_priority_rank(code),
        "severity": severity_n,
        "blocking_bool": blocking,
        "scope_type": normalize_health_scope_type(scope_type),
        "bot_id": str(bot_id or "").strip() or None,
        "symbol": str(symbol or "").strip().upper() or None,
        "evidence": evidence if isinstance(evidence, dict) else {},
        "penalty": int(HEALTH_REASON_PENALTIES.get(code, 0)),
    }


def sort_health_reasons(reasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [dict(reason) for reason in reasons if isinstance(reason, dict)],
        key=lambda row: (
            int(row.get("priority_rank") if isinstance(row.get("priority_rank"), int) else health_priority_rank(row.get("reason_code"))),
            -health_severity_rank(row.get("severity")),
            0 if bool(row.get("blocking_bool", False)) else 1,
            str(row.get("reason_code") or ""),
            str(row.get("scope_type") or ""),
            str(row.get("bot_id") or ""),
            str(row.get("symbol") or ""),
        ),
    )


def summarize_health_reasons(reasons: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    ordered = sort_health_reasons(reasons)
    score = 100
    penalties: list[dict[str, Any]] = []
    for row in ordered:
        penalty = int(row.get("penalty") or 0)
        if penalty <= 0:
            continue
        score -= penalty
        penalties.append(
            {
                "reason_code": str(row.get("reason_code") or ""),
                "scope_type": str(row.get("scope_type") or "GLOBAL"),
                "bot_id": row.get("bot_id"),
                "symbol": row.get("symbol"),
                "penalty": penalty,
            }
        )
    return max(0, score), penalties


def _final_health_state(reasons: list[dict[str, Any]], score: int) -> tuple[str, str]:
    ordered = sort_health_reasons(reasons)
    hard_block = any(
        bool(row.get("blocking_bool", False)) and normalize_health_reason_code(row.get("reason_code")) in HARD_BLOCK_REASON_CODES
        for row in ordered
    )
    manual_review = any(
        normalize_health_reason_code(row.get("reason_code")) in MANUAL_REVIEW_REASON_CODES
        for row in ordered
    )
    if hard_block:
        return "BLOCKED", "CRITICAL"
    if manual_review:
        return "MANUAL_REVIEW_REQUIRED", "CRITICAL"
    if ordered:
        if score < 70:
            return "DEGRADED", "CRITICAL"
        if score < 90 or any(health_severity_rank(row.get("severity")) >= 1 for row in ordered):
            return "DEGRADED", "WARN"
    return "HEALTHY", "INFO"


def finalize_health_scope(
    *,
    scope_type: str,
    bot_id: str | None = None,
    symbol: str | None = None,
    reasons: list[dict[str, Any]],
    freshness: dict[str, Any] | None = None,
    recommended_actions: list[str] | None = None,
    component_status: dict[str, Any] | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    ordered = sort_health_reasons(reasons)
    score, penalties = summarize_health_reasons(ordered)
    state, severity = _final_health_state(ordered, score)
    scope_type_n = normalize_health_scope_type(scope_type)
    if scope_type_n != "GLOBAL" and state != "MANUAL_REVIEW_REQUIRED":
        if any(bool(row.get("blocking_bool", False)) for row in ordered):
            state = "BLOCKED"
            severity = "CRITICAL"
    reason_codes = [str(row.get("reason_code") or "") for row in ordered]
    hard_blockers = [
        str(row.get("reason_code") or "")
        for row in ordered
        if bool(row.get("blocking_bool", False)) and normalize_health_reason_code(row.get("reason_code")) in HARD_BLOCK_REASON_CODES
    ]
    warnings = [
        str(row.get("reason_code") or "")
        for row in ordered
        if not bool(row.get("blocking_bool", False))
    ]
    return {
        "scope_key": health_scope_key(scope_type_n, bot_id=bot_id, symbol=symbol),
        "scope_type": scope_type_n,
        "bot_id": str(bot_id or "").strip() or None,
        "symbol": str(symbol or "").strip().upper() or None,
        "state": state,
        "score": score,
        "severity": severity,
        "blocking_bool": state in {"BLOCKED", "MANUAL_REVIEW_REQUIRED"},
        "top_priority_reason_code": reason_codes[0] if reason_codes else "",
        "reason_codes": reason_codes,
        "hard_blockers": list(dict.fromkeys(hard_blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "reason_items": ordered,
        "score_penalties": penalties,
        "freshness": freshness if isinstance(freshness, dict) else {},
        "recommended_actions": list(dict.fromkeys(str(action) for action in (recommended_actions or []) if str(action).strip())),
        "component_status": component_status if isinstance(component_status, dict) else {},
        "can_submit_order": state not in {"BLOCKED", "MANUAL_REVIEW_REQUIRED"},
        "evaluated_at": str(evaluated_at or ""),
    }


def finalize_live_health_summary(
    *,
    evaluated_at: str,
    reasons: list[dict[str, Any]],
    component_status: dict[str, Any],
    freshness: dict[str, Any],
    recommended_actions: list[str] | None = None,
    scope_status: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    global_scope = finalize_health_scope(
        scope_type="GLOBAL",
        reasons=reasons,
        freshness=freshness,
        recommended_actions=recommended_actions,
        component_status=component_status,
        evaluated_at=evaluated_at,
    )
    scopes = scope_status if isinstance(scope_status, list) else []
    can_submit = {
        str(row.get("scope_key") or health_scope_key(row.get("scope_type"), row.get("bot_id"), row.get("symbol"))): bool(row.get("can_submit_order", False))
        for row in scopes
        if isinstance(row, dict)
    }
    can_submit.setdefault("GLOBAL", bool(global_scope.get("can_submit_order", False)))
    return {
        "state": str(global_scope.get("state") or "DEGRADED"),
        "score": int(global_scope.get("score") or 0),
        "severity": str(global_scope.get("severity") or "WARN"),
        "global_state": str(global_scope.get("state") or "DEGRADED"),
        "global_score": int(global_scope.get("score") or 0),
        "global_severity": str(global_scope.get("severity") or "WARN"),
        "blocking_bool": bool(global_scope.get("blocking_bool", False)),
        "top_priority_reason_code": str(global_scope.get("top_priority_reason_code") or ""),
        "reason_codes": list(global_scope.get("reason_codes") or []),
        "hard_blockers": list(global_scope.get("hard_blockers") or []),
        "warnings": list(global_scope.get("warnings") or []),
        "reason_items": list(global_scope.get("reason_items") or []),
        "score_penalties": list(global_scope.get("score_penalties") or []),
        "component_status": component_status if isinstance(component_status, dict) else {},
        "scope_status": scopes,
        "freshness": freshness if isinstance(freshness, dict) else {},
        "recommended_actions": list(global_scope.get("recommended_actions") or []),
        "can_enable_live_mode": str(global_scope.get("state") or "DEGRADED") not in {"BLOCKED", "MANUAL_REVIEW_REQUIRED"},
        "can_start_live": str(global_scope.get("state") or "DEGRADED") not in {"BLOCKED", "MANUAL_REVIEW_REQUIRED"},
        "can_submit_order_by_scope": can_submit,
        "last_evaluated_at": str(evaluated_at or ""),
    }

from __future__ import annotations

from typing import Any


ALERT_SCOPE_TYPES = {"GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"}
ALERT_SEVERITIES = {"INFO", "WARN", "CRITICAL"}
ALERT_STATES = {"OPEN", "ACKED", "SUPPRESSED", "COOLDOWN", "RESOLVED", "EXPIRED"}
ALERT_ACTIVE_STATES = {"OPEN", "ACKED", "SUPPRESSED", "COOLDOWN"}
ALERT_SOURCE_LAYERS = {"RAW", "HEALTH", "SAFETY"}
ALERT_EVENT_TYPES = {
    "OPENED",
    "UPDATED",
    "ACKED",
    "SUPPRESSED",
    "COOLDOWN_STARTED",
    "RESOLVED",
    "RESOLVE_REJECTED",
    "REOPENED",
    "EXPIRED",
}

ALERT_TRIGGER_CATALOG: dict[str, dict[str, Any]] = {
    "STREAM_GAP_WARN": {
        "description": "Stream gap observado sobre umbral warn.",
        "default_severity": "WARN",
        "source_layer": "RAW",
        "scope_type_supported": ["GLOBAL", "SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "STREAM_GAP_CRITICAL": {
        "description": "Stream gap observado sobre umbral critical.",
        "default_severity": "CRITICAL",
        "source_layer": "RAW",
        "scope_type_supported": ["GLOBAL", "SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "STREAM_TERMINATED": {
        "description": "El stream fue marcado como terminado.",
        "default_severity": "CRITICAL",
        "source_layer": "RAW",
        "scope_type_supported": ["GLOBAL", "SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "PREFLIGHT_EXPIRED": {
        "description": "Preflight live expirado.",
        "default_severity": "CRITICAL",
        "source_layer": "HEALTH",
        "scope_type_supported": ["GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "PREFLIGHT_FAIL": {
        "description": "Preflight live en fail.",
        "default_severity": "CRITICAL",
        "source_layer": "HEALTH",
        "scope_type_supported": ["GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "RECONCILIATION_DESYNC_OPEN": {
        "description": "Reconciliation con DESYNC abierto.",
        "default_severity": "CRITICAL",
        "source_layer": "HEALTH",
        "scope_type_supported": ["GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "RECONCILIATION_MANUAL_REVIEW_OPEN": {
        "description": "Reconciliation requiere manual review.",
        "default_severity": "CRITICAL",
        "source_layer": "HEALTH",
        "scope_type_supported": ["GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "UNKNOWN_TIMEOUT_STUCK": {
        "description": "Unknown timeout sigue activo por encima del hard deadline.",
        "default_severity": "CRITICAL",
        "source_layer": "HEALTH",
        "scope_type_supported": ["GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "BREAKER_OPEN_BLOCKING": {
        "description": "Breaker abierto y bloqueante.",
        "default_severity": "CRITICAL",
        "source_layer": "SAFETY",
        "scope_type_supported": ["GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "MANUAL_LOCK_ACTIVE": {
        "description": "Manual lock activo.",
        "default_severity": "CRITICAL",
        "source_layer": "SAFETY",
        "scope_type_supported": ["GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "RATE_LIMIT_PRESSURE_HIGH": {
        "description": "Presion alta de rate limits observada.",
        "default_severity": "WARN",
        "source_layer": "RAW",
        "scope_type_supported": ["GLOBAL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "HTTP_418_RISK_ACTIVE": {
        "description": "Riesgo activo de ban 418.",
        "default_severity": "CRITICAL",
        "source_layer": "RAW",
        "scope_type_supported": ["GLOBAL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "OPEN_ORDER_PRESSURE_HIGH": {
        "description": "Presion alta por ordenes abiertas.",
        "default_severity": "WARN",
        "source_layer": "RAW",
        "scope_type_supported": ["GLOBAL", "SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "EMERGENCY_ACTION_ACTIVE": {
        "description": "Accion de emergencia reciente o activa.",
        "default_severity": "WARN",
        "source_layer": "SAFETY",
        "scope_type_supported": ["GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "FREEZE_SYMBOL_ACTIVE": {
        "description": "Freeze por simbolo activo.",
        "default_severity": "WARN",
        "source_layer": "SAFETY",
        "scope_type_supported": ["SYMBOL", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "FREEZE_BOT_ACTIVE": {
        "description": "Freeze por bot activo.",
        "default_severity": "WARN",
        "source_layer": "SAFETY",
        "scope_type_supported": ["BOT", "BOT_SYMBOL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
    "FREEZE_GLOBAL_ACTIVE": {
        "description": "Freeze global activo.",
        "default_severity": "CRITICAL",
        "source_layer": "SAFETY",
        "scope_type_supported": ["GLOBAL"],
        "dedup_strategy": "trigger_scope_active",
        "suppression_strategy": "manual_until",
        "cooldown_strategy": "timebox_rearm",
    },
}

ALERT_TRIGGER_CODES = set(ALERT_TRIGGER_CATALOG.keys())


def _normalize_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_alert_scope_type(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in ALERT_SCOPE_TYPES else "GLOBAL"


def normalize_alert_state(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in ALERT_STATES else "OPEN"


def normalize_alert_severity(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in ALERT_SEVERITIES else "WARN"


def normalize_alert_source_layer(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in ALERT_SOURCE_LAYERS else "RAW"


def normalize_alert_event_type(value: Any) -> str:
    normalized = _normalize_upper(value).replace("-", "_").replace(" ", "_")
    return normalized if normalized in ALERT_EVENT_TYPES else "UPDATED"


def normalize_alert_trigger_code(value: Any) -> str:
    normalized = _normalize_upper(value).replace("-", "_").replace(" ", "_")
    if normalized in ALERT_TRIGGER_CODES:
        return normalized
    return normalized or "STREAM_GAP_WARN"


def alert_scope_key(scope_type: Any, bot_id: Any = None, symbol: Any = None) -> str:
    scope_type_n = normalize_alert_scope_type(scope_type)
    bot_id_n = str(bot_id or "").strip()
    symbol_n = str(symbol or "").strip().upper()
    if scope_type_n == "GLOBAL":
        return "GLOBAL"
    if scope_type_n == "BOT":
        return f"BOT:{bot_id_n}"
    if scope_type_n == "SYMBOL":
        return f"SYMBOL:{symbol_n}"
    return f"BOT_SYMBOL:{bot_id_n}:{symbol_n}"


def alert_scope_matches(
    *,
    row_scope_type: Any,
    row_bot_id: Any,
    row_symbol: Any,
    bot_id: str | None = None,
    symbol: str | None = None,
) -> bool:
    scope_type = normalize_alert_scope_type(row_scope_type)
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


def alert_severity_rank(value: Any) -> int:
    return {"INFO": 0, "WARN": 1, "CRITICAL": 2}.get(normalize_alert_severity(value), 1)


def alert_state_active(value: Any) -> bool:
    return normalize_alert_state(value) in ALERT_ACTIVE_STATES


def choose_alert_severity(*values: Any) -> str:
    candidates = [normalize_alert_severity(value) for value in values if str(value or "").strip()]
    if not candidates:
        return "WARN"
    return max(candidates, key=alert_severity_rank)


def alert_catalog_entry(trigger_code: Any) -> dict[str, Any]:
    code = normalize_alert_trigger_code(trigger_code)
    spec = ALERT_TRIGGER_CATALOG.get(code, {})
    return {
        "trigger_code": code,
        "description": str(spec.get("description") or code),
        "default_severity": normalize_alert_severity(spec.get("default_severity")),
        "source_layer": normalize_alert_source_layer(spec.get("source_layer")),
        "scope_type_supported": [normalize_alert_scope_type(value) for value in list(spec.get("scope_type_supported") or [])],
        "dedup_strategy": str(spec.get("dedup_strategy") or "trigger_scope_active"),
        "suppression_strategy": str(spec.get("suppression_strategy") or "manual_until"),
        "cooldown_strategy": str(spec.get("cooldown_strategy") or "timebox_rearm"),
    }


def default_alert_catalog_entries() -> list[dict[str, Any]]:
    return [alert_catalog_entry(trigger_code) for trigger_code in sorted(ALERT_TRIGGER_CATALOG.keys())]


def build_alert_instance(
    *,
    trigger_code: Any,
    severity: Any,
    state: Any,
    source_layer: Any,
    scope_type: Any,
    bot_id: Any = None,
    symbol: Any = None,
    opened_at: Any = None,
    last_seen_at: Any = None,
    acked_at: Any = None,
    suppressed_until: Any = None,
    cooldown_until: Any = None,
    resolved_at: Any = None,
    expires_at: Any = None,
    source_refs: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    summary_text: Any = None,
) -> dict[str, Any]:
    scope_type_n = normalize_alert_scope_type(scope_type)
    bot_id_n = str(bot_id or "").strip() or None
    symbol_n = str(symbol or "").strip().upper() or None
    state_n = normalize_alert_state(state)
    return {
        "trigger_code": normalize_alert_trigger_code(trigger_code),
        "severity": normalize_alert_severity(severity),
        "state": state_n,
        "source_layer": normalize_alert_source_layer(source_layer),
        "scope_type": scope_type_n,
        "scope_key": alert_scope_key(scope_type_n, bot_id=bot_id_n, symbol=symbol_n),
        "bot_id": bot_id_n,
        "symbol": symbol_n,
        "opened_at": str(opened_at or ""),
        "last_seen_at": str(last_seen_at or ""),
        "acked_at": str(acked_at or "") or None,
        "suppressed_until": str(suppressed_until or "") or None,
        "cooldown_until": str(cooldown_until or "") or None,
        "resolved_at": str(resolved_at or "") or None,
        "expires_at": str(expires_at or "") or None,
        "source_refs": source_refs if isinstance(source_refs, dict) else {},
        "evidence": evidence if isinstance(evidence, dict) else {},
        "summary_text": str(summary_text or ""),
        "lifecycle": {
            "acked_bool": state_n == "ACKED",
            "suppressed_bool": state_n == "SUPPRESSED",
            "cooldown_bool": state_n == "COOLDOWN",
            "resolved_bool": state_n == "RESOLVED",
            "expired_bool": state_n == "EXPIRED",
            "active_bool": alert_state_active(state_n),
        },
    }


def build_alert_event(
    *,
    alert_instance_id: Any,
    event_type: Any,
    previous_state: Any = None,
    next_state: Any = None,
    payload: dict[str, Any] | None = None,
    actor: Any = None,
    occurred_at: Any = None,
) -> dict[str, Any]:
    return {
        "alert_instance_id": str(alert_instance_id or ""),
        "event_type": normalize_alert_event_type(event_type),
        "previous_state": normalize_alert_state(previous_state) if str(previous_state or "").strip() else None,
        "next_state": normalize_alert_state(next_state) if str(next_state or "").strip() else None,
        "payload": payload if isinstance(payload, dict) else {},
        "actor": str(actor or "").strip() or None,
        "occurred_at": str(occurred_at or ""),
    }


def alert_summary_text(
    trigger_code: Any,
    *,
    scope_type: Any,
    bot_id: Any = None,
    symbol: Any = None,
    evidence: dict[str, Any] | None = None,
) -> str:
    entry = alert_catalog_entry(trigger_code)
    scope_key = alert_scope_key(scope_type, bot_id=bot_id, symbol=symbol)
    parts = [str(entry.get("description") or trigger_code), scope_key]
    if isinstance(evidence, dict):
        hint = str(
            evidence.get("reason_code")
            or evidence.get("breaker_code")
            or evidence.get("event_code")
            or evidence.get("source_status")
            or ""
        ).strip()
        if hint:
            parts.append(hint)
    return " | ".join(part for part in parts if part)

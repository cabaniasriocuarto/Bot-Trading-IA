from __future__ import annotations

from typing import Any


LIVE_SIGNAL_SCOPE_TYPES = {"GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"}
LIVE_SIGNAL_SNAPSHOT_TYPES = {
    "EXECUTION",
    "FILLS",
    "STREAM",
    "RECONCILIATION",
    "PREFLIGHT",
    "RATE_LIMIT",
    "RISK",
}
LIVE_SIGNAL_SOURCE_TYPES = {
    "EXECUTION",
    "STREAM",
    "FILL",
    "RECONCILIATION",
    "PREFLIGHT",
    "RATE_LIMIT",
    "RISK",
}
LIVE_SIGNAL_SEVERITIES = {"INFO", "WARN", "CRITICAL"}
LIVE_SIGNAL_SOURCE_STATUSES = {"OK", "WARN", "CRITICAL", "MISSING"}


def _normalize_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_live_signal_scope_type(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in LIVE_SIGNAL_SCOPE_TYPES else "GLOBAL"


def normalize_live_signal_snapshot_type(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in LIVE_SIGNAL_SNAPSHOT_TYPES else "EXECUTION"


def normalize_live_signal_source_type(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in LIVE_SIGNAL_SOURCE_TYPES else "EXECUTION"


def normalize_live_signal_severity(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in LIVE_SIGNAL_SEVERITIES else "INFO"


def normalize_live_signal_source_status(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in LIVE_SIGNAL_SOURCE_STATUSES else "OK"


def normalize_live_signal_event_code(value: Any) -> str:
    text = _normalize_upper(value).replace("-", "_").replace(" ", "_")
    return text or "SIGNAL_OBSERVED"


def live_signal_scope_key(scope_type: Any, bot_id: Any = None, symbol: Any = None) -> str:
    scope_type_n = normalize_live_signal_scope_type(scope_type)
    bot_id_n = str(bot_id or "").strip()
    symbol_n = str(symbol or "").strip().upper()
    if scope_type_n == "GLOBAL":
        return "GLOBAL"
    if scope_type_n == "BOT":
        return f"BOT:{bot_id_n}"
    if scope_type_n == "SYMBOL":
        return f"SYMBOL:{symbol_n}"
    return f"BOT_SYMBOL:{bot_id_n}:{symbol_n}"


def build_live_signal_payload(
    *,
    metrics: dict[str, Any] | None = None,
    observed_states: dict[str, Any] | None = None,
    freshness: dict[str, Any] | None = None,
    source_timestamps: dict[str, Any] | None = None,
    source_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "metrics": metrics if isinstance(metrics, dict) else {},
        "observed_states": observed_states if isinstance(observed_states, dict) else {},
        "freshness": freshness if isinstance(freshness, dict) else {},
        "source_timestamps": source_timestamps if isinstance(source_timestamps, dict) else {},
        "source_refs": source_refs if isinstance(source_refs, dict) else {},
    }


def build_live_signal_snapshot(
    *,
    scope_type: str,
    snapshot_type: str,
    source_module: str,
    collected_at: str,
    freshness_ms: int | None,
    signal_payload: dict[str, Any],
    source_status: str = "OK",
    bot_id: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    scope_type_n = normalize_live_signal_scope_type(scope_type)
    snapshot_type_n = normalize_live_signal_snapshot_type(snapshot_type)
    return {
        "signal_snapshot_id": None,
        "scope_type": scope_type_n,
        "scope_key": live_signal_scope_key(scope_type_n, bot_id=bot_id, symbol=symbol),
        "bot_id": str(bot_id or "").strip() or None,
        "symbol": str(symbol or "").strip().upper() or None,
        "snapshot_type": snapshot_type_n,
        "collected_at": str(collected_at or ""),
        "source_module": str(source_module or f"runtime_bridge.{snapshot_type_n.lower()}"),
        "freshness_ms": int(freshness_ms) if freshness_ms is not None else None,
        "source_status": normalize_live_signal_source_status(source_status),
        "signal_payload": build_live_signal_payload(
            metrics=signal_payload.get("metrics") if isinstance(signal_payload, dict) else None,
            observed_states=signal_payload.get("observed_states") if isinstance(signal_payload, dict) else None,
            freshness=signal_payload.get("freshness") if isinstance(signal_payload, dict) else None,
            source_timestamps=signal_payload.get("source_timestamps") if isinstance(signal_payload, dict) else None,
            source_refs=signal_payload.get("source_refs") if isinstance(signal_payload, dict) else None,
        ),
    }


def build_live_signal_event(
    *,
    source_type: str,
    event_code: str,
    scope_type: str,
    event_time: str,
    observed_value: dict[str, Any] | None = None,
    raw_payload: dict[str, Any] | None = None,
    severity_observed: str = "INFO",
    bot_id: str | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    return {
        "signal_event_id": None,
        "event_time": str(event_time or ""),
        "source_type": normalize_live_signal_source_type(source_type),
        "event_code": normalize_live_signal_event_code(event_code),
        "scope_type": normalize_live_signal_scope_type(scope_type),
        "bot_id": str(bot_id or "").strip() or None,
        "symbol": str(symbol or "").strip().upper() or None,
        "severity_observed": normalize_live_signal_severity(severity_observed),
        "observed_value": observed_value if isinstance(observed_value, dict) else {},
        "raw_payload": raw_payload if isinstance(raw_payload, dict) else {},
    }


from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any


LIVE_SIGNAL_SCHEMA_VERSION = 2

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

LIVE_SIGNAL_PAYLOAD_SCHEMAS: dict[str, dict[str, set[str]]] = {
    "EXECUTION": {
        "numeric_metrics": {
            "execution_submit_total_window",
            "execution_reject_total_window",
            "execution_cancel_fail_total_window",
            "execution_unknown_timeout_active_count",
            "execution_open_orders_count",
            "execution_terminal_orders_recent_count",
            "execution_pending_orders_recent_count",
        },
        "state_values": {
            "runtime_last_remote_submit_error",
            "runtime_last_remote_submit_reason",
            "runtime_last_signal_action",
            "runtime_last_signal_symbol",
            "runtime_last_signal_side",
            "runtime_unknown_timeout_active",
        },
        "timestamps_ms": {
            "latest_order_updated_at_ms",
            "runtime_last_remote_submit_at_ms",
            "runtime_unknown_timeout_since_ms",
        },
        "refs": {
            "scope_key",
            "source_table",
            "source_module",
        },
    },
    "FILLS": {
        "numeric_metrics": {
            "fills_recent_count",
            "fills_partial_recent_count",
            "fills_final_recent_count",
            "fills_commission_observed_recent_count",
            "fills_last_event_age_ms",
            "fills_count_runtime_total",
            "fills_notional_runtime_usd_total",
        },
        "state_values": {
            "commission_observed_supported",
            "runtime_cost_proxy_available",
            "fills_runtime_costs_source",
        },
        "timestamps_ms": {
            "last_fill_updated_at_ms",
        },
        "refs": {
            "scope_key",
            "source_module",
        },
    },
    "STREAM": {
        "numeric_metrics": {
            "stream_gap_ms",
            "stream_last_event_age_ms",
            "stream_reconnect_count_window",
        },
        "state_values": {
            "stream_connected_bool",
            "stream_terminated_bool",
            "stream_reconnect_count_observed",
            "runtime_exchange_reason",
        },
        "timestamps_ms": {
            "stream_last_event_at_ms",
        },
        "refs": {
            "scope_key",
            "stream_gap_warn_ms",
            "stream_gap_critical_ms",
            "source_module",
        },
    },
    "RECONCILIATION": {
        "numeric_metrics": {
            "reconciliation_last_run_age_ms",
            "reconciliation_open_cases_count",
            "reconciliation_desync_count",
            "reconciliation_manual_review_count",
        },
        "state_values": {
            "reconciliation_source",
            "reconciliation_source_ok",
            "reconciliation_source_reason",
        },
        "timestamps_ms": {
            "reconciliation_last_run_at_ms",
        },
        "refs": {
            "scope_key",
            "source_module",
        },
    },
    "PREFLIGHT": {
        "numeric_metrics": {
            "preflight_last_run_age_ms",
            "preflight_time_to_expiry_ms",
            "preflight_attestation_age_ms",
        },
        "state_values": {
            "preflight_last_status_observed",
            "preflight_last_reason_observed",
            "preflight_attestation_supported",
        },
        "timestamps_ms": {
            "preflight_last_run_at_ms",
        },
        "refs": {
            "scope_key",
            "preflight_stale_threshold_ms",
            "preflight_expired_threshold_ms",
            "source_module",
        },
    },
    "RATE_LIMIT": {
        "numeric_metrics": {
            "rate_limit_429_count_window",
            "open_order_pressure_count",
            "rate_limit_hits_cumulative",
            "last_rate_limit_event_age_ms",
        },
        "state_values": {
            "rate_limit_418_active_bool",
            "retry_after_active_bool",
        },
        "timestamps_ms": {
            "last_rate_limit_event_at_ms",
        },
        "refs": {
            "scope_key",
            "guardrail_http_429_threshold",
            "source_module",
        },
    },
    "RISK": {
        "numeric_metrics": {
            "risk_open_positions_count",
            "risk_daily_loss_value",
            "risk_max_drawdown_value",
            "risk_equity_value",
        },
        "state_values": {
            "runtime_risk_allow_new_positions",
            "runtime_risk_reason",
        },
        "timestamps_ms": {
            "runtime_last_event_at_ms",
        },
        "refs": {
            "scope_key",
            "source_module",
            "risk_observed_only",
        },
    },
}


def _normalize_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _normalize_bot_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_schema_version(value: Any) -> int:
    try:
        version = int(value)
    except Exception:
        version = LIVE_SIGNAL_SCHEMA_VERSION
    return version if version > 0 else LIVE_SIGNAL_SCHEMA_VERSION


def _normalize_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _normalize_timestamp_iso(value: Any) -> str:
    dt = _normalize_datetime(value)
    return dt.isoformat() if isinstance(dt, datetime) else ""


def _normalize_timestamp_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not isfinite(float(value)):
            return None
        return int(value)
    dt = _normalize_datetime(value)
    if not isinstance(dt, datetime):
        return None
    return int(dt.timestamp() * 1000.0)


def _normalize_numeric_value(value: Any) -> int | float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not isfinite(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        if any(token in text for token in (".", "e", "E")):
            parsed = float(text)
            return parsed if isfinite(parsed) else None
        return int(text)
    except Exception:
        return None


def _normalize_scalar_ref(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not isfinite(value):
            return None
        return value
    if isinstance(value, (list, tuple)):
        normalized_list = []
        for item in value:
            normalized = _normalize_scalar_ref(item)
            if normalized is not None and not isinstance(normalized, (list, tuple, dict)):
                normalized_list.append(normalized)
        return normalized_list
    return None


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


def live_signal_payload_schema(snapshot_type: Any) -> dict[str, set[str]]:
    snapshot_type_n = normalize_live_signal_snapshot_type(snapshot_type)
    return LIVE_SIGNAL_PAYLOAD_SCHEMAS.get(snapshot_type_n, LIVE_SIGNAL_PAYLOAD_SCHEMAS["EXECUTION"])


def _normalize_live_signal_payload_dict(
    values: dict[str, Any] | None,
    *,
    allowed_keys: set[str],
    normalize_value,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in allowed_keys:
        normalized = normalize_value(values.get(key) if isinstance(values, dict) else None)
        if normalized is not None:
            out[key] = normalized
    return out


def _legacy_live_signal_payload(snapshot_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    observed_states = payload.get("observed_states") if isinstance(payload.get("observed_states"), dict) else {}
    freshness = payload.get("freshness") if isinstance(payload.get("freshness"), dict) else {}
    source_timestamps = payload.get("source_timestamps") if isinstance(payload.get("source_timestamps"), dict) else {}
    source_refs = payload.get("source_refs") if isinstance(payload.get("source_refs"), dict) else {}

    merged_metrics = dict(metrics)
    for key, value in freshness.items():
        if key not in merged_metrics:
            merged_metrics[key] = value

    timestamps_ms: dict[str, Any] = {}
    for key, value in source_timestamps.items():
        suffix_key = key if key.endswith("_ms") else f"{key}_ms"
        timestamps_ms[suffix_key] = value

    return build_live_signal_payload(
        snapshot_type=snapshot_type,
        numeric_metrics=merged_metrics,
        state_values=observed_states,
        timestamps_ms=timestamps_ms,
        refs=source_refs,
    )


def build_live_signal_payload(
    *,
    snapshot_type: str,
    numeric_metrics: dict[str, Any] | None = None,
    state_values: dict[str, Any] | None = None,
    timestamps_ms: dict[str, Any] | None = None,
    refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot_type_n = normalize_live_signal_snapshot_type(snapshot_type)
    schema = live_signal_payload_schema(snapshot_type_n)

    normalized_metrics = _normalize_live_signal_payload_dict(
        numeric_metrics,
        allowed_keys=schema["numeric_metrics"],
        normalize_value=_normalize_numeric_value,
    )
    normalized_states = _normalize_live_signal_payload_dict(
        state_values,
        allowed_keys=schema["state_values"],
        normalize_value=lambda value: value if isinstance(value, (str, int, float, bool)) or value is None else None,
    )
    normalized_timestamps = _normalize_live_signal_payload_dict(
        timestamps_ms,
        allowed_keys=schema["timestamps_ms"],
        normalize_value=_normalize_timestamp_ms,
    )
    normalized_refs = _normalize_live_signal_payload_dict(
        refs,
        allowed_keys=schema["refs"],
        normalize_value=_normalize_scalar_ref,
    )
    return {
        "kind": snapshot_type_n,
        "numeric_metrics": normalized_metrics,
        "state_values": normalized_states,
        "timestamps_ms": normalized_timestamps,
        "refs": normalized_refs,
    }


def live_signal_snapshot_payload(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return build_live_signal_payload(snapshot_type="EXECUTION")
    payload = snapshot.get("payload") if isinstance(snapshot.get("payload"), dict) else None
    if not isinstance(payload, dict):
        payload = snapshot.get("signal_payload") if isinstance(snapshot.get("signal_payload"), dict) else None
    if not isinstance(payload, dict):
        return build_live_signal_payload(snapshot_type=snapshot.get("snapshot_type"))
    if {"kind", "numeric_metrics", "state_values", "timestamps_ms", "refs"} <= set(payload.keys()):
        return build_live_signal_payload(
            snapshot_type=payload.get("kind") or snapshot.get("snapshot_type"),
            numeric_metrics=payload.get("numeric_metrics") if isinstance(payload.get("numeric_metrics"), dict) else {},
            state_values=payload.get("state_values") if isinstance(payload.get("state_values"), dict) else {},
            timestamps_ms=payload.get("timestamps_ms") if isinstance(payload.get("timestamps_ms"), dict) else {},
            refs=payload.get("refs") if isinstance(payload.get("refs"), dict) else {},
        )
    return _legacy_live_signal_payload(
        normalize_live_signal_snapshot_type(snapshot.get("snapshot_type")),
        payload,
    )


def live_signal_numeric_metrics(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return dict(live_signal_snapshot_payload(snapshot).get("numeric_metrics") or {})


def live_signal_state_values(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return dict(live_signal_snapshot_payload(snapshot).get("state_values") or {})


def live_signal_timestamps_ms(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return dict(live_signal_snapshot_payload(snapshot).get("timestamps_ms") or {})


def live_signal_refs(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    return dict(live_signal_snapshot_payload(snapshot).get("refs") or {})


def build_live_signal_snapshot(
    *,
    scope_type: str,
    snapshot_type: str,
    source_module: str,
    collected_at: Any,
    window_ms: int | None,
    freshness_ms: int | None,
    payload: dict[str, Any],
    source_status: str = "OK",
    bot_id: str | None = None,
    symbol: str | None = None,
    schema_version: int | None = None,
) -> dict[str, Any]:
    scope_type_n = normalize_live_signal_scope_type(scope_type)
    snapshot_type_n = normalize_live_signal_snapshot_type(snapshot_type)
    collected_at_iso = _normalize_timestamp_iso(collected_at)
    collected_at_ms = _normalize_timestamp_ms(collected_at)
    payload_n = live_signal_snapshot_payload(
        {
            "snapshot_type": snapshot_type_n,
            "payload": payload,
        }
    )
    return {
        "signal_snapshot_id": None,
        "scope_type": scope_type_n,
        "scope_key": live_signal_scope_key(scope_type_n, bot_id=bot_id, symbol=symbol),
        "bot_id": _normalize_bot_id(bot_id),
        "symbol": _normalize_symbol(symbol),
        "snapshot_type": snapshot_type_n,
        "schema_version": _normalize_schema_version(schema_version),
        "collected_at": collected_at_iso,
        "collected_at_ms": collected_at_ms,
        "window_ms": int(window_ms) if window_ms is not None else None,
        "source_module": str(source_module or f"runtime_bridge.{snapshot_type_n.lower()}"),
        "source_status": normalize_live_signal_source_status(source_status),
        "freshness_ms": int(freshness_ms) if freshness_ms is not None else None,
        "payload": payload_n,
        "signal_payload": payload_n,
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
        "schema_version": LIVE_SIGNAL_SCHEMA_VERSION,
        "event_time": _normalize_timestamp_iso(event_time),
        "event_time_ms": _normalize_timestamp_ms(event_time),
        "source_type": normalize_live_signal_source_type(source_type),
        "event_code": normalize_live_signal_event_code(event_code),
        "scope_type": normalize_live_signal_scope_type(scope_type),
        "scope_key": live_signal_scope_key(scope_type, bot_id=bot_id, symbol=symbol),
        "bot_id": _normalize_bot_id(bot_id),
        "symbol": _normalize_symbol(symbol),
        "severity_observed": normalize_live_signal_severity(severity_observed),
        "observed_value": observed_value if isinstance(observed_value, dict) else {},
        "raw_payload": live_signal_snapshot_payload({"snapshot_type": source_type, "payload": raw_payload}) if isinstance(raw_payload, dict) else {},
    }

from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import yaml

from rtlab_core.execution.binance_adapter import BinanceLiveAdapter
from rtlab_core.execution.filter_prevalidator import (
    describe_filter_rules,
    evaluate_prevalidator,
)
from rtlab_core.execution.live_fill_state import (
    build_live_fill_dedup_key,
    build_live_fill_id,
    fill_reconciliation_status,
    normalize_fill_source_type,
)
from rtlab_core.execution.live_order_state import (
    AMBIGUOUS_LOCAL_ORDER_STATES,
    BLOCKING_LOCAL_ORDER_STATES,
    OPENISH_EXCHANGE_ORDER_STATUSES,
    TERMINAL_LOCAL_ORDER_STATES,
    blocks_new_submits,
    execution_report_dedup_key,
    is_ambiguous_local_state,
    is_terminal_local_state,
    map_exchange_event_to_local_state,
    normalize_local_state,
)
from rtlab_core.execution.live_market_runtime import BinanceMarketWebSocketRuntime
from rtlab_core.execution.live_user_stream_runtime import BinanceUserStreamRuntime
from rtlab_core.execution.reconciliation_engine import (
    RECONCILIATION_CASE_SEVERITIES,
    RECONCILIATION_CASE_STATUSES,
    RECONCILIATION_DISCREPANCY_CODES,
    RECONCILIATION_SNAPSHOT_TYPES,
    RECONCILIATION_TRIGGER_TYPES,
    discrepancy_payload,
    normalize_reconciliation_case_event_source,
    normalize_reconciliation_case_severity,
    normalize_reconciliation_case_status,
    normalize_reconciliation_discrepancy_code,
    normalize_reconciliation_snapshot_type,
    normalize_reconciliation_trigger,
    reconciliation_case_blocks_live,
    reconciliation_severity_rank,
)
from rtlab_core.policy_paths import describe_policy_root_resolution


EXECUTION_SAFETY_FILENAME = "execution_safety.yaml"
EXECUTION_ROUTER_FILENAME = "execution_router.yaml"
POLICY_EXPECTED_FILES: tuple[str, ...] = (
    "instrument_registry.yaml",
    "universes.yaml",
    "cost_stack.yaml",
    "reporting_exports.yaml",
    EXECUTION_SAFETY_FILENAME,
    EXECUTION_ROUTER_FILENAME,
)
PARSER_VERSION = "execution_reality_base_v1"
RECONCILE_TYPES = {
    "ack_missing",
    "fill_discrepancy",
    "fill_missing",
    "status_mismatch",
    "orphan_order",
    "cost_mismatch",
    "position_mismatch",
}
RECONCILE_SEVERITIES = {"INFO", "WARN", "BLOCK"}
TERMINAL_ORDER_STATUSES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED", "EXPIRED_IN_MATCH"}

FAIL_CLOSED_MINIMAL_EXECUTION_SAFETY_POLICY: dict[str, Any] = {
    "execution_safety": {
        "modes": {
            "allow_live": False,
            "allow_testnet": False,
            "allow_paper": False,
            "allow_shadow": False,
        },
        "preflight": {
            "require_policy_loaded": True,
            "require_instrument_registry_match": True,
            "require_universe_membership_for_live": True,
            "require_live_eligible": True,
            "require_capability_snapshot": True,
            "require_snapshot_fresh": True,
            "snapshot_block_if_older_than_hours": 1,
            "quote_stale_block_ms": 1,
            "orderbook_stale_warn_ms": 1,
            "orderbook_stale_block_ms": 1,
            "reject_if_missing_basic_filters": True,
            "reject_if_missing_fee_source_in_live": True,
        },
        "exchange_filters": {
            "max_age_ms": 1,
            "missing_symbol_filters": "block",
            "invalid_tick_alignment": "block",
            "invalid_step_alignment": "block",
            "invalid_min_notional": "block",
            "unsupported_family_filter_combo": "block",
            "missing_exchange_info": "block",
            "filter_source_mismatch": "block",
        },
        "exchange_adapter": {
            "signed_rest_enabled": True,
            "server_time_sync_enabled": True,
            "require_server_time_sync_in_live_like_modes": True,
            "server_time_cache_sec": 1,
            "recv_window_ms": 1000,
            "max_clock_skew_ms": 1,
            "retry_invalid_timestamp_once": True,
        },
        "sizing": {
            "max_notional_per_order_usd": 0.0,
            "max_open_orders_per_symbol": 0,
            "max_open_orders_total": 0,
            "min_notional_buffer_pct_above_exchange_min": 100.0,
        },
        "slippage": {
            "warn_bps_spot": 0.0,
            "block_bps_spot": 0.0,
            "warn_bps_margin": 0.0,
            "block_bps_margin": 0.0,
            "warn_bps_usdm": 0.0,
            "block_bps_usdm": 0.0,
            "warn_bps_coinm": 0.0,
            "block_bps_coinm": 0.0,
        },
        "reconciliation": {
            "poll_open_orders_sec": 1,
            "poll_order_status_sec": 1,
            "poll_user_trades_sec": 1,
            "order_ack_timeout_sec": 1,
            "fill_reconcile_timeout_sec": 1,
            "orphan_order_warn_sec": 1,
            "orphan_order_block_sec": 1,
            "unknown_reconciliation_soft_deadline_sec": 1,
            "unknown_reconciliation_hard_deadline_sec": 1,
        },
        "kill_switch": {
            "enabled": True,
            "auto_cancel_all_on_trip": True,
            "cooldown_sec": 1,
            "critical_rejects_5m_block": 1,
            "consecutive_failed_submits_block": 1,
            "stale_market_data_block_ms": 1,
            "repeated_reconcile_mismatch_block_count": 1,
        },
        "futures_auto_cancel": {
            "enabled": True,
            "heartbeat_sec": 1,
            "countdown_ms": 1,
        },
        "margin": {
            "require_margin_level_visible": True,
            "warn_margin_level_below": 999999.0,
            "block_margin_level_below": 999999.0,
        },
        "risk_reduce_only_priority": {
            "enabled": True,
        },
        "persistence": {
            "write_intents_before_submit": True,
            "write_raw_payloads": True,
            "keep_raw_days": 30,
        },
    }
}

FAIL_CLOSED_MINIMAL_EXECUTION_ROUTER_POLICY: dict[str, Any] = {
    "execution_router": {
        "families_enabled": {
            "spot": False,
            "margin": False,
            "usdm_futures": False,
            "coinm_futures": False,
        },
        "first_iteration_supported_order_types": {
            "spot": [],
            "margin": [],
            "usdm_futures": [],
            "coinm_futures": [],
        },
        "time_in_force_allowed": {
            "spot": [],
            "margin": [],
            "usdm_futures": [],
            "coinm_futures": [],
        },
        "prefer_cancel_replace_spot": False,
        "enable_batch_orders_usdm": False,
        "enable_batch_orders_coinm": False,
        "conditional_orders_phase1": False,
    }
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return _utc_now().isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return copy.deepcopy(default)
    if isinstance(value, (dict, list, int, float, bool)):
        return copy.deepcopy(value)
    try:
        return json.loads(str(value))
    except Exception:
        return copy.deepcopy(default)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_text(_json_dumps(value))


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


def _require_str_list(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> list[str]:
    value = parent.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{path}.{key} debe ser lista de strings no vacios")
        return []
    return [str(item).strip() for item in value]


def _execution_policy_source_label(repo_root: Path, policy_path: Path) -> str:
    try:
        return str(policy_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(policy_path.resolve())


def _db_bool(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _hydrate_intent_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["preflight_errors_json"] = _json_loads(out.get("preflight_errors_json"), [])
    out["raw_request_json"] = _json_loads(out.get("raw_request_json"), {})
    if out.get("reduce_only") is not None:
        out["reduce_only"] = _bool(out.get("reduce_only"))
    return out


def _hydrate_order_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["raw_ack_json"] = _json_loads(out.get("raw_ack_json"), {})
    out["raw_last_status_json"] = _json_loads(out.get("raw_last_status_json"), {})
    out["raw_last_payload_json"] = _json_loads(out.get("raw_last_payload_json"), {})
    if out.get("reduce_only") is not None:
        out["reduce_only"] = _bool(out.get("reduce_only"))
    out["current_local_state"] = normalize_local_state(
        out.get("current_local_state")
        or (
            "FILLED"
            if str(out.get("order_status") or "").upper() == "FILLED"
            else "CANCELED"
            if str(out.get("order_status") or "").upper() == "CANCELED"
            else "REJECTED"
            if str(out.get("order_status") or "").upper() == "REJECTED"
            else "EXPIRED_STP"
            if str(out.get("order_status") or "").upper() == "EXPIRED_IN_MATCH"
            else "EXPIRED"
            if str(out.get("order_status") or "").upper() == "EXPIRED"
            else "WORKING"
        )
    )
    if out.get("terminal_at") and not is_terminal_local_state(out.get("current_local_state")):
        out["terminal_at"] = None
    return out


def _hydrate_user_stream_event_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["payload_json"] = _json_loads(out.get("payload_json"), {})
    out["provenance_json"] = _json_loads(out.get("provenance_json"), {})
    return out


def _hydrate_live_order_event_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["raw_payload_json"] = _json_loads(out.get("raw_payload_json"), {})
    if out.get("applied_bool") is not None:
        out["applied_bool"] = _bool(out.get("applied_bool"))
    return out


def _hydrate_reconciliation_run_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["result_summary_json"] = _json_loads(out.get("result_summary_json"), {})
    return out


def _hydrate_fill_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["raw_fill_json"] = _json_loads(out.get("raw_fill_json"), {})
    out["cost_source_json"] = _json_loads(out.get("cost_source_json"), {})
    out["provenance_json"] = _json_loads(out.get("provenance_json"), {})
    out["unresolved_components_json"] = _json_loads(out.get("unresolved_components_json"), [])
    out["discrepancy_json"] = _json_loads(out.get("discrepancy_json"), {})
    if out.get("maker") is not None:
        out["maker"] = _bool(out.get("maker"))
    if out.get("provisional") is not None:
        out["provisional"] = _bool(out.get("provisional"))
    return out


def _hydrate_reconcile_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["details_json"] = _json_loads(out.get("details_json"), {})
    out["resolved"] = _bool(out.get("resolved"))
    return out


def _hydrate_reconciliation_case_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["local_summary_json"] = _json_loads(out.get("local_summary_json"), {})
    out["remote_summary_json"] = _json_loads(out.get("remote_summary_json"), {})
    out["discrepancy_summary_json"] = _json_loads(out.get("discrepancy_summary_json"), {})
    out["resolution_summary_json"] = _json_loads(out.get("resolution_summary_json"), {})
    out["final_status"] = normalize_reconciliation_case_status(out.get("final_status"))
    out["severity"] = normalize_reconciliation_case_severity(out.get("severity"))
    out["blocking_bool"] = _bool(out.get("blocking_bool"))
    return out


def _hydrate_reconciliation_case_event_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["payload_json"] = _json_loads(out.get("payload_json"), {})
    out["decision_json"] = _json_loads(out.get("decision_json"), {})
    out["source_type"] = normalize_reconciliation_case_event_source(out.get("source_type"))
    out["applied_bool"] = _bool(out.get("applied_bool"))
    return out


def _hydrate_reconciliation_snapshot_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["payload_json"] = _json_loads(out.get("payload_json"), {})
    out["snapshot_type"] = normalize_reconciliation_snapshot_type(out.get("snapshot_type"))
    return out


def _fill_source_lineage(existing: dict[str, Any] | None, incoming_source_type: str) -> list[str]:
    source_types: list[str] = []
    provenance = (existing or {}).get("provenance_json") if isinstance((existing or {}).get("provenance_json"), dict) else {}
    for item in provenance.get("source_lineage") or []:
        text = normalize_fill_source_type(item)
        if text and text not in source_types:
            source_types.append(text)
    existing_source = normalize_fill_source_type((existing or {}).get("raw_source_type"))
    if existing_source and existing_source not in source_types and existing_source != "UNKNOWN":
        source_types.append(existing_source)
    normalized_incoming = normalize_fill_source_type(incoming_source_type)
    if normalized_incoming and normalized_incoming not in source_types and normalized_incoming != "UNKNOWN":
        source_types.append(normalized_incoming)
    return source_types


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


def _validate_execution_safety_policy(candidate: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return ["execution_safety policy debe ser dict"]

    root = _require_dict(candidate, "execution_safety", errors=errors, path="execution")
    modes = _require_dict(root, "modes", errors=errors, path="execution.execution_safety")
    for key in ("allow_live", "allow_testnet", "allow_paper", "allow_shadow"):
        _require_bool(modes, key, errors=errors, path="execution.execution_safety.modes")

    preflight = _require_dict(root, "preflight", errors=errors, path="execution.execution_safety")
    for key in (
        "require_policy_loaded",
        "require_instrument_registry_match",
        "require_universe_membership_for_live",
        "require_live_eligible",
        "require_capability_snapshot",
        "require_snapshot_fresh",
        "reject_if_missing_basic_filters",
        "reject_if_missing_fee_source_in_live",
    ):
        _require_bool(preflight, key, errors=errors, path="execution.execution_safety.preflight")
    for key in ("snapshot_block_if_older_than_hours", "quote_stale_block_ms", "orderbook_stale_warn_ms", "orderbook_stale_block_ms"):
        _require_number(preflight, key, errors=errors, path="execution.execution_safety.preflight")

    exchange_adapter = _require_dict(root, "exchange_adapter", errors=errors, path="execution.execution_safety")
    for key in (
        "signed_rest_enabled",
        "server_time_sync_enabled",
        "require_server_time_sync_in_live_like_modes",
        "retry_invalid_timestamp_once",
    ):
        _require_bool(exchange_adapter, key, errors=errors, path="execution.execution_safety.exchange_adapter")
    for key in ("server_time_cache_sec", "recv_window_ms", "max_clock_skew_ms"):
        _require_number(exchange_adapter, key, errors=errors, path="execution.execution_safety.exchange_adapter")

    sizing = _require_dict(root, "sizing", errors=errors, path="execution.execution_safety")
    for key in (
        "max_notional_per_order_usd",
        "max_open_orders_per_symbol",
        "max_open_orders_total",
        "min_notional_buffer_pct_above_exchange_min",
    ):
        _require_number(sizing, key, errors=errors, path="execution.execution_safety.sizing")

    slippage = _require_dict(root, "slippage", errors=errors, path="execution.execution_safety")
    for key in (
        "warn_bps_spot",
        "block_bps_spot",
        "warn_bps_margin",
        "block_bps_margin",
        "warn_bps_usdm",
        "block_bps_usdm",
        "warn_bps_coinm",
        "block_bps_coinm",
    ):
        _require_number(slippage, key, errors=errors, path="execution.execution_safety.slippage")

    reconciliation = _require_dict(root, "reconciliation", errors=errors, path="execution.execution_safety")
    for key in (
        "poll_open_orders_sec",
        "poll_order_status_sec",
        "poll_user_trades_sec",
        "order_ack_timeout_sec",
        "fill_reconcile_timeout_sec",
        "orphan_order_warn_sec",
        "orphan_order_block_sec",
        "unknown_reconciliation_soft_deadline_sec",
        "unknown_reconciliation_hard_deadline_sec",
    ):
        _require_number(reconciliation, key, errors=errors, path="execution.execution_safety.reconciliation")

    kill_switch = _require_dict(root, "kill_switch", errors=errors, path="execution.execution_safety")
    for key in ("enabled", "auto_cancel_all_on_trip"):
        _require_bool(kill_switch, key, errors=errors, path="execution.execution_safety.kill_switch")
    for key in (
        "cooldown_sec",
        "critical_rejects_5m_block",
        "consecutive_failed_submits_block",
        "stale_market_data_block_ms",
        "repeated_reconcile_mismatch_block_count",
    ):
        _require_number(kill_switch, key, errors=errors, path="execution.execution_safety.kill_switch")

    futures_auto_cancel = _require_dict(root, "futures_auto_cancel", errors=errors, path="execution.execution_safety")
    _require_bool(futures_auto_cancel, "enabled", errors=errors, path="execution.execution_safety.futures_auto_cancel")
    _require_number(futures_auto_cancel, "heartbeat_sec", errors=errors, path="execution.execution_safety.futures_auto_cancel")
    _require_number(futures_auto_cancel, "countdown_ms", errors=errors, path="execution.execution_safety.futures_auto_cancel")

    margin = _require_dict(root, "margin", errors=errors, path="execution.execution_safety")
    _require_bool(margin, "require_margin_level_visible", errors=errors, path="execution.execution_safety.margin")
    _require_number(margin, "warn_margin_level_below", errors=errors, path="execution.execution_safety.margin")
    _require_number(margin, "block_margin_level_below", errors=errors, path="execution.execution_safety.margin")

    risk_reduce_only_priority = _require_dict(root, "risk_reduce_only_priority", errors=errors, path="execution.execution_safety")
    _require_bool(
        risk_reduce_only_priority,
        "enabled",
        errors=errors,
        path="execution.execution_safety.risk_reduce_only_priority",
    )

    persistence = _require_dict(root, "persistence", errors=errors, path="execution.execution_safety")
    _require_bool(persistence, "write_intents_before_submit", errors=errors, path="execution.execution_safety.persistence")
    _require_bool(persistence, "write_raw_payloads", errors=errors, path="execution.execution_safety.persistence")
    _require_number(persistence, "keep_raw_days", errors=errors, path="execution.execution_safety.persistence")

    return errors


def _validate_execution_router_policy(candidate: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return ["execution_router policy debe ser dict"]

    root = _require_dict(candidate, "execution_router", errors=errors, path="execution")
    families_enabled = _require_dict(root, "families_enabled", errors=errors, path="execution.execution_router")
    supported_order_types = _require_dict(root, "first_iteration_supported_order_types", errors=errors, path="execution.execution_router")
    time_in_force_allowed = _require_dict(root, "time_in_force_allowed", errors=errors, path="execution.execution_router")

    for family in ("spot", "margin", "usdm_futures", "coinm_futures"):
        _require_bool(families_enabled, family, errors=errors, path="execution.execution_router.families_enabled")
        _require_str_list(
            supported_order_types,
            family,
            errors=errors,
            path="execution.execution_router.first_iteration_supported_order_types",
        )
        _require_str_list(
            time_in_force_allowed,
            family,
            errors=errors,
            path="execution.execution_router.time_in_force_allowed",
        )

    _require_bool(root, "prefer_cancel_replace_spot", errors=errors, path="execution.execution_router")
    _require_bool(root, "enable_batch_orders_usdm", errors=errors, path="execution.execution_router")
    _require_bool(root, "enable_batch_orders_coinm", errors=errors, path="execution.execution_router")
    _require_bool(root, "conditional_orders_phase1", errors=errors, path="execution.execution_router")
    return errors


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _ms_to_iso(value: Any) -> str | None:
    numeric = _first_number(value)
    if numeric is None:
        return None
    try:
        return datetime.fromtimestamp(float(numeric) / 1000.0, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _iso_plus_seconds(value: Any, seconds: float) -> str | None:
    parsed = _parse_ts(value)
    if parsed is None:
        return None
    try:
        return (parsed + timedelta(seconds=float(seconds or 0.0))).isoformat()
    except Exception:
        return None


def _canonical_symbol(value: Any) -> str:
    return str(value or "").replace("/", "").replace("-", "").strip().upper()


def _normalize_family(value: Any) -> str:
    text = str(value or "").strip().lower()
    allowed = {"spot", "margin", "usdm_futures", "coinm_futures"}
    return text if text in allowed else ""


def _normalize_environment(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"live", "testnet", "paper"} else "live"


def _normalize_mode(value: Any, environment: str | None = None) -> str:
    text = str(value or "").strip().lower()
    if text in {"live", "testnet", "paper", "shadow"}:
        return text
    env = _normalize_environment(environment or "")
    if env == "testnet":
        return "testnet"
    if env == "live":
        return "live"
    return "paper"


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
    return _first_env_pair(mapping.get((_normalize_family(family), _normalize_environment(environment)), []))


def _decimal_floor(value: Any, step: Any) -> float:
    numeric = Decimal(str(_safe_float(value, 0.0)))
    step_dec = Decimal(str(_safe_float(step, 0.0)))
    if step_dec <= 0:
        return float(numeric)
    units = (numeric / step_dec).to_integral_value(rounding=ROUND_DOWN)
    return float(units * step_dec)


def clear_execution_policy_cache() -> None:
    _load_policy_bundle_cached.cache_clear()


@lru_cache(maxsize=16)
def _load_policy_bundle_cached(
    filename: str,
    repo_root_str: str,
    explicit_root_str: str,
) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    resolution = describe_policy_root_resolution(
        repo_root,
        explicit=explicit_root,
        expected_files=POLICY_EXPECTED_FILES,
    )
    selected_root = Path(resolution["selected_root"]).resolve()
    policy_path = (selected_root / filename).resolve()

    if filename == EXECUTION_SAFETY_FILENAME:
        fallback_policy = FAIL_CLOSED_MINIMAL_EXECUTION_SAFETY_POLICY
        validator = _validate_execution_safety_policy
    elif filename == EXECUTION_ROUTER_FILENAME:
        fallback_policy = FAIL_CLOSED_MINIMAL_EXECUTION_ROUTER_POLICY
        validator = _validate_execution_router_policy
    else:
        raise ValueError(f"execution policy filename no soportado: {filename}")

    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    errors: list[str] = []
    warnings: list[str] = list(resolution.get("warnings") or [])
    if policy_path.exists():
        try:
            raw_bytes = policy_path.read_bytes()
            raw_text = raw_bytes.decode("utf-8")
            source_hash = _sha256_bytes(raw_bytes)
            raw = yaml.safe_load(raw_text) or {}
            validation_errors = validator(raw) if isinstance(raw, dict) and raw else [f"{filename} vacio o ausente"]
            if isinstance(raw, dict) and raw and not validation_errors:
                payload = raw
                valid = True
            else:
                errors.extend(validation_errors)
        except Exception:
            payload = {}
            valid = False
            errors.append(f"{filename} no pudo parsearse como YAML valido")
    else:
        errors.append(f"{filename} no existe en la raiz seleccionada")

    active_policy = copy.deepcopy(payload if valid else fallback_policy)
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
        "source": _execution_policy_source_label(repo_root, policy_path) if valid else "default_fail_closed_minimal",
        "errors": errors,
        "warnings": warnings,
        "payload": active_policy,
    }


def _load_policy_bundle(
    filename: str,
    repo_root: Path | None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(_load_policy_bundle_cached(filename, str(resolved_repo_root), explicit_root_str))


def load_execution_safety_bundle(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    return _load_policy_bundle(EXECUTION_SAFETY_FILENAME, repo_root, explicit_root=explicit_root)


def load_execution_router_bundle(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    return _load_policy_bundle(EXECUTION_ROUTER_FILENAME, repo_root, explicit_root=explicit_root)


def execution_safety_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_execution_safety_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("payload")
    return copy.deepcopy(payload if isinstance(payload, dict) else FAIL_CLOSED_MINIMAL_EXECUTION_SAFETY_POLICY)


def execution_router_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_execution_router_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("payload")
    return copy.deepcopy(payload if isinstance(payload, dict) else FAIL_CLOSED_MINIMAL_EXECUTION_ROUTER_POLICY)


class ExecutionRealityDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
        if column_name in self._table_columns(conn, table_name):
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_intents (
                  execution_intent_id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  submitted_at TEXT,
                  venue TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  mode TEXT NOT NULL,
                  strategy_id TEXT,
                  bot_id TEXT,
                  signal_id TEXT,
                  symbol TEXT NOT NULL,
                  side TEXT NOT NULL,
                  order_type TEXT NOT NULL,
                  time_in_force TEXT,
                  quantity REAL,
                  quote_quantity REAL,
                  limit_price REAL,
                  stop_price REAL,
                  reduce_only INTEGER,
                  client_order_id TEXT NOT NULL,
                  requested_notional REAL,
                  estimated_fee REAL,
                  estimated_slippage_bps REAL,
                  estimated_total_cost REAL,
                  preflight_status TEXT NOT NULL,
                  preflight_errors_json TEXT NOT NULL DEFAULT '[]',
                  policy_hash TEXT NOT NULL,
                  snapshot_id TEXT,
                  capability_snapshot_id TEXT,
                  raw_request_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_execution_intents_created_at ON execution_intents(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_execution_intents_family_symbol
                  ON execution_intents(family, environment, symbol, created_at DESC);

                CREATE TABLE IF NOT EXISTS execution_orders (
                  execution_order_id TEXT PRIMARY KEY,
                  execution_intent_id TEXT NOT NULL,
                  exchange TEXT NOT NULL DEFAULT 'binance',
                  market_type TEXT,
                  strategy_id TEXT,
                  bot_id TEXT,
                  signal_id TEXT,
                  venue_order_id TEXT,
                  client_order_id TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  requested_qty REAL,
                  requested_quote_order_qty REAL,
                  requested_price REAL,
                  requested_stop_price REAL,
                  requested_trailing_delta REAL,
                  requested_stp_mode TEXT,
                  requested_new_order_resp_type TEXT,
                  order_list_id TEXT,
                  parent_local_order_id TEXT,
                  current_local_state TEXT,
                  last_exchange_order_status TEXT,
                  last_execution_type TEXT,
                  last_reject_reason TEXT,
                  last_expiry_reason TEXT,
                  order_status TEXT NOT NULL,
                  execution_type_last TEXT,
                  submitted_at TEXT NOT NULL,
                  first_submitted_at TEXT,
                  acknowledged_at TEXT,
                  canceled_at TEXT,
                  expired_at TEXT,
                  reduce_only INTEGER,
                  tif TEXT,
                  price REAL,
                  orig_qty REAL,
                  executed_qty REAL,
                  cum_quote_qty REAL,
                  avg_fill_price REAL,
                  last_fill_qty REAL,
                  last_fill_price REAL,
                  commission_total REAL,
                  commission_asset_last TEXT,
                  working_time TEXT,
                  transact_time_last TEXT,
                  last_event_at TEXT,
                  terminal_at TEXT,
                  reconciliation_status TEXT,
                  unresolved_reason TEXT,
                  reject_code TEXT,
                  reject_reason TEXT,
                  raw_ack_json TEXT NOT NULL DEFAULT '{}',
                  raw_last_status_json TEXT NOT NULL DEFAULT '{}',
                  raw_last_payload_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_execution_orders_submitted_at ON execution_orders(submitted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_execution_orders_status ON execution_orders(order_status, family, environment);
                CREATE INDEX IF NOT EXISTS idx_execution_orders_local_state ON execution_orders(current_local_state, family, environment, symbol);

                CREATE TABLE IF NOT EXISTS execution_fills (
                  execution_fill_id TEXT PRIMARY KEY,
                  execution_order_id TEXT NOT NULL,
                  local_order_id TEXT,
                  exchange TEXT NOT NULL DEFAULT 'binance',
                  market_type TEXT,
                  environment TEXT NOT NULL DEFAULT 'paper',
                  side TEXT,
                  client_order_id TEXT,
                  exchange_order_id TEXT,
                  trade_id TEXT,
                  execution_id TEXT,
                  venue_trade_id TEXT,
                  fill_time TEXT NOT NULL,
                  event_time_exchange TEXT,
                  event_time_local TEXT,
                  symbol TEXT NOT NULL,
                  family TEXT NOT NULL,
                  last_executed_qty REAL,
                  last_executed_price REAL,
                  last_quote_qty REAL,
                  cumulative_filled_qty_after REAL,
                  cumulative_quote_qty_after REAL,
                  price REAL NOT NULL,
                  qty REAL NOT NULL,
                  quote_qty REAL,
                  commission REAL NOT NULL DEFAULT 0.0,
                  commission_asset TEXT,
                  realized_pnl REAL,
                  maker INTEGER,
                  self_trade_prevention_mode TEXT,
                  prevented_match_id TEXT,
                  raw_source_type TEXT NOT NULL DEFAULT 'UNKNOWN',
                  dedup_key TEXT,
                  reconciliation_status TEXT NOT NULL DEFAULT 'PENDING',
                  discrepancy_json TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT,
                  updated_at TEXT,
                  funding_component REAL,
                  borrow_interest_component REAL,
                  spread_realized REAL,
                  slippage_realized REAL,
                  gross_pnl REAL,
                  net_pnl REAL,
                  cost_source_json TEXT NOT NULL DEFAULT '{}',
                  provenance_json TEXT NOT NULL DEFAULT '{}',
                  provisional INTEGER NOT NULL DEFAULT 0,
                  unresolved_components_json TEXT NOT NULL DEFAULT '[]',
                  raw_fill_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_execution_fills_fill_time ON execution_fills(fill_time DESC);
                CREATE INDEX IF NOT EXISTS idx_execution_fills_trade ON execution_fills(execution_order_id, venue_trade_id);
                CREATE INDEX IF NOT EXISTS idx_execution_fills_symbol_status ON execution_fills(symbol, family, environment, fill_time DESC);
                CREATE INDEX IF NOT EXISTS idx_execution_fills_trade_ids ON execution_fills(trade_id, execution_id);
                CREATE INDEX IF NOT EXISTS idx_execution_fills_reconciliation_status ON execution_fills(reconciliation_status, fill_time DESC);

                CREATE TABLE IF NOT EXISTS execution_reconcile_events (
                  reconcile_event_id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  reconcile_type TEXT NOT NULL,
                  severity TEXT NOT NULL,
                  execution_order_id TEXT,
                  client_order_id TEXT,
                  details_json TEXT NOT NULL DEFAULT '{}',
                  resolved INTEGER NOT NULL DEFAULT 0,
                  resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_execution_reconcile_open
                  ON execution_reconcile_events(resolved, severity, created_at DESC);

                CREATE TABLE IF NOT EXISTS execution_user_stream_events (
                  user_stream_event_id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  event_time TEXT,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  execution_connector TEXT,
                  user_stream_mode TEXT,
                  subscription_id TEXT,
                  listen_key TEXT,
                  event_name TEXT NOT NULL,
                  symbol TEXT,
                  client_order_id TEXT,
                  venue_order_id TEXT,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  provenance_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_execution_user_stream_events_created_at
                  ON execution_user_stream_events(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_execution_user_stream_events_lookup
                  ON execution_user_stream_events(family, environment, event_name, created_at DESC);

                CREATE TABLE IF NOT EXISTS live_order_events (
                  event_id TEXT PRIMARY KEY,
                  execution_order_id TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  source_seq INTEGER NOT NULL,
                  exchange_execution_id TEXT,
                  exchange_order_id TEXT,
                  client_order_id TEXT,
                  event_time_exchange TEXT,
                  event_time_local TEXT NOT NULL,
                  local_state_before TEXT,
                  local_state_after TEXT NOT NULL,
                  exchange_order_status TEXT,
                  execution_type TEXT,
                  reject_reason TEXT,
                  expiry_reason TEXT,
                  delta_filled_qty REAL,
                  cumulative_filled_qty REAL,
                  cumulative_quote_qty REAL,
                  price REAL,
                  raw_payload_json TEXT NOT NULL DEFAULT '{}',
                  dedup_key TEXT NOT NULL,
                  applied_bool INTEGER NOT NULL DEFAULT 1,
                  notes TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_live_order_events_order_time
                  ON live_order_events(execution_order_id, event_time_local ASC, source_seq ASC);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_live_order_events_dedup ON live_order_events(dedup_key);

                CREATE TABLE IF NOT EXISTS live_order_reconciliation_runs (
                  reconciliation_run_id TEXT PRIMARY KEY,
                  started_at TEXT NOT NULL,
                  finished_at TEXT,
                  trigger TEXT NOT NULL,
                  family TEXT,
                  environment TEXT,
                  symbol TEXT,
                  bot_id TEXT,
                  result_summary_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_live_order_reconciliation_runs_started_at
                  ON live_order_reconciliation_runs(started_at DESC);

                CREATE TABLE IF NOT EXISTS reconciliation_cases (
                  reconciliation_case_id TEXT PRIMARY KEY,
                  trigger_type TEXT NOT NULL,
                  exchange TEXT NOT NULL DEFAULT 'binance',
                  market_type TEXT,
                  environment TEXT NOT NULL DEFAULT 'live',
                  bot_id TEXT,
                  symbol TEXT,
                  execution_order_id TEXT,
                  execution_fill_scope TEXT,
                  started_at TEXT NOT NULL,
                  finished_at TEXT,
                  final_status TEXT NOT NULL,
                  severity TEXT NOT NULL,
                  local_summary_json TEXT NOT NULL DEFAULT '{}',
                  remote_summary_json TEXT NOT NULL DEFAULT '{}',
                  discrepancy_summary_json TEXT NOT NULL DEFAULT '{}',
                  resolution_summary_json TEXT NOT NULL DEFAULT '{}',
                  blocking_bool INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_reconciliation_cases_started_at
                  ON reconciliation_cases(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_reconciliation_cases_status
                  ON reconciliation_cases(final_status, severity, blocking_bool, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_reconciliation_cases_scope
                  ON reconciliation_cases(environment, market_type, symbol, execution_order_id, started_at DESC);

                CREATE TABLE IF NOT EXISTS reconciliation_case_events (
                  case_event_id TEXT PRIMARY KEY,
                  reconciliation_case_id TEXT NOT NULL,
                  event_time TEXT NOT NULL,
                  source_type TEXT NOT NULL,
                  message TEXT NOT NULL,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  decision_json TEXT NOT NULL DEFAULT '{}',
                  applied_bool INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_reconciliation_case_events_case_time
                  ON reconciliation_case_events(reconciliation_case_id, event_time ASC, case_event_id ASC);

                CREATE TABLE IF NOT EXISTS reconciliation_snapshots (
                  snapshot_id TEXT PRIMARY KEY,
                  reconciliation_case_id TEXT NOT NULL,
                  snapshot_type TEXT NOT NULL,
                  symbol TEXT,
                  execution_order_id TEXT,
                  captured_at TEXT NOT NULL,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  source_freshness_ms REAL
                );
                CREATE INDEX IF NOT EXISTS idx_reconciliation_snapshots_case
                  ON reconciliation_snapshots(reconciliation_case_id, captured_at ASC, snapshot_id ASC);
                CREATE INDEX IF NOT EXISTS idx_reconciliation_snapshots_scope
                  ON reconciliation_snapshots(snapshot_type, symbol, execution_order_id, captured_at DESC);

                CREATE TABLE IF NOT EXISTS kill_switch_events (
                  kill_switch_event_id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  trigger_type TEXT NOT NULL,
                  severity TEXT NOT NULL,
                  family TEXT,
                  symbol TEXT,
                  reason TEXT NOT NULL,
                  auto_actions_json TEXT NOT NULL DEFAULT '[]',
                  cleared_at TEXT,
                  cleared_reason TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_kill_switch_events_created_at ON kill_switch_events(created_at DESC);
                """
            )
            self._ensure_column(conn, "execution_fills", "spread_realized", "REAL")
            self._ensure_column(conn, "execution_fills", "slippage_realized", "REAL")
            self._ensure_column(conn, "execution_fills", "gross_pnl", "REAL")
            self._ensure_column(conn, "execution_fills", "net_pnl", "REAL")
            self._ensure_column(conn, "execution_fills", "cost_source_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "execution_fills", "provenance_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "execution_fills", "provisional", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "execution_fills", "unresolved_components_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "execution_fills", "local_order_id", "TEXT")
            self._ensure_column(conn, "execution_fills", "exchange", "TEXT NOT NULL DEFAULT 'binance'")
            self._ensure_column(conn, "execution_fills", "market_type", "TEXT")
            self._ensure_column(conn, "execution_fills", "environment", "TEXT NOT NULL DEFAULT 'paper'")
            self._ensure_column(conn, "execution_fills", "side", "TEXT")
            self._ensure_column(conn, "execution_fills", "client_order_id", "TEXT")
            self._ensure_column(conn, "execution_fills", "exchange_order_id", "TEXT")
            self._ensure_column(conn, "execution_fills", "trade_id", "TEXT")
            self._ensure_column(conn, "execution_fills", "execution_id", "TEXT")
            self._ensure_column(conn, "execution_fills", "event_time_exchange", "TEXT")
            self._ensure_column(conn, "execution_fills", "event_time_local", "TEXT")
            self._ensure_column(conn, "execution_fills", "last_executed_qty", "REAL")
            self._ensure_column(conn, "execution_fills", "last_executed_price", "REAL")
            self._ensure_column(conn, "execution_fills", "last_quote_qty", "REAL")
            self._ensure_column(conn, "execution_fills", "cumulative_filled_qty_after", "REAL")
            self._ensure_column(conn, "execution_fills", "cumulative_quote_qty_after", "REAL")
            self._ensure_column(conn, "execution_fills", "self_trade_prevention_mode", "TEXT")
            self._ensure_column(conn, "execution_fills", "prevented_match_id", "TEXT")
            self._ensure_column(conn, "execution_fills", "raw_source_type", "TEXT NOT NULL DEFAULT 'UNKNOWN'")
            self._ensure_column(conn, "execution_fills", "dedup_key", "TEXT")
            self._ensure_column(conn, "execution_fills", "reconciliation_status", "TEXT NOT NULL DEFAULT 'PENDING'")
            self._ensure_column(conn, "execution_fills", "discrepancy_json", "TEXT NOT NULL DEFAULT '{}'")
            self._ensure_column(conn, "execution_fills", "created_at", "TEXT")
            self._ensure_column(conn, "execution_fills", "updated_at", "TEXT")
            self._ensure_column(conn, "kill_switch_events", "cleared_reason", "TEXT")
            self._ensure_column(conn, "execution_orders", "exchange", "TEXT NOT NULL DEFAULT 'binance'")
            self._ensure_column(conn, "execution_orders", "market_type", "TEXT")
            self._ensure_column(conn, "execution_orders", "strategy_id", "TEXT")
            self._ensure_column(conn, "execution_orders", "bot_id", "TEXT")
            self._ensure_column(conn, "execution_orders", "signal_id", "TEXT")
            self._ensure_column(conn, "execution_orders", "requested_qty", "REAL")
            self._ensure_column(conn, "execution_orders", "requested_quote_order_qty", "REAL")
            self._ensure_column(conn, "execution_orders", "requested_price", "REAL")
            self._ensure_column(conn, "execution_orders", "requested_stop_price", "REAL")
            self._ensure_column(conn, "execution_orders", "requested_trailing_delta", "REAL")
            self._ensure_column(conn, "execution_orders", "requested_stp_mode", "TEXT")
            self._ensure_column(conn, "execution_orders", "requested_new_order_resp_type", "TEXT")
            self._ensure_column(conn, "execution_orders", "order_list_id", "TEXT")
            self._ensure_column(conn, "execution_orders", "parent_local_order_id", "TEXT")
            self._ensure_column(conn, "execution_orders", "current_local_state", "TEXT")
            self._ensure_column(conn, "execution_orders", "last_exchange_order_status", "TEXT")
            self._ensure_column(conn, "execution_orders", "last_execution_type", "TEXT")
            self._ensure_column(conn, "execution_orders", "last_reject_reason", "TEXT")
            self._ensure_column(conn, "execution_orders", "last_expiry_reason", "TEXT")
            self._ensure_column(conn, "execution_orders", "first_submitted_at", "TEXT")
            self._ensure_column(conn, "execution_orders", "last_fill_qty", "REAL")
            self._ensure_column(conn, "execution_orders", "last_fill_price", "REAL")
            self._ensure_column(conn, "execution_orders", "commission_total", "REAL")
            self._ensure_column(conn, "execution_orders", "commission_asset_last", "TEXT")
            self._ensure_column(conn, "execution_orders", "working_time", "TEXT")
            self._ensure_column(conn, "execution_orders", "transact_time_last", "TEXT")
            self._ensure_column(conn, "execution_orders", "last_event_at", "TEXT")
            self._ensure_column(conn, "execution_orders", "terminal_at", "TEXT")
            self._ensure_column(conn, "execution_orders", "reconciliation_status", "TEXT")
            self._ensure_column(conn, "execution_orders", "unresolved_reason", "TEXT")
            self._ensure_column(conn, "execution_orders", "raw_last_payload_json", "TEXT NOT NULL DEFAULT '{}'")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_execution_orders_local_state ON execution_orders(current_local_state, family, environment, symbol)"
            )
            self._ensure_column(conn, "reconciliation_cases", "exchange", "TEXT NOT NULL DEFAULT 'binance'")
            self._ensure_column(conn, "reconciliation_cases", "market_type", "TEXT")
            self._ensure_column(conn, "reconciliation_cases", "environment", "TEXT NOT NULL DEFAULT 'live'")
            self._ensure_column(conn, "reconciliation_cases", "execution_fill_scope", "TEXT")
            self._ensure_column(conn, "reconciliation_cases", "created_at", "TEXT")
            self._ensure_column(conn, "reconciliation_cases", "updated_at", "TEXT")
            self._ensure_column(conn, "reconciliation_cases", "blocking_bool", "INTEGER NOT NULL DEFAULT 0")

    def table_names(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [str(row["name"]) for row in rows]

    def counts(self) -> dict[str, int]:
        tables = (
            "execution_intents",
            "execution_orders",
            "execution_fills",
            "execution_reconcile_events",
            "execution_user_stream_events",
            "live_order_events",
            "live_order_reconciliation_runs",
            "reconciliation_cases",
            "reconciliation_case_events",
            "reconciliation_snapshots",
            "kill_switch_events",
        )
        with self._connect() as conn:
            return {table: int(conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]) for table in tables}

    def list_intents(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        preflight_status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if family:
            clauses.append("family = ?")
            params.append(_normalize_family(family))
        if environment:
            clauses.append("environment = ?")
            params.append(_normalize_environment(environment))
        if preflight_status:
            clauses.append("preflight_status = ?")
            params.append(str(preflight_status))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM execution_intents
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, execution_intent_id DESC
                LIMIT ? OFFSET ?
                """,
                tuple([*params, int(limit), int(offset)]),
            ).fetchall()
        return [_hydrate_intent_row(_row_to_dict(row)) or {} for row in rows]

    def open_orders(self, *, family: str | None = None, symbol: str | None = None) -> list[dict[str, Any]]:
        clauses = [f"order_status NOT IN ({', '.join(repr(status) for status in sorted(TERMINAL_ORDER_STATUSES))})"]
        params: list[Any] = []
        if family:
            clauses.append("family = ?")
            params.append(str(family))
        if symbol:
            clauses.append("symbol = ?")
            params.append(_canonical_symbol(symbol))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM execution_orders
                WHERE {' AND '.join(clauses)}
                ORDER BY submitted_at DESC, execution_order_id DESC
                """,
                tuple(params),
            ).fetchall()
        return [_hydrate_order_row(_row_to_dict(row)) or {} for row in rows]

    def list_orders(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
        strategy_id: str | None = None,
        bot_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if family:
            clauses.append("o.family = ?")
            params.append(_normalize_family(family))
        if environment:
            clauses.append("o.environment = ?")
            params.append(_normalize_environment(environment))
        if symbol:
            clauses.append("o.symbol = ?")
            params.append(_canonical_symbol(symbol))
        if strategy_id:
            clauses.append("i.strategy_id = ?")
            params.append(str(strategy_id))
        if bot_id:
            clauses.append("i.bot_id = ?")
            params.append(str(bot_id))
        normalized_status = str(status or "").strip().upper()
        if normalized_status:
            if normalized_status == "OPEN":
                clauses.append(f"o.order_status NOT IN ({', '.join(repr(item) for item in sorted(TERMINAL_ORDER_STATUSES))})")
            else:
                clauses.append("o.order_status = ?")
                params.append(normalized_status)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                  o.*,
                  i.mode,
                  i.strategy_id,
                  i.bot_id,
                  i.signal_id,
                  i.venue,
                  i.requested_notional,
                  i.estimated_fee,
                  i.estimated_slippage_bps,
                  i.estimated_total_cost
                FROM execution_orders AS o
                LEFT JOIN execution_intents AS i
                  ON i.execution_intent_id = o.execution_intent_id
                WHERE {' AND '.join(clauses)}
                ORDER BY o.submitted_at DESC, o.execution_order_id DESC
                LIMIT ? OFFSET ?
                """,
                tuple([*params, int(limit), int(offset)]),
            ).fetchall()
        return [_hydrate_order_row(_row_to_dict(row)) or {} for row in rows]

    def intent_by_id(self, execution_intent_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_intents WHERE execution_intent_id = ?",
                (str(execution_intent_id),),
            ).fetchone()
        return _hydrate_intent_row(_row_to_dict(row))

    def update_intent_submission(
        self,
        execution_intent_id: str,
        *,
        submitted_at: str | None = None,
        preflight_status: str | None = None,
        preflight_errors_json: list[str] | None = None,
    ) -> dict[str, Any] | None:
        assignments: list[str] = []
        params: list[Any] = []
        if submitted_at is not None:
            assignments.append("submitted_at = ?")
            params.append(str(submitted_at))
        if preflight_status is not None:
            assignments.append("preflight_status = ?")
            params.append(str(preflight_status))
        if preflight_errors_json is not None:
            assignments.append("preflight_errors_json = ?")
            params.append(_json_dumps(preflight_errors_json))
        if not assignments:
            return self.intent_by_id(execution_intent_id)
        params.append(str(execution_intent_id))
        with self._connect() as conn:
            conn.execute(
                f"UPDATE execution_intents SET {', '.join(assignments)} WHERE execution_intent_id = ?",
                tuple(params),
            )
            row = conn.execute(
                "SELECT * FROM execution_intents WHERE execution_intent_id = ?",
                (str(execution_intent_id),),
            ).fetchone()
        return _hydrate_intent_row(_row_to_dict(row))

    def order_by_id(self, execution_order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_orders WHERE execution_order_id = ?",
                (str(execution_order_id),),
            ).fetchone()
        return _hydrate_order_row(_row_to_dict(row))

    def order_by_client_order_id(self, client_order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_orders WHERE client_order_id = ? ORDER BY submitted_at DESC LIMIT 1",
                (str(client_order_id),),
            ).fetchone()
        return _hydrate_order_row(_row_to_dict(row))

    def order_by_venue_order_id(self, venue_order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_orders WHERE venue_order_id = ? ORDER BY submitted_at DESC LIMIT 1",
                (str(venue_order_id),),
            ).fetchone()
        return _hydrate_order_row(_row_to_dict(row))

    def insert_intent(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "execution_intent_id": str(payload.get("execution_intent_id") or uuid4()),
            "created_at": str(payload.get("created_at") or utc_now_iso()),
            "submitted_at": payload.get("submitted_at"),
            "venue": str(payload.get("venue") or "binance"),
            "family": str(payload.get("family") or ""),
            "environment": str(payload.get("environment") or ""),
            "mode": str(payload.get("mode") or "paper"),
            "strategy_id": payload.get("strategy_id"),
            "bot_id": payload.get("bot_id"),
            "signal_id": payload.get("signal_id"),
            "symbol": str(payload.get("symbol") or ""),
            "side": str(payload.get("side") or ""),
            "order_type": str(payload.get("order_type") or ""),
            "time_in_force": payload.get("time_in_force"),
            "quantity": payload.get("quantity"),
            "quote_quantity": payload.get("quote_quantity"),
            "limit_price": payload.get("limit_price"),
            "stop_price": payload.get("stop_price"),
            "reduce_only": _db_bool(payload.get("reduce_only")),
            "client_order_id": str(payload.get("client_order_id") or uuid4().hex[:24]),
            "requested_notional": payload.get("requested_notional"),
            "estimated_fee": payload.get("estimated_fee"),
            "estimated_slippage_bps": payload.get("estimated_slippage_bps"),
            "estimated_total_cost": payload.get("estimated_total_cost"),
            "preflight_status": str(payload.get("preflight_status") or "pending"),
            "preflight_errors_json": _json_dumps(payload.get("preflight_errors_json") or []),
            "policy_hash": str(payload.get("policy_hash") or ""),
            "snapshot_id": payload.get("snapshot_id"),
            "capability_snapshot_id": payload.get("capability_snapshot_id"),
            "raw_request_json": _json_dumps(payload.get("raw_request_json") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_intents (
                  execution_intent_id, created_at, submitted_at, venue, family, environment, mode,
                  strategy_id, bot_id, signal_id, symbol, side, order_type, time_in_force,
                  quantity, quote_quantity, limit_price, stop_price, reduce_only, client_order_id,
                  requested_notional, estimated_fee, estimated_slippage_bps, estimated_total_cost,
                  preflight_status, preflight_errors_json, policy_hash, snapshot_id, capability_snapshot_id, raw_request_json
                ) VALUES (
                  :execution_intent_id, :created_at, :submitted_at, :venue, :family, :environment, :mode,
                  :strategy_id, :bot_id, :signal_id, :symbol, :side, :order_type, :time_in_force,
                  :quantity, :quote_quantity, :limit_price, :stop_price, :reduce_only, :client_order_id,
                  :requested_notional, :estimated_fee, :estimated_slippage_bps, :estimated_total_cost,
                  :preflight_status, :preflight_errors_json, :policy_hash, :snapshot_id, :capability_snapshot_id, :raw_request_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM execution_intents WHERE execution_intent_id = ?",
                (row["execution_intent_id"],),
            ).fetchone()
        return _hydrate_intent_row(_row_to_dict(stored) or row) or row

    def upsert_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "execution_order_id": str(payload.get("execution_order_id") or uuid4()),
            "execution_intent_id": str(payload.get("execution_intent_id") or ""),
            "exchange": str(payload.get("exchange") or "binance"),
            "market_type": payload.get("market_type"),
            "strategy_id": payload.get("strategy_id"),
            "bot_id": payload.get("bot_id"),
            "signal_id": payload.get("signal_id"),
            "venue_order_id": payload.get("venue_order_id"),
            "client_order_id": str(payload.get("client_order_id") or uuid4().hex[:24]),
            "symbol": str(payload.get("symbol") or ""),
            "family": str(payload.get("family") or ""),
            "environment": str(payload.get("environment") or ""),
            "requested_qty": payload.get("requested_qty"),
            "requested_quote_order_qty": payload.get("requested_quote_order_qty"),
            "requested_price": payload.get("requested_price"),
            "requested_stop_price": payload.get("requested_stop_price"),
            "requested_trailing_delta": payload.get("requested_trailing_delta"),
            "requested_stp_mode": payload.get("requested_stp_mode"),
            "requested_new_order_resp_type": payload.get("requested_new_order_resp_type"),
            "order_list_id": payload.get("order_list_id"),
            "parent_local_order_id": payload.get("parent_local_order_id"),
            "current_local_state": normalize_local_state(
                payload.get("current_local_state")
                or (
                    "FILLED"
                    if str(payload.get("order_status") or "").upper() == "FILLED"
                    else "CANCELED"
                    if str(payload.get("order_status") or "").upper() == "CANCELED"
                    else "REJECTED"
                    if str(payload.get("order_status") or "").upper() == "REJECTED"
                    else "EXPIRED_STP"
                    if str(payload.get("order_status") or "").upper() == "EXPIRED_IN_MATCH"
                    else "EXPIRED"
                    if str(payload.get("order_status") or "").upper() == "EXPIRED"
                    else "WORKING"
                    if str(payload.get("order_status") or "").upper() in {"NEW", "PARTIALLY_FILLED"}
                    else "INTENT_CREATED"
                )
            ),
            "last_exchange_order_status": payload.get("last_exchange_order_status"),
            "last_execution_type": payload.get("last_execution_type"),
            "last_reject_reason": payload.get("last_reject_reason"),
            "last_expiry_reason": payload.get("last_expiry_reason"),
            "order_status": str(payload.get("order_status") or "CREATED"),
            "execution_type_last": payload.get("execution_type_last"),
            "submitted_at": str(payload.get("submitted_at") or utc_now_iso()),
            "first_submitted_at": payload.get("first_submitted_at") or payload.get("submitted_at") or utc_now_iso(),
            "acknowledged_at": payload.get("acknowledged_at"),
            "canceled_at": payload.get("canceled_at"),
            "expired_at": payload.get("expired_at"),
            "reduce_only": _db_bool(payload.get("reduce_only")),
            "tif": payload.get("tif"),
            "price": payload.get("price"),
            "orig_qty": payload.get("orig_qty"),
            "executed_qty": payload.get("executed_qty"),
            "cum_quote_qty": payload.get("cum_quote_qty"),
            "avg_fill_price": payload.get("avg_fill_price"),
            "last_fill_qty": payload.get("last_fill_qty"),
            "last_fill_price": payload.get("last_fill_price"),
            "commission_total": payload.get("commission_total"),
            "commission_asset_last": payload.get("commission_asset_last"),
            "working_time": payload.get("working_time"),
            "transact_time_last": payload.get("transact_time_last"),
            "last_event_at": payload.get("last_event_at") or payload.get("acknowledged_at") or payload.get("submitted_at") or utc_now_iso(),
            "terminal_at": payload.get("terminal_at"),
            "reconciliation_status": payload.get("reconciliation_status") or "PENDING",
            "unresolved_reason": payload.get("unresolved_reason"),
            "reject_code": payload.get("reject_code"),
            "reject_reason": payload.get("reject_reason"),
            "raw_ack_json": _json_dumps(payload.get("raw_ack_json") or {}),
            "raw_last_status_json": _json_dumps(payload.get("raw_last_status_json") or {}),
            "raw_last_payload_json": _json_dumps(payload.get("raw_last_payload_json") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_orders (
                  execution_order_id, execution_intent_id, exchange, market_type, strategy_id, bot_id, signal_id,
                  venue_order_id, client_order_id, symbol, family, environment, requested_qty, requested_quote_order_qty,
                  requested_price, requested_stop_price, requested_trailing_delta, requested_stp_mode,
                  requested_new_order_resp_type, order_list_id, parent_local_order_id, current_local_state,
                  last_exchange_order_status, last_execution_type, last_reject_reason, last_expiry_reason,
                  order_status, execution_type_last, submitted_at, first_submitted_at, acknowledged_at, canceled_at,
                  expired_at, reduce_only, tif, price, orig_qty, executed_qty, cum_quote_qty, avg_fill_price,
                  last_fill_qty, last_fill_price, commission_total, commission_asset_last, working_time,
                  transact_time_last, last_event_at, terminal_at, reconciliation_status, unresolved_reason,
                  reject_code, reject_reason, raw_ack_json, raw_last_status_json, raw_last_payload_json
                ) VALUES (
                  :execution_order_id, :execution_intent_id, :exchange, :market_type, :strategy_id, :bot_id, :signal_id,
                  :venue_order_id, :client_order_id, :symbol, :family, :environment, :requested_qty, :requested_quote_order_qty,
                  :requested_price, :requested_stop_price, :requested_trailing_delta, :requested_stp_mode,
                  :requested_new_order_resp_type, :order_list_id, :parent_local_order_id, :current_local_state,
                  :last_exchange_order_status, :last_execution_type, :last_reject_reason, :last_expiry_reason,
                  :order_status, :execution_type_last, :submitted_at, :first_submitted_at, :acknowledged_at, :canceled_at,
                  :expired_at, :reduce_only, :tif, :price, :orig_qty, :executed_qty, :cum_quote_qty, :avg_fill_price,
                  :last_fill_qty, :last_fill_price, :commission_total, :commission_asset_last, :working_time,
                  :transact_time_last, :last_event_at, :terminal_at, :reconciliation_status, :unresolved_reason,
                  :reject_code, :reject_reason, :raw_ack_json, :raw_last_status_json, :raw_last_payload_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM execution_orders WHERE execution_order_id = ?",
                (row["execution_order_id"],),
            ).fetchone()
        return _hydrate_order_row(_row_to_dict(stored) or row) or row

    def update_order_fields(self, execution_order_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        if not updates:
            return self.order_by_id(execution_order_id)
        with self._connect() as column_conn:
            columns = self._table_columns(column_conn, "execution_orders")
        assignments: list[str] = []
        params: list[Any] = []
        for key, value in updates.items():
            if key not in columns:
                continue
            assignments.append(f"{key} = ?")
            if key in {"raw_ack_json", "raw_last_status_json", "raw_last_payload_json"}:
                params.append(_json_dumps(value or {}))
            elif key == "reduce_only":
                params.append(_db_bool(value))
            else:
                params.append(value)
        if not assignments:
            return self.order_by_id(execution_order_id)
        params.append(str(execution_order_id))
        with self._connect() as conn:
            conn.execute(
                f"UPDATE execution_orders SET {', '.join(assignments)} WHERE execution_order_id = ?",
                tuple(params),
            )
            stored = conn.execute(
                "SELECT * FROM execution_orders WHERE execution_order_id = ?",
                (str(execution_order_id),),
            ).fetchone()
        return _hydrate_order_row(_row_to_dict(stored))

    def insert_live_order_event(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        existing = None
        dedup_key = str(payload.get("dedup_key") or "").strip()
        if dedup_key:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM live_order_events WHERE dedup_key = ?",
                    (dedup_key,),
                ).fetchone()
            existing = _hydrate_live_order_event_row(_row_to_dict(row))
        if existing is not None:
            return existing, True
        order_id = str(payload.get("execution_order_id") or "")
        with self._connect() as conn:
            seq_row = conn.execute(
                "SELECT COALESCE(MAX(source_seq), 0) AS max_seq FROM live_order_events WHERE execution_order_id = ?",
                (order_id,),
            ).fetchone()
            row = {
                "event_id": str(payload.get("event_id") or uuid4()),
                "execution_order_id": order_id,
                "source_type": str(payload.get("source_type") or "MANUAL"),
                "source_seq": int(payload.get("source_seq") or ((seq_row["max_seq"] if seq_row else 0) + 1)),
                "exchange_execution_id": payload.get("exchange_execution_id"),
                "exchange_order_id": payload.get("exchange_order_id"),
                "client_order_id": payload.get("client_order_id"),
                "event_time_exchange": payload.get("event_time_exchange"),
                "event_time_local": str(payload.get("event_time_local") or utc_now_iso()),
                "local_state_before": payload.get("local_state_before"),
                "local_state_after": normalize_local_state(payload.get("local_state_after") or "MANUAL_REVIEW_REQUIRED"),
                "exchange_order_status": payload.get("exchange_order_status"),
                "execution_type": payload.get("execution_type"),
                "reject_reason": payload.get("reject_reason"),
                "expiry_reason": payload.get("expiry_reason"),
                "delta_filled_qty": payload.get("delta_filled_qty"),
                "cumulative_filled_qty": payload.get("cumulative_filled_qty"),
                "cumulative_quote_qty": payload.get("cumulative_quote_qty"),
                "price": payload.get("price"),
                "raw_payload_json": _json_dumps(payload.get("raw_payload_json") or {}),
                "dedup_key": dedup_key or str(uuid4()),
                "applied_bool": _db_bool(payload.get("applied_bool", True)) or 0,
                "notes": payload.get("notes"),
            }
            conn.execute(
                """
                INSERT INTO live_order_events (
                  event_id, execution_order_id, source_type, source_seq, exchange_execution_id, exchange_order_id,
                  client_order_id, event_time_exchange, event_time_local, local_state_before, local_state_after,
                  exchange_order_status, execution_type, reject_reason, expiry_reason, delta_filled_qty,
                  cumulative_filled_qty, cumulative_quote_qty, price, raw_payload_json, dedup_key, applied_bool, notes
                ) VALUES (
                  :event_id, :execution_order_id, :source_type, :source_seq, :exchange_execution_id, :exchange_order_id,
                  :client_order_id, :event_time_exchange, :event_time_local, :local_state_before, :local_state_after,
                  :exchange_order_status, :execution_type, :reject_reason, :expiry_reason, :delta_filled_qty,
                  :cumulative_filled_qty, :cumulative_quote_qty, :price, :raw_payload_json, :dedup_key, :applied_bool, :notes
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM live_order_events WHERE event_id = ?",
                (row["event_id"],),
            ).fetchone()
        return _hydrate_live_order_event_row(_row_to_dict(stored) or row) or row, False

    def live_order_events_for_order(self, execution_order_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM live_order_events
                WHERE execution_order_id = ?
                ORDER BY event_time_local ASC, source_seq ASC, event_id ASC
                """,
                (str(execution_order_id),),
            ).fetchall()
        return [_hydrate_live_order_event_row(_row_to_dict(row)) or {} for row in rows]

    def insert_live_order_reconciliation_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "reconciliation_run_id": str(payload.get("reconciliation_run_id") or uuid4()),
            "started_at": str(payload.get("started_at") or utc_now_iso()),
            "finished_at": payload.get("finished_at"),
            "trigger": str(payload.get("trigger") or "MANUAL"),
            "family": payload.get("family"),
            "environment": payload.get("environment"),
            "symbol": payload.get("symbol"),
            "bot_id": payload.get("bot_id"),
            "result_summary_json": _json_dumps(payload.get("result_summary_json") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO live_order_reconciliation_runs (
                  reconciliation_run_id, started_at, finished_at, trigger, family, environment, symbol, bot_id, result_summary_json
                ) VALUES (
                  :reconciliation_run_id, :started_at, :finished_at, :trigger, :family, :environment, :symbol, :bot_id, :result_summary_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM live_order_reconciliation_runs WHERE reconciliation_run_id = ?",
                (row["reconciliation_run_id"],),
            ).fetchone()
        return _hydrate_reconciliation_run_row(_row_to_dict(stored) or row) or row

    def insert_reconciliation_case(self, payload: dict[str, Any]) -> dict[str, Any]:
        now_iso = utc_now_iso()
        row = {
            "reconciliation_case_id": str(payload.get("reconciliation_case_id") or uuid4()),
            "trigger_type": normalize_reconciliation_trigger(payload.get("trigger_type")),
            "exchange": str(payload.get("exchange") or "binance"),
            "market_type": str(payload.get("market_type") or "spot"),
            "environment": str(payload.get("environment") or "live"),
            "bot_id": payload.get("bot_id"),
            "symbol": _canonical_symbol(payload.get("symbol")),
            "execution_order_id": payload.get("execution_order_id"),
            "execution_fill_scope": payload.get("execution_fill_scope"),
            "started_at": str(payload.get("started_at") or now_iso),
            "finished_at": str(payload.get("finished_at") or now_iso),
            "final_status": normalize_reconciliation_case_status(payload.get("final_status")),
            "severity": normalize_reconciliation_case_severity(payload.get("severity")),
            "local_summary_json": _json_dumps(payload.get("local_summary_json") or {}),
            "remote_summary_json": _json_dumps(payload.get("remote_summary_json") or {}),
            "discrepancy_summary_json": _json_dumps(payload.get("discrepancy_summary_json") or {}),
            "resolution_summary_json": _json_dumps(payload.get("resolution_summary_json") or {}),
            "blocking_bool": _db_bool(payload.get("blocking_bool", False)) or 0,
            "created_at": str(payload.get("created_at") or now_iso),
            "updated_at": str(payload.get("updated_at") or now_iso),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reconciliation_cases (
                  reconciliation_case_id, trigger_type, exchange, market_type, environment, bot_id, symbol,
                  execution_order_id, execution_fill_scope, started_at, finished_at, final_status, severity,
                  local_summary_json, remote_summary_json, discrepancy_summary_json, resolution_summary_json,
                  blocking_bool, created_at, updated_at
                ) VALUES (
                  :reconciliation_case_id, :trigger_type, :exchange, :market_type, :environment, :bot_id, :symbol,
                  :execution_order_id, :execution_fill_scope, :started_at, :finished_at, :final_status, :severity,
                  :local_summary_json, :remote_summary_json, :discrepancy_summary_json, :resolution_summary_json,
                  :blocking_bool, :created_at, :updated_at
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM reconciliation_cases WHERE reconciliation_case_id = ?",
                (row["reconciliation_case_id"],),
            ).fetchone()
        return _hydrate_reconciliation_case_row(_row_to_dict(stored) or row) or row

    def reconciliation_case_by_id(self, reconciliation_case_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reconciliation_cases WHERE reconciliation_case_id = ?",
                (str(reconciliation_case_id),),
            ).fetchone()
        return _hydrate_reconciliation_case_row(_row_to_dict(row))

    def list_reconciliation_cases(
        self,
        *,
        final_status: str | None = None,
        severity: str | None = None,
        blocking_only: bool = False,
        environment: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
        execution_order_id: str | None = None,
        bot_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if final_status:
            clauses.append("final_status = ?")
            params.append(normalize_reconciliation_case_status(final_status))
        if severity:
            clauses.append("severity = ?")
            params.append(normalize_reconciliation_case_severity(severity))
        if blocking_only:
            clauses.append("blocking_bool = 1")
        if environment:
            clauses.append("environment = ?")
            params.append(_normalize_environment(environment))
        if family:
            clauses.append("market_type = ?")
            params.append(_normalize_family(family))
        if symbol:
            clauses.append("symbol = ?")
            params.append(_canonical_symbol(symbol))
        if execution_order_id:
            clauses.append("execution_order_id = ?")
            params.append(str(execution_order_id))
        if bot_id:
            clauses.append("bot_id = ?")
            params.append(str(bot_id))
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM reconciliation_cases
                WHERE {' AND '.join(clauses)}
                ORDER BY started_at DESC, reconciliation_case_id DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params),
            ).fetchall()
        return [_hydrate_reconciliation_case_row(_row_to_dict(row)) or {} for row in rows]

    def insert_reconciliation_case_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "case_event_id": str(payload.get("case_event_id") or uuid4()),
            "reconciliation_case_id": str(payload.get("reconciliation_case_id") or ""),
            "event_time": str(payload.get("event_time") or utc_now_iso()),
            "source_type": normalize_reconciliation_case_event_source(payload.get("source_type")),
            "message": str(payload.get("message") or ""),
            "payload_json": _json_dumps(payload.get("payload_json") or {}),
            "decision_json": _json_dumps(payload.get("decision_json") or {}),
            "applied_bool": _db_bool(payload.get("applied_bool", True)) or 0,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reconciliation_case_events (
                  case_event_id, reconciliation_case_id, event_time, source_type, message, payload_json, decision_json, applied_bool
                ) VALUES (
                  :case_event_id, :reconciliation_case_id, :event_time, :source_type, :message, :payload_json, :decision_json, :applied_bool
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM reconciliation_case_events WHERE case_event_id = ?",
                (row["case_event_id"],),
            ).fetchone()
        return _hydrate_reconciliation_case_event_row(_row_to_dict(stored) or row) or row

    def reconciliation_case_events(self, reconciliation_case_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM reconciliation_case_events
                WHERE reconciliation_case_id = ?
                ORDER BY event_time ASC, case_event_id ASC
                """,
                (str(reconciliation_case_id),),
            ).fetchall()
        return [_hydrate_reconciliation_case_event_row(_row_to_dict(row)) or {} for row in rows]

    def insert_reconciliation_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "snapshot_id": str(payload.get("snapshot_id") or uuid4()),
            "reconciliation_case_id": str(payload.get("reconciliation_case_id") or ""),
            "snapshot_type": normalize_reconciliation_snapshot_type(payload.get("snapshot_type")),
            "symbol": _canonical_symbol(payload.get("symbol")),
            "execution_order_id": payload.get("execution_order_id"),
            "captured_at": str(payload.get("captured_at") or utc_now_iso()),
            "payload_json": _json_dumps(payload.get("payload_json") or {}),
            "source_freshness_ms": _first_number(payload.get("source_freshness_ms")),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reconciliation_snapshots (
                  snapshot_id, reconciliation_case_id, snapshot_type, symbol, execution_order_id, captured_at, payload_json, source_freshness_ms
                ) VALUES (
                  :snapshot_id, :reconciliation_case_id, :snapshot_type, :symbol, :execution_order_id, :captured_at, :payload_json, :source_freshness_ms
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM reconciliation_snapshots WHERE snapshot_id = ?",
                (row["snapshot_id"],),
            ).fetchone()
        return _hydrate_reconciliation_snapshot_row(_row_to_dict(stored) or row) or row

    def reconciliation_snapshots(self, reconciliation_case_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM reconciliation_snapshots
                WHERE reconciliation_case_id = ?
                ORDER BY captured_at ASC, snapshot_id ASC
                """,
                (str(reconciliation_case_id),),
            ).fetchall()
        return [_hydrate_reconciliation_snapshot_row(_row_to_dict(row)) or {} for row in rows]

    def fill_by_id(self, execution_fill_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_fills WHERE execution_fill_id = ?",
                (str(execution_fill_id),),
            ).fetchone()
        return _hydrate_fill_row(_row_to_dict(row))

    def fill_by_dedup_key(self, dedup_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_fills WHERE dedup_key = ? ORDER BY updated_at DESC, execution_fill_id DESC LIMIT 1",
                (str(dedup_key),),
            ).fetchone()
        return _hydrate_fill_row(_row_to_dict(row))

    def insert_fill(self, payload: dict[str, Any]) -> dict[str, Any]:
        incoming = copy.deepcopy(payload)
        now_iso = utc_now_iso()
        trade_id = incoming.get("trade_id", incoming.get("venue_trade_id"))
        execution_id = incoming.get("execution_id")
        exchange_order_id = incoming.get("exchange_order_id")
        if exchange_order_id is None:
            exchange_order_id = incoming.get("venue_order_id")
        dedup_key_candidate = incoming.get("dedup_key")
        if not str(dedup_key_candidate or "").strip():
            dedup_key_candidate = build_live_fill_dedup_key(
                symbol=incoming.get("symbol"),
                exchange_order_id=exchange_order_id,
                trade_id=trade_id,
                execution_id=execution_id,
                client_order_id=incoming.get("client_order_id"),
                execution_type=incoming.get("execution_type"),
                transaction_time=incoming.get("event_time_exchange") or incoming.get("fill_time"),
                last_executed_qty=incoming.get("last_executed_qty") or incoming.get("qty"),
                last_executed_price=incoming.get("last_executed_price") or incoming.get("price"),
                cumulative_filled_qty_after=incoming.get("cumulative_filled_qty_after"),
            )
        execution_fill_id_candidate = str(incoming.get("execution_fill_id") or build_live_fill_id(str(dedup_key_candidate)))
        existing = self.fill_by_id(execution_fill_id_candidate) or self.fill_by_dedup_key(str(dedup_key_candidate))
        dedup_key = str((existing or {}).get("dedup_key") or dedup_key_candidate)
        execution_fill_id = str(incoming.get("execution_fill_id") or (existing or {}).get("execution_fill_id") or build_live_fill_id(dedup_key))
        source_types = set(_fill_source_lineage(existing, str(incoming.get("raw_source_type") or "")))
        discrepancy = copy.deepcopy(existing.get("discrepancy_json")) if isinstance((existing or {}).get("discrepancy_json"), dict) else {}
        incoming_discrepancy = incoming.get("discrepancy_json")
        if isinstance(incoming_discrepancy, dict):
            discrepancy.update(copy.deepcopy(incoming_discrepancy))
        provenance = copy.deepcopy(existing.get("provenance_json")) if isinstance((existing or {}).get("provenance_json"), dict) else {}
        provenance.update(copy.deepcopy(incoming.get("provenance_json") or {}))
        provenance["source_lineage"] = sorted(source_types)
        provenance.setdefault("source_kind", "execution_reality_fill")
        venue_trade_id = incoming.get("venue_trade_id") or incoming.get("trade_id") or (existing or {}).get("venue_trade_id")
        trade_id = incoming.get("trade_id", venue_trade_id) or (existing or {}).get("trade_id")
        execution_id = incoming.get("execution_id") or (existing or {}).get("execution_id")
        fill_time = str(
            incoming.get("fill_time")
            or incoming.get("event_time_exchange")
            or (existing or {}).get("fill_time")
            or now_iso
        )
        event_time_exchange = str(
            incoming.get("event_time_exchange")
            or incoming.get("fill_time")
            or (existing or {}).get("event_time_exchange")
            or fill_time
        )
        last_executed_qty = _first_number(incoming.get("last_executed_qty"), incoming.get("qty"), (existing or {}).get("last_executed_qty"), (existing or {}).get("qty"))
        last_executed_price = _first_number(incoming.get("last_executed_price"), incoming.get("price"), (existing or {}).get("last_executed_price"), (existing or {}).get("price"))
        last_quote_qty = _first_number(incoming.get("last_quote_qty"), incoming.get("quote_qty"), (existing or {}).get("last_quote_qty"), (existing or {}).get("quote_qty"))
        qty = _first_number(incoming.get("qty"), last_executed_qty, (existing or {}).get("qty"))
        price = _first_number(incoming.get("price"), last_executed_price, (existing or {}).get("price"))
        quote_qty = _first_number(incoming.get("quote_qty"), last_quote_qty, (existing or {}).get("quote_qty"))
        if quote_qty is None and price is not None and qty is not None:
            quote_qty = float(price) * float(qty)
        reconciliation_status = (
            "DISCREPANCY"
            if discrepancy
            else str(
                incoming.get("reconciliation_status")
                or fill_reconciliation_status(source_types=source_types, has_discrepancy=False)
            )
        )
        row = {
            "execution_fill_id": execution_fill_id,
            "execution_order_id": str(incoming.get("execution_order_id") or (existing or {}).get("execution_order_id") or ""),
            "local_order_id": str(incoming.get("local_order_id") or (existing or {}).get("local_order_id") or incoming.get("execution_order_id") or (existing or {}).get("execution_order_id") or ""),
            "exchange": str(incoming.get("exchange") or (existing or {}).get("exchange") or "binance"),
            "market_type": str(incoming.get("market_type") or (existing or {}).get("market_type") or incoming.get("family") or (existing or {}).get("family") or ""),
            "environment": str(incoming.get("environment") or (existing or {}).get("environment") or "paper"),
            "side": str(incoming.get("side") or (existing or {}).get("side") or "") or None,
            "client_order_id": str(incoming.get("client_order_id") or (existing or {}).get("client_order_id") or "") or None,
            "exchange_order_id": str(exchange_order_id or (existing or {}).get("exchange_order_id") or "") or None,
            "trade_id": str(trade_id or "").strip() or None,
            "execution_id": str(execution_id or "").strip() or None,
            "venue_trade_id": str(venue_trade_id or "").strip() or None,
            "fill_time": fill_time,
            "event_time_exchange": event_time_exchange,
            "event_time_local": str(incoming.get("event_time_local") or (existing or {}).get("event_time_local") or now_iso),
            "symbol": str(incoming.get("symbol") or (existing or {}).get("symbol") or ""),
            "family": str(incoming.get("family") or (existing or {}).get("family") or ""),
            "last_executed_qty": last_executed_qty,
            "last_executed_price": last_executed_price,
            "last_quote_qty": last_quote_qty,
            "cumulative_filled_qty_after": _first_number(incoming.get("cumulative_filled_qty_after"), (existing or {}).get("cumulative_filled_qty_after")),
            "cumulative_quote_qty_after": _first_number(incoming.get("cumulative_quote_qty_after"), (existing or {}).get("cumulative_quote_qty_after")),
            "price": price,
            "qty": qty,
            "quote_qty": quote_qty,
            "commission": _first_number(incoming.get("commission"), (existing or {}).get("commission"), 0.0) or 0.0,
            "commission_asset": str(incoming.get("commission_asset") or (existing or {}).get("commission_asset") or "") or None,
            "realized_pnl": _first_number(incoming.get("realized_pnl"), (existing or {}).get("realized_pnl")),
            "maker": _db_bool(incoming.get("maker") if incoming.get("maker") is not None else (existing or {}).get("maker")),
            "self_trade_prevention_mode": str(incoming.get("self_trade_prevention_mode") or (existing or {}).get("self_trade_prevention_mode") or "") or None,
            "prevented_match_id": str(incoming.get("prevented_match_id") or (existing or {}).get("prevented_match_id") or "") or None,
            "raw_source_type": normalize_fill_source_type(incoming.get("raw_source_type") or (existing or {}).get("raw_source_type")),
            "dedup_key": dedup_key,
            "reconciliation_status": reconciliation_status,
            "discrepancy_json": _json_dumps(discrepancy),
            "created_at": str((existing or {}).get("created_at") or incoming.get("created_at") or now_iso),
            "updated_at": str(incoming.get("updated_at") or now_iso),
            "funding_component": _first_number(incoming.get("funding_component"), (existing or {}).get("funding_component")),
            "borrow_interest_component": _first_number(incoming.get("borrow_interest_component"), (existing or {}).get("borrow_interest_component")),
            "spread_realized": _first_number(incoming.get("spread_realized"), (existing or {}).get("spread_realized")),
            "slippage_realized": _first_number(incoming.get("slippage_realized"), (existing or {}).get("slippage_realized")),
            "gross_pnl": _first_number(incoming.get("gross_pnl"), (existing or {}).get("gross_pnl")),
            "net_pnl": _first_number(incoming.get("net_pnl"), (existing or {}).get("net_pnl")),
            "cost_source_json": _json_dumps(incoming.get("cost_source_json") or (existing or {}).get("cost_source_json") or {}),
            "provenance_json": _json_dumps(provenance),
            "provisional": _db_bool(incoming.get("provisional") if incoming.get("provisional") is not None else (existing or {}).get("provisional", False)) or 0,
            "unresolved_components_json": _json_dumps(incoming.get("unresolved_components_json") or (existing or {}).get("unresolved_components_json") or []),
            "raw_fill_json": _json_dumps(incoming.get("raw_fill_json") or (existing or {}).get("raw_fill_json") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_fills (
                  execution_fill_id, execution_order_id, local_order_id, exchange, market_type, environment,
                  side, client_order_id, exchange_order_id, trade_id, execution_id, venue_trade_id,
                  fill_time, event_time_exchange, event_time_local, symbol, family, last_executed_qty,
                  last_executed_price, last_quote_qty, cumulative_filled_qty_after, cumulative_quote_qty_after,
                  price, qty, quote_qty, commission, commission_asset, realized_pnl, maker,
                  self_trade_prevention_mode, prevented_match_id, raw_source_type, dedup_key,
                  reconciliation_status, discrepancy_json, created_at, updated_at,
                  funding_component, borrow_interest_component, spread_realized, slippage_realized,
                  gross_pnl, net_pnl, cost_source_json, provenance_json, provisional,
                  unresolved_components_json, raw_fill_json
                ) VALUES (
                  :execution_fill_id, :execution_order_id, :local_order_id, :exchange, :market_type, :environment,
                  :side, :client_order_id, :exchange_order_id, :trade_id, :execution_id, :venue_trade_id,
                  :fill_time, :event_time_exchange, :event_time_local, :symbol, :family, :last_executed_qty,
                  :last_executed_price, :last_quote_qty, :cumulative_filled_qty_after, :cumulative_quote_qty_after,
                  :price, :qty, :quote_qty, :commission, :commission_asset, :realized_pnl, :maker,
                  :self_trade_prevention_mode, :prevented_match_id, :raw_source_type, :dedup_key,
                  :reconciliation_status, :discrepancy_json, :created_at, :updated_at,
                  :funding_component, :borrow_interest_component, :spread_realized, :slippage_realized,
                  :gross_pnl, :net_pnl, :cost_source_json, :provenance_json, :provisional,
                  :unresolved_components_json, :raw_fill_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM execution_fills WHERE execution_fill_id = ?",
                (row["execution_fill_id"],),
            ).fetchone()
        return _hydrate_fill_row(_row_to_dict(stored) or row) or row

    def list_fills(
        self,
        *,
        execution_order_id: str | None = None,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        reconciliation_status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if execution_order_id:
            clauses.append("execution_order_id = ?")
            params.append(str(execution_order_id))
        if family:
            clauses.append("family = ?")
            params.append(str(family))
        if environment:
            clauses.append("environment = ?")
            params.append(str(environment))
        if symbol:
            clauses.append("symbol = ?")
            params.append(str(symbol))
        if reconciliation_status:
            clauses.append("reconciliation_status = ?")
            params.append(str(reconciliation_status))
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM execution_fills
                WHERE {' AND '.join(clauses)}
                ORDER BY event_time_exchange DESC, fill_time DESC, execution_fill_id DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params),
            ).fetchall()
        return [_hydrate_fill_row(_row_to_dict(row)) or {} for row in rows]

    def list_reconcile_events(
        self,
        *,
        resolved: bool | None = None,
        reconcile_type: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if resolved is not None:
            clauses.append("resolved = ?")
            params.append(1 if resolved else 0)
        if reconcile_type:
            clauses.append("reconcile_type = ?")
            params.append(str(reconcile_type))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM execution_reconcile_events
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, reconcile_event_id DESC
                """,
                tuple(params),
            ).fetchall()
        return [_hydrate_reconcile_row(_row_to_dict(row)) or {} for row in rows]

    def insert_reconcile_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        reconcile_type = str(payload.get("reconcile_type") or "status_mismatch")
        severity = str(payload.get("severity") or "WARN").upper()
        if reconcile_type not in RECONCILE_TYPES:
            raise ValueError(f"Unsupported reconcile_type: {reconcile_type}")
        if severity not in RECONCILE_SEVERITIES:
            raise ValueError(f"Unsupported severity: {severity}")
        row = {
            "reconcile_event_id": str(payload.get("reconcile_event_id") or uuid4()),
            "created_at": str(payload.get("created_at") or utc_now_iso()),
            "family": str(payload.get("family") or ""),
            "environment": str(payload.get("environment") or ""),
            "reconcile_type": reconcile_type,
            "severity": severity,
            "execution_order_id": payload.get("execution_order_id"),
            "client_order_id": payload.get("client_order_id"),
            "details_json": _json_dumps(payload.get("details_json") or {}),
            "resolved": _db_bool(payload.get("resolved", False)),
            "resolved_at": payload.get("resolved_at"),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_reconcile_events (
                  reconcile_event_id, created_at, family, environment, reconcile_type, severity,
                  execution_order_id, client_order_id, details_json, resolved, resolved_at
                ) VALUES (
                  :reconcile_event_id, :created_at, :family, :environment, :reconcile_type, :severity,
                  :execution_order_id, :client_order_id, :details_json, :resolved, :resolved_at
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM execution_reconcile_events WHERE reconcile_event_id = ?",
                (row["reconcile_event_id"],),
            ).fetchone()
        return _hydrate_reconcile_row(_row_to_dict(stored) or row) or row

    def fills_for_order(self, execution_order_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM execution_fills
                WHERE execution_order_id = ?
                ORDER BY event_time_exchange ASC, fill_time ASC, execution_fill_id ASC
                """,
                (str(execution_order_id),),
            ).fetchall()
        return [_hydrate_fill_row(_row_to_dict(row)) or {} for row in rows]

    def reconcile_events_for_order(self, execution_order_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM execution_reconcile_events
                WHERE execution_order_id = ?
                ORDER BY created_at DESC, reconcile_event_id DESC
                """,
                (str(execution_order_id),),
            ).fetchall()
        return [_hydrate_reconcile_row(_row_to_dict(row)) or {} for row in rows]

    def unresolved_reconcile_events(self) -> list[dict[str, Any]]:
        return self.list_reconcile_events(resolved=False)

    def resolve_reconcile_events(
        self,
        *,
        reconcile_type: str | None = None,
        execution_order_id: str | None = None,
        client_order_id: str | None = None,
        family: str | None = None,
        environment: str | None = None,
    ) -> int:
        clauses = ["resolved = 0"]
        params: list[Any] = []
        if reconcile_type:
            clauses.append("reconcile_type = ?")
            params.append(str(reconcile_type))
        if execution_order_id:
            clauses.append("execution_order_id = ?")
            params.append(str(execution_order_id))
        if client_order_id:
            clauses.append("client_order_id = ?")
            params.append(str(client_order_id))
        if family:
            clauses.append("family = ?")
            params.append(str(family))
        if environment:
            clauses.append("environment = ?")
            params.append(str(environment))
        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE execution_reconcile_events
                SET resolved = 1, resolved_at = ?
                WHERE {' AND '.join(clauses)}
                """,
                tuple([utc_now_iso(), *params]),
            )
            return int(cursor.rowcount or 0)

    def insert_user_stream_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "user_stream_event_id": str(payload.get("user_stream_event_id") or uuid4()),
            "created_at": str(payload.get("created_at") or utc_now_iso()),
            "event_time": payload.get("event_time"),
            "family": str(payload.get("family") or ""),
            "environment": str(payload.get("environment") or ""),
            "execution_connector": payload.get("execution_connector"),
            "user_stream_mode": payload.get("user_stream_mode"),
            "subscription_id": payload.get("subscription_id"),
            "listen_key": payload.get("listen_key"),
            "event_name": str(payload.get("event_name") or "unknown"),
            "symbol": payload.get("symbol"),
            "client_order_id": payload.get("client_order_id"),
            "venue_order_id": payload.get("venue_order_id"),
            "payload_json": _json_dumps(payload.get("payload_json") or {}),
            "provenance_json": _json_dumps(payload.get("provenance_json") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_user_stream_events (
                  user_stream_event_id, created_at, event_time, family, environment, execution_connector,
                  user_stream_mode, subscription_id, listen_key, event_name, symbol, client_order_id,
                  venue_order_id, payload_json, provenance_json
                ) VALUES (
                  :user_stream_event_id, :created_at, :event_time, :family, :environment, :execution_connector,
                  :user_stream_mode, :subscription_id, :listen_key, :event_name, :symbol, :client_order_id,
                  :venue_order_id, :payload_json, :provenance_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM execution_user_stream_events WHERE user_stream_event_id = ?",
                (row["user_stream_event_id"],),
            ).fetchone()
        return _hydrate_user_stream_event_row(_row_to_dict(stored) or row) or row

    def list_user_stream_events(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        event_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if family:
            clauses.append("family = ?")
            params.append(str(family))
        if environment:
            clauses.append("environment = ?")
            params.append(str(environment))
        if event_name:
            clauses.append("event_name = ?")
            params.append(str(event_name))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM execution_user_stream_events
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, user_stream_event_id DESC
                LIMIT ?
                """,
                tuple([*params, int(limit)]),
            ).fetchall()
        return [_hydrate_user_stream_event_row(_row_to_dict(row)) or {} for row in rows]

    def trip_kill_switch(
        self,
        *,
        trigger_type: str,
        severity: str,
        family: str | None = None,
        symbol: str | None = None,
        reason: str,
        auto_actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        row = {
            "kill_switch_event_id": str(uuid4()),
            "created_at": utc_now_iso(),
            "trigger_type": str(trigger_type or "manual"),
            "severity": str(severity or "BLOCK").upper(),
            "family": family,
            "symbol": symbol,
            "reason": str(reason or "manual_trip"),
            "auto_actions_json": _json_dumps(auto_actions or []),
            "cleared_at": None,
            "cleared_reason": None,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kill_switch_events (
                  kill_switch_event_id, created_at, trigger_type, severity, family, symbol, reason, auto_actions_json, cleared_at, cleared_reason
                ) VALUES (
                  :kill_switch_event_id, :created_at, :trigger_type, :severity, :family, :symbol, :reason, :auto_actions_json, :cleared_at, :cleared_reason
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM kill_switch_events WHERE kill_switch_event_id = ?",
                (row["kill_switch_event_id"],),
            ).fetchone()
        out = _row_to_dict(stored) or row
        out["auto_actions_json"] = _json_loads(out.get("auto_actions_json"), [])
        return out

    def reset_kill_switch(self, *, reason: str | None = None) -> dict[str, Any]:
        cleared_at = utc_now_iso()
        cleared_reason = str(reason or "manual_reset")
        with self._connect() as conn:
            conn.execute(
                "UPDATE kill_switch_events SET cleared_at = ?, cleared_reason = ? WHERE cleared_at IS NULL",
                (cleared_at, cleared_reason),
            )
        return self.kill_switch_status()

    def kill_switch_events(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM kill_switch_events
                ORDER BY created_at DESC, kill_switch_event_id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = _row_to_dict(row) or {}
            payload["auto_actions_json"] = _json_loads(payload.get("auto_actions_json"), [])
            items.append(payload)
        return items

    def kill_switch_status(self) -> dict[str, Any]:
        with self._connect() as conn:
            active = conn.execute(
                """
                SELECT *
                FROM kill_switch_events
                WHERE cleared_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
            latest = conn.execute(
                """
                SELECT *
                FROM kill_switch_events
                ORDER BY created_at DESC
                LIMIT 1
                """
            ).fetchone()
        active_payload = _row_to_dict(active)
        latest_payload = _row_to_dict(latest)
        if active_payload is not None:
            active_payload["auto_actions_json"] = _json_loads(active_payload.get("auto_actions_json"), [])
        if latest_payload is not None:
            latest_payload["auto_actions_json"] = _json_loads(latest_payload.get("auto_actions_json"), [])
        return {
            "armed": active_payload is not None,
            "active_event": active_payload,
            "last_event": latest_payload,
            "last_trigger_at": active_payload.get("created_at") if isinstance(active_payload, dict) else None,
            "last_cleared_at": latest_payload.get("cleared_at") if isinstance(latest_payload, dict) else None,
        }


class ExecutionRealityService:
    def __init__(
        self,
        *,
        user_data_dir: Path,
        repo_root: Path,
        instrument_registry_service: Any | None = None,
        universe_service: Any | None = None,
        reporting_bridge_service: Any | None = None,
        explicit_policy_root: Path | None = None,
        runs_loader: Any | None = None,
    ) -> None:
        self.user_data_dir = Path(user_data_dir).resolve()
        self.repo_root = Path(repo_root).resolve()
        self.instrument_registry_service = instrument_registry_service
        self.universe_service = universe_service
        self.reporting_bridge_service = reporting_bridge_service
        self.explicit_policy_root = explicit_policy_root.resolve() if explicit_policy_root is not None else None
        self.runs_loader = runs_loader
        self.db = ExecutionRealityDB(self.user_data_dir / "execution" / "execution.sqlite3")
        self._quotes: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._user_stream_status: dict[tuple[str, str], dict[str, Any]] = {}
        self._market_stream_status: dict[tuple[str, str], dict[str, Any]] = {}
        self._margin_levels: dict[str, dict[str, Any]] = {}
        self._futures_auto_cancel_status: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._binance_adapter = BinanceLiveAdapter(
            credential_resolver=_credentials_for_family,
            request_timeout_resolver=self._request_timeout,
            recv_window_resolver=self._exchange_adapter_recv_window_ms,
            server_time_url_resolver=self._server_time_endpoint,
            server_time_sync_enabled_resolver=self._exchange_adapter_server_time_sync_enabled,
            require_server_time_sync_resolver=self._exchange_adapter_require_server_time_sync,
            server_time_cache_sec_resolver=self._exchange_adapter_server_time_cache_sec,
            max_clock_skew_ms_resolver=self._exchange_adapter_max_clock_skew_ms,
            retry_invalid_timestamp_once_resolver=self._exchange_adapter_retry_invalid_timestamp_once,
        )
        self._market_ws_runtime = BinanceMarketWebSocketRuntime(
            repo_root=self.repo_root,
            explicit_policy_root=self.explicit_policy_root,
            market_snapshot_writer=self.set_market_snapshot,
            status_writer=self.mark_market_stream_status,
        )
        self._user_stream_runtime = BinanceUserStreamRuntime(
            repo_root=self.repo_root,
            explicit_policy_root=self.explicit_policy_root,
            status_writer=self.mark_user_stream_runtime_status,
            event_ingestor=lambda family, environment, payload: self.ingest_user_stream_event(
                family=family,
                environment=environment,
                payload=payload,
            ),
            api_key_requester=self._user_stream_api_key_request,
            signed_ws_params_builder=self._user_stream_signed_ws_params,
        )

    def safety_bundle(self) -> dict[str, Any]:
        return load_execution_safety_bundle(self.repo_root, explicit_root=self.explicit_policy_root)

    def router_bundle(self) -> dict[str, Any]:
        return load_execution_router_bundle(self.repo_root, explicit_root=self.explicit_policy_root)

    def safety_policy(self) -> dict[str, Any]:
        payload = execution_safety_policy(self.repo_root, explicit_root=self.explicit_policy_root)
        return payload.get("execution_safety") if isinstance(payload.get("execution_safety"), dict) else {}

    def router_policy(self) -> dict[str, Any]:
        payload = execution_router_policy(self.repo_root, explicit_root=self.explicit_policy_root)
        return payload.get("execution_router") if isinstance(payload.get("execution_router"), dict) else {}

    def policies_loaded(self) -> bool:
        source = self.policy_source()
        return bool(source["execution_safety"]["valid"]) and bool(source["execution_router"]["valid"])

    def policy_source(self) -> dict[str, Any]:
        safety_bundle = self.safety_bundle()
        router_bundle = self.router_bundle()
        return {
            "execution_safety": {
                "path": safety_bundle.get("path"),
                "source_root": safety_bundle.get("source_root"),
                "source_hash": safety_bundle.get("source_hash"),
                "policy_hash": safety_bundle.get("policy_hash"),
                "source": safety_bundle.get("source"),
                "valid": bool(safety_bundle.get("valid")),
                "errors": list(safety_bundle.get("errors") or []),
                "warnings": list(safety_bundle.get("warnings") or []),
                "fallback_used": bool(safety_bundle.get("fallback_used")),
                "selected_role": safety_bundle.get("selected_role"),
                "canonical_root": safety_bundle.get("canonical_root"),
                "canonical_role": safety_bundle.get("canonical_role"),
                "divergent_candidates": copy.deepcopy(safety_bundle.get("divergent_candidates") or []),
            },
            "execution_router": {
                "path": router_bundle.get("path"),
                "source_root": router_bundle.get("source_root"),
                "source_hash": router_bundle.get("source_hash"),
                "policy_hash": router_bundle.get("policy_hash"),
                "source": router_bundle.get("source"),
                "valid": bool(router_bundle.get("valid")),
                "errors": list(router_bundle.get("errors") or []),
                "warnings": list(router_bundle.get("warnings") or []),
                "fallback_used": bool(router_bundle.get("fallback_used")),
                "selected_role": router_bundle.get("selected_role"),
                "canonical_root": router_bundle.get("canonical_root"),
                "canonical_role": router_bundle.get("canonical_role"),
                "divergent_candidates": copy.deepcopy(router_bundle.get("divergent_candidates") or []),
            },
        }

    def policy_hash(self) -> str:
        return _stable_payload_hash(
            {
                "execution_safety": self.safety_policy(),
                "execution_router": self.router_policy(),
            }
        )

    def binance_live_runtime_source(self) -> dict[str, Any]:
        return self._market_ws_runtime.policy_source()

    def binance_live_runtime_hash(self) -> str:
        return self._market_ws_runtime.policy_hash()

    def family_split_summary(self) -> dict[str, Any]:
        return self._market_ws_runtime.family_split_summary()

    def market_streams_summary(self) -> dict[str, Any]:
        summary = self._market_ws_runtime.summary()
        sessions = summary.get("sessions") if isinstance(summary.get("sessions"), list) else []
        live_sessions = [row for row in sessions if _normalize_environment(row.get("environment")) == "live"]
        summary["running_sessions"] = len([row for row in sessions if _bool(row.get("running"))])
        summary["live_sessions"] = len(live_sessions)
        summary["live_blocked"] = any(_bool(row.get("block_live")) for row in live_sessions)
        summary["live_degraded"] = any(_bool(row.get("degraded_mode")) for row in live_sessions)
        return summary

    def user_streams_summary(self) -> dict[str, Any]:
        summary = self._user_stream_runtime.summary()
        sessions = summary.get("sessions") if isinstance(summary.get("sessions"), list) else []
        live_sessions = [row for row in sessions if _normalize_environment(row.get("environment")) == "live"]
        summary["running_sessions"] = len([row for row in sessions if _bool(row.get("running"))])
        summary["live_sessions"] = len(live_sessions)
        summary["live_blocked"] = any(_bool(row.get("block_live")) for row in live_sessions)
        summary["live_degraded"] = any(_bool(row.get("degraded_mode")) for row in live_sessions)
        return summary

    def start_market_stream(
        self,
        *,
        execution_connector: str,
        environment: str,
        symbols: list[str],
        transport_mode: str | None = None,
    ) -> dict[str, Any]:
        return self._market_ws_runtime.start(
            execution_connector=execution_connector,
            environment=environment,
            symbols=symbols,
            transport_mode=transport_mode,
        )

    def stop_market_stream(self, *, execution_connector: str, environment: str) -> dict[str, Any]:
        return self._market_ws_runtime.stop(execution_connector=execution_connector, environment=environment)

    def stop_all_market_streams(self) -> list[dict[str, Any]]:
        return self._market_ws_runtime.stop_all()

    def start_user_stream(
        self,
        *,
        execution_connector: str,
        environment: str,
        user_stream_mode: str | None = None,
    ) -> dict[str, Any]:
        connector_cfg = self._market_ws_runtime.connector_config(execution_connector)
        repo_family = str(connector_cfg.get("repo_family") or "")
        control_endpoints = self._user_stream_control_endpoints(
            family=repo_family,
            environment=environment,
            user_stream_mode=user_stream_mode or str(connector_cfg.get("user_stream_mode") or ""),
        )
        return self._user_stream_runtime.start(
            execution_connector=execution_connector,
            environment=environment,
            user_stream_mode=user_stream_mode,
            control_endpoints=control_endpoints,
        )

    def stop_user_stream(self, *, execution_connector: str, environment: str) -> dict[str, Any]:
        return self._user_stream_runtime.stop(execution_connector=execution_connector, environment=environment)

    def stop_all_user_streams(self) -> list[dict[str, Any]]:
        return self._user_stream_runtime.stop_all()

    def _user_stream_api_key_request(
        self,
        method: str,
        endpoint_url: str,
        *,
        family: str,
        environment: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        return self._binance_adapter.api_key_request(
            method,
            endpoint_url,
            family=family,
            environment=environment,
            params=params,
        )

    def _user_stream_signed_ws_params(
        self,
        *,
        family: str,
        environment: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        return self._binance_adapter.signed_websocket_params(
            family=family,
            environment=environment,
            params=params,
        )

    def _exchange_adapter_policy(self) -> dict[str, Any]:
        payload = self.safety_policy().get("exchange_adapter")
        return payload if isinstance(payload, dict) else {}

    def _exchange_adapter_recv_window_ms(self) -> float:
        return _safe_float(self._exchange_adapter_policy().get("recv_window_ms"), 5000.0)

    def _exchange_adapter_server_time_sync_enabled(self) -> bool:
        return _bool(self._exchange_adapter_policy().get("server_time_sync_enabled", True))

    def _exchange_adapter_require_server_time_sync(self, environment: str) -> bool:
        normalized = _normalize_environment(environment)
        if normalized not in {"live", "testnet"}:
            return False
        return _bool(self._exchange_adapter_policy().get("require_server_time_sync_in_live_like_modes", True))

    def _exchange_adapter_server_time_cache_sec(self) -> float:
        return _safe_float(self._exchange_adapter_policy().get("server_time_cache_sec"), 30.0)

    def _exchange_adapter_max_clock_skew_ms(self) -> float:
        return _safe_float(self._exchange_adapter_policy().get("max_clock_skew_ms"), 1000.0)

    def _exchange_adapter_retry_invalid_timestamp_once(self) -> bool:
        return _bool(self._exchange_adapter_policy().get("retry_invalid_timestamp_once", True))

    def _server_time_endpoint(self, family: str, environment: str) -> str:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        if normalized_family == "margin":
            return f"{self._execution_api_root('spot', normalized_environment)}/api/v3/time"
        mapping = {
            "spot": "/api/v3/time",
            "usdm_futures": "/fapi/v1/time",
            "coinm_futures": "/dapi/v1/time",
        }
        path = mapping.get(normalized_family)
        if not path:
            return ""
        return f"{self._execution_api_root(normalized_family, normalized_environment)}{path}"

    def _account_endpoint_from_policy(self, family: str, environment: str) -> str:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        policy = self._instrument_registry_policy()
        endpoints = policy.get("endpoints") if isinstance(policy.get("endpoints"), dict) else {}
        if normalized_family == "spot":
            cfg = endpoints.get("spot") if isinstance(endpoints.get("spot"), dict) else {}
            path = str(cfg.get("account") or "/api/v3/account").strip()
            if not path.startswith("/"):
                path = f"/{path}"
            return f"{self._execution_api_root('spot', normalized_environment)}{path}"
        if normalized_family == "margin":
            cfg = endpoints.get("margin") if isinstance(endpoints.get("margin"), dict) else {}
            endpoint = str(
                cfg.get("testnet_account") if normalized_environment == "testnet" else cfg.get("live_account") or ""
            ).strip()
            override = os.getenv("BINANCE_MARGIN_BASE_URL") or os.getenv("BINANCE_SPOT_BASE_URL")
            if endpoint:
                return _apply_base_override(endpoint, override)
            return f"{self._execution_api_root('spot', normalized_environment)}/sapi/v1/margin/account"
        if normalized_family == "usdm_futures":
            cfg = endpoints.get("usdm_futures") if isinstance(endpoints.get("usdm_futures"), dict) else {}
            endpoint = str(
                cfg.get("account_testnet") if normalized_environment == "testnet" else cfg.get("account_live") or ""
            ).strip()
            override = os.getenv("BINANCE_USDM_TESTNET_BASE_URL" if normalized_environment == "testnet" else "BINANCE_USDM_BASE_URL")
            if endpoint:
                return _apply_base_override(endpoint, override)
            return f"{self._execution_api_root('usdm_futures', normalized_environment)}/fapi/v2/account"
        if normalized_family == "coinm_futures":
            cfg = endpoints.get("coinm_futures") if isinstance(endpoints.get("coinm_futures"), dict) else {}
            endpoint = str(
                cfg.get("account_testnet") if normalized_environment == "testnet" else cfg.get("account_live") or ""
            ).strip()
            override = os.getenv("BINANCE_COINM_TESTNET_BASE_URL" if normalized_environment == "testnet" else "BINANCE_COINM_BASE_URL")
            if endpoint:
                return _apply_base_override(endpoint, override)
            return f"{self._execution_api_root('coinm_futures', normalized_environment)}/dapi/v1/account"
        return ""

    def _exchange_contract_endpoint(self, family: str, environment: str, operation: str) -> str:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        normalized_operation = str(operation or "").strip().lower()
        if normalized_operation in {
            "submit",
            "query",
            "open_orders",
            "cancel",
            "cancel_all",
            "my_trades",
            "user_trades",
            "income",
            "countdown_cancel_all",
        }:
            return self._execution_endpoint(normalized_family, normalized_environment, normalized_operation)
        if normalized_operation == "server_time":
            return self._server_time_endpoint(normalized_family, normalized_environment)
        if normalized_operation == "exchange_info":
            root_family = "spot" if normalized_family == "margin" else normalized_family
            mapping = {
                "spot": "/api/v3/exchangeInfo",
                "usdm_futures": "/fapi/v1/exchangeInfo",
                "coinm_futures": "/dapi/v1/exchangeInfo",
            }
            path = mapping.get(root_family)
            if not path:
                raise ValueError(f"Unsupported exchange info operation for family: {family}")
            return f"{self._execution_api_root(root_family, normalized_environment)}{path}"
        if normalized_operation == "balances":
            endpoint = self._account_endpoint_from_policy(normalized_family, normalized_environment)
            if not endpoint:
                raise ValueError(f"Unsupported balances operation for family: {family}")
            return endpoint
        if normalized_operation == "test_order":
            if normalized_family != "spot":
                raise ValueError(f"Unsupported test order operation for family: {family}")
            return f"{self._execution_api_root('spot', normalized_environment)}/api/v3/order/test"
        raise ValueError(f"Unsupported exchange contract operation: {family}:{operation}")

    def _user_stream_endpoint(self, family: str, environment: str) -> str:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        if normalized_family == "spot":
            return f"{self._execution_api_root('spot', normalized_environment)}/api/v3/userDataStream"
        if normalized_family == "margin":
            return f"{self._execution_api_root('spot', normalized_environment)}/sapi/v1/userDataStream"
        if normalized_family == "usdm_futures":
            return f"{self._execution_api_root('usdm_futures', normalized_environment)}/fapi/v1/listenKey"
        if normalized_family == "coinm_futures":
            return f"{self._execution_api_root('coinm_futures', normalized_environment)}/dapi/v1/listenKey"
        return ""

    def _user_stream_control_endpoints(self, *, family: str, environment: str, user_stream_mode: str | None = None) -> dict[str, str]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        mode = str(user_stream_mode or "").strip()
        if mode == "futures_listenkey" and normalized_family in {"usdm_futures", "coinm_futures"}:
            endpoint = self._user_stream_endpoint(normalized_family, normalized_environment)
            return {"start": endpoint, "keepalive": endpoint, "close": endpoint}
        if mode == "legacy_listenkey" and normalized_family in {"spot", "margin"}:
            endpoint = self._user_stream_endpoint(normalized_family, normalized_environment)
            return {"start": endpoint, "keepalive": endpoint, "close": endpoint}
        return {}

    def _exchange_adapter_supported_contracts(self) -> dict[str, dict[str, bool]]:
        return {
            "spot": {
                "server_time": True,
                "exchange_info": True,
                "balances": True,
                "test_order": True,
                "new_order": True,
                "query_order": True,
                "query_open_orders": True,
                "cancel_order": True,
                "cancel_all_open_orders": True,
            },
            "margin": {
                "server_time": True,
                "exchange_info": True,
                "balances": True,
                "test_order": False,
                "new_order": True,
                "query_order": True,
                "query_open_orders": True,
                "cancel_order": True,
                "cancel_all_open_orders": True,
            },
            "usdm_futures": {
                "server_time": True,
                "exchange_info": True,
                "balances": True,
                "test_order": False,
                "new_order": True,
                "query_order": True,
                "query_open_orders": True,
                "cancel_order": True,
                "cancel_all_open_orders": True,
            },
            "coinm_futures": {
                "server_time": True,
                "exchange_info": True,
                "balances": True,
                "test_order": False,
                "new_order": True,
                "query_order": True,
                "query_open_orders": True,
                "cancel_order": True,
                "cancel_all_open_orders": True,
            },
        }

    def exchange_adapter_summary(self) -> dict[str, Any]:
        policy = self._exchange_adapter_policy()
        return {
            "enabled": _bool(policy.get("signed_rest_enabled", True)),
            "recv_window_ms": int(self._exchange_adapter_recv_window_ms()),
            "server_time_sync_enabled": self._exchange_adapter_server_time_sync_enabled(),
            "require_server_time_sync_in_live_like_modes": self._exchange_adapter_require_server_time_sync("live"),
            "server_time_cache_sec": self._exchange_adapter_server_time_cache_sec(),
            "max_clock_skew_ms": self._exchange_adapter_max_clock_skew_ms(),
            "retry_invalid_timestamp_once": self._exchange_adapter_retry_invalid_timestamp_once(),
            "supported_contracts": self._exchange_adapter_supported_contracts(),
            "server_time_cache": self._binance_adapter.cache_status(),
        }

    def fetch_exchange_info(self, *, family: str, environment: str) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        endpoint = self._exchange_contract_endpoint(normalized_family, normalized_environment, "exchange_info")
        payload, meta = self._public_request("GET", endpoint, family=normalized_family, environment=normalized_environment)
        meta = copy.deepcopy(meta)
        if normalized_family == "margin":
            meta["contract_source"] = "spot_exchange_info_for_margin"
        symbols = payload.get("symbols") if isinstance(payload, dict) and isinstance(payload.get("symbols"), list) else []
        return {
            "family": normalized_family,
            "environment": normalized_environment,
            "ok": bool(meta.get("ok")),
            "symbol_count": len(symbols),
            "exchange_info": payload if isinstance(payload, dict) else {},
            "remote_source": meta,
        }

    def fetch_account_balances(
        self,
        *,
        family: str,
        environment: str,
        omit_zero_balances: bool = True,
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        params: dict[str, Any] = {}
        if normalized_family == "spot":
            params["omitZeroBalances"] = "true" if omit_zero_balances else "false"
        payload, meta = self._signed_request(
            "GET",
            self._exchange_contract_endpoint(normalized_family, normalized_environment, "balances"),
            family=normalized_family,
            environment=normalized_environment,
            params=params,
        )
        account_payload = payload if isinstance(payload, dict) else {}
        if normalized_family == "spot":
            balances = account_payload.get("balances") if isinstance(account_payload.get("balances"), list) else []
        elif normalized_family == "margin":
            balances = account_payload.get("userAssets") if isinstance(account_payload.get("userAssets"), list) else []
            margin_level = _first_number(account_payload.get("marginLevel"))
            if margin_level is not None:
                self.set_margin_level(
                    environment=normalized_environment,
                    level=margin_level,
                    source="binance_margin_account",
                )
        else:
            balances = account_payload.get("assets") if isinstance(account_payload.get("assets"), list) else []
        return {
            "family": normalized_family,
            "environment": normalized_environment,
            "ok": bool(meta.get("ok")),
            "balances_count": len(balances),
            "balances": copy.deepcopy(balances),
            "account": account_payload,
            "remote_source": meta,
        }

    def test_order_contract(
        self,
        *,
        family: str,
        environment: str,
        preview: dict[str, Any],
        client_order_id: str,
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        try:
            endpoint = self._exchange_contract_endpoint(normalized_family, normalized_environment, "test_order")
        except ValueError:
            return {
                "family": normalized_family,
                "environment": normalized_environment,
                "ok": False,
                "supported": False,
                "remote_source": {
                    "ok": False,
                    "reason": "unsupported_contract",
                    "error_category": "endpoint",
                },
            }
        params, local_blocking = self._build_submit_params(
            family=normalized_family,
            environment=normalized_environment,
            preview=preview,
            client_order_id=client_order_id,
        )
        if local_blocking:
            return {
                "family": normalized_family,
                "environment": normalized_environment,
                "ok": False,
                "supported": True,
                "blocking_reasons": list(local_blocking),
                "remote_source": {
                    "ok": False,
                    "reason": "invalid_local_contract_payload",
                    "error_category": "request",
                },
            }
        payload, meta = self._signed_request(
            "POST",
            endpoint,
            family=normalized_family,
            environment=normalized_environment,
            params=params,
        )
        return {
            "family": normalized_family,
            "environment": normalized_environment,
            "ok": bool(meta.get("ok")),
            "supported": True,
            "payload": payload if isinstance(payload, dict) else {},
            "remote_source": meta,
        }

    def _kill_switch_policy(self) -> dict[str, Any]:
        payload = self.safety_policy().get("kill_switch")
        return payload if isinstance(payload, dict) else {}

    def _futures_auto_cancel_policy(self) -> dict[str, Any]:
        payload = self.safety_policy().get("futures_auto_cancel")
        return payload if isinstance(payload, dict) else {}

    def _risk_reduce_only_priority_policy(self) -> dict[str, Any]:
        payload = self.safety_policy().get("risk_reduce_only_priority")
        return payload if isinstance(payload, dict) else {}

    def kill_switch_status(self) -> dict[str, Any]:
        raw = self.db.kill_switch_status()
        cfg = self._kill_switch_policy()
        enabled = _bool(cfg.get("enabled"))
        cooldown_sec = max(0, int(_safe_float(cfg.get("cooldown_sec"), 0.0)))
        reference_event = raw.get("active_event") if isinstance(raw.get("active_event"), dict) else raw.get("last_event")
        trigger_at = (reference_event or {}).get("created_at") if isinstance(reference_event, dict) else None
        cooldown_until = _iso_plus_seconds(trigger_at, cooldown_sec) if trigger_at else None
        cooldown_active = False
        cooldown_until_dt = _parse_ts(cooldown_until)
        if not _bool(raw.get("armed")) and cooldown_until_dt is not None:
            cooldown_active = _utc_now() < cooldown_until_dt
        return {
            "enabled": enabled,
            "armed": _bool(raw.get("armed")),
            "active": _bool(raw.get("armed")),
            "blocking_submit": enabled and (_bool(raw.get("armed")) or cooldown_active),
            "cooldown_sec": cooldown_sec,
            "cooldown_until": cooldown_until,
            "cooldown_active": cooldown_active,
            "auto_cancel_all_on_trip": _bool(cfg.get("auto_cancel_all_on_trip")),
            "active_event": copy.deepcopy(raw.get("active_event")),
            "last_event": copy.deepcopy(raw.get("last_event")),
            "last_trigger_at": raw.get("last_trigger_at") or trigger_at,
            "last_cleared_at": raw.get("last_cleared_at"),
            "policy_hash": self.policy_hash(),
        }

    def _supported_live_families(self, parity: dict[str, Any]) -> list[str]:
        supported: list[str] = []
        for family in ("spot", "margin", "usdm_futures", "coinm_futures"):
            live_payload = ((parity.get(family) or {}).get("live") or {}) if isinstance(parity, dict) else {}
            if _bool(live_payload.get("supported")):
                supported.append(family)
        return supported

    def _recent_rejected_order_count(self, *, window_sec: float = 300.0) -> int:
        cutoff = _utc_now() - timedelta(seconds=max(1.0, float(window_sec or 300.0)))
        count = 0
        for row in self.db.list_orders(limit=1000, offset=0):
            if _normalize_environment(row.get("environment")) not in {"live", "testnet"}:
                continue
            ts = _parse_ts(row.get("acknowledged_at")) or _parse_ts(row.get("submitted_at"))
            if ts is None or ts < cutoff:
                continue
            status = str(row.get("order_status") or "").upper()
            if status == "REJECTED" or row.get("reject_code") or row.get("reject_reason"):
                count += 1
        return count

    def _consecutive_failed_submit_count(self) -> int:
        count = 0
        for row in self.db.list_intents(limit=300, offset=0):
            if _normalize_environment(row.get("environment")) not in {"live", "testnet"}:
                continue
            status = str(row.get("preflight_status") or "").strip().lower()
            if status == "submitted":
                break
            if status == "submit_failed":
                count += 1
        return count

    def _repeated_reconcile_mismatch_count(self) -> int:
        blocking_types = {"ack_missing", "fill_missing", "status_mismatch", "cost_mismatch"}
        return sum(
            1
            for row in self.db.unresolved_reconcile_events()
            if str(row.get("reconcile_type") or "") in blocking_types
        )

    def _open_order_safety_state(self) -> dict[str, Any]:
        sizing_cfg = self.safety_policy().get("sizing") if isinstance(self.safety_policy().get("sizing"), dict) else {}
        per_symbol_limit = max(0, int(_safe_float(sizing_cfg.get("max_open_orders_per_symbol"), 0.0)))
        total_limit = max(0, int(_safe_float(sizing_cfg.get("max_open_orders_total"), 0.0)))
        open_orders = [
            row
            for row in self.db.open_orders()
            if _normalize_environment(row.get("environment")) in {"live", "testnet"}
        ]
        by_symbol: dict[tuple[str, str], int] = defaultdict(int)
        for row in open_orders:
            by_symbol[(_normalize_family(row.get("family")), _canonical_symbol(row.get("symbol")))] += 1
        breached_symbols = [
            {
                "family": family,
                "symbol": symbol,
                "count": count,
                "limit": per_symbol_limit,
            }
            for (family, symbol), count in sorted(by_symbol.items())
            if per_symbol_limit > 0 and count >= per_symbol_limit
        ]
        total_breached = total_limit > 0 and len(open_orders) >= total_limit
        return {
            "open_orders_total": len(open_orders),
            "max_open_orders_total": total_limit,
            "max_open_orders_per_symbol": per_symbol_limit,
            "breached_total": total_breached,
            "breached_symbols": breached_symbols,
            "breached": total_breached or bool(breached_symbols),
        }

    def _market_data_safety_state(self) -> dict[str, Any]:
        preflight_cfg = self.safety_policy().get("preflight") if isinstance(self.safety_policy().get("preflight"), dict) else {}
        ks_cfg = self._kill_switch_policy()
        quote_block_ms = max(
            int(_safe_float(preflight_cfg.get("quote_stale_block_ms"), 0.0)),
            int(_safe_float(ks_cfg.get("stale_market_data_block_ms"), 0.0)),
        )
        orderbook_block_ms = max(
            int(_safe_float(preflight_cfg.get("orderbook_stale_block_ms"), 0.0)),
            int(_safe_float(ks_cfg.get("stale_market_data_block_ms"), 0.0)),
        )
        live_quotes = [
            {"family": family, "symbol": symbol, **copy.deepcopy(snapshot)}
            for (family, environment, symbol), snapshot in self._quotes.items()
            if _normalize_environment(environment) == "live"
        ]
        quote_stale = not live_quotes
        orderbook_stale = not live_quotes
        now_ms = int(time.time() * 1000)
        stale_items: list[dict[str, Any]] = []
        for snapshot in live_quotes:
            quote_ts_ms = snapshot.get("quote_ts_ms")
            orderbook_ts_ms = snapshot.get("orderbook_ts_ms")
            quote_age_ms = None if quote_ts_ms is None else max(0, now_ms - int(quote_ts_ms))
            orderbook_age_ms = None if orderbook_ts_ms is None else max(0, now_ms - int(orderbook_ts_ms))
            item_quote_stale = quote_age_ms is None or quote_age_ms >= quote_block_ms
            item_orderbook_stale = orderbook_age_ms is None or orderbook_age_ms >= orderbook_block_ms
            quote_stale = quote_stale or item_quote_stale
            orderbook_stale = orderbook_stale or item_orderbook_stale
            if item_quote_stale or item_orderbook_stale:
                stale_items.append(
                    {
                        "family": snapshot.get("family"),
                        "symbol": snapshot.get("symbol"),
                        "quote_age_ms": quote_age_ms,
                        "orderbook_age_ms": orderbook_age_ms,
                        "quote_stale": item_quote_stale,
                        "orderbook_stale": item_orderbook_stale,
                    }
                )
        return {
            "quote_stale": quote_stale,
            "orderbook_stale": orderbook_stale,
            "stale_market_data": quote_stale or orderbook_stale,
            "quote_block_ms": quote_block_ms,
            "orderbook_block_ms": orderbook_block_ms,
            "items_checked": len(live_quotes),
            "stale_items": stale_items,
        }

    def _margin_guard_state(self, *, supported_families: list[str]) -> dict[str, Any]:
        margin_cfg = self.safety_policy().get("margin") if isinstance(self.safety_policy().get("margin"), dict) else {}
        requires_visibility = _bool(margin_cfg.get("require_margin_level_visible"))
        relevant = any(family in {"margin", "usdm_futures", "coinm_futures"} for family in supported_families)
        payload = copy.deepcopy(self._margin_levels.get("live") or {})
        level = _first_number(payload.get("level"))
        if not relevant:
            return {"status": "NOT_REQUIRED", "level": None, "source": payload.get("source"), "visible": False}
        if level is None:
            return {
                "status": "BLOCK" if requires_visibility else "UNKNOWN",
                "level": None,
                "source": payload.get("source"),
                "visible": False,
            }
        block_below = _safe_float(margin_cfg.get("block_margin_level_below"), 0.0)
        warn_below = _safe_float(margin_cfg.get("warn_margin_level_below"), block_below)
        if level < block_below:
            status = "BLOCK"
        elif level < warn_below:
            status = "WARN"
        else:
            status = "OK"
        return {
            "status": status,
            "level": level,
            "source": payload.get("source"),
            "visible": True,
            "warn_margin_level_below": warn_below,
            "block_margin_level_below": block_below,
        }

    def _arm_futures_auto_cancel_heartbeat(
        self,
        *,
        family: str,
        environment: str,
        symbol: str,
        stop_timer: bool = False,
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        target_symbol = _canonical_symbol(symbol)
        cfg = self._futures_auto_cancel_policy()
        key = (normalized_family, normalized_environment, target_symbol)
        state = {
            "family": normalized_family,
            "environment": normalized_environment,
            "symbol": target_symbol,
            "supported": normalized_family in {"usdm_futures", "coinm_futures"} and normalized_environment in {"live", "testnet"},
            "enabled": _bool(cfg.get("enabled")),
            "heartbeat_sec": max(1, int(_safe_float(cfg.get("heartbeat_sec"), 0.0) or 1)),
            "countdown_ms": max(0, int(_safe_float(cfg.get("countdown_ms"), 0.0))),
            "countdown_stopped": bool(stop_timer),
            "ok": False,
            "reason": "not_evaluated",
            "last_sent_at": utc_now_iso(),
        }
        if not state["supported"]:
            state["reason"] = "unsupported_family_or_environment"
            self._futures_auto_cancel_status[key] = state
            return copy.deepcopy(state)
        if not state["enabled"]:
            state["reason"] = "policy_disabled"
            self._futures_auto_cancel_status[key] = state
            return copy.deepcopy(state)
        countdown_ms = 0 if stop_timer else state["countdown_ms"]
        endpoint = self._execution_endpoint(normalized_family, normalized_environment, "countdown_cancel_all")
        payload, meta = self._signed_request(
            "POST",
            endpoint,
            family=normalized_family,
            environment=normalized_environment,
            params={"symbol": target_symbol, "countdownTime": countdown_ms},
        )
        state.update(
            {
                "endpoint": endpoint,
                "meta": meta,
                "reason": str(meta.get("reason") or "signed_request_failed"),
                "ok": isinstance(payload, dict) and _bool(meta.get("ok")),
                "effective_countdown_ms": int(_safe_float((payload or {}).get("countdownTime"), countdown_ms)),
                "raw_payload": copy.deepcopy(payload) if isinstance(payload, dict) else None,
            }
        )
        self._futures_auto_cancel_status[key] = copy.deepcopy(state)
        return state

    def _refresh_futures_auto_cancel_heartbeats(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        open_orders = [
            row
            for row in self.db.open_orders()
            if _normalize_family(row.get("family")) in {"usdm_futures", "coinm_futures"}
            and _normalize_environment(row.get("environment")) in {"live", "testnet"}
        ]
        targets = sorted(
            {
                (
                    _normalize_family(row.get("family")),
                    _normalize_environment(row.get("environment")),
                    _canonical_symbol(row.get("symbol")),
                )
                for row in open_orders
                if row.get("symbol")
            }
        )
        for family, environment, symbol in targets:
            actions.append(
                self._arm_futures_auto_cancel_heartbeat(
                    family=family,
                    environment=environment,
                    symbol=symbol,
                )
            )
        return actions

    def _cost_stack_policy(self) -> dict[str, Any]:
        if self.reporting_bridge_service is None:
            return {}
        return self.reporting_bridge_service.cost_stack()

    def _freshness_payload(self, fetched_at: str | None) -> dict[str, Any]:
        if self.instrument_registry_service is None:
            return {"status": "missing", "age_hours": None, "warn_after_hours": None, "block_after_hours": None}
        policy = self.instrument_registry_service.policy()
        freshness = policy.get("freshness") if isinstance(policy.get("freshness"), dict) else {}
        warn_hours = float(freshness.get("warn_if_snapshot_older_than_hours", 24) or 24)
        block_hours = float(freshness.get("block_if_snapshot_older_than_hours", 72) or 72)
        dt = _parse_ts(fetched_at)
        if dt is None:
            return {"status": "missing", "age_hours": None, "warn_after_hours": warn_hours, "block_after_hours": block_hours}
        age_hours = max(0.0, (_utc_now() - dt).total_seconds() / 3600.0)
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

    def _exchange_filter_policy(self) -> dict[str, Any]:
        payload = self.safety_policy().get("exchange_filters")
        return payload if isinstance(payload, dict) else {}

    def _exchange_filter_freshness(self, family: str, environment: str) -> dict[str, Any]:
        latest = self._latest_snapshot(family, environment)
        fetched_at = latest.get("fetched_at") if isinstance(latest, dict) else None
        policy = self._exchange_filter_policy()
        max_age_ms = max(0, int(_safe_float(policy.get("max_age_ms"), 300000.0)))
        dt = _parse_ts(fetched_at)
        if dt is None:
            return {
                "status": "missing",
                "snapshot_id": (latest or {}).get("snapshot_id") if isinstance(latest, dict) else None,
                "fetched_at": fetched_at,
                "age_ms": None,
                "max_age_ms": max_age_ms,
            }
        age_ms = max(0, int((_utc_now() - dt).total_seconds() * 1000))
        return {
            "status": "block" if max_age_ms > 0 and age_ms > max_age_ms else "fresh",
            "snapshot_id": (latest or {}).get("snapshot_id") if isinstance(latest, dict) else None,
            "fetched_at": fetched_at,
            "age_ms": age_ms,
            "max_age_ms": max_age_ms,
        }

    def _latest_snapshot(self, family: str, environment: str) -> dict[str, Any] | None:
        if self.instrument_registry_service is None:
            return None
        return self.instrument_registry_service.db.latest_snapshot(
            _normalize_family(family),
            "testnet" if _normalize_environment(environment) == "testnet" else "live",
            success_only=True,
        )

    def _capability_snapshot(self, family: str, environment: str) -> dict[str, Any] | None:
        if self.instrument_registry_service is None:
            return None
        target_env = "testnet" if _normalize_environment(environment) == "testnet" else "live"
        return self.instrument_registry_service.db.latest_capability_snapshot(_normalize_family(family), target_env)

    def _instrument_row(self, family: str, symbol: str) -> dict[str, Any] | None:
        if self.instrument_registry_service is None:
            return None
        target_family = _normalize_family(family)
        target_symbol = _canonical_symbol(symbol)
        base_row = None
        for row in self.instrument_registry_service.db.registry_rows(active_only=True):
            if str(row.get("family") or "") == target_family and _canonical_symbol(row.get("symbol")) == target_symbol:
                base_row = row
                break
        if base_row is None:
            return None
        snapshots: list[str] = []
        latest_live = self._latest_snapshot(target_family, "live")
        if isinstance(latest_live, dict) and latest_live.get("snapshot_id"):
            snapshots.append(str(latest_live.get("snapshot_id")))
        latest_testnet = self._latest_snapshot(target_family, "testnet")
        if isinstance(latest_testnet, dict) and latest_testnet.get("snapshot_id"):
            snapshots.append(str(latest_testnet.get("snapshot_id")))
        for snapshot_id in snapshots:
            for item in self.instrument_registry_service.db.snapshot_items(snapshot_id):
                if _canonical_symbol(item.get("symbol")) == target_symbol:
                    merged = copy.deepcopy(base_row)
                    merged.update(item)
                    return merged
        return base_row

    def _universe_membership(self, family: str, symbol: str) -> dict[str, Any]:
        if self.universe_service is None:
            return {"matched": False, "universes": [], "snapshot_source": None, "policy_source": None}
        if hasattr(self.universe_service, "membership"):
            try:
                return self.universe_service.membership(family=family, symbol=symbol)
            except Exception:
                pass
        return {"matched": False, "universes": [], "snapshot_source": None, "policy_source": None}

    def _quote_snapshot(
        self,
        family: str,
        environment: str,
        symbol: str,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        canonical_symbol = _canonical_symbol(symbol)
        payload = body if isinstance(body, dict) else {}
        if payload:
            snapshot = {
                "bid": _first_number(payload.get("bid")),
                "ask": _first_number(payload.get("ask")),
                "mark_price": _first_number(payload.get("mark_price"), payload.get("markPrice")),
                "quote_ts_ms": int(payload.get("quote_ts_ms") or int(time.time() * 1000)),
                "orderbook_ts_ms": int(payload.get("orderbook_ts_ms") or int(time.time() * 1000)),
                "source": str(payload.get("source") or "request"),
                "updated_at": utc_now_iso(),
            }
            self._quotes[(normalized_family, normalized_environment, canonical_symbol)] = snapshot
            return snapshot
        key = (normalized_family, normalized_environment, canonical_symbol)
        cached = self._quotes.get(key)
        mark_environment = normalized_environment
        if normalized_environment == "paper":
            live_cached = self._quotes.get((normalized_family, "live", canonical_symbol))

            def _snapshot_ts(snapshot: dict[str, Any] | None, field: str) -> int:
                if not isinstance(snapshot, dict):
                    return 0
                try:
                    return int(snapshot.get(field) or 0)
                except (TypeError, ValueError):
                    return 0

            if isinstance(live_cached, dict):
                # Paper runtime consumes live market streams. When paper has no
                # dedicated snapshot, or its cached snapshot is older than live,
                # prefer the fresher live market reference.
                if not isinstance(cached, dict):
                    cached = live_cached
                    mark_environment = "live"
                else:
                    live_quote_ts = _snapshot_ts(live_cached, "quote_ts_ms")
                    live_orderbook_ts = _snapshot_ts(live_cached, "orderbook_ts_ms")
                    paper_quote_ts = _snapshot_ts(cached, "quote_ts_ms")
                    paper_orderbook_ts = _snapshot_ts(cached, "orderbook_ts_ms")
                    if (
                        live_quote_ts > paper_quote_ts
                        or live_orderbook_ts > paper_orderbook_ts
                    ):
                        cached = live_cached
                        mark_environment = "live"
        if isinstance(cached, dict):
            snapshot = copy.deepcopy(cached)
            if snapshot.get("mark_price") is None:
                snapshot["mark_price"] = self._mark_price_snapshot(
                    family=family,
                    environment=mark_environment,
                    symbol=symbol,
                )
            return snapshot
        return {
            "bid": None,
            "ask": None,
            "mark_price": self._mark_price_snapshot(
                family=family,
                environment="live" if normalized_environment == "paper" else normalized_environment,
                symbol=symbol,
            ),
            "quote_ts_ms": None,
            "orderbook_ts_ms": None,
            "source": "missing",
            "updated_at": None,
        }

    def _mark_price_snapshot(self, *, family: str, environment: str, symbol: str) -> float | None:
        normalized_family = _normalize_family(family)
        if normalized_family not in {"usdm_futures", "coinm_futures"}:
            return None
        runtime = self.market_streams_summary()
        sessions = runtime.get("sessions") if isinstance(runtime.get("sessions"), list) else []
        target_symbol = _canonical_symbol(symbol)
        for row in sessions:
            if _normalize_family(row.get("repo_family")) != normalized_family:
                continue
            if _normalize_environment(row.get("environment")) != _normalize_environment(environment):
                continue
            mark_prices = row.get("mark_prices") if isinstance(row.get("mark_prices"), dict) else {}
            payload = mark_prices.get(target_symbol) if isinstance(mark_prices.get(target_symbol), dict) else {}
            mark_price = _first_number((payload or {}).get("mark_price"))
            if mark_price is not None:
                return mark_price
        return None

    def _normalize_order(self, instrument: dict[str, Any], request: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
        filters = instrument.get("filter_summary") if isinstance(instrument.get("filter_summary"), dict) else {}
        price_filter = filters.get("price_filter") if isinstance(filters.get("price_filter"), dict) else {}
        lot_size = filters.get("lot_size") if isinstance(filters.get("lot_size"), dict) else {}
        market_lot_size = filters.get("market_lot_size") if isinstance(filters.get("market_lot_size"), dict) else {}
        order_type = str(request.get("order_type") or "MARKET").upper()
        side = str(request.get("side") or "").upper()

        market_step = market_lot_size.get("step_size") if isinstance(market_lot_size, dict) else None
        lot_step = lot_size.get("step_size") if isinstance(lot_size, dict) else None
        step_size = str(market_step or lot_step or "0")
        tick_size = str(price_filter.get("tick_size") or "0")
        qty = _first_number(request.get("quantity"))
        quote_quantity = _first_number(request.get("quote_quantity"))
        limit_price = _first_number(request.get("price"))
        stop_price = _first_number(request.get("stopPrice"), request.get("stop_price"))
        bid = _first_number(quote.get("bid"))
        ask = _first_number(quote.get("ask"))
        mark_price = _first_number(quote.get("mark_price"))
        expected_price = limit_price
        if expected_price is None:
            expected_price = ask or bid if side == "BUY" else bid or ask
        normalized_qty = None if qty is None else _decimal_floor(qty, step_size)
        normalized_price = None if limit_price is None else _decimal_floor(limit_price, tick_size)
        normalized_stop_price = None if stop_price is None else _decimal_floor(stop_price, tick_size)
        preview_price = normalized_price if normalized_price is not None else expected_price
        requested_notional = _safe_float(request.get("requested_notional"), 0.0)
        if requested_notional <= 0:
            if normalized_qty is not None and preview_price is not None:
                requested_notional = abs(normalized_qty * preview_price)
            elif quote_quantity is not None:
                requested_notional = abs(quote_quantity)
        return {
            "symbol": _canonical_symbol(request.get("symbol")),
            "side": side,
            "order_type": order_type,
            "time_in_force": str(request.get("time_in_force") or ("GTC" if order_type == "LIMIT" else "")).upper() or None,
            "quantity": normalized_qty,
            "quote_quantity": quote_quantity,
            "limit_price": normalized_price,
            "stop_price": normalized_stop_price,
            "limit_price_provided": limit_price is not None,
            "preview_price": preview_price,
            "requested_notional": requested_notional,
            "reduce_only": None if request.get("reduce_only") is None else _bool(request.get("reduce_only")),
            "step_size": step_size,
            "tick_size": tick_size,
            "mark_price": mark_price,
            "price_filter": price_filter,
            "lot_size": lot_size,
            "market_lot_size": market_lot_size,
        }

    def _prevalidate_exchange_filters(
        self,
        *,
        family: str,
        environment: str,
        mode: str,
        request: dict[str, Any],
        instrument: dict[str, Any] | None,
        latest_snapshot: dict[str, Any] | None,
        quote: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        target_symbol = _canonical_symbol(request.get("symbol"))
        open_symbol_orders_count = len(
            [
                row
                for row in self.db.open_orders(family=normalized_family, symbol=target_symbol)
                if _normalize_environment(row.get("environment")) == normalized_environment
            ]
        )
        return evaluate_prevalidator(
            family=normalized_family,
            environment=normalized_environment,
            mode=mode,
            symbol=target_symbol,
            side=request.get("side"),
            order_type=request.get("order_type"),
            request=request,
            instrument=instrument,
            filter_summary=(instrument or {}).get("filter_summary") if isinstance((instrument or {}).get("filter_summary"), dict) else {},
            snapshot_fetched_at=(latest_snapshot or {}).get("fetched_at") if isinstance(latest_snapshot, dict) else None,
            filter_policy=self._exchange_filter_policy(),
            quote_reference=quote,
            open_symbol_orders_count=open_symbol_orders_count,
        )

    def filter_rules(self, *, family: str, symbol: str, environment: str = "live") -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        target_symbol = _canonical_symbol(symbol)
        instrument = self._instrument_row(normalized_family, target_symbol)
        latest_snapshot = self._latest_snapshot(normalized_family, normalized_environment)
        payload = describe_filter_rules(
            family=normalized_family,
            environment=normalized_environment,
            symbol=target_symbol,
            instrument=instrument,
            snapshot_fetched_at=(latest_snapshot or {}).get("fetched_at") if isinstance(latest_snapshot, dict) else None,
            filter_policy=self._exchange_filter_policy(),
        )
        payload["policy_source"] = self.policy_source()
        payload["available"] = instrument is not None
        return payload

    def _estimated_costs(self, *, family: str, request: dict[str, Any], preview: dict[str, Any], instrument: dict[str, Any]) -> dict[str, Any]:
        policy = self._cost_stack_policy()
        estimation = policy.get("estimation") if isinstance(policy.get("estimation"), dict) else {}
        notional = _safe_float(preview.get("requested_notional"), 0.0)
        fee_hint = _first_number(request.get("estimated_fee"), request.get("exchange_fee_estimated"))
        spread_bps = _safe_float(request.get("spread_bps"), estimation.get("spread_bps_default", 4.0))
        slippage_bps = _safe_float(request.get("slippage_bps"), estimation.get("slippage_bps_default", 6.0))
        fee_estimated = _safe_float(fee_hint, notional * 0.001)
        spread_estimated = notional * spread_bps / 10000.0
        slippage_estimated = notional * slippage_bps / 10000.0
        total = fee_estimated + spread_estimated + slippage_estimated
        return {
            "requested_notional": round(notional, 8),
            "exchange_fee_estimated": round(fee_estimated, 8),
            "spread_estimated": round(spread_estimated, 8),
            "slippage_estimated": round(slippage_estimated, 8),
            "slippage_bps": round(slippage_bps, 8),
            "total_cost_estimated": round(total, 8),
            "family": family,
            "instrument_id": instrument.get("instrument_id"),
        }

    def _fee_source_state(self, family: str, environment: str) -> dict[str, Any]:
        if self.reporting_bridge_service is None:
            return {"available": False, "fresh": False, "latest": None}
        rows = self.reporting_bridge_service.db.cost_source_snapshots()
        matches = [
            row
            for row in rows
            if str(row.get("family") or "").strip().lower() == _normalize_family(family)
            and str(row.get("environment") or "").strip().lower() == _normalize_environment(environment)
            and _bool(row.get("success"))
        ]
        if not matches:
            return {"available": False, "fresh": False, "latest": None}
        latest = max(matches, key=lambda row: str(row.get("fetched_at") or ""))
        status = self.reporting_bridge_service._latest_cost_source_status(family=family)  # type: ignore[attr-defined]
        return {"available": True, "fresh": status == "fresh", "latest": latest}

    def _slippage_thresholds(self, family: str) -> tuple[float, float]:
        cfg = self.safety_policy().get("slippage") if isinstance(self.safety_policy().get("slippage"), dict) else {}
        suffix = {
            "spot": "spot",
            "margin": "margin",
            "usdm_futures": "usdm",
            "coinm_futures": "coinm",
        }.get(_normalize_family(family), "spot")
        return (
            _safe_float(cfg.get(f"warn_bps_{suffix}"), 10.0),
            _safe_float(cfg.get(f"block_bps_{suffix}"), 25.0),
        )

    def _mode_allowed(self, mode: str) -> bool:
        modes = self.safety_policy().get("modes") if isinstance(self.safety_policy().get("modes"), dict) else {}
        key = {
            "live": "allow_live",
            "testnet": "allow_testnet",
            "paper": "allow_paper",
            "shadow": "allow_shadow",
        }.get(mode, "allow_paper")
        return _bool(modes.get(key, False))

    def set_market_snapshot(
        self,
        *,
        family: str,
        environment: str,
        symbol: str,
        bid: float | None,
        ask: float | None,
        quote_ts_ms: int | None = None,
        orderbook_ts_ms: int | None = None,
        source: str = "manual",
    ) -> dict[str, Any]:
        payload = {
            "bid": bid,
            "ask": ask,
            "quote_ts_ms": int(quote_ts_ms) if quote_ts_ms is not None else int(time.time() * 1000),
            "orderbook_ts_ms": int(orderbook_ts_ms) if orderbook_ts_ms is not None else int(time.time() * 1000),
            "source": str(source or "manual"),
            "updated_at": utc_now_iso(),
        }
        self._quotes[(str(family), str(environment), str(symbol).upper())] = payload
        return payload

    def mark_user_stream_status(
        self,
        *,
        family: str,
        environment: str,
        available: bool,
        degraded_reason: str = "",
    ) -> dict[str, Any]:
        payload = {
            "available": bool(available),
            "degraded_mode": not bool(available),
            "reason": str(degraded_reason or ("ok" if available else "stream_unavailable")),
            "updated_at": utc_now_iso(),
        }
        self._user_stream_status[(_normalize_family(family), _normalize_environment(environment))] = payload
        return payload

    def mark_user_stream_runtime_status(
        self,
        *,
        family: str,
        environment: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = copy.deepcopy(payload if isinstance(payload, dict) else {})
        row["updated_at"] = utc_now_iso()
        self._user_stream_status[(_normalize_family(family), _normalize_environment(environment))] = row
        return copy.deepcopy(row)

    def mark_market_stream_status(
        self,
        *,
        family: str,
        environment: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        row = copy.deepcopy(payload if isinstance(payload, dict) else {})
        row["updated_at"] = utc_now_iso()
        self._market_stream_status[(_normalize_family(family), _normalize_environment(environment))] = row
        return copy.deepcopy(row)

    def set_margin_level(self, *, environment: str, level: float | None, source: str = "manual") -> dict[str, Any]:
        payload = {
            "level": level,
            "source": str(source or "manual"),
            "updated_at": utc_now_iso(),
        }
        self._margin_levels[str(environment)] = payload
        return payload

    def _refresh_margin_level_from_account(self, *, environment: str) -> dict[str, Any] | None:
        try:
            return self.fetch_account_balances(
                family="margin",
                environment=environment,
                omit_zero_balances=False,
            )
        except Exception:
            return None

    def bootstrap_summary(self) -> dict[str, Any]:
        safety = self.safety_policy()
        router = self.router_policy()
        families_enabled = router.get("families_enabled") if isinstance(router.get("families_enabled"), dict) else {}
        supported_order_types = (
            router.get("first_iteration_supported_order_types")
            if isinstance(router.get("first_iteration_supported_order_types"), dict)
            else {}
        )
        policy_source = self.policy_source()
        return {
            "parser_version": PARSER_VERSION,
            "db_path": str(self.db.db_path),
            "tables": self.db.table_names(),
            "counts": self.db.counts(),
            "policy_loaded": self.policies_loaded(),
            "policy_hash": self.policy_hash(),
            "policy_source": policy_source,
            "binance_live_runtime": {
                "policy_loaded": self._market_ws_runtime.policies_loaded(),
                "policy_hash": self.binance_live_runtime_hash(),
                "policy_source": self.binance_live_runtime_source(),
                "family_split": self.family_split_summary().get("connectors") or {},
            },
            "exchange_adapter": self.exchange_adapter_summary(),
            "market_streams": self.market_streams_summary(),
            "user_streams": self.user_streams_summary(),
            "kill_switch": self.kill_switch_status(),
            "modes": safety.get("modes") if isinstance(safety.get("modes"), dict) else {},
            "families_enabled": sorted([name for name, enabled in families_enabled.items() if enabled]),
            "supported_order_types": supported_order_types,
            "persistence": safety.get("persistence") if isinstance(safety.get("persistence"), dict) else {},
            "dependencies": {
                "instrument_registry_service": self.instrument_registry_service is not None,
                "universe_service": self.universe_service is not None,
                "reporting_bridge_service": self.reporting_bridge_service is not None,
                "runs_loader": callable(self.runs_loader),
            },
            "cache_sizes": {
                "market_snapshots": len(self._quotes),
                "user_stream_status": len(self._user_stream_status),
                "market_stream_status": len(self._market_stream_status),
                "margin_levels": len(self._margin_levels),
                "futures_auto_cancel_status": len(self._futures_auto_cancel_status),
            },
        }

    def _instrument_registry_policy(self) -> dict[str, Any]:
        if self.instrument_registry_service is None or not hasattr(self.instrument_registry_service, "policy"):
            return {}
        try:
            policy = self.instrument_registry_service.policy()
        except Exception:
            return {}
        return policy if isinstance(policy, dict) else {}

    def _request_timeout(self) -> float:
        sync_cfg = self._instrument_registry_policy().get("sync") if isinstance(self._instrument_registry_policy().get("sync"), dict) else {}
        return float(sync_cfg.get("request_timeout_sec", 12) or 12)

    def _execution_api_root(self, family: str, environment: str) -> str:
        family = _normalize_family(family)
        environment = _normalize_environment(environment)
        policy = self._instrument_registry_policy()
        endpoints = policy.get("endpoints") if isinstance(policy.get("endpoints"), dict) else {}
        if family == "spot":
            cfg = endpoints.get("spot") if isinstance(endpoints.get("spot"), dict) else {}
            endpoint = str(
                cfg.get("testnet" if environment == "testnet" else "live")
                or ("https://testnet.binance.vision/api/v3/exchangeInfo" if environment == "testnet" else "https://api.binance.com/api/v3/exchangeInfo")
            ).strip()
            override = os.getenv("BINANCE_SPOT_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_SPOT_BASE_URL")
            return _url_root(_apply_base_override(endpoint, override))
        if family == "margin":
            cfg = endpoints.get("margin") if isinstance(endpoints.get("margin"), dict) else {}
            endpoint = str(cfg.get("live_account") or "https://api.binance.com/sapi/v1/margin/account").strip()
            override = os.getenv("BINANCE_MARGIN_BASE_URL") or os.getenv("BINANCE_SPOT_BASE_URL")
            return _url_root(_apply_base_override(endpoint, override))
        if family == "usdm_futures":
            cfg = endpoints.get("usdm_futures") if isinstance(endpoints.get("usdm_futures"), dict) else {}
            endpoint = str(
                cfg.get("testnet" if environment == "testnet" else "live")
                or ("https://demo-fapi.binance.com/fapi/v1/exchangeInfo" if environment == "testnet" else "https://fapi.binance.com/fapi/v1/exchangeInfo")
            ).strip()
            override = os.getenv("BINANCE_USDM_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_USDM_BASE_URL")
            return _url_root(_apply_base_override(endpoint, override))
        if family == "coinm_futures":
            cfg = endpoints.get("coinm_futures") if isinstance(endpoints.get("coinm_futures"), dict) else {}
            endpoint = str(
                cfg.get("testnet" if environment == "testnet" else "live")
                or ("https://testnet.binancefuture.com/dapi/v1/exchangeInfo" if environment == "testnet" else "https://dapi.binance.com/dapi/v1/exchangeInfo")
            ).strip()
            override = os.getenv("BINANCE_COINM_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_COINM_BASE_URL")
            return _url_root(_apply_base_override(endpoint, override))
        raise ValueError(f"Unsupported family: {family}")

    def _execution_endpoint(self, family: str, environment: str, operation: str) -> str:
        root = self._execution_api_root(family, environment)
        mapping = {
            ("spot", "submit"): "/api/v3/order",
            ("spot", "query"): "/api/v3/order",
            ("spot", "open_orders"): "/api/v3/openOrders",
            ("spot", "cancel"): "/api/v3/order",
            ("spot", "cancel_all"): "/api/v3/openOrders",
            ("spot", "my_trades"): "/api/v3/myTrades",
            ("margin", "submit"): "/sapi/v1/margin/order",
            ("margin", "query"): "/sapi/v1/margin/order",
            ("margin", "open_orders"): "/sapi/v1/margin/openOrders",
            ("margin", "cancel"): "/sapi/v1/margin/order",
            ("margin", "cancel_all"): "/sapi/v1/margin/openOrders",
            ("margin", "my_trades"): "/sapi/v1/margin/myTrades",
            ("margin", "interest_history"): "/sapi/v1/margin/interestHistory",
            ("usdm_futures", "submit"): "/fapi/v1/order",
            ("usdm_futures", "query"): "/fapi/v1/order",
            ("usdm_futures", "open_orders"): "/fapi/v1/openOrders",
            ("usdm_futures", "cancel"): "/fapi/v1/order",
            ("usdm_futures", "cancel_all"): "/fapi/v1/allOpenOrders",
            ("usdm_futures", "countdown_cancel_all"): "/fapi/v1/countdownCancelAll",
            ("usdm_futures", "user_trades"): "/fapi/v1/userTrades",
            ("usdm_futures", "income"): "/fapi/v1/income",
            ("coinm_futures", "submit"): "/dapi/v1/order",
            ("coinm_futures", "query"): "/dapi/v1/order",
            ("coinm_futures", "open_orders"): "/dapi/v1/openOrders",
            ("coinm_futures", "cancel"): "/dapi/v1/order",
            ("coinm_futures", "cancel_all"): "/dapi/v1/allOpenOrders",
            ("coinm_futures", "countdown_cancel_all"): "/dapi/v1/countdownCancelAll",
            ("coinm_futures", "user_trades"): "/dapi/v1/userTrades",
            ("coinm_futures", "income"): "/dapi/v1/income",
        }
        path = mapping.get((_normalize_family(family), str(operation).strip().lower()))
        if not path:
            raise ValueError(f"Unsupported execution operation: {family}:{operation}")
        return f"{root}{path}"

    def _signed_request(
        self,
        method: str,
        endpoint_url: str,
        *,
        family: str,
        environment: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        if not _bool(self._exchange_adapter_policy().get("signed_rest_enabled", True)):
            api_key, _api_secret, env_names = _credentials_for_family(family, environment)
            return None, {
                "ok": False,
                "reason": "signed_rest_disabled_by_policy",
                "error_category": "policy",
                "retryable": False,
                "credentials_present": bool(api_key),
                "credential_envs_tried": env_names,
                "endpoint": endpoint_url,
                "method": method.upper(),
            }
        return self._binance_adapter.signed_request(
            method,
            endpoint_url,
            family=family,
            environment=environment,
            params=params,
        )

    def _public_request(
        self,
        method: str,
        endpoint_url: str,
        *,
        family: str,
        environment: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        _ = (_normalize_family(family), _normalize_environment(environment))
        return self._binance_adapter.public_request(method, endpoint_url, params=params)

    def _build_submit_params(
        self,
        *,
        family: str,
        environment: str,
        preview: dict[str, Any],
        client_order_id: str,
    ) -> tuple[dict[str, Any], list[str]]:
        family = _normalize_family(family)
        order_type = str(preview.get("order_type") or "").upper()
        quantity = _first_number(preview.get("quantity"))
        quote_quantity = _first_number(preview.get("quote_quantity"))
        limit_price = _first_number(preview.get("limit_price"))
        params: dict[str, Any] = {
            "symbol": _canonical_symbol(preview.get("symbol")),
            "side": str(preview.get("side") or "").upper(),
            "type": order_type,
            "newClientOrderId": str(client_order_id),
            "newOrderRespType": "FULL" if family == "spot" else "ACK",
        }
        local_blocking: list[str] = []
        if order_type == "LIMIT":
            if quantity is None:
                local_blocking.append("quantity_required_for_limit")
            if limit_price is None:
                local_blocking.append("limit_price_required")
            if preview.get("time_in_force"):
                params["timeInForce"] = preview.get("time_in_force")
            params["price"] = limit_price
            params["quantity"] = quantity
        elif family in {"usdm_futures", "coinm_futures"}:
            if quantity is None:
                local_blocking.append("quantity_required_for_futures")
            params["quantity"] = quantity
        else:
            if quantity is None and quote_quantity is None:
                local_blocking.append("quantity_or_quote_quantity_required")
            if quantity is not None:
                params["quantity"] = quantity
            if quantity is None and quote_quantity is not None:
                params["quoteOrderQty"] = quote_quantity
        if family in {"usdm_futures", "coinm_futures"} and preview.get("reduce_only") is not None:
            params["reduceOnly"] = "true" if _bool(preview.get("reduce_only")) else "false"
        if family == "margin":
            params["isIsolated"] = "FALSE"
        return params, local_blocking

    def _order_row_from_exchange(
        self,
        *,
        execution_order_id: str,
        execution_intent_id: str,
        client_order_id: str,
        family: str,
        environment: str,
        preview: dict[str, Any],
        ack_payload: dict[str, Any] | None,
        submitted_at: str,
        intent: dict[str, Any] | None = None,
        acknowledged_at: str | None = None,
        existing: dict[str, Any] | None = None,
        canceled: bool = False,
    ) -> dict[str, Any]:
        payload = ack_payload if isinstance(ack_payload, dict) else {}
        current = existing or {}
        raw_last = payload or current.get("raw_last_status_json") or {}
        executed_qty = _first_number(payload.get("executedQty"), payload.get("z"), current.get("executed_qty")) or 0.0
        cum_quote_qty = _first_number(payload.get("cummulativeQuoteQty"), payload.get("cumQuote"), payload.get("Z"), payload.get("cumQuoteQty"), current.get("cum_quote_qty")) or 0.0
        avg_fill_price = _first_number(payload.get("avgPrice"), payload.get("ap"), current.get("avg_fill_price"))
        if avg_fill_price is None and executed_qty > 0 and cum_quote_qty > 0:
            avg_fill_price = cum_quote_qty / executed_qty
        order_status = str(
            payload.get("status")
            or payload.get("X")
            or raw_last.get("status")
            or raw_last.get("X")
            or current.get("order_status")
            or ("CANCELED" if canceled else "NEW")
        ).upper()
        ack_time = (
            acknowledged_at
            or _ms_to_iso(payload.get("updateTime"))
            or _ms_to_iso(payload.get("transactTime"))
            or _ms_to_iso(payload.get("T"))
            or _ms_to_iso(payload.get("E"))
            or current.get("acknowledged_at")
            or submitted_at
        )
        canceled_at = (
            utc_now_iso()
            if canceled or order_status == "CANCELED"
            else current.get("canceled_at")
        )
        last_execution_type = str(payload.get("executionType") or payload.get("x") or current.get("last_execution_type") or current.get("execution_type_last") or order_status)
        resolved_local_state = normalize_local_state(
            current.get("current_local_state")
            or map_exchange_event_to_local_state(
                current_local_state=current.get("current_local_state"),
                source_type="REST_CREATE_RESPONSE",
                exchange_order_status=order_status,
                execution_type=last_execution_type,
                cumulative_filled_qty=executed_qty,
                orig_qty=_first_number(payload.get("origQty"), payload.get("q"), preview.get("quantity"), current.get("orig_qty")),
            )
        )
        return {
            "execution_order_id": str(current.get("execution_order_id") or execution_order_id),
            "execution_intent_id": execution_intent_id,
            "exchange": str(current.get("exchange") or "binance"),
            "market_type": str(current.get("market_type") or family),
            "strategy_id": (intent or {}).get("strategy_id") if isinstance(intent, dict) else current.get("strategy_id"),
            "bot_id": (intent or {}).get("bot_id") if isinstance(intent, dict) else current.get("bot_id"),
            "signal_id": (intent or {}).get("signal_id") if isinstance(intent, dict) else current.get("signal_id"),
            "venue_order_id": str(payload.get("orderId") or payload.get("i") or current.get("venue_order_id") or "") or None,
            "client_order_id": str(
                payload.get("clientOrderId")
                or payload.get("c")
                or payload.get("origClientOrderId")
                or payload.get("C")
                or current.get("client_order_id")
                or client_order_id
            ),
            "symbol": _canonical_symbol(payload.get("symbol") or preview.get("symbol") or current.get("symbol")),
            "family": family,
            "environment": environment,
            "requested_qty": _first_number(preview.get("quantity"), current.get("requested_qty"), (intent or {}).get("quantity")),
            "requested_quote_order_qty": _first_number(preview.get("quote_quantity"), current.get("requested_quote_order_qty"), (intent or {}).get("quote_quantity")),
            "requested_price": _first_number(preview.get("limit_price"), current.get("requested_price"), (intent or {}).get("limit_price")),
            "requested_stop_price": _first_number(preview.get("stop_price"), current.get("requested_stop_price"), (intent or {}).get("stop_price")),
            "requested_trailing_delta": _first_number(preview.get("trailing_delta"), current.get("requested_trailing_delta")),
            "requested_stp_mode": preview.get("stp_mode") or current.get("requested_stp_mode"),
            "requested_new_order_resp_type": payload.get("newOrderRespType") or current.get("requested_new_order_resp_type") or "FULL",
            "order_list_id": payload.get("orderListId") or payload.get("g") or current.get("order_list_id"),
            "parent_local_order_id": current.get("parent_local_order_id"),
            "current_local_state": resolved_local_state,
            "last_exchange_order_status": order_status,
            "last_execution_type": last_execution_type,
            "last_reject_reason": payload.get("msg") or payload.get("r") or current.get("last_reject_reason"),
            "last_expiry_reason": current.get("last_expiry_reason"),
            "order_status": order_status,
            "execution_type_last": last_execution_type,
            "submitted_at": str(current.get("submitted_at") or submitted_at),
            "first_submitted_at": str(current.get("first_submitted_at") or current.get("submitted_at") or submitted_at),
            "acknowledged_at": ack_time,
            "canceled_at": canceled_at,
            "expired_at": ack_time if order_status in {"EXPIRED", "EXPIRED_IN_MATCH"} else current.get("expired_at"),
            "reduce_only": current.get("reduce_only") if current.get("reduce_only") is not None else preview.get("reduce_only"),
            "tif": str(payload.get("timeInForce") or payload.get("f") or preview.get("time_in_force") or current.get("tif") or "") or None,
            "price": _first_number(payload.get("price"), payload.get("p"), preview.get("limit_price"), current.get("price")),
            "orig_qty": _first_number(payload.get("origQty"), payload.get("q"), preview.get("quantity"), current.get("orig_qty")),
            "executed_qty": executed_qty,
            "cum_quote_qty": cum_quote_qty,
            "avg_fill_price": avg_fill_price,
            "last_fill_qty": current.get("last_fill_qty"),
            "last_fill_price": current.get("last_fill_price"),
            "commission_total": _first_number(current.get("commission_total"), 0.0) or 0.0,
            "commission_asset_last": current.get("commission_asset_last"),
            "working_time": _ms_to_iso(payload.get("workingTime") or payload.get("W")) or current.get("working_time"),
            "transact_time_last": _ms_to_iso(payload.get("transactTime") or payload.get("T") or payload.get("updateTime") or payload.get("O")) or current.get("transact_time_last") or ack_time,
            "last_event_at": _ms_to_iso(payload.get("E") or payload.get("T") or payload.get("transactTime") or payload.get("updateTime")) or ack_time,
            "terminal_at": ack_time if is_terminal_local_state(resolved_local_state) else current.get("terminal_at"),
            "reconciliation_status": current.get("reconciliation_status") or "PENDING",
            "unresolved_reason": current.get("unresolved_reason"),
            "reject_code": payload.get("code") or payload.get("r") or current.get("reject_code"),
            "reject_reason": payload.get("msg") or payload.get("r") or current.get("reject_reason"),
            "raw_ack_json": payload if payload else current.get("raw_ack_json") or {},
            "raw_last_status_json": raw_last,
            "raw_last_payload_json": payload if payload else current.get("raw_last_payload_json") or raw_last,
        }

    def _paper_ack_payload(self, preview: dict[str, Any], client_order_id: str, submitted_at: str) -> dict[str, Any]:
        return {
            "symbol": _canonical_symbol(preview.get("symbol")),
            "clientOrderId": client_order_id,
            "status": "NEW",
            "type": str(preview.get("order_type") or "").upper(),
            "side": str(preview.get("side") or "").upper(),
            "price": preview.get("limit_price") or 0.0,
            "origQty": preview.get("quantity") or 0.0,
            "executedQty": 0.0,
            "cummulativeQuoteQty": 0.0,
            "timeInForce": preview.get("time_in_force"),
            "transactTime": int(_parse_ts(submitted_at).timestamp() * 1000) if _parse_ts(submitted_at) else int(time.time() * 1000),
            "source": "paper_local",
        }

    def _reconciliation_deadlines(self) -> dict[str, float]:
        policy = self._reconciliation_policy()
        return {
            "soft_deadline_sec": float(policy.get("unknown_reconciliation_soft_deadline_sec") or 5.0),
            "hard_deadline_sec": float(policy.get("unknown_reconciliation_hard_deadline_sec") or 30.0),
            "ack_timeout_sec": float(policy.get("order_ack_timeout_sec") or 8.0),
            "fill_timeout_sec": float(policy.get("fill_reconcile_timeout_sec") or 20.0),
        }

    def _event_time_iso(self, payload: dict[str, Any] | None) -> str | None:
        source = payload if isinstance(payload, dict) else {}
        return (
            _ms_to_iso(source.get("E"))
            or _ms_to_iso(source.get("T"))
            or _ms_to_iso(source.get("transactTime"))
            or _ms_to_iso(source.get("updateTime"))
            or _ms_to_iso(source.get("O"))
            or _ms_to_iso(source.get("workingTime"))
        )

    def _event_execution_id(self, payload: dict[str, Any] | None) -> str | None:
        source = payload if isinstance(payload, dict) else {}
        return str(source.get("executionId") or source.get("I") or "").strip() or None

    def _order_event_dedup_key(
        self,
        *,
        order: dict[str, Any],
        source_type: str,
        payload: dict[str, Any] | None = None,
        forced_state: str | None = None,
    ) -> str:
        source = str(source_type or "").strip().upper()
        raw = payload if isinstance(payload, dict) else {}
        if source == "WS_EXECUTION_REPORT":
            return execution_report_dedup_key(
                symbol=raw.get("s") or order.get("symbol"),
                exchange_order_id=raw.get("i") or raw.get("orderId") or order.get("venue_order_id"),
                exchange_execution_id=self._event_execution_id(raw),
                client_order_id=raw.get("c") or raw.get("clientOrderId") or order.get("client_order_id"),
                execution_type=raw.get("x") or raw.get("executionType"),
                exchange_order_status=raw.get("X") or raw.get("status"),
                transaction_time=raw.get("T") or raw.get("transactTime") or raw.get("E"),
                cumulative_filled_qty=raw.get("z") or raw.get("executedQty") or order.get("executed_qty"),
            )
        if source == "WS_LIST_STATUS":
            return ":".join(
                [
                    "ws_list_status",
                    str(raw.get("s") or order.get("symbol") or "").strip().upper() or "UNKNOWN",
                    str(raw.get("g") or raw.get("orderListId") or order.get("order_list_id") or "").strip() or "0",
                    str(raw.get("l") or raw.get("listStatusType") or "").strip().upper() or "UNKNOWN",
                    str(raw.get("E") or raw.get("transactionTime") or "").strip() or "0",
                ]
            )
        if source == "REST_CREATE_RESPONSE":
            return ":".join(
                [
                    "rest_create",
                    str(order.get("execution_order_id") or ""),
                    str(raw.get("orderId") or raw.get("i") or "").strip() or "0",
                    str(raw.get("transactTime") or raw.get("updateTime") or "").strip() or "0",
                    str(raw.get("status") or raw.get("X") or "").strip().upper() or "UNKNOWN",
                ]
            )
        if source == "REST_CANCEL_RESPONSE":
            return ":".join(
                [
                    "rest_cancel",
                    str(order.get("execution_order_id") or ""),
                    str(raw.get("orderId") or raw.get("i") or order.get("venue_order_id") or "").strip() or "0",
                    str(raw.get("transactTime") or raw.get("updateTime") or "").strip() or "0",
                    str(raw.get("status") or raw.get("X") or "").strip().upper() or "UNKNOWN",
                ]
            )
        if source in {"REST_QUERY_ORDER", "REST_OPEN_ORDERS_SNAPSHOT", "RECOVERY"}:
            return ":".join(
                [
                    source.lower(),
                    str(order.get("execution_order_id") or ""),
                    str(raw.get("orderId") or raw.get("i") or order.get("venue_order_id") or "").strip() or "0",
                    str(raw.get("updateTime") or raw.get("time") or raw.get("transactTime") or raw.get("E") or "").strip() or "0",
                    str(raw.get("status") or raw.get("X") or "").strip().upper() or "UNKNOWN",
                    str(raw.get("executedQty") or raw.get("z") or order.get("executed_qty") or 0),
                ]
            )
        if source == "LOCAL_INTENT":
            return ":".join(
                [
                    "local_intent",
                    str(order.get("execution_order_id") or ""),
                    str(forced_state or order.get("current_local_state") or "INTENT_CREATED"),
                    str(order.get("submitted_at") or order.get("first_submitted_at") or utc_now_iso()),
                ]
            )
        return ":".join(
            [
                "manual",
                str(order.get("execution_order_id") or ""),
                str(source or "UNKNOWN"),
                str(forced_state or raw.get("status") or raw.get("X") or utc_now_iso()),
            ]
        )

    def _apply_order_event(
        self,
        *,
        order: dict[str, Any],
        source_type: str,
        payload: dict[str, Any] | None = None,
        forced_local_state: str | None = None,
        notes: str | None = None,
        unresolved_reason: str | None = None,
        reconciliation_status: str | None = None,
        event_time_local: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        raw = copy.deepcopy(payload if isinstance(payload, dict) else {})
        before = copy.deepcopy(order)
        before_state = normalize_local_state(before.get("current_local_state") or "INTENT_CREATED")
        exchange_status = str(
            raw.get("status")
            or raw.get("X")
            or before.get("last_exchange_order_status")
            or before.get("order_status")
            or ""
        ).upper() or None
        execution_type = str(
            raw.get("executionType")
            or raw.get("x")
            or before.get("last_execution_type")
            or before.get("execution_type_last")
            or ""
        ).upper() or None
        cumulative_filled_qty = (
            _first_number(raw.get("executedQty"), raw.get("z"), before.get("executed_qty"))
            or 0.0
        )
        cumulative_quote_qty = (
            _first_number(raw.get("cummulativeQuoteQty"), raw.get("cumQuote"), raw.get("Z"), raw.get("cumQuoteQty"), before.get("cum_quote_qty"))
            or 0.0
        )
        orig_qty = _first_number(raw.get("origQty"), raw.get("q"), before.get("orig_qty")) or 0.0
        last_fill_price = _first_number(raw.get("lastExecutedPrice"), raw.get("L"), raw.get("price"), raw.get("p"))
        next_state = normalize_local_state(
            forced_local_state
            or map_exchange_event_to_local_state(
                current_local_state=before_state,
                source_type=source_type,
                exchange_order_status=exchange_status,
                execution_type=execution_type,
                cumulative_filled_qty=cumulative_filled_qty,
                orig_qty=orig_qty,
            )
        )
        event_exchange_time = self._event_time_iso(raw)
        local_event_time = str(event_time_local or event_exchange_time or utc_now_iso())
        delta_filled_qty = max(0.0, cumulative_filled_qty - _safe_float(before.get("executed_qty"), 0.0))
        dedup_key = self._order_event_dedup_key(
            order=before,
            source_type=source_type,
            payload=raw,
            forced_state=forced_local_state,
        )
        event_row, duplicated = self.db.insert_live_order_event(
            {
                "execution_order_id": before.get("execution_order_id"),
                "source_type": source_type,
                "exchange_execution_id": self._event_execution_id(raw),
                "exchange_order_id": raw.get("orderId") or raw.get("i") or before.get("venue_order_id"),
                "client_order_id": raw.get("clientOrderId") or raw.get("c") or raw.get("origClientOrderId") or before.get("client_order_id"),
                "event_time_exchange": event_exchange_time,
                "event_time_local": local_event_time,
                "local_state_before": before_state,
                "local_state_after": next_state,
                "exchange_order_status": exchange_status,
                "execution_type": execution_type,
                "reject_reason": raw.get("msg") or raw.get("r") or before.get("last_reject_reason"),
                "expiry_reason": raw.get("expiryReason") or before.get("last_expiry_reason"),
                "delta_filled_qty": delta_filled_qty,
                "cumulative_filled_qty": cumulative_filled_qty,
                "cumulative_quote_qty": cumulative_quote_qty,
                "price": last_fill_price or _first_number(raw.get("price"), raw.get("p"), before.get("price")),
                "raw_payload_json": raw,
                "dedup_key": dedup_key,
                "applied_bool": True,
                "notes": notes,
            }
        )
        if duplicated:
            return before, event_row, True
        avg_fill_price = _first_number(raw.get("avgPrice"), raw.get("ap"), before.get("avg_fill_price"))
        if avg_fill_price is None and cumulative_filled_qty > 0.0 and cumulative_quote_qty > 0.0:
            avg_fill_price = cumulative_quote_qty / cumulative_filled_qty
        updates = {
            "venue_order_id": raw.get("orderId") or raw.get("i") or before.get("venue_order_id"),
            "client_order_id": raw.get("clientOrderId") or raw.get("c") or raw.get("origClientOrderId") or before.get("client_order_id"),
            "order_list_id": raw.get("orderListId") or raw.get("g") or before.get("order_list_id"),
            "current_local_state": next_state,
            "last_exchange_order_status": exchange_status or before.get("last_exchange_order_status") or before.get("order_status"),
            "last_execution_type": execution_type or before.get("last_execution_type") or before.get("execution_type_last"),
            "order_status": exchange_status or before.get("order_status"),
            "execution_type_last": execution_type or before.get("execution_type_last"),
            "executed_qty": cumulative_filled_qty,
            "cum_quote_qty": cumulative_quote_qty,
            "avg_fill_price": avg_fill_price,
            "last_fill_qty": delta_filled_qty if delta_filled_qty > 0.0 else before.get("last_fill_qty"),
            "last_fill_price": last_fill_price or before.get("last_fill_price"),
            "last_reject_reason": raw.get("msg") or raw.get("r") or before.get("last_reject_reason"),
            "last_expiry_reason": raw.get("expiryReason") or before.get("last_expiry_reason"),
            "working_time": self._event_time_iso({"workingTime": raw.get("workingTime") or raw.get("W")}) or before.get("working_time"),
            "transact_time_last": event_exchange_time or before.get("transact_time_last"),
            "last_event_at": local_event_time,
            "acknowledged_at": before.get("acknowledged_at") or local_event_time,
            "expired_at": local_event_time if next_state in {"EXPIRED", "EXPIRED_STP"} else before.get("expired_at"),
            "canceled_at": local_event_time if next_state == "CANCELED" else before.get("canceled_at"),
            "terminal_at": local_event_time if is_terminal_local_state(next_state) else None,
            "reconciliation_status": reconciliation_status
            or ("UNRESOLVED" if next_state in AMBIGUOUS_LOCAL_ORDER_STATES else "RESOLVED"),
            "unresolved_reason": unresolved_reason if next_state in AMBIGUOUS_LOCAL_ORDER_STATES else None,
            "raw_last_status_json": {
                "status": exchange_status or before.get("order_status"),
                "executionType": execution_type,
                "symbol": before.get("symbol"),
            },
            "raw_last_payload_json": raw or before.get("raw_last_payload_json"),
        }
        updated = self.db.update_order_fields(str(before.get("execution_order_id")), updates) or before
        return updated, event_row, False

    def _block_new_submit_for_unresolved_orders(
        self,
        *,
        family: str,
        environment: str,
        bot_id: str | None,
        symbol: str,
    ) -> dict[str, Any]:
        if _normalize_environment(environment) != "live":
            return {"blocking_reasons": [], "warnings": [], "items": []}
        deadlines = self._reconciliation_deadlines()
        items: list[dict[str, Any]] = []
        for row in self.db.list_orders(
            family=family,
            environment=environment,
            symbol=symbol,
            bot_id=bot_id,
            limit=200,
            offset=0,
        ):
            state = normalize_local_state(row.get("current_local_state"))
            if state not in BLOCKING_LOCAL_ORDER_STATES:
                continue
            last_event = _parse_ts(row.get("last_event_at")) or _parse_ts(row.get("submitted_at")) or _utc_now()
            age_sec = max(0.0, (_utc_now() - last_event).total_seconds())
            items.append(
                {
                    "execution_order_id": row.get("execution_order_id"),
                    "current_local_state": state,
                    "symbol": row.get("symbol"),
                    "bot_id": row.get("bot_id"),
                    "age_sec": round(age_sec, 4),
                    "unresolved_reason": row.get("unresolved_reason"),
                }
            )
        blocking = [
            "unresolved_live_order_same_bot_symbol"
            for item in items
            if item["age_sec"] >= deadlines["hard_deadline_sec"] or item["current_local_state"] in {"UNKNOWN_PENDING_RECONCILIATION", "MANUAL_REVIEW_REQUIRED"}
        ]
        warnings = [
            "live_order_reconciliation_pending_same_bot_symbol"
            for item in items
            if item["age_sec"] >= deadlines["soft_deadline_sec"]
        ]
        return {
            "blocking_reasons": list(dict.fromkeys(blocking)),
            "warnings": list(dict.fromkeys(warnings)),
            "items": items,
            "soft_deadline_sec": deadlines["soft_deadline_sec"],
            "hard_deadline_sec": deadlines["hard_deadline_sec"],
        }

    def _block_new_submit_for_reconciliation_cases(
        self,
        *,
        family: str,
        environment: str,
        bot_id: str | None,
        symbol: str,
    ) -> dict[str, Any]:
        if _normalize_environment(environment) != "live":
            return {"blocking_reasons": [], "warnings": [], "items": []}
        items = self._active_reconciliation_cases(
            family=family,
            environment=environment,
            symbol=symbol,
            bot_id=bot_id,
            blocking_only=True,
            limit=100,
        )
        blocking = ["reconciliation_case_blocker_same_bot_symbol"] if items else []
        warnings = ["reconciliation_case_open_same_bot_symbol"] if items else []
        return {
            "blocking_reasons": blocking,
            "warnings": warnings,
            "items": [self._reconciliation_case_summary_row(row) for row in items],
        }

    def _mark_order_unknown_pending_reconciliation(
        self,
        order: dict[str, Any],
        *,
        source_type: str,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        updated, _event_row, _duplicated = self._apply_order_event(
            order=order,
            source_type=source_type,
            payload=payload,
            forced_local_state="UNKNOWN_PENDING_RECONCILIATION",
            notes="unknown_result_requires_reconciliation",
            unresolved_reason=reason,
            reconciliation_status="UNRESOLVED",
        )
        return updated

    def _is_unknown_exchange_result(self, meta: dict[str, Any] | None) -> bool:
        payload = meta if isinstance(meta, dict) else {}
        reason = str(payload.get("reason") or "").strip().lower()
        exchange_code = payload.get("exchange_code")
        try:
            exchange_code_int = int(exchange_code) if exchange_code is not None else None
        except Exception:
            exchange_code_int = None
        exchange_msg = str(payload.get("exchange_msg") or payload.get("error") or "").lower()
        return reason in {"exchange_unavailable", "request_exception"} or exchange_code_int in {-1006, -1007} or "status unknown" in exchange_msg

    def _reconciliation_policy(self) -> dict[str, Any]:
        payload = self.safety_policy().get("reconciliation")
        return payload if isinstance(payload, dict) else {}

    def _reconciliation_engine_policy(self) -> dict[str, Any]:
        policy = self._reconciliation_policy()
        deadlines = self._reconciliation_deadlines()
        return {
            "periodic_enabled": _bool(policy.get("reconciliation_periodic_enabled", True)),
            "periodic_interval_sec": float(policy.get("reconciliation_periodic_interval_sec") or 30.0),
            "startup_enabled": _bool(policy.get("reconciliation_startup_enabled", True)),
            "before_live_start_required": _bool(policy.get("reconciliation_before_live_start_required", True)),
            "max_snapshot_age_ms": float(policy.get("reconciliation_max_snapshot_age_ms") or 15000.0),
            "max_stream_gap_ms": float(policy.get("reconciliation_max_stream_gap_ms") or 10000.0),
            "unknown_hard_deadline_sec": float(
                policy.get("reconciliation_unknown_hard_deadline_sec")
                or deadlines["hard_deadline_sec"]
            ),
            "manual_review_blocks_live": _bool(policy.get("reconciliation_manual_review_blocks_live", True)),
            "desync_blocks_live": _bool(policy.get("reconciliation_desync_blocks_live", True)),
            "open_remote_without_local_blocks_live": _bool(
                policy.get("reconciliation_open_remote_without_local_blocks_live", True)
            ),
            "remote_query_retry_count": max(1, int(_safe_float(policy.get("reconciliation_remote_query_retry_count"), 3))),
            "remote_query_backoff_ms": max(0, int(_safe_float(policy.get("reconciliation_remote_query_backoff_ms"), 500))),
            "recent_trades_limit": max(1, int(_safe_float(policy.get("reconciliation_recent_trades_limit"), 100))),
            "recent_open_orders_scope": str(policy.get("reconciliation_recent_open_orders_scope") or "symbol_first"),
        }

    def _stream_state(self, family: str, environment: str) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        if normalized_environment not in {"live", "testnet"}:
            return {
                "available": True,
                "degraded_mode": False,
                "reason": "not_required",
                "updated_at": None,
            }
        cached = copy.deepcopy(self._user_stream_status.get((normalized_family, normalized_environment)) or {})
        if not cached:
            return {
                "available": False,
                "degraded_mode": True,
                "block_live": False,
                "reason": "stream_status_unknown",
                "updated_at": None,
            }
        return {
            **cached,
            "available": _bool(cached.get("available")),
            "degraded_mode": _bool(cached.get("degraded_mode")),
            "block_live": _bool(cached.get("block_live")),
            "reason": str(cached.get("reason") or ("ok" if _bool(cached.get("available")) else "stream_unavailable")),
            "updated_at": cached.get("updated_at"),
        }

    def _cost_stack_policy_hash(self) -> str:
        if self.reporting_bridge_service is None:
            return ""
        if hasattr(self.reporting_bridge_service, "cost_stack_bundle"):
            try:
                bundle = self.reporting_bridge_service.cost_stack_bundle()
            except Exception:
                bundle = {}
            if isinstance(bundle, dict):
                return str(bundle.get("policy_hash") or bundle.get("source_hash") or "")
        if hasattr(self.reporting_bridge_service, "policy_source"):
            try:
                source = self.reporting_bridge_service.policy_source()
            except Exception:
                source = {}
            if isinstance(source, dict):
                cost_stack = source.get("cost_stack") if isinstance(source.get("cost_stack"), dict) else {}
                return str(cost_stack.get("policy_hash") or cost_stack.get("hash") or "")
        return ""

    def _quote_reference_for_order(self, order: dict[str, Any], intent: dict[str, Any] | None) -> dict[str, Any]:
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        symbol = _canonical_symbol(order.get("symbol"))
        request = (intent or {}).get("raw_request_json") if isinstance((intent or {}).get("raw_request_json"), dict) else {}
        market_snapshot = request.get("market_snapshot") if isinstance(request.get("market_snapshot"), dict) else {}
        cached = self._quote_snapshot(family, environment, symbol)
        bid = _first_number((market_snapshot or {}).get("bid"), cached.get("bid"))
        ask = _first_number((market_snapshot or {}).get("ask"), cached.get("ask"))
        mid = ((bid + ask) / 2.0) if bid is not None and ask is not None else None
        side = str((intent or {}).get("side") or order.get("raw_ack_json", {}).get("side") or "").upper()
        best_quote = ask if side == "BUY" else bid
        preview_price = _first_number(
            (intent or {}).get("limit_price"),
            request.get("price"),
            (order.get("raw_ack_json") if isinstance(order.get("raw_ack_json"), dict) else {}).get("price"),
            order.get("price"),
        )
        if preview_price is None:
            preview_price = best_quote or mid
        return {
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "best_quote": best_quote,
            "preview_price": preview_price,
        }

    def _normalize_trade_payload(
        self,
        *,
        family: str,
        order: dict[str, Any],
        row: dict[str, Any],
        source_kind: str,
    ) -> dict[str, Any] | None:
        symbol = _canonical_symbol(row.get("symbol") or row.get("s") or order.get("symbol"))
        price = _first_number(row.get("price"), row.get("L"), row.get("p"), row.get("ap"))
        qty = _first_number(row.get("qty"), row.get("l"), row.get("lastFilledQty"), row.get("q"))
        quote_qty = _first_number(
            row.get("quoteQty"),
            row.get("Y"),
            row.get("lastQuoteQty"),
            row.get("baseQty"),
        )
        if quote_qty is None and price is not None and qty is not None:
            quote_qty = price * qty
        if price is None or qty is None or qty <= 0:
            return None
        event_time_exchange = (
            _ms_to_iso(row.get("time"))
            or _ms_to_iso(row.get("T"))
            or _ms_to_iso(row.get("transactTime"))
            or _ms_to_iso(row.get("updateTime"))
            or utc_now_iso()
        )
        fill_time = (
            event_time_exchange
        )
        maker = row.get("maker")
        if maker is None:
            maker = row.get("m")
        if maker is None:
            maker = row.get("isMaker")
        client_order_id = str(
            row.get("clientOrderId")
            or row.get("c")
            or row.get("origClientOrderId")
            or row.get("C")
            or order.get("client_order_id")
            or ""
        ).strip() or None
        exchange_order_id = str(
            row.get("orderId")
            or row.get("i")
            or order.get("venue_order_id")
            or ""
        ).strip() or None
        trade_id = str(
            row.get("id")
            or row.get("t")
            or row.get("tradeId")
            or ""
        ).strip() or None
        execution_id = str(
            row.get("executionId")
            or row.get("I")
            or ""
        ).strip() or None
        last_qty = _first_number(row.get("l"), row.get("lastFilledQty"), row.get("qty"), row.get("q"), qty)
        last_price = _first_number(row.get("L"), row.get("lastFilledPrice"), row.get("price"), row.get("p"), price)
        last_quote_qty = _first_number(row.get("Y"), row.get("lastQuoteQty"), row.get("quoteQty"), quote_qty)
        cumulative_filled_qty_after = _first_number(row.get("z"), row.get("executedQty"))
        cumulative_quote_qty_after = _first_number(row.get("Z"), row.get("cummulativeQuoteQty"), row.get("cumQuote"), row.get("cumQuoteQty"))
        source_type = normalize_fill_source_type(source_kind)
        dedup_key = build_live_fill_dedup_key(
            symbol=symbol,
            exchange_order_id=exchange_order_id,
            trade_id=trade_id,
            execution_id=execution_id,
            client_order_id=client_order_id,
            execution_type=row.get("executionType") or row.get("x"),
            transaction_time=event_time_exchange,
            last_executed_qty=last_qty,
            last_executed_price=last_price,
            cumulative_filled_qty_after=cumulative_filled_qty_after,
        )
        return {
            "exchange": "binance",
            "market_type": _normalize_family(family),
            "environment": _normalize_environment(order.get("environment")),
            "side": str(order.get("side") or row.get("side") or row.get("S") or "").upper() or None,
            "client_order_id": client_order_id,
            "exchange_order_id": exchange_order_id,
            "trade_id": trade_id,
            "execution_id": execution_id,
            "venue_trade_id": trade_id or execution_id,
            "venue_order_id": exchange_order_id,
            "fill_time": fill_time,
            "event_time_exchange": event_time_exchange,
            "event_time_local": utc_now_iso(),
            "symbol": symbol,
            "family": _normalize_family(family),
            "last_executed_qty": last_qty,
            "last_executed_price": last_price,
            "last_quote_qty": last_quote_qty,
            "cumulative_filled_qty_after": cumulative_filled_qty_after,
            "cumulative_quote_qty_after": cumulative_quote_qty_after,
            "price": price,
            "qty": qty,
            "quote_qty": quote_qty,
            "commission": _safe_float(_first_number(row.get("commission"), row.get("n"), 0.0), 0.0),
            "commission_asset": str(row.get("commissionAsset") or row.get("N") or row.get("feeAsset") or "").strip() or None,
            "realized_pnl": _first_number(row.get("realizedPnl"), row.get("rp")),
            "maker": None if maker is None else _bool(maker),
            "self_trade_prevention_mode": str(row.get("selfTradePreventionMode") or row.get("V") or "").strip() or None,
            "prevented_match_id": str(row.get("preventedMatchId") or row.get("v") or "").strip() or None,
            "raw_fill_json": copy.deepcopy(row),
            "raw_source_type": source_type,
            "dedup_key": dedup_key,
            "execution_type": str(row.get("executionType") or row.get("x") or "").upper() or None,
            "source_kind": source_kind,
        }

    def _fetch_remote_trade_rows(self, order: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        params: dict[str, Any] = {"symbol": _canonical_symbol(order.get("symbol"))}
        if order.get("venue_order_id"):
            params["orderId"] = order.get("venue_order_id")
        operation = "my_trades" if family in {"spot", "margin"} else "user_trades"
        payload, meta = self._signed_request(
            "GET",
            self._execution_endpoint(family, environment, operation),
            family=family,
            environment=environment,
            params=params,
        )
        rows = payload if isinstance(payload, list) else []
        normalized = [
            normalized_row
            for row in rows
            if isinstance(row, dict)
            for normalized_row in [self._normalize_trade_payload(family=family, order=order, row=row, source_kind=f"{operation}_rest")]
            if normalized_row is not None
        ]
        return normalized, meta

    def _fetch_remote_income_rows(self, order: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        if family not in {"usdm_futures", "coinm_futures"}:
            return [], {"ok": True, "reason": "not_applicable"}
        payload, meta = self._signed_request(
            "GET",
            self._execution_endpoint(family, environment, "income"),
            family=family,
            environment=environment,
            params={"symbol": _canonical_symbol(order.get("symbol")), "limit": 50},
        )
        rows = payload if isinstance(payload, list) else []
        return [copy.deepcopy(row) for row in rows if isinstance(row, dict)], meta

    def _fetch_margin_interest_rows(self, order: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        if family != "margin":
            return [], {"ok": True, "reason": "not_applicable"}
        instrument = self._instrument_row(family, order.get("symbol")) or {}
        candidate_assets = [
            str(asset).strip().upper()
            for asset in (
                instrument.get("margin_asset"),
                instrument.get("quote_asset"),
                instrument.get("base_asset"),
            )
            if str(asset or "").strip()
        ]
        rows: list[dict[str, Any]] = []
        last_meta: dict[str, Any] = {"ok": True, "reason": "not_available"}
        for asset in list(dict.fromkeys(candidate_assets)):
            payload, meta = self._signed_request(
                "GET",
                self._execution_endpoint(family, environment, "interest_history"),
                family=family,
                environment=environment,
                params={"asset": asset, "size": 50},
            )
            last_meta = meta
            if isinstance(payload, list):
                rows.extend(copy.deepcopy(row) for row in payload if isinstance(row, dict))
        return rows, last_meta

    def _distributed_component_map(
        self,
        fills: list[dict[str, Any]],
        *,
        total_component: float | None,
    ) -> dict[str, float | None]:
        if total_component is None or not fills:
            return {}
        weights: list[float] = []
        for row in fills:
            weight = abs(_safe_float(row.get("quote_qty"), 0.0))
            if weight <= 0:
                weight = abs(_safe_float(row.get("price"), 0.0) * _safe_float(row.get("qty"), 0.0))
            if weight <= 0:
                weight = 1.0
            weights.append(weight)
        total_weight = sum(weights)
        if total_weight <= 0:
            total_weight = float(len(fills))
        distributed: dict[str, float | None] = {}
        for idx, row in enumerate(fills):
            share = (weights[idx] / total_weight) if total_weight > 0 else (1.0 / len(fills))
            distributed[str(row.get("execution_fill_id") or row.get("venue_trade_id") or idx)] = float(total_component) * share
        return distributed

    def _futures_income_total(self, order: dict[str, Any], income_rows: list[dict[str, Any]]) -> float | None:
        if not income_rows:
            return None
        symbol = _canonical_symbol(order.get("symbol"))
        submitted_dt = _parse_ts(order.get("submitted_at")) or _utc_now()
        cutoff_before = submitted_dt.timestamp() - (12 * 3600)
        cutoff_after = submitted_dt.timestamp() + (12 * 3600)
        total = 0.0
        matched = False
        for row in income_rows:
            if _canonical_symbol(row.get("symbol")) != symbol:
                continue
            income_type = str(row.get("incomeType") or "").upper()
            if income_type != "FUNDING_FEE":
                continue
            row_time = _first_number(row.get("time"))
            if row_time is not None:
                row_ts = float(row_time) / 1000.0
                if row_ts < cutoff_before or row_ts > cutoff_after:
                    continue
            total += -_safe_float(_first_number(row.get("income"), row.get("incomeAmount"), 0.0), 0.0)
            matched = True
        return total if matched else None

    def _margin_borrow_total(self, order: dict[str, Any], interest_rows: list[dict[str, Any]]) -> float | None:
        if not interest_rows:
            return None
        submitted_dt = _parse_ts(order.get("submitted_at")) or _utc_now()
        cutoff_before = submitted_dt.timestamp() - (12 * 3600)
        cutoff_after = submitted_dt.timestamp() + (12 * 3600)
        total = 0.0
        matched = False
        for row in interest_rows:
            interest_time = _first_number(row.get("interestAccuredTime"), row.get("timestamp"), row.get("createdTime"))
            if interest_time is not None:
                row_ts = float(interest_time) / 1000.0
                if row_ts < cutoff_before or row_ts > cutoff_after:
                    continue
            interest_value = _first_number(row.get("interest"), row.get("interestAccrued"), row.get("interestAccured"))
            if interest_value is None:
                continue
            total += float(interest_value)
            matched = True
        return total if matched else None

    def _fill_payload_from_trade(
        self,
        *,
        order: dict[str, Any],
        intent: dict[str, Any] | None,
        trade: dict[str, Any],
        event_source: str,
        degraded_mode: bool,
        funding_component: float | None = None,
        borrow_interest_component: float | None = None,
    ) -> dict[str, Any]:
        family = _normalize_family(order.get("family"))
        side = str((intent or {}).get("side") or (order.get("raw_ack_json") if isinstance(order.get("raw_ack_json"), dict) else {}).get("side") or "").upper()
        quote_reference = self._quote_reference_for_order(order, intent)
        qty = _safe_float(trade.get("qty"), 0.0)
        price = _safe_float(trade.get("price"), 0.0)
        quote_qty = _first_number(trade.get("quote_qty"))
        if quote_qty is None and qty > 0 and price > 0:
            quote_qty = qty * price
        best_quote = _first_number(quote_reference.get("best_quote"))
        mid = _first_number(quote_reference.get("mid"))
        preview_price = _first_number(quote_reference.get("preview_price"), price)
        spread_realized = None
        if mid is not None and best_quote is not None and qty > 0:
            spread_realized = abs(best_quote - mid) * qty
        slippage_reference = best_quote if best_quote is not None else preview_price
        slippage_realized = None
        if slippage_reference is not None and qty > 0:
            if side == "SELL":
                slippage_realized = max(float(slippage_reference) - price, 0.0) * qty
            else:
                slippage_realized = max(price - float(slippage_reference), 0.0) * qty
        commission = _safe_float(trade.get("commission"), 0.0)
        gross_pnl = _first_number(trade.get("realized_pnl"))
        total_realized_cost = (
            commission
            + _safe_float(spread_realized, 0.0)
            + _safe_float(slippage_realized, 0.0)
            + _safe_float(funding_component, 0.0)
            + _safe_float(borrow_interest_component, 0.0)
        )
        net_pnl = None if gross_pnl is None else float(gross_pnl) - total_realized_cost
        unresolved_components: list[str] = []
        if family in {"usdm_futures", "coinm_futures"} and funding_component is None:
            unresolved_components.append("funding_realized")
        if family == "margin" and borrow_interest_component is None:
            unresolved_components.append("borrow_interest_realized")
        provisional = bool(unresolved_components)
        return {
            "execution_fill_id": trade.get("execution_fill_id"),
            "execution_order_id": str(order.get("execution_order_id")),
            "local_order_id": str(order.get("execution_order_id")),
            "exchange": "binance",
            "market_type": order.get("market_type") or family,
            "environment": order.get("environment"),
            "side": side or order.get("side"),
            "client_order_id": order.get("client_order_id"),
            "exchange_order_id": trade.get("exchange_order_id") or order.get("venue_order_id"),
            "trade_id": trade.get("trade_id") or trade.get("venue_trade_id"),
            "execution_id": trade.get("execution_id"),
            "venue_trade_id": trade.get("venue_trade_id"),
            "fill_time": trade.get("fill_time"),
            "event_time_exchange": trade.get("event_time_exchange") or trade.get("fill_time"),
            "event_time_local": trade.get("event_time_local") or utc_now_iso(),
            "symbol": _canonical_symbol(trade.get("symbol") or order.get("symbol")),
            "family": family,
            "last_executed_qty": trade.get("last_executed_qty") or qty,
            "last_executed_price": trade.get("last_executed_price") or price,
            "last_quote_qty": trade.get("last_quote_qty") or quote_qty,
            "cumulative_filled_qty_after": trade.get("cumulative_filled_qty_after"),
            "cumulative_quote_qty_after": trade.get("cumulative_quote_qty_after"),
            "price": price,
            "qty": qty,
            "quote_qty": quote_qty,
            "commission": commission,
            "commission_asset": trade.get("commission_asset"),
            "realized_pnl": gross_pnl,
            "maker": trade.get("maker"),
            "self_trade_prevention_mode": trade.get("self_trade_prevention_mode"),
            "prevented_match_id": trade.get("prevented_match_id"),
            "raw_source_type": trade.get("raw_source_type"),
            "dedup_key": trade.get("dedup_key"),
            "reconciliation_status": trade.get("reconciliation_status"),
            "discrepancy_json": trade.get("discrepancy_json") or {},
            "funding_component": funding_component,
            "borrow_interest_component": borrow_interest_component,
            "spread_realized": spread_realized,
            "slippage_realized": slippage_realized,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "cost_source_json": {
                "source_kind": event_source,
                "degraded_mode": degraded_mode,
                "execution_policy_hash": self.policy_hash(),
                "cost_stack_policy_hash": self._cost_stack_policy_hash(),
                "reference": {
                    "preview_price": preview_price,
                    "best_quote": best_quote,
                    "mid": mid,
                },
            },
            "provenance_json": {
                "execution_intent_id": (intent or {}).get("execution_intent_id"),
                "execution_order_id": order.get("execution_order_id"),
                "client_order_id": order.get("client_order_id"),
                "venue_order_id": order.get("venue_order_id"),
                "venue_trade_id": trade.get("venue_trade_id"),
                "trade_id": trade.get("trade_id") or trade.get("venue_trade_id"),
                "execution_id": trade.get("execution_id"),
                "source_kind": "execution_reality_fill",
                "event_source": event_source,
                "policy_hash": self.policy_hash(),
                "source_lineage": [normalize_fill_source_type(trade.get("raw_source_type"))],
            },
            "provisional": provisional,
            "unresolved_components_json": unresolved_components,
            "raw_fill_json": trade.get("raw_fill_json") or {},
        }

    def _rebuild_order_from_fills(self, order: dict[str, Any]) -> dict[str, Any]:
        fills = self.db.fills_for_order(str(order.get("execution_order_id")))
        if not fills:
            return order
        executed_qty = sum(_safe_float(fill.get("qty"), 0.0) for fill in fills)
        cum_quote_qty = sum(
            _safe_float(fill.get("quote_qty"), 0.0)
            if fill.get("quote_qty") is not None
            else (_safe_float(fill.get("price"), 0.0) * _safe_float(fill.get("qty"), 0.0))
            for fill in fills
        )
        avg_fill_price = (cum_quote_qty / executed_qty) if executed_qty > 0 else None
        orig_qty = _safe_float(order.get("orig_qty"), 0.0)
        status = str(order.get("order_status") or "NEW").upper()
        local_state = normalize_local_state(order.get("current_local_state") or "WORKING")
        if executed_qty > 0:
            if orig_qty > 0 and executed_qty + 1e-12 >= orig_qty:
                status = "FILLED"
                local_state = "FILLED"
            elif status not in TERMINAL_ORDER_STATUSES:
                status = "PARTIALLY_FILLED"
                local_state = "PARTIALLY_FILLED"
        last_fill = fills[-1]
        commission_total = sum(_safe_float(fill.get("commission"), 0.0) for fill in fills)
        payload = copy.deepcopy(order)
        payload.update(
            {
                "executed_qty": executed_qty,
                "cum_quote_qty": cum_quote_qty,
                "avg_fill_price": avg_fill_price,
                "order_status": status,
                "execution_type_last": "TRADE" if executed_qty > 0 else order.get("execution_type_last"),
                "current_local_state": local_state,
                "last_exchange_order_status": status,
                "last_execution_type": "TRADE" if executed_qty > 0 else order.get("last_execution_type"),
                "acknowledged_at": order.get("acknowledged_at") or fills[0].get("fill_time") or order.get("submitted_at"),
                "last_fill_qty": last_fill.get("qty"),
                "last_fill_price": last_fill.get("price"),
                "commission_total": commission_total,
                "commission_asset_last": last_fill.get("commission_asset"),
                "last_event_at": last_fill.get("fill_time") or order.get("last_event_at"),
                "terminal_at": (last_fill.get("fill_time") or order.get("last_event_at")) if local_state == "FILLED" else order.get("terminal_at"),
                "raw_last_payload_json": order.get("raw_last_payload_json") or order.get("raw_last_status_json"),
            }
        )
        return self.db.upsert_order(payload)

    def _aggregate_order_costs(
        self,
        *,
        order: dict[str, Any],
        intent: dict[str, Any] | None,
        fills: list[dict[str, Any]],
    ) -> dict[str, Any]:
        estimated = {
            "requested_notional": _first_number((intent or {}).get("requested_notional")),
            "exchange_fee_estimated": _first_number((intent or {}).get("estimated_fee")),
            "spread_estimated": None,
            "slippage_estimated": None,
            "slippage_bps": _first_number((intent or {}).get("estimated_slippage_bps")),
            "total_cost_estimated": _first_number((intent or {}).get("estimated_total_cost")),
        }
        if not fills:
            return {
                "estimated_costs": estimated,
                "realized_costs": {
                    "exchange_fee_realized": None,
                    "spread_realized": None,
                    "slippage_realized": None,
                    "funding_realized": None,
                    "borrow_interest_realized": None,
                    "total_cost_realized": None,
                    "cost_classification": "estimated_only",
                    "provisional": False,
                    "unresolved_components": [],
                },
                "gross_pnl": None,
                "net_pnl": None,
            }

        def _sum_if_present(key: str) -> float | None:
            values = [float(fill[key]) for fill in fills if fill.get(key) is not None]
            return sum(values) if values else None

        unresolved_components = sorted(
            {
                str(item)
                for fill in fills
                for item in (_json_loads(fill.get("unresolved_components_json"), []) if isinstance(fill, dict) else [])
                if str(item).strip()
            }
        )
        exchange_fee_realized = _sum_if_present("commission")
        spread_realized = _sum_if_present("spread_realized")
        slippage_realized = _sum_if_present("slippage_realized")
        funding_realized = _sum_if_present("funding_component")
        borrow_interest_realized = _sum_if_present("borrow_interest_component")
        gross_pnl = _sum_if_present("gross_pnl")
        total_realized_cost = sum(
            _safe_float(value, 0.0)
            for value in (
                exchange_fee_realized,
                spread_realized,
                slippage_realized,
                funding_realized,
                borrow_interest_realized,
            )
            if value is not None
        )
        net_pnl = _sum_if_present("net_pnl")
        if net_pnl is None and gross_pnl is not None:
            net_pnl = gross_pnl - total_realized_cost
        has_realized = any(
            value is not None
            for value in (
                exchange_fee_realized,
                spread_realized,
                slippage_realized,
                funding_realized,
                borrow_interest_realized,
            )
        )
        classification = "estimated_only"
        if has_realized and estimated.get("total_cost_estimated") is not None:
            classification = "mixed"
        elif has_realized:
            classification = "realized"
        return {
            "estimated_costs": estimated,
            "realized_costs": {
                "exchange_fee_realized": exchange_fee_realized,
                "spread_realized": spread_realized,
                "slippage_realized": slippage_realized,
                "funding_realized": funding_realized,
                "borrow_interest_realized": borrow_interest_realized,
                "total_cost_realized": total_realized_cost if has_realized else None,
                "cost_classification": classification,
                "provisional": bool(unresolved_components),
                "unresolved_components": unresolved_components,
            },
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
        }

    def _reporting_rows_from_live_fills(
        self,
        *,
        order: dict[str, Any],
        intent: dict[str, Any] | None,
        fills: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        strategy_id = (intent or {}).get("strategy_id")
        bot_id = (intent or {}).get("bot_id")
        execution_policy_hash = self.policy_hash()
        cost_stack_policy_hash = self._cost_stack_policy_hash()
        rows: list[dict[str, Any]] = []
        for fill in fills:
            quote_qty = _first_number(fill.get("quote_qty"))
            if quote_qty is None:
                quote_qty = _safe_float(fill.get("price"), 0.0) * _safe_float(fill.get("qty"), 0.0)
            rows.append(
                {
                    "trade_cost_id": f"TCL-{hashlib.sha256(str(fill.get('execution_fill_id')).encode('utf-8')).hexdigest()[:16].upper()}",
                    "trade_ref": str(fill.get("execution_fill_id") or fill.get("venue_trade_id") or ""),
                    "run_id": None,
                    "venue": "binance",
                    "family": order.get("family"),
                    "environment": order.get("environment"),
                    "symbol": order.get("symbol"),
                    "strategy_id": strategy_id,
                    "bot_id": bot_id,
                    "executed_at": str(fill.get("fill_time") or utc_now_iso()),
                    "exchange_fee_estimated": 0.0,
                    "exchange_fee_realized": _first_number(fill.get("commission")),
                    "fee_asset": fill.get("commission_asset"),
                    "spread_estimated": 0.0,
                    "spread_realized": _first_number(fill.get("spread_realized")),
                    "slippage_estimated": 0.0,
                    "slippage_realized": _first_number(fill.get("slippage_realized")),
                    "funding_estimated": 0.0,
                    "funding_realized": _first_number(fill.get("funding_component")),
                    "borrow_interest_estimated": 0.0,
                    "borrow_interest_realized": _first_number(fill.get("borrow_interest_component")),
                    "rebates_or_discounts": 0.0,
                    "total_cost_estimated": 0.0,
                    "total_cost_realized": sum(
                        _safe_float(value, 0.0)
                        for value in (
                            _first_number(fill.get("commission")),
                            _first_number(fill.get("spread_realized")),
                            _first_number(fill.get("slippage_realized")),
                            _first_number(fill.get("funding_component")),
                            _first_number(fill.get("borrow_interest_component")),
                        )
                        if value is not None
                    ),
                    "gross_pnl": _safe_float(fill.get("gross_pnl"), 0.0),
                    "net_pnl": _safe_float(fill.get("net_pnl"), 0.0),
                    "cost_source": {
                        **(_json_loads(fill.get("cost_source_json"), {}) if isinstance(fill, dict) else {}),
                        "execution_policy_hash": execution_policy_hash,
                        "cost_stack_policy_hash": cost_stack_policy_hash,
                        "quote_qty": quote_qty,
                    },
                    "provenance": {
                        **(_json_loads(fill.get("provenance_json"), {}) if isinstance(fill, dict) else {}),
                        "execution_order_id": order.get("execution_order_id"),
                        "execution_intent_id": (intent or {}).get("execution_intent_id"),
                        "trade_id": fill.get("trade_id") or fill.get("venue_trade_id"),
                        "execution_id": fill.get("execution_id"),
                        "raw_source_type": fill.get("raw_source_type"),
                        "reconciliation_status": fill.get("reconciliation_status"),
                        "source_kind": "execution_reality_fill",
                    },
                    "created_at": utc_now_iso(),
                }
            )
        return rows

    def _sync_fills_to_reporting_bridge(
        self,
        *,
        order: dict[str, Any],
        intent: dict[str, Any] | None,
        fills: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if self.reporting_bridge_service is None or not hasattr(self.reporting_bridge_service, "upsert_execution_trade_rows"):
            return None
        rows = self._reporting_rows_from_live_fills(order=order, intent=intent, fills=fills)
        return self.reporting_bridge_service.upsert_execution_trade_rows(rows)

    def _materialize_trade_rows(
        self,
        *,
        order: dict[str, Any],
        intent: dict[str, Any] | None,
        trade_rows: list[dict[str, Any]],
        event_source: str,
        degraded_mode: bool,
        income_rows: list[dict[str, Any]] | None = None,
        interest_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_rows = [copy.deepcopy(row) for row in trade_rows if isinstance(row, dict)]
        if not normalized_rows:
            return {"fills": [], "order": order, "reporting_sync": None}
        normalized_rows.sort(
            key=lambda row: (
                str(row.get("event_time_exchange") or row.get("fill_time") or ""),
                str(row.get("trade_id") or row.get("venue_trade_id") or row.get("execution_id") or ""),
            )
        )
        running_qty = 0.0
        running_quote = 0.0
        temp_fill_keys: list[str] = []
        for idx, row in enumerate(normalized_rows):
            qty_value = _safe_float(row.get("qty"), 0.0)
            quote_value = _first_number(row.get("quote_qty"), row.get("last_quote_qty"))
            if quote_value is None and _first_number(row.get("price")) is not None:
                quote_value = _safe_float(row.get("price"), 0.0) * qty_value
            if row.get("cumulative_filled_qty_after") is None:
                running_qty += qty_value
                row["cumulative_filled_qty_after"] = running_qty
            else:
                running_qty = max(running_qty, _safe_float(row.get("cumulative_filled_qty_after"), running_qty))
            if row.get("cumulative_quote_qty_after") is None:
                running_quote += _safe_float(quote_value, 0.0)
                row["cumulative_quote_qty_after"] = running_quote
            else:
                running_quote = max(running_quote, _safe_float(row.get("cumulative_quote_qty_after"), running_quote))
            row["last_executed_qty"] = _first_number(row.get("last_executed_qty"), row.get("qty"))
            row["last_executed_price"] = _first_number(row.get("last_executed_price"), row.get("price"))
            row["last_quote_qty"] = _first_number(row.get("last_quote_qty"), row.get("quote_qty"), quote_value)
            row["raw_source_type"] = normalize_fill_source_type(row.get("raw_source_type") or row.get("source_kind"))
            row["dedup_key"] = str(
                row.get("dedup_key")
                or build_live_fill_dedup_key(
                    symbol=row.get("symbol") or order.get("symbol"),
                    exchange_order_id=row.get("exchange_order_id") or row.get("venue_order_id") or order.get("venue_order_id"),
                    trade_id=row.get("trade_id") or row.get("venue_trade_id"),
                    execution_id=row.get("execution_id"),
                    client_order_id=row.get("client_order_id") or order.get("client_order_id"),
                    execution_type=row.get("execution_type"),
                    transaction_time=row.get("event_time_exchange") or row.get("fill_time"),
                    last_executed_qty=row.get("last_executed_qty"),
                    last_executed_price=row.get("last_executed_price"),
                    cumulative_filled_qty_after=row.get("cumulative_filled_qty_after"),
                )
            )
            if not row.get("execution_fill_id"):
                row["execution_fill_id"] = build_live_fill_id(str(row.get("dedup_key") or f"{order.get('execution_order_id')}:{idx}"))
            row["reconciliation_status"] = row.get(
                "reconciliation_status",
                fill_reconciliation_status(
                    source_types={normalize_fill_source_type(row.get("raw_source_type"))},
                    has_discrepancy=bool(row.get("discrepancy_json")),
                ),
            )
            temp_fill_keys.append(str(row["execution_fill_id"]))
        funding_map = self._distributed_component_map(
            normalized_rows,
            total_component=self._futures_income_total(order, income_rows or []),
        )
        borrow_map = self._distributed_component_map(
            normalized_rows,
            total_component=self._margin_borrow_total(order, interest_rows or []),
        )
        persisted: list[dict[str, Any]] = []
        for row in normalized_rows:
            fill_key = str(row.get("execution_fill_id"))
            fill_payload = self._fill_payload_from_trade(
                order=order,
                intent=intent,
                trade=row,
                event_source=event_source,
                degraded_mode=degraded_mode,
                funding_component=funding_map.get(fill_key),
                borrow_interest_component=borrow_map.get(fill_key),
            )
            persisted.append(self.db.insert_fill(fill_payload))
        updated_order = self._rebuild_order_from_fills(order)
        reporting_sync = self._sync_fills_to_reporting_bridge(order=updated_order, intent=intent, fills=persisted)
        return {
            "fills": persisted,
            "order": updated_order,
            "reporting_sync": reporting_sync,
        }

    def _record_reconcile_event(
        self,
        *,
        reconcile_type: str,
        severity: str,
        family: str,
        environment: str,
        execution_order_id: str | None,
        client_order_id: str | None,
        details: dict[str, Any],
        resolved: bool = False,
    ) -> dict[str, Any]:
        details_payload = copy.deepcopy(details)
        details_payload.setdefault(
            "signature_hash",
            _stable_payload_hash(
                {
                    "reconcile_type": reconcile_type,
                    "execution_order_id": execution_order_id,
                    "client_order_id": client_order_id,
                    "details": details,
                }
            ),
        )
        if not resolved:
            for existing in self.db.list_reconcile_events(resolved=False, reconcile_type=reconcile_type):
                if str(existing.get("execution_order_id") or "") != str(execution_order_id or ""):
                    continue
                if str(existing.get("client_order_id") or "") != str(client_order_id or ""):
                    continue
                if str((existing.get("details_json") or {}).get("signature_hash") or "") == str(details_payload["signature_hash"]):
                    return existing
        return self.db.insert_reconcile_event(
            {
                "family": family,
                "environment": environment,
                "reconcile_type": reconcile_type,
                "severity": severity,
                "execution_order_id": execution_order_id,
                "client_order_id": client_order_id,
                "details_json": details_payload,
                "resolved": resolved,
                "resolved_at": utc_now_iso() if resolved else None,
            }
        )

    def _fill_reconciliation_window(self) -> dict[str, float]:
        policy = self._reconciliation_policy()
        return {
            "recent_limit": float(policy.get("my_trades_recent_limit") or 100),
            "window_hours": float(policy.get("my_trades_window_hours") or 24),
        }

    def _compare_fill_to_trade(self, fill: dict[str, Any], trade: dict[str, Any]) -> dict[str, Any]:
        discrepancies: dict[str, Any] = {}
        for key in ("commission", "commission_asset", "maker", "trade_id", "execution_id"):
            fill_value = fill.get(key)
            trade_value = trade.get(key)
            if key == "commission":
                fill_num = _first_number(fill_value)
                trade_num = _first_number(trade_value)
                if fill_num is not None and trade_num is not None and abs(fill_num - trade_num) > 1e-12:
                    discrepancies[key] = {"local": fill_num, "remote": trade_num}
            elif str(fill_value or "") != str(trade_value or "") and str(trade_value or "").strip():
                discrepancies[key] = {"local": fill_value, "remote": trade_value}
        return discrepancies

    def _reconcile_fill_rows_against_remote(
        self,
        *,
        order: dict[str, Any],
        remote_rows: list[dict[str, Any]],
        remote_meta: dict[str, Any] | None,
        trigger: str,
    ) -> list[dict[str, Any]]:
        execution_order_id = str(order.get("execution_order_id") or "")
        client_order_id = str(order.get("client_order_id") or "")
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        existing_fills = self.db.fills_for_order(execution_order_id)
        existing_by_key = {str(fill.get("dedup_key") or ""): fill for fill in existing_fills if str(fill.get("dedup_key") or "").strip()}
        remote_by_key = {str(row.get("dedup_key") or ""): row for row in remote_rows if str(row.get("dedup_key") or "").strip()}
        created: list[dict[str, Any]] = []

        for remote_key, remote_row in remote_by_key.items():
            local_fill = existing_by_key.get(remote_key)
            if local_fill is None:
                continue
            delta = self._compare_fill_to_trade(local_fill, remote_row)
            if delta:
                created.append(
                    self._record_reconcile_event(
                        reconcile_type="fill_discrepancy",
                        severity="WARN",
                        family=family,
                        environment=environment,
                        execution_order_id=execution_order_id,
                        client_order_id=client_order_id,
                        details={
                            "discrepancy_type": "ws_vs_mytrades_value_mismatch",
                            "execution_fill_id": local_fill.get("execution_fill_id"),
                            "dedup_key": remote_key,
                            "trigger": trigger,
                            "delta": delta,
                            "remote_source": remote_meta or {},
                        },
                        resolved=False,
                    )
                )
                self.db.insert_fill(
                    {
                        "execution_fill_id": local_fill.get("execution_fill_id"),
                        "execution_order_id": execution_order_id,
                        "discrepancy_json": {
                            **(local_fill.get("discrepancy_json") if isinstance(local_fill.get("discrepancy_json"), dict) else {}),
                            "ws_vs_mytrades_value_mismatch": delta,
                        },
                        "raw_source_type": "REST_MYTRADES",
                        "reconciliation_status": "DISCREPANCY",
                        "trade_id": remote_row.get("trade_id"),
                        "execution_id": remote_row.get("execution_id"),
                        "commission": remote_row.get("commission"),
                        "commission_asset": remote_row.get("commission_asset"),
                        "maker": remote_row.get("maker"),
                        "raw_fill_json": remote_row.get("raw_fill_json") or {},
                        "event_time_exchange": remote_row.get("event_time_exchange"),
                        "event_time_local": utc_now_iso(),
                    }
                )
            else:
                self.db.insert_fill(
                    {
                        "execution_fill_id": local_fill.get("execution_fill_id"),
                        "execution_order_id": execution_order_id,
                        "trade_id": remote_row.get("trade_id"),
                        "execution_id": remote_row.get("execution_id"),
                        "commission": remote_row.get("commission"),
                        "commission_asset": remote_row.get("commission_asset"),
                        "maker": remote_row.get("maker"),
                        "raw_source_type": "REST_MYTRADES",
                        "reconciliation_status": "RECONCILED",
                        "raw_fill_json": remote_row.get("raw_fill_json") or {},
                        "event_time_exchange": remote_row.get("event_time_exchange"),
                        "event_time_local": utc_now_iso(),
                    }
                )

        missing_remote = [
            fill
            for key, fill in existing_by_key.items()
            if key and key not in remote_by_key and normalize_fill_source_type(fill.get("raw_source_type")) == "WS_EXECUTION_REPORT"
        ]
        for fill in missing_remote:
            created.append(
                self._record_reconcile_event(
                    reconcile_type="fill_discrepancy",
                    severity="WARN",
                    family=family,
                    environment=environment,
                    execution_order_id=execution_order_id,
                    client_order_id=client_order_id,
                    details={
                        "discrepancy_type": "ws_fill_missing_in_mytrades",
                        "execution_fill_id": fill.get("execution_fill_id"),
                        "dedup_key": fill.get("dedup_key"),
                        "trigger": trigger,
                        "remote_source": remote_meta or {},
                    },
                    resolved=False,
                )
            )
            self.db.insert_fill(
                {
                    "execution_fill_id": fill.get("execution_fill_id"),
                    "execution_order_id": execution_order_id,
                    "discrepancy_json": {
                        **(fill.get("discrepancy_json") if isinstance(fill.get("discrepancy_json"), dict) else {}),
                        "ws_fill_missing_in_mytrades": True,
                    },
                    "reconciliation_status": "DISCREPANCY",
                    "updated_at": utc_now_iso(),
                }
            )

        if remote_rows and not missing_remote and not created:
            self.db.resolve_reconcile_events(
                reconcile_type="fill_discrepancy",
                execution_order_id=execution_order_id,
            )
            for fill in self.db.fills_for_order(execution_order_id):
                if str(fill.get("reconciliation_status") or "").upper() == "DISCREPANCY":
                    continue
                if normalize_fill_source_type(fill.get("raw_source_type")) in {"WS_EXECUTION_REPORT", "REST_MYTRADES"}:
                    self.db.insert_fill(
                        {
                            "execution_fill_id": fill.get("execution_fill_id"),
                            "execution_order_id": execution_order_id,
                            "reconciliation_status": "RECONCILED",
                            "updated_at": utc_now_iso(),
                        }
                    )
        return created

    def _fetch_remote_trade_rows_for_symbol(
        self,
        *,
        family: str,
        environment: str,
        symbol: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        params: dict[str, Any] = {
            "symbol": _canonical_symbol(symbol),
            "limit": max(1, int(limit)),
        }
        operation = "my_trades" if normalized_family in {"spot", "margin"} else "user_trades"
        payload, meta = self._signed_request(
            "GET",
            self._execution_endpoint(normalized_family, normalized_environment, operation),
            family=normalized_family,
            environment=normalized_environment,
            params=params,
        )
        rows = payload if isinstance(payload, list) else []
        normalized: list[dict[str, Any]] = []
        order_hint = {
            "symbol": _canonical_symbol(symbol),
            "environment": normalized_environment,
            "family": normalized_family,
        }
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized_row = self._normalize_trade_payload(
                family=normalized_family,
                order=order_hint,
                row=row,
                source_kind=f"{operation}_rest",
            )
            if normalized_row is not None:
                normalized.append(normalized_row)
        return normalized, meta

    def _materialize_paper_fill(self, order: dict[str, Any], intent: dict[str, Any] | None) -> dict[str, Any]:
        if _normalize_environment(order.get("environment")) != "paper":
            return {"fills": [], "order": order, "reporting_sync": None}
        if str(order.get("order_status") or "").upper() in TERMINAL_ORDER_STATUSES:
            return {"fills": self.db.fills_for_order(str(order.get("execution_order_id"))), "order": order, "reporting_sync": None}
        if self.db.fills_for_order(str(order.get("execution_order_id"))):
            return {"fills": self.db.fills_for_order(str(order.get("execution_order_id"))), "order": order, "reporting_sync": None}
        reference = self._quote_reference_for_order(order, intent)
        side = str((intent or {}).get("side") or "").upper()
        order_type = str((intent or {}).get("order_type") or (order.get("raw_ack_json") if isinstance(order.get("raw_ack_json"), dict) else {}).get("type") or "").upper()
        qty = _first_number(order.get("orig_qty"), (intent or {}).get("quantity"))
        if qty is None or qty <= 0:
            return {"fills": [], "order": order, "reporting_sync": None}
        fill_price = None
        if order_type == "MARKET":
            fill_price = _first_number(reference.get("best_quote"), reference.get("preview_price"), order.get("price"))
        else:
            limit_price = _first_number(order.get("price"), (intent or {}).get("limit_price"))
            bid = _first_number(reference.get("bid"))
            ask = _first_number(reference.get("ask"))
            if side == "BUY" and ask is not None and limit_price is not None and ask <= limit_price:
                fill_price = limit_price
            elif side == "SELL" and bid is not None and limit_price is not None and bid >= limit_price:
                fill_price = limit_price
        if fill_price is None:
            return {"fills": [], "order": order, "reporting_sync": None}
        fill_time = utc_now_iso()
        fill_seed = f"{order.get('execution_order_id')}:{fill_time}"
        trade_row = {
            "execution_fill_id": f"PFILL-{hashlib.sha256(fill_seed.encode('utf-8')).hexdigest()[:16].upper()}",
            "venue_trade_id": None,
            "fill_time": fill_time,
            "event_time_exchange": fill_time,
            "event_time_local": fill_time,
            "symbol": order.get("symbol"),
            "family": order.get("family"),
            "price": fill_price,
            "qty": qty,
            "quote_qty": fill_price * qty,
            "commission": 0.0,
            "commission_asset": None,
            "realized_pnl": None,
            "maker": False,
            "raw_source_type": "PAPER_LOCAL_FILL",
            "raw_fill_json": {"source": "paper_local_fill", "fill_price": fill_price},
        }
        return self._materialize_trade_rows(
            order=order,
            intent=intent,
            trade_rows=[trade_row],
            event_source="paper_local_fill",
            degraded_mode=False,
        )

    def _trade_rows_from_create_response(
        self,
        *,
        family: str,
        order: dict[str, Any],
        ack_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if _normalize_family(family) not in {"spot", "margin"}:
            return []
        fills = ack_payload.get("fills") if isinstance(ack_payload.get("fills"), list) else []
        if not fills:
            return []
        rows: list[dict[str, Any]] = []
        for item in fills:
            if not isinstance(item, dict):
                continue
            normalized = self._normalize_trade_payload(
                family=family,
                order=order,
                row={
                    **copy.deepcopy(item),
                    "symbol": ack_payload.get("symbol") or order.get("symbol"),
                    "orderId": ack_payload.get("orderId") or order.get("venue_order_id"),
                    "clientOrderId": ack_payload.get("clientOrderId") or order.get("client_order_id"),
                    "transactTime": ack_payload.get("transactTime"),
                    "executionType": "TRADE",
                    "x": "TRADE",
                    "status": ack_payload.get("status"),
                    "X": ack_payload.get("status"),
                },
                source_kind="REST_CREATE_FULL",
            )
            if normalized is not None and _safe_float(normalized.get("qty"), 0.0) > 0:
                rows.append(normalized)
        return rows

    def ingest_user_stream_event(self, *, family: str, environment: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        self.mark_user_stream_status(family=normalized_family, environment=normalized_environment, available=True)
        raw_payload = copy.deepcopy(payload if isinstance(payload, dict) else {})
        runtime_meta = raw_payload.pop("_rtlab_user_stream", {}) if isinstance(raw_payload.get("_rtlab_user_stream"), dict) else {}
        wrapper_payload = runtime_meta.get("raw_wrapper") if isinstance(runtime_meta.get("raw_wrapper"), dict) else raw_payload
        event_payload = raw_payload.get("event") if isinstance(raw_payload.get("event"), dict) else raw_payload
        if not isinstance(event_payload, dict):
            event_payload = {}
        event_name = str(event_payload.get("e") or "").strip()
        order_payload = event_payload
        if normalized_family in {"usdm_futures", "coinm_futures"}:
            order_payload = event_payload.get("o") if isinstance(event_payload.get("o"), dict) else {}
        venue_order_id = str(order_payload.get("orderId") or order_payload.get("i") or "").strip() or None
        client_order_id = str(order_payload.get("clientOrderId") or order_payload.get("c") or order_payload.get("origClientOrderId") or order_payload.get("C") or "").strip() or None
        stored_event = self.db.insert_user_stream_event(
            {
                "created_at": str(runtime_meta.get("received_at") or utc_now_iso()),
                "event_time": _ms_to_iso(event_payload.get("E")) or _ms_to_iso(event_payload.get("T")) or utc_now_iso(),
                "family": normalized_family,
                "environment": normalized_environment,
                "execution_connector": runtime_meta.get("execution_connector"),
                "user_stream_mode": runtime_meta.get("user_stream_mode"),
                "subscription_id": runtime_meta.get("subscription_id"),
                "listen_key": runtime_meta.get("listen_key"),
                "event_name": event_name or "unknown",
                "symbol": _canonical_symbol(event_payload.get("s") or order_payload.get("s")),
                "client_order_id": client_order_id,
                "venue_order_id": venue_order_id,
                "payload_json": wrapper_payload if isinstance(wrapper_payload, dict) else raw_payload,
                "provenance_json": {
                    "source": "user_stream_runtime",
                    "received_at": runtime_meta.get("received_at"),
                    "execution_connector": runtime_meta.get("execution_connector"),
                    "user_stream_mode": runtime_meta.get("user_stream_mode"),
                },
            }
        )
        non_order_events = {
            "outboundAccountPosition",
            "balanceUpdate",
            "externalLockUpdate",
            "ACCOUNT_UPDATE",
            "MARGIN_CALL",
            "listenKeyExpired",
            "eventStreamTerminated",
        }
        if event_name in non_order_events:
            return {
                "ok": True,
                "event_name": event_name,
                "user_stream_event_id": stored_event.get("user_stream_event_id"),
                "account_event": True,
                "degraded_mode": False,
            }
        if event_name == "listStatus":
            return {
                "ok": True,
                "event_name": event_name,
                "user_stream_event_id": stored_event.get("user_stream_event_id"),
                "partial_support": True,
                "notes": ["raw_list_status_persisted"],
                "degraded_mode": False,
            }
        order = None
        if client_order_id:
            order = self.db.order_by_client_order_id(client_order_id)
        if order is None and venue_order_id:
            order = self.db.order_by_venue_order_id(venue_order_id)
        if order is None:
            event_details = {
                "event_name": event_name or "unknown",
                "source_kind": "user_stream_orphan",
                "payload": event_payload,
            }
            self._record_reconcile_event(
                reconcile_type="orphan_order",
                severity="WARN",
                family=normalized_family,
                environment=normalized_environment,
                execution_order_id=None,
                client_order_id=client_order_id,
                details=event_details,
                resolved=False,
            )
            return {
                "ok": False,
                "reason": "local_order_not_found",
                "event_name": event_name,
                "user_stream_event_id": stored_event.get("user_stream_event_id"),
            }
        intent = self.db.intent_by_id(str(order.get("execution_intent_id") or "")) if order.get("execution_intent_id") else None
        updated_order = self.db.upsert_order(
            self._order_row_from_exchange(
                execution_order_id=str(order.get("execution_order_id")),
                execution_intent_id=str(order.get("execution_intent_id") or ""),
                client_order_id=str(order.get("client_order_id") or client_order_id or ""),
                family=normalized_family,
                environment=normalized_environment,
                preview=order,
                ack_payload=order_payload,
                submitted_at=str(order.get("submitted_at") or utc_now_iso()),
                intent=intent,
                existing=order,
            )
        )
        source_type = "WS_EXECUTION_REPORT" if event_name in {"executionReport", "ORDER_TRADE_UPDATE"} else "MANUAL"
        updated_order, live_event, duplicated = self._apply_order_event(
            order=updated_order,
            source_type=source_type,
            payload=order_payload if isinstance(order_payload, dict) else event_payload,
            notes=f"user_stream_{event_name}",
        )
        trade_rows: list[dict[str, Any]] = []
        if not duplicated and normalized_family in {"spot", "margin"} and event_name == "executionReport":
            normalized_trade = self._normalize_trade_payload(
                family=normalized_family,
                order=updated_order,
                row=event_payload,
                source_kind="executionReport_stream",
            )
            if normalized_trade is not None and _safe_float(normalized_trade.get("qty"), 0.0) > 0 and str(event_payload.get("x") or "").upper() == "TRADE":
                trade_rows.append(normalized_trade)
        elif not duplicated and normalized_family in {"usdm_futures", "coinm_futures"} and event_name == "ORDER_TRADE_UPDATE":
            normalized_trade = self._normalize_trade_payload(
                family=normalized_family,
                order=updated_order,
                row=order_payload,
                source_kind="ORDER_TRADE_UPDATE_stream",
            )
            if normalized_trade is not None and _safe_float(normalized_trade.get("qty"), 0.0) > 0 and str(order_payload.get("x") or "").upper() == "TRADE":
                trade_rows.append(normalized_trade)
        materialized = self._materialize_trade_rows(
            order=updated_order,
            intent=intent,
            trade_rows=trade_rows,
            event_source="user_stream_event",
            degraded_mode=False,
        )
        final_order = materialized["order"] if materialized["fills"] else updated_order
        return {
            "ok": True,
            "event_name": event_name,
            "user_stream_event_id": stored_event.get("user_stream_event_id"),
            "live_order_event_id": live_event.get("event_id"),
            "duplicated_event": duplicated,
            "execution_order_id": final_order.get("execution_order_id"),
            "order": final_order,
            "fills": materialized["fills"],
            "degraded_mode": False,
        }

    def _reconcile_single_order(self, order: dict[str, Any]) -> dict[str, Any]:
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        intent = self.db.intent_by_id(str(order.get("execution_intent_id") or "")) if order.get("execution_intent_id") else None
        recon_cfg = self._reconciliation_policy()
        deadlines = self._reconciliation_deadlines()
        stream_state = self._stream_state(family, environment)
        now = _utc_now()
        updated_order = copy.deepcopy(order)
        remote_meta: dict[str, Any] | None = None
        touched_events: list[dict[str, Any]] = []
        remote_order_snapshot: dict[str, Any] | None = None
        remote_trade_rows: list[dict[str, Any]] = []
        remote_trade_meta: dict[str, Any] | None = None

        if environment == "paper":
            materialized = self._materialize_paper_fill(updated_order, intent)
            if materialized["fills"]:
                updated_order = materialized["order"]
            fills = self.db.fills_for_order(str(updated_order.get("execution_order_id")))
            return {
                "order": updated_order,
                "intent": intent,
                "fills": fills,
                "degraded_mode": False,
                "remote_source": {"ok": True, "reason": "paper_local"},
                "remote_order_snapshot": None,
                "remote_trade_rows": [],
                "remote_trade_source": {"ok": True, "reason": "paper_local"},
                "stream_state": stream_state,
                "events": touched_events,
            }

        previous_status = str(updated_order.get("order_status") or "").upper()
        remote_order, remote_meta = self._query_remote_order_snapshot(updated_order)
        if remote_order is not None:
            updated_order = remote_order
            remote_order_snapshot = copy.deepcopy(remote_order)
            remote_status = str(remote_order.get("order_status") or "").upper()
            if remote_status != previous_status:
                touched_events.append(
                    self._record_reconcile_event(
                        reconcile_type="status_mismatch",
                        severity="WARN",
                        family=family,
                        environment=environment,
                        execution_order_id=str(updated_order.get("execution_order_id")),
                        client_order_id=str(updated_order.get("client_order_id") or ""),
                        details={
                            "local_status_before": previous_status,
                            "remote_status": remote_status,
                            "source": "rest_query",
                        },
                        resolved=True,
                    )
                )

        ack_timeout_sec = float(recon_cfg.get("order_ack_timeout_sec") or 0.0)
        submitted_dt = _parse_ts(updated_order.get("submitted_at")) or now
        ack_dt = _parse_ts(updated_order.get("acknowledged_at"))
        ack_age_sec = max(0.0, (now - submitted_dt).total_seconds())
        if ack_dt is None and ack_age_sec >= deadlines["soft_deadline_sec"] and normalize_local_state(updated_order.get("current_local_state")) == "SUBMITTING":
            updated_order = self._mark_order_unknown_pending_reconciliation(
                updated_order,
                source_type="RECOVERY",
                reason="ack_missing_timeout",
                payload={
                    "status": updated_order.get("order_status"),
                    "clientOrderId": updated_order.get("client_order_id"),
                    "ack_age_sec": round(ack_age_sec, 4),
                },
            )
        if ack_dt is None and ack_age_sec >= ack_timeout_sec:
            severity = "BLOCK" if ack_age_sec >= float(recon_cfg.get("orphan_order_block_sec") or ack_timeout_sec) else "WARN"
            touched_events.append(
                self._record_reconcile_event(
                    reconcile_type="ack_missing",
                    severity=severity,
                    family=family,
                    environment=environment,
                    execution_order_id=str(updated_order.get("execution_order_id")),
                    client_order_id=str(updated_order.get("client_order_id") or ""),
                    details={"ack_age_sec": round(ack_age_sec, 4), "source": "reconcile_timeout"},
                    resolved=False,
                )
            )
        else:
            self.db.resolve_reconcile_events(
                reconcile_type="ack_missing",
                execution_order_id=str(updated_order.get("execution_order_id")),
            )

        should_fetch_trades = stream_state["degraded_mode"] or str(updated_order.get("order_status") or "").upper() in {"FILLED", "PARTIALLY_FILLED"} or _safe_float(updated_order.get("executed_qty"), 0.0) > 0
        fills_before = self.db.fills_for_order(str(updated_order.get("execution_order_id")))
        if should_fetch_trades:
            trade_rows, trade_meta = self._fetch_remote_trade_rows(updated_order)
            remote_trade_rows = [copy.deepcopy(row) for row in trade_rows]
            remote_trade_meta = copy.deepcopy(trade_meta)
            income_rows, _ = self._fetch_remote_income_rows(updated_order)
            interest_rows, _ = self._fetch_margin_interest_rows(updated_order)
            touched_events.extend(
                self._reconcile_fill_rows_against_remote(
                    order=updated_order,
                    remote_rows=trade_rows,
                    remote_meta=trade_meta,
                    trigger="RECONCILE_ORDER",
                )
            )
            if trade_rows:
                known_fill_ids = {str(fill.get("execution_fill_id") or "") for fill in fills_before}
                materialized = self._materialize_trade_rows(
                    order=updated_order,
                    intent=intent,
                    trade_rows=trade_rows,
                    event_source="rest_fallback",
                    degraded_mode=stream_state["degraded_mode"],
                    income_rows=income_rows,
                    interest_rows=interest_rows,
                )
                updated_order = materialized["order"]
                new_fill_count = sum(
                    1
                    for fill in materialized["fills"]
                    if str(fill.get("execution_fill_id") or "") not in known_fill_ids
                )
                if new_fill_count > 0:
                    self.db.resolve_reconcile_events(
                        reconcile_type="fill_missing",
                        execution_order_id=str(updated_order.get("execution_order_id")),
                    )
                    touched_events.append(
                        self._record_reconcile_event(
                            reconcile_type="fill_missing",
                            severity="WARN",
                            family=family,
                            environment=environment,
                            execution_order_id=str(updated_order.get("execution_order_id")),
                            client_order_id=str(updated_order.get("client_order_id") or ""),
                            details={
                                "backfilled_count": new_fill_count,
                                "source": trade_meta,
                            },
                            resolved=True,
                        )
                    )

        fills = self.db.fills_for_order(str(updated_order.get("execution_order_id")))
        fill_timeout_sec = float(recon_cfg.get("fill_reconcile_timeout_sec") or 0.0)
        if (
            not fills
            and (str(updated_order.get("order_status") or "").upper() in {"FILLED", "PARTIALLY_FILLED"} or _safe_float(updated_order.get("executed_qty"), 0.0) > 0)
            and ack_age_sec >= fill_timeout_sec
        ):
            severity = "BLOCK" if ack_age_sec >= float(recon_cfg.get("orphan_order_block_sec") or fill_timeout_sec) else "WARN"
            touched_events.append(
                self._record_reconcile_event(
                    reconcile_type="fill_missing",
                    severity=severity,
                    family=family,
                    environment=environment,
                    execution_order_id=str(updated_order.get("execution_order_id")),
                    client_order_id=str(updated_order.get("client_order_id") or ""),
                    details={"fill_age_sec": round(ack_age_sec, 4), "source": "reconcile_timeout"},
                    resolved=False,
                )
            )
        elif fills:
            self.db.resolve_reconcile_events(
                reconcile_type="fill_missing",
                execution_order_id=str(updated_order.get("execution_order_id")),
            )

        if normalize_local_state(updated_order.get("current_local_state")) == "UNKNOWN_PENDING_RECONCILIATION" and ack_age_sec >= deadlines["hard_deadline_sec"]:
            updated_order, live_event, _ = self._apply_order_event(
                order=updated_order,
                source_type="RECOVERY",
                payload={
                    "status": updated_order.get("last_exchange_order_status") or updated_order.get("order_status"),
                    "clientOrderId": updated_order.get("client_order_id"),
                    "ack_age_sec": round(ack_age_sec, 4),
                },
                forced_local_state="MANUAL_REVIEW_REQUIRED",
                notes="unknown_pending_exceeded_hard_deadline",
                unresolved_reason="reconciliation_hard_deadline_exceeded",
                reconciliation_status="UNRESOLVED",
            )
            touched_events.append(
                self._record_reconcile_event(
                    reconcile_type="status_mismatch",
                    severity="BLOCK",
                    family=family,
                    environment=environment,
                    execution_order_id=str(updated_order.get("execution_order_id")),
                    client_order_id=str(updated_order.get("client_order_id") or ""),
                    details={
                        "reason": "manual_review_required_after_hard_deadline",
                        "current_local_state": updated_order.get("current_local_state"),
                        "live_order_event_id": live_event.get("event_id"),
                    },
                    resolved=False,
                )
            )

        costs = self._aggregate_order_costs(order=updated_order, intent=intent, fills=fills)
        estimated_total = _first_number((costs.get("estimated_costs") if isinstance(costs.get("estimated_costs"), dict) else {}).get("total_cost_estimated"))
        realized_total = _first_number((costs.get("realized_costs") if isinstance(costs.get("realized_costs"), dict) else {}).get("total_cost_realized"))
        if estimated_total is not None and realized_total is not None:
            notional = _first_number(
                (costs.get("estimated_costs") if isinstance(costs.get("estimated_costs"), dict) else {}).get("requested_notional"),
                updated_order.get("cum_quote_qty"),
            )
            delta_abs = abs(realized_total - estimated_total)
            delta_bps = ((delta_abs / notional) * 10000.0) if notional and notional > 0 else 0.0
            warn_bps, block_bps = self._slippage_thresholds(family)
            if delta_bps >= warn_bps:
                severity = "BLOCK" if delta_bps >= block_bps else "WARN"
                touched_events.append(
                    self._record_reconcile_event(
                        reconcile_type="cost_mismatch",
                        severity=severity,
                        family=family,
                        environment=environment,
                        execution_order_id=str(updated_order.get("execution_order_id")),
                        client_order_id=str(updated_order.get("client_order_id") or ""),
                        details={
                            "estimated_total_cost": estimated_total,
                            "realized_total_cost": realized_total,
                            "delta_abs": delta_abs,
                            "delta_bps": round(delta_bps, 8),
                        },
                        resolved=False,
                    )
                )
            else:
                self.db.resolve_reconcile_events(
                    reconcile_type="cost_mismatch",
                    execution_order_id=str(updated_order.get("execution_order_id")),
                )

        return {
            "order": updated_order,
            "intent": intent,
            "fills": fills,
            "degraded_mode": bool(stream_state["degraded_mode"]),
            "remote_source": remote_meta,
            "remote_order_snapshot": remote_order_snapshot,
            "remote_trade_rows": remote_trade_rows,
            "remote_trade_source": remote_trade_meta,
            "stream_state": stream_state,
            "events": touched_events,
        }

    def _reconcile_orphan_orders(self, *, family: str, environment: str) -> list[dict[str, Any]]:
        if environment not in {"live", "testnet"}:
            return []
        recon_cfg = self._reconciliation_policy()
        now = _utc_now()
        self.db.resolve_reconcile_events(
            reconcile_type="orphan_order",
            family=family,
            environment=environment,
        )
        items, meta = self._remote_open_orders_snapshot(family=family, environment=environment)
        created: list[dict[str, Any]] = []
        for item in items:
            if item.get("execution_order_id"):
                continue
            submitted_dt = _parse_ts(item.get("submitted_at")) or now
            age_sec = max(0.0, (now - submitted_dt).total_seconds())
            warn_after = float(recon_cfg.get("orphan_order_warn_sec") or 0.0)
            block_after = float(recon_cfg.get("orphan_order_block_sec") or warn_after)
            severity = "INFO"
            if age_sec >= block_after:
                severity = "BLOCK"
            elif age_sec >= warn_after:
                severity = "WARN"
            created.append(
                self._record_reconcile_event(
                    reconcile_type="orphan_order",
                    severity=severity,
                    family=family,
                    environment=environment,
                    execution_order_id=None,
                    client_order_id=str(item.get("client_order_id") or ""),
                    details={
                        "remote_order": item,
                        "remote_source": meta,
                        "orphan_age_sec": round(age_sec, 4),
                    },
                    resolved=False,
                )
            )
        return created

    def _query_remote_order_snapshot(self, order: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        params: dict[str, Any] = {
            "symbol": _canonical_symbol(order.get("symbol")),
            "origClientOrderId": order.get("client_order_id"),
        }
        if order.get("venue_order_id"):
            params["orderId"] = order.get("venue_order_id")
        payload, meta = self._signed_request(
            "GET",
            self._execution_endpoint(family, environment, "query"),
            family=family,
            environment=environment,
            params=params,
        )
        if isinstance(payload, dict):
            updated = self.db.upsert_order(
                self._order_row_from_exchange(
                    execution_order_id=str(order.get("execution_order_id")),
                    execution_intent_id=str(order.get("execution_intent_id") or ""),
                    client_order_id=str(order.get("client_order_id") or ""),
                    family=family,
                    environment=environment,
                    preview=order,
                    ack_payload=payload,
                    submitted_at=str(order.get("submitted_at") or utc_now_iso()),
                    existing=order,
                )
            )
            updated, _event_row, _ = self._apply_order_event(
                order=updated,
                source_type="REST_QUERY_ORDER",
                payload=payload,
                notes="rest_query_order_reconciliation",
            )
            return updated, meta
        return None, meta

    def _remote_open_orders_snapshot(
        self,
        *,
        family: str,
        environment: str,
        symbol: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        params = {"symbol": _canonical_symbol(symbol)} if symbol else {}
        payload, meta = self._signed_request(
            "GET",
            self._execution_endpoint(family, environment, "open_orders"),
            family=family,
            environment=environment,
            params=params,
        )
        rows = payload if isinstance(payload, list) else []
        items: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            local = None
            if row.get("orderId"):
                local = self.db.order_by_venue_order_id(str(row.get("orderId")))
            if local is None and row.get("clientOrderId"):
                local = self.db.order_by_client_order_id(str(row.get("clientOrderId")))
            if local is not None:
                updated = self.db.upsert_order(
                    self._order_row_from_exchange(
                        execution_order_id=str(local.get("execution_order_id")),
                        execution_intent_id=str(local.get("execution_intent_id") or ""),
                        client_order_id=str(local.get("client_order_id") or row.get("clientOrderId") or ""),
                        family=family,
                        environment=environment,
                        preview=local,
                        ack_payload=row,
                        submitted_at=str(local.get("submitted_at") or utc_now_iso()),
                        existing=local,
                    )
                )
                updated, _event_row, _ = self._apply_order_event(
                    order=updated,
                    source_type="REST_OPEN_ORDERS_SNAPSHOT",
                    payload=row,
                    notes="open_orders_snapshot_recovery",
                )
                items.append(updated)
            else:
                items.append(
                    _hydrate_order_row(
                        {
                            "execution_order_id": None,
                            "execution_intent_id": None,
                            "venue_order_id": str(row.get("orderId") or "") or None,
                            "client_order_id": str(row.get("clientOrderId") or ""),
                            "symbol": _canonical_symbol(row.get("symbol")),
                            "family": family,
                            "environment": environment,
                            "current_local_state": "RECOVERED_OPEN",
                            "last_exchange_order_status": str(row.get("status") or "NEW").upper(),
                            "last_execution_type": str(row.get("executionType") or row.get("status") or "NEW").upper(),
                            "order_status": str(row.get("status") or "NEW").upper(),
                            "execution_type_last": str(row.get("executionType") or row.get("status") or "NEW").upper(),
                            "submitted_at": _ms_to_iso(row.get("time")) or utc_now_iso(),
                            "first_submitted_at": _ms_to_iso(row.get("time")) or utc_now_iso(),
                            "acknowledged_at": _ms_to_iso(row.get("updateTime")) or _ms_to_iso(row.get("time")) or utc_now_iso(),
                            "canceled_at": None,
                            "expired_at": None,
                            "reduce_only": row.get("reduceOnly"),
                            "tif": row.get("timeInForce"),
                            "price": _first_number(row.get("price")),
                            "orig_qty": _first_number(row.get("origQty")),
                            "executed_qty": _first_number(row.get("executedQty")) or 0.0,
                            "cum_quote_qty": _first_number(row.get("cummulativeQuoteQty"), row.get("cumQuote")) or 0.0,
                            "avg_fill_price": _first_number(row.get("avgPrice")),
                            "reconciliation_status": "UNRESOLVED",
                            "unresolved_reason": "remote_open_order_without_local_snapshot",
                            "reject_code": None,
                            "reject_reason": None,
                            "raw_ack_json": {},
                            "raw_last_status_json": row,
                            "raw_last_payload_json": row,
                        }
                    )
                    or {}
                )
        return items, meta

    def preflight(self, request: dict[str, Any]) -> dict[str, Any]:
        family = _normalize_family(request.get("family"))
        environment = _normalize_environment(request.get("environment"))
        mode = _normalize_mode(request.get("mode"), environment)
        symbol = _canonical_symbol(request.get("symbol"))
        preflight_started_ms = int(time.time() * 1000)
        warnings: list[str] = []
        blocking: list[str] = []
        fail_closed = False

        if not family or not symbol:
            blocking.append("family_or_symbol_missing")
        if not self._mode_allowed(mode):
            blocking.append(f"mode_disabled:{mode}")
        if family and not _bool((self.router_policy().get("families_enabled") or {}).get(family)):
            blocking.append(f"family_disabled:{family}")

        instrument = self._instrument_row(family, symbol) if family and symbol else None
        if instrument is None and _bool((self.safety_policy().get("preflight") or {}).get("require_instrument_registry_match")):
            blocking.append("instrument_not_in_registry")

        capability = self._capability_snapshot(family, environment) if family else None
        latest_snapshot = self._latest_snapshot(family, environment) if family else None
        request_market_snapshot = request.get("market_snapshot") if isinstance(request.get("market_snapshot"), dict) else None
        quote = self._quote_snapshot(
            family,
            environment,
            symbol,
            request_market_snapshot,
        )

        if instrument is None:
            preview = {
                "symbol": symbol,
                "side": str(request.get("side") or "").upper(),
                "order_type": str(request.get("order_type") or "").upper(),
                "quantity": request.get("quantity"),
                "quote_quantity": request.get("quote_quantity"),
                "limit_price": request.get("price"),
                "stop_price": request.get("stopPrice") if request.get("stopPrice") is not None else request.get("stop_price"),
                "preview_price": request.get("price"),
                "requested_notional": _safe_float(request.get("requested_notional"), 0.0),
                "reduce_only": request.get("reduce_only"),
                "time_in_force": request.get("time_in_force"),
            }
            costs = self._estimated_costs(family=family or "spot", request=request, preview=preview, instrument={})
        else:
            preview = self._normalize_order(instrument, request, quote)
            costs = self._estimated_costs(family=family, request=request, preview=preview, instrument=instrument)
        filter_validation = self._prevalidate_exchange_filters(
            family=family,
            environment=environment,
            mode=mode,
            request=request,
            instrument=instrument,
            latest_snapshot=latest_snapshot,
            quote=quote,
        ) if instrument is not None else None
        if isinstance(filter_validation, dict):
            if isinstance(filter_validation.get("normalized_values"), dict):
                normalized_values = filter_validation.get("normalized_values") or {}
                preview["quantity"] = normalized_values.get("quantity")
                preview["quote_quantity"] = normalized_values.get("quote_quantity")
                preview["limit_price"] = normalized_values.get("limit_price")
                preview["stop_price"] = normalized_values.get("stop_price")
                preview["requested_notional"] = normalized_values.get("requested_notional")
            warnings.extend(filter_validation.get("warnings") or [])
            blocking.extend(filter_validation.get("blocking_reasons") or [])
            if mode == "live" and (filter_validation.get("block") or filter_validation.get("status") == "BLOCK"):
                fail_closed = True

        preflight_cfg = self.safety_policy().get("preflight") if isinstance(self.safety_policy().get("preflight"), dict) else {}
        sizing_cfg = self.safety_policy().get("sizing") if isinstance(self.safety_policy().get("sizing"), dict) else {}
        margin_cfg = self.safety_policy().get("margin") if isinstance(self.safety_policy().get("margin"), dict) else {}
        cost_policy = self._cost_stack_policy()
        estimation_cfg = cost_policy.get("estimation") if isinstance(cost_policy.get("estimation"), dict) else {}

        if _bool(preflight_cfg.get("require_policy_loaded")):
            source = self.policy_source()
            if not bool(source["execution_safety"]["valid"]) or not bool(source["execution_router"]["valid"]):
                blocking.append("execution_policy_not_loaded")

        supported_types = (self.router_policy().get("first_iteration_supported_order_types") or {}).get(family) or []
        if supported_types and str(preview.get("order_type") or "").upper() not in {str(item).upper() for item in supported_types}:
            blocking.append(f"unsupported_order_type:{preview.get('order_type')}")

        allowed_tif = (self.router_policy().get("time_in_force_allowed") or {}).get(family) or []
        tif = str(preview.get("time_in_force") or "").upper()
        if tif and allowed_tif and tif not in {str(item).upper() for item in allowed_tif}:
            blocking.append(f"unsupported_time_in_force:{tif}")

        if instrument is not None:
            status = str(instrument.get("status") or "").upper()
            if status != "TRADING":
                blocking.append("instrument_status_not_operational")
            if environment == "live" and _bool(preflight_cfg.get("require_live_eligible")) and not _bool(instrument.get("live_eligible")):
                blocking.append("instrument_not_live_eligible")
            if environment == "testnet" and not _bool(instrument.get("testnet_eligible")):
                blocking.append("instrument_not_testnet_eligible")
            filters = instrument.get("filter_summary") if isinstance(instrument.get("filter_summary"), dict) else {}
            notional_filters = filters.get("notional") if isinstance(filters.get("notional"), dict) else {}
            min_notional = _first_number(
                (notional_filters or {}).get("min_notional"),
                ((filters.get("min_notional") if isinstance(filters.get("min_notional"), dict) else {}) or {}).get("min_notional"),
            )
            buffer_pct = _safe_float(sizing_cfg.get("min_notional_buffer_pct_above_exchange_min"))
            min_required = 0.0 if min_notional is None else min_notional * (1.0 + buffer_pct / 100.0)
            if _safe_float(preview.get("requested_notional"), 0.0) < min_required:
                blocking.append("notional_below_exchange_min_with_buffer")

        max_notional = _safe_float(sizing_cfg.get("max_notional_per_order_usd"))
        if _safe_float(preview.get("requested_notional"), 0.0) > max_notional:
            blocking.append("max_notional_per_order_exceeded")

        open_symbol = len(self.db.open_orders(family=family, symbol=symbol))
        open_total = len(self.db.open_orders())
        if open_symbol >= int(sizing_cfg.get("max_open_orders_per_symbol") or 0):
            blocking.append("max_open_orders_per_symbol_reached")
        if open_total >= int(sizing_cfg.get("max_open_orders_total") or 0):
            blocking.append("max_open_orders_total_reached")

        membership = self._universe_membership(family, symbol) if family and symbol else {"matched": False, "universes": []}
        if environment in {"live", "testnet"} and _bool(preflight_cfg.get("require_universe_membership_for_live")) and not _bool(membership.get("matched")):
            blocking.append("symbol_not_in_active_universe")

        if environment in {"live", "testnet"} and _bool(preflight_cfg.get("require_capability_snapshot")) and capability is None:
            blocking.append("capability_snapshot_missing")
        if capability is not None and not _bool(capability.get("can_trade")) and environment in {"live", "testnet"}:
            blocking.append("account_cannot_trade")
        if family == "margin" and environment in {"live", "testnet"} and capability is not None and not _bool(capability.get("can_margin")):
            blocking.append("margin_capability_missing")

        freshness = self._freshness_payload(latest_snapshot.get("fetched_at") if latest_snapshot else None)
        if _bool(preflight_cfg.get("require_snapshot_fresh")):
            if freshness.get("status") == "missing":
                blocking.append("instrument_snapshot_missing")
                if mode == "live":
                    fail_closed = True
            elif freshness.get("status") == "block":
                blocking.append("instrument_snapshot_stale")
                if mode == "live":
                    fail_closed = True
            elif freshness.get("status") == "warn":
                warnings.append("instrument_snapshot_near_stale")

        quote_ts_ms = quote.get("quote_ts_ms")
        if quote_ts_ms is None:
            blocking.append("quote_snapshot_missing")
        else:
            quote_age_reference_ms = int(time.time() * 1000)
            if mode == "paper" and isinstance(request_market_snapshot, dict):
                # Paper submits carry a request-scoped quote snapshot for the
                # current cycle. Measure freshness against preflight start so
                # local prechecks do not consume the full stale budget before
                # the simulated order hits the paper ledger.
                quote_age_reference_ms = preflight_started_ms
            age_ms = max(0, quote_age_reference_ms - int(quote_ts_ms))
            if age_ms >= int(preflight_cfg.get("quote_stale_block_ms") or 0):
                blocking.append("quote_stale")
                if mode == "live":
                    fail_closed = True

        orderbook_ts_ms = quote.get("orderbook_ts_ms")
        if orderbook_ts_ms is not None:
            orderbook_age_reference_ms = int(time.time() * 1000)
            if mode == "paper" and isinstance(request_market_snapshot, dict):
                orderbook_age_reference_ms = preflight_started_ms
            ob_age_ms = max(0, orderbook_age_reference_ms - int(orderbook_ts_ms))
            if ob_age_ms >= int(preflight_cfg.get("orderbook_stale_block_ms") or 0):
                blocking.append("orderbook_stale")
                if mode == "live":
                    fail_closed = True
            elif ob_age_ms >= int(preflight_cfg.get("orderbook_stale_warn_ms") or 0):
                warnings.append("orderbook_stale_warn")

        fee_state = self._fee_source_state(family, environment) if family else {"available": False, "fresh": False, "latest": None}
        if mode == "live" and _bool(preflight_cfg.get("reject_if_missing_fee_source_in_live")) and not _bool(fee_state.get("available")):
            blocking.append("fee_source_missing_in_live")
            fail_closed = True
        elif mode == "live" and not _bool(fee_state.get("fresh")):
            warnings.append("fee_source_stale")

        if mode == "live" and _bool(estimation_cfg.get("block_if_missing_real_cost_source_in_live", True)) and not _bool(fee_state.get("available")):
            fail_closed = True

        margin_level = self._margin_levels.get(environment)
        if family == "margin" and _bool(margin_cfg.get("require_margin_level_visible")):
            if not isinstance(margin_level, dict) or margin_level.get("level") is None:
                blocking.append("margin_level_missing")
                if mode == "live":
                    fail_closed = True
            else:
                level = _safe_float(margin_level.get("level"), 0.0)
                if level < _safe_float(margin_cfg.get("block_margin_level_below")):
                    blocking.append("margin_level_blocked")
                    if mode == "live":
                        fail_closed = True
                elif level < _safe_float(margin_cfg.get("warn_margin_level_below")):
                    warnings.append("margin_level_warn")

        slip_warn, slip_block = self._slippage_thresholds(family)
        slip_bps = _safe_float(costs.get("slippage_bps"), 0.0)
        if slip_bps >= slip_block:
            blocking.append("slippage_block_threshold")
        elif slip_bps >= slip_warn:
            warnings.append("slippage_warn_threshold")

        if mode == "live":
            critical_live_reasons = {
                "instrument_not_in_registry",
                "symbol_not_in_active_universe",
                "capability_snapshot_missing",
                "account_cannot_trade",
                "margin_capability_missing",
                "instrument_snapshot_missing",
                "instrument_snapshot_stale",
                "quote_snapshot_missing",
                "quote_stale",
                "orderbook_stale",
                "fee_source_missing_in_live",
                "margin_level_missing",
                "margin_level_blocked",
                "missing_basic_filters",
                "instrument_status_not_operational",
                "instrument_not_live_eligible",
            }
            if critical_live_reasons.intersection(blocking):
                fail_closed = True

        return {
            "allowed": not blocking,
            "warnings": list(dict.fromkeys(warnings)),
            "blocking_reasons": list(dict.fromkeys(blocking)),
            "normalized_order_preview": preview,
            "filter_validation": filter_validation,
            "estimated_costs": costs,
            "policy_source": self.policy_source(),
            "snapshot_source": {
                "snapshot_id": (latest_snapshot or {}).get("snapshot_id"),
                "fetched_at": (latest_snapshot or {}).get("fetched_at"),
                "freshness": freshness,
                "exchange_filters": self._exchange_filter_freshness(family, environment) if family else {},
                "universe_membership": membership,
            },
            "capability_source": {
                "capability_snapshot_id": (capability or {}).get("capability_snapshot_id"),
                "capability_source": (capability or {}).get("capability_source"),
                "can_trade": _bool((capability or {}).get("can_trade")),
            },
            "fail_closed": fail_closed,
        }

    def _cancel_open_orders_for_kill_switch(
        self,
        *,
        family: str | None = None,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        target_family = _normalize_family(family) if family else None
        target_symbol = _canonical_symbol(symbol) if symbol else None
        families = [target_family] if target_family else ["spot", "margin", "usdm_futures", "coinm_futures"]
        for family_name in families:
            for environment in ("live", "testnet"):
                try:
                    self._remote_open_orders_snapshot(
                        family=family_name,
                        environment=environment,
                        symbol=target_symbol,
                    )
                except Exception:
                    continue
        local_open = [
            row
            for row in self.db.open_orders(family=target_family, symbol=target_symbol)
            if (not target_family or _normalize_family(row.get("family")) == target_family)
            and (not target_symbol or _canonical_symbol(row.get("symbol")) == target_symbol)
        ]
        grouped = sorted(
            {
                (
                    _normalize_family(row.get("family")),
                    _normalize_environment(row.get("environment")),
                    _canonical_symbol(row.get("symbol")),
                )
                for row in local_open
                if row.get("symbol")
            }
        )
        actions: list[dict[str, Any]] = []
        for family_name, environment, symbol_name in grouped:
            try:
                result = self.cancel_all(
                    family=family_name,
                    environment=environment,
                    symbol=symbol_name,
                )
                actions.append(
                    {
                        "kind": "cancel_all",
                        "family": family_name,
                        "environment": environment,
                        "symbol": symbol_name,
                        "ok": True,
                        "canceled_count": int(result.get("canceled_count") or 0),
                        "remote_source": result.get("remote_source"),
                    }
                )
            except Exception as exc:
                actions.append(
                    {
                        "kind": "cancel_all",
                        "family": family_name,
                        "environment": environment,
                        "symbol": symbol_name,
                        "ok": False,
                        "error": str(exc),
                    }
                )
        return actions

    def trip_kill_switch(
        self,
        *,
        trigger_type: str,
        severity: str = "BLOCK",
        family: str | None = None,
        symbol: str | None = None,
        reason: str,
    ) -> dict[str, Any]:
        status_before = self.kill_switch_status()
        if status_before.get("active"):
            return {
                **status_before,
                "trip_recorded": False,
                "event": status_before.get("active_event"),
                "auto_actions": ((status_before.get("active_event") or {}).get("auto_actions_json") if isinstance(status_before.get("active_event"), dict) else []),
            }
        auto_actions: list[dict[str, Any]] = []
        if _bool(self._kill_switch_policy().get("auto_cancel_all_on_trip")):
            auto_actions = self._cancel_open_orders_for_kill_switch(family=family, symbol=symbol)
        event = self.db.trip_kill_switch(
            trigger_type=trigger_type,
            severity=severity,
            family=_normalize_family(family) if family else None,
            symbol=_canonical_symbol(symbol) if symbol else None,
            reason=reason,
            auto_actions=auto_actions,
        )
        return {
            **self.kill_switch_status(),
            "trip_recorded": True,
            "event": event,
            "auto_actions": auto_actions,
        }

    def reset_kill_switch(self, *, reason: str = "manual_reset") -> dict[str, Any]:
        self.db.reset_kill_switch(reason=reason)
        return {
            **self.kill_switch_status(),
            "reset_applied": True,
            "reset_reason": reason,
        }

    def _live_submit_safety_gate(
        self,
        *,
        family: str,
        environment: str,
        symbol: str,
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        target_symbol = _canonical_symbol(symbol)
        ks_cfg = self._kill_switch_policy()
        kill_switch = self.kill_switch_status()
        blockers: list[str] = []
        warnings: list[str] = []
        auto_trip: dict[str, Any] | None = None

        if kill_switch.get("active"):
            blockers.append("kill_switch_active")
        elif kill_switch.get("cooldown_active"):
            blockers.append("kill_switch_cooldown_active")

        if normalized_environment in {"live", "testnet"}:
            reject_count = self._recent_rejected_order_count(window_sec=300.0)
            reject_threshold = max(0, int(_safe_float(ks_cfg.get("critical_rejects_5m_block"), 0.0)))
            if reject_threshold > 0 and reject_count >= reject_threshold:
                blockers.append("reject_storm_block")

            failed_submit_count = self._consecutive_failed_submit_count()
            failed_submit_threshold = max(0, int(_safe_float(ks_cfg.get("consecutive_failed_submits_block"), 0.0)))
            if failed_submit_threshold > 0 and failed_submit_count >= failed_submit_threshold:
                blockers.append("consecutive_failed_submit_block")

            repeated_mismatch_count = self._repeated_reconcile_mismatch_count()
            repeated_mismatch_threshold = max(
                0,
                int(_safe_float(ks_cfg.get("repeated_reconcile_mismatch_block_count"), 0.0)),
            )
            if repeated_mismatch_threshold > 0 and repeated_mismatch_count >= repeated_mismatch_threshold:
                blockers.append("repeated_reconcile_mismatch_block")

            if blockers and _bool(ks_cfg.get("enabled")) and not kill_switch.get("active"):
                auto_trip_reason = next(
                    (
                        item
                        for item in blockers
                        if item in {
                            "reject_storm_block",
                            "consecutive_failed_submit_block",
                            "repeated_reconcile_mismatch_block",
                        }
                    ),
                    None,
                )
                if auto_trip_reason:
                    auto_trip = self.trip_kill_switch(
                        trigger_type=auto_trip_reason,
                        severity="BLOCK",
                        family=normalized_family,
                        symbol=target_symbol,
                        reason=auto_trip_reason,
                    )
                    kill_switch = self.kill_switch_status()
                    blockers = sorted(set([*blockers, "kill_switch_active"]))
        else:
            reject_count = 0
            reject_threshold = max(0, int(_safe_float(ks_cfg.get("critical_rejects_5m_block"), 0.0)))
            failed_submit_count = self._consecutive_failed_submit_count()
            failed_submit_threshold = max(0, int(_safe_float(ks_cfg.get("consecutive_failed_submits_block"), 0.0)))
            repeated_mismatch_count = self._repeated_reconcile_mismatch_count()
            repeated_mismatch_threshold = max(
                0,
                int(_safe_float(ks_cfg.get("repeated_reconcile_mismatch_block_count"), 0.0)),
            )

        if kill_switch.get("cooldown_active") and not kill_switch.get("active"):
            warnings.append("kill_switch_recently_reset")

        return {
            "blocking_reasons": list(dict.fromkeys(blockers)),
            "warnings": list(dict.fromkeys(warnings)),
            "kill_switch": kill_switch,
            "auto_trip": auto_trip,
            "reject_storm_count_5m": reject_count,
            "reject_storm_threshold": reject_threshold,
            "consecutive_failed_submit_count": failed_submit_count,
            "consecutive_failed_submit_threshold": failed_submit_threshold,
            "repeated_reconcile_mismatch_count": repeated_mismatch_count,
            "repeated_reconcile_mismatch_threshold": repeated_mismatch_threshold,
        }

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = copy.deepcopy(payload)
        preflight = self.preflight(request)
        normalized = preflight.get("normalized_order_preview") if isinstance(preflight.get("normalized_order_preview"), dict) else {}
        estimated_costs = preflight.get("estimated_costs") if isinstance(preflight.get("estimated_costs"), dict) else {}
        stored_request = copy.deepcopy(request)
        stored_request["_preflight_context"] = {
            "filter_validation": copy.deepcopy(preflight.get("filter_validation")),
            "normalized_order_preview": copy.deepcopy(normalized),
            "snapshot_source": copy.deepcopy(preflight.get("snapshot_source")),
        }
        family = _normalize_family(request.get("family"))
        environment = _normalize_environment(request.get("environment"))
        mode = _normalize_mode(request.get("mode"), environment)
        submitted_at = utc_now_iso()
        safety_gate = self._live_submit_safety_gate(
            family=family,
            environment=environment,
            symbol=normalized.get("symbol") or request.get("symbol") or "",
        )
        order_gate = self._block_new_submit_for_unresolved_orders(
            family=family,
            environment=environment,
            bot_id=str(request.get("bot_id") or "").strip() or None,
            symbol=normalized.get("symbol") or request.get("symbol") or "",
        )
        reconciliation_gate = self._block_new_submit_for_reconciliation_cases(
            family=family,
            environment=environment,
            bot_id=str(request.get("bot_id") or "").strip() or None,
            symbol=normalized.get("symbol") or request.get("symbol") or "",
        )

        intent = self.db.insert_intent(
            {
                "venue": "binance",
                "family": family,
                "environment": environment,
                "mode": mode,
                "strategy_id": request.get("strategy_id"),
                "bot_id": request.get("bot_id"),
                "signal_id": request.get("signal_id"),
                "symbol": normalized.get("symbol") or _canonical_symbol(request.get("symbol")),
                "side": normalized.get("side") or str(request.get("side") or "").upper(),
                "order_type": normalized.get("order_type") or str(request.get("order_type") or "").upper(),
                "time_in_force": normalized.get("time_in_force"),
                "quantity": normalized.get("quantity"),
                "quote_quantity": normalized.get("quote_quantity"),
                "limit_price": normalized.get("limit_price"),
                "reduce_only": normalized.get("reduce_only"),
                "requested_notional": estimated_costs.get("requested_notional"),
                "estimated_fee": estimated_costs.get("exchange_fee_estimated"),
                "estimated_slippage_bps": estimated_costs.get("slippage_bps"),
                "estimated_total_cost": estimated_costs.get("total_cost_estimated"),
                "preflight_status": "blocked" if not _bool(preflight.get("allowed")) else "allowed",
                "preflight_errors_json": preflight.get("blocking_reasons") or [],
                "policy_hash": self.policy_hash(),
                "snapshot_id": ((preflight.get("snapshot_source") or {}).get("snapshot_id") if isinstance(preflight.get("snapshot_source"), dict) else None),
                "capability_snapshot_id": ((preflight.get("capability_source") or {}).get("capability_snapshot_id") if isinstance(preflight.get("capability_source"), dict) else None),
                "raw_request_json": stored_request,
            }
        )

        if (
            not _bool(preflight.get("allowed"))
            or bool(safety_gate.get("blocking_reasons"))
            or bool(order_gate.get("blocking_reasons"))
            or bool(reconciliation_gate.get("blocking_reasons"))
        ):
            blocking_reasons = list(preflight.get("blocking_reasons") or [])
            blocking_reasons.extend(safety_gate.get("blocking_reasons") or [])
            blocking_reasons.extend(order_gate.get("blocking_reasons") or [])
            blocking_reasons.extend(reconciliation_gate.get("blocking_reasons") or [])
            warnings = list(preflight.get("warnings") or [])
            warnings.extend(safety_gate.get("warnings") or [])
            warnings.extend(order_gate.get("warnings") or [])
            warnings.extend(reconciliation_gate.get("warnings") or [])
            self.db.update_intent_submission(
                str(intent.get("execution_intent_id")),
                preflight_status="blocked",
                preflight_errors_json=list(dict.fromkeys(blocking_reasons)),
            )
            return {
                "execution_intent_id": intent.get("execution_intent_id"),
                "execution_order_id": None,
                "client_order_id": intent.get("client_order_id"),
                "family": family,
                "environment": environment,
                "mode": mode,
                "order_status": "BLOCKED",
                "estimated_costs": estimated_costs,
                "fail_closed": _bool(preflight.get("fail_closed")) or mode == "live",
                "warnings": list(dict.fromkeys(warnings)),
                "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
                "preflight": preflight,
                "live_safety_gate": safety_gate,
                "live_order_gate": order_gate,
                "reconciliation_gate": reconciliation_gate,
            }

        params, local_blocking = self._build_submit_params(
            family=family,
            environment=environment,
            preview=normalized,
            client_order_id=str(intent.get("client_order_id")),
        )
        if local_blocking:
            self.db.update_intent_submission(
                str(intent.get("execution_intent_id")),
                preflight_status="blocked",
                preflight_errors_json=list(local_blocking),
            )
            return {
                "execution_intent_id": intent.get("execution_intent_id"),
                "execution_order_id": None,
                "client_order_id": intent.get("client_order_id"),
                "family": family,
                "environment": environment,
                "mode": mode,
                "order_status": "BLOCKED",
                "estimated_costs": estimated_costs,
                "fail_closed": mode == "live",
                "warnings": [
                    *(preflight.get("warnings") or []),
                    *(safety_gate.get("warnings") or []),
                    *(order_gate.get("warnings") or []),
                    *(reconciliation_gate.get("warnings") or []),
                ],
                "blocking_reasons": list(local_blocking),
                "preflight": preflight,
                "live_safety_gate": safety_gate,
                "live_order_gate": order_gate,
                "reconciliation_gate": reconciliation_gate,
            }

        order = self.db.upsert_order(
            {
                "execution_intent_id": str(intent.get("execution_intent_id")),
                "exchange": "binance",
                "market_type": family,
                "strategy_id": intent.get("strategy_id"),
                "bot_id": intent.get("bot_id"),
                "signal_id": intent.get("signal_id"),
                "client_order_id": str(intent.get("client_order_id")),
                "symbol": normalized.get("symbol") or _canonical_symbol(request.get("symbol")),
                "family": family,
                "environment": environment,
                "requested_qty": normalized.get("quantity"),
                "requested_quote_order_qty": normalized.get("quote_quantity"),
                "requested_price": normalized.get("limit_price"),
                "requested_stop_price": normalized.get("stop_price"),
                "requested_trailing_delta": normalized.get("trailing_delta"),
                "requested_stp_mode": normalized.get("stp_mode"),
                "requested_new_order_resp_type": params.get("newOrderRespType"),
                "current_local_state": "INTENT_CREATED",
                "order_status": "CREATED",
                "submitted_at": submitted_at,
                "first_submitted_at": submitted_at,
                "price": normalized.get("limit_price"),
                "orig_qty": normalized.get("quantity"),
                "reduce_only": normalized.get("reduce_only"),
                "tif": normalized.get("time_in_force"),
                "raw_ack_json": {},
                "raw_last_status_json": {"status": "CREATED"},
                "raw_last_payload_json": {"source": "local_intent", "request": stored_request},
                "reconciliation_status": "PENDING",
            }
        )
        order, _intent_event, _ = self._apply_order_event(
            order=order,
            source_type="LOCAL_INTENT",
            forced_local_state="INTENT_CREATED",
            notes="intent_persisted_before_submit",
            event_time_local=submitted_at,
        )
        order, _precheck_event, _ = self._apply_order_event(
            order=order,
            source_type="LOCAL_INTENT",
            forced_local_state="PRECHECK_PASSED",
            notes="precheck_passed_before_submit",
            event_time_local=submitted_at,
        )
        order, _submitting_event, _ = self._apply_order_event(
            order=order,
            source_type="LOCAL_INTENT",
            forced_local_state="SUBMITTING",
            notes="submit_initiated",
            event_time_local=submitted_at,
        )
        self.db.update_intent_submission(
            str(intent.get("execution_intent_id")),
            submitted_at=submitted_at,
            preflight_status="submitted",
        )

        if environment == "paper":
            order = self.db.upsert_order(
                self._order_row_from_exchange(
                    execution_order_id=str(order.get("execution_order_id")),
                    execution_intent_id=str(intent.get("execution_intent_id")),
                    client_order_id=str(intent.get("client_order_id")),
                    family=family,
                    environment=environment,
                    preview=normalized,
                    ack_payload=self._paper_ack_payload(normalized, str(intent.get("client_order_id")), submitted_at),
                    submitted_at=submitted_at,
                    intent=intent,
                    acknowledged_at=submitted_at,
                    existing=order,
                )
            )
            order, _ack_event, _ = self._apply_order_event(
                order=order,
                source_type="REST_CREATE_RESPONSE",
                payload=order.get("raw_ack_json") if isinstance(order.get("raw_ack_json"), dict) else {},
                notes="paper_local_ack",
            )
            return {
                "execution_intent_id": intent.get("execution_intent_id"),
                "execution_order_id": order.get("execution_order_id"),
                "client_order_id": order.get("client_order_id"),
                "family": family,
                "environment": environment,
                "mode": mode,
                "order_status": order.get("order_status"),
                "current_local_state": order.get("current_local_state"),
                "estimated_costs": estimated_costs,
                "fail_closed": False,
                "warnings": [
                    *(preflight.get("warnings") or []),
                    *(safety_gate.get("warnings") or []),
                    *(order_gate.get("warnings") or []),
                    *(reconciliation_gate.get("warnings") or []),
                ],
                "blocking_reasons": [],
                "reconciliation_gate": reconciliation_gate,
            }

        endpoint = self._execution_endpoint(family, environment, "submit")
        ack_payload, meta = self._signed_request(
            "POST",
            endpoint,
            family=family,
            environment=environment,
            params=params,
        )
        if not isinstance(ack_payload, dict):
            if self._is_unknown_exchange_result(meta):
                order = self._mark_order_unknown_pending_reconciliation(
                    order,
                    source_type="REST_CREATE_RESPONSE",
                    reason=str(meta.get("reason") or "unknown_submit_result"),
                    payload={
                        "status": order.get("order_status"),
                        "clientOrderId": order.get("client_order_id"),
                        "meta": meta,
                    },
                )
                reconcile_result = self._reconcile_single_order(order)
                order = reconcile_result["order"]
                return {
                    "execution_intent_id": intent.get("execution_intent_id"),
                    "execution_order_id": order.get("execution_order_id"),
                    "client_order_id": order.get("client_order_id"),
                    "family": family,
                    "environment": environment,
                    "mode": mode,
                    "order_status": order.get("order_status"),
                    "current_local_state": order.get("current_local_state"),
                    "estimated_costs": estimated_costs,
                    "fail_closed": mode == "live",
                    "warnings": [
                        *(preflight.get("warnings") or []),
                        *(order_gate.get("warnings") or []),
                        *(reconciliation_gate.get("warnings") or []),
                    ],
                    "blocking_reasons": [str(meta.get("reason") or "unknown_submit_result")],
                    "submit_meta": meta,
                    "remote_source": reconcile_result.get("remote_source"),
                    "reconciliation_gate": reconciliation_gate,
                }
            order, _reject_event, _ = self._apply_order_event(
                order=order,
                source_type="REST_CREATE_RESPONSE",
                payload={
                    "status": "REJECTED",
                    "executionType": "REJECTED",
                    "clientOrderId": order.get("client_order_id"),
                    "msg": str(meta.get("reason") or "submit_failed"),
                    "meta": meta,
                },
                notes="rest_submit_failed",
            )
            self.db.update_intent_submission(
                str(intent.get("execution_intent_id")),
                preflight_status="submit_failed",
                preflight_errors_json=[str(meta.get("reason") or "submit_failed")],
            )
            return {
                "execution_intent_id": intent.get("execution_intent_id"),
                "execution_order_id": order.get("execution_order_id"),
                "client_order_id": order.get("client_order_id"),
                "family": family,
                "environment": environment,
                "mode": mode,
                "order_status": order.get("order_status"),
                "current_local_state": order.get("current_local_state"),
                "estimated_costs": estimated_costs,
                "fail_closed": mode == "live",
                "warnings": [
                    *(preflight.get("warnings") or []),
                    *(reconciliation_gate.get("warnings") or []),
                ],
                "blocking_reasons": [str(meta.get("reason") or "submit_failed")],
                "submit_meta": meta,
                "reconciliation_gate": reconciliation_gate,
            }

        order = self.db.upsert_order(
            self._order_row_from_exchange(
                execution_order_id=str(order.get("execution_order_id")),
                execution_intent_id=str(intent.get("execution_intent_id")),
                client_order_id=str(intent.get("client_order_id")),
                family=family,
                environment=environment,
                preview=normalized,
                ack_payload=ack_payload,
                submitted_at=submitted_at,
                intent=intent,
                existing=order,
            )
        )
        order, _ack_event, _ = self._apply_order_event(
            order=order,
            source_type="REST_CREATE_RESPONSE",
            payload=ack_payload,
            notes="rest_submit_acknowledged",
        )
        create_full_materialized = self._materialize_trade_rows(
            order=order,
            intent=intent,
            trade_rows=self._trade_rows_from_create_response(
                family=family,
                order=order,
                ack_payload=ack_payload,
            ),
            event_source="rest_create_full",
            degraded_mode=False,
        )
        if create_full_materialized["fills"]:
            order = create_full_materialized["order"]
        heartbeat_meta = None
        if family in {"usdm_futures", "coinm_futures"} and environment in {"live", "testnet"}:
            heartbeat_meta = self._arm_futures_auto_cancel_heartbeat(
                family=family,
                environment=environment,
                symbol=normalized.get("symbol") or request.get("symbol") or "",
            )
        return {
            "execution_intent_id": intent.get("execution_intent_id"),
            "execution_order_id": order.get("execution_order_id"),
            "client_order_id": order.get("client_order_id"),
            "family": family,
            "environment": environment,
            "mode": mode,
            "order_status": order.get("order_status"),
            "current_local_state": order.get("current_local_state"),
            "estimated_costs": estimated_costs,
            "fail_closed": False,
            "warnings": [
                *(preflight.get("warnings") or []),
                *(safety_gate.get("warnings") or []),
                *(order_gate.get("warnings") or []),
                *(reconciliation_gate.get("warnings") or []),
            ],
            "blocking_reasons": [],
            "submit_meta": {**meta, "futures_auto_cancel": heartbeat_meta},
            "reconciliation_gate": reconciliation_gate,
        }

    def list_orders(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
        strategy_id: str | None = None,
        bot_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family) if family else None
        normalized_environment = _normalize_environment(environment) if environment else None
        items = self.db.list_orders(
            family=normalized_family,
            environment=normalized_environment,
            symbol=symbol,
            status=status,
            strategy_id=strategy_id,
            bot_id=bot_id,
            limit=limit,
            offset=offset,
        )
        remote_snapshot: list[dict[str, Any]] = []
        remote_meta: dict[str, Any] | None = None
        if normalized_family and normalized_environment in {"live", "testnet"}:
            remote_snapshot, remote_meta = self._remote_open_orders_snapshot(
                family=normalized_family,
                environment=normalized_environment,
                symbol=symbol,
            )
            items = self.db.list_orders(
                family=normalized_family,
                environment=normalized_environment,
                symbol=symbol,
                status=status,
                strategy_id=strategy_id,
                bot_id=bot_id,
                limit=limit,
                offset=offset,
            )
        return {
            "items": items,
            "count": len(items),
            "filters": {
                "family": normalized_family,
                "environment": normalized_environment,
                "symbol": _canonical_symbol(symbol) if symbol else None,
                "status": str(status or "").upper() or None,
                "strategy_id": strategy_id,
                "bot_id": bot_id,
                "limit": int(limit),
                "offset": int(offset),
            },
            "remote_open_orders": remote_snapshot,
            "remote_source": remote_meta,
        }

    def _live_order_summary_row(self, order: dict[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(order)
        current_local_state = normalize_local_state(payload.get("current_local_state"))
        requested_qty = _first_number(payload.get("requested_qty"), payload.get("orig_qty"))
        executed_qty = _safe_float(payload.get("executed_qty"), 0.0)
        filled_pct = ((executed_qty / requested_qty) * 100.0) if requested_qty and requested_qty > 0 else None
        payload.update(
            {
                "local_order_id": payload.get("execution_order_id"),
                "exchange_order_id": payload.get("venue_order_id"),
                "current_local_state": current_local_state,
                "last_exchange_order_status": payload.get("last_exchange_order_status") or payload.get("order_status"),
                "last_execution_type": payload.get("last_execution_type") or payload.get("execution_type_last"),
                "terminal": is_terminal_local_state(current_local_state),
                "filled_pct": round(filled_pct, 8) if filled_pct is not None else None,
                "timeline_size": len(self.db.live_order_events_for_order(str(payload.get("execution_order_id")))),
            }
        )
        return payload

    def _live_fill_summary_row(self, fill: dict[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(fill)
        price = _safe_float(payload.get("price"), 0.0)
        qty = _safe_float(payload.get("qty"), 0.0)
        quote_qty = _first_number(payload.get("quote_qty"), payload.get("last_quote_qty"))
        if quote_qty is None and price > 0 and qty > 0:
            quote_qty = price * qty
        payload.update(
            {
                "fill_id": payload.get("execution_fill_id"),
                "local_order_id": payload.get("local_order_id") or payload.get("execution_order_id"),
                "maker_bool": payload.get("maker"),
                "fill_notional": quote_qty,
                "reconciled": str(payload.get("reconciliation_status") or "").upper() == "RECONCILED",
                "discrepancies": copy.deepcopy(payload.get("discrepancy_json") or {}),
            }
        )
        return payload

    def list_live_orders(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        bot_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        items = self.db.list_orders(
            family=_normalize_family(family) if family else None,
            environment=_normalize_environment(environment) if environment else None,
            symbol=symbol,
            bot_id=bot_id,
            limit=limit,
            offset=offset,
        )
        rows = [self._live_order_summary_row(item) for item in items]
        return {
            "items": rows,
            "count": len(rows),
            "filters": {
                "family": _normalize_family(family) if family else None,
                "environment": _normalize_environment(environment) if environment else None,
                "symbol": _canonical_symbol(symbol) if symbol else None,
                "bot_id": bot_id,
                "limit": int(limit),
                "offset": int(offset),
            },
        }

    def list_live_fills(
        self,
        *,
        execution_order_id: str | None = None,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        reconciliation_status: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = self.db.list_fills(
            execution_order_id=execution_order_id,
            family=_normalize_family(family) if family else None,
            environment=_normalize_environment(environment) if environment else None,
            symbol=_canonical_symbol(symbol) if symbol else None,
            reconciliation_status=str(reconciliation_status or "").upper() or None,
            limit=limit,
            offset=offset,
        )
        items = [self._live_fill_summary_row(row) for row in rows]
        return {
            "items": items,
            "count": len(items),
            "filters": {
                "execution_order_id": execution_order_id,
                "family": _normalize_family(family) if family else None,
                "environment": _normalize_environment(environment) if environment else None,
                "symbol": _canonical_symbol(symbol) if symbol else None,
                "reconciliation_status": str(reconciliation_status or "").upper() or None,
                "limit": int(limit),
                "offset": int(offset),
            },
        }

    def live_fill_detail(self, execution_fill_id: str) -> dict[str, Any] | None:
        fill = self.db.fill_by_id(execution_fill_id)
        if fill is None:
            return None
        execution_order_id = str(fill.get("execution_order_id") or "")
        order = self.db.order_by_id(execution_order_id) if execution_order_id else None
        discrepancy_events = [
            row
            for row in self.db.reconcile_events_for_order(execution_order_id)
            if str(row.get("reconcile_type") or "") == "fill_discrepancy"
            and (
                str((row.get("details_json") or {}).get("execution_fill_id") or "") == str(fill.get("execution_fill_id") or "")
                or not str((row.get("details_json") or {}).get("execution_fill_id") or "").strip()
            )
        ]
        return {
            "fill": self._live_fill_summary_row(fill),
            "order": self._live_order_summary_row(order) if isinstance(order, dict) else None,
            "timeline": self.db.live_order_events_for_order(execution_order_id) if execution_order_id else [],
            "discrepancy_events": discrepancy_events,
        }

    def live_fill_discrepancies(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        execution_order_id: str | None = None,
    ) -> dict[str, Any]:
        candidate_rows = self.db.list_fills(
            execution_order_id=execution_order_id,
            family=_normalize_family(family) if family else None,
            environment=_normalize_environment(environment) if environment else None,
            symbol=_canonical_symbol(symbol) if symbol else None,
            limit=500,
            offset=0,
        )
        items = [
            self._live_fill_summary_row(row)
            for row in candidate_rows
            if str(row.get("reconciliation_status") or "").upper() == "DISCREPANCY"
            or bool(row.get("discrepancy_json"))
        ]
        execution_order_ids = {str(row.get("execution_order_id") or "") for row in items if str(row.get("execution_order_id") or "").strip()}
        events = [
            row
            for row in self.db.list_reconcile_events(resolved=False, reconcile_type="fill_discrepancy")
            if (
                not execution_order_ids
                or str(row.get("execution_order_id") or "") in execution_order_ids
                or (
                    not str(row.get("execution_order_id") or "").strip()
                    and (not symbol or _canonical_symbol(((row.get("details_json") or {}).get("trade") or {}).get("symbol")) == _canonical_symbol(symbol))
                )
            )
        ]
        return {
            "count": len(items),
            "items": items,
            "events": events,
        }

    def live_order_timeline(self, execution_order_id: str) -> list[dict[str, Any]]:
        return self.db.live_order_events_for_order(execution_order_id)

    def unresolved_live_orders(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        bot_id: str | None = None,
    ) -> dict[str, Any]:
        deadlines = self._reconciliation_deadlines()
        rows = self.db.list_orders(
            family=_normalize_family(family) if family else None,
            environment=_normalize_environment(environment) if environment else None,
            symbol=symbol,
            bot_id=bot_id,
            limit=1000,
            offset=0,
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            state = normalize_local_state(row.get("current_local_state"))
            last_event = _parse_ts(row.get("last_event_at")) or _parse_ts(row.get("submitted_at")) or _utc_now()
            age_sec = max(0.0, (_utc_now() - last_event).total_seconds())
            unresolved = (
                is_ambiguous_local_state(state)
                or str(row.get("reconciliation_status") or "").upper() == "UNRESOLVED"
                or (blocks_new_submits(state) and age_sec >= deadlines["hard_deadline_sec"])
            )
            if not unresolved:
                continue
            payload = self._live_order_summary_row(row)
            payload["age_sec"] = round(age_sec, 4)
            items.append(payload)
        return {
            "count": len(items),
            "items": items,
            "soft_deadline_sec": deadlines["soft_deadline_sec"],
            "hard_deadline_sec": deadlines["hard_deadline_sec"],
        }

    def _recent_terminal_missing_fills(self, row: dict[str, Any]) -> bool:
        if not is_terminal_local_state(row.get("current_local_state")):
            return False
        if _safe_float(row.get("executed_qty"), 0.0) <= 0.0 and str(row.get("order_status") or "").upper() not in {"FILLED", "PARTIALLY_FILLED"}:
            return False
        if self.db.fills_for_order(str(row.get("execution_order_id") or "")):
            return False
        reference_dt = (
            _parse_ts(row.get("terminal_at"))
            or _parse_ts(row.get("last_event_at"))
            or _parse_ts(row.get("transact_time_last"))
            or _parse_ts(row.get("acknowledged_at"))
            or _parse_ts(row.get("submitted_at"))
        )
        if reference_dt is None:
            return True
        age_hours = max(0.0, (_utc_now() - reference_dt).total_seconds() / 3600.0)
        return age_hours <= float(self._fill_reconciliation_window().get("window_hours") or 24.0)

    def _reconciliation_case_scope_key(
        self,
        *,
        case: dict[str, Any] | None = None,
        execution_order_id: str | None = None,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        bot_id: str | None = None,
        execution_fill_scope: str | None = None,
    ) -> str:
        payload = case if isinstance(case, dict) else {}
        order_id = str(execution_order_id or payload.get("execution_order_id") or "").strip()
        if order_id:
            return f"order:{order_id}"
        return ":".join(
            [
                "scope",
                str(payload.get("exchange") or "binance"),
                _normalize_family(family or payload.get("market_type")),
                _normalize_environment(environment or payload.get("environment")),
                _canonical_symbol(symbol or payload.get("symbol")) or "*",
                str(bot_id or payload.get("bot_id") or "*"),
                str(execution_fill_scope or payload.get("execution_fill_scope") or "scope"),
            ]
        )

    def _active_reconciliation_cases(
        self,
        *,
        final_status: str | None = None,
        severity: str | None = None,
        blocking_only: bool = False,
        environment: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
        execution_order_id: str | None = None,
        bot_id: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        latest_by_scope: dict[str, dict[str, Any]] = {}
        rows = self.db.list_reconciliation_cases(
            final_status=None,
            severity=severity,
            blocking_only=False,
            environment=environment,
            family=family,
            symbol=symbol,
            execution_order_id=execution_order_id,
            bot_id=bot_id,
            limit=max(50, int(limit)),
            offset=0,
        )
        for row in rows:
            key = self._reconciliation_case_scope_key(case=row)
            if key not in latest_by_scope:
                latest_by_scope[key] = row
        items = [
            row
            for row in latest_by_scope.values()
            if normalize_reconciliation_case_status(row.get("final_status")) not in {"CLEAN", "RESOLVED"}
        ]
        if final_status:
            normalized_status = normalize_reconciliation_case_status(final_status)
            items = [row for row in items if normalize_reconciliation_case_status(row.get("final_status")) == normalized_status]
        if blocking_only:
            items = [row for row in items if reconciliation_case_blocks_live(row.get("final_status"), row.get("blocking_bool"))]
        items.sort(
            key=lambda row: (str(row.get("started_at") or ""), str(row.get("reconciliation_case_id") or "")),
            reverse=True,
        )
        return items[: max(1, int(limit))]

    def _reconciliation_case_summary_row(self, case: dict[str, Any]) -> dict[str, Any]:
        payload = copy.deepcopy(case)
        discrepancies = payload.get("discrepancy_summary_json")
        items = discrepancies.get("items") if isinstance(discrepancies, dict) and isinstance(discrepancies.get("items"), list) else []
        payload.update(
            {
                "trigger": payload.get("trigger_type"),
                "scope": {
                    "exchange": payload.get("exchange"),
                    "market_type": payload.get("market_type"),
                    "environment": payload.get("environment"),
                    "symbol": payload.get("symbol"),
                    "bot_id": payload.get("bot_id"),
                    "execution_order_id": payload.get("execution_order_id"),
                    "execution_fill_scope": payload.get("execution_fill_scope"),
                },
                "discrepancies": copy.deepcopy(items),
                "discrepancy_count": len(items),
                "blocking_bool": reconciliation_case_blocks_live(payload.get("final_status"), payload.get("blocking_bool")),
            }
        )
        return payload

    def _insert_reconciliation_case_bundle(
        self,
        *,
        case_payload: dict[str, Any],
        events: list[dict[str, Any]],
        snapshots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        stored_case = self.db.insert_reconciliation_case(case_payload)
        case_id = str(stored_case.get("reconciliation_case_id") or "")
        for row in events:
            self.db.insert_reconciliation_case_event(
                {
                    "reconciliation_case_id": case_id,
                    **row,
                }
            )
        for row in snapshots:
            self.db.insert_reconciliation_snapshot(
                {
                    "reconciliation_case_id": case_id,
                    **row,
                }
            )
        detail = self.reconciliation_case_detail(case_id)
        return detail["case"] if isinstance(detail, dict) and isinstance(detail.get("case"), dict) else self._reconciliation_case_summary_row(stored_case)

    def _stream_gap_ms(self, stream_state: dict[str, Any] | None) -> float | None:
        payload = stream_state if isinstance(stream_state, dict) else {}
        if _first_number(payload.get("stale_ms")) is not None:
            return _first_number(payload.get("stale_ms"))
        updated_at = _parse_ts(payload.get("updated_at"))
        if updated_at is None:
            return None
        return max(0.0, (_utc_now() - updated_at).total_seconds() * 1000.0)

    def _reconciliation_retry_call(self, fn, *args, **kwargs):  # noqa: ANN001, ANN202
        policy = self._reconciliation_engine_policy()
        attempts = max(1, int(policy.get("remote_query_retry_count") or 1))
        backoff_ms = max(0, int(policy.get("remote_query_backoff_ms") or 0))
        last_result = None
        last_exc: Exception | None = None
        for idx in range(attempts):
            try:
                last_result = fn(*args, **kwargs)
                meta = last_result[1] if isinstance(last_result, tuple) and len(last_result) > 1 and isinstance(last_result[1], dict) else {}
                if meta.get("ok") or idx + 1 >= attempts:
                    if isinstance(last_result, tuple) and len(last_result) > 1 and isinstance(last_result[1], dict):
                        last_result[1]["attempts"] = idx + 1
                    return last_result
            except Exception as exc:  # pragma: no cover - defensive
                last_exc = exc
                if idx + 1 >= attempts:
                    raise
            if backoff_ms > 0:
                time.sleep(backoff_ms / 1000.0)
        if last_exc is not None:  # pragma: no cover - defensive
            raise last_exc
        return last_result

    def _find_open_snapshot_match(
        self,
        *,
        order: dict[str, Any],
        open_orders: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        execution_order_id = str(order.get("execution_order_id") or "")
        venue_order_id = str(order.get("venue_order_id") or "")
        client_order_id = str(order.get("client_order_id") or "")
        for item in open_orders:
            if execution_order_id and str(item.get("execution_order_id") or "") == execution_order_id:
                return item
            if venue_order_id and str(item.get("venue_order_id") or "") == venue_order_id:
                return item
            if client_order_id and str(item.get("client_order_id") or "") == client_order_id:
                return item
        return None

    def _build_reconciliation_case_for_order(
        self,
        order: dict[str, Any],
        *,
        trigger_type: str,
    ) -> dict[str, Any]:
        started_at = utc_now_iso()
        normalized_trigger = normalize_reconciliation_trigger(trigger_type)
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        original_order = copy.deepcopy(order)
        original_state = normalize_local_state(original_order.get("current_local_state"))
        local_fills_before = self.db.fills_for_order(str(original_order.get("execution_order_id") or ""))
        original_fill_map = {str(fill.get("dedup_key") or ""): fill for fill in local_fills_before if str(fill.get("dedup_key") or "").strip()}
        result = self._reconcile_single_order(copy.deepcopy(order))
        resolved_order = copy.deepcopy(result.get("order") or original_order)
        resolved_state = normalize_local_state(resolved_order.get("current_local_state"))
        stream_state = copy.deepcopy(result.get("stream_state") or self._stream_state(family, environment))
        stream_gap_ms = self._stream_gap_ms(stream_state)

        remote_order_snapshot = copy.deepcopy(result.get("remote_order_snapshot")) if isinstance(result.get("remote_order_snapshot"), dict) else None
        remote_query_meta = copy.deepcopy(result.get("remote_source") or {})
        if remote_order_snapshot is None and not is_terminal_local_state(original_state):
            remote_order_snapshot, remote_query_meta = self._reconciliation_retry_call(self._query_remote_order_snapshot, resolved_order)

        open_orders_snapshot, open_orders_meta = self._reconciliation_retry_call(
            self._remote_open_orders_snapshot,
            family=family,
            environment=environment,
            symbol=resolved_order.get("symbol"),
        )

        remote_trade_rows = copy.deepcopy(result.get("remote_trade_rows") or [])
        remote_trade_meta = copy.deepcopy(result.get("remote_trade_source") or {})
        if not remote_trade_rows and family == "spot" and environment in {"live", "testnet"}:
            remote_trade_rows, remote_trade_meta = self._reconciliation_retry_call(
                self._fetch_remote_trade_rows_for_symbol,
                family=family,
                environment=environment,
                symbol=resolved_order.get("symbol"),
                limit=int(self._reconciliation_engine_policy().get("recent_trades_limit") or 100),
            )

        local_fills_after = self.db.fills_for_order(str(resolved_order.get("execution_order_id") or ""))
        local_fill_map = {str(fill.get("dedup_key") or ""): fill for fill in local_fills_after if str(fill.get("dedup_key") or "").strip()}

        discrepancies: list[dict[str, Any]] = []
        resolution_actions: list[str] = []
        severity = "INFO"
        final_status = "CLEAN"

        remote_open_match = self._find_open_snapshot_match(order=resolved_order, open_orders=open_orders_snapshot)
        remote_open_status = str((remote_open_match or {}).get("order_status") or "").upper()
        remote_query_status = str((remote_order_snapshot or {}).get("order_status") or "").upper()
        remote_is_open = remote_query_status in OPENISH_EXCHANGE_ORDER_STATUSES or remote_open_status in OPENISH_EXCHANGE_ORDER_STATUSES
        remote_is_terminal = remote_query_status in TERMINAL_ORDER_STATUSES
        local_was_open = not is_terminal_local_state(original_state)
        local_is_open = not is_terminal_local_state(resolved_state)

        if local_was_open and remote_is_terminal:
            discrepancies.append(
                discrepancy_payload(
                    code="ORDER_REMOTE_TERMINAL_BUT_LOCAL_OPEN",
                    severity="WARN",
                    entity_scope="order",
                    local_value={"local_state_before": original_state},
                    remote_value={"remote_status": remote_query_status},
                    auto_resolvable_bool=True,
                    proposed_action="adopt_remote_terminal_state",
                    final_action=f"resolved_to_{resolved_state.lower()}",
                )
            )
            resolution_actions.append("remote_terminal_state_adopted")
            final_status = "RESOLVED"
            severity = "WARN"

        if is_terminal_local_state(original_state) and remote_is_open:
            auto_resolvable = remote_query_status in OPENISH_EXCHANGE_ORDER_STATUSES and remote_open_match is not None and local_is_open
            discrepancies.append(
                discrepancy_payload(
                    code="ORDER_LOCAL_TERMINAL_BUT_REMOTE_OPEN",
                    severity="CRITICAL" if not auto_resolvable else "WARN",
                    entity_scope="order",
                    local_value={"local_state_before": original_state},
                    remote_value={"query_status": remote_query_status, "open_snapshot_status": remote_open_status},
                    auto_resolvable_bool=auto_resolvable,
                    proposed_action="recover_open_order_from_exchange",
                    final_action=f"resolved_to_{resolved_state.lower()}" if auto_resolvable else "manual_review_required",
                )
            )
            if auto_resolvable:
                resolution_actions.append("remote_open_order_recovered")
                final_status = "RESOLVED"
                severity = "WARN"
            else:
                final_status = "DESYNC"
                severity = "CRITICAL"

        if local_is_open and remote_query_status == "" and remote_open_match is None:
            discrepancies.append(
                discrepancy_payload(
                    code="ORDER_LOCAL_OPEN_BUT_REMOTE_MISSING",
                    severity="CRITICAL",
                    entity_scope="order",
                    local_value={"local_state_after": resolved_state},
                    remote_value={"query_meta": remote_query_meta, "open_orders_meta": open_orders_meta},
                    auto_resolvable_bool=False,
                    proposed_action="query_again_or_manual_review",
                    final_action="desync_pending_resolution",
                )
            )
            final_status = "DESYNC"
            severity = "CRITICAL"

        remote_trade_map = {str(row.get("dedup_key") or ""): row for row in remote_trade_rows if str(row.get("dedup_key") or "").strip()}
        missing_remote_fills = [fill for key, fill in original_fill_map.items() if key and key not in remote_trade_map]
        missing_local_fills = [row for key, row in remote_trade_map.items() if key and key not in local_fill_map]
        if missing_local_fills:
            discrepancies.append(
                discrepancy_payload(
                    code="FILLS_REMOTE_NOT_IN_LOCAL",
                    severity="WARN",
                    entity_scope="fills",
                    local_value={"count_before": len(local_fills_before)},
                    remote_value={"missing_rows": len(missing_local_fills)},
                    auto_resolvable_bool=True,
                    proposed_action="persist_missing_remote_fills",
                    final_action="persisted_remote_fills" if len(local_fills_after) >= len(local_fills_before) + len(missing_local_fills) else "manual_review_required",
                )
            )
            if len(local_fills_after) >= len(local_fills_before) + len(missing_local_fills):
                resolution_actions.append("remote_fills_backfilled")
                if final_status == "CLEAN":
                    final_status = "RESOLVED"
                    severity = "WARN"
            else:
                final_status = "MANUAL_REVIEW_REQUIRED"
                severity = "CRITICAL"
        if missing_remote_fills:
            discrepancies.append(
                discrepancy_payload(
                    code="FILLS_LOCAL_NOT_CONFIRMED_REMOTE",
                    severity="WARN",
                    entity_scope="fills",
                    local_value={"missing_rows": len(missing_remote_fills)},
                    remote_value={"remote_rows": len(remote_trade_rows)},
                    auto_resolvable_bool=False,
                    proposed_action="retain_local_evidence_until_trade_list_catches_up",
                    final_action="manual_review_required",
                )
            )
            if final_status not in {"DESYNC", "MANUAL_REVIEW_REQUIRED"}:
                final_status = "MANUAL_REVIEW_REQUIRED"
                severity = "WARN"

        if remote_trade_rows and local_fills_after:
            local_qty = sum(_safe_float(fill.get("last_executed_qty"), 0.0) for fill in local_fills_after)
            remote_qty = sum(_safe_float(row.get("last_executed_qty"), 0.0) for row in remote_trade_rows)
            if abs(local_qty - remote_qty) > 1e-12:
                discrepancies.append(
                    discrepancy_payload(
                        code="CUM_QTY_MISMATCH",
                        severity="WARN",
                        entity_scope="fills",
                        local_value={"qty": round(local_qty, 12)},
                        remote_value={"qty": round(remote_qty, 12)},
                        auto_resolvable_bool=False,
                        proposed_action="review_trade_linkage",
                        final_action="manual_review_required",
                    )
                )
                if final_status not in {"DESYNC", "MANUAL_REVIEW_REQUIRED"}:
                    final_status = "MANUAL_REVIEW_REQUIRED"
                    severity = "WARN"
            local_quote = sum(_safe_float(fill.get("last_quote_qty"), 0.0) for fill in local_fills_after)
            remote_quote = sum(_safe_float(row.get("last_quote_qty"), 0.0) for row in remote_trade_rows)
            if abs(local_quote - remote_quote) > 1e-9:
                discrepancies.append(
                    discrepancy_payload(
                        code="CUM_QUOTE_MISMATCH",
                        severity="WARN",
                        entity_scope="fills",
                        local_value={"quote": round(local_quote, 12)},
                        remote_value={"quote": round(remote_quote, 12)},
                        auto_resolvable_bool=False,
                        proposed_action="review_trade_quote_consistency",
                        final_action="manual_review_required",
                    )
                )
                if final_status not in {"DESYNC", "MANUAL_REVIEW_REQUIRED"}:
                    final_status = "MANUAL_REVIEW_REQUIRED"
                    severity = "WARN"
            for fill in local_fills_after:
                remote_row = remote_trade_map.get(str(fill.get("dedup_key") or ""))
                if remote_row is None:
                    continue
                if str(fill.get("client_order_id") or "") != str(remote_row.get("client_order_id") or fill.get("client_order_id") or ""):
                    discrepancies.append(
                        discrepancy_payload(
                            code="CLIENT_ORDER_LINK_MISMATCH",
                            severity="WARN",
                            entity_scope="fill",
                            local_value={"client_order_id": fill.get("client_order_id")},
                            remote_value={"client_order_id": remote_row.get("client_order_id")},
                            auto_resolvable_bool=False,
                            proposed_action="review_order_linkage",
                            final_action="manual_review_required",
                        )
                    )
                local_commission = _first_number(fill.get("commission"))
                remote_commission = _first_number(remote_row.get("commission"))
                if local_commission is not None and remote_commission is not None and abs(local_commission - remote_commission) > 1e-12:
                    discrepancies.append(
                        discrepancy_payload(
                            code="COMMISSION_MISMATCH",
                            severity="WARN",
                            entity_scope="fill",
                            local_value={"commission": local_commission, "asset": fill.get("commission_asset")},
                            remote_value={"commission": remote_commission, "asset": remote_row.get("commission_asset")},
                            auto_resolvable_bool=False,
                            proposed_action="prefer_trade_ledger_commission_values",
                            final_action="manual_review_required",
                        )
                    )

        order_age_sec = max(
            0.0,
            (
                _utc_now()
                - (
                    _parse_ts(resolved_order.get("last_event_at"))
                    or _parse_ts(resolved_order.get("submitted_at"))
                    or _utc_now()
                )
            ).total_seconds(),
        )
        if original_state == "UNKNOWN_PENDING_RECONCILIATION" and (
            resolved_state in {"UNKNOWN_PENDING_RECONCILIATION", "MANUAL_REVIEW_REQUIRED"}
            and order_age_sec > float(self._reconciliation_engine_policy().get("unknown_hard_deadline_sec") or 30.0)
        ):
            discrepancies.append(
                discrepancy_payload(
                    code="UNKNOWN_TIMEOUT_UNRESOLVED",
                    severity="CRITICAL",
                    entity_scope="order",
                    local_value={"state": resolved_state, "age_sec": round(order_age_sec, 4)},
                    remote_value={"query_meta": remote_query_meta, "open_orders_meta": open_orders_meta},
                    auto_resolvable_bool=False,
                    proposed_action="block_symbol_until_manual_reconcile",
                    final_action="desync_block_live",
                )
            )
            final_status = "DESYNC"
            severity = "CRITICAL"

        if resolved_state == "EXPIRED_STP" or remote_query_status == "EXPIRED_IN_MATCH":
            discrepancies.append(
                discrepancy_payload(
                    code="STP_PREVENTED_MATCH_NEEDS_RECLASSIFICATION",
                    severity="WARN",
                    entity_scope="order",
                    local_value={"local_state_after": resolved_state},
                    remote_value={"remote_status": remote_query_status},
                    auto_resolvable_bool=True,
                    proposed_action="classify_as_expired_stp",
                    final_action="classified_expired_stp",
                )
            )
            if final_status == "CLEAN":
                final_status = "RESOLVED"
                severity = "WARN"

        if stream_gap_ms is not None and stream_gap_ms > float(self._reconciliation_engine_policy().get("max_snapshot_age_ms") or 15000.0):
            discrepancies.append(
                discrepancy_payload(
                    code="SNAPSHOT_STALENESS_TOO_HIGH",
                    severity="WARN",
                    entity_scope="stream",
                    local_value={"stream_gap_ms": round(stream_gap_ms, 3)},
                    remote_value={"max_snapshot_age_ms": self._reconciliation_engine_policy().get("max_snapshot_age_ms")},
                    auto_resolvable_bool=False,
                    proposed_action="refresh_stream_or_reconcile_again",
                    final_action="warning_recorded",
                )
            )
            if final_status == "CLEAN":
                final_status = "RESOLVED"
                severity = "WARN"

        has_open_orders = bool(remote_open_match) or local_is_open
        if stream_gap_ms is not None and stream_gap_ms > float(self._reconciliation_engine_policy().get("max_stream_gap_ms") or 10000.0) and has_open_orders:
            discrepancies.append(
                discrepancy_payload(
                    code="STREAM_GAP_WITH_PENDING_OPEN_ORDERS",
                    severity="CRITICAL" if environment == "live" else "WARN",
                    entity_scope="stream",
                    local_value={"stream_state": stream_state},
                    remote_value={"open_order_present": has_open_orders},
                    auto_resolvable_bool=False,
                    proposed_action="require_manual_reconcile_before_next_submit",
                    final_action="desync_block_live" if environment == "live" else "warning_recorded",
                )
            )
            if environment == "live":
                final_status = "DESYNC"
                severity = "CRITICAL"
            elif final_status == "CLEAN":
                final_status = "RESOLVED"
                severity = "WARN"

        if remote_query_status and remote_open_match is not None:
            open_snapshot_status = str(remote_open_match.get("order_status") or "").upper()
            query_open = remote_query_status in OPENISH_EXCHANGE_ORDER_STATUSES
            snapshot_open = open_snapshot_status in OPENISH_EXCHANGE_ORDER_STATUSES
            if query_open != snapshot_open:
                discrepancies.append(
                    discrepancy_payload(
                        code="ORDER_REMOTE_TERMINAL_BUT_LOCAL_OPEN" if query_open else "ORDER_LOCAL_OPEN_BUT_REMOTE_MISSING",
                        severity="CRITICAL",
                        entity_scope="order",
                        local_value={"query_status": remote_query_status},
                        remote_value={"open_snapshot_status": open_snapshot_status},
                        auto_resolvable_bool=False,
                        proposed_action="manual_review_query_vs_snapshot_conflict",
                        final_action="manual_review_required",
                    )
                )
                final_status = "MANUAL_REVIEW_REQUIRED"
                severity = "CRITICAL"

        blocking = False
        if final_status == "DESYNC":
            blocking = _bool(self._reconciliation_engine_policy().get("desync_blocks_live", True))
        elif final_status == "MANUAL_REVIEW_REQUIRED":
            blocking = _bool(self._reconciliation_engine_policy().get("manual_review_blocks_live", True))

        case_payload = {
            "trigger_type": normalized_trigger,
            "exchange": "binance",
            "market_type": family,
            "environment": environment,
            "bot_id": resolved_order.get("bot_id"),
            "symbol": resolved_order.get("symbol"),
            "execution_order_id": resolved_order.get("execution_order_id"),
            "execution_fill_scope": "order",
            "started_at": started_at,
            "finished_at": utc_now_iso(),
            "final_status": final_status,
            "severity": severity,
            "local_summary_json": {
                "local_state_before": original_state,
                "local_state_after": resolved_state,
                "order_status_before": original_order.get("order_status"),
                "order_status_after": resolved_order.get("order_status"),
                "execution_order_id": resolved_order.get("execution_order_id"),
                "client_order_id": resolved_order.get("client_order_id"),
                "local_fill_count_before": len(local_fills_before),
                "local_fill_count_after": len(local_fills_after),
            },
            "remote_summary_json": {
                "query_order_source": copy.deepcopy(remote_query_meta or {}),
                "open_orders_source": copy.deepcopy(open_orders_meta or {}),
                "trade_list_source": copy.deepcopy(remote_trade_meta or {}),
                "remote_order_status": remote_query_status or None,
                "open_orders_count": len(open_orders_snapshot),
                "remote_trade_count": len(remote_trade_rows),
                "stream_state": copy.deepcopy(stream_state),
                "stream_gap_ms": stream_gap_ms,
                "evidence_precedence": [
                    "user_stream_recent",
                    "query_order",
                    "open_orders",
                    "my_trades",
                    "rest_create_cancel_history",
                    "local_prior_state",
                ],
            },
            "discrepancy_summary_json": {
                "count": len(discrepancies),
                "items": discrepancies,
            },
            "resolution_summary_json": {
                "actions": resolution_actions,
                "final_local_state": resolved_state,
                "final_exchange_status": resolved_order.get("order_status"),
            },
            "blocking_bool": blocking,
        }
        events = [
            {
                "event_time": started_at,
                "source_type": "LOCAL_STATE",
                "message": "local_order_loaded",
                "payload_json": {"order": original_order},
                "decision_json": {"local_state": original_state},
                "applied_bool": True,
            },
            {
                "event_time": utc_now_iso(),
                "source_type": "REST_QUERY_ORDER",
                "message": "query_order_evidence",
                "payload_json": copy.deepcopy(remote_query_meta or {}),
                "decision_json": {"remote_status": remote_query_status or None},
                "applied_bool": bool(remote_query_meta.get("ok")) if isinstance(remote_query_meta, dict) else False,
            },
            {
                "event_time": utc_now_iso(),
                "source_type": "REST_OPEN_ORDERS",
                "message": "open_orders_snapshot_evidence",
                "payload_json": copy.deepcopy(open_orders_meta or {}),
                "decision_json": {"matched_order": bool(remote_open_match), "snapshot_count": len(open_orders_snapshot)},
                "applied_bool": bool(open_orders_meta.get("ok")) if isinstance(open_orders_meta, dict) else False,
            },
            {
                "event_time": utc_now_iso(),
                "source_type": "REST_MYTRADES",
                "message": "mytrades_evidence",
                "payload_json": copy.deepcopy(remote_trade_meta or {}),
                "decision_json": {"trade_count": len(remote_trade_rows)},
                "applied_bool": bool(remote_trade_meta.get("ok")) if isinstance(remote_trade_meta, dict) else False,
            },
            {
                "event_time": utc_now_iso(),
                "source_type": "POLICY",
                "message": "reconciliation_policy_context",
                "payload_json": self._reconciliation_engine_policy(),
                "decision_json": {"final_status": final_status, "blocking_bool": blocking},
                "applied_bool": True,
            },
        ]
        snapshots = [
            {
                "snapshot_type": "LOCAL_ORDER",
                "symbol": resolved_order.get("symbol"),
                "execution_order_id": resolved_order.get("execution_order_id"),
                "captured_at": started_at,
                "payload_json": original_order,
                "source_freshness_ms": 0.0,
            },
            {
                "snapshot_type": "REMOTE_ORDER",
                "symbol": resolved_order.get("symbol"),
                "execution_order_id": resolved_order.get("execution_order_id"),
                "captured_at": utc_now_iso(),
                "payload_json": remote_order_snapshot or {},
                "source_freshness_ms": 0.0 if remote_order_snapshot else None,
            },
            {
                "snapshot_type": "OPEN_ORDERS",
                "symbol": resolved_order.get("symbol"),
                "execution_order_id": resolved_order.get("execution_order_id"),
                "captured_at": utc_now_iso(),
                "payload_json": {"items": open_orders_snapshot, "meta": open_orders_meta},
                "source_freshness_ms": 0.0,
            },
            {
                "snapshot_type": "TRADE_LIST",
                "symbol": resolved_order.get("symbol"),
                "execution_order_id": resolved_order.get("execution_order_id"),
                "captured_at": utc_now_iso(),
                "payload_json": {"items": remote_trade_rows, "meta": remote_trade_meta},
                "source_freshness_ms": 0.0 if remote_trade_rows else None,
            },
            {
                "snapshot_type": "LOCAL_FILLS",
                "symbol": resolved_order.get("symbol"),
                "execution_order_id": resolved_order.get("execution_order_id"),
                "captured_at": utc_now_iso(),
                "payload_json": {"items": local_fills_after},
                "source_freshness_ms": 0.0,
            },
            {
                "snapshot_type": "POLICY_CONTEXT",
                "symbol": resolved_order.get("symbol"),
                "execution_order_id": resolved_order.get("execution_order_id"),
                "captured_at": utc_now_iso(),
                "payload_json": self._reconciliation_engine_policy(),
                "source_freshness_ms": 0.0,
            },
            {
                "snapshot_type": "STREAM_HEALTH",
                "symbol": resolved_order.get("symbol"),
                "execution_order_id": resolved_order.get("execution_order_id"),
                "captured_at": utc_now_iso(),
                "payload_json": stream_state,
                "source_freshness_ms": stream_gap_ms,
            },
        ]
        return self._insert_reconciliation_case_bundle(
            case_payload=case_payload,
            events=events,
            snapshots=snapshots,
        )

    def _build_remote_open_cases(
        self,
        *,
        family: str,
        environment: str,
        symbol: str | None,
        bot_id: str | None,
        trigger_type: str,
    ) -> list[dict[str, Any]]:
        if environment not in {"live", "testnet"}:
            return []
        items, meta = self._reconciliation_retry_call(
            self._remote_open_orders_snapshot,
            family=family,
            environment=environment,
            symbol=symbol,
        )
        created: list[dict[str, Any]] = []
        for item in items:
            if item.get("execution_order_id"):
                continue
            blocking = environment == "live" and _bool(self._reconciliation_engine_policy().get("open_remote_without_local_blocks_live", True))
            discrepancy = discrepancy_payload(
                code="ORDER_MISSING_LOCALLY_BUT_REMOTE_OPEN",
                severity="CRITICAL" if blocking else "WARN",
                entity_scope="symbol",
                local_value={"local_order": None},
                remote_value={"remote_order": item},
                auto_resolvable_bool=False,
                proposed_action="manual_import_or_remote_cancel",
                final_action="desync_block_live" if blocking else "manual_review_required",
            )
            created.append(
                self._insert_reconciliation_case_bundle(
                    case_payload={
                        "trigger_type": normalize_reconciliation_trigger(trigger_type),
                        "exchange": "binance",
                        "market_type": family,
                        "environment": environment,
                        "bot_id": bot_id,
                        "symbol": item.get("symbol"),
                        "execution_order_id": None,
                        "execution_fill_scope": "symbol_remote_open",
                        "started_at": utc_now_iso(),
                        "finished_at": utc_now_iso(),
                        "final_status": "DESYNC" if blocking else "MANUAL_REVIEW_REQUIRED",
                        "severity": "CRITICAL" if blocking else "WARN",
                        "local_summary_json": {"local_order_present": False},
                        "remote_summary_json": {"remote_open_order": item, "open_orders_source": meta},
                        "discrepancy_summary_json": {"count": 1, "items": [discrepancy]},
                        "resolution_summary_json": {"actions": [], "final_local_state": None, "final_exchange_status": item.get("order_status")},
                        "blocking_bool": blocking,
                    },
                    events=[
                        {
                            "event_time": utc_now_iso(),
                            "source_type": "REST_OPEN_ORDERS",
                            "message": "remote_open_order_without_local_match",
                            "payload_json": {"remote_order": item, "meta": meta},
                            "decision_json": {"blocking_bool": blocking},
                            "applied_bool": True,
                        }
                    ],
                    snapshots=[
                        {
                            "snapshot_type": "OPEN_ORDERS",
                            "symbol": item.get("symbol"),
                            "execution_order_id": None,
                            "captured_at": utc_now_iso(),
                            "payload_json": {"remote_order": item, "meta": meta},
                            "source_freshness_ms": 0.0,
                        }
                    ],
                )
            )
        return created

    def list_reconciliation_cases_payload(
        self,
        *,
        final_status: str | None = None,
        severity: str | None = None,
        blocking_only: bool = False,
        environment: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
        execution_order_id: str | None = None,
        bot_id: str | None = None,
        active_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        rows = (
            self._active_reconciliation_cases(
                final_status=final_status,
                severity=severity,
                blocking_only=blocking_only,
                environment=environment,
                family=family,
                symbol=symbol,
                execution_order_id=execution_order_id,
                bot_id=bot_id,
                limit=limit,
            )
            if active_only
            else self.db.list_reconciliation_cases(
                final_status=final_status,
                severity=severity,
                blocking_only=blocking_only,
                environment=environment,
                family=family,
                symbol=symbol,
                execution_order_id=execution_order_id,
                bot_id=bot_id,
                limit=limit,
                offset=offset,
            )
        )
        items = [self._reconciliation_case_summary_row(row) for row in rows]
        return {
            "items": items,
            "count": len(items),
            "filters": {
                "final_status": normalize_reconciliation_case_status(final_status) if final_status else None,
                "severity": normalize_reconciliation_case_severity(severity) if severity else None,
                "blocking_only": bool(blocking_only),
                "environment": _normalize_environment(environment) if environment else None,
                "family": _normalize_family(family) if family else None,
                "symbol": _canonical_symbol(symbol) if symbol else None,
                "execution_order_id": execution_order_id,
                "bot_id": bot_id,
                "active_only": bool(active_only),
                "limit": int(limit),
                "offset": int(offset),
            },
        }

    def reconciliation_case_detail(self, reconciliation_case_id: str) -> dict[str, Any] | None:
        case = self.db.reconciliation_case_by_id(reconciliation_case_id)
        if case is None:
            return None
        return {
            "case": self._reconciliation_case_summary_row(case),
            "events": self.db.reconciliation_case_events(reconciliation_case_id),
            "snapshots": self.db.reconciliation_snapshots(reconciliation_case_id),
        }

    def open_reconciliation_cases(
        self,
        *,
        environment: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
        execution_order_id: str | None = None,
        bot_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        return self.list_reconciliation_cases_payload(
            environment=environment,
            family=family,
            symbol=symbol,
            execution_order_id=execution_order_id,
            bot_id=bot_id,
            active_only=True,
            limit=limit,
        )

    def desync_reconciliation_cases(
        self,
        *,
        environment: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
        bot_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        return self.list_reconciliation_cases_payload(
            final_status="DESYNC",
            environment=environment,
            family=family,
            symbol=symbol,
            bot_id=bot_id,
            active_only=True,
            limit=limit,
        )

    def reconciliation_summary(
        self,
        *,
        environment: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
        bot_id: str | None = None,
        execution_order_id: str | None = None,
    ) -> dict[str, Any]:
        active = self._active_reconciliation_cases(
            environment=environment,
            family=family,
            symbol=symbol,
            execution_order_id=execution_order_id,
            bot_id=bot_id,
            limit=500,
        )
        desync = [row for row in active if normalize_reconciliation_case_status(row.get("final_status")) == "DESYNC"]
        manual = [row for row in active if normalize_reconciliation_case_status(row.get("final_status")) == "MANUAL_REVIEW_REQUIRED"]
        blocking = [row for row in active if reconciliation_case_blocks_live(row.get("final_status"), row.get("blocking_bool"))]
        latest = self.db.list_reconciliation_cases(
            environment=environment,
            family=family,
            symbol=symbol,
            execution_order_id=execution_order_id,
            bot_id=bot_id,
            limit=1,
            offset=0,
        )
        return {
            "overall_status": "BLOCK" if blocking else "WARN" if active else "OK",
            "open_cases_count": len(active),
            "desync_count": len(desync),
            "manual_review_count": len(manual),
            "blocking_cases_count": len(blocking),
            "last_run": self._reconciliation_case_summary_row(latest[0]) if latest else None,
            "open_cases": [self._reconciliation_case_summary_row(row) for row in active[:20]],
            "desync_cases": [self._reconciliation_case_summary_row(row) for row in desync[:20]],
            "policy": self._reconciliation_engine_policy(),
            "filters": {
                "environment": _normalize_environment(environment) if environment else None,
                "family": _normalize_family(family) if family else None,
                "symbol": _canonical_symbol(symbol) if symbol else None,
                "bot_id": bot_id,
                "execution_order_id": execution_order_id,
            },
        }

    def run_reconciliation_engine(
        self,
        *,
        execution_order_id: str | None = None,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        bot_id: str | None = None,
        trigger: str = "MANUAL",
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family) if family else None
        normalized_environment = _normalize_environment(environment) if environment else None
        normalized_symbol = _canonical_symbol(symbol) if symbol else None
        normalized_trigger = normalize_reconciliation_trigger(trigger)
        started_at = utc_now_iso()

        rows = self.db.list_orders(
            family=normalized_family,
            environment=normalized_environment,
            symbol=normalized_symbol,
            bot_id=bot_id,
            limit=1000,
            offset=0,
        )
        if execution_order_id:
            rows = [row for row in rows if str(row.get("execution_order_id") or "") == str(execution_order_id)]
        elif normalized_trigger in {"STARTUP", "PRESTART_LIVE"}:
            rows = [
                row
                for row in rows
                if _normalize_environment(row.get("environment")) in {"live", "testnet"}
                and (
                    not is_terminal_local_state(row.get("current_local_state"))
                    or self._recent_terminal_missing_fills(row)
                )
            ]
        else:
            rows = [
                row
                for row in rows
                if (
                    not is_terminal_local_state(row.get("current_local_state"))
                    or self._recent_terminal_missing_fills(row)
                    or normalize_local_state(row.get("current_local_state")) in AMBIGUOUS_LOCAL_ORDER_STATES
                )
            ]

        cases: list[dict[str, Any]] = []
        for row in rows:
            cases.append(self._build_reconciliation_case_for_order(row, trigger_type=normalized_trigger))

        scope_pairs: set[tuple[str, str, str | None]] = set()
        if execution_order_id:
            order = self.db.order_by_id(execution_order_id)
            if order is not None:
                scope_pairs.add((_normalize_family(order.get("family")), _normalize_environment(order.get("environment")), _canonical_symbol(order.get("symbol"))))
        elif normalized_environment:
            if normalized_family:
                scope_pairs.add((normalized_family, normalized_environment, normalized_symbol))
            elif normalized_environment in {"live", "testnet"}:
                scope_pairs.add(("spot", normalized_environment, normalized_symbol))
        else:
            for row in rows:
                scope_pairs.add((_normalize_family(row.get("family")), _normalize_environment(row.get("environment")), None))

        if not scope_pairs and normalized_trigger in {"STARTUP", "PRESTART_LIVE"}:
            default_environment = normalized_environment or "live"
            if default_environment in {"live", "testnet"}:
                scope_pairs.add((normalized_family or "spot", default_environment, normalized_symbol))

        for scope_family, scope_environment, scope_symbol in sorted(scope_pairs):
            if scope_environment not in {"live", "testnet"}:
                continue
            cases.extend(
                self._build_remote_open_cases(
                    family=scope_family,
                    environment=scope_environment,
                    symbol=scope_symbol,
                    bot_id=bot_id,
                    trigger_type=normalized_trigger,
                )
            )

        run = self.db.insert_live_order_reconciliation_run(
            {
                "started_at": started_at,
                "finished_at": utc_now_iso(),
                "trigger": normalized_trigger,
                "family": normalized_family,
                "environment": normalized_environment,
                "symbol": normalized_symbol,
                "bot_id": bot_id,
                "result_summary_json": {
                    "processed_orders": len(rows),
                    "generated_cases": len(cases),
                    "execution_order_id": execution_order_id,
                },
            }
        )
        active_cases = self._active_reconciliation_cases(
            environment=normalized_environment,
            family=normalized_family,
            symbol=normalized_symbol,
            execution_order_id=execution_order_id,
            bot_id=bot_id,
            limit=200,
        )
        blocking_cases = [row for row in active_cases if reconciliation_case_blocks_live(row.get("final_status"), row.get("blocking_bool"))]
        return {
            "reconciliation_run": run,
            "processed_orders": len(rows),
            "generated_cases": len(cases),
            "items": [self._reconciliation_case_summary_row(row) for row in cases],
            "open_cases": [self._reconciliation_case_summary_row(row) for row in active_cases],
            "blocking_cases": [self._reconciliation_case_summary_row(row) for row in blocking_cases],
            "summary": self.reconciliation_summary(
                environment=normalized_environment,
                family=normalized_family,
                symbol=normalized_symbol,
                bot_id=bot_id,
                execution_order_id=execution_order_id,
            ),
            "filters": {
                "execution_order_id": execution_order_id,
                "family": normalized_family,
                "environment": normalized_environment,
                "symbol": normalized_symbol,
                "bot_id": bot_id,
                "trigger": normalized_trigger,
            },
        }

    def live_reconciliation_gate(
        self,
        *,
        family: str | None = None,
        environment: str = "live",
        symbol: str | None = None,
        bot_id: str | None = None,
        trigger: str = "PRESTART_LIVE",
        run_required: bool = True,
    ) -> dict[str, Any]:
        normalized_environment = _normalize_environment(environment)
        if normalized_environment != "live":
            return {"ok": True, "reason": "reconciliation_not_required_non_live", "summary": self.reconciliation_summary(environment=normalized_environment)}
        policy = self._reconciliation_engine_policy()
        run_payload = None
        if run_required and _bool(policy.get("before_live_start_required", True)):
            run_payload = self.run_reconciliation_engine(
                family=family,
                environment=normalized_environment,
                symbol=symbol,
                bot_id=bot_id,
                trigger=trigger,
            )
        blocking_cases = self._active_reconciliation_cases(
            environment=normalized_environment,
            family=family,
            symbol=symbol,
            bot_id=bot_id,
            blocking_only=True,
            limit=200,
        )
        return {
            "ok": len(blocking_cases) == 0,
            "reason": "reconciliation_clean" if not blocking_cases else "reconciliation_blocking_cases_open",
            "run": run_payload,
            "summary": self.reconciliation_summary(
                environment=normalized_environment,
                family=family,
                symbol=symbol,
                bot_id=bot_id,
            ),
            "blocking_cases": [self._reconciliation_case_summary_row(row) for row in blocking_cases],
        }

    def reconcile_live_fills(
        self,
        *,
        execution_order_id: str | None = None,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        bot_id: str | None = None,
        trigger: str = "MANUAL",
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family) if family else None
        normalized_environment = _normalize_environment(environment) if environment else None
        rows = self.db.list_orders(
            family=normalized_family,
            environment=normalized_environment,
            symbol=symbol,
            bot_id=bot_id,
            limit=500,
            offset=0,
        )
        if execution_order_id:
            rows = [row for row in rows if str(row.get("execution_order_id") or "") == str(execution_order_id)]
        else:
            window = self._fill_reconciliation_window()
            cutoff = _utc_now() - timedelta(hours=float(window["window_hours"]))
            rows = [
                row
                for row in rows
                if (
                    not is_terminal_local_state(row.get("current_local_state"))
                    or (_parse_ts(row.get("last_event_at")) or _parse_ts(row.get("submitted_at")) or _utc_now()) >= cutoff
                )
            ]

        processed = [self._reconcile_single_order(row) for row in rows]
        unlinked_trades: list[dict[str, Any]] = []
        symbol_target = _canonical_symbol(symbol) if symbol else None
        if normalized_family == "spot" and normalized_environment in {"live", "testnet"} and symbol_target:
            remote_rows, remote_meta = self._fetch_remote_trade_rows_for_symbol(
                family=normalized_family,
                environment=normalized_environment,
                symbol=symbol_target,
                limit=int(self._fill_reconciliation_window()["recent_limit"]),
            )
            known_order_ids = {
                str(row.get("venue_order_id") or "")
                for row in self.db.list_orders(
                    family=normalized_family,
                    environment=normalized_environment,
                    symbol=symbol_target,
                    limit=500,
                    offset=0,
                )
                if str(row.get("venue_order_id") or "").strip()
            }
            for trade in remote_rows:
                exchange_order_id = str(trade.get("exchange_order_id") or "").strip()
                if exchange_order_id and exchange_order_id in known_order_ids:
                    continue
                self._record_reconcile_event(
                    reconcile_type="fill_discrepancy",
                    severity="WARN",
                    family=normalized_family,
                    environment=normalized_environment,
                    execution_order_id=None,
                    client_order_id=str(trade.get("client_order_id") or ""),
                    details={
                        "discrepancy_type": "mytrades_unlinked_local_order",
                        "trade": trade,
                        "trigger": trigger,
                        "remote_source": remote_meta or {},
                    },
                    resolved=False,
                )
                unlinked_trades.append(trade)

        discrepancies = self.live_fill_discrepancies(
            family=normalized_family,
            environment=normalized_environment,
            symbol=symbol_target,
            execution_order_id=execution_order_id,
        )
        return {
            "processed_orders": len(rows),
            "items": [
                {
                    "execution_order_id": item["order"].get("execution_order_id"),
                    "current_local_state": item["order"].get("current_local_state"),
                    "fills_count": len(item.get("fills") or []),
                    "degraded_mode": item.get("degraded_mode"),
                    "remote_source": item.get("remote_source"),
                }
                for item in processed
            ],
            "unlinked_mytrades": unlinked_trades,
            "discrepancies": discrepancies,
            "filters": {
                "execution_order_id": execution_order_id,
                "family": normalized_family,
                "environment": normalized_environment,
                "symbol": symbol_target,
                "bot_id": bot_id,
                "trigger": trigger,
            },
        }

    def reconcile_live_orders(
        self,
        *,
        execution_order_id: str | None = None,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        bot_id: str | None = None,
        trigger: str = "MANUAL",
    ) -> dict[str, Any]:
        engine_payload = self.run_reconciliation_engine(
            execution_order_id=execution_order_id,
            family=family,
            environment=environment,
            symbol=symbol,
            bot_id=bot_id,
            trigger=trigger,
        )
        rows = self.db.list_orders(
            family=_normalize_family(family) if family else None,
            environment=_normalize_environment(environment) if environment else None,
            symbol=symbol,
            bot_id=bot_id,
            limit=1000,
            offset=0,
        )
        if execution_order_id:
            rows = [row for row in rows if str(row.get("execution_order_id") or "") == str(execution_order_id)]
        else:
            rows = [row for row in rows if not is_terminal_local_state(row.get("current_local_state"))]
        results = [self._reconcile_single_order(row) for row in rows]
        unresolved = self.unresolved_live_orders(family=family, environment=environment, symbol=symbol, bot_id=bot_id)
        return {
            "reconciliation_run": engine_payload["reconciliation_run"],
            "processed_orders": len(rows),
            "items": [
                {
                    "execution_order_id": item["order"].get("execution_order_id"),
                    "current_local_state": item["order"].get("current_local_state"),
                    "order_status": item["order"].get("order_status"),
                    "degraded_mode": item.get("degraded_mode"),
                    "remote_source": item.get("remote_source"),
                }
                for item in results
            ],
            "unresolved": unresolved,
            "reconciliation_cases": engine_payload.get("items") or [],
            "blocking_cases": engine_payload.get("blocking_cases") or [],
            "summary": engine_payload.get("summary") or {},
        }

    def recover_live_orders_on_startup(self) -> dict[str, Any]:
        return self.run_reconciliation_engine(trigger="STARTUP")

    def order_detail(self, execution_order_id: str) -> dict[str, Any] | None:
        order = self.db.order_by_id(execution_order_id)
        if order is None:
            return None
        reconcile_result = self._reconcile_single_order(order)
        order = reconcile_result["order"]
        intent = reconcile_result["intent"]
        fills = reconcile_result["fills"]
        costs = self._aggregate_order_costs(order=order, intent=intent, fills=fills)
        request_context = (intent or {}).get("raw_request_json") if isinstance((intent or {}).get("raw_request_json"), dict) else {}
        preflight_context = request_context.get("_preflight_context") if isinstance(request_context.get("_preflight_context"), dict) else {}
        return {
            "order": order,
            "intent": intent,
            "fills": fills,
            "fill_discrepancies": [
                row
                for row in self.db.reconcile_events_for_order(str(order.get("execution_order_id")))
                if str(row.get("reconcile_type") or "") == "fill_discrepancy"
            ],
            "reconcile_events": self.db.reconcile_events_for_order(str(order.get("execution_order_id"))),
            "timeline": self.db.live_order_events_for_order(str(order.get("execution_order_id"))),
            "remote_status": order.get("raw_last_status_json") if isinstance(order, dict) else None,
            "remote_source": reconcile_result.get("remote_source"),
            "estimated_costs": costs.get("estimated_costs"),
            "realized_costs": costs.get("realized_costs"),
            "gross_pnl": costs.get("gross_pnl"),
            "net_pnl": costs.get("net_pnl"),
            "degraded_mode": reconcile_result.get("degraded_mode"),
            "current_local_state": order.get("current_local_state"),
            "last_exchange_order_status": order.get("last_exchange_order_status") or order.get("order_status"),
            "last_execution_type": order.get("last_execution_type") or order.get("execution_type_last"),
            "terminal": is_terminal_local_state(order.get("current_local_state")),
            "unresolved_reason": order.get("unresolved_reason"),
            "reconciliation_cases": self.open_reconciliation_cases(execution_order_id=str(order.get("execution_order_id")), limit=25)["items"],
            "filter_validation": copy.deepcopy(preflight_context.get("filter_validation")),
            "normalized_order_preview": copy.deepcopy(preflight_context.get("normalized_order_preview")),
        }

    def cancel_order(self, execution_order_id: str) -> dict[str, Any]:
        order = self.db.order_by_id(execution_order_id)
        if order is None:
            raise ValueError("execution_order_not_found")
        if str(order.get("order_status") or "").upper() in TERMINAL_ORDER_STATUSES:
            return {
                "execution_order_id": order.get("execution_order_id"),
                "order_status": order.get("order_status"),
                "already_terminal": True,
                "order": order,
            }
        family = _normalize_family(order.get("family"))
        environment = _normalize_environment(order.get("environment"))
        order, _cancel_request_event, _ = self._apply_order_event(
            order=order,
            source_type="LOCAL_INTENT",
            forced_local_state="CANCEL_REQUESTED",
            notes="cancel_requested_by_operator",
        )
        if environment == "paper":
            updated = self.db.upsert_order(
                self._order_row_from_exchange(
                    execution_order_id=str(order.get("execution_order_id")),
                    execution_intent_id=str(order.get("execution_intent_id") or ""),
                    client_order_id=str(order.get("client_order_id") or ""),
                    family=family,
                    environment=environment,
                    preview=order,
                    ack_payload={"status": "CANCELED", "symbol": order.get("symbol"), "clientOrderId": order.get("client_order_id"), "source": "paper_local_cancel"},
                    submitted_at=str(order.get("submitted_at") or utc_now_iso()),
                    intent=self.db.intent_by_id(str(order.get("execution_intent_id") or "")) if order.get("execution_intent_id") else None,
                    existing=order,
                    canceled=True,
                )
            )
            updated, _event_row, _ = self._apply_order_event(
                order=updated,
                source_type="REST_CANCEL_RESPONSE",
                payload=updated.get("raw_last_payload_json") if isinstance(updated.get("raw_last_payload_json"), dict) else {"status": "CANCELED"},
                notes="paper_cancel_applied",
            )
            heartbeat_meta = None
            if family in {"usdm_futures", "coinm_futures"} and environment in {"live", "testnet"}:
                remaining = [
                    row
                    for row in self.db.open_orders(family=family, symbol=updated.get("symbol"))
                    if _normalize_environment(row.get("environment")) == environment
                ]
                if not remaining:
                    heartbeat_meta = self._arm_futures_auto_cancel_heartbeat(
                        family=family,
                        environment=environment,
                        symbol=str(updated.get("symbol") or ""),
                        stop_timer=True,
                    )
            return {
                "execution_order_id": updated.get("execution_order_id"),
                "order_status": updated.get("order_status"),
                "canceled_count": 1,
                "order": updated,
                "remote_source": {"ok": True, "reason": "paper_local", "futures_auto_cancel": heartbeat_meta},
            }
        params: dict[str, Any] = {
            "symbol": _canonical_symbol(order.get("symbol")),
            "origClientOrderId": order.get("client_order_id"),
        }
        if order.get("venue_order_id"):
            params["orderId"] = order.get("venue_order_id")
        payload, meta = self._signed_request(
            "DELETE",
            self._execution_endpoint(family, environment, "cancel"),
            family=family,
            environment=environment,
            params=params,
        )
        if not isinstance(payload, dict):
            if self._is_unknown_exchange_result(meta):
                updated = self._mark_order_unknown_pending_reconciliation(
                    order,
                    source_type="REST_CANCEL_RESPONSE",
                    reason=str(meta.get("reason") or "unknown_cancel_result"),
                    payload={
                        "status": order.get("order_status"),
                        "clientOrderId": order.get("client_order_id"),
                        "meta": meta,
                    },
                )
                reconcile_result = self._reconcile_single_order(updated)
                resolved_order = reconcile_result["order"]
                return {
                    "execution_order_id": resolved_order.get("execution_order_id"),
                    "order_status": resolved_order.get("order_status"),
                    "current_local_state": resolved_order.get("current_local_state"),
                    "canceled_count": 0,
                    "order": resolved_order,
                    "remote_source": reconcile_result.get("remote_source"),
                }
            raise RuntimeError(str(meta.get("error") or meta.get("reason") or "cancel_failed"))
        updated = self.db.upsert_order(
            self._order_row_from_exchange(
                execution_order_id=str(order.get("execution_order_id")),
                execution_intent_id=str(order.get("execution_intent_id") or ""),
                client_order_id=str(order.get("client_order_id") or ""),
                family=family,
                environment=environment,
                preview=order,
                ack_payload=payload,
                submitted_at=str(order.get("submitted_at") or utc_now_iso()),
                intent=self.db.intent_by_id(str(order.get("execution_intent_id") or "")) if order.get("execution_intent_id") else None,
                existing=order,
                canceled=True,
            )
        )
        updated, _cancel_event, _ = self._apply_order_event(
            order=updated,
            source_type="REST_CANCEL_RESPONSE",
            payload=payload,
            notes="rest_cancel_acknowledged",
        )
        heartbeat_meta = None
        if family in {"usdm_futures", "coinm_futures"} and environment in {"live", "testnet"}:
            remaining = [
                row
                for row in self.db.open_orders(family=family, symbol=updated.get("symbol"))
                if _normalize_environment(row.get("environment")) == environment
            ]
            if not remaining:
                heartbeat_meta = self._arm_futures_auto_cancel_heartbeat(
                    family=family,
                    environment=environment,
                    symbol=str(updated.get("symbol") or ""),
                    stop_timer=True,
                )
        return {
            "execution_order_id": updated.get("execution_order_id"),
            "order_status": updated.get("order_status"),
            "current_local_state": updated.get("current_local_state"),
            "canceled_count": 1,
            "order": updated,
            "remote_source": {**meta, "futures_auto_cancel": heartbeat_meta},
        }

    def cancel_all(self, *, family: str, environment: str, symbol: str | None = None) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        target_symbol = _canonical_symbol(symbol) if symbol else None
        if not target_symbol:
            raise ValueError("symbol_required_for_cancel_all")
        open_orders = [
            row
            for row in self.db.open_orders(family=normalized_family, symbol=target_symbol)
            if str(row.get("environment") or "").lower() == normalized_environment
        ]
        if normalized_environment == "paper":
            canceled: list[dict[str, Any]] = []
            for row in open_orders:
                canceled.append(self.cancel_order(str(row.get("execution_order_id")))["order"])
            return {
                "family": normalized_family,
                "environment": normalized_environment,
                "symbol": target_symbol,
                "canceled_count": len(canceled),
                "items": canceled,
                "remote_source": {"ok": True, "reason": "paper_local", "futures_auto_cancel": None},
            }
        params = {"symbol": target_symbol}
        payload, meta = self._signed_request(
            "DELETE",
            self._execution_endpoint(normalized_family, normalized_environment, "cancel_all"),
            family=normalized_family,
            environment=normalized_environment,
            params=params,
        )
        if payload is None:
            raise RuntimeError(str(meta.get("error") or meta.get("reason") or "cancel_all_failed"))
        canceled: list[dict[str, Any]] = []
        for row in open_orders:
            updated = self.db.upsert_order(
                self._order_row_from_exchange(
                    execution_order_id=str(row.get("execution_order_id")),
                    execution_intent_id=str(row.get("execution_intent_id") or ""),
                    client_order_id=str(row.get("client_order_id") or ""),
                    family=normalized_family,
                    environment=normalized_environment,
                    preview=row,
                    ack_payload={"status": "CANCELED", "symbol": row.get("symbol"), "clientOrderId": row.get("client_order_id"), "raw_cancel_all_payload": payload},
                    submitted_at=str(row.get("submitted_at") or utc_now_iso()),
                    existing=row,
                    canceled=True,
                )
            )
            updated, _event_row, _ = self._apply_order_event(
                order=updated,
                source_type="REST_CANCEL_RESPONSE",
                payload={"status": "CANCELED", "clientOrderId": row.get("client_order_id"), "raw_cancel_all_payload": payload},
                notes="cancel_all_acknowledged",
            )
            canceled.append(updated)
        heartbeat_meta = None
        if normalized_family in {"usdm_futures", "coinm_futures"} and normalized_environment in {"live", "testnet"}:
            heartbeat_meta = self._arm_futures_auto_cancel_heartbeat(
                family=normalized_family,
                environment=normalized_environment,
                symbol=target_symbol,
                stop_timer=True,
            )
        return {
            "family": normalized_family,
            "environment": normalized_environment,
            "symbol": target_symbol,
            "canceled_count": len(canceled),
            "items": canceled,
            "remote_source": {**meta, "raw_payload": payload, "futures_auto_cancel": heartbeat_meta},
        }

    def reconcile_orders(self) -> dict[str, Any]:
        started_at = utc_now_iso()
        orders = self.db.list_orders(limit=1000, offset=0)
        pairs = {
            (_normalize_family(order.get("family")), _normalize_environment(order.get("environment")))
            for order in orders
            if _normalize_environment(order.get("environment")) in {"live", "testnet"}
        }
        degraded_mode = any(self._stream_state(family, environment)["degraded_mode"] for family, environment in pairs)
        results: list[dict[str, Any]] = []
        for order in orders:
            results.append(self._reconcile_single_order(order))
        orphan_events: list[dict[str, Any]] = []
        for family, environment in sorted(pairs):
            orphan_events.extend(self._reconcile_orphan_orders(family=family, environment=environment))
        unresolved = self.db.unresolved_reconcile_events()
        grouped: dict[str, int] = defaultdict(int)
        for row in unresolved:
            grouped[str(row.get("reconcile_type") or "")] += 1
        heartbeat_actions = self._refresh_futures_auto_cancel_heartbeats()
        summary = {
            "ack_missing": grouped.get("ack_missing", 0),
            "fill_missing": grouped.get("fill_missing", 0),
            "orphan_orders": grouped.get("orphan_order", 0),
            "status_mismatches": grouped.get("status_mismatch", 0),
            "cost_mismatches": grouped.get("cost_mismatch", 0),
            "unresolved_count": len(unresolved),
            "degraded_mode": degraded_mode,
            "policy_hash": self.policy_hash(),
            "policy_source": self.policy_source(),
            "processed_orders": len(orders),
            "orphan_events_seen": len(orphan_events),
            "futures_auto_cancel": heartbeat_actions,
            "pairs_checked": [
                {"family": family, "environment": environment, "stream_state": self._stream_state(family, environment)}
                for family, environment in sorted(pairs)
            ],
        }
        summary["reconciliation_run"] = self.db.insert_live_order_reconciliation_run(
            {
                "started_at": started_at,
                "finished_at": utc_now_iso(),
                "trigger": "PERIODIC",
                "result_summary_json": {
                    "processed_orders": len(orders),
                    "unresolved_count": len(unresolved),
                    "pairs_checked": len(pairs),
                },
            }
        )
        return summary

    def live_safety_summary(self, reconcile_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        if reconcile_summary is None:
            reconcile_summary = self.reconcile_orders() if self.db.counts().get("execution_orders", 0) else None
        parity = self.instrument_registry_service.live_parity_matrix() if self.instrument_registry_service is not None else {}
        supported_families = self._supported_live_families(parity)
        fee_details: list[dict[str, Any]] = []
        fee_fresh = bool(supported_families)
        capabilities_known = bool(supported_families)
        for family in supported_families:
            state = self._fee_source_state(family, "live")
            fee_details.append({"family": family, **state})
            fee_fresh = fee_fresh and _bool(state.get("available")) and _bool(state.get("fresh"))
            capabilities_known = capabilities_known and _bool((((parity.get(family) or {}).get("live") or {}).get("capabilities_known")))
        market_data = self._market_data_safety_state()
        snapshot_fresh = (
            all(((parity.get(family) or {}).get("live") or {}).get("snapshot_fresh", False) for family in supported_families)
            if supported_families
            else False
        )
        exchange_filter_details = [self._exchange_filter_freshness(family, "live") | {"family": family} for family in supported_families]
        exchange_filters_fresh = bool(supported_families) and all(str(item.get("status") or "") == "fresh" for item in exchange_filter_details)
        current_margin_level = self._margin_levels.get("live")
        if any(family in {"margin", "usdm_futures", "coinm_futures"} for family in supported_families):
            if not isinstance(current_margin_level, dict) or _first_number(current_margin_level.get("level")) is None:
                self._refresh_margin_level_from_account(environment="live")
        margin_state = self._margin_guard_state(supported_families=supported_families)
        market_runtime = self.market_streams_summary()
        market_runtime_sessions = market_runtime.get("sessions") if isinstance(market_runtime.get("sessions"), list) else []
        market_runtime_live_sessions = [
            row for row in market_runtime_sessions if _normalize_environment(row.get("environment")) == "live"
        ]
        market_runtime_blocked = any(_bool(row.get("block_live")) for row in market_runtime_live_sessions if _bool(row.get("running")))
        market_runtime_degraded = any(_bool(row.get("degraded_mode")) for row in market_runtime_live_sessions if _bool(row.get("running")))
        user_runtime = self.user_streams_summary()
        user_runtime_sessions = user_runtime.get("sessions") if isinstance(user_runtime.get("sessions"), list) else []
        user_runtime_live_sessions = [
            row for row in user_runtime_sessions if _normalize_environment(row.get("environment")) == "live"
        ]
        user_runtime_blocked = any(_bool(row.get("block_live")) for row in user_runtime_live_sessions if _bool(row.get("running")))
        user_runtime_degraded = any(_bool(row.get("degraded_mode")) for row in user_runtime_live_sessions if _bool(row.get("running")))
        cached_live_user_status = [
            copy.deepcopy(row)
            for (family, environment), row in self._user_stream_status.items()
            if _normalize_environment(environment) == "live"
        ]
        user_runtime_blocked = user_runtime_blocked or any(_bool(row.get("block_live")) for row in cached_live_user_status)
        user_runtime_degraded = user_runtime_degraded or any(_bool(row.get("degraded_mode")) for row in cached_live_user_status)
        degraded_mode = any(
            _bool(row.get("degraded_mode"))
            for (family, environment), row in self._user_stream_status.items()
            if _normalize_environment(environment) in {"live", "testnet"}
        )
        degraded_mode = degraded_mode or market_runtime_degraded or user_runtime_degraded
        kill_switch = self.kill_switch_status()
        open_orders_guard = self._open_order_safety_state()
        reject_storm_count = self._recent_rejected_order_count(window_sec=300.0)
        consecutive_failed_submit_count = self._consecutive_failed_submit_count()
        repeated_reconcile_mismatch_count = self._repeated_reconcile_mismatch_count()
        ks_cfg = self._kill_switch_policy()
        reject_storm_threshold = max(0, int(_safe_float(ks_cfg.get("critical_rejects_5m_block"), 0.0)))
        consecutive_failed_submit_threshold = max(0, int(_safe_float(ks_cfg.get("consecutive_failed_submits_block"), 0.0)))
        repeated_reconcile_mismatch_threshold = max(
            0,
            int(_safe_float(ks_cfg.get("repeated_reconcile_mismatch_block_count"), 0.0)),
        )
        unresolved_live_orders = self.unresolved_live_orders(environment="live")
        reconciliation_engine = self.reconciliation_summary(environment="live")
        futures_auto_cancel = [
            copy.deepcopy(item)
            for item in sorted(
                self._futures_auto_cancel_status.values(),
                key=lambda row: (str(row.get("family") or ""), str(row.get("environment") or ""), str(row.get("symbol") or "")),
            )
        ]
        blockers: list[str] = []
        warnings: list[str] = []
        if not self.policies_loaded():
            blockers.append("execution_policy_not_loaded")
        if kill_switch.get("active"):
            blockers.append("kill_switch_active")
        elif kill_switch.get("cooldown_active"):
            blockers.append("kill_switch_cooldown_active")
        if market_data.get("quote_stale"):
            blockers.append("stale_quote_blocker")
        if market_data.get("orderbook_stale"):
            blockers.append("stale_orderbook_blocker")
        if market_runtime_blocked:
            blockers.append("market_ws_runtime_blocker")
        if user_runtime_blocked:
            blockers.append("user_stream_runtime_blocker")
        if reject_storm_threshold > 0 and reject_storm_count >= reject_storm_threshold:
            blockers.append("reject_storm_blocker")
        if consecutive_failed_submit_threshold > 0 and consecutive_failed_submit_count >= consecutive_failed_submit_threshold:
            blockers.append("consecutive_failed_submit_blocker")
        if repeated_reconcile_mismatch_threshold > 0 and repeated_reconcile_mismatch_count >= repeated_reconcile_mismatch_threshold:
            blockers.append("repeated_reconcile_mismatch_blocker")
        if int(unresolved_live_orders.get("count") or 0) > 0:
            blockers.append("unresolved_live_orders_blocker")
        if int(reconciliation_engine.get("blocking_cases_count") or 0) > 0:
            blockers.append("reconciliation_desync_blocker")
        if open_orders_guard.get("breached"):
            blockers.append("open_orders_limit_blocker")
        if not fee_fresh:
            blockers.append("cost_source_missing_blocker")
        if not snapshot_fresh:
            blockers.append("snapshot_freshness_blocker")
        if not exchange_filters_fresh:
            blockers.append("exchange_filters_blocker")
        if not capabilities_known:
            blockers.append("capability_snapshot_blocker")
        if str(margin_state.get("status") or "").upper() == "BLOCK":
            blockers.append("margin_level_blocker")
        if degraded_mode:
            warnings.append("degraded_mode")
        if market_runtime_degraded:
            warnings.append("market_ws_degraded")
        if user_runtime_degraded:
            warnings.append("user_stream_degraded")
        if str(margin_state.get("status") or "").upper() == "WARN":
            warnings.append("margin_level_warn")
        if any(item.get("supported") and item.get("enabled") and not item.get("ok") for item in futures_auto_cancel):
            warnings.append("futures_auto_cancel_unavailable")
        overall = "BLOCK" if blockers else "WARN" if warnings else "OK"
        return {
            "live_parity_base_ready": all(
                ((parity.get(family) or {}).get("live") or {}).get("live_parity_base_ready", False)
                for family in supported_families
            ) if supported_families else False,
            "execution_policy_loaded": self.policies_loaded(),
            "policy_hash": self.policy_hash(),
            "kill_switch_armed": _bool(kill_switch.get("armed")),
            "kill_switch_active": _bool(kill_switch.get("active")),
            "kill_switch_status": kill_switch,
            "stale_market_data": _bool(market_data.get("stale_market_data")),
            "stale_quote": _bool(market_data.get("quote_stale")),
            "stale_orderbook": _bool(market_data.get("orderbook_stale")),
            "fee_source_fresh": fee_fresh,
            "fee_source_details": fee_details,
            "snapshot_fresh": snapshot_fresh,
            "exchange_filters_fresh": exchange_filters_fresh,
            "exchange_filters_details": exchange_filter_details,
            "capabilities_known": capabilities_known,
            "margin_guard_status": margin_state.get("status"),
            "margin_guard": margin_state,
            "degraded_mode": degraded_mode,
            "supported_families": supported_families,
            "reject_storm_count_5m": reject_storm_count,
            "reject_storm_threshold": reject_storm_threshold,
            "consecutive_failed_submit_count": consecutive_failed_submit_count,
            "consecutive_failed_submit_threshold": consecutive_failed_submit_threshold,
            "repeated_reconcile_mismatch_count": repeated_reconcile_mismatch_count,
            "repeated_reconcile_mismatch_threshold": repeated_reconcile_mismatch_threshold,
            "unresolved_live_orders": unresolved_live_orders,
            "reconciliation_engine": reconciliation_engine,
            "open_orders_guard": open_orders_guard,
            "market_data_guard": market_data,
            "market_stream_runtime": market_runtime,
            "market_stream_runtime_blocked": market_runtime_blocked,
            "market_stream_runtime_degraded": market_runtime_degraded,
            "user_stream_runtime": user_runtime,
            "user_stream_runtime_blocked": user_runtime_blocked,
            "user_stream_runtime_degraded": user_runtime_degraded,
            "futures_auto_cancel": futures_auto_cancel,
            "risk_reduce_only_priority_enabled": _bool(self._risk_reduce_only_priority_policy().get("enabled")),
            "safety_blockers": blockers,
            "safety_warnings": warnings,
            "overall_status": overall,
            "policy_source": self.policy_source(),
            "unresolved_reconcile_count": int((reconcile_summary or {}).get("unresolved_count") or 0),
        }

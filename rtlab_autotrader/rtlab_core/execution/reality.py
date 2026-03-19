from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import requests
import yaml

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
    "fill_missing",
    "status_mismatch",
    "orphan_order",
    "cost_mismatch",
    "position_mismatch",
}
RECONCILE_SEVERITIES = {"INFO", "WARN", "BLOCK"}
TERMINAL_ORDER_STATUSES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}

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
    if value in {None, ""}:
        return copy.deepcopy(default)
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
    if out.get("reduce_only") is not None:
        out["reduce_only"] = _bool(out.get("reduce_only"))
    return out


def _hydrate_fill_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["raw_fill_json"] = _json_loads(out.get("raw_fill_json"), {})
    if out.get("maker") is not None:
        out["maker"] = _bool(out.get("maker"))
    return out


def _hydrate_reconcile_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["details_json"] = _json_loads(out.get("details_json"), {})
    out["resolved"] = _bool(out.get("resolved"))
    return out


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
                  venue_order_id TEXT,
                  client_order_id TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  order_status TEXT NOT NULL,
                  execution_type_last TEXT,
                  submitted_at TEXT NOT NULL,
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
                  reject_code TEXT,
                  reject_reason TEXT,
                  raw_ack_json TEXT NOT NULL DEFAULT '{}',
                  raw_last_status_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_execution_orders_submitted_at ON execution_orders(submitted_at DESC);
                CREATE INDEX IF NOT EXISTS idx_execution_orders_status ON execution_orders(order_status, family, environment);

                CREATE TABLE IF NOT EXISTS execution_fills (
                  execution_fill_id TEXT PRIMARY KEY,
                  execution_order_id TEXT NOT NULL,
                  venue_trade_id TEXT,
                  fill_time TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  family TEXT NOT NULL,
                  price REAL NOT NULL,
                  qty REAL NOT NULL,
                  quote_qty REAL,
                  commission REAL NOT NULL DEFAULT 0.0,
                  commission_asset TEXT,
                  realized_pnl REAL,
                  maker INTEGER,
                  funding_component REAL,
                  borrow_interest_component REAL,
                  raw_fill_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_execution_fills_fill_time ON execution_fills(fill_time DESC);

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

                CREATE TABLE IF NOT EXISTS kill_switch_events (
                  kill_switch_event_id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  trigger_type TEXT NOT NULL,
                  severity TEXT NOT NULL,
                  family TEXT,
                  symbol TEXT,
                  reason TEXT NOT NULL,
                  auto_actions_json TEXT NOT NULL DEFAULT '[]',
                  cleared_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_kill_switch_events_created_at ON kill_switch_events(created_at DESC);
                """
            )

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
            "kill_switch_events",
        )
        with self._connect() as conn:
            return {table: int(conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]) for table in tables}

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
            "venue_order_id": payload.get("venue_order_id"),
            "client_order_id": str(payload.get("client_order_id") or uuid4().hex[:24]),
            "symbol": str(payload.get("symbol") or ""),
            "family": str(payload.get("family") or ""),
            "environment": str(payload.get("environment") or ""),
            "order_status": str(payload.get("order_status") or "CREATED"),
            "execution_type_last": payload.get("execution_type_last"),
            "submitted_at": str(payload.get("submitted_at") or utc_now_iso()),
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
            "reject_code": payload.get("reject_code"),
            "reject_reason": payload.get("reject_reason"),
            "raw_ack_json": _json_dumps(payload.get("raw_ack_json") or {}),
            "raw_last_status_json": _json_dumps(payload.get("raw_last_status_json") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_orders (
                  execution_order_id, execution_intent_id, venue_order_id, client_order_id, symbol, family,
                  environment, order_status, execution_type_last, submitted_at, acknowledged_at, canceled_at,
                  expired_at, reduce_only, tif, price, orig_qty, executed_qty, cum_quote_qty, avg_fill_price,
                  reject_code, reject_reason, raw_ack_json, raw_last_status_json
                ) VALUES (
                  :execution_order_id, :execution_intent_id, :venue_order_id, :client_order_id, :symbol, :family,
                  :environment, :order_status, :execution_type_last, :submitted_at, :acknowledged_at, :canceled_at,
                  :expired_at, :reduce_only, :tif, :price, :orig_qty, :executed_qty, :cum_quote_qty, :avg_fill_price,
                  :reject_code, :reject_reason, :raw_ack_json, :raw_last_status_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM execution_orders WHERE execution_order_id = ?",
                (row["execution_order_id"],),
            ).fetchone()
        return _hydrate_order_row(_row_to_dict(stored) or row) or row

    def insert_fill(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "execution_fill_id": str(payload.get("execution_fill_id") or uuid4()),
            "execution_order_id": str(payload.get("execution_order_id") or ""),
            "venue_trade_id": payload.get("venue_trade_id"),
            "fill_time": str(payload.get("fill_time") or utc_now_iso()),
            "symbol": str(payload.get("symbol") or ""),
            "family": str(payload.get("family") or ""),
            "price": payload.get("price"),
            "qty": payload.get("qty"),
            "quote_qty": payload.get("quote_qty"),
            "commission": payload.get("commission", 0.0),
            "commission_asset": payload.get("commission_asset"),
            "realized_pnl": payload.get("realized_pnl"),
            "maker": _db_bool(payload.get("maker")),
            "funding_component": payload.get("funding_component"),
            "borrow_interest_component": payload.get("borrow_interest_component"),
            "raw_fill_json": _json_dumps(payload.get("raw_fill_json") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_fills (
                  execution_fill_id, execution_order_id, venue_trade_id, fill_time, symbol, family,
                  price, qty, quote_qty, commission, commission_asset, realized_pnl, maker,
                  funding_component, borrow_interest_component, raw_fill_json
                ) VALUES (
                  :execution_fill_id, :execution_order_id, :venue_trade_id, :fill_time, :symbol, :family,
                  :price, :qty, :quote_qty, :commission, :commission_asset, :realized_pnl, :maker,
                  :funding_component, :borrow_interest_component, :raw_fill_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM execution_fills WHERE execution_fill_id = ?",
                (row["execution_fill_id"],),
            ).fetchone()
        return _hydrate_fill_row(_row_to_dict(stored) or row) or row

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
                ORDER BY fill_time ASC, execution_fill_id ASC
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
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM execution_reconcile_events
                WHERE resolved = 0
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [_hydrate_reconcile_row(_row_to_dict(row)) or {} for row in rows]

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
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kill_switch_events (
                  kill_switch_event_id, created_at, trigger_type, severity, family, symbol, reason, auto_actions_json, cleared_at
                ) VALUES (
                  :kill_switch_event_id, :created_at, :trigger_type, :severity, :family, :symbol, :reason, :auto_actions_json, :cleared_at
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

    def reset_kill_switch(self) -> dict[str, Any]:
        cleared_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute("UPDATE kill_switch_events SET cleared_at = ? WHERE cleared_at IS NULL", (cleared_at,))
        return self.kill_switch_status()

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
        self._margin_levels: dict[str, dict[str, Any]] = {}

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
        payload = body if isinstance(body, dict) else {}
        if payload:
            snapshot = {
                "bid": _first_number(payload.get("bid")),
                "ask": _first_number(payload.get("ask")),
                "quote_ts_ms": int(payload.get("quote_ts_ms") or int(time.time() * 1000)),
                "orderbook_ts_ms": int(payload.get("orderbook_ts_ms") or int(time.time() * 1000)),
                "source": str(payload.get("source") or "request"),
                "updated_at": utc_now_iso(),
            }
            self._quotes[(_normalize_family(family), _normalize_environment(environment), _canonical_symbol(symbol))] = snapshot
            return snapshot
        key = (_normalize_family(family), _normalize_environment(environment), _canonical_symbol(symbol))
        cached = self._quotes.get(key)
        if isinstance(cached, dict):
            return copy.deepcopy(cached)
        return {"bid": None, "ask": None, "quote_ts_ms": None, "orderbook_ts_ms": None, "source": "missing", "updated_at": None}

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
        bid = _first_number(quote.get("bid"))
        ask = _first_number(quote.get("ask"))
        expected_price = limit_price
        if expected_price is None:
            expected_price = ask or bid if side == "BUY" else bid or ask
        normalized_qty = None if qty is None else _decimal_floor(qty, step_size)
        normalized_price = None if limit_price is None else _decimal_floor(limit_price, tick_size)
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
            "limit_price_provided": limit_price is not None,
            "preview_price": preview_price,
            "requested_notional": requested_notional,
            "reduce_only": None if request.get("reduce_only") is None else _bool(request.get("reduce_only")),
            "step_size": step_size,
            "tick_size": tick_size,
            "price_filter": price_filter,
            "lot_size": lot_size,
            "market_lot_size": market_lot_size,
        }

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
        self._user_stream_status[(str(family), str(environment))] = payload
        return payload

    def set_margin_level(self, *, environment: str, level: float | None, source: str = "manual") -> dict[str, Any]:
        payload = {
            "level": level,
            "source": str(source or "manual"),
            "updated_at": utc_now_iso(),
        }
        self._margin_levels[str(environment)] = payload
        return payload

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
                "margin_levels": len(self._margin_levels),
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
            endpoint = str(cfg.get("testnet" if environment == "testnet" else "live") or "").strip()
            override = os.getenv("BINANCE_SPOT_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_SPOT_BASE_URL")
            return _url_root(_apply_base_override(endpoint, override))
        if family == "margin":
            cfg = endpoints.get("margin") if isinstance(endpoints.get("margin"), dict) else {}
            endpoint = str(cfg.get("live_account") or "").strip()
            override = os.getenv("BINANCE_MARGIN_BASE_URL") or os.getenv("BINANCE_SPOT_BASE_URL")
            return _url_root(_apply_base_override(endpoint, override))
        if family == "usdm_futures":
            cfg = endpoints.get("usdm_futures") if isinstance(endpoints.get("usdm_futures"), dict) else {}
            endpoint = str(cfg.get("testnet" if environment == "testnet" else "live") or "").strip()
            override = os.getenv("BINANCE_USDM_TESTNET_BASE_URL" if environment == "testnet" else "BINANCE_USDM_BASE_URL")
            return _url_root(_apply_base_override(endpoint, override))
        if family == "coinm_futures":
            cfg = endpoints.get("coinm_futures") if isinstance(endpoints.get("coinm_futures"), dict) else {}
            endpoint = str(cfg.get("testnet" if environment == "testnet" else "live") or "").strip()
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
            ("margin", "submit"): "/sapi/v1/margin/order",
            ("margin", "query"): "/sapi/v1/margin/order",
            ("margin", "open_orders"): "/sapi/v1/margin/openOrders",
            ("margin", "cancel"): "/sapi/v1/margin/order",
            ("margin", "cancel_all"): "/sapi/v1/margin/openOrders",
            ("usdm_futures", "submit"): "/fapi/v1/order",
            ("usdm_futures", "query"): "/fapi/v1/order",
            ("usdm_futures", "open_orders"): "/fapi/v1/openOrders",
            ("usdm_futures", "cancel"): "/fapi/v1/order",
            ("usdm_futures", "cancel_all"): "/fapi/v1/allOpenOrders",
            ("coinm_futures", "submit"): "/dapi/v1/order",
            ("coinm_futures", "query"): "/dapi/v1/order",
            ("coinm_futures", "open_orders"): "/dapi/v1/openOrders",
            ("coinm_futures", "cancel"): "/dapi/v1/order",
            ("coinm_futures", "cancel_all"): "/dapi/v1/allOpenOrders",
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
        api_key, api_secret, env_names = _credentials_for_family(family, environment)
        if not api_key or not api_secret or not endpoint_url:
            return None, {
                "ok": False,
                "reason": "missing_credentials",
                "credentials_present": False,
                "credential_envs_tried": env_names,
                "endpoint": endpoint_url,
                "method": method.upper(),
            }
        filtered = {
            str(key): value
            for key, value in (params or {}).items()
            if value is not None and str(value) != ""
        }
        filtered.setdefault("timestamp", int(time.time() * 1000))
        filtered.setdefault("recvWindow", 5000)
        query = urlencode(filtered, doseq=True)
        signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
        url = f"{endpoint_url}?{query}&signature={signature}"
        headers = {"X-MBX-APIKEY": api_key}
        try:
            response = requests.request(method.upper(), url, headers=headers, timeout=self._request_timeout())
            response.raise_for_status()
            payload = response.json() if response.content else {}
            return payload, {
                "ok": True,
                "reason": "ok",
                "credentials_present": True,
                "credential_envs_tried": env_names,
                "endpoint": endpoint_url,
                "method": method.upper(),
            }
        except Exception as exc:
            return None, {
                "ok": False,
                "reason": "signed_request_failed",
                "credentials_present": True,
                "credential_envs_tried": env_names,
                "endpoint": endpoint_url,
                "method": method.upper(),
                "error": str(exc),
            }

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
            "newOrderRespType": "ACK",
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
        acknowledged_at: str | None = None,
        existing: dict[str, Any] | None = None,
        canceled: bool = False,
    ) -> dict[str, Any]:
        payload = ack_payload if isinstance(ack_payload, dict) else {}
        current = existing or {}
        raw_last = payload or current.get("raw_last_status_json") or {}
        order_status = str(
            payload.get("status")
            or raw_last.get("status")
            or current.get("order_status")
            or ("CANCELED" if canceled else "NEW")
        ).upper()
        ack_time = acknowledged_at or _ms_to_iso(payload.get("updateTime")) or _ms_to_iso(payload.get("transactTime")) or current.get("acknowledged_at") or submitted_at
        canceled_at = (
            utc_now_iso()
            if canceled or order_status == "CANCELED"
            else current.get("canceled_at")
        )
        return {
            "execution_order_id": str(current.get("execution_order_id") or execution_order_id),
            "execution_intent_id": execution_intent_id,
            "venue_order_id": str(payload.get("orderId") or current.get("venue_order_id") or "") or None,
            "client_order_id": str(
                payload.get("clientOrderId")
                or payload.get("origClientOrderId")
                or current.get("client_order_id")
                or client_order_id
            ),
            "symbol": _canonical_symbol(payload.get("symbol") or preview.get("symbol") or current.get("symbol")),
            "family": family,
            "environment": environment,
            "order_status": order_status,
            "execution_type_last": str(payload.get("executionType") or current.get("execution_type_last") or order_status),
            "submitted_at": str(current.get("submitted_at") or submitted_at),
            "acknowledged_at": ack_time,
            "canceled_at": canceled_at,
            "expired_at": current.get("expired_at"),
            "reduce_only": current.get("reduce_only") if current.get("reduce_only") is not None else preview.get("reduce_only"),
            "tif": str(payload.get("timeInForce") or preview.get("time_in_force") or current.get("tif") or "") or None,
            "price": _first_number(payload.get("price"), preview.get("limit_price"), current.get("price")),
            "orig_qty": _first_number(payload.get("origQty"), preview.get("quantity"), current.get("orig_qty")),
            "executed_qty": _first_number(payload.get("executedQty"), current.get("executed_qty")) or 0.0,
            "cum_quote_qty": _first_number(payload.get("cummulativeQuoteQty"), payload.get("cumQuote"), current.get("cum_quote_qty")) or 0.0,
            "avg_fill_price": _first_number(payload.get("avgPrice"), current.get("avg_fill_price")),
            "reject_code": payload.get("code") or current.get("reject_code"),
            "reject_reason": payload.get("msg") or current.get("reject_reason"),
            "raw_ack_json": payload if payload else current.get("raw_ack_json") or {},
            "raw_last_status_json": raw_last,
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
                            "order_status": str(row.get("status") or "NEW").upper(),
                            "execution_type_last": str(row.get("executionType") or row.get("status") or "NEW").upper(),
                            "submitted_at": _ms_to_iso(row.get("time")) or utc_now_iso(),
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
                            "reject_code": None,
                            "reject_reason": None,
                            "raw_ack_json": {},
                            "raw_last_status_json": row,
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
        quote = self._quote_snapshot(
            family,
            environment,
            symbol,
            request.get("market_snapshot") if isinstance(request.get("market_snapshot"), dict) else None,
        )

        if instrument is None:
            preview = {
                "symbol": symbol,
                "side": str(request.get("side") or "").upper(),
                "order_type": str(request.get("order_type") or "").upper(),
                "quantity": request.get("quantity"),
                "quote_quantity": request.get("quote_quantity"),
                "limit_price": request.get("price"),
                "preview_price": request.get("price"),
                "requested_notional": _safe_float(request.get("requested_notional"), 0.0),
                "reduce_only": request.get("reduce_only"),
                "time_in_force": request.get("time_in_force"),
            }
            costs = self._estimated_costs(family=family or "spot", request=request, preview=preview, instrument={})
        else:
            preview = self._normalize_order(instrument, request, quote)
            costs = self._estimated_costs(family=family, request=request, preview=preview, instrument=instrument)

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
            if _bool(preflight_cfg.get("reject_if_missing_basic_filters")):
                if not isinstance(filters.get("price_filter"), dict) or not isinstance(filters.get("lot_size"), dict):
                    blocking.append("missing_basic_filters")

            price_filter = preview.get("price_filter") if isinstance(preview.get("price_filter"), dict) else {}
            lot_size = preview.get("lot_size") if isinstance(preview.get("lot_size"), dict) else {}
            market_lot_size = preview.get("market_lot_size") if isinstance(preview.get("market_lot_size"), dict) else {}
            active_size_filter = market_lot_size if preview.get("order_type") == "MARKET" and market_lot_size else lot_size
            min_qty = _first_number((active_size_filter or {}).get("min_qty"))
            max_qty = _first_number((active_size_filter or {}).get("max_qty"))
            qty = _first_number(preview.get("quantity"))
            quote_qty = _first_number(preview.get("quote_quantity"))
            if qty is None and quote_qty is None:
                blocking.append("quantity_or_quote_quantity_required")
            if preview.get("order_type") == "LIMIT" and qty is None:
                blocking.append("quantity_required_for_limit")
            if family in {"usdm_futures", "coinm_futures"} and qty is None:
                blocking.append("quantity_required_for_futures")
            if qty is not None and min_qty is not None and qty < min_qty:
                blocking.append("quantity_below_min_qty")
            if qty is not None and max_qty is not None and qty > max_qty:
                blocking.append("quantity_above_max_qty")

            limit_price = _first_number(preview.get("limit_price"))
            if preview.get("order_type") == "LIMIT" and not _bool(preview.get("limit_price_provided")):
                blocking.append("limit_price_required")
            if limit_price is not None:
                min_price = _first_number((price_filter or {}).get("min_price"))
                max_price = _first_number((price_filter or {}).get("max_price"))
                if min_price is not None and limit_price < min_price:
                    blocking.append("price_below_min_price")
                if max_price is not None and max_price > 0 and limit_price > max_price:
                    blocking.append("price_above_max_price")

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
            age_ms = max(0, int(time.time() * 1000) - int(quote_ts_ms))
            if age_ms >= int(preflight_cfg.get("quote_stale_block_ms") or 0):
                blocking.append("quote_stale")
                if mode == "live":
                    fail_closed = True

        orderbook_ts_ms = quote.get("orderbook_ts_ms")
        if orderbook_ts_ms is not None:
            ob_age_ms = max(0, int(time.time() * 1000) - int(orderbook_ts_ms))
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
            "warnings": warnings,
            "blocking_reasons": blocking,
            "normalized_order_preview": preview,
            "estimated_costs": costs,
            "policy_source": self.policy_source(),
            "snapshot_source": {
                "snapshot_id": (latest_snapshot or {}).get("snapshot_id"),
                "fetched_at": (latest_snapshot or {}).get("fetched_at"),
                "freshness": freshness,
                "universe_membership": membership,
            },
            "capability_source": {
                "capability_snapshot_id": (capability or {}).get("capability_snapshot_id"),
                "capability_source": (capability or {}).get("capability_source"),
                "can_trade": _bool((capability or {}).get("can_trade")),
            },
            "fail_closed": fail_closed,
        }

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = copy.deepcopy(payload)
        preflight = self.preflight(request)
        normalized = preflight.get("normalized_order_preview") if isinstance(preflight.get("normalized_order_preview"), dict) else {}
        estimated_costs = preflight.get("estimated_costs") if isinstance(preflight.get("estimated_costs"), dict) else {}
        family = _normalize_family(request.get("family"))
        environment = _normalize_environment(request.get("environment"))
        mode = _normalize_mode(request.get("mode"), environment)
        submitted_at = utc_now_iso()

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
                "raw_request_json": request,
            }
        )

        if not _bool(preflight.get("allowed")):
            return {
                "execution_intent_id": intent.get("execution_intent_id"),
                "execution_order_id": None,
                "client_order_id": intent.get("client_order_id"),
                "family": family,
                "environment": environment,
                "mode": mode,
                "order_status": "BLOCKED",
                "estimated_costs": estimated_costs,
                "fail_closed": _bool(preflight.get("fail_closed")),
                "warnings": preflight.get("warnings") or [],
                "blocking_reasons": preflight.get("blocking_reasons") or [],
                "preflight": preflight,
            }

        if environment == "paper":
            order = self.db.upsert_order(
                self._order_row_from_exchange(
                    execution_order_id=str(uuid4()),
                    execution_intent_id=str(intent.get("execution_intent_id")),
                    client_order_id=str(intent.get("client_order_id")),
                    family=family,
                    environment=environment,
                    preview=normalized,
                    ack_payload=self._paper_ack_payload(normalized, str(intent.get("client_order_id")), submitted_at),
                    submitted_at=submitted_at,
                    acknowledged_at=submitted_at,
                )
            )
            self.db.update_intent_submission(
                str(intent.get("execution_intent_id")),
                submitted_at=submitted_at,
                preflight_status="submitted",
            )
            return {
                "execution_intent_id": intent.get("execution_intent_id"),
                "execution_order_id": order.get("execution_order_id"),
                "client_order_id": order.get("client_order_id"),
                "family": family,
                "environment": environment,
                "mode": mode,
                "order_status": order.get("order_status"),
                "estimated_costs": estimated_costs,
                "fail_closed": False,
                "warnings": preflight.get("warnings") or [],
                "blocking_reasons": [],
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
                "warnings": preflight.get("warnings") or [],
                "blocking_reasons": list(local_blocking),
                "preflight": preflight,
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
            self.db.update_intent_submission(
                str(intent.get("execution_intent_id")),
                preflight_status="submit_failed",
                preflight_errors_json=[str(meta.get("reason") or "submit_failed")],
            )
            return {
                "execution_intent_id": intent.get("execution_intent_id"),
                "execution_order_id": None,
                "client_order_id": intent.get("client_order_id"),
                "family": family,
                "environment": environment,
                "mode": mode,
                "order_status": "SUBMIT_FAILED",
                "estimated_costs": estimated_costs,
                "fail_closed": mode == "live",
                "warnings": preflight.get("warnings") or [],
                "blocking_reasons": [str(meta.get("reason") or "submit_failed")],
                "submit_meta": meta,
            }

        order = self.db.upsert_order(
            self._order_row_from_exchange(
                execution_order_id=str(uuid4()),
                execution_intent_id=str(intent.get("execution_intent_id")),
                client_order_id=str(intent.get("client_order_id")),
                family=family,
                environment=environment,
                preview=normalized,
                ack_payload=ack_payload,
                submitted_at=submitted_at,
            )
        )
        self.db.update_intent_submission(
            str(intent.get("execution_intent_id")),
            submitted_at=submitted_at,
            preflight_status="submitted",
        )
        return {
            "execution_intent_id": intent.get("execution_intent_id"),
            "execution_order_id": order.get("execution_order_id"),
            "client_order_id": order.get("client_order_id"),
            "family": family,
            "environment": environment,
            "mode": mode,
            "order_status": order.get("order_status"),
            "estimated_costs": estimated_costs,
            "fail_closed": False,
            "warnings": preflight.get("warnings") or [],
            "blocking_reasons": [],
            "submit_meta": meta,
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

    def order_detail(self, execution_order_id: str) -> dict[str, Any] | None:
        order = self.db.order_by_id(execution_order_id)
        if order is None:
            return None
        remote_status = None
        remote_meta = None
        if str(order.get("environment") or "").lower() in {"live", "testnet"}:
            remote_status, remote_meta = self._query_remote_order_snapshot(order)
            if remote_status is not None:
                order = remote_status
        intent = self.db.intent_by_id(str(order.get("execution_intent_id") or "")) if order.get("execution_intent_id") else None
        return {
            "order": order,
            "intent": intent,
            "fills": self.db.fills_for_order(str(order.get("execution_order_id"))),
            "reconcile_events": self.db.reconcile_events_for_order(str(order.get("execution_order_id"))),
            "remote_status": remote_status.get("raw_last_status_json") if isinstance(remote_status, dict) else None,
            "remote_source": remote_meta,
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
                    existing=order,
                    canceled=True,
                )
            )
            return {
                "execution_order_id": updated.get("execution_order_id"),
                "order_status": updated.get("order_status"),
                "canceled_count": 1,
                "order": updated,
                "remote_source": {"ok": True, "reason": "paper_local"},
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
                existing=order,
                canceled=True,
            )
        )
        return {
            "execution_order_id": updated.get("execution_order_id"),
            "order_status": updated.get("order_status"),
            "canceled_count": 1,
            "order": updated,
            "remote_source": meta,
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
                "remote_source": {"ok": True, "reason": "paper_local"},
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
            canceled.append(updated)
        return {
            "family": normalized_family,
            "environment": normalized_environment,
            "symbol": target_symbol,
            "canceled_count": len(canceled),
            "items": canceled,
            "remote_source": {**meta, "raw_payload": payload},
        }

    def reconcile_orders(self) -> dict[str, Any]:
        raise NotImplementedError("Execution reconcile se implementa en la parte 3.4 del bloque.")

    def live_safety_summary(self) -> dict[str, Any]:
        parity = self.instrument_registry_service.live_parity_matrix() if self.instrument_registry_service is not None else {}
        fee_fresh = True
        supported_families = []
        capabilities_known = True
        for family in {"spot", "margin", "usdm_futures", "coinm_futures"}:
            live_payload = ((parity.get(family) or {}).get("live") or {}) if isinstance(parity, dict) else {}
            if live_payload.get("supported"):
                supported_families.append(family)
                fee_fresh = fee_fresh and _bool(self._fee_source_state(family, "live").get("fresh"))
                capabilities_known = capabilities_known and _bool(live_payload.get("capabilities_known"))
        stale_market_data = False
        if not self._quotes:
            stale_market_data = True
        else:
            block_ms = int((self.safety_policy().get("preflight") or {}).get("quote_stale_block_ms") or 0)
            for snapshot in self._quotes.values():
                quote_ts_ms = snapshot.get("quote_ts_ms")
                if quote_ts_ms is None:
                    stale_market_data = True
                    break
                if int(time.time() * 1000) - int(quote_ts_ms) >= block_ms:
                    stale_market_data = True
                    break
        snapshot_fresh = all(
            ((parity.get(family) or {}).get("live") or {}).get("snapshot_fresh", False)
            for family in supported_families
        ) if supported_families else False
        margin_payload = self._margin_levels.get("live") or {}
        margin_status = "unknown"
        if margin_payload.get("level") is not None:
            level = _safe_float(margin_payload.get("level"), 0.0)
            if level < _safe_float((self.safety_policy().get("margin") or {}).get("block_margin_level_below")):
                margin_status = "BLOCK"
            elif level < _safe_float((self.safety_policy().get("margin") or {}).get("warn_margin_level_below")):
                margin_status = "WARN"
            else:
                margin_status = "OK"
        degraded_mode = any(_bool(row.get("degraded_mode")) for row in self._user_stream_status.values())
        overall = "OK"
        if not snapshot_fresh or not fee_fresh or stale_market_data or not capabilities_known:
            overall = "BLOCK"
        elif margin_status == "WARN" or degraded_mode:
            overall = "WARN"
        return {
            "live_parity_base_ready": all(
                ((parity.get(family) or {}).get("live") or {}).get("live_parity_base_ready", False)
                for family in supported_families
            ) if supported_families else False,
            "execution_policy_loaded": self.policies_loaded(),
            "policy_hash": self.policy_hash(),
            "stale_market_data": stale_market_data,
            "fee_source_fresh": fee_fresh,
            "snapshot_fresh": snapshot_fresh,
            "capabilities_known": capabilities_known,
            "margin_guard_status": margin_status,
            "degraded_mode": degraded_mode,
            "supported_families": supported_families,
            "overall_status": overall,
            "policy_source": self.policy_source(),
        }

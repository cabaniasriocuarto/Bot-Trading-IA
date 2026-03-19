from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import requests
import yaml

from rtlab_core.policy_paths import resolve_policy_root


VENUE_BINANCE = "binance"
FAMILIES: tuple[str, ...] = ("spot", "margin", "usdm_futures", "coinm_futures")
ENVIRONMENTS: tuple[str, ...] = ("live", "testnet")
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
PARSER_VERSION = "execution_reality_v1"
OPEN_ORDER_STATUSES = {"NEW", "PARTIALLY_FILLED", "PENDING_CANCEL"}
FINAL_ORDER_STATUSES = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}
RECONCILE_TYPES = {
    "ack_missing",
    "fill_missing",
    "status_mismatch",
    "orphan_order",
    "cost_mismatch",
    "position_mismatch",
}

DEFAULT_EXECUTION_SAFETY_POLICY: dict[str, Any] = {
    "execution_safety": {
        "modes": {
            "allow_live": True,
            "allow_testnet": True,
            "allow_paper": True,
            "allow_shadow": True,
        },
        "preflight": {
            "require_policy_loaded": True,
            "require_instrument_registry_match": True,
            "require_universe_membership_for_live": True,
            "require_live_eligible": True,
            "require_capability_snapshot": True,
            "require_snapshot_fresh": True,
            "snapshot_block_if_older_than_hours": 72,
            "quote_stale_block_ms": 3000,
            "orderbook_stale_warn_ms": 1500,
            "orderbook_stale_block_ms": 5000,
            "reject_if_missing_basic_filters": True,
            "reject_if_missing_fee_source_in_live": True,
        },
        "sizing": {
            "max_notional_per_order_usd": 5000.0,
            "max_open_orders_per_symbol": 6,
            "max_open_orders_total": 40,
            "min_notional_buffer_pct_above_exchange_min": 5.0,
        },
        "slippage": {
            "warn_bps_spot": 10.0,
            "block_bps_spot": 25.0,
            "warn_bps_margin": 12.0,
            "block_bps_margin": 30.0,
            "warn_bps_usdm": 8.0,
            "block_bps_usdm": 20.0,
            "warn_bps_coinm": 10.0,
            "block_bps_coinm": 25.0,
        },
        "reconciliation": {
            "poll_open_orders_sec": 5,
            "poll_order_status_sec": 3,
            "poll_user_trades_sec": 10,
            "order_ack_timeout_sec": 8,
            "fill_reconcile_timeout_sec": 20,
            "orphan_order_warn_sec": 30,
            "orphan_order_block_sec": 120,
        },
        "kill_switch": {
            "enabled": True,
            "auto_cancel_all_on_trip": True,
            "cooldown_sec": 300,
            "critical_rejects_5m_block": 8,
            "consecutive_failed_submits_block": 5,
            "stale_market_data_block_ms": 5000,
            "repeated_reconcile_mismatch_block_count": 5,
        },
        "futures_auto_cancel": {
            "enabled": True,
            "heartbeat_sec": 30,
            "countdown_ms": 120000,
        },
        "margin": {
            "require_margin_level_visible": True,
            "warn_margin_level_below": 1.50,
            "block_margin_level_below": 1.25,
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

DEFAULT_EXECUTION_ROUTER_POLICY: dict[str, Any] = {
    "execution_router": {
        "families_enabled": {
            "spot": True,
            "margin": True,
            "usdm_futures": True,
            "coinm_futures": True,
        },
        "first_iteration_supported_order_types": {
            "spot": ["MARKET", "LIMIT"],
            "margin": ["MARKET", "LIMIT"],
            "usdm_futures": ["MARKET", "LIMIT"],
            "coinm_futures": ["MARKET", "LIMIT"],
        },
        "time_in_force_allowed": {
            "spot": ["GTC", "IOC", "FOK"],
            "margin": ["GTC", "IOC", "FOK"],
            "usdm_futures": ["GTC", "IOC", "FOK", "GTX"],
            "coinm_futures": ["GTC", "IOC", "FOK", "GTX"],
        },
        "prefer_cancel_replace_spot": True,
        "enable_batch_orders_usdm": False,
        "enable_batch_orders_coinm": False,
        "conditional_orders_phase1": False,
    }
}

DEFAULT_ENDPOINTS: dict[tuple[str, str], dict[str, str]] = {
    ("spot", "live"): {
        "base_url": "https://api.binance.com",
        "order": "/api/v3/order",
        "open_orders": "/api/v3/openOrders",
        "cancel_replace": "/api/v3/order/cancelReplace",
        "order_test": "/api/v3/order/test",
        "user_trades": "/api/v3/myTrades",
        "book_ticker": "/api/v3/ticker/bookTicker",
    },
    ("spot", "testnet"): {
        "base_url": "https://testnet.binance.vision",
        "order": "/api/v3/order",
        "open_orders": "/api/v3/openOrders",
        "cancel_replace": "/api/v3/order/cancelReplace",
        "order_test": "/api/v3/order/test",
        "user_trades": "/api/v3/myTrades",
        "book_ticker": "/api/v3/ticker/bookTicker",
    },
    ("margin", "live"): {
        "base_url": "https://api.binance.com",
        "order": "/sapi/v1/margin/order",
        "open_orders": "/sapi/v1/margin/openOrders",
        "cancel_all": "/sapi/v1/margin/openOrders",
        "user_trades": "/sapi/v1/margin/myTrades",
        "book_ticker": "/api/v3/ticker/bookTicker",
        "order_test": "/api/v3/order/test",
        "interest": "/sapi/v1/margin/interestHistory",
    },
    ("usdm_futures", "live"): {
        "base_url": "https://fapi.binance.com",
        "order": "/fapi/v1/order",
        "open_orders": "/fapi/v1/openOrders",
        "cancel_all": "/fapi/v1/allOpenOrders",
        "user_trades": "/fapi/v1/userTrades",
        "book_ticker": "/fapi/v1/ticker/bookTicker",
        "commission_rate": "/fapi/v1/commissionRate",
        "income": "/fapi/v1/income",
        "auto_cancel": "/fapi/v1/countdownCancelAll",
    },
    ("usdm_futures", "testnet"): {
        "base_url": "https://demo-fapi.binance.com",
        "order": "/fapi/v1/order",
        "open_orders": "/fapi/v1/openOrders",
        "cancel_all": "/fapi/v1/allOpenOrders",
        "user_trades": "/fapi/v1/userTrades",
        "book_ticker": "/fapi/v1/ticker/bookTicker",
        "commission_rate": "/fapi/v1/commissionRate",
        "income": "/fapi/v1/income",
        "auto_cancel": "/fapi/v1/countdownCancelAll",
    },
    ("coinm_futures", "live"): {
        "base_url": "https://dapi.binance.com",
        "order": "/dapi/v1/order",
        "open_orders": "/dapi/v1/openOrders",
        "cancel_all": "/dapi/v1/allOpenOrders",
        "user_trades": "/dapi/v1/userTrades",
        "book_ticker": "/dapi/v1/ticker/bookTicker",
        "commission_rate": "/dapi/v1/commissionRate",
        "income": "/dapi/v1/income",
        "auto_cancel": "/dapi/v1/countdownCancelAll",
    },
    ("coinm_futures", "testnet"): {
        "base_url": "https://testnet.binancefuture.com",
        "order": "/dapi/v1/order",
        "open_orders": "/dapi/v1/openOrders",
        "cancel_all": "/dapi/v1/allOpenOrders",
        "user_trades": "/dapi/v1/userTrades",
        "book_ticker": "/dapi/v1/ticker/bookTicker",
        "commission_rate": "/dapi/v1/commissionRate",
        "income": "/dapi/v1/income",
        "auto_cancel": "/dapi/v1/countdownCancelAll",
    },
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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _round_money(value: Any) -> float:
    return round(_safe_float(value, 0.0), 8)


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value in {None, ""}:
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def _canonical_symbol(value: Any) -> str:
    return str(value or "").replace("/", "").replace("-", "").strip().upper()


def _normalize_family(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in FAMILIES else ""


def _normalize_environment(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in ENVIRONMENTS else "live"


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


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()


def _decimal_floor(value: Any, step: Any) -> float:
    numeric = Decimal(str(_safe_float(value, 0.0)))
    step_dec = Decimal(str(_safe_float(step, 0.0)))
    if step_dec <= 0:
        return float(numeric)
    units = (numeric / step_dec).to_integral_value(rounding=ROUND_DOWN)
    return float(units * step_dec)


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


@lru_cache(maxsize=8)
def _load_policy_bundle_cached(
    repo_root_str: str,
    explicit_root_str: str,
    filename: str,
    defaults_json: str,
) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    expected_files = POLICY_EXPECTED_FILES
    selected_root = resolve_policy_root(repo_root, explicit=explicit_root, expected_files=expected_files).resolve()
    path = (selected_root / filename).resolve()
    defaults = json.loads(defaults_json)
    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    if path.exists():
        try:
            raw_text = path.read_text(encoding="utf-8")
            source_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            raw = yaml.safe_load(raw_text) or {}
            if isinstance(raw, dict):
                payload = raw
                valid = bool(raw)
        except Exception:
            payload = {}
            valid = False
    merged = _deep_merge(defaults, payload)
    if not source_hash:
        source_hash = _sha256_json(merged)
    return {
        "source_root": str(selected_root),
        "path": str(path),
        "exists": path.exists(),
        "valid": valid,
        "source_hash": source_hash,
        "source": f"config/policies/{filename}" if valid else "default_fail_closed",
        "payload": merged,
    }


def _load_policy_bundle(
    filename: str,
    defaults: dict[str, Any],
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(
        _load_policy_bundle_cached(
            str(resolved_repo_root),
            explicit_root_str,
            filename,
            _json_dumps(defaults),
        )
    )


def load_execution_safety_bundle(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    return _load_policy_bundle(
        EXECUTION_SAFETY_FILENAME,
        DEFAULT_EXECUTION_SAFETY_POLICY,
        repo_root,
        explicit_root=explicit_root,
    )


def load_execution_router_bundle(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    return _load_policy_bundle(
        EXECUTION_ROUTER_FILENAME,
        DEFAULT_EXECUTION_ROUTER_POLICY,
        repo_root,
        explicit_root=explicit_root,
    )


def execution_safety_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_execution_safety_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("payload")
    return copy.deepcopy(payload if isinstance(payload, dict) else DEFAULT_EXECUTION_SAFETY_POLICY)


def execution_router_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_execution_router_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("payload")
    return copy.deepcopy(payload if isinstance(payload, dict) else DEFAULT_EXECUTION_ROUTER_POLICY)


@dataclass(slots=True)
class PreflightResult:
    allowed: bool
    warnings: list[str]
    blocking_reasons: list[str]
    normalized_order_preview: dict[str, Any]
    estimated_costs: dict[str, Any]
    policy_source: dict[str, Any]
    snapshot_source: dict[str, Any]
    capability_source: dict[str, Any]
    fail_closed: bool


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
                CREATE INDEX IF NOT EXISTS idx_execution_intents_family_symbol ON execution_intents(family, environment, symbol, created_at DESC);

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
                CREATE INDEX IF NOT EXISTS idx_execution_reconcile_open ON execution_reconcile_events(resolved, severity, created_at DESC);

                CREATE TABLE IF NOT EXISTS kill_switch_events (
                  kill_switch_event_id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  trigger_type TEXT NOT NULL,
                  severity TEXT NOT NULL,
                  family TEXT,
                  symbol TEXT,
                  reason TEXT NOT NULL,
                  auto_actions_json TEXT NOT NULL DEFAULT '{}',
                  cleared_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_kill_switch_events_open ON kill_switch_events(cleared_at, created_at DESC);
                """
            )
            conn.commit()

    def upsert_intent(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "execution_intent_id": str(row.get("execution_intent_id") or ""),
            "created_at": str(row.get("created_at") or utc_now_iso()),
            "submitted_at": str(row.get("submitted_at") or "") or None,
            "venue": str(row.get("venue") or VENUE_BINANCE),
            "family": str(row.get("family") or "spot"),
            "environment": str(row.get("environment") or "live"),
            "mode": str(row.get("mode") or "paper"),
            "strategy_id": str(row.get("strategy_id") or "") or None,
            "bot_id": str(row.get("bot_id") or "") or None,
            "signal_id": str(row.get("signal_id") or "") or None,
            "symbol": _canonical_symbol(row.get("symbol")),
            "side": str(row.get("side") or "").upper(),
            "order_type": str(row.get("order_type") or "").upper(),
            "time_in_force": str(row.get("time_in_force") or "") or None,
            "quantity": None if row.get("quantity") is None else _safe_float(row.get("quantity"), 0.0),
            "quote_quantity": None if row.get("quote_quantity") is None else _safe_float(row.get("quote_quantity"), 0.0),
            "limit_price": None if row.get("limit_price") is None else _safe_float(row.get("limit_price"), 0.0),
            "stop_price": None if row.get("stop_price") is None else _safe_float(row.get("stop_price"), 0.0),
            "reduce_only": None if row.get("reduce_only") is None else (1 if _bool(row.get("reduce_only")) else 0),
            "client_order_id": str(row.get("client_order_id") or ""),
            "requested_notional": _safe_float(row.get("requested_notional"), 0.0),
            "estimated_fee": _safe_float(row.get("estimated_fee"), 0.0),
            "estimated_slippage_bps": _safe_float(row.get("estimated_slippage_bps"), 0.0),
            "estimated_total_cost": _safe_float(row.get("estimated_total_cost"), 0.0),
            "preflight_status": str(row.get("preflight_status") or "UNKNOWN"),
            "preflight_errors_json": _json_dumps(row.get("preflight_errors") or []),
            "policy_hash": str(row.get("policy_hash") or ""),
            "snapshot_id": str(row.get("snapshot_id") or "") or None,
            "capability_snapshot_id": str(row.get("capability_snapshot_id") or "") or None,
            "raw_request_json": _json_dumps(row.get("raw_request") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_intents (
                  execution_intent_id, created_at, submitted_at, venue, family, environment, mode,
                  strategy_id, bot_id, signal_id, symbol, side, order_type, time_in_force,
                  quantity, quote_quantity, limit_price, stop_price, reduce_only, client_order_id,
                  requested_notional, estimated_fee, estimated_slippage_bps, estimated_total_cost,
                  preflight_status, preflight_errors_json, policy_hash, snapshot_id,
                  capability_snapshot_id, raw_request_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload.values()),
            )
            conn.commit()
        return self.intent(payload["execution_intent_id"]) or payload

    def upsert_order(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "execution_order_id": str(row.get("execution_order_id") or ""),
            "execution_intent_id": str(row.get("execution_intent_id") or ""),
            "venue_order_id": str(row.get("venue_order_id") or "") or None,
            "client_order_id": str(row.get("client_order_id") or ""),
            "symbol": _canonical_symbol(row.get("symbol")),
            "family": str(row.get("family") or "spot"),
            "environment": str(row.get("environment") or "live"),
            "order_status": str(row.get("order_status") or "NEW").upper(),
            "execution_type_last": str(row.get("execution_type_last") or "") or None,
            "submitted_at": str(row.get("submitted_at") or utc_now_iso()),
            "acknowledged_at": str(row.get("acknowledged_at") or "") or None,
            "canceled_at": str(row.get("canceled_at") or "") or None,
            "expired_at": str(row.get("expired_at") or "") or None,
            "reduce_only": None if row.get("reduce_only") is None else (1 if _bool(row.get("reduce_only")) else 0),
            "tif": str(row.get("tif") or "") or None,
            "price": None if row.get("price") is None else _safe_float(row.get("price"), 0.0),
            "orig_qty": None if row.get("orig_qty") is None else _safe_float(row.get("orig_qty"), 0.0),
            "executed_qty": None if row.get("executed_qty") is None else _safe_float(row.get("executed_qty"), 0.0),
            "cum_quote_qty": None if row.get("cum_quote_qty") is None else _safe_float(row.get("cum_quote_qty"), 0.0),
            "avg_fill_price": None if row.get("avg_fill_price") is None else _safe_float(row.get("avg_fill_price"), 0.0),
            "reject_code": str(row.get("reject_code") or "") or None,
            "reject_reason": str(row.get("reject_reason") or "") or None,
            "raw_ack_json": _json_dumps(row.get("raw_ack") or {}),
            "raw_last_status_json": _json_dumps(row.get("raw_last_status") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_orders (
                  execution_order_id, execution_intent_id, venue_order_id, client_order_id, symbol, family,
                  environment, order_status, execution_type_last, submitted_at, acknowledged_at, canceled_at,
                  expired_at, reduce_only, tif, price, orig_qty, executed_qty, cum_quote_qty, avg_fill_price,
                  reject_code, reject_reason, raw_ack_json, raw_last_status_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload.values()),
            )
            conn.commit()
        return self.order(payload["execution_order_id"]) or payload

    def insert_fill(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "execution_fill_id": str(row.get("execution_fill_id") or ""),
            "execution_order_id": str(row.get("execution_order_id") or ""),
            "venue_trade_id": str(row.get("venue_trade_id") or "") or None,
            "fill_time": str(row.get("fill_time") or utc_now_iso()),
            "symbol": _canonical_symbol(row.get("symbol")),
            "family": str(row.get("family") or "spot"),
            "price": _safe_float(row.get("price"), 0.0),
            "qty": _safe_float(row.get("qty"), 0.0),
            "quote_qty": None if row.get("quote_qty") is None else _safe_float(row.get("quote_qty"), 0.0),
            "commission": _safe_float(row.get("commission"), 0.0),
            "commission_asset": str(row.get("commission_asset") or "") or None,
            "realized_pnl": None if row.get("realized_pnl") is None else _safe_float(row.get("realized_pnl"), 0.0),
            "maker": None if row.get("maker") is None else (1 if _bool(row.get("maker")) else 0),
            "funding_component": None if row.get("funding_component") is None else _safe_float(row.get("funding_component"), 0.0),
            "borrow_interest_component": None if row.get("borrow_interest_component") is None else _safe_float(row.get("borrow_interest_component"), 0.0),
            "raw_fill_json": _json_dumps(row.get("raw_fill") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO execution_fills (
                  execution_fill_id, execution_order_id, venue_trade_id, fill_time, symbol, family, price,
                  qty, quote_qty, commission, commission_asset, realized_pnl, maker, funding_component,
                  borrow_interest_component, raw_fill_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload.values()),
            )
            conn.commit()
        return self.fill(payload["execution_fill_id"]) or payload

    def insert_reconcile_event(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "reconcile_event_id": str(row.get("reconcile_event_id") or ""),
            "created_at": str(row.get("created_at") or utc_now_iso()),
            "family": str(row.get("family") or "spot"),
            "environment": str(row.get("environment") or "live"),
            "reconcile_type": str(row.get("reconcile_type") or "status_mismatch"),
            "severity": str(row.get("severity") or "WARN"),
            "execution_order_id": str(row.get("execution_order_id") or "") or None,
            "client_order_id": str(row.get("client_order_id") or "") or None,
            "details_json": _json_dumps(row.get("details") or {}),
            "resolved": 1 if _bool(row.get("resolved")) else 0,
            "resolved_at": str(row.get("resolved_at") or "") or None,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO execution_reconcile_events (
                  reconcile_event_id, created_at, family, environment, reconcile_type, severity,
                  execution_order_id, client_order_id, details_json, resolved, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload.values()),
            )
            conn.commit()
        return self.reconcile_event(payload["reconcile_event_id"]) or payload

    def trip_kill_switch(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "kill_switch_event_id": str(row.get("kill_switch_event_id") or ""),
            "created_at": str(row.get("created_at") or utc_now_iso()),
            "trigger_type": str(row.get("trigger_type") or "manual_trip"),
            "severity": str(row.get("severity") or "BLOCK"),
            "family": str(row.get("family") or "") or None,
            "symbol": _canonical_symbol(row.get("symbol")) or None,
            "reason": str(row.get("reason") or "kill_switch"),
            "auto_actions_json": _json_dumps(row.get("auto_actions") or {}),
            "cleared_at": str(row.get("cleared_at") or "") or None,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO kill_switch_events (
                  kill_switch_event_id, created_at, trigger_type, severity, family, symbol, reason, auto_actions_json, cleared_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload.values()),
            )
            conn.commit()
        return self.kill_switch_status()

    def clear_kill_switch(self) -> dict[str, Any]:
        cleared_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute("UPDATE kill_switch_events SET cleared_at = ? WHERE cleared_at IS NULL", (cleared_at,))
            conn.commit()
        return self.kill_switch_status()

    def intent(self, execution_intent_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_intents WHERE execution_intent_id = ?", (execution_intent_id,)).fetchone()
        return self._intent_row(row)

    def order(self, execution_order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_orders WHERE execution_order_id = ?", (execution_order_id,)).fetchone()
        return self._order_row(row)

    def fill(self, execution_fill_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_fills WHERE execution_fill_id = ?", (execution_fill_id,)).fetchone()
        return self._fill_row(row)

    def reconcile_event(self, reconcile_event_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_reconcile_events WHERE reconcile_event_id = ?", (reconcile_event_id,)).fetchone()
        return self._reconcile_row(row)

    def fills_for_order(self, execution_order_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_fills WHERE execution_order_id = ? ORDER BY fill_time ASC, execution_fill_id ASC",
                (execution_order_id,),
            ).fetchall()
        return [self._fill_row(row) for row in rows if row is not None]

    def reconcile_events_for_order(self, execution_order_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM execution_reconcile_events
                WHERE execution_order_id = ?
                ORDER BY created_at DESC, reconcile_event_id DESC
                """,
                (execution_order_id,),
            ).fetchall()
        return [self._reconcile_row(row) for row in rows if row is not None]

    def list_orders(
        self,
        *,
        family: str | None = None,
        environment: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
        strategy_id: str | None = None,
        bot_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["1=1"]
        params: list[Any] = []
        if family:
            clauses.append("o.family = ?")
            params.append(str(family))
        if environment:
            clauses.append("o.environment = ?")
            params.append(str(environment))
        if symbol:
            clauses.append("o.symbol = ?")
            params.append(_canonical_symbol(symbol))
        if status:
            clauses.append("o.order_status = ?")
            params.append(str(status).upper())
        if strategy_id:
            clauses.append("i.strategy_id = ?")
            params.append(str(strategy_id))
        if bot_id:
            clauses.append("i.bot_id = ?")
            params.append(str(bot_id))
        query = f"""
            SELECT o.*, i.mode, i.strategy_id, i.bot_id, i.signal_id
            FROM execution_orders o
            LEFT JOIN execution_intents i ON i.execution_intent_id = o.execution_intent_id
            WHERE {' AND '.join(clauses)}
            ORDER BY o.submitted_at DESC, o.execution_order_id DESC
            LIMIT ? OFFSET ?
        """
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._order_row(row) for row in rows if row is not None]

    def open_orders(self, *, family: str | None = None, symbol: str | None = None) -> list[dict[str, Any]]:
        clauses = ["order_status IN ('NEW', 'PARTIALLY_FILLED', 'PENDING_CANCEL')"]
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
                SELECT * FROM execution_orders
                WHERE {' AND '.join(clauses)}
                ORDER BY submitted_at DESC, execution_order_id DESC
                """,
                tuple(params),
            ).fetchall()
        return [self._order_row(row) for row in rows if row is not None]

    def unresolved_reconcile_events(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM execution_reconcile_events
                WHERE resolved = 0
                ORDER BY created_at DESC, reconcile_event_id DESC
                """
            ).fetchall()
        return [self._reconcile_row(row) for row in rows if row is not None]

    def recent_rejects(self, *, since_seconds: int = 300) -> list[dict[str, Any]]:
        cutoff = (_utc_now() - timedelta(seconds=max(1, int(since_seconds)))).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM execution_orders
                WHERE submitted_at >= ?
                  AND order_status = 'REJECTED'
                ORDER BY submitted_at DESC
                """,
                (cutoff,),
            ).fetchall()
        return [self._order_row(row) for row in rows if row is not None]

    def recent_failed_submit_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM execution_orders
                WHERE order_status = 'REJECTED'
                ORDER BY submitted_at DESC
                """
            ).fetchone()
        return int((row["count"] if row is not None else 0) or 0)

    def kill_switch_status(self) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM kill_switch_events
                ORDER BY CASE WHEN cleared_at IS NULL THEN 0 ELSE 1 END, created_at DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return {
                "armed": False,
                "active_event": None,
                "history_count": 0,
            }
        active = row["cleared_at"] is None
        count = 0
        with self._connect() as conn:
            count_row = conn.execute("SELECT COUNT(*) AS count FROM kill_switch_events").fetchone()
            count = int((count_row["count"] if count_row is not None else 0) or 0)
        return {
            "armed": active,
            "active_event": self._kill_row(row),
            "history_count": count,
        }

    @staticmethod
    def _intent_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "execution_intent_id": str(row["execution_intent_id"]),
            "created_at": str(row["created_at"]),
            "submitted_at": str(row["submitted_at"] or "") or None,
            "venue": str(row["venue"]),
            "family": str(row["family"]),
            "environment": str(row["environment"]),
            "mode": str(row["mode"]),
            "strategy_id": str(row["strategy_id"] or "") or None,
            "bot_id": str(row["bot_id"] or "") or None,
            "signal_id": str(row["signal_id"] or "") or None,
            "symbol": str(row["symbol"]),
            "side": str(row["side"]),
            "order_type": str(row["order_type"]),
            "time_in_force": str(row["time_in_force"] or "") or None,
            "quantity": None if row["quantity"] is None else float(row["quantity"]),
            "quote_quantity": None if row["quote_quantity"] is None else float(row["quote_quantity"]),
            "limit_price": None if row["limit_price"] is None else float(row["limit_price"]),
            "stop_price": None if row["stop_price"] is None else float(row["stop_price"]),
            "reduce_only": None if row["reduce_only"] is None else _bool(row["reduce_only"]),
            "client_order_id": str(row["client_order_id"]),
            "requested_notional": float(row["requested_notional"] or 0.0),
            "estimated_fee": float(row["estimated_fee"] or 0.0),
            "estimated_slippage_bps": float(row["estimated_slippage_bps"] or 0.0),
            "estimated_total_cost": float(row["estimated_total_cost"] or 0.0),
            "preflight_status": str(row["preflight_status"]),
            "preflight_errors": _json_loads(row["preflight_errors_json"], []),
            "policy_hash": str(row["policy_hash"]),
            "snapshot_id": str(row["snapshot_id"] or "") or None,
            "capability_snapshot_id": str(row["capability_snapshot_id"] or "") or None,
            "raw_request": _json_loads(row["raw_request_json"], {}),
        }

    @staticmethod
    def _order_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = {
            "execution_order_id": str(row["execution_order_id"]),
            "execution_intent_id": str(row["execution_intent_id"]),
            "venue_order_id": str(row["venue_order_id"] or "") or None,
            "client_order_id": str(row["client_order_id"]),
            "symbol": str(row["symbol"]),
            "family": str(row["family"]),
            "environment": str(row["environment"]),
            "order_status": str(row["order_status"]),
            "execution_type_last": str(row["execution_type_last"] or "") or None,
            "submitted_at": str(row["submitted_at"]),
            "acknowledged_at": str(row["acknowledged_at"] or "") or None,
            "canceled_at": str(row["canceled_at"] or "") or None,
            "expired_at": str(row["expired_at"] or "") or None,
            "reduce_only": None if row["reduce_only"] is None else _bool(row["reduce_only"]),
            "tif": str(row["tif"] or "") or None,
            "price": None if row["price"] is None else float(row["price"]),
            "orig_qty": None if row["orig_qty"] is None else float(row["orig_qty"]),
            "executed_qty": None if row["executed_qty"] is None else float(row["executed_qty"]),
            "cum_quote_qty": None if row["cum_quote_qty"] is None else float(row["cum_quote_qty"]),
            "avg_fill_price": None if row["avg_fill_price"] is None else float(row["avg_fill_price"]),
            "reject_code": str(row["reject_code"] or "") or None,
            "reject_reason": str(row["reject_reason"] or "") or None,
            "raw_ack": _json_loads(row["raw_ack_json"], {}),
            "raw_last_status": _json_loads(row["raw_last_status_json"], {}),
        }
        if "mode" in row.keys():
            payload["mode"] = str(row["mode"] or "") or None
        if "strategy_id" in row.keys():
            payload["strategy_id"] = str(row["strategy_id"] or "") or None
        if "bot_id" in row.keys():
            payload["bot_id"] = str(row["bot_id"] or "") or None
        if "signal_id" in row.keys():
            payload["signal_id"] = str(row["signal_id"] or "") or None
        return payload

    @staticmethod
    def _fill_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "execution_fill_id": str(row["execution_fill_id"]),
            "execution_order_id": str(row["execution_order_id"]),
            "venue_trade_id": str(row["venue_trade_id"] or "") or None,
            "fill_time": str(row["fill_time"]),
            "symbol": str(row["symbol"]),
            "family": str(row["family"]),
            "price": float(row["price"] or 0.0),
            "qty": float(row["qty"] or 0.0),
            "quote_qty": None if row["quote_qty"] is None else float(row["quote_qty"]),
            "commission": float(row["commission"] or 0.0),
            "commission_asset": str(row["commission_asset"] or "") or None,
            "realized_pnl": None if row["realized_pnl"] is None else float(row["realized_pnl"]),
            "maker": None if row["maker"] is None else _bool(row["maker"]),
            "funding_component": None if row["funding_component"] is None else float(row["funding_component"]),
            "borrow_interest_component": None if row["borrow_interest_component"] is None else float(row["borrow_interest_component"]),
            "raw_fill": _json_loads(row["raw_fill_json"], {}),
        }

    @staticmethod
    def _reconcile_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "reconcile_event_id": str(row["reconcile_event_id"]),
            "created_at": str(row["created_at"]),
            "family": str(row["family"]),
            "environment": str(row["environment"]),
            "reconcile_type": str(row["reconcile_type"]),
            "severity": str(row["severity"]),
            "execution_order_id": str(row["execution_order_id"] or "") or None,
            "client_order_id": str(row["client_order_id"] or "") or None,
            "details": _json_loads(row["details_json"], {}),
            "resolved": _bool(row["resolved"]),
            "resolved_at": str(row["resolved_at"] or "") or None,
        }

    @staticmethod
    def _kill_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "kill_switch_event_id": str(row["kill_switch_event_id"]),
            "created_at": str(row["created_at"]),
            "trigger_type": str(row["trigger_type"]),
            "severity": str(row["severity"]),
            "family": str(row["family"] or "") or None,
            "symbol": str(row["symbol"] or "") or None,
            "reason": str(row["reason"]),
            "auto_actions": _json_loads(row["auto_actions_json"], {}),
            "cleared_at": str(row["cleared_at"] or "") or None,
        }


def _credentials_for_family(family: str, environment: str) -> tuple[str, str, list[str]]:
    mapping: dict[tuple[str, str], list[tuple[str, str]]] = {
        ("spot", "live"): [("BINANCE_API_KEY", "BINANCE_API_SECRET")],
        ("spot", "testnet"): [("BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET")],
        ("margin", "live"): [("BINANCE_API_KEY", "BINANCE_API_SECRET")],
        ("margin", "testnet"): [],
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
    tried: list[str] = []
    for key_name, secret_name in mapping.get((family, environment), []):
        tried.extend([key_name, secret_name])
        key = str(os.getenv(key_name, "")).strip()
        secret = str(os.getenv(secret_name, "")).strip()
        if key and secret:
            return key, secret, tried
    return "", "", tried


def _env_base_override(family: str, environment: str) -> str:
    key_map = {
        ("spot", "live"): "BINANCE_SPOT_BASE_URL",
        ("spot", "testnet"): "BINANCE_SPOT_TESTNET_BASE_URL",
        ("margin", "live"): "BINANCE_SPOT_BASE_URL",
        ("usdm_futures", "live"): "BINANCE_USDM_BASE_URL",
        ("usdm_futures", "testnet"): "BINANCE_USDM_TESTNET_BASE_URL",
        ("coinm_futures", "live"): "BINANCE_COINM_BASE_URL",
        ("coinm_futures", "testnet"): "BINANCE_COINM_TESTNET_BASE_URL",
    }
    return str(os.getenv(key_map.get((family, environment), ""), "")).strip()


def _build_endpoint(family: str, environment: str, key: str) -> str:
    descriptor = copy.deepcopy(DEFAULT_ENDPOINTS.get((family, environment), {}))
    base_url = _env_base_override(family, environment) or str(descriptor.get("base_url") or "")
    path = str(descriptor.get(key) or "")
    return f"{base_url.rstrip('/')}{path}" if base_url and path else ""


class ExecutionRealityService:
    def __init__(
        self,
        *,
        user_data_dir: Path,
        repo_root: Path,
        instrument_registry_service: Any,
        universe_service: Any,
        reporting_bridge_service: Any,
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

    def policy_source(self) -> dict[str, Any]:
        safety_bundle = self.safety_bundle()
        router_bundle = self.router_bundle()
        return {
            "execution_safety": {
                "path": safety_bundle.get("path"),
                "hash": safety_bundle.get("source_hash"),
                "source": safety_bundle.get("source"),
                "valid": bool(safety_bundle.get("valid")),
            },
            "execution_router": {
                "path": router_bundle.get("path"),
                "hash": router_bundle.get("source_hash"),
                "source": router_bundle.get("source"),
                "valid": bool(router_bundle.get("valid")),
            },
        }

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
            "bid": None if bid is None else _safe_float(bid, 0.0),
            "ask": None if ask is None else _safe_float(ask, 0.0),
            "quote_ts_ms": int(quote_ts_ms) if quote_ts_ms is not None else int(time.time() * 1000),
            "orderbook_ts_ms": int(orderbook_ts_ms) if orderbook_ts_ms is not None else int(time.time() * 1000),
            "source": str(source or "manual"),
            "updated_at": utc_now_iso(),
        }
        self._quotes[(_normalize_family(family), _normalize_environment(environment), _canonical_symbol(symbol))] = payload
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

    def set_margin_level(self, *, environment: str, level: float | None, source: str = "manual") -> dict[str, Any]:
        payload = {
            "level": None if level is None else _safe_float(level, 0.0),
            "source": str(source or "manual"),
            "updated_at": utc_now_iso(),
        }
        self._margin_levels[_normalize_environment(environment)] = payload
        return payload

    def _runs(self) -> list[dict[str, Any]]:
        if callable(self.runs_loader):
            data = self.runs_loader()
            return data if isinstance(data, list) else []
        return self.reporting_bridge_service.load_runs()

    def _policy_hash(self) -> str:
        source = self.policy_source()
        return _sha256_json(
            {
                "execution_safety": source["execution_safety"]["hash"],
                "execution_router": source["execution_router"]["hash"],
                "cost_stack": self.reporting_bridge_service.policy_source()["cost_stack"]["hash"],
            }
        )

    def _cost_stack_policy(self) -> dict[str, Any]:
        return self.reporting_bridge_service.cost_stack()

    def _freshness_payload(self, fetched_at: str | None) -> dict[str, Any]:
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
        return {"status": status, "age_hours": round(age_hours, 4), "warn_after_hours": warn_hours, "block_after_hours": block_hours}

    def _instrument_row(self, family: str, symbol: str) -> dict[str, Any] | None:
        target_family = _normalize_family(family)
        target_symbol = _canonical_symbol(symbol)
        base_row = None
        for row in self.instrument_registry_service.db.registry_rows(active_only=True):
            if str(row.get("family") or "") == target_family and _canonical_symbol(row.get("symbol")) == target_symbol:
                base_row = row
                break
        if base_row is None:
            return None
        snapshots = []
        latest_env = self._latest_snapshot(target_family, "live")
        if isinstance(latest_env, dict) and latest_env.get("snapshot_id"):
            snapshots.append(str(latest_env.get("snapshot_id")))
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

    def _capability_snapshot(self, family: str, environment: str) -> dict[str, Any] | None:
        return self.instrument_registry_service.db.latest_capability_snapshot(_normalize_family(family), _normalize_environment(environment))

    def _latest_snapshot(self, family: str, environment: str) -> dict[str, Any] | None:
        return self.instrument_registry_service.db.latest_snapshot(_normalize_family(family), _normalize_environment(environment), success_only=True)

    def _universe_membership(self, family: str, symbol: str) -> dict[str, Any]:
        if hasattr(self.universe_service, "membership"):
            try:
                return self.universe_service.membership(family=family, symbol=symbol)
            except Exception:
                pass
        summary = self.universe_service.summary()
        items = summary.get("items") if isinstance(summary.get("items"), list) else []
        target_symbol = _canonical_symbol(symbol)
        matches = []
        for row in items:
            if str(row.get("family") or "") != _normalize_family(family):
                continue
            symbols = row.get("symbols") if isinstance(row.get("symbols"), list) else []
            if target_symbol in {_canonical_symbol(item) for item in symbols}:
                matches.append(row)
        return {
            "matched": bool(matches),
            "universes": [str(row.get("name") or "") for row in matches],
            "snapshot_source": next((row.get("snapshot_source") for row in matches), None),
        }

    def _quote_snapshot(self, family: str, environment: str, symbol: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
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

        step_size = str((market_lot_size if order_type == "MARKET" and isinstance(market_lot_size, dict) else lot_size).get("step_size") or lot_size.get("step_size") or "0")
        tick_size = str(price_filter.get("tick_size") or "0")
        qty = _first_number(request.get("quantity"))
        quote_quantity = _first_number(request.get("quote_quantity"))
        limit_price = _first_number(request.get("price"))
        bid = _first_number(quote.get("bid"))
        ask = _first_number(quote.get("ask"))
        expected_price = limit_price
        if expected_price is None:
            if side == "BUY":
                expected_price = ask or bid
            else:
                expected_price = bid or ask
        normalized_qty = None if qty is None else _decimal_floor(qty, step_size)
        normalized_price = None if limit_price is None else _decimal_floor(limit_price, tick_size)
        if order_type == "LIMIT" and normalized_price is None and expected_price is not None:
            normalized_price = _decimal_floor(expected_price, tick_size)
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
        rows = self.reporting_bridge_service.db.cost_source_snapshots()
        matches = [
            row
            for row in rows
            if str(row.get("family") or "") == _normalize_family(family)
            and str(row.get("environment") or "") == _normalize_environment(environment)
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
        if family and not _bool((self.router_policy().get("families_enabled") or {}).get(family, False)):
            blocking.append(f"family_disabled:{family}")

        instrument = self._instrument_row(family, symbol) if family and symbol else None
        if instrument is None:
            if _bool((self.safety_policy().get("preflight") or {}).get("require_instrument_registry_match", True)):
                blocking.append("instrument_not_in_registry")
        capability = self._capability_snapshot(family, environment) if family else None
        latest_snapshot = self._latest_snapshot(family, environment) if family else None
        quote = self._quote_snapshot(family, environment, symbol, request.get("market_snapshot") if isinstance(request.get("market_snapshot"), dict) else None)

        if instrument is None:
            preview = {"symbol": symbol, "side": str(request.get("side") or "").upper(), "order_type": str(request.get("order_type") or "").upper(), "quantity": request.get("quantity"), "quote_quantity": request.get("quote_quantity"), "limit_price": request.get("price"), "preview_price": request.get("price"), "requested_notional": _safe_float(request.get("requested_notional"), 0.0), "reduce_only": request.get("reduce_only"), "time_in_force": request.get("time_in_force")}
            costs = self._estimated_costs(family=family or "spot", request=request, preview=preview, instrument={})
        else:
            preview = self._normalize_order(instrument, request, quote)
            costs = self._estimated_costs(family=family, request=request, preview=preview, instrument=instrument)

        preflight_cfg = self.safety_policy().get("preflight") if isinstance(self.safety_policy().get("preflight"), dict) else {}
        sizing_cfg = self.safety_policy().get("sizing") if isinstance(self.safety_policy().get("sizing"), dict) else {}
        margin_cfg = self.safety_policy().get("margin") if isinstance(self.safety_policy().get("margin"), dict) else {}
        cost_policy = self._cost_stack_policy()
        estimation_cfg = cost_policy.get("estimation") if isinstance(cost_policy.get("estimation"), dict) else {}

        if _bool(preflight_cfg.get("require_policy_loaded", True)):
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
            if environment == "live" and _bool(preflight_cfg.get("require_live_eligible", True)) and not _bool(instrument.get("live_eligible")):
                blocking.append("instrument_not_live_eligible")
            if environment == "testnet" and not _bool(instrument.get("testnet_eligible")):
                blocking.append("instrument_not_testnet_eligible")
            if _bool(preflight_cfg.get("reject_if_missing_basic_filters", True)):
                filters = instrument.get("filter_summary") if isinstance(instrument.get("filter_summary"), dict) else {}
                if not isinstance(filters.get("price_filter"), dict) or not isinstance(filters.get("lot_size"), dict):
                    blocking.append("missing_basic_filters")

            price_filter = preview.get("price_filter") if isinstance(preview.get("price_filter"), dict) else {}
            lot_size = preview.get("lot_size") if isinstance(preview.get("lot_size"), dict) else {}
            notional = instrument.get("filter_summary") if isinstance(instrument.get("filter_summary"), dict) else {}
            min_qty = _first_number((lot_size or {}).get("min_qty"))
            max_qty = _first_number((lot_size or {}).get("max_qty"))
            qty = _first_number(preview.get("quantity"))
            if qty is not None and min_qty is not None and qty < min_qty:
                blocking.append("quantity_below_min_qty")
            if qty is not None and max_qty is not None and qty > max_qty:
                blocking.append("quantity_above_max_qty")
            limit_price = _first_number(preview.get("limit_price"))
            if preview.get("order_type") == "LIMIT" and limit_price is None:
                blocking.append("limit_price_required")
            if limit_price is not None:
                min_price = _first_number((price_filter or {}).get("min_price"))
                max_price = _first_number((price_filter or {}).get("max_price"))
                if min_price is not None and limit_price < min_price:
                    blocking.append("price_below_min_price")
                if max_price is not None and max_price > 0 and limit_price > max_price:
                    blocking.append("price_above_max_price")

            notional_filters = notional.get("notional") if isinstance(notional.get("notional"), dict) else {}
            min_notional = _first_number(
                (notional_filters or {}).get("min_notional"),
                ((notional.get("min_notional") if isinstance(notional.get("min_notional"), dict) else {}) or {}).get("min_notional"),
            )
            buffer_pct = _safe_float(sizing_cfg.get("min_notional_buffer_pct_above_exchange_min"), 5.0)
            min_required = 0.0 if min_notional is None else min_notional * (1.0 + buffer_pct / 100.0)
            if _safe_float(preview.get("requested_notional"), 0.0) < min_required:
                blocking.append("notional_below_exchange_min_with_buffer")

        max_notional = _safe_float(sizing_cfg.get("max_notional_per_order_usd"), 5000.0)
        if _safe_float(preview.get("requested_notional"), 0.0) > max_notional:
            blocking.append("max_notional_per_order_exceeded")

        open_symbol = len(self.db.open_orders(family=family, symbol=symbol))
        open_total = len(self.db.open_orders())
        if open_symbol >= int(sizing_cfg.get("max_open_orders_per_symbol", 6) or 6):
            blocking.append("max_open_orders_per_symbol_reached")
        if open_total >= int(sizing_cfg.get("max_open_orders_total", 40) or 40):
            blocking.append("max_open_orders_total_reached")

        membership = self._universe_membership(family, symbol) if family and symbol else {"matched": False, "universes": []}
        if environment in {"live", "testnet"} and _bool(preflight_cfg.get("require_universe_membership_for_live", True)) and not _bool(membership.get("matched")):
            blocking.append("symbol_not_in_active_universe")

        if _bool(preflight_cfg.get("require_capability_snapshot", True)) and capability is None:
            blocking.append("capability_snapshot_missing")
        if capability is not None and not _bool(capability.get("can_trade")) and environment in {"live", "testnet"}:
            blocking.append("account_cannot_trade")

        if _bool(preflight_cfg.get("require_snapshot_fresh", True)):
            freshness = self._freshness_payload(latest_snapshot.get("fetched_at") if latest_snapshot else None)
            if freshness.get("status") == "block":
                blocking.append("instrument_snapshot_stale")
            elif freshness.get("status") == "warn":
                warnings.append("instrument_snapshot_near_stale")
        else:
            freshness = self._freshness_payload(latest_snapshot.get("fetched_at") if latest_snapshot else None)

        quote_ts_ms = quote.get("quote_ts_ms")
        if quote_ts_ms is None:
            blocking.append("quote_snapshot_missing")
        else:
            age_ms = max(0, int(time.time() * 1000) - int(quote_ts_ms))
            if age_ms >= int(preflight_cfg.get("quote_stale_block_ms", 3000) or 3000):
                blocking.append("quote_stale")

        orderbook_ts_ms = quote.get("orderbook_ts_ms")
        if orderbook_ts_ms is not None:
            ob_age_ms = max(0, int(time.time() * 1000) - int(orderbook_ts_ms))
            if ob_age_ms >= int(preflight_cfg.get("orderbook_stale_block_ms", 5000) or 5000):
                blocking.append("orderbook_stale")
            elif ob_age_ms >= int(preflight_cfg.get("orderbook_stale_warn_ms", 1500) or 1500):
                warnings.append("orderbook_stale_warn")

        fee_state = self._fee_source_state(family, environment) if family else {"available": False, "fresh": False, "latest": None}
        if mode == "live" and _bool(preflight_cfg.get("reject_if_missing_fee_source_in_live", True)) and not _bool(fee_state.get("available")):
            blocking.append("fee_source_missing_in_live")
            fail_closed = True
        elif mode == "live" and not _bool(fee_state.get("fresh")):
            warnings.append("fee_source_stale")

        if mode == "live" and _bool(estimation_cfg.get("block_if_missing_real_cost_source_in_live", True)) and not _bool(fee_state.get("available")):
            fail_closed = True

        margin_level = self._margin_levels.get(environment)
        if family == "margin" and _bool(margin_cfg.get("require_margin_level_visible", True)):
            if not isinstance(margin_level, dict) or margin_level.get("level") is None:
                blocking.append("margin_level_missing")
            else:
                level = _safe_float(margin_level.get("level"), 0.0)
                if level < _safe_float(margin_cfg.get("block_margin_level_below"), 1.25):
                    blocking.append("margin_level_blocked")
                elif level < _safe_float(margin_cfg.get("warn_margin_level_below"), 1.5):
                    warnings.append("margin_level_warn")

        slip_warn, slip_block = self._slippage_thresholds(family)
        slip_bps = _safe_float(costs.get("slippage_bps"), 0.0)
        if slip_bps >= slip_block:
            blocking.append("slippage_block_threshold")
        elif slip_bps >= slip_warn:
            warnings.append("slippage_warn_threshold")

        ks_status = self.db.kill_switch_status()
        if _bool((ks_status.get("active_event") or {}).get("severity") == "BLOCK") and _bool(ks_status.get("armed")):
            blocking.append("kill_switch_armed")
            fail_closed = True

        reject_limit = int((self.safety_policy().get("kill_switch") or {}).get("critical_rejects_5m_block", 8) or 8)
        if len(self.db.recent_rejects()) >= reject_limit:
            blocking.append("reject_storm_blocked")
            fail_closed = True

        mismatch_limit = int((self.safety_policy().get("kill_switch") or {}).get("repeated_reconcile_mismatch_block_count", 5) or 5)
        unresolved = [row for row in self.db.unresolved_reconcile_events() if str(row.get("severity") or "") == "BLOCK"]
        if len(unresolved) >= mismatch_limit:
            blocking.append("reconcile_mismatch_blocked")
            fail_closed = True

        result = PreflightResult(
            allowed=not blocking,
            warnings=warnings,
            blocking_reasons=blocking,
            normalized_order_preview=preview,
            estimated_costs=costs,
            policy_source=self.policy_source(),
            snapshot_source={
                "snapshot_id": (latest_snapshot or {}).get("snapshot_id"),
                "fetched_at": (latest_snapshot or {}).get("fetched_at"),
                "freshness": freshness,
                "universe_membership": membership,
            },
            capability_source={
                "capability_snapshot_id": (capability or {}).get("capability_snapshot_id"),
                "capability_source": (capability or {}).get("capability_source"),
                "can_trade": _bool((capability or {}).get("can_trade")),
            },
            fail_closed=fail_closed,
        )
        return {
            "allowed": result.allowed,
            "warnings": result.warnings,
            "blocking_reasons": result.blocking_reasons,
            "normalized_order_preview": result.normalized_order_preview,
            "estimated_costs": result.estimated_costs,
            "policy_source": result.policy_source,
            "snapshot_source": result.snapshot_source,
            "capability_source": result.capability_source,
            "fail_closed": result.fail_closed,
        }

    def _signed_request(
        self,
        *,
        family: str,
        environment: str,
        method: str,
        endpoint_key: str,
        params: dict[str, Any] | None = None,
        signed: bool = True,
    ) -> dict[str, Any]:
        endpoint_url = _build_endpoint(family, environment, endpoint_key)
        if not endpoint_url:
            raise RuntimeError(f"Endpoint no configurado para {family}/{environment}/{endpoint_key}")
        request_params = {key: value for key, value in (params or {}).items() if value not in {None, ""}}
        headers: dict[str, str] = {}
        if signed:
            api_key, api_secret, _ = _credentials_for_family(family, environment)
            if not api_key or not api_secret:
                raise RuntimeError(f"Missing credentials for {family}/{environment}")
            request_params["timestamp"] = int(time.time() * 1000)
            request_params["recvWindow"] = 5000
            query = urlencode(request_params, doseq=True)
            signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
            request_params["signature"] = signature
            headers["X-MBX-APIKEY"] = api_key
        timeout = float(
            ((self.instrument_registry_service.policy().get("sync") if isinstance(self.instrument_registry_service.policy().get("sync"), dict) else {}) or {}).get(
                "request_timeout_sec",
                12,
            )
            or 12
        )
        response = requests.request(method.upper(), endpoint_url, params=request_params, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        return {"data": payload}

    def _paper_fill(self, order: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
        preview = preflight.get("normalized_order_preview") if isinstance(preflight.get("normalized_order_preview"), dict) else {}
        quote = self._quote_snapshot(order["family"], order["environment"], order["symbol"])
        fill_price = _first_number(preview.get("preview_price"), quote.get("ask"), quote.get("bid"), order.get("price"), 0.0) or 0.0
        qty = _first_number(order.get("orig_qty"), preview.get("quantity"), 0.0) or 0.0
        quote_qty = fill_price * qty
        cost = preflight.get("estimated_costs") if isinstance(preflight.get("estimated_costs"), dict) else {}
        fill = {
            "execution_fill_id": f"XFL-{uuid4().hex[:16].upper()}",
            "execution_order_id": order["execution_order_id"],
            "venue_trade_id": f"PAPER-{uuid4().hex[:12].upper()}",
            "fill_time": utc_now_iso(),
            "symbol": order["symbol"],
            "family": order["family"],
            "price": fill_price,
            "qty": qty,
            "quote_qty": quote_qty,
            "commission": _safe_float(cost.get("exchange_fee_estimated"), 0.0),
            "commission_asset": "USDT",
            "realized_pnl": _safe_float(preflight.get("gross_pnl"), 0.0),
            "maker": order.get("order_status") == "NEW" and str(order.get("tif") or "") == "GTX",
            "funding_component": 0.0,
            "borrow_interest_component": 0.0,
            "raw_fill": {
                "simulated": True,
                "cost_classification": "estimated_only",
                "preview_price": preview.get("preview_price"),
            },
        }
        self.db.insert_fill(fill)
        avg_fill_price = 0.0 if qty <= 0 else quote_qty / qty
        self.db.upsert_order(
            {
                **order,
                "order_status": "FILLED",
                "execution_type_last": "TRADE",
                "acknowledged_at": order.get("acknowledged_at") or utc_now_iso(),
                "executed_qty": qty,
                "cum_quote_qty": quote_qty,
                "avg_fill_price": avg_fill_price,
                "raw_last_status": {"simulated": True, "fills": [fill]},
            }
        )
        return fill

    def _submit_remote_order(self, request: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
        family = _normalize_family(request.get("family"))
        environment = _normalize_environment(request.get("environment"))
        return self._signed_request(
            family=family,
            environment=environment,
            method="POST",
            endpoint_key="order",
            params={
                "symbol": _canonical_symbol(request.get("symbol")),
                "side": str(request.get("side") or "").upper(),
                "type": str(request.get("order_type") or "").upper(),
                "newClientOrderId": str(request.get("client_order_id") or ""),
                "quantity": preview.get("quantity"),
                "quoteOrderQty": preview.get("quote_quantity"),
                "timeInForce": preview.get("time_in_force"),
                "price": preview.get("limit_price"),
                "reduceOnly": "true" if _bool(preview.get("reduce_only")) else None,
                "newOrderRespType": "FULL" if family in {"spot", "margin"} else "RESULT",
            },
            signed=True,
        )

    def _cancel_remote_order(self, order: dict[str, Any]) -> dict[str, Any]:
        return self._signed_request(
            family=str(order.get("family") or ""),
            environment=str(order.get("environment") or ""),
            method="DELETE",
            endpoint_key="order",
            params={
                "symbol": str(order.get("symbol") or ""),
                "origClientOrderId": str(order.get("client_order_id") or ""),
                "orderId": str(order.get("venue_order_id") or "") or None,
            },
            signed=True,
        )

    def _arm_futures_auto_cancel(self, *, family: str, environment: str, symbol: str | None = None) -> dict[str, Any] | None:
        if family not in {"usdm_futures", "coinm_futures"}:
            return None
        cfg = self.safety_policy().get("futures_auto_cancel") if isinstance(self.safety_policy().get("futures_auto_cancel"), dict) else {}
        if not _bool(cfg.get("enabled", True)):
            return None
        return self._signed_request(
            family=family,
            environment=environment,
            method="POST",
            endpoint_key="auto_cancel",
            params={
                "symbol": _canonical_symbol(symbol) if symbol else None,
                "countdownTime": int(cfg.get("countdown_ms", 120000) or 120000),
            },
            signed=True,
        )

    def create_order(self, request: dict[str, Any]) -> dict[str, Any]:
        family = _normalize_family(request.get("family"))
        environment = _normalize_environment(request.get("environment"))
        mode = _normalize_mode(request.get("mode"), environment)
        preflight = self.preflight({**request, "family": family, "environment": environment, "mode": mode})
        client_order_id = str(request.get("client_order_id") or f"RTLAB-{uuid4().hex[:20].upper()}")
        intent_id = f"XIN-{uuid4().hex[:16].upper()}"
        intent = {
            "execution_intent_id": intent_id,
            "created_at": utc_now_iso(),
            "venue": VENUE_BINANCE,
            "family": family,
            "environment": environment,
            "mode": mode,
            "strategy_id": request.get("strategy_id"),
            "bot_id": request.get("bot_id"),
            "signal_id": request.get("signal_id"),
            "symbol": request.get("symbol"),
            "side": request.get("side"),
            "order_type": request.get("order_type"),
            "time_in_force": (preflight.get("normalized_order_preview") or {}).get("time_in_force"),
            "quantity": (preflight.get("normalized_order_preview") or {}).get("quantity"),
            "quote_quantity": (preflight.get("normalized_order_preview") or {}).get("quote_quantity"),
            "limit_price": (preflight.get("normalized_order_preview") or {}).get("limit_price"),
            "stop_price": request.get("stop_price"),
            "reduce_only": request.get("reduce_only"),
            "client_order_id": client_order_id,
            "requested_notional": (preflight.get("estimated_costs") or {}).get("requested_notional"),
            "estimated_fee": (preflight.get("estimated_costs") or {}).get("exchange_fee_estimated"),
            "estimated_slippage_bps": (preflight.get("estimated_costs") or {}).get("slippage_bps"),
            "estimated_total_cost": (preflight.get("estimated_costs") or {}).get("total_cost_estimated"),
            "preflight_status": "ALLOWED" if _bool(preflight.get("allowed")) else "BLOCKED",
            "preflight_errors": preflight.get("blocking_reasons") or [],
            "policy_hash": self._policy_hash(),
            "snapshot_id": (preflight.get("snapshot_source") or {}).get("snapshot_id"),
            "capability_snapshot_id": (preflight.get("capability_source") or {}).get("capability_snapshot_id"),
            "raw_request": request,
        }
        self.db.upsert_intent(intent)
        order_id = f"XOR-{uuid4().hex[:16].upper()}"
        preview = preflight.get("normalized_order_preview") if isinstance(preflight.get("normalized_order_preview"), dict) else {}
        base_order = {
            "execution_order_id": order_id,
            "execution_intent_id": intent_id,
            "venue_order_id": None,
            "client_order_id": client_order_id,
            "symbol": request.get("symbol"),
            "family": family,
            "environment": environment,
            "order_status": "REJECTED" if not _bool(preflight.get("allowed")) else "NEW",
            "execution_type_last": "REJECTED" if not _bool(preflight.get("allowed")) else "NEW",
            "submitted_at": utc_now_iso(),
            "acknowledged_at": None,
            "reduce_only": request.get("reduce_only"),
            "tif": preview.get("time_in_force"),
            "price": preview.get("limit_price"),
            "orig_qty": preview.get("quantity"),
            "executed_qty": 0.0,
            "cum_quote_qty": 0.0,
            "avg_fill_price": None,
            "reject_code": None if _bool(preflight.get("allowed")) else "PREFLIGHT_BLOCK",
            "reject_reason": None if _bool(preflight.get("allowed")) else ";".join(preflight.get("blocking_reasons") or []),
            "raw_ack": {},
            "raw_last_status": {},
        }
        if not _bool(preflight.get("allowed")):
            self.db.upsert_order(base_order)
            if _bool(preflight.get("fail_closed")):
                self.trip_kill_switch(
                    trigger_type="fail_closed_preflight",
                    severity="BLOCK",
                    family=family,
                    symbol=request.get("symbol"),
                    reason=";".join(preflight.get("blocking_reasons") or []),
                )
            return {
                "execution_intent_id": intent_id,
                "execution_order_id": order_id,
                "client_order_id": client_order_id,
                "order_status": "REJECTED",
                "mode": mode,
                "environment": environment,
                "family": family,
                "estimated_costs": preflight.get("estimated_costs"),
                "fail_closed": bool(preflight.get("fail_closed")),
            }

        if mode in {"paper", "shadow"}:
            order_row = self.db.upsert_order({**base_order, "acknowledged_at": utc_now_iso(), "raw_ack": {"simulated": True}})
            if str(request.get("order_type") or "").upper() == "MARKET":
                self._paper_fill(order_row, preflight)
            self.refresh_reporting_views()
            final_order = self.db.order(order_id) or order_row
            return {
                "execution_intent_id": intent_id,
                "execution_order_id": order_id,
                "client_order_id": client_order_id,
                "order_status": final_order.get("order_status"),
                "mode": mode,
                "environment": environment,
                "family": family,
                "estimated_costs": preflight.get("estimated_costs"),
                "fail_closed": False,
            }

        try:
            auto_cancel_payload = None
            if family in {"usdm_futures", "coinm_futures"}:
                auto_cancel_payload = self._arm_futures_auto_cancel(family=family, environment=environment, symbol=request.get("symbol"))
            ack = self._submit_remote_order({**request, "client_order_id": client_order_id, "family": family, "environment": environment}, preview)
            order_row = self.db.upsert_order(
                {
                    **base_order,
                    "venue_order_id": ack.get("orderId") or ack.get("orderID"),
                    "order_status": str(ack.get("status") or "NEW").upper(),
                    "execution_type_last": str(ack.get("type") or ack.get("executionType") or "NEW").upper(),
                    "acknowledged_at": utc_now_iso(),
                    "executed_qty": _safe_float(ack.get("executedQty"), 0.0),
                    "cum_quote_qty": _safe_float(ack.get("cummulativeQuoteQty"), 0.0),
                    "avg_fill_price": _first_number(ack.get("avgPrice"), ack.get("price")),
                    "raw_ack": {**ack, "auto_cancel": auto_cancel_payload},
                    "raw_last_status": ack,
                }
            )
            fills = ack.get("fills") if isinstance(ack.get("fills"), list) else []
            for idx, fill in enumerate(fills):
                if not isinstance(fill, dict):
                    continue
                self.db.insert_fill(
                    {
                        "execution_fill_id": f"XFL-{uuid4().hex[:16].upper()}",
                        "execution_order_id": order_id,
                        "venue_trade_id": fill.get("tradeId") or f"{order_id}-{idx}",
                        "fill_time": utc_now_iso(),
                        "symbol": request.get("symbol"),
                        "family": family,
                        "price": _first_number(fill.get("price"), ack.get("price"), 0.0),
                        "qty": _first_number(fill.get("qty"), 0.0),
                        "quote_qty": _first_number(fill.get("quoteQty")),
                        "commission": _first_number(fill.get("commission"), 0.0),
                        "commission_asset": fill.get("commissionAsset"),
                        "raw_fill": fill,
                    }
                )
            self.refresh_reporting_views()
            return {
                "execution_intent_id": intent_id,
                "execution_order_id": order_id,
                "client_order_id": client_order_id,
                "order_status": order_row.get("order_status"),
                "mode": mode,
                "environment": environment,
                "family": family,
                "estimated_costs": preflight.get("estimated_costs"),
                "fail_closed": False,
            }
        except Exception as exc:
            self.db.upsert_order(
                {
                    **base_order,
                    "order_status": "REJECTED",
                    "execution_type_last": "REJECTED",
                    "reject_code": "SUBMIT_FAILED",
                    "reject_reason": str(exc),
                }
            )
            fail_closed = mode == "live"
            if fail_closed:
                self.trip_kill_switch(trigger_type="submit_failed", severity="BLOCK", family=family, symbol=request.get("symbol"), reason=str(exc))
            return {
                "execution_intent_id": intent_id,
                "execution_order_id": order_id,
                "client_order_id": client_order_id,
                "order_status": "REJECTED",
                "mode": mode,
                "environment": environment,
                "family": family,
                "estimated_costs": preflight.get("estimated_costs"),
                "fail_closed": fail_closed,
            }

    def order_detail(self, execution_order_id: str) -> dict[str, Any] | None:
        order = self.db.order(execution_order_id)
        if order is None:
            return None
        intent = self.db.intent(str(order.get("execution_intent_id") or ""))
        fills = self.db.fills_for_order(execution_order_id)
        reconcile_events = self.db.reconcile_events_for_order(execution_order_id)
        realized_fee = sum(_safe_float(fill.get("commission"), 0.0) for fill in fills)
        funding = sum(_safe_float(fill.get("funding_component"), 0.0) for fill in fills)
        borrow = sum(_safe_float(fill.get("borrow_interest_component"), 0.0) for fill in fills)
        gross_pnl = sum(_safe_float(fill.get("realized_pnl"), 0.0) for fill in fills)
        realized_costs = {
            "exchange_fee_realized": round(realized_fee, 8),
            "funding_realized": round(funding, 8),
            "borrow_interest_realized": round(borrow, 8),
            "gross_pnl": round(gross_pnl, 8),
            "net_pnl": round(gross_pnl - realized_fee - funding - borrow, 8),
        }
        return {
            "order": order,
            "intent": intent,
            "ack": order.get("raw_ack"),
            "last_status": order.get("raw_last_status"),
            "fills": fills,
            "realized_costs": realized_costs,
            "reconcile_events": reconcile_events,
        }

    def cancel_order(self, execution_order_id: str) -> dict[str, Any]:
        order = self.db.order(execution_order_id)
        if order is None:
            raise ValueError(f"Execution order not found: {execution_order_id}")
        mode = str((self.db.intent(str(order.get("execution_intent_id") or "")) or {}).get("mode") or "paper")
        if mode in {"paper", "shadow"} or not str(order.get("venue_order_id") or ""):
            updated = self.db.upsert_order(
                {
                    **order,
                    "order_status": "CANCELED",
                    "execution_type_last": "CANCELED",
                    "canceled_at": utc_now_iso(),
                    "raw_last_status": {"simulated": True, "status": "CANCELED"},
                }
            )
            return {"ok": True, "order": updated}
        payload = self._cancel_remote_order(order)
        updated = self.db.upsert_order(
            {
                **order,
                "order_status": str(payload.get("status") or "CANCELED").upper(),
                "execution_type_last": "CANCELED",
                "canceled_at": utc_now_iso(),
                "raw_last_status": payload,
            }
        )
        return {"ok": True, "order": updated}

    def cancel_all(self, *, family: str, environment: str, symbol: str | None = None) -> dict[str, Any]:
        canceled: list[str] = []
        for order in self.db.open_orders(family=family, symbol=symbol):
            if str(order.get("environment") or "") != _normalize_environment(environment):
                continue
            self.cancel_order(str(order.get("execution_order_id") or ""))
            canceled.append(str(order.get("execution_order_id") or ""))
        return {"ok": True, "count": len(canceled), "execution_order_ids": canceled}

    def trip_kill_switch(
        self,
        *,
        trigger_type: str,
        severity: str = "BLOCK",
        family: str | None = None,
        symbol: str | None = None,
        reason: str = "manual",
        auto_actions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        actions = copy.deepcopy(auto_actions or {})
        if _bool((self.safety_policy().get("kill_switch") or {}).get("auto_cancel_all_on_trip", True)):
            cancel_targets = []
            for order in self.db.open_orders(family=family):
                self.cancel_order(str(order.get("execution_order_id") or ""))
                cancel_targets.append(str(order.get("execution_order_id") or ""))
            actions.setdefault("canceled_orders", cancel_targets)
        self.db.trip_kill_switch(
            {
                "kill_switch_event_id": f"KSE-{uuid4().hex[:16].upper()}",
                "created_at": utc_now_iso(),
                "trigger_type": trigger_type,
                "severity": severity,
                "family": family,
                "symbol": symbol,
                "reason": reason,
                "auto_actions": actions,
            }
        )
        return self.db.kill_switch_status()

    def reset_kill_switch(self) -> dict[str, Any]:
        active = self.db.kill_switch_status()
        event = active.get("active_event") if isinstance(active.get("active_event"), dict) else None
        if event is None or not _bool(active.get("armed")):
            return active
        cooldown = int((self.safety_policy().get("kill_switch") or {}).get("cooldown_sec", 300) or 300)
        created_at = _parse_ts(event.get("created_at"))
        if created_at is not None and (_utc_now() - created_at).total_seconds() < cooldown:
            remaining = cooldown - int((_utc_now() - created_at).total_seconds())
            return {**active, "reset_allowed": False, "cooldown_remaining_sec": max(0, remaining)}
        status = self.db.clear_kill_switch()
        return {**status, "reset_allowed": True, "cooldown_remaining_sec": 0}

    def ingest_spot_execution_report(self, payload: dict[str, Any]) -> dict[str, Any]:
        client_order_id = str(payload.get("c") or "")
        orders = self.db.list_orders(limit=500)
        target = next((row for row in orders if str(row.get("client_order_id") or "") == client_order_id), None)
        if target is None:
            return {"ok": False, "reason": "order_not_found"}
        updated = self.db.upsert_order(
            {
                **target,
                "venue_order_id": payload.get("i") or target.get("venue_order_id"),
                "order_status": str(payload.get("X") or target.get("order_status") or "NEW").upper(),
                "execution_type_last": str(payload.get("x") or target.get("execution_type_last") or "TRADE").upper(),
                "acknowledged_at": target.get("acknowledged_at") or utc_now_iso(),
                "executed_qty": _first_number(payload.get("z"), target.get("executed_qty"), 0.0),
                "cum_quote_qty": _first_number(payload.get("Z"), target.get("cum_quote_qty"), 0.0),
                "avg_fill_price": _first_number(payload.get("L"), target.get("avg_fill_price")),
                "raw_last_status": payload,
            }
        )
        if str(payload.get("x") or "").upper() == "TRADE":
            self.db.insert_fill(
                {
                    "execution_fill_id": f"XFL-{uuid4().hex[:16].upper()}",
                    "execution_order_id": str(updated.get("execution_order_id") or ""),
                    "venue_trade_id": payload.get("t"),
                    "fill_time": utc_now_iso(),
                    "symbol": updated.get("symbol"),
                    "family": updated.get("family"),
                    "price": _first_number(payload.get("L"), updated.get("avg_fill_price"), 0.0),
                    "qty": _first_number(payload.get("l"), 0.0),
                    "quote_qty": _first_number(payload.get("Y")),
                    "commission": _first_number(payload.get("n"), 0.0),
                    "commission_asset": payload.get("N"),
                    "raw_fill": payload,
                }
            )
        self.mark_user_stream_status(family=str(updated.get("family") or ""), environment=str(updated.get("environment") or ""), available=True, degraded_reason="ok")
        self.refresh_reporting_views()
        return {"ok": True, "order": updated}

    def ingest_futures_order_trade_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        order_payload = payload.get("o") if isinstance(payload.get("o"), dict) else payload
        client_order_id = str(order_payload.get("c") or "")
        orders = self.db.list_orders(limit=500)
        target = next((row for row in orders if str(row.get("client_order_id") or "") == client_order_id), None)
        if target is None:
            return {"ok": False, "reason": "order_not_found"}
        updated = self.db.upsert_order(
            {
                **target,
                "venue_order_id": order_payload.get("i") or target.get("venue_order_id"),
                "order_status": str(order_payload.get("X") or target.get("order_status") or "NEW").upper(),
                "execution_type_last": str(order_payload.get("x") or target.get("execution_type_last") or "TRADE").upper(),
                "acknowledged_at": target.get("acknowledged_at") or utc_now_iso(),
                "executed_qty": _first_number(order_payload.get("z"), target.get("executed_qty"), 0.0),
                "cum_quote_qty": _first_number(order_payload.get("z")) * _first_number(order_payload.get("ap"), 0.0),
                "avg_fill_price": _first_number(order_payload.get("ap"), target.get("avg_fill_price")),
                "raw_last_status": payload,
            }
        )
        if str(order_payload.get("x") or "").upper() == "TRADE":
            self.db.insert_fill(
                {
                    "execution_fill_id": f"XFL-{uuid4().hex[:16].upper()}",
                    "execution_order_id": str(updated.get("execution_order_id") or ""),
                    "venue_trade_id": order_payload.get("t"),
                    "fill_time": utc_now_iso(),
                    "symbol": updated.get("symbol"),
                    "family": updated.get("family"),
                    "price": _first_number(order_payload.get("L"), order_payload.get("ap"), 0.0),
                    "qty": _first_number(order_payload.get("l"), 0.0),
                    "quote_qty": _first_number(order_payload.get("z")) * _first_number(order_payload.get("ap"), 0.0),
                    "commission": _first_number(order_payload.get("n"), 0.0),
                    "commission_asset": order_payload.get("N"),
                    "realized_pnl": _first_number(order_payload.get("rp")),
                    "maker": _bool(order_payload.get("m")),
                    "raw_fill": payload,
                }
            )
        self.mark_user_stream_status(family=str(updated.get("family") or ""), environment=str(updated.get("environment") or ""), available=True, degraded_reason="ok")
        self.refresh_reporting_views()
        return {"ok": True, "order": updated}

    def _record_reconcile_event(
        self,
        *,
        family: str,
        environment: str,
        reconcile_type: str,
        severity: str,
        execution_order_id: str | None = None,
        client_order_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.db.insert_reconcile_event(
            {
                "reconcile_event_id": f"REC-{uuid4().hex[:16].upper()}",
                "created_at": utc_now_iso(),
                "family": family,
                "environment": environment,
                "reconcile_type": reconcile_type,
                "severity": severity,
                "execution_order_id": execution_order_id,
                "client_order_id": client_order_id,
                "details": details or {},
            }
        )

    def reconcile_orders(self) -> dict[str, Any]:
        summary = {
            "ack_missing": 0,
            "fill_missing": 0,
            "orphan_orders": 0,
            "status_mismatches": 0,
            "cost_mismatches": 0,
            "unresolved_count": 0,
        }
        ack_timeout = int((self.safety_policy().get("reconciliation") or {}).get("order_ack_timeout_sec", 8) or 8)
        for order in self.db.list_orders(limit=500):
            age_sec = max(0.0, (_utc_now() - (_parse_ts(order.get("submitted_at")) or _utc_now())).total_seconds())
            if not order.get("acknowledged_at") and age_sec >= ack_timeout:
                self._record_reconcile_event(
                    family=str(order.get("family") or ""),
                    environment=str(order.get("environment") or ""),
                    reconcile_type="ack_missing",
                    severity="WARN",
                    execution_order_id=str(order.get("execution_order_id") or ""),
                    client_order_id=str(order.get("client_order_id") or ""),
                    details={"age_sec": age_sec},
                )
                summary["ack_missing"] += 1
            if str(order.get("order_status") or "") == "FILLED" and not self.db.fills_for_order(str(order.get("execution_order_id") or "")):
                self._record_reconcile_event(
                    family=str(order.get("family") or ""),
                    environment=str(order.get("environment") or ""),
                    reconcile_type="fill_missing",
                    severity="WARN",
                    execution_order_id=str(order.get("execution_order_id") or ""),
                    client_order_id=str(order.get("client_order_id") or ""),
                    details={"reason": "filled_without_local_fills"},
                )
                summary["fill_missing"] += 1
            if str(order.get("environment") or "") in {"live", "testnet"} and not _bool((self._user_stream_status.get((str(order.get("family") or ""), str(order.get("environment") or ""))) or {}).get("available")):
                self.mark_user_stream_status(
                    family=str(order.get("family") or ""),
                    environment=str(order.get("environment") or ""),
                    available=False,
                    degraded_reason="rest_polling_fallback",
                )
        unresolved = self.db.unresolved_reconcile_events()
        for item in unresolved:
            kind = str(item.get("reconcile_type") or "")
            if kind == "status_mismatch":
                summary["status_mismatches"] += 1
            if kind == "cost_mismatch":
                summary["cost_mismatches"] += 1
            if kind == "orphan_order":
                summary["orphan_orders"] += 1
        summary["unresolved_count"] = len(unresolved)
        return summary

    def reporting_trade_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for order in self.db.list_orders(limit=1000):
            intent = self.db.intent(str(order.get("execution_intent_id") or ""))
            fills = self.db.fills_for_order(str(order.get("execution_order_id") or ""))
            if not fills:
                continue
            estimated = {
                "exchange_fee_estimated": _safe_float((intent or {}).get("estimated_fee"), 0.0),
                "slippage_bps": _safe_float((intent or {}).get("estimated_slippage_bps"), 0.0),
                "total_cost_estimated": _safe_float((intent or {}).get("estimated_total_cost"), 0.0),
            }
            raw_request = (intent or {}).get("raw_request") if isinstance((intent or {}).get("raw_request"), dict) else {}
            preview_price = _first_number((raw_request or {}).get("price"), order.get("price"), order.get("avg_fill_price"), 0.0) or 0.0
            for fill in fills:
                spread_realized = 0.0
                slippage_realized = max(0.0, abs(_safe_float(fill.get("price"), 0.0) - preview_price) * _safe_float(fill.get("qty"), 0.0))
                total_realized = _safe_float(fill.get("commission"), 0.0) + _safe_float(fill.get("funding_component"), 0.0) + _safe_float(fill.get("borrow_interest_component"), 0.0) + slippage_realized + spread_realized
                gross_pnl = _safe_float(fill.get("realized_pnl"), 0.0)
                cost_classification = "realized" if str((intent or {}).get("mode") or "") in {"live", "testnet"} else "estimated_only"
                rows.append(
                    {
                        "trade_cost_id": f"EXE-{str(fill.get('execution_fill_id') or '')}",
                        "trade_ref": str(fill.get("venue_trade_id") or fill.get("execution_fill_id") or ""),
                        "run_id": None,
                        "venue": VENUE_BINANCE,
                        "family": str(fill.get("family") or ""),
                        "environment": str(order.get("environment") or "paper"),
                        "symbol": str(fill.get("symbol") or ""),
                        "strategy_id": (intent or {}).get("strategy_id"),
                        "bot_id": (intent or {}).get("bot_id"),
                        "executed_at": str(fill.get("fill_time") or utc_now_iso()),
                        "exchange_fee_estimated": estimated["exchange_fee_estimated"],
                        "exchange_fee_realized": _safe_float(fill.get("commission"), 0.0),
                        "fee_asset": fill.get("commission_asset"),
                        "spread_estimated": 0.0,
                        "spread_realized": spread_realized,
                        "slippage_estimated": 0.0 if cost_classification == "realized" else estimated["total_cost_estimated"],
                        "slippage_realized": slippage_realized,
                        "funding_estimated": 0.0,
                        "funding_realized": _safe_float(fill.get("funding_component"), 0.0),
                        "borrow_interest_estimated": 0.0,
                        "borrow_interest_realized": _safe_float(fill.get("borrow_interest_component"), 0.0),
                        "rebates_or_discounts": 0.0,
                        "total_cost_estimated": estimated["total_cost_estimated"],
                        "total_cost_realized": total_realized,
                        "gross_pnl": gross_pnl,
                        "net_pnl": gross_pnl - total_realized,
                        "cost_source": {
                            "mode": (intent or {}).get("mode"),
                            "environment": order.get("environment"),
                            "cost_classification": cost_classification,
                            "used_estimation_fallback": cost_classification != "realized",
                            "policy_hash": self._policy_hash(),
                        },
                        "provenance": {
                            "execution_order_id": order.get("execution_order_id"),
                            "execution_fill_id": fill.get("execution_fill_id"),
                            "source_kind": "execution_reality_fill",
                            "policy_hash": self._policy_hash(),
                        },
                        "created_at": utc_now_iso(),
                    }
                )
        return rows

    def reporting_cost_source_snapshots(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for family in FAMILIES:
            for environment in ENVIRONMENTS:
                latest = self._fee_source_state(family, environment).get("latest")
                payload = {
                    "venue": VENUE_BINANCE,
                    "family": family,
                    "environment": environment,
                    "execution_policy_hash": self._policy_hash(),
                    "degraded_mode": _bool((self._user_stream_status.get((family, environment)) or {}).get("degraded_mode")),
                }
                rows.append(
                    {
                        "cost_source_snapshot_id": f"EXCS-{hashlib.sha256(f'{family}:{environment}:{self._policy_hash()}'.encode('utf-8')).hexdigest()[:16].upper()}",
                        "venue": VENUE_BINANCE,
                        "family": family,
                        "environment": environment,
                        "source_kind": "execution_reality_cost_source",
                        "fetched_at": utc_now_iso(),
                        "source_endpoint": str((latest or {}).get("source_endpoint") or ""),
                        "source_hash": _sha256_json({"latest": latest, "payload": payload}),
                        "parser_version": PARSER_VERSION,
                        "payload": payload,
                        "success": True,
                        "error_message": None,
                    }
                )
        return rows

    def refresh_reporting_views(self, runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        base_rows = self.reporting_bridge_service._build_trade_rows(runs if runs is not None else self._runs())  # type: ignore[attr-defined]
        merged_rows = base_rows + self.reporting_trade_rows()
        merged_rows.sort(key=lambda row: (str(row.get("executed_at") or ""), str(row.get("trade_cost_id") or "")))
        snapshots = self.reporting_bridge_service._build_performance_snapshots(merged_rows)  # type: ignore[attr-defined]
        cost_sources = self.reporting_bridge_service._cost_source_binding_rows() + self.reporting_cost_source_snapshots()  # type: ignore[attr-defined]
        self.reporting_bridge_service.db.replace_trade_rows(merged_rows)
        self.reporting_bridge_service.db.replace_performance_snapshots(snapshots)
        self.reporting_bridge_service.db.replace_cost_source_snapshots(cost_sources)
        return {
            "ok": True,
            "trade_rows": len(merged_rows),
            "performance_snapshots": len(snapshots),
            "cost_source_snapshots": len(cost_sources),
            "policy_source": {
                **self.reporting_bridge_service.policy_source(),
                **self.policy_source(),
            },
        }

    def live_safety_summary(self) -> dict[str, Any]:
        parity = self.instrument_registry_service.live_parity_matrix()
        unresolved = self.db.unresolved_reconcile_events()
        fee_fresh = all(
            _bool(self._fee_source_state(family, "live").get("fresh")) or not ((parity.get(family) or {}).get("live") or {}).get("supported")
            for family in FAMILIES
        )
        stale_market_data = False
        if not self._quotes:
            stale_market_data = True
        else:
            for snapshot in self._quotes.values():
                quote_ts_ms = snapshot.get("quote_ts_ms")
                if quote_ts_ms is None:
                    stale_market_data = True
                    break
                if int(time.time() * 1000) - int(quote_ts_ms) >= int((self.safety_policy().get("kill_switch") or {}).get("stale_market_data_block_ms", 5000) or 5000):
                    stale_market_data = True
                    break
        margin_payload = self._margin_levels.get("live") or {}
        margin_status = "unknown"
        if margin_payload.get("level") is not None:
            level = _safe_float(margin_payload.get("level"), 0.0)
            if level < _safe_float((self.safety_policy().get("margin") or {}).get("block_margin_level_below"), 1.25):
                margin_status = "BLOCK"
            elif level < _safe_float((self.safety_policy().get("margin") or {}).get("warn_margin_level_below"), 1.5):
                margin_status = "WARN"
            else:
                margin_status = "OK"
        snapshot_fresh = all(
            ((parity.get(family) or {}).get("live") or {}).get("snapshot_fresh", False)
            for family in FAMILIES
            if ((parity.get(family) or {}).get("live") or {}).get("supported")
        )
        kill = self.db.kill_switch_status()
        overall = "OK"
        if _bool(kill.get("armed")) or not snapshot_fresh or not fee_fresh or stale_market_data:
            overall = "BLOCK"
        elif unresolved:
            overall = "WARN"
        return {
            "live_parity_base_ready": all(
                ((parity.get(family) or {}).get("live") or {}).get("live_parity_base_ready", False)
                for family in FAMILIES
                if ((parity.get(family) or {}).get("live") or {}).get("supported")
            ),
            "execution_policy_loaded": bool(self.policy_source()["execution_safety"]["valid"]) and bool(self.policy_source()["execution_router"]["valid"]),
            "kill_switch_armed": _bool(kill.get("armed")),
            "stale_market_data": stale_market_data,
            "fee_source_fresh": fee_fresh,
            "snapshot_fresh": snapshot_fresh,
            "unresolved_reconcile_count": len(unresolved),
            "margin_guard_status": margin_status,
            "degraded_mode": any(_bool(row.get("degraded_mode")) for row in self._user_stream_status.values()),
            "overall_status": overall,
            "policy_source": self.policy_source(),
        }

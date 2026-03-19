from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from rtlab_core.policy_paths import resolve_policy_root


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return _utc_now().isoformat()


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


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


def _sha256_json(value: Any) -> str:
    return _sha256_text(_json_dumps(value))


def _db_bool(value: Any) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


@lru_cache(maxsize=16)
def _load_policy_bundle_cached(
    filename: str,
    repo_root_str: str,
    explicit_root_str: str,
    default_payload_text: str,
) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    selected_root = resolve_policy_root(
        repo_root,
        explicit=explicit_root,
        expected_files=POLICY_EXPECTED_FILES,
    ).resolve()
    policy_path = (selected_root / filename).resolve()

    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    if policy_path.exists():
        try:
            raw_text = policy_path.read_text(encoding="utf-8")
            source_hash = _sha256_text(raw_text)
            raw = yaml.safe_load(raw_text) or {}
            if isinstance(raw, dict) and raw:
                payload = raw
                valid = True
        except Exception:
            payload = {}
            valid = False

    default_payload = yaml.safe_load(default_payload_text) or {}
    merged = _deep_merge(default_payload if isinstance(default_payload, dict) else {}, payload)
    if not source_hash:
        source_hash = _sha256_json(merged)
    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "source_hash": source_hash,
        "source": f"config/policies/{filename}" if valid else "default_fail_closed",
        "payload": merged,
    }


def _load_policy_bundle(
    filename: str,
    default_payload: dict[str, Any],
    repo_root: Path | None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(
        _load_policy_bundle_cached(
            filename,
            str(resolved_repo_root),
            explicit_root_str,
            yaml.safe_dump(default_payload, sort_keys=True),
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
        out = _row_to_dict(stored) or row
        out["preflight_errors_json"] = _json_loads(out.get("preflight_errors_json"), [])
        out["raw_request_json"] = _json_loads(out.get("raw_request_json"), {})
        return out

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
        out = _row_to_dict(stored) or row
        out["raw_ack_json"] = _json_loads(out.get("raw_ack_json"), {})
        out["raw_last_status_json"] = _json_loads(out.get("raw_last_status_json"), {})
        return out

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
        out = _row_to_dict(stored) or row
        out["raw_fill_json"] = _json_loads(out.get("raw_fill_json"), {})
        return out

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
        out = _row_to_dict(stored) or row
        out["details_json"] = _json_loads(out.get("details_json"), {})
        return out

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
        items = []
        for row in rows:
            payload = _row_to_dict(row) or {}
            payload["details_json"] = _json_loads(payload.get("details_json"), {})
            items.append(payload)
        return items

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

    def policy_hash(self) -> str:
        return _sha256_json(self.policy_source())

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
            "policy_loaded": bool(policy_source["execution_safety"]["valid"]) and bool(policy_source["execution_router"]["valid"]),
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

    def preflight(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Execution preflight se implementa en la parte 3.2 del bloque.")

    def create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Execution router fase 1 se implementa en la parte 3.3 del bloque.")

    def order_detail(self, execution_order_id: str) -> dict[str, Any] | None:
        raise NotImplementedError("Execution order detail se implementa en la parte 3.3 del bloque.")

    def cancel_order(self, execution_order_id: str) -> dict[str, Any]:
        raise NotImplementedError("Execution cancel se implementa en la parte 3.3 del bloque.")

    def cancel_all(self, *, family: str, environment: str, symbol: str | None = None) -> dict[str, Any]:
        raise NotImplementedError("Execution cancel-all se implementa en la parte 3.3 del bloque.")

    def reconcile_orders(self) -> dict[str, Any]:
        raise NotImplementedError("Execution reconcile se implementa en la parte 3.4 del bloque.")

    def live_safety_summary(self) -> dict[str, Any]:
        raise NotImplementedError("Execution live safety summary se implementa en la parte 3.5 del bloque.")

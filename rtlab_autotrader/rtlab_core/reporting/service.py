from __future__ import annotations

import copy
import hashlib
import json
import math
import sqlite3
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

import yaml

from rtlab_core.policy_paths import resolve_policy_root


VENUE_BINANCE = "binance"
FAMILIES: tuple[str, ...] = ("spot", "margin", "usdm_futures", "coinm_futures")
COST_STACK_FILENAME = "cost_stack.yaml"
REPORTING_EXPORTS_FILENAME = "reporting_exports.yaml"
PARSER_VERSION = "cost_reporting_bridge_v1"
POLICY_EXPECTED_FILES: tuple[str, ...] = (
    "runtime_controls.yaml",
    "instrument_registry.yaml",
    "universes.yaml",
    "cost_stack.yaml",
    "reporting_exports.yaml",
)

DEFAULT_COST_STACK_POLICY: dict[str, Any] = {
    "sources": {
        "spot_commission_source": "binance_account_commission",
        "spot_order_commission_estimation_source": "binance_order_test_computeCommissionRates",
        "futures_income_source": "binance_futures_income",
        "margin_interest_source": "binance_margin_interest_history",
    },
    "estimation": {
        "spread_bps_default": 4.0,
        "slippage_bps_default": 6.0,
        "block_if_missing_real_cost_source_in_live": True,
        "allow_fallback_estimation_in_paper": True,
    },
    "funding": {
        "enabled": True,
        "default_if_missing": 0.0,
    },
    "borrow_interest": {
        "enabled": True,
        "default_if_missing": 0.0,
    },
    "aggregation": {
        "supported_periods": ["day", "week", "month", "ytd", "all_time"],
        "trading_day_cutoff_tz": "UTC",
    },
    "display": {
        "show_gross_and_net_always": True,
        "require_cost_breakdown_for_strategy_kpis": True,
    },
    "alerts": {
        "warn_if_total_cost_pct_of_gross_pnl_gt": 35.0,
        "block_if_total_cost_pct_of_gross_pnl_gt": 80.0,
        "warn_if_slippage_bps_gt": 12.0,
        "warn_if_fee_source_stale_hours_gt": 24,
    },
}

DEFAULT_REPORTING_EXPORTS_POLICY: dict[str, Any] = {
    "formats": {
        "csv": True,
        "xlsx": True,
        "pdf": True,
    },
    "xlsx": {
        "include_summary_sheet": True,
        "include_daily_sheet": True,
        "include_monthly_sheet": True,
        "include_trades_sheet": True,
        "include_cost_breakdown_sheet": True,
    },
    "pdf": {
        "include_summary_cards": True,
        "include_equity_curve": True,
        "include_daily_pnl_chart": True,
        "include_monthly_pnl_chart": True,
        "include_cost_breakdown_table": True,
        "include_top_strategies": True,
    },
    "retention": {
        "export_manifest_keep_days": 30,
    },
    "filenames": {
        "prefix": "rtlab_report",
    },
    "limits": {
        "max_rows_per_export": 50000,
    },
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


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _round_money(value: Any) -> float:
    return round(_safe_float(value, 0.0), 8)


def _canonical_symbol(value: Any) -> str:
    return str(value or "").replace("/", "").replace("-", "").strip().upper()


def _normalize_family(value: Any) -> str:
    family = str(value or "").strip().lower()
    if family in FAMILIES:
        return family
    return ""


def _normalize_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode else "paper"


def _environment_from_mode(value: Any) -> str:
    mode = _normalize_mode(value)
    if mode == "live":
        return "live"
    if mode == "testnet":
        return "testnet"
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


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


def _infer_run_family(run: dict[str, Any], trade: dict[str, Any] | None = None) -> str:
    candidates = [
        (trade or {}).get("family"),
        run.get("family"),
        (run.get("metadata") if isinstance(run.get("metadata"), dict) else {}).get("family"),
        (run.get("provenance") if isinstance(run.get("provenance"), dict) else {}).get("family"),
        (run.get("params_json") if isinstance(run.get("params_json"), dict) else {}).get("family"),
    ]
    for candidate in candidates:
        family = _normalize_family(candidate)
        if family:
            return family

    symbol = _canonical_symbol(
        (trade or {}).get("symbol")
        or next(iter(run.get("symbols") or []), None)
        or next(iter(run.get("universe") or []), None)
    )
    if symbol.endswith("PERP") and "USD" in symbol and "USDT" not in symbol:
        return "coinm_futures"
    return "spot"


def _trade_notional(trade: dict[str, Any]) -> float:
    entry_px = _safe_float(trade.get("entry_px"), 0.0)
    exit_px = _safe_float(trade.get("exit_px"), entry_px)
    qty = abs(_safe_float(trade.get("qty"), 0.0))
    roundtrip = abs(entry_px * qty) + abs(exit_px * qty)
    if roundtrip > 0:
        return roundtrip
    return abs(_safe_float(trade.get("quote_qty"), 0.0))


def _window_start(period_type: str, latest: datetime, tz_name: str) -> datetime:
    tz = ZoneInfo(tz_name)
    local = latest.astimezone(tz)
    if period_type == "day":
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period_type == "week":
        start_local = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period_type == "month":
        start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period_type == "ytd":
        start_local = local.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start_local = datetime(1970, 1, 1, tzinfo=tz)
    return start_local.astimezone(timezone.utc)


def _max_drawdown_from_rows(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: str(row.get("executed_at") or ""))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for row in ordered:
        equity += _safe_float(row.get("net_pnl"), 0.0)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
    return round(max_dd, 8)


def _percent_of_gross(total_cost: float, gross_pnl: float) -> float:
    gross_abs = abs(gross_pnl)
    if gross_abs <= 0:
        return 0.0
    return round((abs(total_cost) / gross_abs) * 100.0, 6)


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


@lru_cache(maxsize=8)
def _load_cost_stack_bundle_cached(repo_root_str: str, explicit_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    selected_root = resolve_policy_root(
        repo_root,
        explicit=explicit_root,
        expected_files=POLICY_EXPECTED_FILES,
    ).resolve()
    policy_path = (selected_root / COST_STACK_FILENAME).resolve()

    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    if policy_path.exists():
        try:
            raw_text = policy_path.read_text(encoding="utf-8")
            source_hash = _sha256_text(raw_text)
            raw = yaml.safe_load(raw_text) or {}
            candidate = raw.get("cost_stack") if isinstance(raw.get("cost_stack"), dict) else {}
            if isinstance(candidate, dict) and candidate:
                payload = candidate
                valid = True
        except Exception:
            payload = {}
            valid = False
    merged = _deep_merge(DEFAULT_COST_STACK_POLICY, payload)
    if not source_hash:
        source_hash = _sha256_json(merged)
    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "source_hash": source_hash,
        "source": "config/policies/cost_stack.yaml" if valid else "default_fail_closed",
        "cost_stack": merged,
    }


def load_cost_stack_bundle(repo_root: Path | None = None, *, explicit_root: Path | None = None) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(_load_cost_stack_bundle_cached(str(resolved_repo_root), explicit_root_str))


def cost_stack_policy(repo_root: Path | None = None, *, explicit_root: Path | None = None) -> dict[str, Any]:
    bundle = load_cost_stack_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("cost_stack")
    return payload if isinstance(payload, dict) else copy.deepcopy(DEFAULT_COST_STACK_POLICY)


@lru_cache(maxsize=8)
def _load_reporting_exports_bundle_cached(repo_root_str: str, explicit_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    selected_root = resolve_policy_root(
        repo_root,
        explicit=explicit_root,
        expected_files=POLICY_EXPECTED_FILES,
    ).resolve()
    policy_path = (selected_root / REPORTING_EXPORTS_FILENAME).resolve()

    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    if policy_path.exists():
        try:
            raw_text = policy_path.read_text(encoding="utf-8")
            source_hash = _sha256_text(raw_text)
            raw = yaml.safe_load(raw_text) or {}
            candidate = raw.get("reporting_exports") if isinstance(raw.get("reporting_exports"), dict) else {}
            if isinstance(candidate, dict) and candidate:
                payload = candidate
                valid = True
        except Exception:
            payload = {}
            valid = False
    merged = _deep_merge(DEFAULT_REPORTING_EXPORTS_POLICY, payload)
    if not source_hash:
        source_hash = _sha256_json(merged)
    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "source_hash": source_hash,
        "source": "config/policies/reporting_exports.yaml" if valid else "default_fail_closed",
        "reporting_exports": merged,
    }


def load_reporting_exports_bundle(repo_root: Path | None = None, *, explicit_root: Path | None = None) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(_load_reporting_exports_bundle_cached(str(resolved_repo_root), explicit_root_str))


def reporting_exports_policy(repo_root: Path | None = None, *, explicit_root: Path | None = None) -> dict[str, Any]:
    bundle = load_reporting_exports_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("reporting_exports")
    return payload if isinstance(payload, dict) else copy.deepcopy(DEFAULT_REPORTING_EXPORTS_POLICY)


class ReportingBridgeDB:
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
                CREATE TABLE IF NOT EXISTS performance_cost_snapshots (
                  snapshot_id TEXT PRIMARY KEY,
                  venue TEXT NOT NULL,
                  family TEXT NOT NULL,
                  strategy_id TEXT,
                  bot_id TEXT,
                  period_type TEXT NOT NULL,
                  period_start TEXT NOT NULL,
                  period_end TEXT NOT NULL,
                  gross_pnl REAL NOT NULL DEFAULT 0.0,
                  total_cost_estimated REAL NOT NULL DEFAULT 0.0,
                  total_cost_realized REAL NOT NULL DEFAULT 0.0,
                  net_pnl REAL NOT NULL DEFAULT 0.0,
                  trade_count INTEGER NOT NULL DEFAULT 0,
                  win_rate REAL,
                  profit_factor REAL,
                  expectancy REAL,
                  max_drawdown REAL,
                  source_kind TEXT NOT NULL,
                  policy_hash TEXT NOT NULL,
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_perf_snapshots_period ON performance_cost_snapshots(period_type, family, created_at DESC);

                CREATE TABLE IF NOT EXISTS trade_cost_ledger (
                  trade_cost_id TEXT PRIMARY KEY,
                  trade_ref TEXT NOT NULL,
                  run_id TEXT,
                  venue TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  strategy_id TEXT,
                  bot_id TEXT,
                  executed_at TEXT NOT NULL,
                  exchange_fee_estimated REAL NOT NULL DEFAULT 0.0,
                  exchange_fee_realized REAL,
                  fee_asset TEXT,
                  spread_estimated REAL NOT NULL DEFAULT 0.0,
                  spread_realized REAL,
                  slippage_estimated REAL NOT NULL DEFAULT 0.0,
                  slippage_realized REAL,
                  funding_estimated REAL NOT NULL DEFAULT 0.0,
                  funding_realized REAL,
                  borrow_interest_estimated REAL NOT NULL DEFAULT 0.0,
                  borrow_interest_realized REAL,
                  rebates_or_discounts REAL NOT NULL DEFAULT 0.0,
                  total_cost_estimated REAL NOT NULL DEFAULT 0.0,
                  total_cost_realized REAL NOT NULL DEFAULT 0.0,
                  gross_pnl REAL NOT NULL DEFAULT 0.0,
                  net_pnl REAL NOT NULL DEFAULT 0.0,
                  cost_source_json TEXT NOT NULL DEFAULT '{}',
                  provenance_json TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_trade_cost_ledger_executed ON trade_cost_ledger(executed_at DESC);
                CREATE INDEX IF NOT EXISTS idx_trade_cost_ledger_family_symbol ON trade_cost_ledger(family, symbol, executed_at DESC);

                CREATE TABLE IF NOT EXISTS export_manifest (
                  export_id TEXT PRIMARY KEY,
                  export_type TEXT NOT NULL,
                  report_scope TEXT NOT NULL,
                  generated_at TEXT NOT NULL,
                  generated_by TEXT NOT NULL,
                  period_start TEXT,
                  period_end TEXT,
                  row_count INTEGER NOT NULL DEFAULT 0,
                  artifact_path TEXT NOT NULL,
                  source_snapshot_ids_json TEXT NOT NULL DEFAULT '[]',
                  success INTEGER NOT NULL DEFAULT 1,
                  error_message TEXT,
                  provenance_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_export_manifest_generated ON export_manifest(generated_at DESC);

                CREATE TABLE IF NOT EXISTS cost_source_snapshots (
                  cost_source_snapshot_id TEXT PRIMARY KEY,
                  venue TEXT NOT NULL,
                  family TEXT NOT NULL,
                  environment TEXT NOT NULL,
                  source_kind TEXT NOT NULL,
                  fetched_at TEXT NOT NULL,
                  source_endpoint TEXT NOT NULL,
                  source_hash TEXT NOT NULL,
                  parser_version TEXT NOT NULL,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  success INTEGER NOT NULL DEFAULT 1,
                  error_message TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_cost_source_snapshots_family_env ON cost_source_snapshots(family, environment, fetched_at DESC);
                """
            )
            conn.commit()

    def replace_trade_rows(self, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM trade_cost_ledger")
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO trade_cost_ledger (
                      trade_cost_id, trade_ref, run_id, venue, family, environment, symbol,
                      strategy_id, bot_id, executed_at, exchange_fee_estimated, exchange_fee_realized,
                      fee_asset, spread_estimated, spread_realized, slippage_estimated, slippage_realized,
                      funding_estimated, funding_realized, borrow_interest_estimated, borrow_interest_realized,
                      rebates_or_discounts, total_cost_estimated, total_cost_realized,
                      gross_pnl, net_pnl, cost_source_json, provenance_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(row.get("trade_cost_id") or ""),
                        str(row.get("trade_ref") or ""),
                        str(row.get("run_id") or "") or None,
                        str(row.get("venue") or VENUE_BINANCE),
                        str(row.get("family") or "spot"),
                        str(row.get("environment") or "paper"),
                        str(row.get("symbol") or ""),
                        str(row.get("strategy_id") or "") or None,
                        str(row.get("bot_id") or "") or None,
                        str(row.get("executed_at") or utc_now_iso()),
                        _round_money(row.get("exchange_fee_estimated")),
                        None if row.get("exchange_fee_realized") is None else _round_money(row.get("exchange_fee_realized")),
                        str(row.get("fee_asset") or "") or None,
                        _round_money(row.get("spread_estimated")),
                        None if row.get("spread_realized") is None else _round_money(row.get("spread_realized")),
                        _round_money(row.get("slippage_estimated")),
                        None if row.get("slippage_realized") is None else _round_money(row.get("slippage_realized")),
                        _round_money(row.get("funding_estimated")),
                        None if row.get("funding_realized") is None else _round_money(row.get("funding_realized")),
                        _round_money(row.get("borrow_interest_estimated")),
                        None if row.get("borrow_interest_realized") is None else _round_money(row.get("borrow_interest_realized")),
                        _round_money(row.get("rebates_or_discounts")),
                        _round_money(row.get("total_cost_estimated")),
                        _round_money(row.get("total_cost_realized")),
                        _round_money(row.get("gross_pnl")),
                        _round_money(row.get("net_pnl")),
                        _json_dumps(row.get("cost_source") or {}),
                        _json_dumps(row.get("provenance") or {}),
                        str(row.get("created_at") or utc_now_iso()),
                    ),
                )
            conn.commit()

    def replace_performance_snapshots(self, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM performance_cost_snapshots")
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO performance_cost_snapshots (
                      snapshot_id, venue, family, strategy_id, bot_id, period_type,
                      period_start, period_end, gross_pnl, total_cost_estimated,
                      total_cost_realized, net_pnl, trade_count, win_rate, profit_factor,
                      expectancy, max_drawdown, source_kind, policy_hash, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(row.get("snapshot_id") or ""),
                        str(row.get("venue") or VENUE_BINANCE),
                        str(row.get("family") or "all"),
                        str(row.get("strategy_id") or "") or None,
                        str(row.get("bot_id") or "") or None,
                        str(row.get("period_type") or "all_time"),
                        str(row.get("period_start") or ""),
                        str(row.get("period_end") or ""),
                        _round_money(row.get("gross_pnl")),
                        _round_money(row.get("total_cost_estimated")),
                        _round_money(row.get("total_cost_realized")),
                        _round_money(row.get("net_pnl")),
                        int(row.get("trade_count") or 0),
                        None if row.get("win_rate") is None else float(row.get("win_rate")),
                        None if row.get("profit_factor") is None else float(row.get("profit_factor")),
                        None if row.get("expectancy") is None else float(row.get("expectancy")),
                        None if row.get("max_drawdown") is None else float(row.get("max_drawdown")),
                        str(row.get("source_kind") or "trade_cost_ledger_rollup"),
                        str(row.get("policy_hash") or ""),
                        str(row.get("created_at") or utc_now_iso()),
                    ),
                )
            conn.commit()

    def replace_cost_source_snapshots(self, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM cost_source_snapshots")
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO cost_source_snapshots (
                      cost_source_snapshot_id, venue, family, environment, source_kind,
                      fetched_at, source_endpoint, source_hash, parser_version, payload_json,
                      success, error_message
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(row.get("cost_source_snapshot_id") or ""),
                        str(row.get("venue") or VENUE_BINANCE),
                        str(row.get("family") or "spot"),
                        str(row.get("environment") or "paper"),
                        str(row.get("source_kind") or "cost_source_binding"),
                        str(row.get("fetched_at") or utc_now_iso()),
                        str(row.get("source_endpoint") or ""),
                        str(row.get("source_hash") or ""),
                        str(row.get("parser_version") or PARSER_VERSION),
                        _json_dumps(row.get("payload") or {}),
                        1 if _bool(row.get("success")) else 0,
                        str(row.get("error_message") or "") or None,
                    ),
                )
            conn.commit()

    def insert_export_manifest(self, row: dict[str, Any]) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO export_manifest (
                  export_id, export_type, report_scope, generated_at, generated_by,
                  period_start, period_end, row_count, artifact_path,
                  source_snapshot_ids_json, success, error_message, provenance_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(row.get("export_id") or ""),
                    str(row.get("export_type") or ""),
                    str(row.get("report_scope") or "full"),
                    str(row.get("generated_at") or utc_now_iso()),
                    str(row.get("generated_by") or "system"),
                    str(row.get("period_start") or "") or None,
                    str(row.get("period_end") or "") or None,
                    int(row.get("row_count") or 0),
                    str(row.get("artifact_path") or ""),
                    _json_dumps(row.get("source_snapshot_ids") or []),
                    1 if _bool(row.get("success", True)) else 0,
                    str(row.get("error_message") or "") or None,
                    _json_dumps(row.get("provenance") or {}),
                ),
            )
            conn.commit()
        return row

    def trade_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM trade_cost_ledger ORDER BY executed_at DESC, trade_cost_id DESC").fetchall()
        return [
            {
                "trade_cost_id": str(row["trade_cost_id"]),
                "trade_ref": str(row["trade_ref"]),
                "run_id": str(row["run_id"] or "") or None,
                "venue": str(row["venue"]),
                "family": str(row["family"]),
                "environment": str(row["environment"]),
                "symbol": str(row["symbol"]),
                "strategy_id": str(row["strategy_id"] or "") or None,
                "bot_id": str(row["bot_id"] or "") or None,
                "executed_at": str(row["executed_at"]),
                "exchange_fee_estimated": float(row["exchange_fee_estimated"] or 0.0),
                "exchange_fee_realized": None if row["exchange_fee_realized"] is None else float(row["exchange_fee_realized"]),
                "fee_asset": str(row["fee_asset"] or "") or None,
                "spread_estimated": float(row["spread_estimated"] or 0.0),
                "spread_realized": None if row["spread_realized"] is None else float(row["spread_realized"]),
                "slippage_estimated": float(row["slippage_estimated"] or 0.0),
                "slippage_realized": None if row["slippage_realized"] is None else float(row["slippage_realized"]),
                "funding_estimated": float(row["funding_estimated"] or 0.0),
                "funding_realized": None if row["funding_realized"] is None else float(row["funding_realized"]),
                "borrow_interest_estimated": float(row["borrow_interest_estimated"] or 0.0),
                "borrow_interest_realized": None if row["borrow_interest_realized"] is None else float(row["borrow_interest_realized"]),
                "rebates_or_discounts": float(row["rebates_or_discounts"] or 0.0),
                "total_cost_estimated": float(row["total_cost_estimated"] or 0.0),
                "total_cost_realized": float(row["total_cost_realized"] or 0.0),
                "gross_pnl": float(row["gross_pnl"] or 0.0),
                "net_pnl": float(row["net_pnl"] or 0.0),
                "cost_source": _json_loads(row["cost_source_json"], {}),
                "provenance": _json_loads(row["provenance_json"], {}),
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def performance_snapshots(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM performance_cost_snapshots ORDER BY created_at DESC, snapshot_id DESC").fetchall()
        return [dict(row) for row in rows]

    def cost_source_snapshots(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM cost_source_snapshots ORDER BY fetched_at DESC, cost_source_snapshot_id DESC").fetchall()
        return [
            {
                "cost_source_snapshot_id": str(row["cost_source_snapshot_id"]),
                "venue": str(row["venue"]),
                "family": str(row["family"]),
                "environment": str(row["environment"]),
                "source_kind": str(row["source_kind"]),
                "fetched_at": str(row["fetched_at"]),
                "source_endpoint": str(row["source_endpoint"]),
                "source_hash": str(row["source_hash"]),
                "parser_version": str(row["parser_version"]),
                "payload": _json_loads(row["payload_json"], {}),
                "success": _bool(row["success"]),
                "error_message": str(row["error_message"] or "") or None,
            }
            for row in rows
        ]

    def list_exports(self, *, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM export_manifest ORDER BY generated_at DESC, export_id DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()
        return [
            {
                "export_id": str(row["export_id"]),
                "export_type": str(row["export_type"]),
                "report_scope": str(row["report_scope"]),
                "generated_at": str(row["generated_at"]),
                "generated_by": str(row["generated_by"]),
                "period_start": str(row["period_start"] or "") or None,
                "period_end": str(row["period_end"] or "") or None,
                "row_count": int(row["row_count"] or 0),
                "artifact_path": str(row["artifact_path"]),
                "source_snapshot_ids": _json_loads(row["source_snapshot_ids_json"], []),
                "success": _bool(row["success"]),
                "error_message": str(row["error_message"] or "") or None,
                "provenance": _json_loads(row["provenance_json"], {}),
            }
            for row in rows
        ]


class ReportingBridgeService:
    def __init__(
        self,
        *,
        user_data_dir: Path,
        repo_root: Path,
        explicit_policy_root: Path | None = None,
        instrument_registry_service: Any | None = None,
        runs_path: Path | None = None,
    ) -> None:
        self.user_data_dir = Path(user_data_dir).resolve()
        self.repo_root = Path(repo_root).resolve()
        self.explicit_policy_root = explicit_policy_root.resolve() if explicit_policy_root is not None else None
        self.instrument_registry_service = instrument_registry_service
        self.runs_path = (runs_path or (self.user_data_dir / "backtests" / "runs.json")).resolve()
        self.exports_dir = (self.user_data_dir / "reporting" / "exports").resolve()
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.db = ReportingBridgeDB(self.user_data_dir / "reporting" / "reporting.sqlite3")

    def cost_stack_bundle(self) -> dict[str, Any]:
        return load_cost_stack_bundle(self.repo_root, explicit_root=self.explicit_policy_root)

    def reporting_exports_bundle(self) -> dict[str, Any]:
        return load_reporting_exports_bundle(self.repo_root, explicit_root=self.explicit_policy_root)

    def cost_stack(self) -> dict[str, Any]:
        return cost_stack_policy(self.repo_root, explicit_root=self.explicit_policy_root)

    def exports_policy(self) -> dict[str, Any]:
        return reporting_exports_policy(self.repo_root, explicit_root=self.explicit_policy_root)

    def policy_source(self) -> dict[str, Any]:
        cost_bundle = self.cost_stack_bundle()
        exports_bundle = self.reporting_exports_bundle()
        return {
            "cost_stack": {
                "path": cost_bundle.get("path"),
                "hash": cost_bundle.get("source_hash"),
                "source": cost_bundle.get("source"),
                "valid": bool(cost_bundle.get("valid")),
            },
            "reporting_exports": {
                "path": exports_bundle.get("path"),
                "hash": exports_bundle.get("source_hash"),
                "source": exports_bundle.get("source"),
                "valid": bool(exports_bundle.get("valid")),
            },
        }

    def load_runs(self) -> list[dict[str, Any]]:
        if not self.runs_path.exists():
            return []
        try:
            payload = json.loads(self.runs_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def _cost_source_binding_rows(self) -> list[dict[str, Any]]:
        policy = self.cost_stack()
        sources = policy.get("sources") if isinstance(policy.get("sources"), dict) else {}
        registry_policy = {}
        if self.instrument_registry_service is not None:
            try:
                registry_policy = self.instrument_registry_service.policy()
            except Exception:
                registry_policy = {}
        environments_cfg = registry_policy.get("environments") if isinstance(registry_policy.get("environments"), dict) else {
            "spot": {"live": True, "testnet": True},
            "margin": {"live": True, "testnet": False},
            "usdm_futures": {"live": True, "testnet": True},
            "coinm_futures": {"live": True, "testnet": True},
        }
        descriptors: dict[str, dict[str, Any]] = {
            "spot": {
                "primary_source": str(sources.get("spot_commission_source") or "binance_account_commission"),
                "estimated_source": str(sources.get("spot_order_commission_estimation_source") or "binance_order_test_computeCommissionRates"),
                "source_endpoint": "GET /api/v3/account/commission",
                "estimated_endpoint": "POST /api/v3/order/test?computeCommissionRates=true",
            },
            "margin": {
                "primary_source": str(sources.get("spot_commission_source") or "binance_account_commission"),
                "realized_interest_source": str(sources.get("margin_interest_source") or "binance_margin_interest_history"),
                "source_endpoint": "GET /sapi/v1/margin/interestHistory",
                "estimated_endpoint": "POST /api/v3/order/test?computeCommissionRates=true",
            },
            "usdm_futures": {
                "primary_source": str(sources.get("futures_income_source") or "binance_futures_income"),
                "commission_rate_source": "binance_usdm_commission_rate",
                "source_endpoint": "GET /fapi/v1/income",
                "estimated_endpoint": "GET /fapi/v1/commissionRate",
            },
            "coinm_futures": {
                "primary_source": str(sources.get("futures_income_source") or "binance_futures_income"),
                "commission_rate_source": "binance_coinm_commission_rate",
                "source_endpoint": "GET /dapi/v1/income",
                "estimated_endpoint": "GET /dapi/v1/commissionRate",
            },
        }
        rows: list[dict[str, Any]] = []
        fetched_at = utc_now_iso()
        policy_source = self.policy_source()
        for family in FAMILIES:
            envs = environments_cfg.get(family) if isinstance(environments_cfg.get(family), dict) else {}
            for environment, enabled in sorted(envs.items()):
                if not _bool(enabled):
                    continue
                descriptor = {
                    "venue": VENUE_BINANCE,
                    "family": family,
                    "environment": str(environment),
                    "sources": descriptors.get(family) or {},
                    "policy_hash": str(policy_source["cost_stack"]["hash"] or ""),
                    "policy_source": policy_source["cost_stack"],
                    "provenance_mode": "official_source_binding",
                }
                rows.append(
                    {
                        "cost_source_snapshot_id": f"CSS-{hashlib.sha256(f'{family}:{environment}'.encode('utf-8')).hexdigest()[:12].upper()}",
                        "venue": VENUE_BINANCE,
                        "family": family,
                        "environment": str(environment),
                        "source_kind": "cost_source_binding",
                        "fetched_at": fetched_at,
                        "source_endpoint": str((descriptors.get(family) or {}).get("source_endpoint") or ""),
                        "source_hash": _sha256_json(descriptor),
                        "parser_version": PARSER_VERSION,
                        "payload": descriptor,
                        "success": True,
                        "error_message": None,
                    }
                )
        return rows

    def refresh_materialized_views(self, runs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        runtime_rows = [
            row
            for row in self.db.trade_rows()
            if str((row.get("provenance") if isinstance(row.get("provenance"), dict) else {}).get("source_kind") or "")
            in {"execution_reality_fill", "execution_reality_runtime"}
        ]
        rows = self._merge_trade_rows(
            self._build_trade_rows(runs if runs is not None else self.load_runs()),
            runtime_rows,
        )
        snapshots = self._build_performance_snapshots(rows)
        cost_sources = self._cost_source_binding_rows()
        self.db.replace_trade_rows(rows)
        self.db.replace_performance_snapshots(snapshots)
        self.db.replace_cost_source_snapshots(cost_sources)
        return {
            "ok": True,
            "trade_rows": len(rows),
            "performance_snapshots": len(snapshots),
            "cost_source_snapshots": len(cost_sources),
            "policy_source": self.policy_source(),
        }

    def upsert_execution_trade_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        existing = [
            row
            for row in self.db.trade_rows()
            if str((row.get("provenance") if isinstance(row.get("provenance"), dict) else {}).get("source_kind") or "")
            not in {"execution_reality_fill", "execution_reality_runtime"}
        ]
        merged = self._merge_trade_rows(existing, rows)
        snapshots = self._build_performance_snapshots(merged)
        cost_sources = self._cost_source_binding_rows()
        self.db.replace_trade_rows(merged)
        self.db.replace_performance_snapshots(snapshots)
        self.db.replace_cost_source_snapshots(cost_sources)
        return {
            "ok": True,
            "trade_rows_upserted": len(rows),
            "trade_rows_total": len(merged),
            "performance_snapshots": len(snapshots),
            "cost_source_snapshots": len(cost_sources),
            "policy_source": self.policy_source(),
        }

    def _merge_trade_rows(self, base_rows: list[dict[str, Any]], overlay_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for row in base_rows:
            if not isinstance(row, dict):
                continue
            trade_cost_id = str(row.get("trade_cost_id") or "").strip()
            if not trade_cost_id:
                continue
            merged[trade_cost_id] = copy.deepcopy(row)
        for row in overlay_rows:
            if not isinstance(row, dict):
                continue
            trade_cost_id = str(row.get("trade_cost_id") or "").strip()
            if not trade_cost_id:
                continue
            merged[trade_cost_id] = copy.deepcopy(row)
        items = list(merged.values())
        items.sort(key=lambda row: (str(row.get("executed_at") or ""), str(row.get("trade_cost_id") or "")))
        return items

    def _build_trade_rows(self, runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        policy = self.cost_stack()
        estimation_cfg = policy.get("estimation") if isinstance(policy.get("estimation"), dict) else {}
        funding_cfg = policy.get("funding") if isinstance(policy.get("funding"), dict) else {}
        borrow_cfg = policy.get("borrow_interest") if isinstance(policy.get("borrow_interest"), dict) else {}
        policy_hash = str(self.policy_source()["cost_stack"]["hash"] or "")
        source_bindings = {
            (row["family"], row["environment"]): row
            for row in self._cost_source_binding_rows()
        }
        trade_rows: list[dict[str, Any]] = []

        for run in runs:
            if not isinstance(run, dict):
                continue
            mode = _normalize_mode(run.get("mode"))
            environment = _environment_from_mode(mode)
            venue = str((run.get("provenance") if isinstance(run.get("provenance"), dict) else {}).get("venue") or VENUE_BINANCE).strip().lower() or VENUE_BINANCE
            strategy_id = str(run.get("strategy_id") or "").strip() or None
            bot_id = str((run.get("params_json") if isinstance(run.get("params_json"), dict) else {}).get("bot_id") or "").strip() or None
            run_id = str(run.get("id") or run.get("run_id") or "").strip() or None
            costs_model = run.get("costs_model") if isinstance(run.get("costs_model"), dict) else {}
            trades = run.get("trades") if isinstance(run.get("trades"), list) else []
            for idx, trade in enumerate(trades):
                if not isinstance(trade, dict):
                    continue
                family = _infer_run_family(run, trade) or "spot"
                symbol = _canonical_symbol(trade.get("symbol") or next(iter(run.get("symbols") or []), None) or "")
                executed_dt = (
                    _parse_ts(trade.get("exit_time"))
                    or _parse_ts(trade.get("executed_at"))
                    or _parse_ts(trade.get("time"))
                    or _parse_ts(trade.get("entry_time"))
                    or _parse_ts(run.get("finished_at"))
                    or _parse_ts(run.get("created_at"))
                    or _utc_now()
                )
                binding = source_bindings.get((family, "live")) or source_bindings.get((family, "testnet"))
                roundtrip_notional = _trade_notional(trade)
                fee_default = roundtrip_notional * (_safe_float(costs_model.get("fees_bps"), 0.0) / 10000.0)
                spread_default = roundtrip_notional * (_safe_float(costs_model.get("spread_bps"), estimation_cfg.get("spread_bps_default", 4.0)) / 10000.0)
                slippage_default = roundtrip_notional * (_safe_float(costs_model.get("slippage_bps"), estimation_cfg.get("slippage_bps_default", 6.0)) / 10000.0)
                funding_default = roundtrip_notional * (_safe_float(costs_model.get("funding_bps"), funding_cfg.get("default_if_missing", 0.0)) / 10000.0)
                borrow_default = _safe_float(borrow_cfg.get("default_if_missing"), 0.0)

                fee_realized = _first_number(trade.get("exchange_fee_realized"))
                if fee_realized is None and mode in {"live", "testnet"} and trade.get("commissionAsset"):
                    fee_realized = _first_number(trade.get("commission"), trade.get("fees"))
                spread_realized = _first_number(trade.get("spread_realized"))
                slippage_realized = _first_number(trade.get("slippage_realized"))
                funding_realized = _first_number(trade.get("funding_realized"))
                borrow_realized = _first_number(trade.get("borrow_interest_realized"))

                estimated_only_mode = mode in {"backtest", "paper", "shadow"}
                allow_estimation = estimated_only_mode or mode == "testnet" or _bool(estimation_cfg.get("allow_fallback_estimation_in_paper"))

                fee_estimated = 0.0
                spread_estimated = 0.0
                slippage_estimated = 0.0
                funding_estimated = 0.0
                borrow_estimated = 0.0

                if estimated_only_mode:
                    fee_estimated = _safe_float(_first_number(trade.get("exchange_fee_estimated"), trade.get("fees"), fee_default), 0.0)
                    spread_estimated = _safe_float(_first_number(trade.get("spread_estimated"), trade.get("spread_cost"), spread_default), 0.0)
                    slippage_estimated = _safe_float(_first_number(trade.get("slippage_estimated"), trade.get("slippage_cost"), slippage_default), 0.0)
                    funding_estimated = _safe_float(_first_number(trade.get("funding_estimated"), trade.get("funding_cost"), funding_default), 0.0)
                    borrow_estimated = _safe_float(_first_number(trade.get("borrow_interest_estimated"), trade.get("borrow_interest"), borrow_default), 0.0)
                else:
                    if fee_realized is None and allow_estimation:
                        fee_estimated = _safe_float(_first_number(trade.get("exchange_fee_estimated"), trade.get("fees"), fee_default), 0.0)
                    spread_estimated = _safe_float(_first_number(trade.get("spread_estimated"), trade.get("spread_cost"), spread_default), 0.0)
                    slippage_estimated = _safe_float(_first_number(trade.get("slippage_estimated"), trade.get("slippage_cost"), slippage_default), 0.0)
                    if funding_realized is None and _bool(funding_cfg.get("enabled", True)):
                        funding_estimated = _safe_float(_first_number(trade.get("funding_estimated"), trade.get("funding_cost"), funding_default), 0.0)
                    if borrow_realized is None and _bool(borrow_cfg.get("enabled", True)):
                        borrow_estimated = _safe_float(_first_number(trade.get("borrow_interest_estimated"), trade.get("borrow_interest"), borrow_default), 0.0)

                if mode == "live" and _bool(estimation_cfg.get("block_if_missing_real_cost_source_in_live", True)):
                    missing_real: list[str] = []
                    if fee_realized is None:
                        missing_real.append("exchange_fee_realized")
                    if family in {"usdm_futures", "coinm_futures"} and _bool(funding_cfg.get("enabled", True)) and funding_realized is None:
                        missing_real.append("funding_realized")
                    if family == "margin" and _bool(borrow_cfg.get("enabled", True)) and borrow_realized is None:
                        missing_real.append("borrow_interest_realized")
                    if missing_real:
                        joined = ", ".join(missing_real)
                        raise RuntimeError(
                            f"Live cost stack fail-closed para {family}/{symbol or 'UNKNOWN'}: faltan fuentes reales ({joined})."
                        )

                gross_pnl = _safe_float(_first_number(trade.get("gross_pnl"), trade.get("pnl"), 0.0), 0.0)
                rebates = _safe_float(_first_number(trade.get("rebates_or_discounts"), trade.get("rebate"), 0.0), 0.0)
                total_estimated = fee_estimated + spread_estimated + slippage_estimated + funding_estimated + borrow_estimated - rebates
                total_realized = (
                    _safe_float(fee_realized, 0.0)
                    + _safe_float(spread_realized, 0.0)
                    + _safe_float(slippage_realized, 0.0)
                    + _safe_float(funding_realized, 0.0)
                    + _safe_float(borrow_realized, 0.0)
                    - rebates
                )
                provided_net = _first_number(trade.get("net_pnl"), trade.get("pnl_net"))
                net_reference = total_realized if total_realized > 0 else total_estimated
                net_pnl = _safe_float(provided_net if provided_net is not None else (gross_pnl - net_reference), 0.0)
                cost_classification = (
                    "realized"
                    if total_realized > 0 and total_estimated == 0
                    else "mixed"
                    if total_realized > 0 and total_estimated > 0
                    else "estimated_only"
                )
                trade_ref = str(trade.get("id") or trade.get("trade_id") or trade.get("fill_id") or f"{run_id or 'RUN'}-{idx:04d}")
                trade_key = f"{run_id or 'RUN'}:{trade_ref}:{executed_dt.isoformat()}"
                trade_cost_id = f"TCL-{hashlib.sha256(trade_key.encode('utf-8')).hexdigest()[:16].upper()}"
                cost_source = {
                    "mode": mode,
                    "environment": environment,
                    "cost_classification": cost_classification,
                    "binding": (binding or {}).get("payload") or {},
                    "used_estimation_fallback": cost_classification != "realized",
                    "policy_hash": policy_hash,
                }
                provenance = {
                    "run_id": run_id,
                    "trade_ref": trade_ref,
                    "policy_hash": policy_hash,
                    "policy_source": self.policy_source()["cost_stack"],
                    "run_created_at": run.get("created_at"),
                    "fee_snapshot_id": run.get("fee_snapshot_id"),
                    "funding_snapshot_id": run.get("funding_snapshot_id"),
                    "dataset_hash": (run.get("provenance") if isinstance(run.get("provenance"), dict) else {}).get("dataset_hash")
                    or run.get("dataset_hash"),
                    "source_kind": "runs_json_backfill",
                }
                trade_rows.append(
                    {
                        "trade_cost_id": trade_cost_id,
                        "trade_ref": trade_ref,
                        "run_id": run_id,
                        "venue": venue,
                        "family": family,
                        "environment": environment,
                        "symbol": symbol or "UNKNOWN",
                        "strategy_id": strategy_id,
                        "bot_id": bot_id,
                        "executed_at": executed_dt.isoformat(),
                        "exchange_fee_estimated": fee_estimated,
                        "exchange_fee_realized": fee_realized,
                        "fee_asset": str(trade.get("fee_asset") or trade.get("commissionAsset") or "") or None,
                        "spread_estimated": spread_estimated,
                        "spread_realized": spread_realized,
                        "slippage_estimated": slippage_estimated,
                        "slippage_realized": slippage_realized,
                        "funding_estimated": funding_estimated,
                        "funding_realized": funding_realized,
                        "borrow_interest_estimated": borrow_estimated,
                        "borrow_interest_realized": borrow_realized,
                        "rebates_or_discounts": rebates,
                        "total_cost_estimated": total_estimated,
                        "total_cost_realized": total_realized,
                        "gross_pnl": gross_pnl,
                        "net_pnl": net_pnl,
                        "cost_source": cost_source,
                        "provenance": provenance,
                        "created_at": utc_now_iso(),
                    }
                )
        trade_rows.sort(key=lambda row: (str(row.get("executed_at") or ""), str(row.get("trade_cost_id") or "")))
        return trade_rows

    def _aggregate_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        gross_pnl = sum(_safe_float(row.get("gross_pnl"), 0.0) for row in rows)
        total_cost_estimated = sum(_safe_float(row.get("total_cost_estimated"), 0.0) for row in rows)
        total_cost_realized = sum(_safe_float(row.get("total_cost_realized"), 0.0) for row in rows)
        net_pnl = sum(_safe_float(row.get("net_pnl"), 0.0) for row in rows)
        trade_count = len(rows)
        win_count = sum(1 for row in rows if _safe_float(row.get("net_pnl"), 0.0) > 0)
        gross_profit = sum(_safe_float(row.get("net_pnl"), 0.0) for row in rows if _safe_float(row.get("net_pnl"), 0.0) > 0)
        gross_loss = abs(sum(_safe_float(row.get("net_pnl"), 0.0) for row in rows if _safe_float(row.get("net_pnl"), 0.0) < 0))
        total_cost_effective = total_cost_realized if total_cost_realized > 0 else total_cost_estimated
        return {
            "gross_pnl": round(gross_pnl, 8),
            "total_cost_estimated": round(total_cost_estimated, 8),
            "total_cost_realized": round(total_cost_realized, 8),
            "net_pnl": round(net_pnl, 8),
            "trade_count": trade_count,
            "win_rate": round((win_count / trade_count), 8) if trade_count else None,
            "profit_factor": round((gross_profit / gross_loss), 8) if gross_loss > 0 else (None if gross_profit <= 0 else round(gross_profit, 8)),
            "expectancy": round((net_pnl / trade_count), 8) if trade_count else None,
            "max_drawdown": _max_drawdown_from_rows(rows),
            "total_cost_pct_of_gross_pnl": _percent_of_gross(total_cost_effective, gross_pnl),
        }

    def _build_performance_snapshots(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        policy = self.cost_stack()
        aggregation_cfg = policy.get("aggregation") if isinstance(policy.get("aggregation"), dict) else {}
        supported_periods = [
            str(item).strip().lower()
            for item in (aggregation_cfg.get("supported_periods") or ["day", "week", "month", "ytd", "all_time"])
            if str(item).strip()
        ]
        tz_name = str(aggregation_cfg.get("trading_day_cutoff_tz") or "UTC")
        latest = max((_parse_ts(row.get("executed_at")) or _utc_now()) for row in rows)
        created_at = utc_now_iso()
        policy_hash = str(self.policy_source()["cost_stack"]["hash"] or "")

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("family") or "spot")].append(row)
            grouped["all"].append(row)

        snapshots: list[dict[str, Any]] = []
        for family, family_rows in grouped.items():
            earliest = min((_parse_ts(row.get("executed_at")) or latest) for row in family_rows)
            for period_type in supported_periods:
                start = earliest if period_type == "all_time" else _window_start(period_type, latest, tz_name)
                period_rows = [row for row in family_rows if (_parse_ts(row.get("executed_at")) or latest) >= start]
                metrics = self._aggregate_rows(period_rows)
                snapshot_key = {
                    "family": family,
                    "period_type": period_type,
                    "period_start": start.isoformat(),
                    "period_end": latest.isoformat(),
                    "policy_hash": policy_hash,
                    "trade_count": metrics["trade_count"],
                    "gross_pnl": metrics["gross_pnl"],
                    "net_pnl": metrics["net_pnl"],
                }
                snapshots.append(
                    {
                        "snapshot_id": f"PCS-{hashlib.sha256(_json_dumps(snapshot_key).encode('utf-8')).hexdigest()[:16].upper()}",
                        "venue": VENUE_BINANCE,
                        "family": family,
                        "strategy_id": None,
                        "bot_id": None,
                        "period_type": period_type,
                        "period_start": start.isoformat(),
                        "period_end": latest.isoformat(),
                        "gross_pnl": metrics["gross_pnl"],
                        "total_cost_estimated": metrics["total_cost_estimated"],
                        "total_cost_realized": metrics["total_cost_realized"],
                        "net_pnl": metrics["net_pnl"],
                        "trade_count": metrics["trade_count"],
                        "win_rate": metrics["win_rate"],
                        "profit_factor": metrics["profit_factor"],
                        "expectancy": metrics["expectancy"],
                        "max_drawdown": metrics["max_drawdown"],
                        "source_kind": "trade_cost_ledger_rollup",
                        "policy_hash": policy_hash,
                        "created_at": created_at,
                    }
                )
        return snapshots

    def _filtered_trade_rows(
        self,
        *,
        strategy_id: str | None = None,
        bot_id: str | None = None,
        venue: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.db.trade_rows()
        filtered: list[dict[str, Any]] = []
        symbol_n = _canonical_symbol(symbol) if symbol is not None else ""
        for row in rows:
            if strategy_id and str(row.get("strategy_id") or "") != str(strategy_id):
                continue
            if bot_id and str(row.get("bot_id") or "") != str(bot_id):
                continue
            if venue and str(row.get("venue") or "").strip().lower() != str(venue).strip().lower():
                continue
            if family and str(row.get("family") or "").strip().lower() != str(family).strip().lower():
                continue
            if symbol_n and _canonical_symbol(row.get("symbol")) != symbol_n:
                continue
            if date_from and str(row.get("executed_at") or "") < str(date_from):
                continue
            if date_to and str(row.get("executed_at") or "") > str(date_to):
                continue
            filtered.append(row)
        filtered.sort(key=lambda row: str(row.get("executed_at") or ""))
        return filtered

    def _latest_cost_source_status(self, *, family: str | None = None) -> str:
        policy = self.cost_stack()
        alerts_cfg = policy.get("alerts") if isinstance(policy.get("alerts"), dict) else {}
        stale_hours = int(alerts_cfg.get("warn_if_fee_source_stale_hours_gt") or 24)
        rows = self.db.cost_source_snapshots()
        if family:
            rows = [row for row in rows if str(row.get("family") or "").strip().lower() == str(family).strip().lower()]
        if not rows:
            return "unknown"
        latest = max((_parse_ts(row.get("fetched_at")) or datetime(1970, 1, 1, tzinfo=timezone.utc)) for row in rows)
        age = _utc_now() - latest
        return "stale" if age > timedelta(hours=stale_hours) else "fresh"

    def performance_summary(
        self,
        *,
        strategy_id: str | None = None,
        bot_id: str | None = None,
        venue: str | None = None,
        family: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        rows = self._filtered_trade_rows(strategy_id=strategy_id, bot_id=bot_id, venue=venue, family=family, symbol=symbol)
        empty = {
            "gross_pnl": 0.0,
            "total_cost_estimated": 0.0,
            "total_cost_realized": 0.0,
            "net_pnl": 0.0,
            "trade_count": 0,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "max_drawdown": None,
            "policy_source": self.policy_source(),
            "freshness_status": self._latest_cost_source_status(family=family),
        }
        if not rows:
            return {"today": empty, "week": empty, "month": empty, "ytd": empty, "all_time": empty}

        policy = self.cost_stack()
        aggregation_cfg = policy.get("aggregation") if isinstance(policy.get("aggregation"), dict) else {}
        tz_name = str(aggregation_cfg.get("trading_day_cutoff_tz") or "UTC")
        latest = max((_parse_ts(row.get("executed_at")) or _utc_now()) for row in rows)
        mapping = {"today": "day", "week": "week", "month": "month", "ytd": "ytd", "all_time": "all_time"}
        out: dict[str, Any] = {}
        for key, period_type in mapping.items():
            start = _window_start(period_type, latest, tz_name) if period_type != "all_time" else min((_parse_ts(row.get("executed_at")) or latest) for row in rows)
            period_rows = [row for row in rows if (_parse_ts(row.get("executed_at")) or latest) >= start]
            metrics = self._aggregate_rows(period_rows)
            out[key] = {
                **metrics,
                "policy_source": self.policy_source(),
                "freshness_status": self._latest_cost_source_status(family=family),
            }
        return out

    def _series_by_bucket(self, rows: list[dict[str, Any]], *, bucket: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            ts = _parse_ts(row.get("executed_at")) or _utc_now()
            key = ts.strftime("%Y-%m-%d") if bucket == "day" else ts.strftime("%Y-%m")
            grouped[key].append(row)
        items: list[dict[str, Any]] = []
        for key in sorted(grouped):
            metrics = self._aggregate_rows(grouped[key])
            items.append(
                {
                    "bucket": key,
                    "gross_pnl": metrics["gross_pnl"],
                    "total_cost_estimated": metrics["total_cost_estimated"],
                    "total_cost_realized": metrics["total_cost_realized"],
                    "net_pnl": metrics["net_pnl"],
                    "trade_count": metrics["trade_count"],
                }
            )
        return items

    def daily_series(self, **filters: Any) -> dict[str, Any]:
        rows = self._filtered_trade_rows(**filters)
        return {
            "items": self._series_by_bucket(rows, bucket="day"),
            "count": len(rows),
            "policy_source": self.policy_source(),
            "freshness_status": self._latest_cost_source_status(family=filters.get("family")),
        }

    def monthly_series(self, **filters: Any) -> dict[str, Any]:
        rows = self._filtered_trade_rows(**filters)
        return {
            "items": self._series_by_bucket(rows, bucket="month"),
            "count": len(rows),
            "policy_source": self.policy_source(),
            "freshness_status": self._latest_cost_source_status(family=filters.get("family")),
        }

    def costs_breakdown(self, **filters: Any) -> dict[str, Any]:
        rows = self._filtered_trade_rows(**filters)
        totals = {
            "exchange_fee_estimated": sum(_safe_float(row.get("exchange_fee_estimated"), 0.0) for row in rows),
            "exchange_fee_realized": sum(_safe_float(row.get("exchange_fee_realized"), 0.0) for row in rows),
            "spread_estimated": sum(_safe_float(row.get("spread_estimated"), 0.0) for row in rows),
            "spread_realized": sum(_safe_float(row.get("spread_realized"), 0.0) for row in rows),
            "slippage_estimated": sum(_safe_float(row.get("slippage_estimated"), 0.0) for row in rows),
            "slippage_realized": sum(_safe_float(row.get("slippage_realized"), 0.0) for row in rows),
            "funding_realized": sum(_safe_float(row.get("funding_realized"), 0.0) for row in rows),
            "borrow_interest_realized": sum(_safe_float(row.get("borrow_interest_realized"), 0.0) for row in rows),
            "rebates_or_discounts": sum(_safe_float(row.get("rebates_or_discounts"), 0.0) for row in rows),
            "gross_pnl": sum(_safe_float(row.get("gross_pnl"), 0.0) for row in rows),
            "net_pnl": sum(_safe_float(row.get("net_pnl"), 0.0) for row in rows),
            "total_cost_estimated": sum(_safe_float(row.get("total_cost_estimated"), 0.0) for row in rows),
            "total_cost_realized": sum(_safe_float(row.get("total_cost_realized"), 0.0) for row in rows),
        }
        effective_total = totals["total_cost_realized"] if totals["total_cost_realized"] > 0 else totals["total_cost_estimated"]
        totals["total_cost_pct_of_gross_pnl"] = _percent_of_gross(effective_total, totals["gross_pnl"])
        policy = self.cost_stack()
        alerts_cfg = policy.get("alerts") if isinstance(policy.get("alerts"), dict) else {}
        totals["alert_status"] = (
            "block"
            if totals["total_cost_pct_of_gross_pnl"] >= _safe_float(alerts_cfg.get("block_if_total_cost_pct_of_gross_pnl_gt"), 80.0)
            else "warn"
            if totals["total_cost_pct_of_gross_pnl"] >= _safe_float(alerts_cfg.get("warn_if_total_cost_pct_of_gross_pnl_gt"), 35.0)
            else "ok"
        )
        totals["policy_source"] = self.policy_source()
        totals["freshness_status"] = self._latest_cost_source_status(family=filters.get("family"))
        return totals

    def trades(self, *, limit: int = 200, offset: int = 0, **filters: Any) -> dict[str, Any]:
        rows = list(reversed(self._filtered_trade_rows(**filters)))
        limit_n = max(1, min(int(limit or 200), 1000))
        offset_n = max(0, int(offset or 0))
        sliced = rows[offset_n : offset_n + limit_n]
        return {
            "items": sliced,
            "count": len(rows),
            "limit": limit_n,
            "offset": offset_n,
            "policy_source": self.policy_source(),
        }

    def _top_groups(self, rows: list[dict[str, Any]], *, key_name: str) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            key = str(row.get(key_name) or "unknown").strip() or "unknown"
            grouped[key].append(row)
        items: list[dict[str, Any]] = []
        for key, group_rows in grouped.items():
            metrics = self._aggregate_rows(group_rows)
            items.append(
                {
                    key_name: key,
                    "trade_count": metrics["trade_count"],
                    "gross_pnl": metrics["gross_pnl"],
                    "net_pnl": metrics["net_pnl"],
                }
            )
        items.sort(key=lambda row: (_safe_float(row.get("net_pnl"), 0.0), int(row.get("trade_count") or 0)), reverse=True)
        return items[:10]

    def build_report_payload(self, **filters: Any) -> dict[str, Any]:
        rows = self._filtered_trade_rows(**filters)
        daily = self._series_by_bucket(rows, bucket="day")
        monthly = self._series_by_bucket(rows, bucket="month")
        summary = self.performance_summary(
            strategy_id=filters.get("strategy_id"),
            bot_id=filters.get("bot_id"),
            venue=filters.get("venue"),
            family=filters.get("family"),
            symbol=filters.get("symbol"),
        )
        breakdown = self.costs_breakdown(
            strategy_id=filters.get("strategy_id"),
            bot_id=filters.get("bot_id"),
            venue=filters.get("venue"),
            family=filters.get("family"),
            symbol=filters.get("symbol"),
        )
        period_start = rows[0]["executed_at"] if rows else None
        period_end = rows[-1]["executed_at"] if rows else None
        snapshot_ids = [
            str(row.get("snapshot_id") or "")
            for row in self.db.performance_snapshots()
            if str(row.get("family") or "") in {"all", str(filters.get("family") or "all")}
        ]
        return {
            "generated_at": utc_now_iso(),
            "period_start": period_start,
            "period_end": period_end,
            "summary": summary,
            "daily": daily,
            "monthly": monthly,
            "trades": list(reversed(rows)),
            "cost_breakdown": breakdown,
            "top_strategies": self._top_groups(rows, key_name="strategy_id"),
            "top_symbols": self._top_groups(rows, key_name="symbol"),
            "policy_source": self.policy_source(),
            "cost_source_bindings": self.db.cost_source_snapshots(),
            "source_snapshot_ids": snapshot_ids,
        }

    @staticmethod
    def _sheet_rows_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for period, payload in summary.items():
            if not isinstance(payload, dict):
                continue
            rows.append(
                {
                    "periodo": period,
                    "gross_pnl": payload.get("gross_pnl"),
                    "total_cost_estimated": payload.get("total_cost_estimated"),
                    "total_cost_realized": payload.get("total_cost_realized"),
                    "net_pnl": payload.get("net_pnl"),
                    "trade_count": payload.get("trade_count"),
                    "win_rate": payload.get("win_rate"),
                    "profit_factor": payload.get("profit_factor"),
                    "expectancy": payload.get("expectancy"),
                    "max_drawdown": payload.get("max_drawdown"),
                    "freshness_status": payload.get("freshness_status"),
                }
            )
        return rows

    @staticmethod
    def _sheet_rows_from_breakdown(breakdown: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"metric": key, "value": value} for key, value in breakdown.items() if key not in {"policy_source"}]

    @staticmethod
    def _xlsx_cell_ref(col_idx: int, row_idx: int) -> str:
        n = col_idx
        label = ""
        while n >= 0:
            n, rem = divmod(n, 26)
            label = chr(65 + rem) + label
            n -= 1
        return f"{label}{row_idx + 1}"

    @classmethod
    def _worksheet_xml(cls, rows: list[dict[str, Any]]) -> str:
        if not rows:
            headers = ["sin_datos"]
            matrix = [headers, [""]]
        else:
            headers = list(rows[0].keys())
            matrix = [headers]
            for row in rows:
                matrix.append([row.get(header) for header in headers])
        xml_rows: list[str] = []
        for row_idx, values in enumerate(matrix):
            cells: list[str] = []
            for col_idx, value in enumerate(values):
                ref = cls._xlsx_cell_ref(col_idx, row_idx)
                if isinstance(value, bool):
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(str(value))}</t></is></c>')
                elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{xml_escape(str(value or ""))}</t></is></c>')
            xml_rows.append(f'<row r="{row_idx + 1}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(xml_rows)}</sheetData>'
            "</worksheet>"
        )

    def _write_xlsx(self, path: Path, sheets: list[tuple[str, list[dict[str, Any]]]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        safe_sheets: list[tuple[str, list[dict[str, Any]]]] = []
        for idx, (name, rows) in enumerate(sheets, start=1):
            clean = str(name or f"Hoja{idx}")[:31]
            for char in "[]:*?/\\":  # Excel invalid chars.
                clean = clean.replace(char, "_")
            safe_sheets.append((clean or f"Hoja{idx}", rows))
        workbook_xml = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
            "<sheets>",
        ]
        workbook_rels = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        ]
        content_types = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        ]
        for idx, (name, _rows) in enumerate(safe_sheets, start=1):
            workbook_xml.append(f'<sheet name="{xml_escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>')
            workbook_rels.append(
                f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>'
            )
            content_types.append(
                f'<Override PartName="/xl/worksheets/sheet{idx}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
        workbook_xml.extend(["</sheets>", "</workbook>"])
        workbook_rels.append("</Relationships>")
        content_types.append("</Types>")
        rels_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        )
        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>"
        )
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "".join(content_types))
            archive.writestr("_rels/.rels", rels_xml)
            archive.writestr("xl/workbook.xml", "".join(workbook_xml))
            archive.writestr("xl/_rels/workbook.xml.rels", "".join(workbook_rels))
            archive.writestr("xl/styles.xml", styles_xml)
            for idx, (_name, rows) in enumerate(safe_sheets, start=1):
                archive.writestr(f"xl/worksheets/sheet{idx}.xml", self._worksheet_xml(rows))

    @staticmethod
    def _pdf_text(x: float, y: float, size: float, text: str) -> str:
        return f"BT /F1 {size} Tf {x:.2f} {y:.2f} Td ({_escape_pdf_text(text)}) Tj ET\n"

    @staticmethod
    def _pdf_rect(x: float, y: float, w: float, h: float) -> str:
        return f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re S\n"

    @staticmethod
    def _pdf_polyline(points: list[tuple[float, float]]) -> str:
        if len(points) < 2:
            return ""
        start_x, start_y = points[0]
        cmds = [f"{start_x:.2f} {start_y:.2f} m\n"]
        for x, y in points[1:]:
            cmds.append(f"{x:.2f} {y:.2f} l\n")
        cmds.append("S\n")
        return "".join(cmds)

    def _chart_points(self, series: list[dict[str, Any]], *, key: str, x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
        if not series:
            return []
        values = [_safe_float(row.get(key), 0.0) for row in series]
        min_v = min(values)
        max_v = max(values)
        if math.isclose(min_v, max_v):
            max_v = min_v + 1.0
        points: list[tuple[float, float]] = []
        for idx, value in enumerate(values):
            px = x + ((w / max(1, len(values) - 1)) * idx)
            py = y + (((value - min_v) / (max_v - min_v)) * h)
            points.append((px, py))
        return points

    def _write_pdf(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        all_time = summary.get("all_time") if isinstance(summary.get("all_time"), dict) else {}
        daily = payload.get("daily") if isinstance(payload.get("daily"), list) else []
        monthly = payload.get("monthly") if isinstance(payload.get("monthly"), list) else []
        breakdown = payload.get("cost_breakdown") if isinstance(payload.get("cost_breakdown"), dict) else {}
        top_strategies = payload.get("top_strategies") if isinstance(payload.get("top_strategies"), list) else []

        page1 = []
        page1.append(self._pdf_text(50, 790, 16, "RTLAB Reporte de Costos y Performance"))
        page1.append(self._pdf_text(50, 772, 10, f"Rango: {payload.get('period_start') or '-'} -> {payload.get('period_end') or '-'}"))
        page1.append(self._pdf_text(50, 756, 10, f"Generado: {payload.get('generated_at') or utc_now_iso()}"))
        card_y = 700
        cards = [
            ("PnL bruto", all_time.get("gross_pnl")),
            ("Costo estimado", all_time.get("total_cost_estimated")),
            ("Costo realizado", all_time.get("total_cost_realized")),
            ("PnL neto", all_time.get("net_pnl")),
            ("Trades", all_time.get("trade_count")),
        ]
        for idx, (label, value) in enumerate(cards):
            x = 50 + (idx % 2) * 250
            y = card_y - (idx // 2) * 60
            page1.append(self._pdf_rect(x, y, 220, 44))
            page1.append(self._pdf_text(x + 10, y + 26, 10, label))
            page1.append(self._pdf_text(x + 10, y + 10, 12, str(value if value is not None else "-")))
        page1.append(self._pdf_text(50, 565, 12, "Breakdown de costos"))
        current_y = 545
        breakdown_rows = [
            ("Fees estimados", breakdown.get("exchange_fee_estimated")),
            ("Fees realizados", breakdown.get("exchange_fee_realized")),
            ("Spread estimado", breakdown.get("spread_estimated")),
            ("Spread realizado", breakdown.get("spread_realized")),
            ("Slippage estimado", breakdown.get("slippage_estimated")),
            ("Slippage realizado", breakdown.get("slippage_realized")),
            ("Funding realizado", breakdown.get("funding_realized")),
            ("Borrow interest", breakdown.get("borrow_interest_realized")),
            ("Total cost % gross", breakdown.get("total_cost_pct_of_gross_pnl")),
        ]
        for label, value in breakdown_rows:
            page1.append(self._pdf_text(55, current_y, 10, label))
            page1.append(self._pdf_text(260, current_y, 10, str(value if value is not None else "-")))
            current_y -= 16
        page1.append(self._pdf_text(50, 380, 12, "Top estrategias"))
        current_y = 360
        for row in top_strategies[:5]:
            page1.append(
                self._pdf_text(
                    55,
                    current_y,
                    10,
                    f"{row.get('strategy_id') or 'unknown'} | trades {row.get('trade_count')} | net {row.get('net_pnl')}",
                )
            )
            current_y -= 16
        page1.append(self._pdf_text(50, 90, 8, f"Provenance snapshots: {', '.join(payload.get('source_snapshot_ids') or [])}"))

        page2 = []
        page2.append(self._pdf_text(50, 790, 14, "Charts diarios y mensuales"))
        page2.append(self._pdf_rect(50, 430, 500, 250))
        page2.append(self._pdf_text(55, 665, 10, "PnL diario"))
        page2.append(self._pdf_polyline(self._chart_points(daily[-60:], key="net_pnl", x=65, y=445, w=460, h=210)))
        page2.append(self._pdf_rect(50, 110, 500, 250))
        page2.append(self._pdf_text(55, 345, 10, "PnL mensual"))
        page2.append(self._pdf_polyline(self._chart_points(monthly[-24:], key="net_pnl", x=65, y=125, w=460, h=210)))

        pages = [("".join(page1), 595, 842), ("".join(page2), 595, 842)]
        objects: list[bytes] = []

        def add_object(content: str | bytes) -> int:
            raw = content.encode("latin-1") if isinstance(content, str) else content
            objects.append(raw)
            return len(objects)

        font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        page_ids: list[int] = []
        pages_placeholder = add_object("<< /Type /Pages /Kids [] /Count 0 >>")
        for content, width, height in pages:
            content_id = add_object(f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}endstream")
            page_id = add_object(
                f"<< /Type /Page /Parent {pages_placeholder} 0 R /MediaBox [0 0 {width} {height}] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            )
            page_ids.append(page_id)
        objects[pages_placeholder - 1] = (
            f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] /Count {len(page_ids)} >>".encode("latin-1")
        )
        catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_placeholder} 0 R >>")

        pdf = bytearray()
        pdf.extend(b"%PDF-1.4\n")
        offsets: list[int] = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(len(pdf))
            pdf.extend(f"{idx} 0 obj\n".encode("latin-1"))
            pdf.extend(obj)
            pdf.extend(b"\nendobj\n")
        xref_start = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        pdf.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        pdf.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode("latin-1")
        )
        path.write_bytes(bytes(pdf))

    def create_export(
        self,
        *,
        export_type: str,
        generated_by: str,
        report_scope: str = "full",
        **filters: Any,
    ) -> dict[str, Any]:
        export_type_n = str(export_type or "").strip().lower()
        if export_type_n not in {"xlsx", "pdf"}:
            raise ValueError("Solo se soportan exports xlsx/pdf en este bloque.")
        payload = self.build_report_payload(**filters)
        prefix = str((self.exports_policy().get("filenames") or {}).get("prefix") or "rtlab_report").strip() or "rtlab_report"
        export_id = f"EXP-{hashlib.sha256(f'{utc_now_iso()}:{export_type_n}:{generated_by}'.encode('utf-8')).hexdigest()[:16].upper()}"
        filename = f"{prefix}_{export_id}.{export_type_n}"
        artifact_path = self.exports_dir / filename
        if export_type_n == "xlsx":
            sheets = [
                ("Resumen", self._sheet_rows_from_summary(payload.get("summary") if isinstance(payload.get("summary"), dict) else {})),
                ("Diario", payload.get("daily") if isinstance(payload.get("daily"), list) else []),
                ("Mensual", payload.get("monthly") if isinstance(payload.get("monthly"), list) else []),
                ("Trades", payload.get("trades") if isinstance(payload.get("trades"), list) else []),
                ("Costos", self._sheet_rows_from_breakdown(payload.get("cost_breakdown") if isinstance(payload.get("cost_breakdown"), dict) else {})),
            ]
            self._write_xlsx(artifact_path, sheets)
        else:
            self._write_pdf(artifact_path, payload)

        manifest = {
            "export_id": export_id,
            "export_type": export_type_n,
            "report_scope": report_scope,
            "generated_at": utc_now_iso(),
            "generated_by": generated_by,
            "period_start": payload.get("period_start"),
            "period_end": payload.get("period_end"),
            "row_count": len(payload.get("trades") or []),
            "artifact_path": str(artifact_path),
            "source_snapshot_ids": payload.get("source_snapshot_ids") or [],
            "success": True,
            "error_message": None,
            "provenance": {
                "policy_source": self.policy_source(),
                "cost_source_bindings": payload.get("cost_source_bindings") or [],
            },
        }
        self.db.insert_export_manifest(manifest)
        return manifest

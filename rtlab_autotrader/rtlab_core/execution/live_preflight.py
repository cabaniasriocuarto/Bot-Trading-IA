from __future__ import annotations

import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


def _json_loads(payload: Any, default: Any) -> Any:
    if payload in {None, ""}:
        return copy.deepcopy(default)
    if isinstance(payload, (dict, list)):
        return copy.deepcopy(payload)
    try:
        return json.loads(str(payload))
    except Exception:
        return copy.deepcopy(default)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _canonical_symbol(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def _normalize_status(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in {"PASS", "WARN", "FAIL"} else "FAIL"


def _hydrate_run_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["blocking_reasons"] = _json_loads(out.get("blocking_reasons_json"), [])
    out["warnings"] = _json_loads(out.get("warnings_json"), [])
    out["checks"] = _json_loads(out.get("checks_json"), {})
    out["source_versions"] = _json_loads(out.get("source_versions_json"), {})
    out["diagnostics"] = _json_loads(out.get("diagnostics_json"), [])
    out["manual_attestations"] = _json_loads(out.get("manual_attestations_json"), {})
    out["runtime_context"] = _json_loads(out.get("runtime_context_json"), {})
    out["exchange_context"] = _json_loads(out.get("exchange_context_json"), {})
    out.pop("blocking_reasons_json", None)
    out.pop("warnings_json", None)
    out.pop("checks_json", None)
    out.pop("source_versions_json", None)
    out.pop("diagnostics_json", None)
    out.pop("manual_attestations_json", None)
    out.pop("runtime_context_json", None)
    out.pop("exchange_context_json", None)
    out["freshness_seconds"] = _safe_int(out.get("freshness_seconds"), 0)
    out["quantity"] = None if out.get("quantity") is None else _safe_float(out.get("quantity"))
    out["quote_order_qty"] = None if out.get("quote_order_qty") is None else _safe_float(out.get("quote_order_qty"))
    return out


def _hydrate_attestation_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    for key in (
        "manual_permissions_verified",
        "trade_enabled_verified",
        "withdraw_disabled_verified",
        "ip_restriction_verified",
    ):
        out[key] = _bool(out.get(key))
    return out


class LivePreflightDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS live_preflight_runs (
                  preflight_id TEXT PRIMARY KEY,
                  mode TEXT NOT NULL,
                  exchange TEXT NOT NULL,
                  market_type TEXT NOT NULL,
                  symbol TEXT,
                  side TEXT,
                  quantity REAL,
                  quote_order_qty REAL,
                  evaluated_at TEXT NOT NULL,
                  expires_at TEXT,
                  overall_status TEXT NOT NULL,
                  blocking_reasons_json TEXT NOT NULL DEFAULT '[]',
                  warnings_json TEXT NOT NULL DEFAULT '[]',
                  checks_json TEXT NOT NULL DEFAULT '{}',
                  source_versions_json TEXT NOT NULL DEFAULT '{}',
                  diagnostics_json TEXT NOT NULL DEFAULT '[]',
                  manual_attestations_json TEXT NOT NULL DEFAULT '{}',
                  freshness_seconds INTEGER NOT NULL DEFAULT 0,
                  runtime_context_json TEXT NOT NULL DEFAULT '{}',
                  exchange_context_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_live_preflight_runs_mode_eval
                  ON live_preflight_runs(mode, evaluated_at DESC);

                CREATE TABLE IF NOT EXISTS live_preflight_attestations (
                  attestation_id TEXT PRIMARY KEY,
                  mode TEXT NOT NULL,
                  exchange TEXT NOT NULL,
                  market_type TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  verified_by TEXT NOT NULL,
                  verified_at TEXT NOT NULL,
                  note TEXT,
                  manual_permissions_verified INTEGER NOT NULL DEFAULT 0,
                  trade_enabled_verified INTEGER NOT NULL DEFAULT 0,
                  withdraw_disabled_verified INTEGER NOT NULL DEFAULT 0,
                  ip_restriction_verified INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_live_preflight_attestations_mode_created
                  ON live_preflight_attestations(mode, created_at DESC);
                """
            )

    def insert_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "preflight_id": str(payload.get("preflight_id") or uuid4()),
            "mode": str(payload.get("mode") or "live"),
            "exchange": str(payload.get("exchange") or "binance"),
            "market_type": str(payload.get("market_type") or "spot"),
            "symbol": _canonical_symbol(payload.get("symbol")),
            "side": str(payload.get("side") or "BUY").upper(),
            "quantity": None if payload.get("quantity") is None else _safe_float(payload.get("quantity")),
            "quote_order_qty": None if payload.get("quote_order_qty") is None else _safe_float(payload.get("quote_order_qty")),
            "evaluated_at": str(payload.get("evaluated_at") or utc_now_iso()),
            "expires_at": str(payload.get("expires_at") or "") or None,
            "overall_status": _normalize_status(payload.get("overall_status")),
            "blocking_reasons_json": _json_dumps(payload.get("blocking_reasons") or []),
            "warnings_json": _json_dumps(payload.get("warnings") or []),
            "checks_json": _json_dumps(payload.get("checks") or {}),
            "source_versions_json": _json_dumps(payload.get("source_versions") or {}),
            "diagnostics_json": _json_dumps(payload.get("diagnostics") or []),
            "manual_attestations_json": _json_dumps(payload.get("manual_attestations") or {}),
            "freshness_seconds": _safe_int(payload.get("freshness_seconds"), 0),
            "runtime_context_json": _json_dumps(payload.get("runtime_context") or {}),
            "exchange_context_json": _json_dumps(payload.get("exchange_context") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO live_preflight_runs (
                  preflight_id, mode, exchange, market_type, symbol, side, quantity, quote_order_qty,
                  evaluated_at, expires_at, overall_status, blocking_reasons_json, warnings_json,
                  checks_json, source_versions_json, diagnostics_json, manual_attestations_json,
                  freshness_seconds, runtime_context_json, exchange_context_json
                ) VALUES (
                  :preflight_id, :mode, :exchange, :market_type, :symbol, :side, :quantity, :quote_order_qty,
                  :evaluated_at, :expires_at, :overall_status, :blocking_reasons_json, :warnings_json,
                  :checks_json, :source_versions_json, :diagnostics_json, :manual_attestations_json,
                  :freshness_seconds, :runtime_context_json, :exchange_context_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM live_preflight_runs WHERE preflight_id = ?",
                (row["preflight_id"],),
            ).fetchone()
        return _hydrate_run_row(dict(stored) if stored is not None else row) or row

    def list_runs(self, *, mode: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if mode:
            clauses.append("mode = ?")
            params.append(str(mode))
        params.append(max(1, int(limit)))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM live_preflight_runs
                WHERE {' AND '.join(clauses)}
                ORDER BY evaluated_at DESC, preflight_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_hydrate_run_row(dict(row)) or {} for row in rows]

    def latest_run(self, *, mode: str | None = None) -> dict[str, Any] | None:
        items = self.list_runs(mode=mode, limit=1)
        return items[0] if items else None

    def insert_attestation(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "attestation_id": str(payload.get("attestation_id") or uuid4()),
            "mode": str(payload.get("mode") or "live"),
            "exchange": str(payload.get("exchange") or "binance"),
            "market_type": str(payload.get("market_type") or "spot"),
            "created_at": str(payload.get("created_at") or utc_now_iso()),
            "verified_by": str(payload.get("verified_by") or "unknown"),
            "verified_at": str(payload.get("verified_at") or payload.get("created_at") or utc_now_iso()),
            "note": str(payload.get("note") or ""),
            "manual_permissions_verified": 1 if _bool(payload.get("manual_permissions_verified")) else 0,
            "trade_enabled_verified": 1 if _bool(payload.get("trade_enabled_verified")) else 0,
            "withdraw_disabled_verified": 1 if _bool(payload.get("withdraw_disabled_verified")) else 0,
            "ip_restriction_verified": 1 if _bool(payload.get("ip_restriction_verified")) else 0,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO live_preflight_attestations (
                  attestation_id, mode, exchange, market_type, created_at, verified_by, verified_at, note,
                  manual_permissions_verified, trade_enabled_verified, withdraw_disabled_verified, ip_restriction_verified
                ) VALUES (
                  :attestation_id, :mode, :exchange, :market_type, :created_at, :verified_by, :verified_at, :note,
                  :manual_permissions_verified, :trade_enabled_verified, :withdraw_disabled_verified, :ip_restriction_verified
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM live_preflight_attestations WHERE attestation_id = ?",
                (row["attestation_id"],),
            ).fetchone()
        return _hydrate_attestation_row(dict(stored) if stored is not None else row) or row

    def latest_attestation(self, *, mode: str | None = None) -> dict[str, Any] | None:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if mode:
            clauses.append("mode = ?")
            params.append(str(mode))
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM live_preflight_attestations
                WHERE {' AND '.join(clauses)}
                ORDER BY verified_at DESC, attestation_id DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return _hydrate_attestation_row(dict(row) if row is not None else None)


def attestation_status(
    attestation: dict[str, Any] | None,
    *,
    max_age_days: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if attestation is None:
        return {
            "status": "FAIL",
            "reason": "manual_attestation_missing",
            "age_days": None,
            "expires_at": None,
            "verified_at": None,
        }
    verified_at_raw = str(attestation.get("verified_at") or attestation.get("created_at") or "").strip()
    try:
        verified_dt = datetime.fromisoformat(verified_at_raw.replace("Z", "+00:00"))
        if verified_dt.tzinfo is None:
            verified_dt = verified_dt.replace(tzinfo=timezone.utc)
        verified_dt = verified_dt.astimezone(timezone.utc)
    except Exception:
        return {
            "status": "FAIL",
            "reason": "manual_attestation_invalid_timestamp",
            "age_days": None,
            "expires_at": None,
            "verified_at": verified_at_raw or None,
        }
    age_days = max(0.0, (current - verified_dt).total_seconds() / 86400.0)
    expires_at = (verified_dt + timedelta(days=max(1, int(max_age_days)))).isoformat()
    attestation_ok = all(
        (
            _bool(attestation.get("manual_permissions_verified")),
            _bool(attestation.get("trade_enabled_verified")),
            _bool(attestation.get("withdraw_disabled_verified")),
            _bool(attestation.get("ip_restriction_verified")),
        )
    )
    if not attestation_ok:
        return {
            "status": "FAIL",
            "reason": "manual_attestation_incomplete",
            "age_days": round(age_days, 3),
            "expires_at": expires_at,
            "verified_at": verified_dt.isoformat(),
        }
    if age_days > float(max(1, int(max_age_days))):
        return {
            "status": "FAIL",
            "reason": "manual_attestation_expired",
            "age_days": round(age_days, 3),
            "expires_at": expires_at,
            "verified_at": verified_dt.isoformat(),
        }
    return {
        "status": "PASS",
        "reason": "manual_attestation_valid",
        "age_days": round(age_days, 3),
        "expires_at": expires_at,
        "verified_at": verified_dt.isoformat(),
    }

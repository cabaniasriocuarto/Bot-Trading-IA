from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from rtlab_core.domains.common import utc_now_iso


class BotDecisionLogRepository:
    def __init__(
        self,
        *,
        db_path: Path,
        schema_sql: str,
        backfill_max_rows: int,
        integrity_window_hours: int,
        unknown_ratio_warn: float,
        unknown_min_events: int,
    ) -> None:
        self.path = Path(db_path)
        self.schema_sql = schema_sql
        self.backfill_max_rows = int(backfill_max_rows)
        self.integrity_window_hours = int(integrity_window_hours)
        self.unknown_ratio_warn = float(unknown_ratio_warn)
        self.unknown_min_events = int(unknown_min_events)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self, *, include_backfill: bool = True) -> None:
        with self._connect() as conn:
            conn.executescript(self.schema_sql)
            self._ensure_migrations(conn)
            if include_backfill:
                self._run_backfills(conn)
            conn.commit()

    def _ensure_migrations(self, conn: sqlite3.Connection) -> None:
        columns = {str(row["name"] or "").strip() for row in conn.execute("PRAGMA table_info(logs)").fetchall()}
        if "has_bot_ref" not in columns:
            conn.execute("ALTER TABLE logs ADD COLUMN has_bot_ref INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_has_bot_ref_id ON logs(has_bot_ref, id DESC)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS log_bot_refs (
                log_id INTEGER NOT NULL,
                bot_id TEXT NOT NULL,
                PRIMARY KEY (log_id, bot_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_log_bot_refs_bot_id_log_id ON log_bot_refs(bot_id, log_id DESC)")
    def _run_backfills(self, conn: sqlite3.Connection) -> None:
        self._backfill_logs_has_bot_ref(conn)
        self._backfill_log_bot_refs(conn)
        self._backfill_breaker_events_from_logs(conn)

    def backfill_runtime_indexes(self) -> None:
        with self._connect() as conn:
            self._run_backfills(conn)
            conn.commit()

    def _backfill_logs_has_bot_ref(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT MAX(id) AS max_id FROM logs").fetchone()
        max_id = int((row["max_id"] if row is not None else 0) or 0)
        if max_id <= 0:
            return
        min_id = max(1, max_id - self.backfill_max_rows + 1)
        conn.execute(
            """
            UPDATE logs
            SET has_bot_ref = 1
            WHERE id >= ?
              AND has_bot_ref = 0
              AND (
                  related_ids LIKE '%BOT-%'
                  OR payload_json LIKE '%"bot_id"%'
              )
            """,
            (min_id,),
        )

    def _backfill_log_bot_refs(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT MAX(id) AS max_id FROM logs").fetchone()
        max_id = int((row["max_id"] if row is not None else 0) or 0)
        if max_id <= 0:
            return
        min_id = max(1, max_id - self.backfill_max_rows + 1)
        rows = conn.execute(
            """
            SELECT id, related_ids, payload_json
            FROM logs
            WHERE id >= ?
              AND id NOT IN (SELECT log_id FROM log_bot_refs)
            ORDER BY id DESC
            LIMIT ?
            """,
            (min_id, self.backfill_max_rows),
        ).fetchall()
        inserts: list[tuple[int, str]] = []
        for row in rows:
            related_raw = row["related_ids"] if row["related_ids"] is not None else "[]"
            payload_raw = row["payload_json"] if row["payload_json"] is not None else "{}"
            try:
                related_ids = json.loads(related_raw)
            except Exception:
                related_ids = []
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {}
            refs = self._extract_bot_refs_from_log(
                related_ids if isinstance(related_ids, list) else [],
                payload if isinstance(payload, dict) else {},
            )
            if not refs:
                continue
            log_id = int(row["id"])
            for bot_id in refs:
                inserts.append((log_id, bot_id))
        if inserts:
            conn.executemany(
                "INSERT OR IGNORE INTO log_bot_refs (log_id, bot_id) VALUES (?, ?)",
                inserts,
            )

    @staticmethod
    def _normalize_log_bot_ref(value: Any) -> str:
        ref = str(value or "").strip()
        if not ref:
            return ""
        return ref.upper() if ref.upper().startswith("BOT-") else ref

    @classmethod
    def _extract_bot_refs_from_log(cls, related_ids: list[str], payload: dict[str, Any]) -> set[str]:
        refs: set[str] = set()
        payload_map = payload if isinstance(payload, dict) else {}
        bot_id = cls._normalize_log_bot_ref(payload_map.get("bot_id"))
        if bot_id:
            refs.add(bot_id)
        bot_ids = payload_map.get("bot_ids")
        if isinstance(bot_ids, list):
            for item in bot_ids:
                item_id = cls._normalize_log_bot_ref(item)
                if item_id:
                    refs.add(item_id)
        if isinstance(related_ids, list):
            for rid in related_ids:
                item_id = cls._normalize_log_bot_ref(rid)
                if item_id and item_id.upper().startswith("BOT-"):
                    refs.add(item_id)
        return refs

    @classmethod
    def log_has_bot_ref(cls, related_ids: list[str], payload: dict[str, Any]) -> bool:
        return bool(cls._extract_bot_refs_from_log(related_ids, payload))

    @staticmethod
    def _normalize_breaker_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"shadow", "paper", "testnet", "live"}:
            return mode
        return "unknown"

    @staticmethod
    def _normalize_breaker_bot_id(value: str | None) -> str:
        bot_id = str(value or "").strip()
        return bot_id if bot_id else "unknown_bot"

    def _insert_breaker_event(
        self,
        conn: sqlite3.Connection,
        *,
        ts: str,
        bot_id: str | None,
        mode: str | None,
        reason: str | None,
        run_id: str | None = None,
        symbol: str | None = None,
        source_log_id: int | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO breaker_events (ts, bot_id, mode, reason, run_id, symbol, source_log_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ts or utc_now_iso()),
                self._normalize_breaker_bot_id(bot_id),
                self._normalize_breaker_mode(mode),
                str(reason or "breaker_triggered"),
                str(run_id).strip() if run_id is not None and str(run_id).strip() else None,
                str(symbol).strip().upper() if symbol is not None and str(symbol).strip() else None,
                int(source_log_id) if source_log_id is not None else None,
            ),
        )

    def _backfill_breaker_events_from_logs(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT id, ts, message, payload_json
            FROM logs
            WHERE type = 'breaker_triggered'
              AND id NOT IN (
                  SELECT source_log_id
                  FROM breaker_events
                  WHERE source_log_id IS NOT NULL
              )
            ORDER BY id ASC
            """
        ).fetchall()
        for row in rows:
            payload_raw = row["payload_json"] if row["payload_json"] is not None else "{}"
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {}
            payload_map = payload if isinstance(payload, dict) else {}
            self._insert_breaker_event(
                conn,
                ts=str(row["ts"] or utc_now_iso()),
                bot_id=str(payload_map.get("bot_id") or ""),
                mode=str(payload_map.get("mode") or ""),
                reason=str(payload_map.get("reason") or row["message"] or "breaker_triggered"),
                run_id=str(payload_map.get("run_id") or ""),
                symbol=str(payload_map.get("symbol") or ""),
                source_log_id=int(row["id"]),
            )

    def breaker_events_integrity(self, *, window_hours: int | None = None, strict: bool = True) -> dict[str, Any]:
        from datetime import datetime, timedelta, timezone

        def utc_now() -> datetime:
            return datetime.now(timezone.utc)

        window_h = max(1, int(window_hours or self.integrity_window_hours))
        since = (utc_now() - timedelta(hours=window_h)).isoformat()
        strict_mode = bool(strict)

        def _query_counts(conn: sqlite3.Connection, *, since_ts: str | None = None) -> dict[str, Any]:
            where_sql = "WHERE ts >= ?" if since_ts else ""
            params: tuple[Any, ...] = (since_ts,) if since_ts else ()
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN bot_id='unknown_bot' THEN 1 ELSE 0 END) AS unknown_bot_total,
                    SUM(CASE WHEN mode='unknown' THEN 1 ELSE 0 END) AS unknown_mode_total,
                    SUM(CASE WHEN bot_id='unknown_bot' OR mode='unknown' THEN 1 ELSE 0 END) AS unknown_any_total
                FROM breaker_events
                {where_sql}
                """,
                params,
            ).fetchone()
            mode_rows = conn.execute(
                f"""
                SELECT mode, COUNT(*) AS n
                FROM breaker_events
                {where_sql}
                GROUP BY mode
                """,
                params,
            ).fetchall()
            total = int((row["total"] if row is not None else 0) or 0)
            unknown_bot_total = int((row["unknown_bot_total"] if row is not None else 0) or 0)
            unknown_mode_total = int((row["unknown_mode_total"] if row is not None else 0) or 0)
            unknown_any_total = int((row["unknown_any_total"] if row is not None else 0) or 0)
            mode_counts = {str(r["mode"] or "unknown"): int(r["n"] or 0) for r in mode_rows}
            return {
                "total": total,
                "unknown_bot_total": unknown_bot_total,
                "unknown_mode_total": unknown_mode_total,
                "unknown_any_total": unknown_any_total,
                "unknown_bot_ratio": round((unknown_bot_total / total), 6) if total else 0.0,
                "unknown_mode_ratio": round((unknown_mode_total / total), 6) if total else 0.0,
                "unknown_any_ratio": round((unknown_any_total / total), 6) if total else 0.0,
                "mode_counts": mode_counts,
            }

        with self._connect() as conn:
            overall = _query_counts(conn)
            window = _query_counts(conn, since_ts=since)

        warnings: list[str] = []

        def _warn_if_high_unknown(scope_name: str, payload: dict[str, Any]) -> None:
            if int(payload.get("total") or 0) < self.unknown_min_events:
                return
            if float(payload.get("unknown_any_ratio") or 0.0) > self.unknown_ratio_warn:
                warnings.append(
                    f"{scope_name}: unknown_any_ratio={payload.get('unknown_any_ratio')} "
                    f"supera umbral={round(self.unknown_ratio_warn, 6)} con total={payload.get('total')}"
                )

        _warn_if_high_unknown("overall", overall)
        _warn_if_high_unknown(f"window_{window_h}h", window)

        if int(overall.get("total") or 0) == 0:
            status = "NO_DATA"
        elif warnings:
            status = "WARN"
        else:
            status = "PASS"

        return {
            "status": status,
            "ok": status == "PASS" if strict_mode else status != "WARN",
            "strict_mode": strict_mode,
            "generated_at": utc_now_iso(),
            "window_hours": window_h,
            "thresholds": {
                "unknown_ratio_warn": round(self.unknown_ratio_warn, 6),
                "min_events_warn": self.unknown_min_events,
            },
            "overall": overall,
            "window": window,
            "warnings": warnings,
        }

    def add_log(
        self,
        event_type: str,
        severity: str,
        module: str,
        message: str,
        related_ids: list[str],
        payload: dict[str, Any],
    ) -> int:
        with self._connect() as conn:
            ts_now = utc_now_iso()
            event_type_norm = str(event_type or "").strip().lower()
            related_ids_list = related_ids if isinstance(related_ids, list) else []
            payload_map = payload if isinstance(payload, dict) else {}
            has_bot_ref = 1 if self.log_has_bot_ref(related_ids_list, payload_map) else 0
            cursor = conn.execute(
                """
                INSERT INTO logs (ts, type, severity, module, message, related_ids, payload_json, has_bot_ref)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_now,
                    event_type,
                    severity,
                    module,
                    message,
                    json.dumps(related_ids_list),
                    json.dumps(payload_map),
                    has_bot_ref,
                ),
            )
            if has_bot_ref:
                bot_refs = self._extract_bot_refs_from_log(related_ids_list, payload_map)
                if bot_refs:
                    conn.executemany(
                        "INSERT OR IGNORE INTO log_bot_refs (log_id, bot_id) VALUES (?, ?)",
                        [(int(cursor.lastrowid), bot_id) for bot_id in bot_refs],
                    )
            if event_type_norm == "breaker_triggered":
                self._insert_breaker_event(
                    conn,
                    ts=ts_now,
                    bot_id=str(payload_map.get("bot_id") or ""),
                    mode=str(payload_map.get("mode") or ""),
                    reason=str(payload_map.get("reason") or message or "breaker_triggered"),
                    run_id=str(payload_map.get("run_id") or ""),
                    symbol=str(payload_map.get("symbol") or ""),
                    source_log_id=int(cursor.lastrowid),
                )
            conn.commit()
            return int(cursor.lastrowid)

    def logs_since(self, min_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM logs WHERE id > ? ORDER BY id ASC",
                (min_id,),
            ).fetchall()
        return [self.log_row_to_dict(row) for row in rows]

    def list_logs(
        self,
        *,
        severity: str | None,
        module: str | None,
        since: str | None,
        until: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        clauses = []
        params: list[Any] = []
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if module:
            clauses.append("module = ?")
            params.append(module)
        if since:
            clauses.append("ts >= ?")
            params.append(since)
        if until:
            clauses.append("ts <= ?")
            params.append(until)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        offset = (max(page, 1) - 1) * max(page_size, 1)
        with self._connect() as conn:
            total_row = conn.execute(f"SELECT COUNT(*) AS n FROM logs {where_sql}", tuple(params)).fetchone()
            rows = conn.execute(
                f"SELECT * FROM logs {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
                tuple(params + [page_size, offset]),
            ).fetchall()
        return {
            "items": [self.log_row_to_dict(row) for row in rows],
            "total": int(total_row["n"]) if total_row else 0,
            "page": page,
            "page_size": page_size,
        }

    @staticmethod
    def log_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": f"log_{row['id']}",
            "numeric_id": int(row["id"]),
            "ts": row["ts"],
            "type": row["type"],
            "severity": row["severity"],
            "module": row["module"],
            "message": row["message"],
            "related_ids": json.loads(row["related_ids"]),
            "payload": json.loads(row["payload_json"]),
        }

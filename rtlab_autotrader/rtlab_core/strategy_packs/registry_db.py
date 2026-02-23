from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name, version)
);

CREATE TABLE IF NOT EXISTS backtests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    timerange TEXT NOT NULL,
    exchange TEXT NOT NULL,
    pairs TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    artifacts_path TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(strategy_id) REFERENCES strategies(id)
);

CREATE TABLE IF NOT EXISTS principals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_id INTEGER NOT NULL,
    mode TEXT NOT NULL,
    activated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(strategy_id) REFERENCES strategies(id)
);

CREATE TABLE IF NOT EXISTS strategy_registry (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    enabled_for_trading INTEGER NOT NULL DEFAULT 1,
    allow_learning INTEGER NOT NULL DEFAULT 1,
    is_primary INTEGER NOT NULL DEFAULT 0,
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_provenance (
    run_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    ts_from TEXT,
    ts_to TEXT,
    dataset_source TEXT,
    dataset_hash TEXT,
    costs_json TEXT NOT NULL DEFAULT '{}',
    commit_hash TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class RegistryDB:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)
            conn.commit()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        self._ensure_column(conn, "strategy_registry", "enabled_for_trading", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(conn, "strategy_registry", "allow_learning", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(conn, "strategy_registry", "is_primary", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "strategy_registry", "tags_json", "TEXT NOT NULL DEFAULT '[]'")
        self._ensure_column(conn, "strategy_registry", "created_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        self._ensure_column(conn, "strategy_registry", "updated_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        self._ensure_column(conn, "run_provenance", "costs_json", "TEXT NOT NULL DEFAULT '{}'")

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not rows:
            return
        names = {str(row["name"]) if isinstance(row, sqlite3.Row) else str(row[1]) for row in rows}
        if column in names:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def upsert_strategy(
        self,
        name: str,
        version: str,
        path: str,
        sha256: str,
        status: str = "draft",
        notes: str | None = None,
    ) -> int:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategies (name, version, path, sha256, status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, version) DO UPDATE SET
                    path=excluded.path,
                    sha256=excluded.sha256,
                    status=excluded.status,
                    notes=excluded.notes
                """,
                (name, version, path, sha256, status, notes),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id FROM strategies WHERE name=? AND version=?",
                (name, version),
            ).fetchone()
            return int(row["id"])

    def set_status(self, strategy_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE strategies SET status=? WHERE id=?", (status, strategy_id))
            conn.commit()

    def list_strategies(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, version, path, status, created_at FROM strategies ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_strategy_by_name(self, name: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM strategies WHERE name=? ORDER BY created_at DESC LIMIT 1",
                (name,),
            ).fetchone()
        return dict(row) if row else None

    def add_backtest(
        self,
        strategy_id: int,
        timerange: str,
        exchange: str,
        pairs: list[str],
        metrics: dict[str, Any],
        artifacts_path: str,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO backtests (strategy_id, timerange, exchange, pairs, metrics_json, artifacts_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (strategy_id, timerange, exchange, ",".join(pairs), json.dumps(metrics), artifacts_path),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_latest_backtest(self, strategy_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM backtests WHERE strategy_id=? ORDER BY created_at DESC LIMIT 1",
                (strategy_id,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metrics_json"] = json.loads(item["metrics_json"])
        return item

    def list_backtests(self, timerange: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM backtests"
        params: tuple[Any, ...] = ()
        if timerange:
            query += " WHERE timerange=?"
            params = (timerange,)
        query += " ORDER BY created_at DESC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["metrics_json"] = json.loads(item["metrics_json"])
            out.append(item)
        return out

    def set_principal(self, strategy_id: int, mode: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM principals WHERE mode=?", (mode,))
            conn.execute("INSERT INTO principals (strategy_id, mode) VALUES (?, ?)", (strategy_id, mode))
            conn.execute("UPDATE strategies SET status='principal' WHERE id=?", (strategy_id,))
            conn.commit()

    def get_principal(self, mode: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT p.id, p.mode, p.activated_at, s.id AS strategy_id, s.name, s.version, s.path
                FROM principals p
                JOIN strategies s ON s.id = p.strategy_id
                WHERE p.mode=?
                ORDER BY p.activated_at DESC
                LIMIT 1
                """,
                (mode,),
            ).fetchone()
        return dict(row) if row else None

    def principals(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT p.mode, p.activated_at, s.name, s.version
                FROM principals p
                JOIN strategies s ON s.id = p.strategy_id
                ORDER BY p.activated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_strategy_registry(
        self,
        *,
        strategy_key: str,
        name: str,
        version: str,
        source: str,
        status: str,
        enabled_for_trading: bool,
        allow_learning: bool,
        is_primary: bool,
        tags: list[str] | None = None,
    ) -> None:
        tags_json = json.dumps(tags or [])
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_registry (
                    id, name, version, source, status, enabled_for_trading, allow_learning, is_primary, tags_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    version=excluded.version,
                    source=excluded.source,
                    status=excluded.status,
                    enabled_for_trading=excluded.enabled_for_trading,
                    allow_learning=excluded.allow_learning,
                    is_primary=excluded.is_primary,
                    tags_json=excluded.tags_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    strategy_key,
                    name,
                    version,
                    source,
                    status,
                    1 if enabled_for_trading else 0,
                    1 if allow_learning else 0,
                    1 if is_primary else 0,
                    tags_json,
                ),
            )
            if is_primary:
                conn.execute("UPDATE strategy_registry SET is_primary=0 WHERE id<>?", (strategy_key,))
                conn.execute("UPDATE strategy_registry SET is_primary=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (strategy_key,))
            conn.commit()

    def get_strategy_registry(self, strategy_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM strategy_registry WHERE id=?", (strategy_key,)).fetchone()
        if not row:
            return None
        return self._strategy_registry_row(row)

    def list_strategy_registry(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM strategy_registry
                ORDER BY is_primary DESC, enabled_for_trading DESC, updated_at DESC, id ASC
                """
            ).fetchall()
        return [self._strategy_registry_row(row) for row in rows]

    def patch_strategy_registry(
        self,
        strategy_key: str,
        *,
        status: str | None = None,
        enabled_for_trading: bool | None = None,
        allow_learning: bool | None = None,
        is_primary: bool | None = None,
    ) -> dict[str, Any] | None:
        row = self.get_strategy_registry(strategy_key)
        if not row:
            return None
        next_status = row["status"] if status is None else status
        next_enabled = row["enabled_for_trading"] if enabled_for_trading is None else bool(enabled_for_trading)
        next_allow_learning = row["allow_learning"] if allow_learning is None else bool(allow_learning)
        next_is_primary = row["is_primary"] if is_primary is None else bool(is_primary)
        if next_status == "archived":
            next_enabled = False
            next_allow_learning = False
            next_is_primary = False
        if not next_enabled:
            next_is_primary = False
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE strategy_registry
                SET status=?, enabled_for_trading=?, allow_learning=?, is_primary=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (next_status, 1 if next_enabled else 0, 1 if next_allow_learning else 0, 1 if next_is_primary else 0, strategy_key),
            )
            if next_is_primary:
                conn.execute("UPDATE strategy_registry SET is_primary=0, updated_at=CURRENT_TIMESTAMP WHERE id<>?", (strategy_key,))
                conn.execute("UPDATE strategy_registry SET is_primary=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (strategy_key,))
            conn.commit()
        return self.get_strategy_registry(strategy_key)

    def enabled_for_trading_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS n FROM strategy_registry WHERE enabled_for_trading=1 AND status <> 'archived'"
            ).fetchone()
        return int(row["n"] if row else 0)

    def allow_learning_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(1) AS n FROM strategy_registry WHERE allow_learning=1 AND status <> 'archived'"
            ).fetchone()
        return int(row["n"] if row else 0)

    def ensure_registry_primary(self) -> None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM strategy_registry
                WHERE is_primary=1 AND enabled_for_trading=1 AND status <> 'archived'
                LIMIT 1
                """
            ).fetchone()
            if row:
                return
            # Clear stale/invalid primary flags (archived/disabled).
            conn.execute("UPDATE strategy_registry SET is_primary=0 WHERE is_primary=1")
            first = conn.execute(
                """
                SELECT id FROM strategy_registry
                WHERE enabled_for_trading=1 AND status <> 'archived'
                ORDER BY updated_at DESC, id ASC
                LIMIT 1
                """
            ).fetchone()
            if first:
                conn.execute("UPDATE strategy_registry SET is_primary=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (first["id"],))
                conn.commit()

    def upsert_run_provenance(
        self,
        *,
        run_id: str,
        strategy_id: str,
        mode: str,
        ts_from: str | None,
        ts_to: str | None,
        dataset_source: str | None,
        dataset_hash: str | None,
        costs_used: dict[str, Any],
        commit_hash: str | None,
        created_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_provenance (
                    run_id, strategy_id, mode, ts_from, ts_to, dataset_source, dataset_hash, costs_json, commit_hash, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(run_id) DO UPDATE SET
                    strategy_id=excluded.strategy_id,
                    mode=excluded.mode,
                    ts_from=excluded.ts_from,
                    ts_to=excluded.ts_to,
                    dataset_source=excluded.dataset_source,
                    dataset_hash=excluded.dataset_hash,
                    costs_json=excluded.costs_json,
                    commit_hash=excluded.commit_hash,
                    created_at=COALESCE(excluded.created_at, run_provenance.created_at)
                """,
                (
                    run_id,
                    strategy_id,
                    mode,
                    ts_from,
                    ts_to,
                    dataset_source,
                    dataset_hash,
                    json.dumps(costs_used or {}),
                    commit_hash,
                    created_at,
                ),
            )
            conn.commit()

    def list_run_provenance(self, strategy_id: str | None = None, mode: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM run_provenance WHERE 1=1"
        params: list[Any] = []
        if strategy_id:
            query += " AND strategy_id=?"
            params.append(strategy_id)
        if mode:
            query += " AND mode=?"
            params.append(mode)
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["costs_used"] = json.loads(item.pop("costs_json", "{}") or "{}")
            except Exception:
                item["costs_used"] = {}
            out.append(item)
        return out

    def _strategy_registry_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["tags"] = json.loads(item.pop("tags_json", "[]") or "[]")
        except Exception:
            item["tags"] = []
        item["enabled_for_trading"] = bool(item.get("enabled_for_trading"))
        item["allow_learning"] = bool(item.get("allow_learning"))
        item["is_primary"] = bool(item.get("is_primary"))
        return item

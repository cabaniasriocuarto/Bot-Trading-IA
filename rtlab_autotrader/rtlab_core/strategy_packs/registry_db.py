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
            conn.commit()

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

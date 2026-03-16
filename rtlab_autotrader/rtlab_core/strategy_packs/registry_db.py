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

CREATE TABLE IF NOT EXISTS experience_episode (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('backtest', 'shadow', 'paper', 'testnet')),
    source_weight REAL NOT NULL DEFAULT 1.0,
    strategy_id TEXT NOT NULL,
    bot_id TEXT,
    asset TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    start_ts TEXT,
    end_ts TEXT,
    dataset_source TEXT,
    dataset_hash TEXT,
    commit_hash TEXT,
    costs_profile_id TEXT,
    validation_quality TEXT NOT NULL DEFAULT 'unknown',
    cost_fidelity_level TEXT NOT NULL DEFAULT 'standard',
    feature_set TEXT NOT NULL DEFAULT 'unknown',
    notes TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, source, strategy_id, asset, timeframe, dataset_hash)
);

CREATE INDEX IF NOT EXISTS idx_experience_episode_strategy_source
ON experience_episode(strategy_id, source, asset, timeframe, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_experience_episode_bot_source
ON experience_episode(bot_id, source, asset, timeframe, created_at DESC);

CREATE TABLE IF NOT EXISTS experience_event (
    id TEXT PRIMARY KEY,
    episode_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    regime_label TEXT NOT NULL CHECK (regime_label IN ('trend', 'range', 'high_vol', 'toxic', 'unknown')),
    features_json TEXT NOT NULL DEFAULT '{}',
    action TEXT NOT NULL CHECK (action IN ('enter', 'exit', 'hold', 'reduce', 'add', 'skip')),
    side TEXT NOT NULL CHECK (side IN ('long', 'short', 'flat')),
    predicted_edge REAL,
    realized_pnl_gross REAL,
    realized_pnl_net REAL,
    fee REAL NOT NULL DEFAULT 0,
    spread_cost REAL NOT NULL DEFAULT 0,
    slippage_cost REAL NOT NULL DEFAULT 0,
    funding_cost REAL NOT NULL DEFAULT 0,
    latency_ms REAL,
    spread_bps REAL,
    vpin_value REAL,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(episode_id) REFERENCES experience_episode(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_experience_event_episode_ts
ON experience_event(episode_id, ts ASC);

CREATE INDEX IF NOT EXISTS idx_experience_event_regime_action
ON experience_event(regime_label, action, ts DESC);

CREATE TABLE IF NOT EXISTS regime_kpi (
    strategy_id TEXT NOT NULL,
    asset TEXT NOT NULL DEFAULT '',
    timeframe TEXT NOT NULL DEFAULT '',
    regime_label TEXT NOT NULL CHECK (regime_label IN ('trend', 'range', 'high_vol', 'toxic', 'unknown')),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    n_trades INTEGER NOT NULL DEFAULT 0,
    n_days INTEGER NOT NULL DEFAULT 0,
    expectancy_net REAL NOT NULL DEFAULT 0,
    expectancy_gross REAL NOT NULL DEFAULT 0,
    profit_factor REAL NOT NULL DEFAULT 0,
    sharpe REAL NOT NULL DEFAULT 0,
    sortino REAL NOT NULL DEFAULT 0,
    max_dd REAL NOT NULL DEFAULT 0,
    hit_rate REAL NOT NULL DEFAULT 0,
    turnover REAL NOT NULL DEFAULT 0,
    avg_trade_duration REAL NOT NULL DEFAULT 0,
    cost_ratio REAL NOT NULL DEFAULT 0,
    pbo REAL,
    dsr REAL,
    psr REAL,
    last_updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(strategy_id, asset, timeframe, regime_label, period_start, period_end)
);

CREATE TABLE IF NOT EXISTS learning_proposal (
    id TEXT PRIMARY KEY,
    asset TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    regime_label TEXT NOT NULL CHECK (regime_label IN ('trend', 'range', 'high_vol', 'toxic', 'unknown')),
    proposed_strategy_id TEXT NOT NULL,
    replaces_strategy_id TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    rationale TEXT NOT NULL DEFAULT '',
    required_gates_json TEXT NOT NULL DEFAULT '[]',
    score_json TEXT NOT NULL DEFAULT '{}',
    metrics_json TEXT NOT NULL DEFAULT '{}',
    source_summary_json TEXT NOT NULL DEFAULT '{}',
    needs_validation INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_learning_proposal_status_created
ON learning_proposal(status, created_at DESC);

CREATE TABLE IF NOT EXISTS strategy_policy_guidance (
    strategy_id TEXT PRIMARY KEY,
    preferred_regimes_json TEXT NOT NULL DEFAULT '[]',
    avoid_regimes_json TEXT NOT NULL DEFAULT '[]',
    min_confidence_to_recommend REAL NOT NULL DEFAULT 0,
    max_risk_multiplier REAL NOT NULL DEFAULT 1.0,
    max_spread_bps_allowed REAL,
    max_vpin_allowed REAL,
    cost_stress_result TEXT NOT NULL DEFAULT 'unknown',
    notes TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        self._ensure_column(conn, "experience_episode", "source_weight", "REAL NOT NULL DEFAULT 1.0")
        self._ensure_column(conn, "experience_episode", "validation_quality", "TEXT NOT NULL DEFAULT 'unknown'")
        self._ensure_column(conn, "experience_episode", "cost_fidelity_level", "TEXT NOT NULL DEFAULT 'standard'")
        self._ensure_column(conn, "experience_episode", "feature_set", "TEXT NOT NULL DEFAULT 'unknown'")
        self._ensure_column(conn, "experience_episode", "bot_id", "TEXT")
        self._ensure_column(conn, "experience_episode", "notes", "TEXT")
        self._ensure_column(conn, "experience_episode", "summary_json", "TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column(conn, "experience_episode", "created_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        self._ensure_column(conn, "experience_episode", "updated_at", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_experience_episode_bot_source
            ON experience_episode(bot_id, source, asset, timeframe, created_at DESC)
            """
        )
        self._ensure_column(conn, "experience_event", "realized_pnl_gross", "REAL")
        self._ensure_column(conn, "experience_event", "latency_ms", "REAL")
        self._ensure_column(conn, "experience_event", "spread_bps", "REAL")
        self._ensure_column(conn, "experience_event", "vpin_value", "REAL")
        self._migrate_regime_kpi(conn)
        self._ensure_column(conn, "learning_proposal", "score_json", "TEXT NOT NULL DEFAULT '{}'")
        self._ensure_column(conn, "learning_proposal", "status", "TEXT NOT NULL DEFAULT 'PENDING_REVIEW'")
        self._ensure_column(conn, "learning_proposal", "reviewed_at", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_policy_guidance (
                strategy_id TEXT PRIMARY KEY,
                preferred_regimes_json TEXT NOT NULL DEFAULT '[]',
                avoid_regimes_json TEXT NOT NULL DEFAULT '[]',
                min_confidence_to_recommend REAL NOT NULL DEFAULT 0,
                max_risk_multiplier REAL NOT NULL DEFAULT 1.0,
                max_spread_bps_allowed REAL,
                max_vpin_allowed REAL,
                cost_stress_result TEXT NOT NULL DEFAULT 'unknown',
                notes TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not rows:
            return
        names = {str(row["name"]) if isinstance(row, sqlite3.Row) else str(row[1]) for row in rows}
        if column in names:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def _migrate_regime_kpi(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(regime_kpi)").fetchall()
        if not rows:
            return
        names = {str(row["name"]) if isinstance(row, sqlite3.Row) else str(row[1]) for row in rows}
        expected = {"asset", "timeframe", "expectancy_gross", "sortino", "turnover", "avg_trade_duration", "cost_ratio", "dsr", "psr"}
        if expected.issubset(names):
            return
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS regime_kpi_v2 (
                strategy_id TEXT NOT NULL,
                asset TEXT NOT NULL DEFAULT '',
                timeframe TEXT NOT NULL DEFAULT '',
                regime_label TEXT NOT NULL CHECK (regime_label IN ('trend', 'range', 'high_vol', 'toxic', 'unknown')),
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                n_trades INTEGER NOT NULL DEFAULT 0,
                n_days INTEGER NOT NULL DEFAULT 0,
                expectancy_net REAL NOT NULL DEFAULT 0,
                expectancy_gross REAL NOT NULL DEFAULT 0,
                profit_factor REAL NOT NULL DEFAULT 0,
                sharpe REAL NOT NULL DEFAULT 0,
                sortino REAL NOT NULL DEFAULT 0,
                max_dd REAL NOT NULL DEFAULT 0,
                hit_rate REAL NOT NULL DEFAULT 0,
                turnover REAL NOT NULL DEFAULT 0,
                avg_trade_duration REAL NOT NULL DEFAULT 0,
                cost_ratio REAL NOT NULL DEFAULT 0,
                pbo REAL,
                dsr REAL,
                psr REAL,
                last_updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(strategy_id, asset, timeframe, regime_label, period_start, period_end)
            );
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO regime_kpi_v2 (
                strategy_id, asset, timeframe, regime_label, period_start, period_end,
                n_trades, n_days, expectancy_net, expectancy_gross, profit_factor,
                sharpe, sortino, max_dd, hit_rate, turnover, avg_trade_duration,
                cost_ratio, pbo, dsr, psr, last_updated
            )
            SELECT
                strategy_id,
                '',
                '',
                regime_label,
                period_start,
                period_end,
                n_trades,
                n_days,
                expectancy_net,
                0,
                profit_factor,
                sharpe,
                0,
                max_dd,
                hit_rate,
                0,
                0,
                0,
                pbo,
                NULL,
                NULL,
                last_updated
            FROM regime_kpi
            """
        )
        conn.execute("DROP TABLE regime_kpi")
        conn.execute("ALTER TABLE regime_kpi_v2 RENAME TO regime_kpi")

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

    def upsert_experience_episode(
        self,
        *,
        episode_id: str,
        run_id: str,
        source: str,
        source_weight: float = 1.0,
        strategy_id: str,
        bot_id: str | None = None,
        asset: str,
        timeframe: str,
        start_ts: str | None,
        end_ts: str | None,
        dataset_source: str | None,
        dataset_hash: str | None,
        commit_hash: str | None,
        costs_profile_id: str | None,
        validation_quality: str | None = None,
        cost_fidelity_level: str | None = None,
        feature_set: str | None = None,
        notes: str | None = None,
        summary: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO experience_episode (
                    id, run_id, source, source_weight, strategy_id, bot_id, asset, timeframe, start_ts, end_ts,
                    dataset_source, dataset_hash, commit_hash, costs_profile_id,
                    validation_quality, cost_fidelity_level, feature_set, notes, summary_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    run_id=excluded.run_id,
                    source=excluded.source,
                    source_weight=excluded.source_weight,
                    strategy_id=excluded.strategy_id,
                    bot_id=excluded.bot_id,
                    asset=excluded.asset,
                    timeframe=excluded.timeframe,
                    start_ts=excluded.start_ts,
                    end_ts=excluded.end_ts,
                    dataset_source=excluded.dataset_source,
                    dataset_hash=excluded.dataset_hash,
                    commit_hash=excluded.commit_hash,
                    costs_profile_id=excluded.costs_profile_id,
                    validation_quality=excluded.validation_quality,
                    cost_fidelity_level=excluded.cost_fidelity_level,
                    feature_set=excluded.feature_set,
                    notes=excluded.notes,
                    summary_json=excluded.summary_json,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    episode_id,
                    run_id,
                    source,
                    float(source_weight),
                    strategy_id,
                    str(bot_id or "").strip() or None,
                    asset,
                    timeframe,
                    start_ts,
                    end_ts,
                    dataset_source,
                    dataset_hash,
                    commit_hash,
                    costs_profile_id,
                    validation_quality or "unknown",
                    cost_fidelity_level or "standard",
                    feature_set or "unknown",
                    notes,
                    json.dumps(summary or {}, ensure_ascii=True, sort_keys=True),
                    created_at,
                ),
            )
            conn.commit()

    def replace_experience_events(self, episode_id: str, events: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM experience_event WHERE episode_id=?", (episode_id,))
            conn.executemany(
                """
                INSERT INTO experience_event (
                    id, episode_id, ts, regime_label, features_json, action, side,
                    predicted_edge, realized_pnl_gross, realized_pnl_net, fee, spread_cost, slippage_cost, funding_cost,
                    latency_ms, spread_bps, vpin_value, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(row.get("id") or ""),
                        episode_id,
                        str(row.get("ts") or ""),
                        str(row.get("regime_label") or "unknown"),
                        json.dumps(row.get("features_json") or {}, ensure_ascii=True, sort_keys=True),
                        str(row.get("action") or "hold"),
                        str(row.get("side") or "flat"),
                        row.get("predicted_edge"),
                        row.get("realized_pnl_gross"),
                        row.get("realized_pnl_net"),
                        float(row.get("fee") or 0.0),
                        float(row.get("spread_cost") or 0.0),
                        float(row.get("slippage_cost") or 0.0),
                        float(row.get("funding_cost") or 0.0),
                        row.get("latency_ms"),
                        row.get("spread_bps"),
                        row.get("vpin_value"),
                        str(row.get("notes") or ""),
                    )
                    for row in events
                ],
            )
            conn.commit()

    def list_experience_episodes(
        self,
        *,
        strategy_ids: list[str] | None = None,
        bot_ids: list[str] | None = None,
        sources: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM experience_episode WHERE 1=1"
        params: list[Any] = []
        if strategy_ids:
            placeholders = ",".join("?" for _ in strategy_ids)
            query += f" AND strategy_id IN ({placeholders})"
            params.extend([str(x) for x in strategy_ids])
        if sources:
            placeholders = ",".join("?" for _ in sources)
            query += f" AND source IN ({placeholders})"
            params.extend([str(x) for x in sources])
        query += " ORDER BY created_at DESC, id DESC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        requested_bot_ids = {str(x).strip() for x in (bot_ids or []) if str(x).strip()}
        for row in rows:
            item = dict(row)
            try:
                item["summary"] = json.loads(item.pop("summary_json", "{}") or "{}")
            except Exception:
                item["summary"] = {}
            summary = item["summary"] if isinstance(item.get("summary"), dict) else {}
            item["bot_id"] = str(item.get("bot_id") or summary.get("bot_id") or "").strip() or None
            item["evidence_status"] = str(summary.get("evidence_status") or "trusted")
            raw_flags = summary.get("evidence_flags") if isinstance(summary.get("evidence_flags"), list) else []
            item["evidence_flags"] = [str(flag).strip() for flag in raw_flags if str(flag).strip()]
            item["learning_excluded"] = bool(summary.get("learning_excluded", False))
            if requested_bot_ids and item["bot_id"] not in requested_bot_ids:
                continue
            out.append(item)
        return out

    def list_experience_events(self, *, episode_ids: list[str] | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM experience_event WHERE 1=1"
        params: list[Any] = []
        if episode_ids:
            placeholders = ",".join("?" for _ in episode_ids)
            query += f" AND episode_id IN ({placeholders})"
            params.extend([str(x) for x in episode_ids])
        query += " ORDER BY ts ASC, id ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["features"] = json.loads(item.pop("features_json", "{}") or "{}")
            except Exception:
                item["features"] = {}
            out.append(item)
        return out

    def replace_regime_kpis(self, strategy_id: str, rows: list[dict[str, Any]]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM regime_kpi WHERE strategy_id=?", (strategy_id,))
            conn.executemany(
                """
                INSERT INTO regime_kpi (
                    strategy_id, asset, timeframe, regime_label, period_start, period_end, n_trades, n_days,
                    expectancy_net, expectancy_gross, profit_factor, sharpe, sortino, max_dd, hit_rate,
                    turnover, avg_trade_duration, cost_ratio, pbo, dsr, psr, last_updated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                """,
                [
                    (
                        strategy_id,
                        str(row.get("asset") or ""),
                        str(row.get("timeframe") or ""),
                        str(row.get("regime_label") or "unknown"),
                        str(row.get("period_start") or ""),
                        str(row.get("period_end") or ""),
                        int(row.get("n_trades") or 0),
                        int(row.get("n_days") or 0),
                        float(row.get("expectancy_net") or 0.0),
                        float(row.get("expectancy_gross") or 0.0),
                        float(row.get("profit_factor") or 0.0),
                        float(row.get("sharpe") or 0.0),
                        float(row.get("sortino") or 0.0),
                        float(row.get("max_dd") or 0.0),
                        float(row.get("hit_rate") or 0.0),
                        float(row.get("turnover") or 0.0),
                        float(row.get("avg_trade_duration") or 0.0),
                        float(row.get("cost_ratio") or 0.0),
                        row.get("pbo"),
                        row.get("dsr"),
                        row.get("psr"),
                        row.get("last_updated"),
                    )
                    for row in rows
                ],
            )
            conn.commit()

    def list_regime_kpis(self, *, strategy_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM regime_kpi WHERE 1=1"
        params: list[Any] = []
        if strategy_id:
            query += " AND strategy_id=?"
            params.append(strategy_id)
        query += " ORDER BY last_updated DESC, strategy_id ASC, regime_label ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def upsert_learning_proposal(
        self,
        *,
        proposal_id: str,
        asset: str,
        timeframe: str,
        regime_label: str,
        proposed_strategy_id: str,
        replaces_strategy_id: str | None,
        confidence: float,
        rationale: str,
        required_gates: list[str] | None = None,
        score: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
        source_summary: dict[str, Any] | None = None,
        needs_validation: bool = False,
        status: str = "PENDING_REVIEW",
        created_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_proposal (
                    id, asset, timeframe, regime_label, proposed_strategy_id, replaces_strategy_id,
                    confidence, rationale, required_gates_json, score_json, metrics_json, source_summary_json,
                    needs_validation, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(id) DO UPDATE SET
                    asset=excluded.asset,
                    timeframe=excluded.timeframe,
                    regime_label=excluded.regime_label,
                    proposed_strategy_id=excluded.proposed_strategy_id,
                    replaces_strategy_id=excluded.replaces_strategy_id,
                    confidence=excluded.confidence,
                    rationale=excluded.rationale,
                    required_gates_json=excluded.required_gates_json,
                    score_json=excluded.score_json,
                    metrics_json=excluded.metrics_json,
                    source_summary_json=excluded.source_summary_json,
                    needs_validation=excluded.needs_validation,
                    status=excluded.status
                """,
                (
                    proposal_id,
                    asset,
                    timeframe,
                    regime_label,
                    proposed_strategy_id,
                    replaces_strategy_id,
                    float(confidence),
                    rationale,
                    json.dumps(required_gates or [], ensure_ascii=True, sort_keys=True),
                    json.dumps(score or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(metrics or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(source_summary or {}, ensure_ascii=True, sort_keys=True),
                    1 if needs_validation else 0,
                    status,
                    created_at,
                ),
            )
            conn.commit()

    def list_learning_proposals(self, *, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM learning_proposal WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC, id DESC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._learning_proposal_row(row) for row in rows]

    def get_learning_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM learning_proposal WHERE id=?", (proposal_id,)).fetchone()
        return self._learning_proposal_row(row) if row else None

    def patch_learning_proposal_status(self, proposal_id: str, *, status: str, note: str | None = None) -> dict[str, Any] | None:
        row = self.get_learning_proposal(proposal_id)
        if row is None:
            return None
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        if note:
            metrics = {**metrics, "review_note": note}
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE learning_proposal
                SET status=?, reviewed_at=CURRENT_TIMESTAMP, metrics_json=?
                WHERE id=?
                """,
                (
                    status,
                    json.dumps(metrics, ensure_ascii=True, sort_keys=True),
                    proposal_id,
                ),
            )
            conn.commit()
        return self.get_learning_proposal(proposal_id)

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

    def _learning_proposal_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["required_gates"] = json.loads(item.pop("required_gates_json", "[]") or "[]")
        except Exception:
            item["required_gates"] = []
        try:
            item["score"] = json.loads(item.pop("score_json", "{}") or "{}")
        except Exception:
            item["score"] = {}
        try:
            item["metrics"] = json.loads(item.pop("metrics_json", "{}") or "{}")
        except Exception:
            item["metrics"] = {}
        try:
            item["source_summary"] = json.loads(item.pop("source_summary_json", "{}") or "{}")
        except Exception:
            item["source_summary"] = {}
        item["needs_validation"] = bool(item.get("needs_validation"))
        return item

    def upsert_strategy_policy_guidance(
        self,
        *,
        strategy_id: str,
        preferred_regimes: list[str] | None = None,
        avoid_regimes: list[str] | None = None,
        min_confidence_to_recommend: float = 0.0,
        max_risk_multiplier: float = 1.0,
        max_spread_bps_allowed: float | None = None,
        max_vpin_allowed: float | None = None,
        cost_stress_result: str = "unknown",
        notes: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_policy_guidance (
                    strategy_id, preferred_regimes_json, avoid_regimes_json, min_confidence_to_recommend,
                    max_risk_multiplier, max_spread_bps_allowed, max_vpin_allowed, cost_stress_result, notes, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    preferred_regimes_json=excluded.preferred_regimes_json,
                    avoid_regimes_json=excluded.avoid_regimes_json,
                    min_confidence_to_recommend=excluded.min_confidence_to_recommend,
                    max_risk_multiplier=excluded.max_risk_multiplier,
                    max_spread_bps_allowed=excluded.max_spread_bps_allowed,
                    max_vpin_allowed=excluded.max_vpin_allowed,
                    cost_stress_result=excluded.cost_stress_result,
                    notes=excluded.notes,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    strategy_id,
                    json.dumps(preferred_regimes or [], ensure_ascii=True, sort_keys=True),
                    json.dumps(avoid_regimes or [], ensure_ascii=True, sort_keys=True),
                    float(min_confidence_to_recommend or 0.0),
                    float(max_risk_multiplier or 1.0),
                    float(max_spread_bps_allowed) if max_spread_bps_allowed is not None else None,
                    float(max_vpin_allowed) if max_vpin_allowed is not None else None,
                    str(cost_stress_result or "unknown"),
                    notes,
                ),
            )
            conn.commit()

    def list_strategy_policy_guidance(self, *, strategy_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM strategy_policy_guidance WHERE 1=1"
        params: list[Any] = []
        if strategy_id:
            query += " AND strategy_id=?"
            params.append(strategy_id)
        query += " ORDER BY updated_at DESC, strategy_id ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["preferred_regimes"] = json.loads(item.pop("preferred_regimes_json", "[]") or "[]")
            except Exception:
                item["preferred_regimes"] = []
            try:
                item["avoid_regimes"] = json.loads(item.pop("avoid_regimes_json", "[]") or "[]")
            except Exception:
                item["avoid_regimes"] = []
            out.append(item)
        return out

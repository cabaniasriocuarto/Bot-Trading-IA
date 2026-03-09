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
    source TEXT NOT NULL CHECK (source IN ('backtest', 'shadow', 'paper', 'testnet', 'live')),
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
    legacy_untrusted INTEGER NOT NULL DEFAULT 0,
    excluded_from_learning INTEGER NOT NULL DEFAULT 0,
    excluded_from_rankings INTEGER NOT NULL DEFAULT 0,
    excluded_from_guidance INTEGER NOT NULL DEFAULT 0,
    excluded_from_brain_scores INTEGER NOT NULL DEFAULT 0,
    stale INTEGER NOT NULL DEFAULT 0,
    as_of TEXT,
    vintage_date TEXT,
    trades_count INTEGER NOT NULL DEFAULT 0,
    attribution_type TEXT NOT NULL DEFAULT 'unknown',
    attribution_confidence REAL NOT NULL DEFAULT 0,
    effective_weight REAL NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS strategy_truth (
    strategy_id TEXT PRIMARY KEY,
    strategy_version TEXT,
    family TEXT,
    market TEXT,
    asset_class TEXT,
    timeframe TEXT,
    thesis_summary TEXT,
    thesis_detail TEXT,
    intended_regimes_json TEXT NOT NULL DEFAULT '[]',
    forbidden_regimes_json TEXT NOT NULL DEFAULT '[]',
    microstructure_constraints_json TEXT NOT NULL DEFAULT '{}',
    capacity_constraints_json TEXT NOT NULL DEFAULT '{}',
    cost_limits_json TEXT NOT NULL DEFAULT '{}',
    invalidation_rules_json TEXT NOT NULL DEFAULT '{}',
    current_status TEXT NOT NULL DEFAULT 'candidate',
    current_confidence REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS strategy_evidence (
    evidence_id TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    run_id TEXT,
    bot_id TEXT,
    dataset_hash TEXT,
    dataset_source TEXT,
    as_of TEXT,
    vintage_date TEXT,
    trades INTEGER NOT NULL DEFAULT 0,
    turnover REAL NOT NULL DEFAULT 0,
    fees_bps REAL,
    spread_bps REAL,
    slippage_bps REAL,
    funding_bps REAL,
    expectancy_net REAL,
    sharpe REAL,
    sortino REAL,
    psr REAL,
    dsr REAL,
    pbo REAL,
    max_dd REAL,
    win_rate REAL,
    profit_factor REAL,
    validation_quality REAL NOT NULL DEFAULT 0,
    source_weight REAL NOT NULL DEFAULT 0,
    freshness_decay REAL NOT NULL DEFAULT 1,
    effective_weight REAL NOT NULL DEFAULT 0,
    legacy_untrusted INTEGER NOT NULL DEFAULT 0,
    excluded_from_learning INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(strategy_id) REFERENCES strategy_registry(id)
);

CREATE INDEX IF NOT EXISTS idx_strategy_evidence_strategy_source
ON strategy_evidence(strategy_id, source_type, created_at DESC);

CREATE TABLE IF NOT EXISTS bot_policy_state (
    bot_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    regime_label TEXT NOT NULL,
    score_current REAL NOT NULL DEFAULT 0,
    weight_target REAL NOT NULL DEFAULT 0,
    weight_live REAL NOT NULL DEFAULT 0,
    veto_until TEXT,
    veto_reason TEXT,
    confidence REAL NOT NULL DEFAULT 0,
    source_scope TEXT NOT NULL DEFAULT 'unknown',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (bot_id, strategy_id, regime_label)
);

CREATE TABLE IF NOT EXISTS bot_decision_log (
    decision_id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    regime_label TEXT NOT NULL,
    candidate_strategies_json TEXT NOT NULL DEFAULT '[]',
    selected_strategy_id TEXT,
    rejected_strategies_json TEXT NOT NULL DEFAULT '[]',
    reason_json TEXT NOT NULL DEFAULT '{}',
    evidence_scope_json TEXT NOT NULL DEFAULT '{}',
    risk_overrides_json TEXT NOT NULL DEFAULT '{}',
    execution_constraints_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_bot_decision_log_bot_ts
ON bot_decision_log(bot_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS run_bot_link (
    run_id TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    attribution_type TEXT NOT NULL,
    attribution_confidence REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, bot_id)
);

CREATE INDEX IF NOT EXISTS idx_run_bot_link_bot_created
ON run_bot_link(bot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS execution_reality (
    execution_id TEXT PRIMARY KEY,
    order_id TEXT,
    bot_id TEXT,
    strategy_id TEXT,
    symbol TEXT,
    timestamp TEXT,
    order_type TEXT,
    side TEXT,
    qty REAL,
    participation_rate REAL,
    expected_fill_price REAL,
    realized_fill_price REAL,
    realized_slippage_bps REAL,
    maker_taker TEXT,
    partial_fill_ratio REAL,
    queue_proxy REAL,
    cancel_replace_count INTEGER NOT NULL DEFAULT 0,
    latency_ms REAL,
    spread_bps REAL,
    impact_bps_est REAL,
    impact_budget_bps REAL,
    reconciliation_status TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_execution_reality_bot_ts
ON execution_reality(bot_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS instrument_registry (
    instrument_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_market TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    normalized_symbol TEXT NOT NULL,
    base_asset TEXT,
    quote_asset TEXT,
    settle_asset TEXT,
    margin_asset TEXT,
    asset_class TEXT NOT NULL DEFAULT 'unknown',
    contract_type TEXT,
    instrument_type TEXT,
    status TEXT NOT NULL DEFAULT 'unknown',
    tradable INTEGER NOT NULL DEFAULT 0,
    backtestable INTEGER NOT NULL DEFAULT 0,
    paper_enabled INTEGER NOT NULL DEFAULT 0,
    test_enabled INTEGER NOT NULL DEFAULT 0,
    demo_enabled INTEGER NOT NULL DEFAULT 0,
    live_enabled INTEGER NOT NULL DEFAULT 0,
    permissions_json TEXT NOT NULL DEFAULT '[]',
    order_types_json TEXT NOT NULL DEFAULT '[]',
    time_in_force_json TEXT NOT NULL DEFAULT '[]',
    tick_size REAL,
    step_size REAL,
    min_qty REAL,
    max_qty REAL,
    min_notional REAL,
    price_precision INTEGER,
    qty_precision INTEGER,
    maker_fee_bps REAL,
    taker_fee_bps REAL,
    funding_interval_hours REAL,
    onboard_date TEXT,
    delivery_date TEXT,
    exchange_filters_json TEXT NOT NULL DEFAULT '{}',
    symbol_filters_json TEXT NOT NULL DEFAULT '{}',
    raw_exchange_payload_json TEXT NOT NULL DEFAULT '{}',
    account_eligibility_json TEXT NOT NULL DEFAULT '{}',
    source_hash TEXT,
    is_active_snapshot INTEGER NOT NULL DEFAULT 1,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delisted_at TEXT,
    UNIQUE(provider, provider_market, provider_symbol)
);

CREATE INDEX IF NOT EXISTS idx_instrument_registry_normalized
ON instrument_registry(normalized_symbol, provider_market, status);

CREATE INDEX IF NOT EXISTS idx_instrument_registry_live
ON instrument_registry(provider, provider_market, live_enabled, tradable);

CREATE TABLE IF NOT EXISTS instrument_catalog_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    provider_market TEXT NOT NULL,
    catalog_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    total_instruments INTEGER NOT NULL DEFAULT 0,
    tradable_instruments INTEGER NOT NULL DEFAULT 0,
    live_enabled_instruments INTEGER NOT NULL DEFAULT 0,
    backtestable_instruments INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_instrument_catalog_snapshot_created
ON instrument_catalog_snapshot(provider, provider_market, created_at DESC);

CREATE TABLE IF NOT EXISTS instrument_catalog_snapshot_item (
    snapshot_id TEXT NOT NULL,
    instrument_id TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    normalized_symbol TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'unknown',
    tradable INTEGER NOT NULL DEFAULT 0,
    backtestable INTEGER NOT NULL DEFAULT 0,
    paper_enabled INTEGER NOT NULL DEFAULT 0,
    test_enabled INTEGER NOT NULL DEFAULT 0,
    demo_enabled INTEGER NOT NULL DEFAULT 0,
    live_enabled INTEGER NOT NULL DEFAULT 0,
    snapshot_payload_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(snapshot_id, instrument_id),
    FOREIGN KEY(snapshot_id) REFERENCES instrument_catalog_snapshot(snapshot_id) ON DELETE CASCADE,
    FOREIGN KEY(instrument_id) REFERENCES instrument_registry(instrument_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_instrument_catalog_snapshot_item_symbol
ON instrument_catalog_snapshot_item(snapshot_id, normalized_symbol, live_enabled);
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
        self._migrate_experience_episode(conn)
        self._ensure_column(conn, "experience_episode", "source_weight", "REAL NOT NULL DEFAULT 1.0")
        self._ensure_column(conn, "experience_episode", "validation_quality", "TEXT NOT NULL DEFAULT 'unknown'")
        self._ensure_column(conn, "experience_episode", "cost_fidelity_level", "TEXT NOT NULL DEFAULT 'standard'")
        self._ensure_column(conn, "experience_episode", "feature_set", "TEXT NOT NULL DEFAULT 'unknown'")
        self._ensure_column(conn, "experience_episode", "bot_id", "TEXT")
        self._ensure_column(conn, "experience_episode", "legacy_untrusted", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "experience_episode", "excluded_from_learning", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "experience_episode", "excluded_from_rankings", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "experience_episode", "excluded_from_guidance", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "experience_episode", "excluded_from_brain_scores", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "experience_episode", "stale", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "experience_episode", "as_of", "TEXT")
        self._ensure_column(conn, "experience_episode", "vintage_date", "TEXT")
        self._ensure_column(conn, "experience_episode", "trades_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(conn, "experience_episode", "attribution_type", "TEXT NOT NULL DEFAULT 'unknown'")
        self._ensure_column(conn, "experience_episode", "attribution_confidence", "REAL NOT NULL DEFAULT 0")
        self._ensure_column(conn, "experience_episode", "effective_weight", "REAL NOT NULL DEFAULT 0")
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

    def _migrate_experience_episode(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("PRAGMA table_info(experience_episode)").fetchall()
        if not rows:
            return
        names = {str(row["name"]) if isinstance(row, sqlite3.Row) else str(row[1]) for row in rows}
        table_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='experience_episode'"
        ).fetchone()
        table_sql = str((table_row["sql"] if isinstance(table_row, sqlite3.Row) else (table_row[0] if table_row else "")) or "").lower()
        required = {
            "legacy_untrusted",
            "excluded_from_learning",
            "excluded_from_rankings",
            "excluded_from_guidance",
            "excluded_from_brain_scores",
            "stale",
            "as_of",
            "vintage_date",
            "trades_count",
            "attribution_type",
            "attribution_confidence",
            "effective_weight",
        }
        requires_rebuild = "live" not in table_sql or not required.issubset(names)
        if not requires_rebuild:
            return
        source_expr = "source" if "source" in names else "'backtest'"
        bot_expr = "bot_id" if "bot_id" in names else "NULL"
        start_expr = "start_ts" if "start_ts" in names else "NULL"
        created_expr = "created_at" if "created_at" in names else "CURRENT_TIMESTAMP"
        summary_expr = "summary_json" if "summary_json" in names else "'{}'"
        trades_expr = "0"
        if "summary_json" in names:
            trades_expr = (
                "CAST(COALESCE(json_extract(summary_json, '$.trade_count'), "
                "json_extract(summary_json, '$.metrics.trade_count'), "
                "json_extract(summary_json, '$.metrics.roundtrips'), 0) AS INTEGER)"
            )
        attribution_type_expr = (
            "CASE WHEN bot_id IS NOT NULL AND TRIM(bot_id) <> '' THEN 'exact' ELSE 'unknown' END"
            if "bot_id" in names
            else "'unknown'"
        )
        attribution_confidence_expr = (
            "CASE WHEN bot_id IS NOT NULL AND TRIM(bot_id) <> '' THEN 1.0 ELSE 0.0 END"
            if "bot_id" in names
            else "0.0"
        )
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS experience_episode_v2 (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                source TEXT NOT NULL CHECK (source IN ('backtest', 'shadow', 'paper', 'testnet', 'live')),
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
                legacy_untrusted INTEGER NOT NULL DEFAULT 0,
                excluded_from_learning INTEGER NOT NULL DEFAULT 0,
                excluded_from_rankings INTEGER NOT NULL DEFAULT 0,
                excluded_from_guidance INTEGER NOT NULL DEFAULT 0,
                excluded_from_brain_scores INTEGER NOT NULL DEFAULT 0,
                stale INTEGER NOT NULL DEFAULT 0,
                as_of TEXT,
                vintage_date TEXT,
                trades_count INTEGER NOT NULL DEFAULT 0,
                attribution_type TEXT NOT NULL DEFAULT 'unknown',
                attribution_confidence REAL NOT NULL DEFAULT 0,
                effective_weight REAL NOT NULL DEFAULT 0,
                notes TEXT,
                summary_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(run_id, source, strategy_id, asset, timeframe, dataset_hash)
            );
            """
        )
        conn.execute(
            f"""
            INSERT OR REPLACE INTO experience_episode_v2 (
                id, run_id, source, source_weight, strategy_id, bot_id, asset, timeframe, start_ts, end_ts,
                dataset_source, dataset_hash, commit_hash, costs_profile_id, validation_quality, cost_fidelity_level,
                feature_set, legacy_untrusted, excluded_from_learning, excluded_from_rankings, excluded_from_guidance,
                excluded_from_brain_scores, stale, as_of, vintage_date, trades_count, attribution_type,
                attribution_confidence, effective_weight, notes, summary_json, created_at, updated_at
            )
            SELECT
                id,
                run_id,
                {source_expr},
                COALESCE(source_weight, 1.0),
                strategy_id,
                {bot_expr},
                asset,
                timeframe,
                {start_expr},
                end_ts,
                dataset_source,
                dataset_hash,
                commit_hash,
                costs_profile_id,
                COALESCE(validation_quality, 'unknown'),
                COALESCE(cost_fidelity_level, 'standard'),
                COALESCE(feature_set, 'unknown'),
                0,
                0,
                0,
                0,
                0,
                0,
                COALESCE({start_expr}, {created_expr}),
                NULL,
                {trades_expr},
                {attribution_type_expr},
                {attribution_confidence_expr},
                COALESCE(source_weight, 1.0),
                notes,
                COALESCE({summary_expr}, '{{}}'),
                COALESCE({created_expr}, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM experience_episode
            """
        )
        conn.execute("DROP TABLE experience_episode")
        conn.execute("ALTER TABLE experience_episode_v2 RENAME TO experience_episode")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_experience_episode_strategy_source
            ON experience_episode(strategy_id, source, asset, timeframe, created_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_experience_episode_bot_source
            ON experience_episode(bot_id, source, asset, timeframe, created_at DESC)
            """
        )

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
        legacy_untrusted: bool = False,
        excluded_from_learning: bool = False,
        excluded_from_rankings: bool = False,
        excluded_from_guidance: bool = False,
        excluded_from_brain_scores: bool = False,
        stale: bool = False,
        as_of: str | None = None,
        vintage_date: str | None = None,
        trades_count: int = 0,
        attribution_type: str | None = None,
        attribution_confidence: float = 0.0,
        effective_weight: float = 0.0,
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
                    validation_quality, cost_fidelity_level, feature_set,
                    legacy_untrusted, excluded_from_learning, excluded_from_rankings, excluded_from_guidance,
                    excluded_from_brain_scores, stale, as_of, vintage_date, trades_count,
                    attribution_type, attribution_confidence, effective_weight,
                    notes, summary_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
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
                    legacy_untrusted=excluded.legacy_untrusted,
                    excluded_from_learning=excluded.excluded_from_learning,
                    excluded_from_rankings=excluded.excluded_from_rankings,
                    excluded_from_guidance=excluded.excluded_from_guidance,
                    excluded_from_brain_scores=excluded.excluded_from_brain_scores,
                    stale=excluded.stale,
                    as_of=excluded.as_of,
                    vintage_date=excluded.vintage_date,
                    trades_count=excluded.trades_count,
                    attribution_type=excluded.attribution_type,
                    attribution_confidence=excluded.attribution_confidence,
                    effective_weight=excluded.effective_weight,
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
                    1 if legacy_untrusted else 0,
                    1 if excluded_from_learning else 0,
                    1 if excluded_from_rankings else 0,
                    1 if excluded_from_guidance else 0,
                    1 if excluded_from_brain_scores else 0,
                    1 if stale else 0,
                    as_of,
                    vintage_date,
                    int(trades_count or 0),
                    attribution_type or "unknown",
                    float(attribution_confidence or 0.0),
                    float(effective_weight or 0.0),
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
            item["legacy_untrusted"] = bool(item.get("legacy_untrusted"))
            item["excluded_from_learning"] = bool(item.get("excluded_from_learning"))
            item["excluded_from_rankings"] = bool(item.get("excluded_from_rankings"))
            item["excluded_from_guidance"] = bool(item.get("excluded_from_guidance"))
            item["excluded_from_brain_scores"] = bool(item.get("excluded_from_brain_scores"))
            item["stale"] = bool(item.get("stale"))
            item["trades_count"] = int(item.get("trades_count") or summary.get("trade_count") or 0)
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

    def upsert_strategy_truth(
        self,
        *,
        strategy_id: str,
        strategy_version: str | None = None,
        family: str | None = None,
        market: str | None = None,
        asset_class: str | None = None,
        timeframe: str | None = None,
        thesis_summary: str | None = None,
        thesis_detail: str | None = None,
        intended_regimes: list[str] | None = None,
        forbidden_regimes: list[str] | None = None,
        microstructure_constraints: dict[str, Any] | None = None,
        capacity_constraints: dict[str, Any] | None = None,
        cost_limits: dict[str, Any] | None = None,
        invalidation_rules: dict[str, Any] | None = None,
        current_status: str = "candidate",
        current_confidence: float = 0.0,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_truth (
                    strategy_id, strategy_version, family, market, asset_class, timeframe,
                    thesis_summary, thesis_detail, intended_regimes_json, forbidden_regimes_json,
                    microstructure_constraints_json, capacity_constraints_json, cost_limits_json,
                    invalidation_rules_json, current_status, current_confidence, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    strategy_version=excluded.strategy_version,
                    family=excluded.family,
                    market=excluded.market,
                    asset_class=excluded.asset_class,
                    timeframe=excluded.timeframe,
                    thesis_summary=excluded.thesis_summary,
                    thesis_detail=excluded.thesis_detail,
                    intended_regimes_json=excluded.intended_regimes_json,
                    forbidden_regimes_json=excluded.forbidden_regimes_json,
                    microstructure_constraints_json=excluded.microstructure_constraints_json,
                    capacity_constraints_json=excluded.capacity_constraints_json,
                    cost_limits_json=excluded.cost_limits_json,
                    invalidation_rules_json=excluded.invalidation_rules_json,
                    current_status=excluded.current_status,
                    current_confidence=excluded.current_confidence,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    strategy_id,
                    strategy_version,
                    family,
                    market,
                    asset_class,
                    timeframe,
                    thesis_summary,
                    thesis_detail,
                    json.dumps(intended_regimes or [], ensure_ascii=True, sort_keys=True),
                    json.dumps(forbidden_regimes or [], ensure_ascii=True, sort_keys=True),
                    json.dumps(microstructure_constraints or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(capacity_constraints or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(cost_limits or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(invalidation_rules or {}, ensure_ascii=True, sort_keys=True),
                    current_status,
                    float(current_confidence or 0.0),
                ),
            )
            conn.commit()

    def get_strategy_truth(self, strategy_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM strategy_truth WHERE strategy_id=?", (strategy_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        for src, dst in (
            ("intended_regimes_json", "intended_regimes"),
            ("forbidden_regimes_json", "forbidden_regimes"),
            ("microstructure_constraints_json", "microstructure_constraints"),
            ("capacity_constraints_json", "capacity_constraints"),
            ("cost_limits_json", "cost_limits"),
            ("invalidation_rules_json", "invalidation_rules"),
        ):
            try:
                item[dst] = json.loads(item.pop(src, "[]") or ("[]" if "regimes" in src else "{}"))
            except Exception:
                item[dst] = [] if "regimes" in src else {}
        return item

    def upsert_strategy_evidence(
        self,
        *,
        evidence_id: str,
        strategy_id: str,
        source_type: str,
        run_id: str | None = None,
        bot_id: str | None = None,
        dataset_hash: str | None = None,
        dataset_source: str | None = None,
        as_of: str | None = None,
        vintage_date: str | None = None,
        trades: int = 0,
        turnover: float = 0.0,
        fees_bps: float | None = None,
        spread_bps: float | None = None,
        slippage_bps: float | None = None,
        funding_bps: float | None = None,
        expectancy_net: float | None = None,
        sharpe: float | None = None,
        sortino: float | None = None,
        psr: float | None = None,
        dsr: float | None = None,
        pbo: float | None = None,
        max_dd: float | None = None,
        win_rate: float | None = None,
        profit_factor: float | None = None,
        validation_quality: float = 0.0,
        source_weight: float = 0.0,
        freshness_decay: float = 1.0,
        effective_weight: float = 0.0,
        legacy_untrusted: bool = False,
        excluded_from_learning: bool = False,
        notes: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO strategy_evidence (
                    evidence_id, strategy_id, source_type, run_id, bot_id, dataset_hash, dataset_source, as_of, vintage_date,
                    trades, turnover, fees_bps, spread_bps, slippage_bps, funding_bps, expectancy_net, sharpe, sortino, psr, dsr,
                    pbo, max_dd, win_rate, profit_factor, validation_quality, source_weight, freshness_decay, effective_weight,
                    legacy_untrusted, excluded_from_learning, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(evidence_id) DO UPDATE SET
                    strategy_id=excluded.strategy_id,
                    source_type=excluded.source_type,
                    run_id=excluded.run_id,
                    bot_id=excluded.bot_id,
                    dataset_hash=excluded.dataset_hash,
                    dataset_source=excluded.dataset_source,
                    as_of=excluded.as_of,
                    vintage_date=excluded.vintage_date,
                    trades=excluded.trades,
                    turnover=excluded.turnover,
                    fees_bps=excluded.fees_bps,
                    spread_bps=excluded.spread_bps,
                    slippage_bps=excluded.slippage_bps,
                    funding_bps=excluded.funding_bps,
                    expectancy_net=excluded.expectancy_net,
                    sharpe=excluded.sharpe,
                    sortino=excluded.sortino,
                    psr=excluded.psr,
                    dsr=excluded.dsr,
                    pbo=excluded.pbo,
                    max_dd=excluded.max_dd,
                    win_rate=excluded.win_rate,
                    profit_factor=excluded.profit_factor,
                    validation_quality=excluded.validation_quality,
                    source_weight=excluded.source_weight,
                    freshness_decay=excluded.freshness_decay,
                    effective_weight=excluded.effective_weight,
                    legacy_untrusted=excluded.legacy_untrusted,
                    excluded_from_learning=excluded.excluded_from_learning,
                    notes=excluded.notes
                """,
                (
                    evidence_id,
                    strategy_id,
                    source_type,
                    run_id,
                    bot_id,
                    dataset_hash,
                    dataset_source,
                    as_of,
                    vintage_date,
                    int(trades or 0),
                    float(turnover or 0.0),
                    fees_bps,
                    spread_bps,
                    slippage_bps,
                    funding_bps,
                    expectancy_net,
                    sharpe,
                    sortino,
                    psr,
                    dsr,
                    pbo,
                    max_dd,
                    win_rate,
                    profit_factor,
                    float(validation_quality or 0.0),
                    float(source_weight or 0.0),
                    float(freshness_decay or 0.0),
                    float(effective_weight or 0.0),
                    1 if legacy_untrusted else 0,
                    1 if excluded_from_learning else 0,
                    notes,
                ),
            )
            conn.commit()

    def list_strategy_evidence(self, *, strategy_id: str | None = None, source_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM strategy_evidence WHERE 1=1"
        params: list[Any] = []
        if strategy_id:
            query += " AND strategy_id=?"
            params.append(strategy_id)
        if source_type:
            query += " AND source_type=?"
            params.append(source_type)
        query += " ORDER BY created_at DESC, evidence_id DESC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out = [dict(row) for row in rows]
        for row in out:
            row["legacy_untrusted"] = bool(row.get("legacy_untrusted"))
            row["excluded_from_learning"] = bool(row.get("excluded_from_learning"))
        return out

    def upsert_bot_policy_state(
        self,
        *,
        bot_id: str,
        strategy_id: str,
        regime_label: str,
        score_current: float,
        weight_target: float,
        weight_live: float,
        veto_until: str | None = None,
        veto_reason: str | None = None,
        confidence: float = 0.0,
        source_scope: str = "unknown",
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_policy_state (
                    bot_id, strategy_id, regime_label, score_current, weight_target, weight_live,
                    veto_until, veto_reason, confidence, source_scope, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(bot_id, strategy_id, regime_label) DO UPDATE SET
                    score_current=excluded.score_current,
                    weight_target=excluded.weight_target,
                    weight_live=excluded.weight_live,
                    veto_until=excluded.veto_until,
                    veto_reason=excluded.veto_reason,
                    confidence=excluded.confidence,
                    source_scope=excluded.source_scope,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    bot_id,
                    strategy_id,
                    regime_label,
                    float(score_current or 0.0),
                    float(weight_target or 0.0),
                    float(weight_live or 0.0),
                    veto_until,
                    veto_reason,
                    float(confidence or 0.0),
                    source_scope,
                ),
            )
            conn.commit()

    def list_bot_policy_state(self, *, bot_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM bot_policy_state WHERE 1=1"
        params: list[Any] = []
        if bot_id:
            query += " AND bot_id=?"
            params.append(bot_id)
        query += " ORDER BY updated_at DESC, strategy_id ASC, regime_label ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def append_bot_decision_log(
        self,
        *,
        decision_id: str,
        bot_id: str,
        timestamp: str,
        regime_label: str,
        candidate_strategies: list[dict[str, Any]] | list[str] | None = None,
        selected_strategy_id: str | None = None,
        rejected_strategies: list[dict[str, Any]] | list[str] | None = None,
        reason: dict[str, Any] | None = None,
        evidence_scope: dict[str, Any] | None = None,
        risk_overrides: dict[str, Any] | None = None,
        execution_constraints: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO bot_decision_log (
                    decision_id, bot_id, timestamp, regime_label, candidate_strategies_json, selected_strategy_id,
                    rejected_strategies_json, reason_json, evidence_scope_json, risk_overrides_json, execution_constraints_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    bot_id,
                    timestamp,
                    regime_label,
                    json.dumps(candidate_strategies or [], ensure_ascii=True, sort_keys=True),
                    selected_strategy_id,
                    json.dumps(rejected_strategies or [], ensure_ascii=True, sort_keys=True),
                    json.dumps(reason or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(evidence_scope or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(risk_overrides or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(execution_constraints or {}, ensure_ascii=True, sort_keys=True),
                ),
            )
            conn.commit()

    def list_bot_decision_log(self, *, bot_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM bot_decision_log WHERE 1=1"
        params: list[Any] = []
        if bot_id:
            query += " AND bot_id=?"
            params.append(bot_id)
        query += " ORDER BY timestamp DESC, decision_id DESC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for src, dst, default in (
                ("candidate_strategies_json", "candidate_strategies", []),
                ("rejected_strategies_json", "rejected_strategies", []),
                ("reason_json", "reason", {}),
                ("evidence_scope_json", "evidence_scope", {}),
                ("risk_overrides_json", "risk_overrides", {}),
                ("execution_constraints_json", "execution_constraints", {}),
            ):
                try:
                    item[dst] = json.loads(item.pop(src, json.dumps(default)) or json.dumps(default))
                except Exception:
                    item[dst] = default
            out.append(item)
        return out

    def upsert_run_bot_link(
        self,
        *,
        run_id: str,
        bot_id: str,
        attribution_type: str,
        attribution_confidence: float,
        created_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_bot_link (run_id, bot_id, attribution_type, attribution_confidence, created_at)
                VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(run_id, bot_id) DO UPDATE SET
                    attribution_type=excluded.attribution_type,
                    attribution_confidence=excluded.attribution_confidence,
                    created_at=COALESCE(excluded.created_at, run_bot_link.created_at)
                """,
                (
                    run_id,
                    bot_id,
                    attribution_type,
                    float(attribution_confidence or 0.0),
                    created_at,
                ),
            )
            conn.commit()

    def list_run_bot_links(self, *, run_id: str | None = None, bot_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM run_bot_link WHERE 1=1"
        params: list[Any] = []
        if run_id:
            query += " AND run_id=?"
            params.append(run_id)
        if bot_id:
            query += " AND bot_id=?"
            params.append(bot_id)
        query += " ORDER BY created_at DESC, run_id ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def upsert_execution_reality(
        self,
        *,
        execution_id: str,
        order_id: str | None = None,
        bot_id: str | None = None,
        strategy_id: str | None = None,
        symbol: str | None = None,
        timestamp: str | None = None,
        order_type: str | None = None,
        side: str | None = None,
        qty: float | None = None,
        participation_rate: float | None = None,
        expected_fill_price: float | None = None,
        realized_fill_price: float | None = None,
        realized_slippage_bps: float | None = None,
        maker_taker: str | None = None,
        partial_fill_ratio: float | None = None,
        queue_proxy: float | None = None,
        cancel_replace_count: int = 0,
        latency_ms: float | None = None,
        spread_bps: float | None = None,
        impact_bps_est: float | None = None,
        impact_budget_bps: float | None = None,
        reconciliation_status: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_reality (
                    execution_id, order_id, bot_id, strategy_id, symbol, timestamp, order_type, side, qty, participation_rate,
                    expected_fill_price, realized_fill_price, realized_slippage_bps, maker_taker, partial_fill_ratio,
                    queue_proxy, cancel_replace_count, latency_ms, spread_bps, impact_bps_est, impact_budget_bps,
                    reconciliation_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(execution_id) DO UPDATE SET
                    order_id=excluded.order_id,
                    bot_id=excluded.bot_id,
                    strategy_id=excluded.strategy_id,
                    symbol=excluded.symbol,
                    timestamp=excluded.timestamp,
                    order_type=excluded.order_type,
                    side=excluded.side,
                    qty=excluded.qty,
                    participation_rate=excluded.participation_rate,
                    expected_fill_price=excluded.expected_fill_price,
                    realized_fill_price=excluded.realized_fill_price,
                    realized_slippage_bps=excluded.realized_slippage_bps,
                    maker_taker=excluded.maker_taker,
                    partial_fill_ratio=excluded.partial_fill_ratio,
                    queue_proxy=excluded.queue_proxy,
                    cancel_replace_count=excluded.cancel_replace_count,
                    latency_ms=excluded.latency_ms,
                    spread_bps=excluded.spread_bps,
                    impact_bps_est=excluded.impact_bps_est,
                    impact_budget_bps=excluded.impact_budget_bps,
                    reconciliation_status=excluded.reconciliation_status
                """,
                (
                    execution_id,
                    order_id,
                    bot_id,
                    strategy_id,
                    symbol,
                    timestamp,
                    order_type,
                    side,
                    qty,
                    participation_rate,
                    expected_fill_price,
                    realized_fill_price,
                    realized_slippage_bps,
                    maker_taker,
                    partial_fill_ratio,
                    queue_proxy,
                    int(cancel_replace_count or 0),
                    latency_ms,
                    spread_bps,
                    impact_bps_est,
                    impact_budget_bps,
                    reconciliation_status,
                ),
            )
            conn.commit()

    def list_execution_reality(
        self,
        *,
        bot_id: str | None = None,
        strategy_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM execution_reality WHERE 1=1"
        params: list[Any] = []
        if bot_id:
            query += " AND bot_id=?"
            params.append(bot_id)
        if strategy_id:
            query += " AND strategy_id=?"
            params.append(strategy_id)
        query += " ORDER BY timestamp DESC, created_at DESC"
        if limit:
            query += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    def upsert_instrument_registry(
        self,
        *,
        instrument_id: str,
        provider: str,
        provider_market: str,
        provider_symbol: str,
        normalized_symbol: str,
        base_asset: str | None = None,
        quote_asset: str | None = None,
        settle_asset: str | None = None,
        margin_asset: str | None = None,
        asset_class: str = "unknown",
        contract_type: str | None = None,
        instrument_type: str | None = None,
        status: str = "unknown",
        tradable: bool = False,
        backtestable: bool = False,
        paper_enabled: bool = False,
        test_enabled: bool = False,
        demo_enabled: bool = False,
        live_enabled: bool = False,
        permissions: list[str] | None = None,
        order_types: list[str] | None = None,
        time_in_force: list[str] | None = None,
        tick_size: float | None = None,
        step_size: float | None = None,
        min_qty: float | None = None,
        max_qty: float | None = None,
        min_notional: float | None = None,
        price_precision: int | None = None,
        qty_precision: int | None = None,
        maker_fee_bps: float | None = None,
        taker_fee_bps: float | None = None,
        funding_interval_hours: float | None = None,
        onboard_date: str | None = None,
        delivery_date: str | None = None,
        exchange_filters: dict[str, Any] | None = None,
        symbol_filters: dict[str, Any] | None = None,
        raw_exchange_payload: dict[str, Any] | None = None,
        account_eligibility: dict[str, Any] | None = None,
        source_hash: str | None = None,
        is_active_snapshot: bool = True,
        first_seen_at: str | None = None,
        last_seen_at: str | None = None,
        delisted_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO instrument_registry (
                    instrument_id, provider, provider_market, provider_symbol, normalized_symbol,
                    base_asset, quote_asset, settle_asset, margin_asset, asset_class,
                    contract_type, instrument_type, status, tradable, backtestable,
                    paper_enabled, test_enabled, demo_enabled, live_enabled,
                    permissions_json, order_types_json, time_in_force_json,
                    tick_size, step_size, min_qty, max_qty, min_notional,
                    price_precision, qty_precision, maker_fee_bps, taker_fee_bps,
                    funding_interval_hours, onboard_date, delivery_date,
                    exchange_filters_json, symbol_filters_json, raw_exchange_payload_json,
                    account_eligibility_json, source_hash, is_active_snapshot,
                    first_seen_at, last_seen_at, delisted_at
                )
                VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?,
                    COALESCE(?, CURRENT_TIMESTAMP), COALESCE(?, CURRENT_TIMESTAMP), ?
                )
                ON CONFLICT(instrument_id) DO UPDATE SET
                    provider=excluded.provider,
                    provider_market=excluded.provider_market,
                    provider_symbol=excluded.provider_symbol,
                    normalized_symbol=excluded.normalized_symbol,
                    base_asset=excluded.base_asset,
                    quote_asset=excluded.quote_asset,
                    settle_asset=excluded.settle_asset,
                    margin_asset=excluded.margin_asset,
                    asset_class=excluded.asset_class,
                    contract_type=excluded.contract_type,
                    instrument_type=excluded.instrument_type,
                    status=excluded.status,
                    tradable=excluded.tradable,
                    backtestable=excluded.backtestable,
                    paper_enabled=excluded.paper_enabled,
                    test_enabled=excluded.test_enabled,
                    demo_enabled=excluded.demo_enabled,
                    live_enabled=excluded.live_enabled,
                    permissions_json=excluded.permissions_json,
                    order_types_json=excluded.order_types_json,
                    time_in_force_json=excluded.time_in_force_json,
                    tick_size=excluded.tick_size,
                    step_size=excluded.step_size,
                    min_qty=excluded.min_qty,
                    max_qty=excluded.max_qty,
                    min_notional=excluded.min_notional,
                    price_precision=excluded.price_precision,
                    qty_precision=excluded.qty_precision,
                    maker_fee_bps=excluded.maker_fee_bps,
                    taker_fee_bps=excluded.taker_fee_bps,
                    funding_interval_hours=excluded.funding_interval_hours,
                    onboard_date=excluded.onboard_date,
                    delivery_date=excluded.delivery_date,
                    exchange_filters_json=excluded.exchange_filters_json,
                    symbol_filters_json=excluded.symbol_filters_json,
                    raw_exchange_payload_json=excluded.raw_exchange_payload_json,
                    account_eligibility_json=excluded.account_eligibility_json,
                    source_hash=excluded.source_hash,
                    is_active_snapshot=excluded.is_active_snapshot,
                    last_seen_at=COALESCE(excluded.last_seen_at, CURRENT_TIMESTAMP),
                    delisted_at=excluded.delisted_at
                """,
                (
                    instrument_id,
                    provider,
                    provider_market,
                    provider_symbol,
                    normalized_symbol,
                    base_asset,
                    quote_asset,
                    settle_asset,
                    margin_asset,
                    asset_class,
                    contract_type,
                    instrument_type,
                    status,
                    1 if tradable else 0,
                    1 if backtestable else 0,
                    1 if paper_enabled else 0,
                    1 if test_enabled else 0,
                    1 if demo_enabled else 0,
                    1 if live_enabled else 0,
                    json.dumps(permissions or [], ensure_ascii=True, sort_keys=True),
                    json.dumps(order_types or [], ensure_ascii=True, sort_keys=True),
                    json.dumps(time_in_force or [], ensure_ascii=True, sort_keys=True),
                    tick_size,
                    step_size,
                    min_qty,
                    max_qty,
                    min_notional,
                    price_precision,
                    qty_precision,
                    maker_fee_bps,
                    taker_fee_bps,
                    funding_interval_hours,
                    onboard_date,
                    delivery_date,
                    json.dumps(exchange_filters or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(symbol_filters or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(raw_exchange_payload or {}, ensure_ascii=True, sort_keys=True),
                    json.dumps(account_eligibility or {}, ensure_ascii=True, sort_keys=True),
                    source_hash,
                    1 if is_active_snapshot else 0,
                    first_seen_at,
                    last_seen_at,
                    delisted_at,
                ),
            )
            conn.commit()

    def list_instrument_registry(
        self,
        *,
        provider: str | None = None,
        provider_market: str | None = None,
        normalized_symbol: str | None = None,
        live_enabled: bool | None = None,
        tradable: bool | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM instrument_registry WHERE 1=1"
        params: list[Any] = []
        if provider:
            query += " AND provider=?"
            params.append(provider)
        if provider_market:
            query += " AND provider_market=?"
            params.append(provider_market)
        if normalized_symbol:
            query += " AND normalized_symbol=?"
            params.append(normalized_symbol)
        if live_enabled is not None:
            query += " AND live_enabled=?"
            params.append(1 if live_enabled else 0)
        if tradable is not None:
            query += " AND tradable=?"
            params.append(1 if tradable else 0)
        query += " ORDER BY provider_market ASC, normalized_symbol ASC, provider_symbol ASC"
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for src, dst, default in (
                ("permissions_json", "permissions", []),
                ("order_types_json", "order_types", []),
                ("time_in_force_json", "time_in_force", []),
                ("exchange_filters_json", "exchange_filters", {}),
                ("symbol_filters_json", "symbol_filters", {}),
                ("raw_exchange_payload_json", "raw_exchange_payload", {}),
                ("account_eligibility_json", "account_eligibility", {}),
            ):
                try:
                    item[dst] = json.loads(item.pop(src, json.dumps(default)) or json.dumps(default))
                except Exception:
                    item[dst] = default
            for key in (
                "tradable",
                "backtestable",
                "paper_enabled",
                "test_enabled",
                "demo_enabled",
                "live_enabled",
                "is_active_snapshot",
            ):
                item[key] = bool(item.get(key))
            out.append(item)
        return out

    def get_instrument_registry(self, instrument_id: str) -> dict[str, Any] | None:
        rows = self.list_instrument_registry()
        for row in rows:
            if row.get("instrument_id") == instrument_id:
                return row
        return None

    def upsert_instrument_catalog_snapshot(
        self,
        *,
        snapshot_id: str,
        provider: str,
        provider_market: str,
        catalog_hash: str,
        items: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        status: str = "active",
        created_at: str | None = None,
    ) -> None:
        tradable_instruments = sum(1 for item in items if item.get("tradable"))
        live_enabled_instruments = sum(1 for item in items if item.get("live_enabled"))
        backtestable_instruments = sum(1 for item in items if item.get("backtestable"))
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO instrument_catalog_snapshot (
                    snapshot_id, provider, provider_market, catalog_hash, status,
                    total_instruments, tradable_instruments, live_enabled_instruments,
                    backtestable_instruments, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                ON CONFLICT(snapshot_id) DO UPDATE SET
                    provider=excluded.provider,
                    provider_market=excluded.provider_market,
                    catalog_hash=excluded.catalog_hash,
                    status=excluded.status,
                    total_instruments=excluded.total_instruments,
                    tradable_instruments=excluded.tradable_instruments,
                    live_enabled_instruments=excluded.live_enabled_instruments,
                    backtestable_instruments=excluded.backtestable_instruments,
                    metadata_json=excluded.metadata_json,
                    created_at=COALESCE(excluded.created_at, instrument_catalog_snapshot.created_at)
                """,
                (
                    snapshot_id,
                    provider,
                    provider_market,
                    catalog_hash,
                    status,
                    len(items),
                    tradable_instruments,
                    live_enabled_instruments,
                    backtestable_instruments,
                    json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True),
                    created_at,
                ),
            )
            conn.execute("DELETE FROM instrument_catalog_snapshot_item WHERE snapshot_id=?", (snapshot_id,))
            for item in items:
                conn.execute(
                    """
                    INSERT INTO instrument_catalog_snapshot_item (
                        snapshot_id, instrument_id, provider_symbol, normalized_symbol, status,
                        tradable, backtestable, paper_enabled, test_enabled, demo_enabled, live_enabled, snapshot_payload_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        str(item.get("instrument_id") or ""),
                        str(item.get("provider_symbol") or ""),
                        str(item.get("normalized_symbol") or ""),
                        str(item.get("status") or "unknown"),
                        1 if item.get("tradable") else 0,
                        1 if item.get("backtestable") else 0,
                        1 if item.get("paper_enabled") else 0,
                        1 if item.get("test_enabled") else 0,
                        1 if item.get("demo_enabled") else 0,
                        1 if item.get("live_enabled") else 0,
                        json.dumps(item, ensure_ascii=True, sort_keys=True),
                    ),
                )
            conn.commit()

    def list_instrument_catalog_snapshots(
        self,
        *,
        provider: str | None = None,
        provider_market: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM instrument_catalog_snapshot WHERE 1=1"
        params: list[Any] = []
        if provider:
            query += " AND provider=?"
            params.append(provider)
        if provider_market:
            query += " AND provider_market=?"
            params.append(provider_market)
        query += " ORDER BY created_at DESC, snapshot_id DESC"
        if limit:
            query += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        out = [dict(row) for row in rows]
        for row in out:
            try:
                row["metadata"] = json.loads(row.pop("metadata_json", "{}") or "{}")
            except Exception:
                row["metadata"] = {}
        return out

    def list_instrument_catalog_snapshot_items(self, snapshot_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM instrument_catalog_snapshot_item
                WHERE snapshot_id=?
                ORDER BY normalized_symbol ASC, provider_symbol ASC
                """,
                (snapshot_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                payload = json.loads(item.pop("snapshot_payload_json", "{}") or "{}")
            except Exception:
                payload = {}
            item["snapshot_payload"] = payload
            for key in (
                "tradable",
                "backtestable",
                "paper_enabled",
                "test_enabled",
                "demo_enabled",
                "live_enabled",
            ):
                item[key] = bool(item.get(key))
            out.append(item)
        return out

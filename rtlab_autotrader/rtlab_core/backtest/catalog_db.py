from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_json(value: Any, default: Any) -> str:
    payload = value if value is not None else default
    try:
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)
    except Exception:
        return json.dumps(default, ensure_ascii=True, sort_keys=True)


def _short_hash(value: Any, length: int = 12) -> str:
    try:
        raw = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    except Exception:
        raw = str(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


class BacktestCatalogDB:
    """Catalogo SQLite incremental para identidad/trazabilidad de runs y batches.

    No reemplaza runs.json ni metadata existente. Se usa como indice estructurado.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        try:
            rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        except Exception:
            return set()
        return {str(r["name"]) for r in rows if r and r["name"]}

    def _ensure_columns(self, conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = self._table_columns(conn, table)
        for name, ddl in columns.items():
            if name in existing:
                continue
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        self._ensure_columns(
            conn,
            "backtest_runs",
            {
                "fee_snapshot_id": "TEXT",
                "funding_snapshot_id": "TEXT",
                "slippage_model_params": "TEXT NOT NULL DEFAULT '{}'",
                "spread_model_params": "TEXT NOT NULL DEFAULT '{}'",
            },
        )

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS id_sequences (
                  prefix TEXT PRIMARY KEY,
                  next_value INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS backtest_runs (
                  run_id TEXT PRIMARY KEY,
                  legacy_json_id TEXT,
                  run_type TEXT NOT NULL,
                  batch_id TEXT,
                  parent_run_id TEXT,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  started_at TEXT,
                  finished_at TEXT,
                  created_by TEXT NOT NULL,
                  mode TEXT NOT NULL,

                  strategy_id TEXT NOT NULL,
                  strategy_name TEXT NOT NULL,
                  strategy_version TEXT NOT NULL,
                  strategy_config_hash TEXT NOT NULL,
                  code_commit_hash TEXT NOT NULL,

                  dataset_source TEXT NOT NULL,
                  dataset_version TEXT NOT NULL,
                  dataset_hash TEXT NOT NULL,
                  symbols_json TEXT NOT NULL,
                  timeframes_json TEXT NOT NULL,
                  timerange_from TEXT NOT NULL,
                  timerange_to TEXT NOT NULL,
                  timezone TEXT NOT NULL,
                  missing_data_policy TEXT NOT NULL,

                  fee_model TEXT NOT NULL,
                  spread_model TEXT NOT NULL,
                  slippage_model TEXT NOT NULL,
                  funding_model TEXT NOT NULL,
                  fee_snapshot_id TEXT,
                  funding_snapshot_id TEXT,
                  slippage_model_params TEXT NOT NULL DEFAULT '{}',
                  spread_model_params TEXT NOT NULL DEFAULT '{}',
                  latency_model TEXT,
                  fill_model TEXT NOT NULL,
                  initial_capital REAL NOT NULL,
                  position_sizing_profile TEXT NOT NULL,
                  max_open_positions INTEGER NOT NULL,

                  params_json TEXT NOT NULL,
                  seed INTEGER,

                  hf_model_id TEXT,
                  hf_revision TEXT,
                  hf_commit_hash TEXT,
                  pipeline_task TEXT,
                  inference_mode TEXT,

                  alias TEXT,
                  tags_json TEXT NOT NULL,
                  pinned INTEGER NOT NULL DEFAULT 0,
                  title_structured TEXT NOT NULL,
                  subtitle_structured TEXT NOT NULL,

                  kpi_summary_json TEXT NOT NULL,
                  regime_kpis_json TEXT NOT NULL,
                  flags_json TEXT NOT NULL,
                  artifacts_json TEXT NOT NULL,

                  updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_backtest_runs_created_at ON backtest_runs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_backtest_runs_batch_id ON backtest_runs(batch_id);
                CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy_id ON backtest_runs(strategy_id);
                CREATE INDEX IF NOT EXISTS idx_backtest_runs_status ON backtest_runs(status);

                CREATE TABLE IF NOT EXISTS backtest_batches (
                  batch_id TEXT PRIMARY KEY,
                  objective TEXT NOT NULL,
                  universe_json TEXT NOT NULL,
                  variables_explored_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  started_at TEXT,
                  finished_at TEXT,
                  status TEXT NOT NULL,
                  run_count_total INTEGER NOT NULL,
                  run_count_done INTEGER NOT NULL,
                  run_count_failed INTEGER NOT NULL,
                  best_runs_cache_json TEXT NOT NULL,
                  config_json TEXT NOT NULL,
                  summary_json TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_backtest_batches_created_at ON backtest_batches(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_backtest_batches_status ON backtest_batches(status);

                CREATE TABLE IF NOT EXISTS artifacts_index (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT,
                  batch_id TEXT,
                  artifact_kind TEXT NOT NULL,
                  artifact_path TEXT NOT NULL,
                  artifact_url TEXT,
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts_index(run_id);
                CREATE INDEX IF NOT EXISTS idx_artifacts_batch_id ON artifacts_index(batch_id);

                CREATE TABLE IF NOT EXISTS fee_snapshots (
                  snapshot_id TEXT PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  market TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  maker_fee REAL NOT NULL,
                  taker_fee REAL NOT NULL,
                  commission_rate REAL,
                  source TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  fetched_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_fee_snapshots_lookup ON fee_snapshots(exchange, market, symbol, fetched_at DESC);

                CREATE TABLE IF NOT EXISTS funding_snapshots (
                  snapshot_id TEXT PRIMARY KEY,
                  exchange TEXT NOT NULL,
                  market TEXT NOT NULL,
                  symbol TEXT NOT NULL,
                  funding_rate REAL,
                  funding_bps REAL NOT NULL,
                  source TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  fetched_at TEXT NOT NULL,
                  expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_funding_snapshots_lookup ON funding_snapshots(exchange, market, symbol, fetched_at DESC);
                """
            )
            self._migrate_schema(conn)
            conn.commit()

    def next_formatted_id(self, prefix: str, *, width: int = 6) -> str:
        px = str(prefix).upper()
        with self._connect() as conn:
            row = conn.execute("SELECT next_value FROM id_sequences WHERE prefix = ?", (px,)).fetchone()
            if row is None:
                next_val = 1
                conn.execute("INSERT INTO id_sequences (prefix, next_value) VALUES (?, ?)", (px, 2))
            else:
                next_val = int(row["next_value"])
                conn.execute("UPDATE id_sequences SET next_value = ? WHERE prefix = ?", (next_val + 1, px))
            conn.commit()
        return f"{px}-{next_val:0{width}d}"

    def _default_run_record(self) -> dict[str, Any]:
        now = _utc_iso()
        return {
            "run_id": "",
            "legacy_json_id": None,
            "run_type": "single",
            "batch_id": None,
            "parent_run_id": None,
            "status": "queued",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "created_by": "system",
            "mode": "backtest",
            "strategy_id": "",
            "strategy_name": "",
            "strategy_version": "0.0.0",
            "strategy_config_hash": "",
            "code_commit_hash": "local",
            "dataset_source": "",
            "dataset_version": "",
            "dataset_hash": "",
            "symbols_json": "[]",
            "timeframes_json": "[]",
            "timerange_from": "",
            "timerange_to": "",
            "timezone": "UTC",
            "missing_data_policy": "warn_skip",
            "fee_model": "maker_taker_bps",
            "spread_model": "static",
            "slippage_model": "static",
            "funding_model": "static",
            "fee_snapshot_id": None,
            "funding_snapshot_id": None,
            "slippage_model_params": "{}",
            "spread_model_params": "{}",
            "latency_model": None,
            "fill_model": "market",
            "initial_capital": 10000.0,
            "position_sizing_profile": "default",
            "max_open_positions": 1,
            "params_json": "{}",
            "seed": None,
            "hf_model_id": None,
            "hf_revision": None,
            "hf_commit_hash": None,
            "pipeline_task": None,
            "inference_mode": None,
            "alias": None,
            "tags_json": "[]",
            "pinned": 0,
            "title_structured": "",
            "subtitle_structured": "",
            "kpi_summary_json": "{}",
            "regime_kpis_json": "{}",
            "flags_json": "{}",
            "artifacts_json": "{}",
            "updated_at": now,
        }

    def _default_batch_record(self) -> dict[str, Any]:
        now = _utc_iso()
        return {
            "batch_id": "",
            "objective": "",
            "universe_json": "{}",
            "variables_explored_json": "{}",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "status": "queued",
            "run_count_total": 0,
            "run_count_done": 0,
            "run_count_failed": 0,
            "best_runs_cache_json": "[]",
            "config_json": "{}",
            "summary_json": "{}",
            "updated_at": now,
        }

    def _structured_title(self, row: dict[str, Any]) -> tuple[str, str]:
        run_id = str(row.get("run_id") or "")
        stid = str(row.get("strategy_id") or "-")
        sname = str(row.get("strategy_name") or stid)
        sv = str(row.get("strategy_version") or "-")
        symbols = []
        try:
            symbols = json.loads(str(row.get("symbols_json") or "[]"))
        except Exception:
            symbols = []
        tfs = []
        try:
            tfs = json.loads(str(row.get("timeframes_json") or "[]"))
        except Exception:
            tfs = []
        symbol = str(symbols[0]) if isinstance(symbols, list) and symbols else "-"
        tf = str(tfs[0]) if isinstance(tfs, list) and tfs else "-"
        dsrc = str(row.get("dataset_source") or "-")
        created = str(row.get("created_at") or "")
        created_short = created[:16].replace("T", " ") if created else "-"
        title = f"{run_id} · {stid} {sname} v{sv} · {symbol} · {tf} · {dsrc} · {created_short}"
        subtitle = (
            f"Rango: {row.get('timerange_from') or '-'}→{row.get('timerange_to') or '-'}"
            f" · Régimen: all · Fee {row.get('fee_model') or '-'}"
            f" · Slippage: {row.get('slippage_model') or '-'} · Dataset: {row.get('dataset_version') or '-'}"
        )
        return title, subtitle

    def upsert_backtest_run(self, data: dict[str, Any]) -> dict[str, Any]:
        row = self._default_run_record()
        row.update({k: v for k, v in data.items() if k in row})
        for json_field in ("slippage_model_params", "spread_model_params"):
            if not isinstance(row.get(json_field), str):
                row[json_field] = _to_json(row.get(json_field), {})
        row["updated_at"] = _utc_iso()
        if not row["run_id"]:
            row["run_id"] = self.next_formatted_id("BT")
        if not row["title_structured"] or not row["subtitle_structured"]:
            title, subtitle = self._structured_title(row)
            row["title_structured"] = title
            row["subtitle_structured"] = subtitle
        cols = list(row.keys())
        placeholders = ",".join(["?"] * len(cols))
        assignments = ",".join([f"{c}=excluded.{c}" for c in cols if c != "run_id"])
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO backtest_runs ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(run_id) DO UPDATE SET {assignments}",
                [row[c] for c in cols],
            )
            conn.commit()
        return row

    def upsert_backtest_batch(self, data: dict[str, Any]) -> dict[str, Any]:
        row = self._default_batch_record()
        row.update({k: v for k, v in data.items() if k in row})
        row["updated_at"] = _utc_iso()
        if not row["batch_id"]:
            row["batch_id"] = self.next_formatted_id("BX")
        cols = list(row.keys())
        placeholders = ",".join(["?"] * len(cols))
        assignments = ",".join([f"{c}=excluded.{c}" for c in cols if c != "batch_id"])
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO backtest_batches ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(batch_id) DO UPDATE SET {assignments}",
                [row[c] for c in cols],
            )
            conn.commit()
        return row

    def patch_batch(
        self,
        batch_id: str,
        *,
        objective: str | None = None,
        status: str | None = None,
        best_runs_cache: list[dict[str, Any]] | None = None,
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        current = self.get_batch(batch_id)
        if not current:
            return None

        updates: dict[str, Any] = {}
        if objective is not None:
            updates["objective"] = str(objective or "").strip()
        if status is not None:
            updates["status"] = str(status or "").strip().lower() or str(current.get("status") or "queued")
        if best_runs_cache is not None:
            updates["best_runs_cache_json"] = _to_json(best_runs_cache, [])
        if summary is not None:
            updates["summary_json"] = _to_json(summary, {})
        if not updates:
            return current

        updates["updated_at"] = _utc_iso()
        assignments = ", ".join(f"{k}=?" for k in updates.keys())
        values = list(updates.values()) + [str(batch_id)]
        with self._connect() as conn:
            conn.execute(f"UPDATE backtest_batches SET {assignments} WHERE batch_id = ?", values)
            conn.commit()
        return self.get_batch(batch_id)

    def add_artifact(self, *, run_id: str | None, batch_id: str | None, kind: str, path: str, url: str | None = None) -> None:
        with self._connect() as conn:
            exists = conn.execute(
                """
                SELECT 1 FROM artifacts_index
                WHERE COALESCE(run_id,'') = COALESCE(?, '')
                  AND COALESCE(batch_id,'') = COALESCE(?, '')
                  AND artifact_kind = ?
                  AND artifact_path = ?
                LIMIT 1
                """,
                (run_id, batch_id, kind, path),
            ).fetchone()
            if exists:
                return
            conn.execute(
                """
                INSERT INTO artifacts_index (run_id, batch_id, artifact_kind, artifact_path, artifact_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, batch_id, kind, path, url, _utc_iso()),
            )
            conn.commit()

    def _row_to_fee_snapshot(self, row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        raw = dict(row)
        try:
            raw["payload"] = json.loads(str(raw.get("payload_json") or "{}"))
        except Exception:
            raw["payload"] = {}
        return {
            "snapshot_id": raw.get("snapshot_id"),
            "exchange": raw.get("exchange"),
            "market": raw.get("market"),
            "symbol": raw.get("symbol"),
            "maker_fee": float(raw.get("maker_fee") or 0.0),
            "taker_fee": float(raw.get("taker_fee") or 0.0),
            "commission_rate": None if raw.get("commission_rate") is None else float(raw.get("commission_rate")),
            "source": raw.get("source"),
            "payload": raw.get("payload") or {},
            "fetched_at": raw.get("fetched_at"),
            "expires_at": raw.get("expires_at"),
        }

    def _row_to_funding_snapshot(self, row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        raw = dict(row)
        try:
            raw["payload"] = json.loads(str(raw.get("payload_json") or "{}"))
        except Exception:
            raw["payload"] = {}
        return {
            "snapshot_id": raw.get("snapshot_id"),
            "exchange": raw.get("exchange"),
            "market": raw.get("market"),
            "symbol": raw.get("symbol"),
            "funding_rate": None if raw.get("funding_rate") is None else float(raw.get("funding_rate")),
            "funding_bps": float(raw.get("funding_bps") or 0.0),
            "source": raw.get("source"),
            "payload": raw.get("payload") or {},
            "fetched_at": raw.get("fetched_at"),
            "expires_at": raw.get("expires_at"),
        }

    def latest_valid_fee_snapshot(self, *, exchange: str, market: str, symbol: str, as_of: str | None = None) -> dict[str, Any] | None:
        ref = str(as_of or _utc_iso())
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM fee_snapshots
                WHERE exchange = ? AND market = ? AND symbol = ? AND expires_at > ?
                ORDER BY fetched_at DESC, snapshot_id DESC
                LIMIT 1
                """,
                (str(exchange).lower(), str(market).lower(), str(symbol).upper(), ref),
            ).fetchone()
        return self._row_to_fee_snapshot(row)

    def latest_valid_funding_snapshot(self, *, exchange: str, market: str, symbol: str, as_of: str | None = None) -> dict[str, Any] | None:
        ref = str(as_of or _utc_iso())
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM funding_snapshots
                WHERE exchange = ? AND market = ? AND symbol = ? AND expires_at > ?
                ORDER BY fetched_at DESC, snapshot_id DESC
                LIMIT 1
                """,
                (str(exchange).lower(), str(market).lower(), str(symbol).upper(), ref),
            ).fetchone()
        return self._row_to_funding_snapshot(row)

    def insert_fee_snapshot(
        self,
        *,
        exchange: str,
        market: str,
        symbol: str,
        maker_fee: float,
        taker_fee: float,
        commission_rate: float | None,
        source: str,
        payload: dict[str, Any] | None,
        fetched_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        snapshot_id = self.next_formatted_id("FS")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO fee_snapshots
                (snapshot_id, exchange, market, symbol, maker_fee, taker_fee, commission_rate, source, payload_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    str(exchange).lower(),
                    str(market).lower(),
                    str(symbol).upper(),
                    float(maker_fee),
                    float(taker_fee),
                    None if commission_rate is None else float(commission_rate),
                    str(source),
                    _to_json(payload or {}, {}),
                    str(fetched_at),
                    str(expires_at),
                ),
            )
            conn.commit()
        return self._row_to_fee_snapshot(
            {
                "snapshot_id": snapshot_id,
                "exchange": str(exchange).lower(),
                "market": str(market).lower(),
                "symbol": str(symbol).upper(),
                "maker_fee": float(maker_fee),
                "taker_fee": float(taker_fee),
                "commission_rate": None if commission_rate is None else float(commission_rate),
                "source": str(source),
                "payload_json": _to_json(payload or {}, {}),
                "fetched_at": str(fetched_at),
                "expires_at": str(expires_at),
            }
        ) or {}

    def insert_funding_snapshot(
        self,
        *,
        exchange: str,
        market: str,
        symbol: str,
        funding_rate: float | None,
        funding_bps: float,
        source: str,
        payload: dict[str, Any] | None,
        fetched_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        snapshot_id = self.next_formatted_id("FN")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO funding_snapshots
                (snapshot_id, exchange, market, symbol, funding_rate, funding_bps, source, payload_json, fetched_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    str(exchange).lower(),
                    str(market).lower(),
                    str(symbol).upper(),
                    None if funding_rate is None else float(funding_rate),
                    float(funding_bps),
                    str(source),
                    _to_json(payload or {}, {}),
                    str(fetched_at),
                    str(expires_at),
                ),
            )
            conn.commit()
        return self._row_to_funding_snapshot(
            {
                "snapshot_id": snapshot_id,
                "exchange": str(exchange).lower(),
                "market": str(market).lower(),
                "symbol": str(symbol).upper(),
                "funding_rate": None if funding_rate is None else float(funding_rate),
                "funding_bps": float(funding_bps),
                "source": str(source),
                "payload_json": _to_json(payload or {}, {}),
                "fetched_at": str(fetched_at),
                "expires_at": str(expires_at),
            }
        ) or {}

    def record_run_from_payload(self, *, run: dict[str, Any], strategy_meta: dict[str, Any] | None = None, created_by: str = "system") -> str:
        strategy = strategy_meta or {}
        costs = run.get("costs_model") if isinstance(run.get("costs_model"), dict) else {}
        metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        provenance = run.get("provenance") if isinstance(run.get("provenance"), dict) else {}
        spread_model_params = run.get("spread_model_params")
        slippage_model_params = run.get("slippage_model_params")
        trades = run.get("trades") if isinstance(run.get("trades"), list) else []
        regime_rows: dict[str, Any] = {}
        for label in ("trend", "range", "high_vol", "toxic"):
            label_trades = [t for t in trades if isinstance(t, dict) and str(t.get("regime_label") or "") == label]
            if not label_trades:
                continue
            pnls = [float(t.get("pnl_net", 0.0) or 0.0) for t in label_trades]
            wins = sum(1 for p in pnls if p > 0)
            regime_rows[label] = {
                "trade_count": len(label_trades),
                "winrate": round(wins / max(1, len(label_trades)), 6),
                "expectancy_value": round(sum(pnls) / max(1, len(pnls)), 6),
                "expectancy_unit": "usd_per_trade",
                "net_pnl": round(sum(pnls), 6),
            }

        raw_id = str(run.get("id") or "")
        catalog_run_id = str(run.get("catalog_run_id") or "")
        run_id = catalog_run_id or (raw_id if raw_id.startswith("BT-") else self.next_formatted_id("BT"))
        data_source = str(run.get("data_source") or provenance.get("dataset_source") or "unknown")
        dataset_manifest = run.get("dataset_manifest") if isinstance(run.get("dataset_manifest"), dict) else {}
        dataset_version = str(
            dataset_manifest.get("version")
            or dataset_manifest.get("dataset_version")
            or run.get("dataset_version")
            or ("ohlcv_v1" if data_source else "unknown")
        )
        symbol = str(run.get("symbol") or "")
        timeframe = str(run.get("timeframe") or "")
        universe = run.get("universe") if isinstance(run.get("universe"), list) else ([symbol] if symbol else [])
        timeframes = [timeframe] if timeframe else []
        strategy_name = str((strategy or {}).get("name") or run.get("strategy_name") or run.get("strategy_id") or "")
        strategy_version = str((strategy or {}).get("version") or run.get("strategy_version") or "0.0.0")
        params_payload = {
            "validation_mode": run.get("validation_mode"),
            "costs_model": costs,
            "dataset_range": run.get("dataset_range"),
            "period": run.get("period"),
        }
        status = str(run.get("status") or "completed").lower()
        finished_at = str(run.get("finished_at") or "") or (str(run.get("created_at") or "") if status in {"completed", "failed"} else None)
        started_at = str(run.get("started_at") or "") or (str(run.get("created_at") or "") if status in {"running", "completed", "failed"} else None)
        record = self.upsert_backtest_run(
            {
                "run_id": run_id,
                "legacy_json_id": raw_id or None,
                "run_type": str(run.get("run_type") or "single"),
                "batch_id": run.get("batch_id"),
                "parent_run_id": run.get("parent_run_id"),
                "status": status if status in {"queued", "preparing", "running", "completed", "completed_warn", "failed", "canceled", "archived"} else "completed",
                "created_at": str(run.get("created_at") or _utc_iso()),
                "started_at": started_at,
                "finished_at": finished_at,
                "created_by": str(run.get("created_by") or created_by),
                "mode": str(run.get("mode") or "backtest"),
                "strategy_id": str((strategy or {}).get("structured_id") or run.get("strategy_id") or ""),
                "strategy_name": strategy_name,
                "strategy_version": strategy_version,
                "strategy_config_hash": str(run.get("strategy_config_hash") or _short_hash(params_payload)),
                "code_commit_hash": str(run.get("git_commit") or provenance.get("commit_hash") or "local"),
                "dataset_source": data_source,
                "dataset_version": dataset_version,
                "dataset_hash": str(run.get("dataset_hash") or provenance.get("dataset_hash") or ""),
                "symbols_json": _to_json(universe, []),
                "timeframes_json": _to_json(timeframes, []),
                "timerange_from": str(((run.get("period") or {}).get("start")) or provenance.get("from") or ""),
                "timerange_to": str(((run.get("period") or {}).get("end")) or provenance.get("to") or ""),
                "timezone": "UTC",
                "missing_data_policy": str(run.get("missing_data_policy") or "warn_skip"),
                "fee_model": str(run.get("fee_model") or f"maker_taker_bps:{float(costs.get('fees_bps', 0.0) or 0.0):.4f}"),
                "spread_model": str(run.get("spread_model") or f"static:{float(costs.get('spread_bps', 0.0) or 0.0):.4f}"),
                "slippage_model": str(run.get("slippage_model") or f"static:{float(costs.get('slippage_bps', 0.0) or 0.0):.4f}"),
                "funding_model": str(run.get("funding_model") or f"static:{float(costs.get('funding_bps', 0.0) or 0.0):.4f}"),
                "fee_snapshot_id": run.get("fee_snapshot_id") or provenance.get("fee_snapshot_id"),
                "funding_snapshot_id": run.get("funding_snapshot_id") or provenance.get("funding_snapshot_id"),
                "slippage_model_params": _to_json(
                    slippage_model_params if isinstance(slippage_model_params, dict) else (run.get("slippage_model_params") if isinstance(run.get("slippage_model_params"), dict) else {}),
                    {},
                ),
                "spread_model_params": _to_json(
                    spread_model_params if isinstance(spread_model_params, dict) else (run.get("spread_model_params") if isinstance(run.get("spread_model_params"), dict) else {}),
                    {},
                ),
                "fill_model": str(run.get("fill_model") or "market"),
                "initial_capital": float(run.get("initial_capital") or 10000.0),
                "position_sizing_profile": str(run.get("position_sizing_profile") or "default"),
                "max_open_positions": int(run.get("max_open_positions") or 1),
                "params_json": _to_json(run.get("params_json") or params_payload, {}),
                "seed": run.get("seed"),
                "hf_model_id": run.get("hf_model_id"),
                "hf_revision": run.get("hf_revision"),
                "hf_commit_hash": run.get("hf_commit_hash"),
                "pipeline_task": run.get("pipeline_task"),
                "inference_mode": run.get("inference_mode"),
                "alias": run.get("alias"),
                "tags_json": _to_json(run.get("tags") or [], []),
                "pinned": 1 if bool(run.get("pinned")) else 0,
                "kpi_summary_json": _to_json(metrics, {}),
                "regime_kpis_json": _to_json(run.get("kpis_by_regime") or regime_rows, {}),
                "flags_json": _to_json(
                    run.get("flags")
                    or {
                        "IS": False,
                        "OOS": bool(str(run.get("validation_mode") or "").lower().startswith("walk")),
                        "WFA": bool(str(run.get("validation_mode") or "").lower() == "walk-forward"),
                        "PASO_GATES": False,
                        "BASELINE": False,
                        "FAVORITO": bool(run.get("pinned")),
                        "ARCHIVADO": status == "archived",
                    },
                    {},
                ),
                "artifacts_json": _to_json(run.get("artifacts_links") or {}, {}),
            }
        )
        if not run.get("catalog_run_id"):
            run["catalog_run_id"] = record["run_id"]
        run["title_structured"] = record.get("title_structured")
        run["subtitle_structured"] = record.get("subtitle_structured")
        if str(run.get("id") or "").startswith("BT-") and run.get("id") != record["run_id"]:
            run["id"] = record["run_id"]
        return record["run_id"]

    def _row_to_run_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        raw = dict(row)
        for key in [
            "symbols_json",
            "timeframes_json",
            "params_json",
            "tags_json",
            "kpi_summary_json",
            "regime_kpis_json",
            "flags_json",
            "artifacts_json",
            "slippage_model_params",
            "spread_model_params",
        ]:
            try:
                raw[key] = json.loads(str(raw.get(key) or "null"))
            except Exception:
                raw[key] = {} if key.endswith("_json") else None
        out = {
            "run_id": raw.get("run_id"),
            "legacy_json_id": raw.get("legacy_json_id"),
            "run_type": raw.get("run_type"),
            "batch_id": raw.get("batch_id"),
            "parent_run_id": raw.get("parent_run_id"),
            "status": raw.get("status"),
            "created_at": raw.get("created_at"),
            "started_at": raw.get("started_at"),
            "finished_at": raw.get("finished_at"),
            "created_by": raw.get("created_by"),
            "mode": raw.get("mode"),
            "strategy_id": raw.get("strategy_id"),
            "strategy_name": raw.get("strategy_name"),
            "strategy_version": raw.get("strategy_version"),
            "strategy_config_hash": raw.get("strategy_config_hash"),
            "code_commit_hash": raw.get("code_commit_hash"),
            "dataset_source": raw.get("dataset_source"),
            "dataset_version": raw.get("dataset_version"),
            "dataset_hash": raw.get("dataset_hash"),
            "symbols": raw.get("symbols_json") or [],
            "timeframes": raw.get("timeframes_json") or [],
            "timerange_from": raw.get("timerange_from"),
            "timerange_to": raw.get("timerange_to"),
            "timezone": raw.get("timezone"),
            "missing_data_policy": raw.get("missing_data_policy"),
            "fee_model": raw.get("fee_model"),
            "spread_model": raw.get("spread_model"),
            "slippage_model": raw.get("slippage_model"),
            "funding_model": raw.get("funding_model"),
            "fee_snapshot_id": raw.get("fee_snapshot_id"),
            "funding_snapshot_id": raw.get("funding_snapshot_id"),
            "slippage_model_params": raw.get("slippage_model_params") or {},
            "spread_model_params": raw.get("spread_model_params") or {},
            "latency_model": raw.get("latency_model"),
            "fill_model": raw.get("fill_model"),
            "initial_capital": raw.get("initial_capital"),
            "position_sizing_profile": raw.get("position_sizing_profile"),
            "max_open_positions": raw.get("max_open_positions"),
            "params_json": raw.get("params_json") or {},
            "seed": raw.get("seed"),
            "hf_model_id": raw.get("hf_model_id"),
            "hf_revision": raw.get("hf_revision"),
            "hf_commit_hash": raw.get("hf_commit_hash"),
            "pipeline_task": raw.get("pipeline_task"),
            "inference_mode": raw.get("inference_mode"),
            "alias": raw.get("alias"),
            "tags": raw.get("tags_json") or [],
            "pinned": bool(raw.get("pinned")),
            "title_structured": raw.get("title_structured"),
            "subtitle_structured": raw.get("subtitle_structured"),
            "kpis": raw.get("kpi_summary_json") or {},
            "kpis_by_regime": raw.get("regime_kpis_json") or {},
            "flags": raw.get("flags_json") or {},
            "artifacts": raw.get("artifacts_json") or {},
            "updated_at": raw.get("updated_at"),
        }
        return out

    def _row_to_batch_dict(self, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        raw = dict(row)
        for key in ["universe_json", "variables_explored_json", "best_runs_cache_json", "config_json", "summary_json"]:
            try:
                raw[key] = json.loads(str(raw.get(key) or "null"))
            except Exception:
                raw[key] = {}
        return {
            "batch_id": raw.get("batch_id"),
            "objective": raw.get("objective"),
            "universe": raw.get("universe_json") or {},
            "variables_explored": raw.get("variables_explored_json") or {},
            "created_at": raw.get("created_at"),
            "started_at": raw.get("started_at"),
            "finished_at": raw.get("finished_at"),
            "status": raw.get("status"),
            "run_count_total": int(raw.get("run_count_total") or 0),
            "run_count_done": int(raw.get("run_count_done") or 0),
            "run_count_failed": int(raw.get("run_count_failed") or 0),
            "best_runs_cache": raw.get("best_runs_cache_json") or [],
            "config": raw.get("config_json") or {},
            "summary": raw.get("summary_json") or {},
            "updated_at": raw.get("updated_at"),
        }

    def list_runs(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM backtest_runs ORDER BY created_at DESC, run_id DESC").fetchall()
        return [self._row_to_run_dict(r) for r in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM backtest_runs WHERE run_id = ?", (str(run_id),)).fetchone()
        return self._row_to_run_dict(row) if row else None

    def get_run_by_legacy_id(self, legacy_json_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM backtest_runs WHERE legacy_json_id = ?", (str(legacy_json_id),)).fetchone()
        return self._row_to_run_dict(row) if row else None

    def patch_run(self, run_id: str, *, alias: str | None = None, tags: list[str] | None = None, pinned: bool | None = None, archived: bool | None = None) -> dict[str, Any] | None:
        current = self.get_run(run_id)
        if not current:
            return None
        updates: dict[str, Any] = {}
        if alias is not None:
            updates["alias"] = str(alias).strip() or None
        if tags is not None:
            updates["tags_json"] = _to_json([str(x).strip() for x in tags if str(x).strip()], [])
        if pinned is not None:
            updates["pinned"] = 1 if bool(pinned) else 0
        if archived is not None:
            updates["status"] = "archived" if bool(archived) else ("completed" if str(current.get("status")) == "archived" else str(current.get("status")))
            flags = dict(current.get("flags") or {})
            flags["ARCHIVADO"] = bool(archived)
            updates["flags_json"] = _to_json(flags, {})
        if not updates:
            return current
        updates["updated_at"] = _utc_iso()
        assignments = ", ".join(f"{k}=?" for k in updates.keys())
        values = list(updates.values()) + [str(run_id)]
        with self._connect() as conn:
            conn.execute(f"UPDATE backtest_runs SET {assignments} WHERE run_id = ?", values)
            conn.commit()
        return self.get_run(run_id)

    def patch_run_flags(self, run_id: str, flags_patch: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_run(run_id)
        if not current:
            return None
        flags = dict(current.get("flags") or {})
        for key, value in (flags_patch or {}).items():
            key_s = str(key).strip().upper()
            if not key_s:
                continue
            flags[key_s] = value
        with self._connect() as conn:
            conn.execute(
                "UPDATE backtest_runs SET flags_json = ?, updated_at = ? WHERE run_id = ?",
                (_to_json(flags, {}), _utc_iso(), str(run_id)),
            )
            conn.commit()
        return self.get_run(run_id)

    def delete_runs(self, run_ids: list[str]) -> dict[str, Any]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in run_ids:
            rid = str(raw or "").strip()
            if not rid or rid in seen:
                continue
            seen.add(rid)
            normalized.append(rid)
        if not normalized:
            return {"deleted_count": 0, "deleted": [], "affected_batches": []}

        placeholders = ",".join(["?"] * len(normalized))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT run_id, legacy_json_id, batch_id FROM backtest_runs WHERE run_id IN ({placeholders})",
                normalized,
            ).fetchall()
            if not rows:
                return {"deleted_count": 0, "deleted": [], "affected_batches": []}

            deleted = [dict(r) for r in rows]
            affected_batches = sorted({str(r["batch_id"]) for r in rows if str(r["batch_id"] or "").strip()})

            conn.execute(f"DELETE FROM artifacts_index WHERE run_id IN ({placeholders})", normalized)
            conn.execute(f"DELETE FROM backtest_runs WHERE run_id IN ({placeholders})", normalized)

            for batch_id in affected_batches:
                counts = conn.execute(
                    """
                    SELECT
                      COUNT(*) AS total_count,
                      SUM(CASE WHEN status IN ('completed','completed_warn') THEN 1 ELSE 0 END) AS done_count,
                      SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count
                    FROM backtest_runs
                    WHERE batch_id = ?
                    """,
                    (batch_id,),
                ).fetchone()
                total_count = int((counts["total_count"] if counts else 0) or 0)
                done_count = int((counts["done_count"] if counts else 0) or 0)
                failed_count = int((counts["failed_count"] if counts else 0) or 0)
                conn.execute(
                    """
                    UPDATE backtest_batches
                    SET run_count_total = ?, run_count_done = ?, run_count_failed = ?, updated_at = ?
                    WHERE batch_id = ?
                    """,
                    (total_count, done_count, failed_count, _utc_iso(), batch_id),
                )
            conn.commit()
        return {"deleted_count": len(deleted), "deleted": deleted, "affected_batches": affected_batches}

    def list_batches(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM backtest_batches ORDER BY created_at DESC, batch_id DESC").fetchall()
        return [self._row_to_batch_dict(r) for r in rows]

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM backtest_batches WHERE batch_id = ?", (str(batch_id),)).fetchone()
        return self._row_to_batch_dict(row) if row else None

    def batch_children_runs(self, batch_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM backtest_runs WHERE batch_id = ? ORDER BY created_at DESC, run_id DESC", (str(batch_id),)).fetchall()
        return [self._row_to_run_dict(r) for r in rows]

    def get_artifacts_for_run(self, run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT artifact_kind, artifact_path, artifact_url, created_at FROM artifacts_index WHERE run_id = ? ORDER BY id ASC",
                (str(run_id),),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_artifacts_for_batch(self, batch_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT artifact_kind, artifact_path, artifact_url, created_at FROM artifacts_index WHERE batch_id = ? ORDER BY id ASC",
                (str(batch_id),),
            ).fetchall()
        return [dict(r) for r in rows]

    def query_runs(
        self,
        *,
        q: str | None = None,
        run_type: str | None = None,
        status: str | None = None,
        strategy_id: str | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        mode: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        min_trades: int | None = None,
        max_dd_lte: float | None = None,
        sharpe_gte: float | None = None,
        flags_any: list[str] | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = self.list_runs()
        qq = str(q or "").strip().lower()
        flags_any = [str(x).strip().upper() for x in (flags_any or []) if str(x).strip()]

        def _match(row: dict[str, Any]) -> bool:
            if run_type and str(row.get("run_type") or "") != str(run_type):
                return False
            if status and str(row.get("status") or "") != str(status):
                return False
            if strategy_id and str(row.get("strategy_id") or "") != str(strategy_id):
                return False
            if mode and str(row.get("mode") or "") != str(mode):
                return False
            if symbol and str(symbol).upper() not in {str(x).upper() for x in (row.get("symbols") or [])}:
                return False
            if timeframe and str(timeframe).lower() not in {str(x).lower() for x in (row.get("timeframes") or [])}:
                return False
            if date_from and str(row.get("created_at") or "") < str(date_from):
                return False
            if date_to and str(row.get("created_at") or "") > str(date_to):
                return False
            k = row.get("kpis") if isinstance(row.get("kpis"), dict) else {}
            if min_trades is not None and int(k.get("trade_count") or k.get("roundtrips") or 0) < int(min_trades):
                return False
            if max_dd_lte is not None and float(k.get("max_dd") or 0.0) > float(max_dd_lte):
                return False
            if sharpe_gte is not None and float(k.get("sharpe") or 0.0) < float(sharpe_gte):
                return False
            if flags_any:
                flags = row.get("flags") if isinstance(row.get("flags"), dict) else {}
                if not any(bool(flags.get(flag)) for flag in flags_any):
                    return False
            if qq:
                haystack = " ".join(
                    [
                        str(row.get("run_id") or ""),
                        str(row.get("alias") or ""),
                        str(row.get("strategy_id") or ""),
                        str(row.get("strategy_name") or ""),
                        str(row.get("dataset_hash") or "")[:12],
                        str(row.get("code_commit_hash") or "")[:12],
                        str(row.get("hf_model_id") or ""),
                        str(row.get("hf_revision") or ""),
                        " ".join([str(t) for t in (row.get("tags") or [])]),
                    ]
                ).lower()
                if qq not in haystack:
                    return False
            return True

        rows = [r for r in rows if _match(r)]

        def _sort_key(row: dict[str, Any]) -> Any:
            k = row.get("kpis") if isinstance(row.get("kpis"), dict) else {}
            mapping = {
                "created_at": row.get("created_at") or "",
                "run_id": row.get("run_id") or "",
                "score": float((row.get("composite_score") or 0.0)),
                "return": float(k.get("return_total") or k.get("cagr") or 0.0),
                "sharpe": float(k.get("sharpe") or 0.0),
                "sortino": float(k.get("sortino") or 0.0),
                "dd": float(k.get("max_dd") or 0.0),
                "pf": float(k.get("profit_factor") or 0.0),
                "winrate": float(k.get("winrate") or 0.0),
                "expectancy": float(k.get("expectancy") or 0.0),
                "trades": int(k.get("trade_count") or k.get("roundtrips") or 0),
                "strategy": str(row.get("strategy_name") or row.get("strategy_id") or ""),
            }
            return mapping.get(str(sort_by), mapping["created_at"])

        reverse = str(sort_dir or "desc").lower() != "asc"
        rows.sort(key=_sort_key, reverse=reverse)
        return rows[: max(1, int(limit))]

    def compare_runs(self, run_ids: list[str]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for rid in run_ids:
            rid_s = str(rid).strip()
            if not rid_s or rid_s in seen:
                continue
            seen.add(rid_s)
            row = self.get_run(rid_s)
            if row:
                out.append(row)
        return out

    def rankings(
        self,
        *,
        preset: str = "balanceado",
        constraints: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        c = constraints or {}
        rows = self.query_runs(
            min_trades=int(c["min_trades"]) if c.get("min_trades") is not None else None,
            max_dd_lte=float(c["max_dd"]) if c.get("max_dd") is not None else None,
            sharpe_gte=float(c["sharpe"]) if c.get("sharpe") is not None else None,
            limit=5000,
        )
        weights_map = {
            "conservador": {"ret": 0.15, "dd": 0.25, "sharpe": 0.2, "sortino": 0.15, "pf": 0.1, "expect": 0.05, "rob": 0.1},
            "balanceado": {"ret": 0.2, "dd": 0.2, "sharpe": 0.2, "sortino": 0.15, "pf": 0.1, "expect": 0.1, "rob": 0.05},
            "agresivo": {"ret": 0.3, "dd": 0.1, "sharpe": 0.15, "sortino": 0.1, "pf": 0.05, "expect": 0.2, "rob": 0.1},
            "cost-aware": {"ret": 0.1, "dd": 0.15, "sharpe": 0.15, "sortino": 0.1, "pf": 0.1, "expect": 0.1, "rob": 0.1, "cost": 0.2},
            "oos-first": {"ret": 0.15, "dd": 0.15, "sharpe": 0.2, "sortino": 0.15, "pf": 0.1, "expect": 0.1, "rob": 0.15},
        }
        w = weights_map.get(str(preset).lower(), weights_map["balanceado"])
        for row in rows:
            k = row.get("kpis") if isinstance(row.get("kpis"), dict) else {}
            flags = row.get("flags") if isinstance(row.get("flags"), dict) else {}
            ret = float(k.get("return_total") or k.get("cagr") or 0.0)
            dd = float(k.get("max_dd") or 0.0)
            sharpe = float(k.get("sharpe") or 0.0)
            sortino = float(k.get("sortino") or 0.0)
            pf = float(k.get("profit_factor") or 0.0)
            exp = float(k.get("expectancy") or 0.0)
            robust = 1.0 if str(flags.get("ROBUSTEZ") or "").lower() == "alta" else 0.6 if str(flags.get("ROBUSTEZ") or "").lower() == "media" else 0.3
            costs_ratio = 0.0
            try:
                costs_ratio = float(((k.get("costs_ratio") if isinstance(k, dict) else None) or 0.0))
            except Exception:
                costs_ratio = 0.0
            penalty_trades = 0.15 if int(k.get("trade_count") or k.get("roundtrips") or 0) < int(c.get("min_trades") or 0 or 1) else 0.0
            composite = (
                w.get("ret", 0) * ret
                + w.get("dd", 0) * (1.0 - min(1.0, max(0.0, dd)))
                + w.get("sharpe", 0) * sharpe
                + w.get("sortino", 0) * sortino
                + w.get("pf", 0) * pf
                + w.get("expect", 0) * exp
                + w.get("rob", 0) * robust
                + w.get("cost", 0) * (1.0 - min(1.0, max(0.0, costs_ratio)))
                - penalty_trades
            )
            row["composite_score"] = round(composite, 6)
        rows.sort(key=lambda r: float(r.get("composite_score") or 0.0), reverse=True)
        for i, row in enumerate(rows, start=1):
            row["rank"] = i
        return {"preset": preset, "constraints": c, "items": rows[: max(1, int(limit))], "total": len(rows)}

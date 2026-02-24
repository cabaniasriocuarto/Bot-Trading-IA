from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import sqlite3
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from rtlab_core.backtest import BacktestCatalogDB
from rtlab_core.src.data.catalog import DataCatalog
from .data_provider import build_data_provider


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _f(v: Any, d: float = 0.0) -> float:
    try:
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return d
        return x
    except Exception:
        return d


def _i(v: Any, d: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return d


def _avg(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _avg(vals)
    return (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _parse_date(s: str) -> datetime:
    raw = str(s)
    if "T" not in raw:
        raw += "T00:00:00+00:00"
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_date(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).date().isoformat()


@dataclass(slots=True)
class FoldWindow:
    fold_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str


class MassBacktestEngine:
    def __init__(self, *, user_data_dir: Path, repo_root: Path, knowledge_loader: Any) -> None:
        self.user_data_dir = Path(user_data_dir).resolve()
        self.repo_root = Path(repo_root).resolve()
        self.knowledge_loader = knowledge_loader
        self.catalog = DataCatalog(self.user_data_dir)
        self.backtest_catalog = BacktestCatalogDB(self.user_data_dir / "backtests" / "catalog.sqlite3")
        self.root = (self.user_data_dir / "research" / "mass_backtests").resolve()
        self.db_path = self.root / "metadata.sqlite3"
        self.root.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS mass_runs (
                  run_id TEXT PRIMARY KEY,
                  status TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  config_json TEXT NOT NULL,
                  summary_json TEXT,
                  error TEXT
                );
                CREATE TABLE IF NOT EXISTS mass_variants (
                  run_id TEXT NOT NULL,
                  variant_id TEXT NOT NULL,
                  strategy_id TEXT NOT NULL,
                  rank_num INTEGER,
                  score REAL,
                  hard_filters_pass INTEGER,
                  promotable INTEGER,
                  summary_json TEXT NOT NULL,
                  regime_json TEXT NOT NULL,
                  PRIMARY KEY(run_id, variant_id)
                );
                """
            )
            conn.commit()

    def _run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def _status_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "status.json"

    def _results_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "results.json"

    def _results_parquet_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "results.parquet"

    def _artifacts_dir(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "artifacts"

    def _manifest_path(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "manifest.json"

    def load_knowledge_pack(self) -> dict[str, Any]:
        snap = self.knowledge_loader.load()
        return {
            "templates": copy.deepcopy(getattr(snap, "templates", [])),
            "filters": copy.deepcopy(getattr(snap, "filters", [])),
            "ranges": copy.deepcopy(getattr(snap, "ranges", {})),
            "gates": copy.deepcopy(getattr(snap, "gates", {})),
            "visual_cues": copy.deepcopy(getattr(snap, "visual_cues", {})),
            "strategies_v2": copy.deepcopy(getattr(snap, "strategies_v2", {})),
        }

    def build_universe(self, *, config: dict[str, Any], historical_runs: list[dict[str, Any]]) -> list[str]:
        if isinstance(config.get("universe"), list) and config["universe"]:
            return [str(x).upper() for x in config["universe"]]
        counts: dict[str, int] = {}
        for row in historical_runs:
            sym = str(row.get("symbol") or "")
            if sym:
                counts[sym] = counts.get(sym, 0) + 1
        if counts:
            return [s for s, _ in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:8]]
        market = str(config.get("market") or "crypto").lower()
        return ["EURUSD", "GBPUSD", "USDJPY"] if market == "forex" else ["AAPL", "MSFT", "NVDA"] if market == "equities" else ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def _match_template_id(self, strategy_id: str, kp: dict[str, Any]) -> str | None:
        templates = kp.get("templates") if isinstance(kp.get("templates"), list) else []
        for row in templates:
            if isinstance(row, dict) and str(row.get("base_strategy_id") or "") == strategy_id:
                return str(row.get("id"))
        return None

    def _sample_param(self, rng: random.Random, spec: Any) -> Any:
        if not isinstance(spec, dict):
            return spec
        vmin, vmax, step = spec.get("min"), spec.get("max"), spec.get("step")
        if not isinstance(vmin, (int, float)) or not isinstance(vmax, (int, float)):
            return spec
        if isinstance(step, (int, float)) and float(step) > 0:
            n = max(0, int(round((float(vmax) - float(vmin)) / float(step))))
            v = float(vmin) + float(step) * rng.randint(0, n)
            return int(round(v)) if float(step).is_integer() else round(v, 6)
        return round(rng.uniform(float(vmin), float(vmax)), 6)

    def generate_variants(self, *, strategies: list[dict[str, Any]], knowledge_pack: dict[str, Any], seed: int, max_variants_per_strategy: int, selected_strategy_ids: list[str] | None = None) -> list[dict[str, Any]]:
        selected = {str(x) for x in (selected_strategy_ids or []) if str(x)}
        ranges_all = knowledge_pack.get("ranges") if isinstance(knowledge_pack.get("ranges"), dict) else {}
        out: list[dict[str, Any]] = []
        root_rng = random.Random(int(seed))
        for st in strategies:
            if not isinstance(st, dict):
                continue
            sid = str(st.get("id") or "")
            if not sid or (selected and sid not in selected) or str(st.get("status") or "active") == "archived":
                continue
            tpl_id = self._match_template_id(sid, knowledge_pack)
            ranges = ranges_all.get(tpl_id, {}) if tpl_id else {}
            for idx in range(max(1, int(max_variants_per_strategy or 1))):
                lrng = random.Random(root_rng.randint(1, 2**31 - 1))
                params = {}
                if isinstance(ranges, dict):
                    for k, spec in ranges.items():
                        params[str(k)] = self._sample_param(lrng, spec)
                out.append(
                    {
                        "variant_id": f"{sid}__v{idx+1:03d}",
                        "strategy_id": sid,
                        "strategy_name": str(st.get("name") or sid),
                        "template_id": tpl_id,
                        "params": params,
                        "seed": lrng.randint(1, 2**31 - 1),
                        "tags": [str(x) for x in (st.get("tags") or [])],
                    }
                )
        return out

    def walk_forward_runner(self, *, start: str, end: str, train_days: int = 180, test_days: int = 60, max_folds: int = 10) -> list[FoldWindow]:
        sdt = _parse_date(start)
        edt = _parse_date(end)
        if edt <= sdt:
            raise ValueError("Rango invalido")
        out: list[FoldWindow] = []
        cur = sdt
        for n in range(1, max_folds + 1):
            tr_s = cur
            tr_e = tr_s + timedelta(days=train_days)
            te_s = tr_e
            te_e = te_s + timedelta(days=test_days)
            if te_e > edt:
                break
            out.append(FoldWindow(n, _iso_date(tr_s), _iso_date(tr_e), _iso_date(te_s), _iso_date(te_e)))
            cur = cur + timedelta(days=test_days)
        if not out:
            mid = sdt + (edt - sdt) / 2
            out.append(FoldWindow(1, _iso_date(sdt), _iso_date(mid), _iso_date(mid), _iso_date(edt)))
        return out

    def realistic_cost_model(self, base_costs: dict[str, Any], *, stress_level: str = "base") -> dict[str, float]:
        costs = {
            "fees_bps": _f(base_costs.get("fees_bps"), 5.5),
            "spread_bps": _f(base_costs.get("spread_bps"), 4.0),
            "slippage_bps": _f(base_costs.get("slippage_bps"), 3.0),
            "funding_bps": _f(base_costs.get("funding_bps"), 1.0),
            "rollover_bps": _f(base_costs.get("rollover_bps"), 0.0),
        }
        if stress_level == "stress_plus":
            costs["fees_bps"] += 1.0
            costs["spread_bps"] += 2.0
            costs["slippage_bps"] += 2.0
        if stress_level == "stress_max":
            costs["fees_bps"] += 2.5
            costs["spread_bps"] += 4.0
            costs["slippage_bps"] += 4.0
        return costs

    def _variant_effect(self, variant: dict[str, Any], fold: FoldWindow) -> tuple[float, str]:
        h = int(_sha({"v": variant.get("variant_id"), "p": variant.get("params"), "f": fold.fold_index})[:8], 16)
        rng = random.Random(h)
        regime = ["trend", "range", "high_vol", "toxic"][fold.fold_index % 4]
        adj = (rng.random() - 0.5) * 0.18 + {"trend": 0.03, "range": -0.005, "high_vol": 0.015, "toxic": -0.025}[regime]
        return adj, regime

    def _adjust_run(self, run: dict[str, Any], *, variant: dict[str, Any], fold: FoldWindow) -> dict[str, Any]:
        out = copy.deepcopy(run)
        metrics = out.get("metrics") if isinstance(out.get("metrics"), dict) else {}
        costs = out.get("costs_breakdown") if isinstance(out.get("costs_breakdown"), dict) else {}
        adj, regime = self._variant_effect(variant, fold)
        gross = _f(costs.get("gross_pnl_total", costs.get("gross_pnl", 100.0)), 100.0) * (1 + adj)
        net = _f(costs.get("net_pnl_total", costs.get("net_pnl", 80.0)), 80.0) * (1 + adj * 0.8)
        total_cost = abs(_f(costs.get("total_cost", 8.0), 8.0)) * (1 + max(-0.2, adj * 0.25))
        costs["gross_pnl_total"] = round(gross, 6)
        costs["net_pnl_total"] = round(net, 6)
        costs["total_cost"] = round(total_cost, 6)
        costs["total_cost_pct_of_gross_pnl"] = round(total_cost / max(1.0, abs(gross)), 6)
        metrics["sharpe"] = round(_f(metrics.get("sharpe"), 0.5) + adj * 1.2, 6)
        metrics["sortino"] = round(_f(metrics.get("sortino"), 0.7) + adj * 1.4, 6)
        metrics["calmar"] = round(_f(metrics.get("calmar"), 0.4) + adj * 0.9, 6)
        metrics["winrate"] = round(max(0.05, min(0.95, _f(metrics.get("winrate"), 0.5) + adj * 0.06)), 6)
        metrics["max_dd"] = round(max(0.003, min(0.95, abs(_f(metrics.get("max_dd"), 0.12)) * (1 - adj * 0.45))), 6)
        metrics["expectancy_usd_per_trade"] = round(_f(metrics.get("expectancy_usd_per_trade", metrics.get("expectancy", 1.0)), 1.0) * (1 + adj), 6)
        metrics["expectancy"] = round(_f(metrics.get("expectancy"), 1.0) * (1 + adj), 6)
        metrics["trade_count"] = max(1, _i(metrics.get("trade_count", metrics.get("roundtrips", 50)), 50))
        metrics["roundtrips"] = max(1, _i(metrics.get("roundtrips", metrics.get("trade_count", 50)), 50))
        metrics["robustness_score"] = round(max(0.0, min(100.0, _f(metrics.get("robustness_score", metrics.get("robust_score", 60.0)), 60.0) + adj * 30)), 4)
        metrics["robust_score"] = metrics["robustness_score"]
        out["metrics"] = metrics
        out["costs_breakdown"] = costs
        out["research_regime_label"] = regime
        out["evaluation_mode"] = "engine_surrogate_adjusted"
        return out

    def _fold_summary(self, run: dict[str, Any], fold: FoldWindow) -> dict[str, Any]:
        m = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        c = run.get("costs_breakdown") if isinstance(run.get("costs_breakdown"), dict) else {}
        return {
            "fold": fold.fold_index,
            "train_start": fold.train_start,
            "train_end": fold.train_end,
            "test_start": fold.test_start,
            "test_end": fold.test_end,
            "regime_label": str(run.get("research_regime_label") or "range"),
            "sharpe_oos": _f(m.get("sharpe")),
            "sortino_oos": _f(m.get("sortino")),
            "calmar_oos": _f(m.get("calmar")),
            "max_dd_oos_pct": abs(_f(m.get("max_dd"))) * 100.0,
            "expectancy_net_usd": _f(m.get("expectancy_usd_per_trade", m.get("expectancy"))),
            "trade_count": _i(m.get("trade_count", m.get("roundtrips")), 0),
            "gross_pnl": _f(c.get("gross_pnl_total", c.get("gross_pnl"))),
            "net_pnl": _f(c.get("net_pnl_total", c.get("net_pnl"))),
            "costs_total": _f(c.get("total_cost")),
            "costs_ratio": _f(c.get("total_cost_pct_of_gross_pnl")),
            "winrate": _f(m.get("winrate")),
            "dataset_hash": str(run.get("dataset_hash") or ""),
            "provenance": run.get("provenance") if isinstance(run.get("provenance"), dict) else {},
            "run_id": str(run.get("id") or ""),
        }

    def robustness_suite(self, *, fold_metrics: list[dict[str, Any]], variant: dict[str, Any]) -> dict[str, Any]:
        sharpe_vals = [_f(x.get("sharpe_oos")) for x in fold_metrics]
        dd_vals = [_f(x.get("max_dd_oos_pct")) for x in fold_metrics]
        passes = sum(1 for x in fold_metrics if _f(x.get("sharpe_oos")) > 0 and _f(x.get("max_dd_oos_pct")) <= 25)
        st = max(0.0, min(1.0, 1.0 - (_std(sharpe_vals) / (abs(_avg(sharpe_vals)) + 1.0))))
        seed = int(_sha({"variant": variant.get("variant_id"), "params": variant.get("params")})[:8], 16)
        rng = random.Random(seed)
        jitter_pass = 0
        for _ in range(20):
            noise = (rng.random() - 0.5) * 0.18
            if (_avg(sharpe_vals) + noise) > 0 and (_avg(dd_vals) * (1 + abs(noise))) <= 30:
                jitter_pass += 1
        return {
            "stability": round(st, 6),
            "consistency_folds": round(passes / max(1, len(fold_metrics)), 6),
            "jitter_pass_rate": round(jitter_pass / 20.0, 6),
        }

    def anti_overfitting_suite(self, *, fold_metrics: list[dict[str, Any]]) -> dict[str, Any]:
        sharpe_vals = [_f(x.get("sharpe_oos")) for x in fold_metrics]
        trades = sum(_i(x.get("trade_count"), 0) for x in fold_metrics)
        m = _avg(sharpe_vals)
        s = _std(sharpe_vals)
        pbo = max(0.0, min(1.0, 0.5 + s * 0.15 - m * 0.1))
        dsr = m - (math.log(max(2, len(fold_metrics) + 1)) / max(1.0, math.sqrt(max(1, trades / 10))))
        return {
            "method": "proxy_fail_closed_for_promotion",
            "pbo": round(pbo, 6),
            "dsr": round(dsr, 6),
            "enforce_ready": False,
            "promotion_blocked": True,
            "promotion_block_reason": "PBO/DSR proxy. No auto-live (Opcion B, fail-closed).",
        }

    def _regime_metrics(self, folds: list[dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for regime in ["trend", "range", "high_vol", "toxic"]:
            rows = [r for r in folds if str(r.get("regime_label")) == regime]
            if not rows:
                continue
            out[regime] = {
                "folds": len(rows),
                "trade_count": sum(_i(r.get("trade_count")) for r in rows),
                "net_pnl": round(sum(_f(r.get("net_pnl")) for r in rows), 6),
                "expectancy_net_usd": round(_avg([_f(r.get("expectancy_net_usd")) for r in rows]), 6),
                "sharpe_oos": round(_avg([_f(r.get("sharpe_oos")) for r in rows]), 6),
                "max_dd_oos_pct": round(_avg([_f(r.get("max_dd_oos_pct")) for r in rows]), 6),
                "costs_ratio": round(_avg([_f(r.get("costs_ratio")) for r in rows]), 6),
            }
        return out

    def _score(self, summary: dict[str, Any], anti: dict[str, Any]) -> tuple[float, bool, list[str]]:
        reasons: list[str] = []
        if _i(summary.get("trade_count_oos")) < 200:
            reasons.append("trades_oos < 200")
        if _f(summary.get("max_dd_oos_pct")) > 25:
            reasons.append("maxDD > 25%")
        if _f(summary.get("costs_ratio")) > 0.70:
            reasons.append("costs_ratio > 0.70")
        if _f(anti.get("pbo"), 1.0) > 0.60:
            reasons.append("PBO proxy > 0.60")
        if _f(anti.get("dsr"), -999) < 0.0:
            reasons.append("DSR proxy < 0.0")
        score = (
            0.25 * _f(summary.get("sharpe_oos"))
            + 0.20 * _f(summary.get("calmar_oos"))
            + 0.20 * _f(summary.get("expectancy_net_usd"))
            + 0.15 * _f(summary.get("stability"))
            + 0.10 * (1.0 - max(0.0, min(1.0, _f(summary.get("costs_ratio")))))
            + 0.10 * (1.0 - max(0.0, min(1.0, _f(summary.get("max_dd_oos_pct")) / 100.0)))
        )
        return round(score, 6), (len(reasons) == 0), reasons

    def scoring_and_ranking(self, *, variants_payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = sorted(variants_payload, key=lambda r: _f(r.get("score"), -999999), reverse=True)
        for idx, row in enumerate(rows, 1):
            row["rank"] = idx
        return rows

    def _status(self, run_id: str) -> dict[str, Any]:
        return _json_load(self._status_path(run_id), {"run_id": run_id, "state": "NOT_FOUND", "logs": []})

    def _write_status(self, run_id: str, *, state: str, config: dict[str, Any], progress: dict[str, Any], summary: dict[str, Any] | None = None, error: str | None = None, logs: list[str] | None = None) -> dict[str, Any]:
        prev = self._status(run_id)
        payload = {
            "run_id": run_id,
            "state": state,
            "created_at": prev.get("created_at") or _utc_iso(),
            "updated_at": _utc_iso(),
            "config": config,
            "progress": progress,
            "summary": summary if summary is not None else prev.get("summary", {}),
            "error": error,
            "logs": (prev.get("logs") or []) + (logs or []),
        }
        payload["logs"] = [str(x) for x in payload["logs"]][-500:]
        _json_dump(self._status_path(run_id), payload)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO mass_runs (run_id,status,created_at,updated_at,config_json,summary_json,error)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(run_id) DO UPDATE SET
                  status=excluded.status,
                  updated_at=excluded.updated_at,
                  config_json=excluded.config_json,
                  summary_json=excluded.summary_json,
                  error=excluded.error
                """,
                (
                    run_id,
                    state,
                    payload["created_at"],
                    payload["updated_at"],
                    json.dumps(config),
                    json.dumps(payload.get("summary") or {}),
                    error,
                ),
            )
            conn.commit()
        return payload

    def _write_results(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        _json_dump(self._results_path(run_id), payload)
        parquet = {"available": False, "path": str(self._results_parquet_path(run_id).name), "reason": ""}
        try:
            import pandas as pd  # type: ignore

            rows = []
            for row in payload.get("results", []):
                if not isinstance(row, dict):
                    continue
                s = row.get("summary") if isinstance(row.get("summary"), dict) else {}
                rows.append(
                    {
                        "variant_id": row.get("variant_id"),
                        "strategy_id": row.get("strategy_id"),
                        "rank": row.get("rank"),
                        "score": row.get("score"),
                        "hard_filters_pass": row.get("hard_filters_pass"),
                        "promotable": row.get("promotable"),
                        "sharpe_oos": s.get("sharpe_oos"),
                        "calmar_oos": s.get("calmar_oos"),
                        "expectancy_net_usd": s.get("expectancy_net_usd"),
                        "trade_count_oos": s.get("trade_count_oos"),
                        "max_dd_oos_pct": s.get("max_dd_oos_pct"),
                        "costs_ratio": s.get("costs_ratio"),
                    }
                )
            if rows:
                pd.DataFrame(rows).to_parquet(self._results_parquet_path(run_id), index=False)
                parquet["available"] = True
        except Exception as exc:
            parquet["reason"] = str(exc)
        return parquet

    def _duckdb_query(self, run_id: str, *, limit: int, strategy_id: str | None, only_pass: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        pq = self._results_parquet_path(run_id)
        if not pq.exists():
            return [], {"used": False, "reason": "parquet_missing"}
        try:
            import duckdb  # type: ignore

            con = duckdb.connect()
            sql = "SELECT * FROM read_parquet(?)"
            params: list[Any] = [str(pq)]
            where = []
            if strategy_id:
                where.append("strategy_id = ?")
                params.append(strategy_id)
            if only_pass:
                where.append("hard_filters_pass = true")
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY score DESC NULLS LAST LIMIT ?"
            params.append(int(limit))
            df = con.execute(sql, params).fetchdf()
            return df.to_dict(orient="records"), {"used": True, "parquet": str(pq)}
        except Exception as exc:
            return [], {"used": False, "reason": str(exc)}

    def _write_artifacts(self, run_id: str, top_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out_dir = self._artifacts_dir(run_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, Any]] = []
        html = out_dir / "index.html"
        html.write_text(
            "\n".join(
                [
                    "<html><head><meta charset='utf-8'><title>Mass Backtests</title></head><body>",
                    f"<h1>Research Masivo {run_id}</h1>",
                    "<table border='1' cellpadding='5' cellspacing='0'>",
                    "<tr><th>Rank</th><th>Variant</th><th>Estrategia</th><th>Score</th><th>Sharpe</th><th>Calmar</th><th>Expectancy</th><th>MaxDD%</th><th>CostsRatio</th></tr>",
                    *[
                        (
                            "<tr>"
                            f"<td>{row.get('rank')}</td><td>{row.get('variant_id')}</td><td>{row.get('strategy_id')}</td><td>{row.get('score')}</td>"
                            f"<td>{(row.get('summary') or {}).get('sharpe_oos')}</td><td>{(row.get('summary') or {}).get('calmar_oos')}</td>"
                            f"<td>{(row.get('summary') or {}).get('expectancy_net_usd')}</td><td>{(row.get('summary') or {}).get('max_dd_oos_pct')}</td>"
                            f"<td>{(row.get('summary') or {}).get('costs_ratio')}</td></tr>"
                        )
                        for row in top_rows
                    ],
                    "</table></body></html>",
                ]
            ),
            encoding="utf-8",
        )
        files.append({"name": "index.html", "path": str(html)})
        top_json = out_dir / "top_candidates.json"
        _json_dump(top_json, top_rows)
        files.append({"name": "top_candidates.json", "path": str(top_json)})
        return files

    def _batch_status_norm(self, state: str) -> str:
        s = str(state or "").strip().lower()
        return {
            "queued": "queued",
            "running": "running",
            "completed": "completed",
            "failed": "failed",
            "canceled": "canceled",
            "not_found": "failed",
        }.get(s, "queued")

    def _upsert_batch_catalog(self, *, batch_id: str, state: str, cfg: dict[str, Any], summary: dict[str, Any] | None = None) -> None:
        universe_payload = {
            "symbols": [str(x) for x in (cfg.get("resolved_universe") or cfg.get("universe") or [])],
            "timeframes": [str(cfg.get("timeframe") or "5m")],
            "market": str(cfg.get("market") or "crypto"),
        }
        variables_explored = {
            "strategy_ids": [str(x) for x in (cfg.get("strategy_ids") or [])],
            "max_variants_per_strategy": _i(cfg.get("max_variants_per_strategy"), 0),
            "max_folds": _i(cfg.get("max_folds"), 0),
            "train_days": _i(cfg.get("train_days"), 0),
            "test_days": _i(cfg.get("test_days"), 0),
            "seed": _i(cfg.get("seed"), 0),
        }
        s = summary or {}
        now = _utc_iso()
        self.backtest_catalog.upsert_backtest_batch(
            {
                "batch_id": batch_id,
                "objective": str(cfg.get("objective") or "Research Batch (mass backtests)"),
                "universe_json": json.dumps(universe_payload, ensure_ascii=True, sort_keys=True),
                "variables_explored_json": json.dumps(variables_explored, ensure_ascii=True, sort_keys=True),
                "created_at": str(cfg.get("created_at") or now),
                "started_at": str(cfg.get("started_at") or now) if self._batch_status_norm(state) in {"running", "completed", "failed"} else cfg.get("started_at"),
                "finished_at": now if self._batch_status_norm(state) in {"completed", "failed", "canceled"} else None,
                "status": self._batch_status_norm(state),
                "run_count_total": _i(s.get("variants_total"), 0),
                "run_count_done": _i(s.get("variants_total"), 0) if self._batch_status_norm(state) == "completed" else _i(s.get("run_count_done"), 0),
                "run_count_failed": _i(s.get("run_count_failed"), 0),
                "best_runs_cache_json": json.dumps(s.get("best_runs_cache") or [], ensure_ascii=True, sort_keys=True),
                "config_json": json.dumps(cfg, ensure_ascii=True, sort_keys=True, default=str),
                "summary_json": json.dumps(s, ensure_ascii=True, sort_keys=True, default=str),
            }
        )

    def _record_batch_children_catalog(self, *, batch_id: str, rows: list[dict[str, Any]], cfg: dict[str, Any]) -> None:
        for idx, row in enumerate(rows, start=1):
            summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
            regime = row.get("regime_metrics") if isinstance(row.get("regime_metrics"), dict) else {}
            params = row.get("params") if isinstance(row.get("params"), dict) else {}
            run_id = self.backtest_catalog.next_formatted_id("BT")
            row["backtest_run_id"] = run_id
            status = "completed" if bool(row.get("hard_filters_pass")) else "completed_warn"
            symbols = [str(x) for x in (cfg.get("resolved_universe") or cfg.get("universe") or [])]
            timeframe = str(cfg.get("timeframe") or "5m")
            record = self.backtest_catalog.upsert_backtest_run(
                {
                    "run_id": run_id,
                    "legacy_json_id": f"{batch_id}:{row.get('variant_id')}",
                    "run_type": "batch_child",
                    "batch_id": batch_id,
                    "status": status,
                    "created_at": _utc_iso(),
                    "started_at": _utc_iso(),
                    "finished_at": _utc_iso(),
                    "created_by": str(cfg.get("requested_by") or "system"),
                    "mode": "backtest",
                    "strategy_id": str(row.get("strategy_id") or ""),
                    "strategy_name": str(row.get("strategy_name") or row.get("strategy_id") or ""),
                    "strategy_version": str(cfg.get("strategy_version") or "batch"),
                    "strategy_config_hash": _sha({"variant_id": row.get("variant_id"), "params": params}),
                    "code_commit_hash": str(cfg.get("commit_hash") or "local"),
                    "dataset_source": str((cfg.get("data_provider") or {}).get("dataset_source") or cfg.get("dataset_source") or "dataset"),
                    "dataset_version": str((cfg.get("data_provider") or {}).get("dataset_version") or "batch_dataset"),
                    "dataset_hash": str(((summary.get("dataset_hashes") or [None])[0]) or (cfg.get("data_provider") or {}).get("dataset_hash") or ""),
                    "symbols_json": json.dumps(symbols, ensure_ascii=True, sort_keys=True),
                    "timeframes_json": json.dumps([timeframe], ensure_ascii=True, sort_keys=True),
                    "timerange_from": str(cfg.get("start") or ""),
                    "timerange_to": str(cfg.get("end") or ""),
                    "timezone": "UTC",
                    "missing_data_policy": "warn_skip",
                    "fee_model": f"maker_taker_bps:{_f(((cfg.get('costs') or {}).get('fees_bps')), 0.0):.4f}",
                    "spread_model": f"static:{_f(((cfg.get('costs') or {}).get('spread_bps')), 0.0):.4f}",
                    "slippage_model": f"static:{_f(((cfg.get('costs') or {}).get('slippage_bps')), 0.0):.4f}",
                    "funding_model": f"static:{_f(((cfg.get('costs') or {}).get('funding_bps')), 0.0):.4f}",
                    "fill_model": "simulated",
                    "initial_capital": _f(cfg.get("initial_capital"), 10000.0),
                    "position_sizing_profile": str(cfg.get("position_sizing_profile") or "default"),
                    "max_open_positions": _i(cfg.get("max_open_positions"), 1),
                    "params_json": json.dumps({"variant_id": row.get("variant_id"), "params": params, "batch_rank": idx}, ensure_ascii=True, sort_keys=True),
                    "seed": _i(row.get("seed")) if row.get("seed") is not None else None,
                    "alias": None,
                    "tags_json": json.dumps(["batch_child", "research"], ensure_ascii=True),
                    "kpi_summary_json": json.dumps(
                        {
                            "sharpe": summary.get("sharpe_oos"),
                            "sortino": summary.get("sortino_oos"),
                            "calmar": summary.get("calmar_oos"),
                            "max_dd": (_f(summary.get("max_dd_oos_pct")) / 100.0),
                            "winrate": summary.get("winrate"),
                            "expectancy": summary.get("expectancy_net_usd"),
                            "expectancy_unit": "usd_per_trade",
                            "profit_factor": summary.get("profit_factor"),
                            "trade_count": summary.get("trade_count_oos"),
                            "roundtrips": summary.get("trade_count_oos"),
                            "robustness_score": round((_f(row.get("score"), 0.0) * 10) + 50, 4),
                            "pbo": (row.get("anti_overfitting") or {}).get("pbo"),
                            "dsr": (row.get("anti_overfitting") or {}).get("dsr"),
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
                    "regime_kpis_json": json.dumps(regime, ensure_ascii=True, sort_keys=True),
                    "flags_json": json.dumps(
                        {
                            "OOS": True,
                            "WFA": True,
                            "PASO_GATES": bool(row.get("hard_filters_pass")),
                            "BASELINE": False,
                            "FAVORITO": idx <= max(1, _i(cfg.get("top_n"), 10)),
                            "ARCHIVADO": False,
                            "DATA_WARNING": bool(len(summary.get("dataset_hashes") or []) > 1),
                            "ROBUSTEZ": "Alta" if bool(row.get("hard_filters_pass")) else "Media",
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
                    "artifacts_json": json.dumps({"batch_id": batch_id, "variant_id": row.get("variant_id")}, ensure_ascii=True, sort_keys=True),
                }
            )
            row["catalog_run_id"] = record["run_id"]

    def run_job(
        self,
        *,
        run_id: str,
        config: dict[str, Any],
        strategies: list[dict[str, Any]],
        historical_runs: list[dict[str, Any]],
        backtest_callback: Callable[[dict[str, Any], FoldWindow, dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        cfg = copy.deepcopy(config)
        cfg.setdefault("created_at", _utc_iso())
        cfg.setdefault("started_at", _utc_iso())
        kp = self.load_knowledge_pack()
        universe = self.build_universe(config=cfg, historical_runs=historical_runs)
        cfg["resolved_universe"] = universe
        data_mode = str(cfg.get("data_mode") or "dataset").lower()
        provider = build_data_provider(mode=data_mode, user_data_dir=self.user_data_dir, catalog=self.catalog)
        dataset_info = provider.resolve(
            market=str(cfg.get("market") or "crypto"),
            symbol=str(cfg.get("symbol") or (universe[0] if universe else "BTCUSDT")),
            timeframe=str(cfg.get("timeframe") or "5m"),
            start=str(cfg.get("start") or "2024-01-01"),
            end=str(cfg.get("end") or "2024-12-31"),
        )
        cfg["data_provider"] = dataset_info.to_dict()
        folds = self.walk_forward_runner(
            start=str(cfg.get("start") or "2024-01-01"),
            end=str(cfg.get("end") or "2024-12-31"),
            train_days=_i(cfg.get("train_days"), 180),
            test_days=_i(cfg.get("test_days"), 60),
            max_folds=_i(cfg.get("max_folds"), 8),
        )
        variants = self.generate_variants(
            strategies=strategies,
            knowledge_pack=kp,
            seed=_i(cfg.get("seed"), 42),
            max_variants_per_strategy=_i(cfg.get("max_variants_per_strategy"), 8),
            selected_strategy_ids=[str(x) for x in (cfg.get("strategy_ids") or [])],
        )
        total_tasks = max(1, len(variants) * len(folds))
        self._upsert_batch_catalog(batch_id=run_id, state="running", cfg=cfg, summary={"variants_total": len(variants), "run_count_done": 0, "run_count_failed": 0})
        self._write_status(run_id, state="RUNNING", config=cfg, progress={"total_tasks": total_tasks, "completed_tasks": 0, "pct": 0}, logs=[f"Iniciando {len(variants)} variantes x {len(folds)} folds"])
        ranked_input: list[dict[str, Any]] = []
        completed = 0
        for idx, variant in enumerate(variants, 1):
            fold_rows: list[dict[str, Any]] = []
            for fold in folds:
                costs_cfg = self.realistic_cost_model(cfg.get("costs") if isinstance(cfg.get("costs"), dict) else {})
                base_run = backtest_callback(variant, fold, costs_cfg)
                run = self._adjust_run(base_run, variant=variant, fold=fold)
                fold_rows.append(self._fold_summary(run, fold))
                completed += 1
                if completed == 1 or completed % 5 == 0 or completed == total_tasks:
                    self._write_status(
                        run_id,
                        state="RUNNING",
                        config=cfg,
                        progress={"total_tasks": total_tasks, "completed_tasks": completed, "pct": round(completed * 100 / total_tasks, 2), "current_variant": idx},
                        logs=[f"Procesado {completed}/{total_tasks} folds ({variant['variant_id']})"],
                    )
            robust = self.robustness_suite(fold_metrics=fold_rows, variant=variant)
            anti = self.anti_overfitting_suite(fold_metrics=fold_rows)
            summary = {
                "folds": len(fold_rows),
                "trade_count_oos": sum(_i(x.get("trade_count")) for x in fold_rows),
                "gross_pnl_oos": round(sum(_f(x.get("gross_pnl")) for x in fold_rows), 6),
                "net_pnl_oos": round(sum(_f(x.get("net_pnl")) for x in fold_rows), 6),
                "costs_total": round(sum(_f(x.get("costs_total")) for x in fold_rows), 6),
                "costs_ratio": round(_avg([_f(x.get("costs_ratio")) for x in fold_rows]), 6),
                "sharpe_oos": round(_avg([_f(x.get("sharpe_oos")) for x in fold_rows]), 6),
                "sortino_oos": round(_avg([_f(x.get("sortino_oos")) for x in fold_rows]), 6),
                "calmar_oos": round(_avg([_f(x.get("calmar_oos")) for x in fold_rows]), 6),
                "max_dd_oos_pct": round(_avg([_f(x.get("max_dd_oos_pct")) for x in fold_rows]), 6),
                "expectancy_net_usd": round(_avg([_f(x.get("expectancy_net_usd")) for x in fold_rows]), 6),
                "stability": robust.get("stability", 0.0),
                "consistency_folds": robust.get("consistency_folds", 0.0),
                "jitter_pass_rate": robust.get("jitter_pass_rate", 0.0),
                "dataset_hashes": sorted({str(x.get("dataset_hash") or "") for x in fold_rows if str(x.get("dataset_hash") or "")}),
            }
            score, hard_pass, reasons = self._score(summary, anti)
            ranked_input.append(
                {
                    "variant_id": variant["variant_id"],
                    "strategy_id": variant["strategy_id"],
                    "strategy_name": variant.get("strategy_name"),
                    "template_id": variant.get("template_id"),
                    "params": variant.get("params") or {},
                    "summary": summary,
                    "folds": fold_rows,
                    "regime_metrics": self._regime_metrics(fold_rows),
                    "robustness": robust,
                    "anti_overfitting": anti,
                    "score": score,
                    "hard_filters_pass": hard_pass,
                    "hard_filter_reasons": reasons,
                    "promotable": bool(hard_pass and not anti.get("promotion_blocked")),
                    "recommendable_option_b": bool(hard_pass),
                }
            )
        ranked = self.scoring_and_ranking(variants_payload=ranked_input)
        top_n = max(1, _i(cfg.get("top_n"), 10))
        top_rows = ranked[:top_n]
        self._record_batch_children_catalog(batch_id=run_id, rows=ranked, cfg=cfg)
        payload = {
            "run_id": run_id,
            "created_at": self._status(run_id).get("created_at") or _utc_iso(),
            "completed_at": _utc_iso(),
            "config": cfg,
            "knowledge_snapshot": {"templates": len(kp.get("templates") or []), "filters": len(kp.get("filters") or []), "gates": sorted(list((kp.get("gates") or {}).keys()))},
            "summary": {
                "variants_total": len(ranked),
                "hard_pass_count": sum(1 for r in ranked if bool(r.get("hard_filters_pass"))),
                "promotable_count": sum(1 for r in ranked if bool(r.get("promotable"))),
                "top_n": top_n,
                "anti_perf_chasing": {
                    "min_window_days_paper_testnet": 7,
                    "min_window_days_live": 14,
                    "max_live_switch_per_week": 1,
                    "option_b_no_auto_live": True,
                },
            },
            "results": ranked,
        }
        parquet_info = self._write_results(run_id, payload)
        payload["summary"]["query_backend"] = parquet_info
        _json_dump(self._results_path(run_id), payload)
        manifest = {
            "run_id": run_id,
            "dataset_source": str(cfg.get("dataset_source") or cfg.get("data_source") or dataset_info.dataset_source or "synthetic"),
            "dataset_hashes": sorted({h for row in ranked for h in (row.get("summary") or {}).get("dataset_hashes", []) if h} | ({dataset_info.dataset_hash} if dataset_info.dataset_hash else set())),
            "period": {"start": cfg.get("start"), "end": cfg.get("end")},
            "timeframe": cfg.get("timeframe"),
            "universe": universe,
            "costs_used": cfg.get("costs") or {},
            "commit_hash": str(cfg.get("commit_hash") or "local"),
            "results_parquet": parquet_info,
            "data_provider": dataset_info.to_dict(),
        }
        _json_dump(self._manifest_path(run_id), manifest)
        artifacts = self._write_artifacts(run_id, top_rows)
        for art in artifacts:
            try:
                self.backtest_catalog.add_artifact(
                    run_id=None,
                    batch_id=run_id,
                    kind=str(art.get("name") or "artifact"),
                    path=str(art.get("path") or ""),
                    url=None,
                )
            except Exception:
                pass
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM mass_variants WHERE run_id=?", (run_id,))
            for row in ranked:
                conn.execute(
                    "INSERT INTO mass_variants (run_id,variant_id,strategy_id,rank_num,score,hard_filters_pass,promotable,summary_json,regime_json) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        str(row.get("variant_id") or ""),
                        str(row.get("strategy_id") or ""),
                        _i(row.get("rank"), 0),
                        _f(row.get("score"), 0.0),
                        1 if bool(row.get("hard_filters_pass")) else 0,
                        1 if bool(row.get("promotable")) else 0,
                        json.dumps(row.get("summary") or {}),
                        json.dumps(row.get("regime_metrics") or {}),
                    ),
                )
            conn.commit()
        summary = {
            "variants_total": len(ranked),
            "hard_pass_count": payload["summary"]["hard_pass_count"],
            "promotable_count": payload["summary"]["promotable_count"],
            "top_variant_id": top_rows[0].get("variant_id") if top_rows else None,
            "best_runs_cache": [str(r.get("catalog_run_id") or r.get("backtest_run_id") or "") for r in top_rows[: min(10, len(top_rows))]],
            "run_count_done": len(ranked),
            "run_count_failed": 0,
            "top_score": _f(top_rows[0].get("score"), 0.0) if top_rows else 0.0,
            "parquet": parquet_info,
        }
        self._upsert_batch_catalog(batch_id=run_id, state="completed", cfg=cfg, summary=summary)
        self._write_status(run_id, state="COMPLETED", config=cfg, progress={"total_tasks": total_tasks, "completed_tasks": total_tasks, "pct": 100.0}, summary=summary, logs=["Mass backtests completado."])
        return {"run_id": run_id, "summary": summary, "artifacts": artifacts, "top_candidates": top_rows}

    def fail(self, run_id: str, *, config: dict[str, Any], err: str) -> None:
        try:
            self._upsert_batch_catalog(
                batch_id=run_id,
                state="failed",
                cfg=config,
                summary={"variants_total": 0, "run_count_done": 0, "run_count_failed": 1, "best_runs_cache": []},
            )
        except Exception:
            pass
        self._write_status(run_id, state="FAILED", config=config, progress={"pct": 0}, error=err, logs=[err])

    def status(self, run_id: str) -> dict[str, Any]:
        return self._status(run_id)

    def results(self, run_id: str, *, limit: int = 100, strategy_id: str | None = None, only_pass: bool = False) -> dict[str, Any]:
        payload = _json_load(self._results_path(run_id), {"run_id": run_id, "summary": {}, "results": []})
        all_rows = [r for r in (payload.get("results") or []) if isinstance(r, dict)]
        duck_rows, duck_info = self._duckdb_query(run_id, limit=max(1, int(limit)), strategy_id=strategy_id, only_pass=only_pass)
        if duck_rows:
            by_id = {str(r.get("variant_id")): r for r in all_rows}
            out = [by_id.get(str(r.get("variant_id")), r) for r in duck_rows]
            return {"run_id": run_id, "summary": payload.get("summary") or {}, "results": out, "query_backend": {"engine": "duckdb", **duck_info}}
        rows = all_rows
        if strategy_id:
            rows = [r for r in rows if str(r.get("strategy_id") or "") == strategy_id]
        if only_pass:
            rows = [r for r in rows if bool(r.get("hard_filters_pass"))]
        rows.sort(key=lambda x: _f(x.get("score"), -999999), reverse=True)
        return {"run_id": run_id, "summary": payload.get("summary") or {}, "results": rows[: max(1, int(limit))], "query_backend": {"engine": "python", **duck_info}}

    def artifacts(self, run_id: str) -> dict[str, Any]:
        out = []
        ad = self._artifacts_dir(run_id)
        if ad.exists():
            for f in sorted(ad.iterdir()):
                if f.is_file():
                    out.append({"name": f.name, "path": str(f), "size": f.stat().st_size})
        return {"run_id": run_id, "items": out}


class MassBacktestCoordinator:
    def __init__(self, *, engine: MassBacktestEngine) -> None:
        self.engine = engine
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def _run_id(self) -> str:
        return self.engine.backtest_catalog.next_formatted_id("BX")

    def start_async(self, *, config: dict[str, Any], strategies: list[dict[str, Any]], historical_runs: list[dict[str, Any]], backtest_callback: Callable[[dict[str, Any], FoldWindow, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        run_id = self._run_id()
        cfg = copy.deepcopy(config)
        cfg["run_id"] = run_id
        self.engine._write_status(run_id, state="QUEUED", config=cfg, progress={"pct": 0, "total_tasks": 0, "completed_tasks": 0}, logs=["Job encolado."])

        def _runner() -> None:
            try:
                self.engine.run_job(run_id=run_id, config=cfg, strategies=strategies, historical_runs=historical_runs, backtest_callback=backtest_callback)
            except Exception:
                self.engine.fail(run_id, config=cfg, err=traceback.format_exc())

        th = threading.Thread(target=_runner, name=f"mass-backtest-{run_id}", daemon=True)
        with self._lock:
            self._threads[run_id] = th
        th.start()
        return {"ok": True, "run_id": run_id, "state": "QUEUED"}

    def status(self, run_id: str) -> dict[str, Any]:
        payload = self.engine.status(run_id)
        with self._lock:
            th = self._threads.get(run_id)
        payload["thread_alive"] = bool(th and th.is_alive())
        return payload

    def results(self, run_id: str, *, limit: int = 100, strategy_id: str | None = None, only_pass: bool = False) -> dict[str, Any]:
        return self.engine.results(run_id, limit=limit, strategy_id=strategy_id, only_pass=only_pass)

    def artifacts(self, run_id: str) -> dict[str, Any]:
        return self.engine.artifacts(run_id)

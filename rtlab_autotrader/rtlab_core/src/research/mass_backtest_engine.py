from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import random
import sqlite3
import threading
import traceback
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from rtlab_core.backtest import BacktestCatalogDB, CostModelResolver, FundamentalsCreditFilter
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


def _var(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = _avg(vals)
    return sum((x - m) ** 2 for x in vals) / len(vals)


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


def _norm_cdf_scalar(z: float) -> float:
    try:
        if math.isnan(z) or math.isinf(z):
            return 0.5
        return 0.5 * (1.0 + math.erf(float(z) / math.sqrt(2.0)))
    except Exception:
        return 0.5


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
        self.cost_model_resolver = CostModelResolver(catalog=self.backtest_catalog)
        self.fundamentals_filter = FundamentalsCreditFilter(catalog=self.backtest_catalog)
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

    def _default_micro_policy(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "order_flow_level": 1,
            "vpin": {
                "enabled": True,
                "time_bar_seconds": 60,
                "target_draws_per_day": 9,
                "bucket_volume_V": {"mode": "adv_div_target_draws", "fallback_fixed_V": 200000},
                "window_buckets_n": 50,
                "bulk_classification": {"method": "standard_normal_cdf", "sigma_price_change_lookback_bars": 390},
                "thresholds": {"soft_kill_cdf": 0.90, "hard_kill_cdf": 0.97},
            },
            "spread_guard": {"enabled": True, "lookback_minutes": 60, "soft_kill_if_spread_gt_multiplier_of_median": 2.0},
            "slippage_guard": {"enabled": True, "lookback_fills": 30, "soft_kill_if_slippage_gt_multiplier_of_expected": 2.0},
            "volatility_guard": {"enabled": True, "lookback_minutes": 60, "soft_kill_if_realized_vol_gt_multiplier": 3.0},
        }

    def _micro_policy(self, cfg: dict[str, Any]) -> dict[str, Any]:
        snap = cfg.get("policy_snapshot") if isinstance(cfg.get("policy_snapshot"), dict) else {}
        micro_file = snap.get("microstructure") if isinstance(snap.get("microstructure"), dict) else {}
        root = micro_file.get("microstructure") if isinstance(micro_file.get("microstructure"), dict) else {}
        base = self._default_micro_policy()
        if isinstance(root, dict) and root:
            # shallow merge by section; good enough for stable schema
            for key, value in root.items():
                if isinstance(value, dict) and isinstance(base.get(key), dict):
                    merged = dict(base.get(key) or {})
                    merged.update(value)
                    if key == "vpin" and isinstance(base.get("vpin"), dict):
                        # merge nested vpin sections one level deeper
                        for nk in ("bucket_volume_V", "bulk_classification", "thresholds"):
                            if isinstance((base.get("vpin") or {}).get(nk), dict) and isinstance(value.get(nk), dict):
                                vv = dict((base.get("vpin") or {}).get(nk) or {})
                                vv.update(value.get(nk) or {})
                                merged[nk] = vv
                    base[key] = merged
                else:
                    base[key] = value
        return base

    def _gates_policy(self, cfg: dict[str, Any]) -> dict[str, Any]:
        snap = cfg.get("policy_snapshot") if isinstance(cfg.get("policy_snapshot"), dict) else {}
        gates_file = snap.get("gates") if isinstance(snap.get("gates"), dict) else {}
        root = gates_file.get("gates") if isinstance(gates_file.get("gates"), dict) else {}
        defaults = {
            "pbo": {"enabled": True, "reject_if_gt": 0.05, "metric": "sharpe", "cscv": {"S": 8, "bootstrap_iters": 2000}},
            "dsr": {"enabled": True, "min_dsr": 0.95, "require_trials_stats": True},
            "walk_forward": {"enabled": True, "folds": 5, "pass_if_positive_folds_at_least": 4, "max_is_to_oos_degradation": 0.30},
            "cost_stress": {"enabled": True, "multipliers": [1.5, 2.0], "must_remain_profitable_at_1_5x": True, "max_score_drop_at_2_0x": 0.50},
            "min_trade_quality": {"enabled": True, "min_trades_per_run": 150, "min_trades_per_symbol": 30},
        }
        out = copy.deepcopy(defaults)
        if isinstance(root, dict):
            for key, value in root.items():
                if isinstance(value, dict) and isinstance(out.get(key), dict):
                    merged = dict(out.get(key) or {})
                    merged.update(value)
                    if key == "pbo" and isinstance(merged.get("cscv"), dict) and isinstance((value or {}).get("cscv"), dict):
                        c = dict((out.get("pbo") or {}).get("cscv") or {})
                        c.update((value or {}).get("cscv") or {})
                        merged["cscv"] = c
                    out[key] = merged
                else:
                    out[key] = value
        return out

    def _batch_cscv_pbo(self, *, ranked_input: list[dict[str, Any]], gates_policy: dict[str, Any]) -> dict[str, Any]:
        pbo_cfg = gates_policy.get("pbo") if isinstance(gates_policy.get("pbo"), dict) else {}
        cscv_cfg = pbo_cfg.get("cscv") if isinstance(pbo_cfg.get("cscv"), dict) else {}
        if not bool(pbo_cfg.get("enabled", True)):
            return {"available": False, "enabled": False, "pbo": None, "splits_used": 0, "reason": "disabled"}

        metric_key = "sharpe_oos" if str(pbo_cfg.get("metric") or "sharpe").lower().startswith("sharpe") else "sharpe_oos"
        fold_ids = sorted(
            {
                _i(f.get("fold"))
                for row in ranked_input
                for f in ((row.get("folds") or []) if isinstance(row.get("folds"), list) else [])
                if _i(f.get("fold")) > 0
            }
        )
        if len(fold_ids) < 2 or len(ranked_input) < 2:
            return {"available": False, "enabled": True, "pbo": None, "splits_used": 0, "reason": "insufficient_variants_or_folds"}
        fold_to_pos = {fid: idx for idx, fid in enumerate(fold_ids)}
        matrix: list[list[float]] = []
        for row in ranked_input:
            vals = [0.0] * len(fold_ids)
            for f in ((row.get("folds") or []) if isinstance(row.get("folds"), list) else []):
                pos = fold_to_pos.get(_i(f.get("fold")))
                if pos is None:
                    continue
                vals[pos] = _f(f.get(metric_key))
            matrix.append(vals)
        m = len(fold_ids)
        k = max(1, min(m - 1, m // 2))
        # Generate combinations, capped by bootstrap_iters
        from itertools import combinations

        combos = list(combinations(range(m), k))
        max_splits = max(1, _i(cscv_cfg.get("bootstrap_iters"), 2000))
        if len(combos) > max_splits:
            rng = random.Random(1337 + len(ranked_input) + m)
            rng.shuffle(combos)
            combos = combos[:max_splits]
        events = 0
        splits_used = 0
        rel_ranks: list[float] = []
        for is_idx in combos:
            oos_idx = tuple(i for i in range(m) if i not in set(is_idx))
            if not oos_idx:
                continue
            is_scores = [_avg([row[i] for i in is_idx]) for row in matrix]
            oos_scores = [_avg([row[i] for i in oos_idx]) for row in matrix]
            best_is = max(range(len(is_scores)), key=lambda i: is_scores[i])
            target_oos = oos_scores[best_is]
            # relative rank in OOS, 1.0 = best, 0.0 = worst
            sorted_oos = sorted(oos_scores)
            rank_pos = sum(1 for x in sorted_oos if x <= target_oos)
            rel_rank = rank_pos / max(1, len(sorted_oos))
            rel_ranks.append(rel_rank)
            if rel_rank <= 0.5:  # below/at median OOS => overfitting event
                events += 1
            splits_used += 1
        pbo = (events / splits_used) if splits_used else None
        return {
            "available": pbo is not None,
            "enabled": True,
            "metric": metric_key,
            "pbo": None if pbo is None else round(float(pbo), 6),
            "splits_used": int(splits_used),
            "events": int(events),
            "avg_oos_rel_rank": round(_avg(rel_ranks), 6) if rel_ranks else None,
            "reject_if_gt": _f(pbo_cfg.get("reject_if_gt"), 0.05),
        }

    def _load_dataset_frame_for_micro(self, dataset_info: Any) -> tuple[Any | None, dict[str, Any]]:
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:
            return None, {"available": False, "reason": f"pandas_missing:{exc}"}
        files = [str(x) for x in (getattr(dataset_info, "files", None) or []) if str(x).strip()]
        manifest = getattr(dataset_info, "manifest", None) or {}
        if isinstance(manifest, dict):
            for x in manifest.get("files") or []:
                if isinstance(x, str) and x not in files:
                    files.append(x)
        for raw in files:
            path = Path(str(raw))
            if not path.exists() or not path.is_file():
                continue
            try:
                if path.suffix.lower() == ".parquet":
                    df = pd.read_parquet(path)
                else:
                    df = pd.read_csv(path)
                cols = {str(c).lower(): c for c in df.columns}
                if "timestamp" not in cols:
                    # common binance raw kline column
                    if "open_time" in cols:
                        df["timestamp"] = pd.to_datetime(df[cols["open_time"]], unit="ms", utc=True)
                    else:
                        continue
                else:
                    df["timestamp"] = pd.to_datetime(df[cols["timestamp"]], utc=True, errors="coerce")
                for c in ("open", "high", "low", "close", "volume"):
                    src = cols.get(c, c)
                    if src in df.columns:
                        df[c] = pd.to_numeric(df[src], errors="coerce")
                if not {"timestamp", "close", "volume"}.issubset(set(df.columns)):
                    continue
                out = df[[c for c in ("timestamp", "open", "high", "low", "close", "volume") if c in df.columns]].copy()
                out = out.dropna(subset=["timestamp", "close", "volume"]).sort_values("timestamp")
                if out.empty:
                    continue
                return out, {
                    "available": True,
                    "source_file": str(path),
                    "rows": int(len(out)),
                    "start": str(out["timestamp"].iloc[0].isoformat()),
                    "end": str(out["timestamp"].iloc[-1].isoformat()),
                }
            except Exception:
                continue
        return None, {"available": False, "reason": "dataset_files_unreadable_or_missing"}

    def _compute_microstructure_dataset_debug(self, *, df: Any, cfg: dict[str, Any]) -> dict[str, Any]:
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:
            return {"available": False, "reason": f"pandas_missing:{exc}"}
        policy = self._micro_policy(cfg)
        if not bool(policy.get("enabled", True)) or not bool((policy.get("vpin") or {}).get("enabled", True)):
            return {"available": False, "reason": "microstructure_disabled", "policy": policy}
        if df is None or len(df) < 20:
            return {"available": False, "reason": "insufficient_rows", "policy": policy}

        vpin_cfg = policy.get("vpin") if isinstance(policy.get("vpin"), dict) else {}
        spread_cfg = policy.get("spread_guard") if isinstance(policy.get("spread_guard"), dict) else {}
        slip_cfg = policy.get("slippage_guard") if isinstance(policy.get("slippage_guard"), dict) else {}
        vol_cfg = policy.get("volatility_guard") if isinstance(policy.get("volatility_guard"), dict) else {}
        thr = vpin_cfg.get("thresholds") if isinstance(vpin_cfg.get("thresholds"), dict) else {}
        soft_thr = _f(thr.get("soft_kill_cdf"), 0.90)
        hard_thr = _f(thr.get("hard_kill_cdf"), 0.97)
        target_draws = max(1, _i(vpin_cfg.get("target_draws_per_day"), 9))
        win_buckets = max(5, _i(vpin_cfg.get("window_buckets_n"), 50))
        sigma_lb = max(5, _i((vpin_cfg.get("bulk_classification") or {}).get("sigma_price_change_lookback_bars"), 390))

        data = df.copy()
        data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True, errors="coerce")
        data = data.dropna(subset=["timestamp", "close", "volume"]).sort_values("timestamp")
        if data.empty:
            return {"available": False, "reason": "empty_after_normalize", "policy": policy}

        # Price-change sigma and bulk buy/sell volume proxy from 1m bars (L1)
        data["dprice"] = data["close"].diff().fillna(0.0)
        sigma = data["dprice"].rolling(sigma_lb, min_periods=max(10, sigma_lb // 6)).std(ddof=0)
        sigma = sigma.replace(0, float("nan")).fillna(method="bfill").fillna(method="ffill")
        data["z"] = (data["dprice"] / sigma).replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
        data["buy_prob"] = data["z"].map(_norm_cdf_scalar)
        data["sell_prob"] = 1.0 - data["buy_prob"]

        # ADV and volume bucket size V = ADV / target_draws (fallback fixed)
        daily_vol = data.assign(day=data["timestamp"].dt.date).groupby("day")["volume"].sum()
        adv = _f(daily_vol.mean(), 0.0)
        bucket_cfg = vpin_cfg.get("bucket_volume_V") if isinstance(vpin_cfg.get("bucket_volume_V"), dict) else {}
        bucket_v = adv / target_draws if adv > 0 else 0.0
        if bucket_v <= 0:
            bucket_v = _f(bucket_cfg.get("fallback_fixed_V"), 200000.0)
        bucket_v = max(1.0, bucket_v)

        # Build volume-time buckets from bars (splitting bars if needed)
        buckets: list[dict[str, Any]] = []
        rem = bucket_v
        vb = 0.0
        vs = 0.0
        end_ts = None
        end_close = None
        for row in data.itertuples(index=False):
            vol = max(0.0, _f(getattr(row, "volume", 0.0)))
            bp = max(0.0, min(1.0, _f(getattr(row, "buy_prob", 0.5), 0.5)))
            ts = getattr(row, "timestamp")
            close = _f(getattr(row, "close", 0.0))
            remaining_bar = vol
            if remaining_bar <= 0:
                continue
            while remaining_bar > 0:
                take = min(rem, remaining_bar)
                vb += take * bp
                vs += take * (1.0 - bp)
                rem -= take
                remaining_bar -= take
                end_ts = ts
                end_close = close
                if rem <= 1e-9:
                    buckets.append({"timestamp": end_ts, "close": end_close, "V_B": vb, "V_S": vs, "V": bucket_v})
                    rem = bucket_v
                    vb = 0.0
                    vs = 0.0
        if not buckets:
            return {"available": False, "reason": "no_volume_buckets", "policy": policy}

        bdf = pd.DataFrame(buckets)
        bdf["OI"] = (bdf["V_B"] - bdf["V_S"]).abs()
        bdf["VPIN"] = bdf["OI"].rolling(win_buckets, min_periods=max(5, win_buckets // 3)).mean() / float(bucket_v)
        bdf["VPIN"] = bdf["VPIN"].clip(lower=0.0).fillna(method="bfill").fillna(method="ffill").fillna(0.0)

        # Empirical rolling CDF over ~30 days worth of draws
        cdf_window = max(win_buckets, target_draws * 30)
        vpin_vals = [float(x) for x in bdf["VPIN"].tolist()]
        cdfs: list[float] = []
        for idx, cur_v in enumerate(vpin_vals):
            start_idx = max(0, idx - cdf_window + 1)
            w = vpin_vals[start_idx : idx + 1]
            cdfs.append(sum(1 for x in w if x <= cur_v) / max(1, len(w)))
        bdf["VPIN_CDF"] = cdfs

        # Proxies for spread/slippage/vol
        base_costs = cfg.get("costs") if isinstance(cfg.get("costs"), dict) else {}
        base_spread_bps = max(0.1, _f(base_costs.get("spread_bps"), 1.0))
        base_slippage_bps = max(0.1, _f(base_costs.get("slippage_bps"), 2.0))
        lookback_min = max(5, _i(spread_cfg.get("lookback_minutes"), 60))
        vol_lb = max(5, _i(vol_cfg.get("lookback_minutes"), 60))
        ret = data["close"].pct_change().fillna(0.0)
        data["realized_vol"] = ret.rolling(vol_lb, min_periods=max(5, vol_lb // 4)).std(ddof=0).fillna(0.0)
        data["realized_vol_med"] = data["realized_vol"].rolling(lookback_min, min_periods=max(5, lookback_min // 4)).median().replace(0, float("nan"))
        data["vol_multiplier"] = (data["realized_vol"] / data["realized_vol_med"]).replace([float("inf"), float("-inf")], 1.0).fillna(1.0).clip(lower=0.0)
        data["spread_bps_proxy"] = base_spread_bps * data["vol_multiplier"].clip(lower=1.0)
        data["spread_med"] = data["spread_bps_proxy"].rolling(lookback_min, min_periods=max(5, lookback_min // 4)).median().replace(0, float("nan"))
        data["spread_multiplier"] = (data["spread_bps_proxy"] / data["spread_med"]).replace([float("inf"), float("-inf")], 1.0).fillna(1.0).clip(lower=0.0)
        data["slippage_bps_proxy"] = base_slippage_bps * data["vol_multiplier"].clip(lower=1.0)
        data["slippage_multiplier"] = (data["slippage_bps_proxy"] / max(0.0001, base_slippage_bps)).clip(lower=0.0)

        # Map 1m bar proxies to bucket timestamps (asof nearest previous bar)
        merge_cols = [
            "timestamp",
            "spread_bps_proxy",
            "spread_multiplier",
            "slippage_bps_proxy",
            "slippage_multiplier",
            "realized_vol",
            "vol_multiplier",
        ]
        mdf = data[merge_cols].dropna(subset=["timestamp"]).sort_values("timestamp")
        bdf = pd.merge_asof(
            bdf.sort_values("timestamp"),
            mdf.sort_values("timestamp"),
            on="timestamp",
            direction="backward",
        )
        bdf["spread_bps_proxy"] = bdf["spread_bps_proxy"].fillna(base_spread_bps)
        bdf["spread_multiplier"] = bdf["spread_multiplier"].fillna(1.0)
        bdf["slippage_bps_proxy"] = bdf["slippage_bps_proxy"].fillna(base_slippage_bps)
        bdf["slippage_multiplier"] = bdf["slippage_multiplier"].fillna(1.0)
        bdf["realized_vol"] = bdf["realized_vol"].fillna(0.0)
        bdf["vol_multiplier"] = bdf["vol_multiplier"].fillna(1.0)

        spread_thr = _f(spread_cfg.get("soft_kill_if_spread_gt_multiplier_of_median"), 2.0)
        slip_thr = _f(slip_cfg.get("soft_kill_if_slippage_gt_multiplier_of_expected"), 2.0)
        vol_thr = _f(vol_cfg.get("soft_kill_if_realized_vol_gt_multiplier"), 3.0)

        bdf["soft_vpin"] = bdf["VPIN_CDF"] >= soft_thr
        bdf["hard_vpin"] = bdf["VPIN_CDF"] >= hard_thr
        bdf["soft_spread"] = bdf["spread_multiplier"] > spread_thr
        bdf["soft_slippage"] = bdf["slippage_multiplier"] > slip_thr
        bdf["soft_vol"] = bdf["vol_multiplier"] > vol_thr
        bdf["soft_kill_symbol"] = bdf[["soft_vpin", "soft_spread", "soft_slippage", "soft_vol"]].any(axis=1)
        bdf["hard_kill_symbol"] = bdf["hard_vpin"]

        return {
            "available": True,
            "policy": {
                "order_flow_level": 1,
                "vpin_soft_kill_cdf": soft_thr,
                "vpin_hard_kill_cdf": hard_thr,
                "target_draws_per_day": target_draws,
                "bucket_volume_V": round(bucket_v, 6),
                "window_buckets_n": win_buckets,
                "spread_soft_multiplier": spread_thr,
                "slippage_soft_multiplier": slip_thr,
                "vol_soft_multiplier": vol_thr,
            },
            "bars_rows": int(len(data)),
            "bucket_rows": int(len(bdf)),
            "bucket_frame": bdf,
        }

    def _micro_fold_snapshot(self, *, micro_debug: dict[str, Any] | None, fold: FoldWindow) -> dict[str, Any]:
        if not isinstance(micro_debug, dict) or not bool(micro_debug.get("available")):
            return {
                "available": False,
                "reason": str((micro_debug or {}).get("reason") or "microstructure_unavailable"),
                "soft_kill_symbol": False,
                "hard_kill_symbol": False,
                "kill_reasons": [],
            }
        bdf = micro_debug.get("bucket_frame")
        if bdf is None:
            return {"available": False, "reason": "bucket_frame_missing", "soft_kill_symbol": False, "hard_kill_symbol": False, "kill_reasons": []}
        try:
            import pandas as pd  # type: ignore

            t0 = pd.Timestamp(fold.test_start).tz_localize("UTC")
            t1 = pd.Timestamp(fold.test_end).tz_localize("UTC") + pd.Timedelta(days=1)
            rows = bdf[(bdf["timestamp"] >= t0) & (bdf["timestamp"] < t1)]
            if rows.empty:
                rows = bdf.tail(min(20, len(bdf)))
            if rows.empty:
                return {"available": False, "reason": "no_rows_for_fold", "soft_kill_symbol": False, "hard_kill_symbol": False, "kill_reasons": []}
            soft_kill = bool(rows["soft_kill_symbol"].any())
            hard_kill = bool(rows["hard_kill_symbol"].any())
            reasons: list[str] = []
            if bool(rows["hard_vpin"].any()):
                reasons.append("VPIN_CDF>=hard")
            if bool(rows["soft_vpin"].any()) and "VPIN_CDF>=hard" not in reasons:
                reasons.append("VPIN_CDF>=soft")
            if bool(rows["soft_spread"].any()):
                reasons.append("spread_multiplier")
            if bool(rows["soft_slippage"].any()):
                reasons.append("slippage_multiplier")
            if bool(rows["soft_vol"].any()):
                reasons.append("realized_vol_multiplier")
            return {
                "available": True,
                "bar_count": int(len(rows)),
                "vpin": round(_f(rows["VPIN"].iloc[-1]), 6),
                "vpin_cdf": round(_f(rows["VPIN_CDF"].max()), 6),
                "vpin_cdf_avg": round(_f(rows["VPIN_CDF"].mean()), 6),
                "spread_bps": round(_f(rows["spread_bps_proxy"].mean()), 6),
                "spread_multiplier": round(_f(rows["spread_multiplier"].max()), 6),
                "slippage_bps": round(_f(rows["slippage_bps_proxy"].mean()), 6),
                "slippage_multiplier": round(_f(rows["slippage_multiplier"].max()), 6),
                "realized_vol": round(_f(rows["realized_vol"].mean()), 8),
                "vol_multiplier": round(_f(rows["vol_multiplier"].max()), 6),
                "soft_kill_symbol": soft_kill,
                "hard_kill_symbol": hard_kill,
                "kill_reasons": reasons,
            }
        except Exception as exc:
            return {"available": False, "reason": f"micro_fold_error:{exc}", "soft_kill_symbol": False, "hard_kill_symbol": False, "kill_reasons": []}

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

    def _fold_summary(self, run: dict[str, Any], fold: FoldWindow, *, micro: dict[str, Any] | None = None) -> dict[str, Any]:
        m = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        c = run.get("costs_breakdown") if isinstance(run.get("costs_breakdown"), dict) else {}
        micro_row = micro if isinstance(micro, dict) else {}
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
            "profit_factor": _f(m.get("profit_factor")),
            "dataset_hash": str(run.get("dataset_hash") or ""),
            "provenance": run.get("provenance") if isinstance(run.get("provenance"), dict) else {},
            "run_id": str(run.get("id") or ""),
            "microstructure": micro_row,
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

    def _gates_policy(self, cfg: dict[str, Any]) -> dict[str, Any]:
        snap = cfg.get("policy_snapshot") if isinstance(cfg.get("policy_snapshot"), dict) else {}
        gates_file = snap.get("gates") if isinstance(snap.get("gates"), dict) else {}
        gates = gates_file.get("gates") if isinstance(gates_file.get("gates"), dict) else {}
        if gates:
            return gates
        # Fallback coherente con config/policies/gates.yaml
        return {
            "pbo": {"enabled": True, "reject_if_gt": 0.05, "metric": "sharpe", "cscv": {"S": 8, "bootstrap_iters": 2000}},
            "dsr": {"enabled": True, "min_dsr": 0.95, "require_trials_stats": True},
            "walk_forward": {"enabled": True, "folds": 5, "pass_if_positive_folds_at_least": 4, "max_is_to_oos_degradation": 0.30},
            "cost_stress": {"enabled": True, "multipliers": [1.5, 2.0], "must_remain_profitable_at_1_5x": True, "max_score_drop_at_2_0x": 0.50},
            "min_trade_quality": {"enabled": True, "min_trades_per_run": 150, "min_trades_per_symbol": 30},
        }

    def _cscv_pbo_batch(self, *, rows: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
        pbo_cfg = policy.get("pbo") if isinstance(policy.get("pbo"), dict) else {}
        if not bool(pbo_cfg.get("enabled", False)):
            return {"enabled": False, "available": False, "pbo": None, "splits_used": 0, "reason": "disabled"}
        variants = [r for r in rows if isinstance(r, dict)]
        if len(variants) < 2:
            return {"enabled": True, "available": False, "pbo": None, "splits_used": 0, "reason": "not_enough_variants"}
        fold_counts = [len([f for f in (r.get("folds") or []) if isinstance(f, dict)]) for r in variants]
        m = min(fold_counts) if fold_counts else 0
        if m < 2:
            return {"enabled": True, "available": False, "pbo": None, "splits_used": 0, "reason": "not_enough_folds"}

        metric_key = "sharpe_oos" if str(pbo_cfg.get("metric") or "sharpe").lower() == "sharpe" else str(pbo_cfg.get("metric"))
        matrix: list[list[float]] = []
        for r in variants:
            folds = [f for f in (r.get("folds") or []) if isinstance(f, dict)]
            row_vals = [_f(folds[i].get(metric_key if metric_key.endswith("_oos") else f"{metric_key}_oos" if f"{metric_key}_oos" in folds[i] else metric_key)) for i in range(m)]
            matrix.append(row_vals)

        k = max(1, m // 2)
        all_combos = list(itertools.combinations(range(m), k))
        max_iters = _i(((pbo_cfg.get("cscv") or {}) if isinstance(pbo_cfg.get("cscv"), dict) else {}).get("bootstrap_iters"), 2000)
        if len(all_combos) > max_iters > 0:
            rng = random.Random(int(_sha({"run": [r.get("variant_id") for r in variants], "m": m})[:8], 16))
            sampled = rng.sample(all_combos, max_iters)
        else:
            sampled = all_combos
        if not sampled:
            return {"enabled": True, "available": False, "pbo": None, "splits_used": 0, "reason": "no_splits"}

        lambdas: list[float] = []
        nonpositive = 0
        for is_idx in sampled:
            is_set = set(is_idx)
            oos_idx = [i for i in range(m) if i not in is_set]
            if not oos_idx:
                continue
            is_scores = [_avg([row[i] for i in is_idx]) for row in matrix]
            oos_scores = [_avg([row[i] for i in oos_idx]) for row in matrix]
            best_ix = max(range(len(is_scores)), key=lambda i: is_scores[i])
            ranked_oos = sorted(range(len(oos_scores)), key=lambda i: oos_scores[i], reverse=True)
            rank_pos = ranked_oos.index(best_ix) + 1  # 1 = mejor
            # Percentil "bueno" alto; convertir a logit CSCV-style (lambda <= 0 => sobreajuste)
            percentile_good = 1.0 - ((rank_pos - 0.5) / max(1.0, float(len(oos_scores))))
            percentile_good = min(0.999999, max(0.000001, percentile_good))
            lam = math.log(percentile_good / (1.0 - percentile_good))
            lambdas.append(lam)
            if lam <= 0:
                nonpositive += 1
        if not lambdas:
            return {"enabled": True, "available": False, "pbo": None, "splits_used": 0, "reason": "no_valid_splits"}
        pbo = nonpositive / len(lambdas)
        return {
            "enabled": True,
            "available": True,
            "pbo": round(pbo, 6),
            "splits_used": len(lambdas),
            "lambda_median": round(sorted(lambdas)[len(lambdas) // 2], 6),
            "metric": str(pbo_cfg.get("metric") or "sharpe"),
            "threshold": _f(pbo_cfg.get("reject_if_gt"), 0.05),
        }

    def _apply_advanced_gates(self, *, rows: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
        policy = self._gates_policy(cfg)
        pbo_batch = self._cscv_pbo_batch(rows=rows, policy=policy)
        sharpe_trials = [_f(((r.get("summary") or {}) if isinstance(r.get("summary"), dict) else {}).get("sharpe_oos")) for r in rows if isinstance(r, dict)]
        sharpe_trial_var = _var(sharpe_trials)
        n_trials = max(1, len(sharpe_trials))
        wf_cfg = policy.get("walk_forward") if isinstance(policy.get("walk_forward"), dict) else {}
        dsr_cfg = policy.get("dsr") if isinstance(policy.get("dsr"), dict) else {}
        stress_cfg = policy.get("cost_stress") if isinstance(policy.get("cost_stress"), dict) else {}
        trade_quality_cfg = policy.get("min_trade_quality") if isinstance(policy.get("min_trade_quality"), dict) else {}
        pbo_cfg = policy.get("pbo") if isinstance(policy.get("pbo"), dict) else {}

        gates_pass_count = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
            folds = [f for f in (row.get("folds") or []) if isinstance(f, dict)]
            anti = row.get("anti_overfitting") if isinstance(row.get("anti_overfitting"), dict) else {}

            # DSR (deflated Sharpe proxy con stats de batch/trials)
            sharpe_mean = _f(summary.get("sharpe_oos"))
            fold_sharpes = [_f(f.get("sharpe_oos")) for f in folds]
            fold_sharpe_std = _std(fold_sharpes)
            eff_std = max(1e-6, fold_sharpe_std if fold_sharpe_std > 0 else math.sqrt(max(1e-9, sharpe_trial_var)))
            expected_max_null = math.sqrt(max(0.0, 2.0 * math.log(max(2, n_trials)))) * math.sqrt(max(1e-9, sharpe_trial_var))
            z_dsr = (sharpe_mean - expected_max_null) / (eff_std / math.sqrt(max(1, len(folds))))
            dsr_value = _norm_cdf_scalar(z_dsr) if bool(dsr_cfg.get("enabled", False)) else None

            # Walk-forward gate (positividad + degradación proxy)
            positive_folds = sum(1 for f in folds if _f(f.get("net_pnl")) > 0)
            wf_required_folds = _i(wf_cfg.get("folds"), 5)
            wf_required_positive = _i(wf_cfg.get("pass_if_positive_folds_at_least"), 4)
            # proxy: caída desde fold "peak" a promedio OOS (conservador y reproducible)
            peak_sharpe = max(fold_sharpes) if fold_sharpes else 0.0
            wf_degradation_proxy = 0.0 if peak_sharpe <= 0 else max(0.0, (peak_sharpe - sharpe_mean) / max(1e-6, abs(peak_sharpe)))

            # Cost stress (x1.5 / x2.0)
            gross = _f(summary.get("gross_pnl_oos"))
            costs_total = _f(summary.get("costs_total"))
            net_base = _f(summary.get("net_pnl_oos"))
            net_1_5 = gross - (costs_total * 1.5)
            net_2_0 = gross - (costs_total * 2.0)
            net_drop_ratio_2_0 = 0.0
            if abs(net_base) > 1e-6:
                net_drop_ratio_2_0 = max(0.0, (net_base - net_2_0) / abs(net_base))
            else:
                net_drop_ratio_2_0 = 1.0 if net_2_0 < 0 else 0.0

            checks: dict[str, Any] = {}
            fail_reasons: list[str] = []

            # PBO / CSCV batch-level
            pbo_threshold = _f(pbo_cfg.get("reject_if_gt"), 0.05)
            pbo_value = pbo_batch.get("pbo")
            pbo_pass = bool(not bool(pbo_cfg.get("enabled", False)) or (pbo_batch.get("available") and _f(pbo_value, 1.0) <= pbo_threshold))
            if bool(pbo_cfg.get("enabled", False)) and (not pbo_batch.get("available")):
                pbo_pass = False
            checks["pbo_cscv"] = {
                "enabled": bool(pbo_cfg.get("enabled", False)),
                "available": bool(pbo_batch.get("available", False)),
                "value": pbo_value,
                "threshold": pbo_threshold,
                "pass": pbo_pass,
                "scope": "batch",
                "splits_used": _i(pbo_batch.get("splits_used"), 0),
                "metric": str(pbo_batch.get("metric") or pbo_cfg.get("metric") or "sharpe"),
                "reason": pbo_batch.get("reason"),
            }
            if not pbo_pass:
                fail_reasons.append("pbo_cscv")

            # DSR deflated
            dsr_min = _f(dsr_cfg.get("min_dsr"), 0.95)
            dsr_pass = bool(not bool(dsr_cfg.get("enabled", False)) or (_f(dsr_value, 0.0) >= dsr_min))
            checks["dsr_deflated"] = {
                "enabled": bool(dsr_cfg.get("enabled", False)),
                "available": True,
                "value": round(_f(dsr_value, 0.0), 6) if dsr_value is not None else None,
                "min": dsr_min,
                "pass": dsr_pass,
                "trials": n_trials,
                "batch_sharpe_var": round(sharpe_trial_var, 8),
                "expected_max_null": round(expected_max_null, 6),
            }
            if not dsr_pass:
                fail_reasons.append("dsr_deflated")

            # Walk-forward
            wf_folds_pass = len(folds) >= wf_required_folds
            wf_positive_pass = positive_folds >= wf_required_positive
            wf_deg_limit = _f(wf_cfg.get("max_is_to_oos_degradation"), 0.30)
            wf_deg_pass = _f(wf_degradation_proxy) <= wf_deg_limit
            wf_pass = (not bool(wf_cfg.get("enabled", False))) or (wf_folds_pass and wf_positive_pass and wf_deg_pass)
            checks["walk_forward"] = {
                "enabled": bool(wf_cfg.get("enabled", False)),
                "folds": len(folds),
                "folds_required": wf_required_folds,
                "positive_folds": positive_folds,
                "positive_folds_required": wf_required_positive,
                "degradation_proxy": round(wf_degradation_proxy, 6),
                "max_degradation": wf_deg_limit,
                "degradation_metric": "peak_to_avg_sharpe_proxy",
                "pass": wf_pass,
            }
            if not wf_pass:
                fail_reasons.append("walk_forward")

            # Cost stress
            cost_enabled = bool(stress_cfg.get("enabled", False))
            must_1_5 = bool(stress_cfg.get("must_remain_profitable_at_1_5x", True))
            max_drop_2_0 = _f(stress_cfg.get("max_score_drop_at_2_0x"), 0.50)
            stress_1_5_pass = (not cost_enabled) or (net_1_5 > 0 if must_1_5 else True)
            stress_2_0_pass = (not cost_enabled) or (net_drop_ratio_2_0 <= max_drop_2_0)
            checks["cost_stress_1_5x"] = {
                "enabled": cost_enabled,
                "multiplier": 1.5,
                "net_base": round(net_base, 6),
                "net_stress": round(net_1_5, 6),
                "must_remain_profitable": must_1_5,
                "pass": stress_1_5_pass,
            }
            checks["cost_stress_2_0x"] = {
                "enabled": cost_enabled,
                "multiplier": 2.0,
                "net_base": round(net_base, 6),
                "net_stress": round(net_2_0, 6),
                "drop_ratio": round(net_drop_ratio_2_0, 6),
                "max_drop_ratio": max_drop_2_0,
                "pass": stress_2_0_pass,
            }
            if not stress_1_5_pass:
                fail_reasons.append("cost_stress_1_5x")
            if not stress_2_0_pass:
                fail_reasons.append("cost_stress_2_0x")

            # Trade quality (policy)
            min_trades = _i(trade_quality_cfg.get("min_trades_per_run"), 150)
            trade_pass = (not bool(trade_quality_cfg.get("enabled", False))) or (_i(summary.get("trade_count_oos"), 0) >= min_trades)
            checks["min_trade_quality"] = {
                "enabled": bool(trade_quality_cfg.get("enabled", False)),
                "trade_count_oos": _i(summary.get("trade_count_oos"), 0),
                "min_trades_per_run": min_trades,
                "pass": trade_pass,
            }
            if not trade_pass:
                fail_reasons.append("min_trade_quality")

            gates_pass = len(fail_reasons) == 0
            if gates_pass:
                gates_pass_count += 1
            row["gates_eval"] = {
                "passed": gates_pass,
                "fail_reasons": fail_reasons,
                "checks": checks,
                "summary": {
                    "trials": n_trials,
                    "batch_pbo": pbo_batch.get("pbo"),
                    "batch_pbo_splits": pbo_batch.get("splits_used"),
                    "batch_sharpe_var": round(sharpe_trial_var, 8),
                },
            }
            anti["method"] = "batch_cscv_pbo_and_dsr_proxy"
            anti["pbo"] = pbo_batch.get("pbo")
            anti["dsr"] = checks["dsr_deflated"]["value"]
            anti["enforce_ready"] = bool(pbo_batch.get("available")) and bool(dsr_cfg.get("enabled", False))
            anti["promotion_blocked"] = not gates_pass
            anti["promotion_block_reason"] = "Advanced gates failed" if not gates_pass else ""
            row["anti_overfitting"] = anti
            row["promotable"] = bool(row.get("hard_filters_pass")) and gates_pass
            row["recommendable_option_b"] = bool(row.get("hard_filters_pass")) and gates_pass

        return {
            "policy": policy,
            "pbo_cscv_batch": pbo_batch,
            "trials": n_trials,
            "batch_sharpe_var": round(sharpe_trial_var, 8),
            "gates_pass_count": gates_pass_count,
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
                "vpin_cdf": round(
                    _avg(
                        [
                            _f(((r.get("microstructure") or {}) if isinstance(r.get("microstructure"), dict) else {}).get("vpin_cdf"))
                            for r in rows
                        ]
                    ),
                    6,
                ),
                "soft_kill_ratio": round(
                    _avg(
                        [
                            1.0 if bool((((r.get("microstructure") or {}) if isinstance(r.get("microstructure"), dict) else {}).get("soft_kill_symbol"))) else 0.0
                            for r in rows
                        ]
                    ),
                    6,
                ),
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
        if _i(summary.get("micro_hard_kill_folds"), 0) > 0:
            reasons.append("micro_hard_kill")
        score = (
            0.25 * _f(summary.get("sharpe_oos"))
            + 0.20 * _f(summary.get("calmar_oos"))
            + 0.20 * _f(summary.get("expectancy_net_usd"))
            + 0.15 * _f(summary.get("stability"))
            + 0.10 * (1.0 - max(0.0, min(1.0, _f(summary.get("costs_ratio")))))
            + 0.10 * (1.0 - max(0.0, min(1.0, _f(summary.get("max_dd_oos_pct")) / 100.0)))
        )
        score -= 0.25 * _f(summary.get("micro_hard_kill_ratio"))
        score -= 0.10 * _f(summary.get("micro_soft_kill_ratio"))
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
        cost_meta = cfg.get("resolved_cost_metadata") if isinstance(cfg.get("resolved_cost_metadata"), dict) else {}
        fund_meta = cfg.get("resolved_fundamentals_metadata") if isinstance(cfg.get("resolved_fundamentals_metadata"), dict) else {}
        for idx, row in enumerate(rows, start=1):
            summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
            regime = row.get("regime_metrics") if isinstance(row.get("regime_metrics"), dict) else {}
            params = row.get("params") if isinstance(row.get("params"), dict) else {}
            micro = row.get("microstructure") if isinstance(row.get("microstructure"), dict) else {}
            gates_eval = row.get("gates_eval") if isinstance(row.get("gates_eval"), dict) else {}
            gates_checks = gates_eval.get("checks") if isinstance(gates_eval.get("checks"), dict) else {}
            micro_agg = micro.get("aggregate") if isinstance(micro.get("aggregate"), dict) else {}
            micro_symbol_kill = micro.get("symbol_kill") if isinstance(micro.get("symbol_kill"), dict) else {}
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
                    "fee_snapshot_id": cost_meta.get("fee_snapshot_id"),
                    "funding_snapshot_id": cost_meta.get("funding_snapshot_id"),
                    "slippage_model_params": json.dumps(cost_meta.get("slippage_model_params") or {}, ensure_ascii=True, sort_keys=True),
                    "spread_model_params": json.dumps(cost_meta.get("spread_model_params") or {}, ensure_ascii=True, sort_keys=True),
                    "fundamentals_snapshot_id": fund_meta.get("snapshot_id"),
                    "fund_status": str(fund_meta.get("fund_status") or "UNKNOWN"),
                    "fund_allow_trade": 1 if bool(fund_meta.get("allow_trade", True)) else 0,
                    "fund_risk_multiplier": float(fund_meta.get("risk_multiplier") or 1.0),
                    "fund_score": float(_f(fund_meta.get("fund_score"), 0.0)) if fund_meta.get("fund_score") is not None else None,
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
                            "pbo": ((gates_checks.get("pbo_cscv") or {}) if isinstance(gates_checks.get("pbo_cscv"), dict) else {}).get("value", (row.get("anti_overfitting") or {}).get("pbo")),
                            "dsr": ((gates_checks.get("dsr_deflated") or {}) if isinstance(gates_checks.get("dsr_deflated"), dict) else {}).get("value", (row.get("anti_overfitting") or {}).get("dsr")),
                            "vpin_cdf": micro_agg.get("vpin_cdf_oos"),
                            "micro_soft_kill_ratio": micro_agg.get("micro_soft_kill_ratio"),
                            "micro_hard_kill_ratio": micro_agg.get("micro_hard_kill_ratio"),
                            "fund_status": fund_meta.get("fund_status"),
                            "fund_score": fund_meta.get("fund_score"),
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
                    "regime_kpis_json": json.dumps(regime, ensure_ascii=True, sort_keys=True),
                    "flags_json": json.dumps(
                        {
                            "OOS": True,
                            "WFA": True,
                            "PASO_GATES": bool(gates_eval.get("passed", bool(row.get("hard_filters_pass")))),
                            "BASELINE": False,
                            "FAVORITO": idx <= max(1, _i(cfg.get("top_n"), 10)),
                            "ARCHIVADO": False,
                            "DATA_WARNING": bool(len(summary.get("dataset_hashes") or []) > 1),
                            "MICRO_SOFT_KILL": bool(micro_symbol_kill.get("soft")),
                            "MICRO_HARD_KILL": bool(micro_symbol_kill.get("hard")),
                            "ROBUSTEZ": "Alta" if bool(gates_eval.get("passed")) else ("Media" if bool(row.get("hard_filters_pass")) else "Baja"),
                            "GATES_ADV_PASS": bool(gates_eval.get("passed")),
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
                    "artifacts_json": json.dumps(
                        {
                            "batch_id": batch_id,
                            "variant_id": row.get("variant_id"),
                            "gates_eval": gates_eval,
                            "microstructure_debug": {
                                "available": bool(micro.get("available")),
                                "symbol_kill": micro_symbol_kill,
                                "aggregate": micro_agg,
                                "policy": (micro.get("policy") if isinstance(micro.get("policy"), dict) else {}),
                            },
                        },
                        ensure_ascii=True,
                        sort_keys=True,
                    ),
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
        if not bool(getattr(dataset_info, "ready", False)):
            hints = [str(x) for x in (getattr(dataset_info, "hints", None) or []) if str(x).strip()]
            hint_text = " | ".join(hints) if hints else "Verificá dataset_source, symbol, timeframe y rango."
            raise ValueError(
                f"No hay dataset real disponible para {cfg.get('market')}/{cfg.get('symbol')}/{cfg.get('timeframe')} en modo {data_mode}. {hint_text}"
            )
        micro_df, micro_source = self._load_dataset_frame_for_micro(dataset_info)
        micro_debug = self._compute_microstructure_dataset_debug(df=micro_df, cfg=cfg) if micro_df is not None else {"available": False, "reason": str((micro_source or {}).get("reason") or "dataset_not_loaded")}
        if isinstance(micro_debug, dict):
            micro_meta = dict(micro_source or {})
            micro_meta["policy"] = (micro_debug.get("policy") if isinstance(micro_debug.get("policy"), dict) else {})
            cfg["resolved_microstructure_meta"] = {
                "available": bool(micro_debug.get("available")),
                "source": micro_meta,
                "reason": micro_debug.get("reason"),
                "bars_rows": _i(micro_debug.get("bars_rows"), 0),
                "bucket_rows": _i(micro_debug.get("bucket_rows"), 0),
            }
        try:
            cfg["resolved_cost_metadata"] = self.cost_model_resolver.resolve(
                exchange=str(cfg.get("exchange") or "binance"),
                market=str(cfg.get("market") or "crypto"),
                symbol=str(cfg.get("symbol") or (universe[0] if universe else "BTCUSDT")),
                costs=cfg.get("costs") if isinstance(cfg.get("costs"), dict) else {},
                df=None,
            )
        except Exception as exc:
            cfg["resolved_cost_metadata"] = {
                "fee_snapshot_id": None,
                "funding_snapshot_id": None,
                "spread_model_params": {"mode": "static", "source": "metadata_error", "error": str(exc)},
                "slippage_model_params": {"mode": "static", "source": "metadata_error", "error": str(exc)},
            }
        try:
            market_n = str(cfg.get("market") or "crypto").lower()
            symbol_n = str(cfg.get("symbol") or (universe[0] if universe else "BTCUSDT"))
            instrument_type = "common" if market_n == "equities" else "other"
            cfg["resolved_fundamentals_metadata"] = self.fundamentals_filter.evaluate(
                exchange=str(cfg.get("exchange") or "binance"),
                market=market_n,
                symbol=symbol_n,
                instrument_type=instrument_type,
                target_mode="backtest",
                asof_date=_utc_iso(),
                source="auto",
                source_id=f"{run_id}:{symbol_n}",
                raw_payload={"market": market_n, "symbol": symbol_n, "batch_id": run_id},
            )
        except Exception as exc:
            cfg["resolved_fundamentals_metadata"] = {
                "enabled": False,
                "enforced": False,
                "snapshot_id": None,
                "allow_trade": True,
                "risk_multiplier": 1.0,
                "fund_score": 0.0,
                "fund_status": "UNKNOWN",
                "explain": [{"code": "FUNDAMENTALS_METADATA_ERROR", "severity": "WARN", "message": str(exc)}],
            }
        fund_meta = cfg.get("resolved_fundamentals_metadata") if isinstance(cfg.get("resolved_fundamentals_metadata"), dict) else {}
        if bool(fund_meta.get("enforced")) and not bool(fund_meta.get("allow_trade", False)):
            reasons = " | ".join(
                [
                    str((row or {}).get("message") or (row or {}).get("code") or "")
                    for row in (fund_meta.get("explain") or [])
                    if isinstance(row, dict)
                ][:3]
            )
            raise ValueError(f"Fundamentals/credit_filter bloqueó Research Batch para {cfg.get('market')}/{cfg.get('symbol')}. {reasons}".strip())
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
                fold_rows.append(self._fold_summary(run, fold, micro=self._micro_fold_snapshot(micro_debug=micro_debug, fold=fold)))
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
                "winrate_oos": round(_avg([_f(x.get("winrate")) for x in fold_rows]), 6),
                "profit_factor_oos": round(_avg([_f(x.get("profit_factor")) for x in fold_rows]), 6),
                "max_dd_oos_pct": round(_avg([_f(x.get("max_dd_oos_pct")) for x in fold_rows]), 6),
                "expectancy_net_usd": round(_avg([_f(x.get("expectancy_net_usd")) for x in fold_rows]), 6),
                "stability": robust.get("stability", 0.0),
                "consistency_folds": robust.get("consistency_folds", 0.0),
                "jitter_pass_rate": robust.get("jitter_pass_rate", 0.0),
                "dataset_hashes": sorted({str(x.get("dataset_hash") or "") for x in fold_rows if str(x.get("dataset_hash") or "")}),
                "vpin_cdf_oos": round(
                    _avg(
                        [
                            _f((((x.get("microstructure") or {}) if isinstance(x.get("microstructure"), dict) else {}).get("vpin_cdf")))
                            for x in fold_rows
                        ]
                    ),
                    6,
                ),
                "micro_soft_kill_folds": sum(
                    1
                    for x in fold_rows
                    if bool((((x.get("microstructure") or {}) if isinstance(x.get("microstructure"), dict) else {}).get("soft_kill_symbol")))
                ),
                "micro_hard_kill_folds": sum(
                    1
                    for x in fold_rows
                    if bool((((x.get("microstructure") or {}) if isinstance(x.get("microstructure"), dict) else {}).get("hard_kill_symbol")))
                ),
            }
            summary["micro_soft_kill_ratio"] = round(_f(summary.get("micro_soft_kill_folds")) / max(1, len(fold_rows)), 6)
            summary["micro_hard_kill_ratio"] = round(_f(summary.get("micro_hard_kill_folds")) / max(1, len(fold_rows)), 6)
            micro_agg_reasons = sorted(
                {
                    str(reason)
                    for x in fold_rows
                    for reason in (
                        ((((x.get("microstructure") or {}) if isinstance(x.get("microstructure"), dict) else {}).get("kill_reasons")) or [])
                        if isinstance((((x.get("microstructure") or {}) if isinstance(x.get("microstructure"), dict) else {}).get("kill_reasons")), list)
                        else []
                    )
                    if str(reason)
                }
            )
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
                    "microstructure": {
                        "available": bool(micro_debug.get("available")) if isinstance(micro_debug, dict) else False,
                        "policy": (micro_debug.get("policy") if isinstance(micro_debug, dict) and isinstance(micro_debug.get("policy"), dict) else {}),
                        "source": cfg.get("resolved_microstructure_meta") if isinstance(cfg.get("resolved_microstructure_meta"), dict) else {},
                        "aggregate": {
                            "vpin_cdf_oos": summary.get("vpin_cdf_oos"),
                            "micro_soft_kill_folds": summary.get("micro_soft_kill_folds"),
                            "micro_hard_kill_folds": summary.get("micro_hard_kill_folds"),
                            "micro_soft_kill_ratio": summary.get("micro_soft_kill_ratio"),
                            "micro_hard_kill_ratio": summary.get("micro_hard_kill_ratio"),
                        },
                        "symbol_kill": {
                            "soft": bool(_i(summary.get("micro_soft_kill_folds")) > 0),
                            "hard": bool(_i(summary.get("micro_hard_kill_folds")) > 0),
                            "reasons": micro_agg_reasons,
                        },
                        "fold_debug": [
                            {
                                "fold": _i(x.get("fold")),
                                "test_start": x.get("test_start"),
                                "test_end": x.get("test_end"),
                                **(((x.get("microstructure") or {}) if isinstance(x.get("microstructure"), dict) else {})),
                            }
                            for x in fold_rows
                        ],
                    },
                    "score": score,
                    "hard_filters_pass": hard_pass,
                    "hard_filter_reasons": reasons,
                    "promotable": bool(hard_pass and not anti.get("promotion_blocked")),
                    "recommendable_option_b": bool(hard_pass),
                }
            )
        ranked = self.scoring_and_ranking(variants_payload=ranked_input)
        gates_summary = self._apply_advanced_gates(rows=ranked, cfg=cfg)
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
                "gates_pass_count": sum(1 for r in ranked if bool(((r.get("gates_eval") or {}) if isinstance(r.get("gates_eval"), dict) else {}).get("passed"))),
                "promotable_count": sum(1 for r in ranked if bool(r.get("promotable"))),
                "top_n": top_n,
                "gates_batch": gates_summary,
                "anti_perf_chasing": {
                    "min_window_days_paper_testnet": 7,
                    "min_window_days_live": 14,
                    "max_live_switch_per_week": 1,
                    "option_b_no_auto_live": True,
                },
                "fundamentals": {
                    "enabled": bool(fund_meta.get("enabled", False)),
                    "enforced": bool(fund_meta.get("enforced", False)),
                    "allow_trade": bool(fund_meta.get("allow_trade", True)),
                    "status": str(fund_meta.get("fund_status") or "UNKNOWN"),
                    "score": fund_meta.get("fund_score"),
                    "snapshot_id": fund_meta.get("snapshot_id"),
                },
            },
            "results": ranked,
        }
        parquet_info = self._write_results(run_id, payload)
        payload["summary"]["query_backend"] = parquet_info
        _json_dump(self._results_path(run_id), payload)
        manifest = {
            "run_id": run_id,
            "dataset_source": str(cfg.get("dataset_source") or cfg.get("data_source") or dataset_info.dataset_source or "dataset"),
            "dataset_hashes": sorted({h for row in ranked for h in (row.get("summary") or {}).get("dataset_hashes", []) if h} | ({dataset_info.dataset_hash} if dataset_info.dataset_hash else set())),
            "period": {"start": cfg.get("start"), "end": cfg.get("end")},
            "timeframe": cfg.get("timeframe"),
            "universe": universe,
            "costs_used": cfg.get("costs") or {},
            "fundamentals_used": cfg.get("resolved_fundamentals_metadata") if isinstance(cfg.get("resolved_fundamentals_metadata"), dict) else {},
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
            "gates_pass_count": payload["summary"]["gates_pass_count"],
            "top_variant_id": top_rows[0].get("variant_id") if top_rows else None,
            "best_runs_cache": [str(r.get("catalog_run_id") or r.get("backtest_run_id") or "") for r in top_rows[: min(10, len(top_rows))]],
            "run_count_done": len(ranked),
            "run_count_failed": 0,
            "top_score": _f(top_rows[0].get("score"), 0.0) if top_rows else 0.0,
            "parquet": parquet_info,
            "gates_batch": gates_summary,
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
        self._beast_scheduler_thread: threading.Thread | None = None
        self._beast_queue: deque[dict[str, Any]] = deque()
        self._beast_active_run_ids: set[str] = set()
        self._beast_jobs_meta: dict[str, dict[str, Any]] = {}
        self._beast_state_path = (self.engine.root / "beast_mode_state.json").resolve()
        self._beast_stop_requested = False
        self._beast_metrics = self._load_beast_metrics()

    def _load_beast_metrics(self) -> dict[str, Any]:
        payload = _json_load(
            self._beast_state_path,
            {
                "day_key": _iso_date(datetime.now(timezone.utc)),
                "daily_jobs_started": 0,
                "daily_jobs_completed": 0,
                "daily_jobs_failed": 0,
                "daily_trial_units_started": 0,
                "stop_requested": False,
                "history": [],
            },
        )
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("day_key", _iso_date(datetime.now(timezone.utc)))
        payload.setdefault("daily_jobs_started", 0)
        payload.setdefault("daily_jobs_completed", 0)
        payload.setdefault("daily_jobs_failed", 0)
        payload.setdefault("daily_trial_units_started", 0)
        payload.setdefault("stop_requested", False)
        payload.setdefault("history", [])
        self._beast_stop_requested = bool(payload.get("stop_requested"))
        return payload

    def _save_beast_metrics_locked(self) -> None:
        payload = {
            **self._beast_metrics,
            "stop_requested": bool(self._beast_stop_requested),
            "queue": [
                {
                    "run_id": str(item.get("run_id") or ""),
                    "queued_at": str(item.get("queued_at") or ""),
                    "estimated_trial_units": _i(item.get("estimated_trial_units"), 0),
                }
                for item in list(self._beast_queue)
            ],
            "jobs": list(self._beast_jobs_meta.values())[-500:],
        }
        _json_dump(self._beast_state_path, payload)

    def _beast_roll_day_if_needed_locked(self) -> None:
        today = _iso_date(datetime.now(timezone.utc))
        if str(self._beast_metrics.get("day_key") or "") == today:
            return
        history = [h for h in (self._beast_metrics.get("history") or []) if isinstance(h, dict)]
        history.append(
            {
                "day_key": str(self._beast_metrics.get("day_key") or ""),
                "daily_jobs_started": _i(self._beast_metrics.get("daily_jobs_started"), 0),
                "daily_jobs_completed": _i(self._beast_metrics.get("daily_jobs_completed"), 0),
                "daily_jobs_failed": _i(self._beast_metrics.get("daily_jobs_failed"), 0),
                "daily_trial_units_started": _i(self._beast_metrics.get("daily_trial_units_started"), 0),
            }
        )
        self._beast_metrics.update(
            {
                "day_key": today,
                "daily_jobs_started": 0,
                "daily_jobs_completed": 0,
                "daily_jobs_failed": 0,
                "daily_trial_units_started": 0,
                "history": history[-30:],
            }
        )

    def _beast_policy(self, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
        pol_root = (cfg or {}).get("policy_snapshot") if isinstance((cfg or {}).get("policy_snapshot"), dict) else {}
        beast = pol_root.get("beast_mode") if isinstance(pol_root.get("beast_mode"), dict) else {}
        governor = beast.get("budget_governor") if isinstance(beast.get("budget_governor"), dict) else {}
        return {
            "enabled": bool(beast.get("enabled", False)),
            "requires_postgres": bool(beast.get("requires_postgres", False)),
            "max_trials_per_batch": _i(beast.get("max_trials_per_batch"), 5000),
            "max_concurrent_jobs": max(1, _i(beast.get("max_concurrent_jobs"), 4)),
            "rate_limit_enabled": bool(((beast.get("per_exchange_rate_limit") or {}) if isinstance(beast.get("per_exchange_rate_limit"), dict) else {}).get("enabled", False)),
            "max_requests_per_minute": _i(((beast.get("per_exchange_rate_limit") or {}) if isinstance(beast.get("per_exchange_rate_limit"), dict) else {}).get("max_requests_per_minute"), 1200),
            "budget_governor_enabled": bool(governor.get("enabled", False)),
            "daily_job_cap_hobby": _i(governor.get("daily_job_cap_hobby"), 200),
            "daily_job_cap_pro": _i(governor.get("daily_job_cap_pro"), 800),
            "stop_at_budget_pct": _f(governor.get("stop_at_budget_pct"), 80.0),
        }

    def _beast_estimated_trial_units(self, *, cfg: dict[str, Any], strategies: list[dict[str, Any]]) -> int:
        strategy_count = max(1, len([s for s in strategies if isinstance(s, dict)]))
        variants = max(1, _i(cfg.get("max_variants_per_strategy"), 1))
        folds = max(1, _i(cfg.get("max_folds"), 1))
        return max(1, strategy_count * variants * folds)

    def _spawn_job_thread_locked(
        self,
        *,
        run_id: str,
        cfg: dict[str, Any],
        strategies: list[dict[str, Any]],
        historical_runs: list[dict[str, Any]],
        backtest_callback: Callable[[dict[str, Any], FoldWindow, dict[str, Any]], dict[str, Any]],
        beast_mode: bool,
    ) -> None:
        def _runner() -> None:
            try:
                self.engine.run_job(run_id=run_id, config=cfg, strategies=strategies, historical_runs=historical_runs, backtest_callback=backtest_callback)
                if beast_mode:
                    with self._lock:
                        self._beast_active_run_ids.discard(run_id)
                        meta = self._beast_jobs_meta.get(run_id, {})
                        meta.update({"state": "COMPLETED", "finished_at": _utc_iso()})
                        self._beast_jobs_meta[run_id] = meta
                        self._beast_roll_day_if_needed_locked()
                        self._beast_metrics["daily_jobs_completed"] = _i(self._beast_metrics.get("daily_jobs_completed"), 0) + 1
                        self._save_beast_metrics_locked()
            except Exception:
                self.engine.fail(run_id, config=cfg, err=traceback.format_exc())
                if beast_mode:
                    with self._lock:
                        self._beast_active_run_ids.discard(run_id)
                        meta = self._beast_jobs_meta.get(run_id, {})
                        meta.update({"state": "FAILED", "finished_at": _utc_iso()})
                        self._beast_jobs_meta[run_id] = meta
                        self._beast_roll_day_if_needed_locked()
                        self._beast_metrics["daily_jobs_failed"] = _i(self._beast_metrics.get("daily_jobs_failed"), 0) + 1
                        self._save_beast_metrics_locked()

        th = threading.Thread(target=_runner, name=f"mass-backtest-{run_id}", daemon=True)
        self._threads[run_id] = th
        th.start()

    def _ensure_beast_scheduler_locked(self) -> None:
        if self._beast_scheduler_thread and self._beast_scheduler_thread.is_alive():
            return

        def _loop() -> None:
            while True:
                time.sleep(0.25)
                with self._lock:
                    # keep queue loop lightweight and self-healing
                    active_running = [rid for rid in list(self._beast_active_run_ids) if self._threads.get(rid) and self._threads[rid].is_alive()]
                    self._beast_active_run_ids = set(active_running)
                    if self._beast_stop_requested or not self._beast_queue:
                        continue
                    # derive policy from first queued job (all jobs store snapshot)
                    first = self._beast_queue[0] if self._beast_queue else None
                    policy = self._beast_policy(first.get("config") if isinstance(first, dict) else None)
                    max_concurrent = max(1, _i(policy.get("max_concurrent_jobs"), 1))
                    if len(self._beast_active_run_ids) >= max_concurrent:
                        continue
                    task = self._beast_queue.popleft()
                    run_id = str(task.get("run_id") or "")
                    if not run_id:
                        self._save_beast_metrics_locked()
                        continue
                    self._beast_roll_day_if_needed_locked()
                    self._beast_active_run_ids.add(run_id)
                    meta = self._beast_jobs_meta.get(run_id, {})
                    meta.update({"state": "RUNNING", "started_at": _utc_iso()})
                    self._beast_jobs_meta[run_id] = meta
                    self._beast_metrics["daily_jobs_started"] = _i(self._beast_metrics.get("daily_jobs_started"), 0) + 1
                    self._beast_metrics["daily_trial_units_started"] = _i(self._beast_metrics.get("daily_trial_units_started"), 0) + _i(task.get("estimated_trial_units"), 0)
                    self._save_beast_metrics_locked()
                    self._spawn_job_thread_locked(
                        run_id=run_id,
                        cfg=task["config"],
                        strategies=task["strategies"],
                        historical_runs=task["historical_runs"],
                        backtest_callback=task["backtest_callback"],
                        beast_mode=True,
                    )

        self._beast_scheduler_thread = threading.Thread(target=_loop, name="mass-backtest-beast-scheduler", daemon=True)
        self._beast_scheduler_thread.start()

    def _run_id(self) -> str:
        return self.engine.backtest_catalog.next_formatted_id("BX")

    def start_async(self, *, config: dict[str, Any], strategies: list[dict[str, Any]], historical_runs: list[dict[str, Any]], backtest_callback: Callable[[dict[str, Any], FoldWindow, dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
        run_id = self._run_id()
        cfg = copy.deepcopy(config)
        cfg["run_id"] = run_id
        self.engine._write_status(run_id, state="QUEUED", config=cfg, progress={"pct": 0, "total_tasks": 0, "completed_tasks": 0}, logs=["Job encolado."])
        with self._lock:
            self._spawn_job_thread_locked(
                run_id=run_id,
                cfg=cfg,
                strategies=strategies,
                historical_runs=historical_runs,
                backtest_callback=backtest_callback,
                beast_mode=False,
            )
        return {"ok": True, "run_id": run_id, "state": "QUEUED"}

    def start_beast_async(
        self,
        *,
        config: dict[str, Any],
        strategies: list[dict[str, Any]],
        historical_runs: list[dict[str, Any]],
        backtest_callback: Callable[[dict[str, Any], FoldWindow, dict[str, Any]], dict[str, Any]],
        tier: str = "hobby",
    ) -> dict[str, Any]:
        run_id = self._run_id()
        cfg = copy.deepcopy(config)
        cfg["run_id"] = run_id
        cfg["execution_mode"] = "beast"
        cfg["beast_tier"] = str(tier or "hobby").lower()
        policy = self._beast_policy(cfg)
        if not bool(policy.get("enabled")):
            raise ValueError("Modo Bestia deshabilitado por policy.")
        est_trials = self._beast_estimated_trial_units(cfg=cfg, strategies=strategies)
        if est_trials > _i(policy.get("max_trials_per_batch"), 5000):
            raise ValueError(f"Batch excede max_trials_per_batch ({est_trials} > {_i(policy.get('max_trials_per_batch'), 5000)}).")

        with self._lock:
            self._beast_roll_day_if_needed_locked()
            cap_key = "daily_job_cap_pro" if str(tier).lower() == "pro" else "daily_job_cap_hobby"
            cap = max(1, _i(policy.get(cap_key), 200))
            stop_pct = max(1.0, _f(policy.get("stop_at_budget_pct"), 80.0))
            cap_threshold = max(1, int(cap * (stop_pct / 100.0)))
            started_today = _i(self._beast_metrics.get("daily_jobs_started"), 0)
            if bool(policy.get("budget_governor_enabled")) and started_today >= cap_threshold:
                raise ValueError(f"Budget governor activo: {started_today}/{cap} jobs iniciados hoy (stop_at={stop_pct:.0f}%).")
            if self._beast_stop_requested:
                raise ValueError("Modo Bestia en stop-all. Reanuda limpiando el stop antes de encolar nuevos jobs.")

            self.engine._write_status(
                run_id,
                state="QUEUED",
                config=cfg,
                progress={"pct": 0, "total_tasks": 0, "completed_tasks": 0},
                logs=["Job encolado en Modo Bestia."],
            )
            self._beast_jobs_meta[run_id] = {
                "run_id": run_id,
                "state": "QUEUED",
                "queued_at": _utc_iso(),
                "started_at": None,
                "finished_at": None,
                "tier": str(tier).lower(),
                "estimated_trial_units": est_trials,
                "strategy_count": len([s for s in strategies if isinstance(s, dict)]),
                "market": str(cfg.get("market") or ""),
                "symbol": str(cfg.get("symbol") or ""),
                "timeframe": str(cfg.get("timeframe") or ""),
                "max_variants_per_strategy": _i(cfg.get("max_variants_per_strategy"), 0),
                "max_folds": _i(cfg.get("max_folds"), 0),
            }
            self._beast_queue.append(
                {
                    "run_id": run_id,
                    "config": cfg,
                    "strategies": copy.deepcopy(strategies),
                    "historical_runs": copy.deepcopy(historical_runs),
                    "backtest_callback": backtest_callback,
                    "queued_at": _utc_iso(),
                    "estimated_trial_units": est_trials,
                }
            )
            self._save_beast_metrics_locked()
            self._ensure_beast_scheduler_locked()
            q_pos = len(self._beast_queue)
        return {"ok": True, "run_id": run_id, "state": "QUEUED", "mode": "beast", "queue_position": q_pos, "estimated_trial_units": est_trials}

    def beast_status(self) -> dict[str, Any]:
        with self._lock:
            self._beast_roll_day_if_needed_locked()
            active_run_ids = [rid for rid in sorted(self._beast_active_run_ids) if self._threads.get(rid) and self._threads[rid].is_alive()]
            queued = len(self._beast_queue)
            jobs = list(self._beast_jobs_meta.values())
            counts = {
                "queued": sum(1 for j in jobs if str(j.get("state")).upper() == "QUEUED"),
                "running": sum(1 for j in jobs if str(j.get("state")).upper() == "RUNNING"),
                "completed": sum(1 for j in jobs if str(j.get("state")).upper() == "COMPLETED"),
                "failed": sum(1 for j in jobs if str(j.get("state")).upper() == "FAILED"),
                "canceled": sum(1 for j in jobs if str(j.get("state")).upper() == "CANCELED"),
            }
            self._save_beast_metrics_locked()
            metrics = copy.deepcopy(self._beast_metrics)
        last_policy = self._beast_policy((self._beast_queue[0].get("config") if self._beast_queue else None) or {})
        tier = "hobby"
        cap = _i(last_policy.get("daily_job_cap_hobby"), 200)
        stop_pct = max(1.0, _f(last_policy.get("stop_at_budget_pct"), 80.0))
        cap_threshold = max(1, int(cap * (stop_pct / 100.0)))
        return {
            "enabled": bool(last_policy.get("enabled")),
            "scheduler": {
                "thread_alive": bool(self._beast_scheduler_thread and self._beast_scheduler_thread.is_alive()),
                "stop_requested": bool(self._beast_stop_requested),
                "queue_depth": queued,
                "workers_active": len(active_run_ids),
                "active_run_ids": active_run_ids,
                "max_concurrent_jobs": _i(last_policy.get("max_concurrent_jobs"), 1),
                "rate_limit_enabled": bool(last_policy.get("rate_limit_enabled")),
                "max_requests_per_minute": _i(last_policy.get("max_requests_per_minute"), 1200),
                "rate_limit_note": "Control local de scheduler; rate-limit de requests real queda para workers distribuidos.",
            },
            "budget": {
                "tier": tier,
                "daily_cap": cap,
                "stop_at_budget_pct": stop_pct,
                "threshold_jobs": cap_threshold,
                "daily_jobs_started": _i(metrics.get("daily_jobs_started"), 0),
                "daily_jobs_completed": _i(metrics.get("daily_jobs_completed"), 0),
                "daily_jobs_failed": _i(metrics.get("daily_jobs_failed"), 0),
                "daily_trial_units_started": _i(metrics.get("daily_trial_units_started"), 0),
                "usage_pct": (100.0 * _i(metrics.get("daily_jobs_started"), 0) / max(1, cap)),
            },
            "counts": counts,
            "recent_history": list(metrics.get("history") or [])[-7:],
            "requires_postgres": bool(last_policy.get("requires_postgres")),
            "mode": "local_scheduler_phase1",
        }

    def beast_jobs(self, *, limit: int = 100) -> dict[str, Any]:
        with self._lock:
            jobs = sorted(
                [copy.deepcopy(v) for v in self._beast_jobs_meta.values()],
                key=lambda x: str(x.get("queued_at") or x.get("started_at") or ""),
                reverse=True,
            )[: max(1, int(limit))]
        return {"items": jobs, "count": len(jobs)}

    def beast_stop_all(self, *, reason: str = "manual_stop_all") -> dict[str, Any]:
        canceled_ids: list[str] = []
        with self._lock:
            self._beast_stop_requested = True
            while self._beast_queue:
                task = self._beast_queue.popleft()
                run_id = str(task.get("run_id") or "")
                if not run_id:
                    continue
                canceled_ids.append(run_id)
                meta = self._beast_jobs_meta.get(run_id, {})
                meta.update({"state": "CANCELED", "finished_at": _utc_iso(), "cancel_reason": reason})
                self._beast_jobs_meta[run_id] = meta
                self.engine._write_status(
                    run_id,
                    state="CANCELED",
                    config=task.get("config") if isinstance(task.get("config"), dict) else {"run_id": run_id},
                    progress={"pct": 0},
                    logs=[f"Cancelado por Stop All (Modo Bestia): {reason}"],
                )
            active = [rid for rid in self._beast_active_run_ids if self._threads.get(rid) and self._threads[rid].is_alive()]
            self._save_beast_metrics_locked()
        return {
            "ok": True,
            "stop_requested": True,
            "canceled_queued": canceled_ids,
            "active_not_interrupted": active,
            "note": "Stop All (fase local) cancela cola y frena nuevos despachos. Los jobs ya corriendo terminan por seguridad.",
        }

    def beast_resume_dispatch(self) -> dict[str, Any]:
        with self._lock:
            self._beast_stop_requested = False
            self._save_beast_metrics_locked()
            self._ensure_beast_scheduler_locked()
        return {"ok": True, "stop_requested": False}

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

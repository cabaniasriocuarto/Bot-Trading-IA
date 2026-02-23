from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from .brain import (
    MEDIUM_RISK_PROFILE,
    StrategySelector,
    compute_normalized_reward,
    deflated_sharpe_ratio,
    detect_drift,
    pbo_cscv,
)
from .knowledge import KnowledgeLoader


BacktestEvalFn = Callable[[dict[str, Any]], dict[str, Any]]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _json_save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class LearningService:
    def __init__(self, *, user_data_dir: Path, repo_root: Path) -> None:
        self.root = (user_data_dir / "learning").resolve()
        self.status_path = self.root / "status.json"
        self.drift_path = self.root / "drift.json"
        self.recommendations_path = self.root / "recommendations.json"
        self.recommend_runtime_path = self.root / "recommend_runtime.json"
        self.knowledge = KnowledgeLoader(repo_root=repo_root)

    @staticmethod
    def default_learning_settings() -> dict[str, Any]:
        return {
            "enabled": False,
            "mode": "OFF",
            "selector_algo": "thompson",
            "drift_algo": "adwin",
            "max_candidates": 30,
            "top_n": 5,
            "validation": {
                "walk_forward": True,
                "train_days": 252,
                "test_days": 126,
                "enforce_pbo": True,
                "enforce_dsr": True,
                "enforce_cpcv": False,
            },
            "promotion": {
                "allow_auto_apply": False,
                "allow_live": False,
            },
            "risk_profile": MEDIUM_RISK_PROFILE,
        }

    def ensure_settings_shape(self, settings: dict[str, Any]) -> dict[str, Any]:
        base = self.default_learning_settings()
        cur = settings.get("learning")
        if not isinstance(cur, dict):
            settings["learning"] = base
            return settings
        settings["learning"] = {
            **base,
            **cur,
            "validation": {**base["validation"], **(cur.get("validation") if isinstance(cur.get("validation"), dict) else {})},
            "promotion": {**base["promotion"], **(cur.get("promotion") if isinstance(cur.get("promotion"), dict) else {})},
            "risk_profile": {**base["risk_profile"], **(cur.get("risk_profile") if isinstance(cur.get("risk_profile"), dict) else {})},
        }
        settings["learning"]["promotion"]["allow_auto_apply"] = False
        settings["learning"]["promotion"]["allow_live"] = False
        return settings

    def _streams_from_runs(self, runs: list[dict[str, Any]]) -> dict[str, list[float]]:
        latest = runs[:50]
        return {
            "returns": [float((r.get("metrics") or {}).get("return_total", 0.0)) for r in latest],
            "realized_vol": [abs(float((r.get("metrics") or {}).get("sortino", 0.0))) / 10.0 for r in latest],
            "atr": [abs(float((r.get("metrics") or {}).get("max_dd", 0.0))) + 0.001 for r in latest],
            "spread_bps": [float((r.get("costs_model") or {}).get("spread_bps", 0.0)) for r in latest],
            "slippage_bps": [float((r.get("costs_model") or {}).get("slippage_bps", 0.0)) for r in latest],
            "expectancy_usd": [float((r.get("metrics") or {}).get("expectancy_usd_per_trade", (r.get("metrics") or {}).get("expectancy", 0.0))) for r in latest],
            "max_dd": [float((r.get("metrics") or {}).get("max_dd", 0.0)) for r in latest],
        }

    def _eligible_learning_pool(self, strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for strategy in strategies:
            if not isinstance(strategy, dict):
                continue
            if str(strategy.get("status") or "active") == "archived":
                continue
            if bool(strategy.get("allow_learning", True)):
                out.append(strategy)
        return out

    def compute_drift(self, *, settings: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
        cfg = self.ensure_settings_shape(dict(settings))
        drift = detect_drift(self._streams_from_runs(runs), algo=str(cfg["learning"].get("drift_algo", "adwin")))
        payload = {
            **drift,
            "updated_at": _utc_iso(),
            "research_loop_triggered": bool(drift.get("drift")),
            "live_auto_change": False,
        }
        _json_save(self.drift_path, payload)
        return payload

    def _infer_regime(self, runs: list[dict[str, Any]]) -> str:
        if not runs:
            return "range"
        recent = runs[:10]
        avg_sharpe = sum(float((r.get("metrics") or {}).get("sharpe", 0.0)) for r in recent) / max(1, len(recent))
        avg_dd = sum(abs(float((r.get("metrics") or {}).get("max_dd", 0.0))) for r in recent) / max(1, len(recent))
        avg_spread = sum(float((r.get("costs_model") or {}).get("spread_bps", 0.0)) for r in recent) / max(1, len(recent))
        if avg_spread > 12:
            return "toxic_flow"
        if avg_dd > 0.22:
            return "high_vol"
        if avg_sharpe > 1.0:
            return "trend"
        return "range"

    def _candidate_seed(self, template_id: str, idx: int) -> int:
        return int(hashlib.sha256(f"{template_id}:{idx}".encode("utf-8")).hexdigest()[:8], 16)

    def _pick_from_range(self, rng: random.Random, spec: Any) -> Any:
        if not isinstance(spec, dict):
            return spec
        vmin = spec.get("min")
        vmax = spec.get("max")
        step = spec.get("step")
        if not isinstance(vmin, (int, float)) or not isinstance(vmax, (int, float)):
            return spec
        if isinstance(step, (int, float)) and float(step) > 0:
            count = int(round((float(vmax) - float(vmin)) / float(step)))
            value = float(vmin) + float(step) * rng.randint(0, max(0, count))
            return int(round(value)) if float(step).is_integer() else round(value, 6)
        return round(rng.uniform(float(vmin), float(vmax)), 6)

    def generate_candidates(self, *, settings: dict[str, Any], runs: list[dict[str, Any]], strategies: list[dict[str, Any]]) -> list[dict[str, Any]]:
        cfg = self.ensure_settings_shape(dict(settings))
        max_candidates = int(cfg["learning"].get("max_candidates", 30) or 30)
        knowledge = self.knowledge.load()
        filters = [row for row in knowledge.filters if bool(row.get("enabled", True))]
        by_strategy = {str(s.get("id")) for s in strategies}
        out: list[dict[str, Any]] = []
        per_template = max(1, max_candidates // max(1, len(knowledge.templates)))
        for template in knowledge.templates:
            template_id = str(template.get("id"))
            ranges = knowledge.ranges.get(template_id, {})
            for idx in range(per_template):
                if len(out) >= max_candidates:
                    break
                rng = random.Random(self._candidate_seed(template_id, idx))
                params: dict[str, Any] = {}
                if isinstance(ranges, dict):
                    for key, spec in ranges.items():
                        params[str(key)] = self._pick_from_range(rng, spec)
                base_strategy_id = str(template.get("base_strategy_id") or "trend_pullback_orderflow_confirm_v1")
                if base_strategy_id not in by_strategy and strategies:
                    base_strategy_id = str(strategies[0].get("id"))
                out.append(
                    {
                        "id": f"cand_{template_id}_{idx+1:03d}",
                        "template_id": template_id,
                        "name": f"{template.get('name', template_id)} #{idx+1}",
                        "base_strategy_id": base_strategy_id,
                        "params": params,
                        "tags": list(template.get("tags") or []),
                        "filters": [str(f.get("id")) for f in filters],
                        "regime_target": str(template.get("category") or "range"),
                    }
                )
        return out[:max_candidates]

    def build_status(self, *, settings: dict[str, Any], strategies: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
        cfg = self.ensure_settings_shape(dict(settings))
        learning = cfg["learning"]
        regime = self._infer_regime(runs)
        drift = self.compute_drift(settings=cfg, runs=runs)
        learning_pool = self._eligible_learning_pool(strategies)

        selector_candidates: list[dict[str, Any]] = []
        for strategy in learning_pool:
            run = next((r for r in runs if r.get("strategy_id") == strategy.get("id")), None)
            metrics = (run or {}).get("metrics") or {}
            costs = (run or {}).get("costs_breakdown") or {}
            reward = compute_normalized_reward(
                pnl_net=float(metrics.get("return_total", 0.0)) * 10000.0,
                total_costs=float(costs.get("total_cost", 0.0)),
                drawdown_increment=abs(float(metrics.get("max_dd", 0.0))) * 100.0,
                atr=abs(float(metrics.get("max_dd", 0.0))) + 0.001,
                realized_vol=abs(float(metrics.get("sortino", 0.0))) / 10.0 + 0.001,
            )
            selector_candidates.append(
                {
                    "id": str(strategy.get("id")),
                    "tags": list(strategy.get("tags") or []),
                    "reward": reward,
                    "stats": {
                        "wins": 2 if float(metrics.get("sharpe", 0.0)) > 0 else 1,
                        "losses": 2 if float(metrics.get("sharpe", 0.0)) <= 0 else 1,
                        "pulls": 3,
                        "reward_mean": reward,
                        "regime_fit": 1.0 if regime in {str(x) for x in (strategy.get("tags") or [])} else 0.35,
                        "cost_penalty": float(((run or {}).get("costs_model") or {}).get("spread_bps", 0.0)) / 10.0,
                        "risk_penalty": abs(float(metrics.get("max_dd", 0.0))) * 4.0,
                    },
                }
            )
        selector = StrategySelector(str(learning.get("selector_algo", "thompson")))
        decision = selector.select(selector_candidates, context={"regime": regime})

        snapshot = self.knowledge.load()
        payload = {
            "enabled": bool(learning.get("enabled", False)),
            "mode": str(learning.get("mode", "OFF")).upper(),
            "selector_algo": str(learning.get("selector_algo", "thompson")),
            "drift_algo": str(learning.get("drift_algo", "adwin")),
            "regime": regime,
            "selector": decision,
            "drift": drift,
            "option_b": {"allow_auto_apply": False, "allow_live": False},
            "learning_pool": {
                "count": len(learning_pool),
                "strategy_ids": [str(s.get("id")) for s in learning_pool],
                "empty_block_recommend": len(learning_pool) == 0 and bool(learning.get("enabled", False)),
            },
            "warnings": (
                ["Pool de aprendizaje vacio: marcar estrategias con 'Incluida en Aprendizaje' para recomendar."]
                if len(learning_pool) == 0 and bool(learning.get("enabled", False))
                else []
            ),
            "risk_profile": learning.get("risk_profile") or MEDIUM_RISK_PROFILE,
            "knowledge": {
                "loaded": True,
                "repo_root": str(snapshot.repo_root),
                "template_count": len(snapshot.templates),
                "filter_count": len(snapshot.filters),
            },
            "updated_at": _utc_iso(),
        }
        _json_save(self.status_path, payload)
        return payload

    def load_recommendations(self) -> list[dict[str, Any]]:
        rows = _json_load(self.recommendations_path, [])
        return rows if isinstance(rows, list) else []

    def get_recommendation(self, candidate_id: str) -> dict[str, Any] | None:
        for row in self.load_recommendations():
            if row.get("id") == candidate_id:
                return row
        return None

    def load_all_recommendations(self) -> list[dict[str, Any]]:
        research = [dict(row, recommendation_source="research") for row in self.load_recommendations()]
        runtime = [dict(row, recommendation_source="runtime") for row in self.load_runtime_recommendations()]
        merged: dict[str, dict[str, Any]] = {}
        for row in research:
            rid = str(row.get("id") or "")
            if rid:
                merged[rid] = row
        for row in runtime:
            rid = str(row.get("id") or "")
            if rid:
                merged[rid] = row
        def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
            return (str(item.get("created_at") or item.get("reviewed_at") or ""), str(item.get("id") or ""))
        return sorted(merged.values(), key=_sort_key, reverse=True)

    def get_any_recommendation(self, recommendation_id: str) -> dict[str, Any] | None:
        for row in self.load_all_recommendations():
            if str(row.get("id")) == recommendation_id:
                return row
        return None

    def run_research(
        self,
        *,
        settings: dict[str, Any],
        strategies: list[dict[str, Any]],
        runs: list[dict[str, Any]],
        backtest_eval: BacktestEvalFn,
    ) -> dict[str, Any]:
        cfg = self.ensure_settings_shape(dict(settings))
        learning = cfg["learning"]
        if not bool(learning.get("enabled")) or str(learning.get("mode", "OFF")).upper() != "RESEARCH":
            raise ValueError("Learning disabled or mode != RESEARCH")
        strategies = self._eligible_learning_pool(strategies)
        if not strategies:
            raise ValueError("Pool de aprendizaje vacio (allow_learning=false en todas las estrategias)")

        drift = self.compute_drift(settings=cfg, runs=runs)
        regime = self._infer_regime(runs)
        candidates = self.generate_candidates(settings=cfg, runs=runs, strategies=strategies)
        evaluated: list[dict[str, Any]] = []
        returns_map: dict[str, list[float]] = {}

        for candidate in candidates:
            result = backtest_eval(candidate)
            metrics = result.get("metrics", {}) if isinstance(result.get("metrics"), dict) else {}
            costs = result.get("costs_breakdown", {}) if isinstance(result.get("costs_breakdown"), dict) else {}
            eq = result.get("equity_curve", []) if isinstance(result.get("equity_curve"), list) else []
            eq_vals = [float(p.get("equity", 0.0)) for p in eq if isinstance(p, dict) and "equity" in p]
            ret_series: list[float] = []
            for i in range(1, len(eq_vals)):
                if eq_vals[i - 1]:
                    ret_series.append((eq_vals[i] - eq_vals[i - 1]) / eq_vals[i - 1])
            returns_map[candidate["id"]] = ret_series

            gross = float(costs.get("gross_pnl_total", 0.0))
            total_cost = float(costs.get("total_cost", 0.0))
            reward = compute_normalized_reward(
                pnl_net=gross - total_cost,
                total_costs=total_cost,
                drawdown_increment=abs(float(metrics.get("max_dd", 0.0))) * 100.0,
                atr=abs(float(metrics.get("expectancy_usd_per_trade", metrics.get("expectancy", 0.0)))) / 100.0 + 0.001,
                realized_vol=abs(float(metrics.get("sortino", 0.0))) / 10.0 + 0.001,
            )
            regime_fit = 1.0 if str(candidate.get("regime_target")) == regime else 0.35
            cost_penalty = float(((result.get("costs_model") or {}).get("spread_bps", 0.0))) / 10.0
            risk_penalty = abs(float(metrics.get("max_dd", 0.0))) * (1.3 if regime_fit < 1.0 else 1.0)

            evaluated.append(
                {
                    **candidate,
                    "backtest": {
                        "data_source": result.get("data_source", "unknown"),
                        "dataset_hash": result.get("dataset_hash", ""),
                        "metrics": metrics,
                        "costs_breakdown": costs,
                    },
                    "reward": round(reward, 6),
                    "stats": {
                        "wins": 2 if float(metrics.get("sharpe", 0.0)) > 0 else 1,
                        "losses": 2 if float(metrics.get("sharpe", 0.0)) <= 0 else 1,
                        "pulls": 3,
                        "reward_mean": reward,
                        "regime_fit": regime_fit,
                        "cost_penalty": round(cost_penalty, 6),
                        "risk_penalty": round(risk_penalty, 6),
                    },
                }
            )

        pbo_payload = pbo_cscv(returns_map)
        gates = self.knowledge.get_gates()
        pbo_max = float(((gates.get("pbo") or {}).get("max_allowed")) or 0.55)
        dsr_min = float(((gates.get("dsr") or {}).get("min_allowed")) or 0.10)
        enforce_pbo = bool((learning.get("validation") or {}).get("enforce_pbo", True))
        enforce_dsr = bool((learning.get("validation") or {}).get("enforce_dsr", True))

        selector = StrategySelector(str(learning.get("selector_algo", "thompson")))
        selector_decision = selector.select(evaluated, context={"regime": regime})

        for row in evaluated:
            dsr_payload = deflated_sharpe_ratio(returns_map.get(str(row["id"]), []), trials=max(1, len(evaluated)))
            reasons: list[str] = []
            accepted = True
            pbo_value = pbo_payload.get("pbo")
            dsr_value = dsr_payload.get("dsr")
            if enforce_pbo and isinstance(pbo_value, (int, float)) and float(pbo_value) > pbo_max:
                accepted = False
                reasons.append(f"PBO alto ({float(pbo_value):.3f} > {pbo_max:.3f})")
            if enforce_dsr and isinstance(dsr_value, (int, float)) and float(dsr_value) < dsr_min:
                accepted = False
                reasons.append(f"DSR bajo ({float(dsr_value):.3f} < {dsr_min:.3f})")
            row["validation"] = {
                "walk_forward": bool((learning.get("validation") or {}).get("walk_forward", True)),
                "pbo": pbo_value,
                "dsr": dsr_value,
                "cpcv": {"implemented": False, "enforce": False, "note": "hook_only"},
                "purged_cv": {"implemented": False, "enforce": False, "note": "hook_only"},
            }
            row["status"] = "APPROVED" if accepted else "REJECTED"
            row["status_reason"] = "; ".join(reasons) if reasons else "Validacion OK"
            row["selector_context"] = {"regime": regime, "drift": bool(drift.get("drift"))}
            row["option_b"] = {"applied_live": False, "requires_admin_adoption": True}

        evaluated.sort(key=lambda r: (r.get("status") == "APPROVED", float(r.get("reward", 0.0))), reverse=True)
        top_n = max(1, int(learning.get("top_n", 5) or 5))
        top = evaluated[:top_n]
        for idx, row in enumerate(top, start=1):
            row["rank"] = idx
            row["explanation"] = self.knowledge.explain_candidate(str(row["id"]))
            row["adoptable_modes"] = ["paper", "testnet"]
            row["generated_params_yaml"] = yaml.safe_dump(row.get("params") or {}, sort_keys=False)
            row["version"] = f"0.1.{idx}"
            row["created_at"] = _utc_iso()

        _json_save(self.recommendations_path, top)
        status_payload = {
            "ok": True,
            "generated": len(candidates),
            "evaluated": len(evaluated),
            "saved_top_n": len(top),
            "drift": drift,
            "selector": selector_decision,
            "option_b": {"allow_auto_apply": False, "allow_live": False},
            "updated_at": _utc_iso(),
        }
        _json_save(self.status_path, {"last_run": status_payload, "mode": str(learning.get("mode", "OFF")).upper()})
        return status_payload

    def load_runtime_recommendations(self) -> list[dict[str, Any]]:
        rows = _json_load(self.recommend_runtime_path, [])
        return rows if isinstance(rows, list) else []

    def _save_runtime_recommendations(self, rows: list[dict[str, Any]]) -> None:
        _json_save(self.recommend_runtime_path, rows[-200:])

    def recommend_from_pool(
        self,
        *,
        settings: dict[str, Any],
        strategies: list[dict[str, Any]],
        runs: list[dict[str, Any]],
        mode: str = "paper",
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> dict[str, Any]:
        cfg = self.ensure_settings_shape(dict(settings))
        learning = cfg["learning"]
        if not bool(learning.get("enabled")):
            raise ValueError("Aprendizaje deshabilitado")
        pool = self._eligible_learning_pool(strategies)
        if not pool:
            raise ValueError("Pool de aprendizaje vacio (tildá 'Incluida en Aprendizaje')")
        regime = self._infer_regime(runs)
        selector_candidates: list[dict[str, Any]] = []
        ranking: list[dict[str, Any]] = []
        for strategy in pool:
            strategy_id = str(strategy.get("id"))
            strat_runs = [r for r in runs if str(r.get("strategy_id")) == strategy_id and str(r.get("mode") or "backtest").lower() in {"backtest", mode.lower()}]
            latest = strat_runs[0] if strat_runs else None
            metrics = (latest or {}).get("metrics") or {}
            costs = (latest or {}).get("costs_breakdown") or {}
            reward = compute_normalized_reward(
                pnl_net=float(costs.get("net_pnl_total", costs.get("net_pnl", 0.0)) or 0.0),
                total_costs=float(costs.get("total_cost", 0.0) or 0.0),
                drawdown_increment=abs(float(metrics.get("max_dd", 0.0) or 0.0)) * 100.0,
                atr=abs(float(metrics.get("avg_trade", metrics.get("expectancy", 0.0)) or 0.0)) / 100.0 + 0.001,
                realized_vol=abs(float(metrics.get("sortino", 0.0) or 0.0)) / 10.0 + 0.001,
            )
            regime_fit = 1.0 if regime in {str(x) for x in (strategy.get("tags") or [])} else 0.4
            candidate = {
                "id": strategy_id,
                "reward": reward,
                "tags": list(strategy.get("tags") or []),
                "stats": {
                    "wins": max(1, int(round(float(metrics.get("winrate", 0.5)) * 10))),
                    "losses": max(1, int(round((1.0 - float(metrics.get("winrate", 0.5))) * 10))),
                    "pulls": max(2, int(metrics.get("trade_count", metrics.get("roundtrips", 2)) or 2)),
                    "reward_mean": reward,
                    "regime_fit": regime_fit,
                    "cost_penalty": float(((latest or {}).get("costs_model") or {}).get("spread_bps", 0.0)) / 10.0,
                    "risk_penalty": abs(float(metrics.get("max_dd", 0.0) or 0.0)) * 4.0,
                },
            }
            selector_candidates.append(candidate)
            ranking.append(
                {
                    "strategy_id": strategy_id,
                    "name": strategy.get("name", strategy_id),
                    "reward": round(float(reward), 6),
                    "winrate": float(metrics.get("winrate", 0.0) or 0.0),
                    "trade_count": int(metrics.get("trade_count", metrics.get("roundtrips", 0)) or 0),
                    "expectancy": float(metrics.get("expectancy_usd_per_trade", metrics.get("expectancy", 0.0)) or 0.0),
                    "expectancy_unit": str(metrics.get("expectancy_unit") or "usd_por_trade"),
                    "max_dd": float(metrics.get("max_dd", 0.0) or 0.0),
                    "sharpe": float(metrics.get("sharpe", 0.0) or 0.0),
                    "sortino": float(metrics.get("sortino", 0.0) or 0.0),
                    "calmar": float(metrics.get("calmar", 0.0) or 0.0),
                }
            )
        selector = StrategySelector(str(learning.get("selector_algo", "thompson")))
        decision = selector.select(selector_candidates, context={"regime": regime})
        ranking.sort(key=lambda r: r["reward"], reverse=True)
        top = ranking[: max(1, int(learning.get("top_n", 5) or 5))]
        if decision.get("active_strategy_id"):
            total_positive = sum(max(0.0, float(r["reward"])) for r in top) or 1.0
            weights = {
                r["strategy_id"]: round(max(0.0, float(r["reward"])) / total_positive, 4)
                for r in top
            }
        else:
            weights = {}
        recommendation = {
            "id": f"rec_{hashlib.sha256(f'{mode}:{regime}:{_utc_iso()}'.encode('utf-8')).hexdigest()[:10]}",
            "status": "PENDING_REVIEW",
            "mode": str(mode).lower(),
            "from_ts": from_ts,
            "to_ts": to_ts,
            "regime": regime,
            "selector_algo": str(learning.get("selector_algo", "thompson")),
            "active_strategy_id": decision.get("active_strategy_id"),
            "weights_sugeridos": weights,
            "ranking": top,
            "option_b": {"allow_auto_apply": False, "allow_live": False, "requires_human_approval": True},
            "created_at": _utc_iso(),
        }
        rows = self.load_runtime_recommendations()
        rows.append(recommendation)
        self._save_runtime_recommendations(rows)
        return recommendation

    def update_runtime_recommendation_status(self, recommendation_id: str, *, status: str, note: str | None = None) -> dict[str, Any] | None:
        rows = self.load_runtime_recommendations()
        found: dict[str, Any] | None = None
        for row in rows:
            if str(row.get("id")) == recommendation_id:
                row["status"] = status
                row["reviewed_at"] = _utc_iso()
                if note:
                    row["note"] = note
                found = row
                break
        if found is not None:
            self._save_runtime_recommendations(rows)
        return found

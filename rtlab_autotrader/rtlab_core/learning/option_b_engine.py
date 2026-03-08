from __future__ import annotations

import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from rtlab_core.learning.brain import deflated_sharpe_ratio
from rtlab_core.strategy_packs.registry_db import RegistryDB

VALID_SOURCES = ("backtest", "shadow", "paper", "testnet")
VALID_REGIMES = ("trend", "range", "high_vol", "toxic", "unknown")


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return float(default)
        return out
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(pstdev(values))


def _zscore_map(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    rows = list(values.items())
    raw = [float(v) for _, v in rows]
    mu = mean(raw)
    sigma = _std(raw)
    if sigma <= 1e-12:
        return {key: 0.0 for key, _ in rows}
    return {key: (float(val) - mu) / sigma for key, val in rows}


class OptionBLearningEngine:
    def __init__(self, registry: RegistryDB) -> None:
        self.registry = registry

    def _eligible_strategies(self, strategies: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in strategies:
            if not isinstance(row, dict):
                continue
            strategy_id = str(row.get("id") or "").strip()
            if not strategy_id:
                continue
            if str(row.get("status") or "active") == "archived":
                continue
            if not bool(row.get("allow_learning", True)):
                continue
            out[strategy_id] = row
        return out

    @staticmethod
    def _primary_strategy_id(strategies: list[dict[str, Any]]) -> str | None:
        primary = next((row for row in strategies if isinstance(row, dict) and bool(row.get("is_primary"))), None)
        if primary:
            return str(primary.get("id") or "") or None
        enabled = next((row for row in strategies if isinstance(row, dict) and bool(row.get("enabled_for_trading", row.get("enabled", False)))), None)
        if enabled:
            return str(enabled.get("id") or "") or None
        return None

    def _load_rows(self, strategies: list[dict[str, Any]]) -> dict[str, Any]:
        eligible = self._eligible_strategies(strategies)
        strategy_ids = list(eligible)
        episodes = self.registry.list_experience_episodes(strategy_ids=strategy_ids, sources=list(VALID_SOURCES))
        episode_ids = [str(row.get("id") or "") for row in episodes if str(row.get("id") or "")]
        events = self.registry.list_experience_events(episode_ids=episode_ids) if episode_ids else []
        regime_kpis = [row for row in self.registry.list_regime_kpis() if str(row.get("strategy_id") or "") in eligible]
        guidance_rows = self.registry.list_strategy_policy_guidance()
        guidance = {str(row.get("strategy_id") or ""): row for row in guidance_rows}
        return {
            "eligible": eligible,
            "episodes": episodes,
            "events": events,
            "regime_kpis": regime_kpis,
            "guidance": guidance,
            "primary_strategy_id": self._primary_strategy_id(strategies),
        }

    @staticmethod
    def _weighted_mean(values: list[float], weights: list[float]) -> float:
        if not values or not weights or len(values) != len(weights):
            return 0.0
        total_weight = sum(max(0.0, float(weight)) for weight in weights)
        if total_weight <= 1e-12:
            return 0.0
        return sum(float(value) * max(0.0, float(weight)) for value, weight in zip(values, weights)) / total_weight

    @staticmethod
    def _weighted_profit_factor(values: list[float], weights: list[float]) -> float:
        if not values or not weights or len(values) != len(weights):
            return 0.0
        gross_profit = sum(max(0.0, float(value) * max(0.0, float(weight))) for value, weight in zip(values, weights))
        gross_loss = abs(sum(min(0.0, float(value) * max(0.0, float(weight))) for value, weight in zip(values, weights)))
        if gross_loss <= 1e-12:
            return float(gross_profit > 0) * max(gross_profit, 0.0)
        return gross_profit / gross_loss

    @staticmethod
    def _weighted_max_drawdown(values: list[float], weights: list[float]) -> float:
        if not values or not weights or len(values) != len(weights):
            return 0.0
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for value, weight in zip(values, weights):
            cumulative += float(value) * max(0.0, float(weight))
            peak = max(peak, cumulative)
            max_dd = min(max_dd, cumulative - peak)
        return abs(max_dd)

    @staticmethod
    def _weighted_cost_ratio(gross_values: list[float], costs: list[float], weights: list[float]) -> float:
        if not gross_values or not costs or not weights:
            return 0.0
        weighted_costs = sum(float(cost) * max(0.0, float(weight)) for cost, weight in zip(costs, weights))
        weighted_gross_profit = sum(max(0.0, float(value) * max(0.0, float(weight))) for value, weight in zip(gross_values, weights))
        if weighted_gross_profit <= 1e-12:
            return 0.0 if weighted_costs <= 1e-12 else weighted_costs
        return weighted_costs / weighted_gross_profit

    @staticmethod
    def _dominant_feature_set(feature_sets: list[str]) -> str | None:
        clean = [str(feature_set or "").strip() for feature_set in feature_sets if str(feature_set or "").strip()]
        if not clean:
            return None
        return Counter(clean).most_common(1)[0][0]

    @staticmethod
    def _episode_trade_count(summary: dict[str, Any]) -> int:
        if not isinstance(summary, dict):
            return 0
        metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
        return _safe_int(summary.get("trade_count") or metrics.get("trade_count") or metrics.get("roundtrips"), 0)

    @staticmethod
    def _source_summary_key(source: str) -> str:
        src = str(source or "backtest").strip().lower()
        return src if src in VALID_SOURCES else "backtest"

    def _build_contexts(self, *, strategies: list[dict[str, Any]]) -> dict[str, Any]:
        rows = self._load_rows(strategies)
        eligible = rows["eligible"]
        episodes = rows["episodes"]
        events = rows["events"]
        regime_kpis = rows["regime_kpis"]
        guidance = rows["guidance"]

        episode_by_id = {str(row.get("id") or ""): row for row in episodes}
        totals: dict[tuple[str, str, str], dict[str, Any]] = {}
        regime_events: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
        primary_feature_sets: dict[tuple[str, str], list[str]] = defaultdict(list)
        for episode in episodes:
            strategy_id = str(episode.get("strategy_id") or "")
            asset = str(episode.get("asset") or "")
            timeframe = str(episode.get("timeframe") or "")
            key = (strategy_id, asset, timeframe)
            summary = episode.get("summary") if isinstance(episode.get("summary"), dict) else {}
            bucket = totals.setdefault(
                key,
                {
                    "trade_count": 0,
                    "days": set(),
                    "feature_sets": set(),
                    "sources": defaultdict(lambda: {"episodes": 0, "trades": 0, "weight_sum": 0.0}),
                    "validation_qualities": set(),
                    "episode_net_pnls": [],
                },
            )
            bucket["trade_count"] += self._episode_trade_count(summary)
            bucket["feature_sets"].add(str(episode.get("feature_set") or "unknown"))
            bucket["validation_qualities"].add(str(episode.get("validation_quality") or "unknown"))
            src = self._source_summary_key(str(episode.get("source") or "backtest"))
            src_row = bucket["sources"][src]
            src_row["episodes"] += 1
            src_row["trades"] += self._episode_trade_count(summary)
            src_row["weight_sum"] += _safe_float(episode.get("source_weight"), 0.0)
            metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
            costs = summary.get("costs_breakdown") if isinstance(summary.get("costs_breakdown"), dict) else {}
            net_episode = _safe_float(costs.get("net_pnl_total"), _safe_float(metrics.get("expectancy")) * max(1, self._episode_trade_count(summary)))
            bucket["episode_net_pnls"].append(net_episode)
            for value in (episode.get("start_ts"), episode.get("end_ts"), episode.get("created_at")):
                text = str(value or "")
                if text:
                    bucket["days"].add(text[:10])
            if strategy_id == rows["primary_strategy_id"]:
                primary_feature_sets[(asset, timeframe)].append(str(episode.get("feature_set") or "unknown"))

        for event in events:
            if str(event.get("action") or "") != "exit":
                continue
            episode = episode_by_id.get(str(event.get("episode_id") or ""))
            if not episode:
                continue
            strategy_id = str(episode.get("strategy_id") or "")
            asset = str(episode.get("asset") or "")
            timeframe = str(episode.get("timeframe") or "")
            regime = str(event.get("regime_label") or "unknown")
            if regime not in VALID_REGIMES:
                regime = "unknown"
            regime_events[(strategy_id, asset, timeframe, regime)].append({**event, "source_weight": _safe_float(episode.get("source_weight"), 0.0)})
            if regime != "unknown":
                regime_events[(strategy_id, asset, timeframe, "unknown")].append({**event, "source_weight": _safe_float(episode.get("source_weight"), 0.0)})

        contexts: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in regime_kpis:
            strategy_id = str(row.get("strategy_id") or "")
            if strategy_id not in eligible:
                continue
            asset = str(row.get("asset") or "")
            timeframe = str(row.get("timeframe") or "")
            raw_regime = str(row.get("regime_label") or "unknown")
            regime = raw_regime if raw_regime in VALID_REGIMES else "unknown"
            total_key = (strategy_id, asset, timeframe)
            total_info = totals.get(total_key, {"trade_count": 0, "days": set(), "feature_sets": set(), "sources": {}, "validation_qualities": set(), "episode_net_pnls": []})
            exit_rows = regime_events.get((strategy_id, asset, timeframe, regime), [])
            if _safe_int(row.get("n_trades"), 0) < 30:
                regime = "unknown"
                exit_rows = regime_events.get((strategy_id, asset, timeframe, "unknown"), exit_rows)
            costs_per_trade = []
            stress_pnls = []
            for event in exit_rows:
                gross = _safe_float(event.get("realized_pnl_gross"))
                fee = _safe_float(event.get("fee"))
                spread_cost = _safe_float(event.get("spread_cost"))
                slippage_cost = _safe_float(event.get("slippage_cost"))
                funding_cost = _safe_float(event.get("funding_cost"))
                total_cost = fee + spread_cost + slippage_cost + funding_cost
                costs_per_trade.append(total_cost)
                stress_pnls.append(gross - (1.5 * total_cost))
            feature_sets = sorted(str(x) for x in total_info.get("feature_sets", set()) if str(x)) or ["unknown"]
            mixed_feature_set = len(set(feature_sets)) > 1
            dominant_feature_set = self._dominant_feature_set(feature_sets) or "unknown"
            baseline_feature_set = self._dominant_feature_set(primary_feature_sets.get((asset, timeframe), []))
            feature_set_matches_baseline = baseline_feature_set is None or dominant_feature_set == baseline_feature_set
            source_summary: dict[str, Any] = {}
            total_weighted_trades = 0.0
            total_trade_weight = 0.0
            for source_name, source_row in (total_info.get("sources") or {}).items():
                trades = _safe_int(source_row.get("trades"), 0)
                episodes_n = _safe_int(source_row.get("episodes"), 0)
                avg_weight = 0.0 if episodes_n <= 0 else _safe_float(source_row.get("weight_sum"), 0.0) / episodes_n
                source_summary[source_name] = {
                    "episodes": episodes_n,
                    "trades": trades,
                    "avg_weight": round(avg_weight, 4),
                }
                total_weighted_trades += trades * avg_weight
                total_trade_weight += trades
            source_quality_factor = 0.0 if total_trade_weight <= 0 else max(0.0, min(1.0, total_weighted_trades / total_trade_weight))
            episode_net_pnls = [float(x) for x in (total_info.get("episode_net_pnls") or []) if isinstance(x, (int, float))]
            if len(episode_net_pnls) >= 3:
                chunk = max(1, len(episode_net_pnls) // min(4, len(episode_net_pnls)))
                windows = [episode_net_pnls[idx : idx + chunk] for idx in range(0, len(episode_net_pnls), chunk)]
                window_means = [mean(window) for window in windows if window]
                if len(window_means) >= 2:
                    stability_factor = max(0.0, min(1.0, 1.0 - (_std(window_means) / max(abs(mean(window_means)), 1e-9))))
                else:
                    stability_factor = 0.5
            else:
                stability_factor = 0.35 if episode_net_pnls else 0.0
            validation_factor = 1.0
            needs_validation = False
            validation_qualities = {str(x) for x in (total_info.get("validation_qualities") or set()) if str(x)}
            if any("synthetic" in quality for quality in validation_qualities):
                validation_factor *= 0.6
                needs_validation = True
            if row.get("pbo") is None:
                validation_factor *= 0.8
                needs_validation = True
            if row.get("dsr") is None or row.get("psr") is None:
                validation_factor *= 0.9
                needs_validation = True
            if mixed_feature_set:
                validation_factor *= 0.5
                needs_validation = True
            weights = [max(0.0, _safe_float(event.get("source_weight"), 0.0)) for event in exit_rows]
            net_pnls = [_safe_float(event.get("realized_pnl_net"), 0.0) for event in exit_rows]
            gross_pnls = [_safe_float(event.get("realized_pnl_gross"), 0.0) for event in exit_rows]
            total_costs = [
                _safe_float(event.get("fee"))
                + _safe_float(event.get("spread_cost"))
                + _safe_float(event.get("slippage_cost"))
                + _safe_float(event.get("funding_cost"))
                for event in exit_rows
            ]
            weighted_expectancy_net = self._weighted_mean(net_pnls, weights) if exit_rows else _safe_float(row.get("expectancy_net"), 0.0)
            weighted_expectancy_gross = self._weighted_mean(gross_pnls, weights) if exit_rows else _safe_float(row.get("expectancy_gross"), 0.0)
            weighted_profit_factor = self._weighted_profit_factor(net_pnls, weights) if exit_rows else _safe_float(row.get("profit_factor"), 0.0)
            weighted_net_series = [value * max(0.0, weight) for value, weight in zip(net_pnls, weights)] if exit_rows else []
            weighted_sharpe_payload = deflated_sharpe_ratio(weighted_net_series, trials=max(1, len(weighted_net_series))) if weighted_net_series else {"sharpe": _safe_float(row.get("sharpe"), 0.0), "dsr": row.get("dsr")}
            weighted_sortino = _safe_float(row.get("sortino"), 0.0)
            if len(weighted_net_series) >= 2:
                downside = [min(0.0, value) for value in weighted_net_series]
                sigma = _std(downside)
                if sigma > 1e-12:
                    weighted_sortino = (mean(weighted_net_series) / sigma) * math.sqrt(len(weighted_net_series))
            weighted_max_dd = self._weighted_max_drawdown(net_pnls, weights) if exit_rows else abs(_safe_float(row.get("max_dd"), 0.0))
            weighted_hit_rate = (
                sum(max(0.0, weight) for pnl, weight in zip(net_pnls, weights) if pnl > 0) / max(1e-12, sum(max(0.0, weight) for weight in weights))
                if exit_rows
                else _safe_float(row.get("hit_rate"), 0.0)
            )
            weighted_cost_ratio = self._weighted_cost_ratio(gross_pnls, total_costs, weights) if exit_rows else _safe_float(row.get("cost_ratio"), 0.0)
            cost_stress_expectancy = self._weighted_mean(stress_pnls, weights) if exit_rows and weights else _safe_float(row.get("expectancy_net"), 0.0)
            item = {
                "strategy_id": strategy_id,
                "strategy_name": str((eligible.get(strategy_id) or {}).get("name") or strategy_id),
                "asset": asset,
                "timeframe": timeframe,
                "regime_label": regime,
                "feature_sets": feature_sets,
                "dominant_feature_set": dominant_feature_set,
                "baseline_feature_set": baseline_feature_set,
                "feature_set_matches_baseline": feature_set_matches_baseline,
                "mixed_feature_set": mixed_feature_set,
                "n_trades_total": _safe_int(total_info.get("trade_count"), 0),
                "n_days_total": len(total_info.get("days") or set()),
                "n_trades_regime": max(len(exit_rows), _safe_int(row.get("n_trades"), 0)),
                "n_days_regime": _safe_int(row.get("n_days"), 0),
                "expectancy_net": weighted_expectancy_net,
                "expectancy_gross": weighted_expectancy_gross,
                "profit_factor": weighted_profit_factor,
                "sharpe": _safe_float(weighted_sharpe_payload.get("sharpe"), _safe_float(row.get("sharpe"), 0.0)),
                "sortino": weighted_sortino,
                "max_dd": weighted_max_dd,
                "hit_rate": weighted_hit_rate,
                "turnover": _safe_float(row.get("turnover"), 0.0),
                "avg_trade_duration": _safe_float(row.get("avg_trade_duration"), 0.0),
                "cost_ratio": weighted_cost_ratio,
                "pbo": row.get("pbo"),
                "dsr": weighted_sharpe_payload.get("dsr", row.get("dsr")),
                "psr": row.get("psr"),
                "cost_stress_expectancy": cost_stress_expectancy,
                "source_quality_factor": source_quality_factor,
                "validation_factor": max(0.0, min(1.0, validation_factor)),
                "stability_factor": max(0.0, min(1.0, stability_factor)),
                "needs_validation": needs_validation,
                "source_summary": source_summary,
                "guidance": guidance.get(strategy_id) or {},
            }
            contexts[(asset, timeframe, regime)].append(item)
        return {
            "contexts": contexts,
            "eligible": eligible,
            "primary_strategy_id": rows["primary_strategy_id"],
            "episodes": episodes,
            "events": events,
        }

    def summarize(self, *, strategies: list[dict[str, Any]]) -> dict[str, Any]:
        payload = self._build_contexts(strategies=strategies)
        proposals = self.registry.list_learning_proposals()
        return {
            "generated_at": _utc_iso(),
            "eligible_strategies": len(payload["eligible"]),
            "experience_episodes": len(payload["episodes"]),
            "experience_events": len(payload["events"]),
            "contexts": len(payload["contexts"]),
            "proposals_pending": sum(1 for row in proposals if str(row.get("status") or "") == "pending"),
            "proposals_needs_validation": sum(1 for row in proposals if str(row.get("status") or "") == "needs_validation"),
            "proposals_approved": sum(1 for row in proposals if str(row.get("status") or "") == "approved"),
            "proposals_rejected": sum(1 for row in proposals if str(row.get("status") or "") == "rejected"),
            "primary_strategy_id": payload["primary_strategy_id"],
        }

    def recalculate(self, *, strategies: list[dict[str, Any]], pbo_max: float, dsr_min: float) -> dict[str, Any]:
        payload = self._build_contexts(strategies=strategies)
        contexts = payload["contexts"]
        primary_strategy_id = payload["primary_strategy_id"]
        generated: list[dict[str, Any]] = []
        rankings: list[dict[str, Any]] = []
        for (asset, timeframe, regime), rows in contexts.items():
            if not rows:
                continue
            expectancy_z = _zscore_map({row["strategy_id"]: row["expectancy_net"] for row in rows})
            pf_z = _zscore_map({row["strategy_id"]: row["profit_factor"] for row in rows})
            sharpe_z = _zscore_map({row["strategy_id"]: row["sharpe"] for row in rows})
            psr_z = _zscore_map({row["strategy_id"]: _safe_float(row.get("psr"), 0.0) for row in rows})
            dsr_z = _zscore_map({row["strategy_id"]: _safe_float(row.get("dsr"), 0.0) for row in rows})
            max_dd_z = _zscore_map({row["strategy_id"]: abs(_safe_float(row.get("max_dd"), 0.0)) for row in rows})
            turnover_cost_z = _zscore_map({row["strategy_id"]: _safe_float(row.get("cost_ratio"), 0.0) + (_safe_float(row.get("turnover"), 0.0) * 0.01) for row in rows})
            scored: list[dict[str, Any]] = []
            for row in rows:
                strategy_id = str(row.get("strategy_id") or "")
                raw_score = (
                    0.45 * expectancy_z.get(strategy_id, 0.0)
                    + 0.20 * pf_z.get(strategy_id, 0.0)
                    + 0.10 * sharpe_z.get(strategy_id, 0.0)
                    + 0.10 * psr_z.get(strategy_id, 0.0)
                    + 0.05 * dsr_z.get(strategy_id, 0.0)
                    - 0.10 * max_dd_z.get(strategy_id, 0.0)
                    - 0.05 * turnover_cost_z.get(strategy_id, 0.0)
                )
                source_quality_factor = max(0.0, min(1.0, _safe_float(row.get("source_quality_factor"), 0.0)))
                validation_factor = max(0.0, min(1.0, _safe_float(row.get("validation_factor"), 0.0)))
                stability_factor = max(0.0, min(1.0, _safe_float(row.get("stability_factor"), 0.0)))
                pbo_value = row.get("pbo")
                pbo_factor = 0.75 if pbo_value is None else max(0.0, min(1.0, 1.0 - _safe_float(pbo_value, 1.0)))
                trade_factor = min(1.0, math.log(1.0 + max(0, _safe_int(row.get("n_trades_regime"), 0))) / math.log(201.0))
                confidence = trade_factor * stability_factor * validation_factor * source_quality_factor * pbo_factor
                needs_validation = bool(row.get("needs_validation"))
                required_gates = ["baseline_compare", "same_feature_set", "pbo_ok", "dsr_ok", "drift_ok"]
                reasons: list[str] = []
                if _safe_int(row.get("n_trades_total"), 0) < 120:
                    reasons.append("n_trades_total<120")
                if _safe_int(row.get("n_days_total"), 0) < 90:
                    reasons.append("n_days_total<90")
                if _safe_int(row.get("n_trades_regime"), 0) < 30:
                    reasons.append("n_trades_regime<30")
                if _safe_float(row.get("expectancy_net"), 0.0) <= 0:
                    reasons.append("expectancy_net<=0")
                if _safe_float(row.get("cost_stress_expectancy"), 0.0) < 0:
                    reasons.append("cost_stress_1_5x<0")
                if pbo_value is not None and _safe_float(pbo_value, 1.0) > pbo_max:
                    reasons.append(f"pbo>{pbo_max:.2f}")
                if row.get("dsr") is not None and _safe_float(row.get("dsr"), 0.0) < dsr_min:
                    reasons.append(f"dsr<{dsr_min:.2f}")
                if bool(row.get("mixed_feature_set")):
                    reasons.append("same_feature_set_fail")
                if not bool(row.get("feature_set_matches_baseline", True)):
                    reasons.append("feature_set_vs_baseline_fail")
                if needs_validation:
                    reasons.append("needs_validation")
                # Hard-block gates: cost stress failure and negative expectancy are non-negotiable.
                # A proposal with these reasons must NOT become eligible even for "needs_validation" review.
                _HARD_BLOCK = {"cost_stress_1_5x<0", "expectancy_net<=0"}
                hard_blocked = any(r in _HARD_BLOCK for r in reasons)
                eligible = (not hard_blocked) and len([r for r in reasons if r != "needs_validation"]) == 0
                status = "pending" if eligible and not needs_validation else "needs_validation"
                rationale = (
                    f"Régimen {regime} | activo {asset or '-'} | timeframe {timeframe or '-'} | "
                    f"score={raw_score:.4f} | confidence={confidence:.4f} | expectancy_neta={_safe_float(row.get('expectancy_net')):.4f} | "
                    f"profit_factor={_safe_float(row.get('profit_factor')):.4f} | sharpe={_safe_float(row.get('sharpe')):.4f} | "
                    f"max_dd={_safe_float(row.get('max_dd')):.4f} | cost_ratio={_safe_float(row.get('cost_ratio')):.4f} | "
                    f"feature_set={','.join(row.get('feature_sets') or ['unknown'])}."
                )
                if row.get("baseline_feature_set"):
                    rationale += f" Baseline feature_set={row.get('baseline_feature_set')}."
                if reasons:
                    rationale += f" Bloqueos/pendientes: {', '.join(reasons)}."
                score = {
                    "score_raw": round(raw_score, 6),
                    "score_weighted": round(raw_score * source_quality_factor, 6),
                    "expectancy_net_z": round(expectancy_z.get(strategy_id, 0.0), 6),
                    "profit_factor_z": round(pf_z.get(strategy_id, 0.0), 6),
                    "sharpe_z": round(sharpe_z.get(strategy_id, 0.0), 6),
                    "psr_z": round(psr_z.get(strategy_id, 0.0), 6),
                    "dsr_z": round(dsr_z.get(strategy_id, 0.0), 6),
                    "max_dd_z": round(max_dd_z.get(strategy_id, 0.0), 6),
                    "turnover_cost_z": round(turnover_cost_z.get(strategy_id, 0.0), 6),
                    "source_quality_factor": round(source_quality_factor, 6),
                    "validation_factor": round(validation_factor, 6),
                    "stability_factor": round(stability_factor, 6),
                }
                scored.append(
                    {
                        **row,
                        "score": score,
                        "confidence": max(0.0, min(1.0, confidence)),
                        "eligible": eligible,
                        "status": status,
                        "required_gates": required_gates,
                        "rationale": rationale,
                        "reasons": reasons,
                        "replaces_strategy_id": primary_strategy_id if primary_strategy_id and primary_strategy_id != strategy_id else None,
                    }
                )
            scored.sort(key=lambda item: (item["status"] != "pending", -_safe_float((item.get("score") or {}).get("score_weighted"), 0.0), -_safe_float(item.get("confidence"), 0.0)))
            rankings.append(
                {
                    "asset": asset,
                    "timeframe": timeframe,
                    "regime_label": regime,
                    "top": scored[:3],
                    "candidate_count": len(scored),
                }
            )
            top = scored[0]
            proposal_id = hashlib.sha256(f"{asset}|{timeframe}|{regime}|{top['strategy_id']}|{','.join(top.get('feature_sets') or [])}".encode("utf-8")).hexdigest()[:24]
            proposal = {
                "id": proposal_id,
                "asset": asset,
                "timeframe": timeframe,
                "regime_label": regime,
                "proposed_strategy_id": top["strategy_id"],
                "replaces_strategy_id": top.get("replaces_strategy_id"),
                "confidence": round(_safe_float(top.get("confidence"), 0.0), 6),
                "score": top.get("score") or {},
                "rationale": top.get("rationale") or "",
                "required_gates": top.get("required_gates") or [],
                "metrics": {
                    "n_trades_total": top.get("n_trades_total"),
                    "n_days_total": top.get("n_days_total"),
                    "n_trades_regime": top.get("n_trades_regime"),
                    "expectancy_net": top.get("expectancy_net"),
                    "expectancy_gross": top.get("expectancy_gross"),
                    "profit_factor": top.get("profit_factor"),
                    "sharpe": top.get("sharpe"),
                    "sortino": top.get("sortino"),
                    "max_dd": top.get("max_dd"),
                    "hit_rate": top.get("hit_rate"),
                    "turnover": top.get("turnover"),
                    "cost_ratio": top.get("cost_ratio"),
                    "cost_stress_expectancy": top.get("cost_stress_expectancy"),
                    "pbo": top.get("pbo"),
                    "dsr": top.get("dsr"),
                    "psr": top.get("psr"),
                        "feature_sets": top.get("feature_sets") or [],
                        "dominant_feature_set": top.get("dominant_feature_set"),
                        "baseline_feature_set": top.get("baseline_feature_set"),
                        "feature_set_matches_baseline": bool(top.get("feature_set_matches_baseline", True)),
                        "mixed_feature_set": bool(top.get("mixed_feature_set")),
                        "reasons": top.get("reasons") or [],
                    },
                "source_summary": {
                    **(top.get("source_summary") or {}),
                    "validation_factor": top.get("validation_factor"),
                    "source_quality_factor": top.get("source_quality_factor"),
                    "stability_factor": top.get("stability_factor"),
                },
                "needs_validation": str(top.get("status") or "") == "needs_validation",
                "status": str(top.get("status") or "needs_validation"),
            }
            self.registry.upsert_learning_proposal(
                proposal_id=proposal_id,
                asset=asset,
                timeframe=timeframe,
                regime_label=regime,
                proposed_strategy_id=str(top.get("strategy_id") or ""),
                replaces_strategy_id=top.get("replaces_strategy_id"),
                confidence=_safe_float(top.get("confidence"), 0.0),
                rationale=str(top.get("rationale") or ""),
                required_gates=top.get("required_gates") or [],
                score=top.get("score") or {},
                metrics=proposal["metrics"],
                source_summary=proposal["source_summary"],
                needs_validation=proposal["needs_validation"],
                status=proposal["status"],
            )
            generated.append(proposal)
        generated_rows = self.registry.list_learning_proposals()
        return {
            "ok": True,
            "generated_at": _utc_iso(),
            "contexts": len(contexts),
            "proposals": generated_rows,
            "rankings": rankings,
            "summary": self.summarize(strategies=strategies),
        }

    def list_proposals(self, *, status: str | None = None) -> list[dict[str, Any]]:
        return self.registry.list_learning_proposals(status=status)

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        return self.registry.get_learning_proposal(proposal_id)

    def set_proposal_status(self, proposal_id: str, *, status: str, note: str | None = None) -> dict[str, Any] | None:
        return self.registry.patch_learning_proposal_status(proposal_id, status=status, note=note)

    def list_guidance(self) -> list[dict[str, Any]]:
        return self.registry.list_strategy_policy_guidance()

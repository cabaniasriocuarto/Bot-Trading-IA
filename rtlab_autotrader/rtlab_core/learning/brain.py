from __future__ import annotations

import itertools
import math
import random
from statistics import mean, pstdev
from typing import Any


MEDIUM_RISK_PROFILE: dict[str, Any] = {
    "risk_profile": "medium",
    "paper": {
        "risk_per_trade_pct": 0.5,
        "max_daily_loss_pct": 3.0,
        "max_drawdown_pct": 15.0,
    },
    "live_initial": {
        "risk_per_trade_pct": 0.25,
        "max_daily_loss_pct": 2.0,
        "max_drawdown_pct": 10.0,
    },
    "max_positions": 10,
    "correlation_penalty_threshold": 0.75,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def compute_normalized_reward(
    *,
    pnl_net: float,
    total_costs: float,
    drawdown_increment: float,
    atr: float | None = None,
    realized_vol: float | None = None,
    lambda_cost: float = 1.0,
    lambda_risk: float = 1.0,
) -> float:
    denom = max(abs(_safe_float(atr, 0.0)), abs(_safe_float(realized_vol, 0.0)), 1e-9)
    reward = _safe_float(pnl_net) - (lambda_cost * _safe_float(total_costs)) - (lambda_risk * _safe_float(drawdown_increment))
    return float(reward / denom)


def _candidate_stats(candidate: dict[str, Any]) -> dict[str, float]:
    stats = candidate.get("stats") if isinstance(candidate.get("stats"), dict) else {}
    wins = int(stats.get("wins", candidate.get("wins", 0)) or 0)
    losses = int(stats.get("losses", candidate.get("losses", 0)) or 0)
    pulls = int(stats.get("pulls", candidate.get("pulls", wins + losses)) or 0)
    reward_mean = _safe_float(stats.get("reward_mean", candidate.get("reward", 0.0)))
    regime_fit = _safe_float(stats.get("regime_fit", candidate.get("regime_fit", 0.0)))
    cost_penalty = _safe_float(stats.get("cost_penalty", candidate.get("cost_penalty", 0.0)))
    risk_penalty = _safe_float(stats.get("risk_penalty", candidate.get("risk_penalty", 0.0)))
    return {
        "wins": float(max(wins, 0)),
        "losses": float(max(losses, 0)),
        "pulls": float(max(pulls, 1)),
        "reward_mean": reward_mean,
        "regime_fit": regime_fit,
        "cost_penalty": cost_penalty,
        "risk_penalty": risk_penalty,
    }


class StrategySelector:
    def __init__(self, algo: str = "thompson", *, seed: int = 7) -> None:
        self.algo = (algo or "thompson").strip().lower()
        self._rng = random.Random(seed)

    def _score_thompson(self, candidate: dict[str, Any]) -> float:
        s = _candidate_stats(candidate)
        alpha = 1.0 + s["wins"]
        beta = 1.0 + s["losses"]
        sample = self._rng.betavariate(alpha, beta)
        return float(sample + 0.35 * math.tanh(s["reward_mean"]) + 0.20 * s["regime_fit"] - 0.15 * s["cost_penalty"] - 0.15 * s["risk_penalty"])

    def _score_ucb1(self, candidate: dict[str, Any], total_pulls: float) -> float:
        s = _candidate_stats(candidate)
        mean_reward = s["reward_mean"]
        pulls = max(1.0, s["pulls"])
        bonus = math.sqrt((2.0 * math.log(max(total_pulls, 2.0))) / pulls)
        return float(mean_reward + bonus + 0.15 * s["regime_fit"] - 0.15 * s["cost_penalty"] - 0.15 * s["risk_penalty"])

    def _score_regime_rules(self, candidate: dict[str, Any], context: dict[str, Any]) -> float:
        s = _candidate_stats(candidate)
        template_tags = set(str(x).lower() for x in candidate.get("tags", []))
        regime = str(context.get("regime", "range")).lower()
        score = s["reward_mean"] - 0.20 * s["cost_penalty"] - 0.20 * s["risk_penalty"]
        if regime in {"trend", "trending"} and {"trend", "momentum"} & template_tags:
            score += 0.5
        if regime in {"range", "lateral"} and {"range", "mean_reversion"} & template_tags:
            score += 0.5
        if regime in {"high_vol", "high-vol", "volatility"} and {"volatility", "breakout"} & template_tags:
            score += 0.5
        score += 0.25 * s["regime_fit"]
        return float(score)

    def select(self, candidates: list[dict[str, Any]], *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        context = context or {}
        if not candidates:
            return {"active_strategy_id": None, "weights": {}, "explanation": "Sin candidatos."}

        algo = self.algo if self.algo in {"thompson", "ucb1", "regime_rules"} else "thompson"
        total_pulls = sum(_candidate_stats(c)["pulls"] for c in candidates)
        scores: list[tuple[dict[str, Any], float]] = []
        for cand in candidates:
            if algo == "ucb1":
                score = self._score_ucb1(cand, total_pulls)
            elif algo == "regime_rules":
                score = self._score_regime_rules(cand, context)
            else:
                score = self._score_thompson(cand)
            scores.append((cand, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        best = scores[0][0]

        top_scores = [max(item[1], -5.0) for item in scores[: min(len(scores), 5)]]
        exps = [math.exp(min(5.0, s)) for s in top_scores]
        total = sum(exps) or 1.0
        weights = {scores[i][0]["id"]: round(exps[i] / total, 4) for i in range(len(exps))}

        regime = str(context.get("regime", "desconocido"))
        costs = _safe_float(best.get("cost_penalty", best.get("stats", {}).get("cost_penalty", 0.0)))
        risk = _safe_float(best.get("risk_penalty", best.get("stats", {}).get("risk_penalty", 0.0)))
        explanation = f"{algo}: seleccionado por regime={regime}, costos={costs:.2f}, riesgo={risk:.2f}"
        return {"active_strategy_id": best["id"], "weights": weights, "explanation": explanation}


def _standardize(values: list[float]) -> list[float]:
    if not values:
        return []
    mu = mean(values)
    sigma = pstdev(values)
    if sigma <= 1e-12:
        return [0.0 for _ in values]
    return [(x - mu) / sigma for x in values]


def _adwin_like(series: list[float]) -> dict[str, Any]:
    if len(series) < 20:
        return {"drift": False, "score": 0.0, "algo": "adwin", "reason": "insufficient_data"}
    half = len(series) // 2
    left = series[:half]
    right = series[half:]
    m1 = mean(left)
    m2 = mean(right)
    v = pstdev(series) or 1e-9
    score = abs(m2 - m1) / v
    return {"drift": score > 1.1, "score": round(score, 4), "algo": "adwin", "reason": f"mean_shift={m2-m1:.4f}"}


def _page_hinkley(series: list[float]) -> dict[str, Any]:
    if len(series) < 20:
        return {"drift": False, "score": 0.0, "algo": "page_hinkley", "reason": "insufficient_data"}
    avg = 0.0
    cumulative = 0.0
    min_cum = 0.0
    delta = 0.01
    lam = 5.0
    max_gap = 0.0
    for idx, x in enumerate(series, start=1):
        avg += (x - avg) / idx
        cumulative += x - avg - delta
        min_cum = min(min_cum, cumulative)
        max_gap = max(max_gap, cumulative - min_cum)
    return {"drift": max_gap > lam, "score": round(max_gap, 4), "algo": "page_hinkley", "reason": f"cum_gap={max_gap:.4f}"}


def detect_drift(streams: dict[str, list[float]], algo: str = "adwin") -> dict[str, Any]:
    algo_n = (algo or "adwin").lower().strip()
    metrics = ["returns", "realized_vol", "atr", "spread_bps", "slippage_bps", "expectancy_usd", "max_dd"]
    per_metric: dict[str, Any] = {}
    votes = 0
    for key in metrics:
        values = [float(x) for x in (streams.get(key) or []) if isinstance(x, (int, float))]
        if key == "max_dd":
            values = [abs(v) for v in values]
        if not values:
            per_metric[key] = {"drift": False, "score": 0.0, "reason": "no_data"}
            continue
        standardized = _standardize(values)
        result = _page_hinkley(standardized) if algo_n == "page_hinkley" else _adwin_like(standardized)
        per_metric[key] = result
        votes += 1 if result.get("drift") else 0
    drift = votes >= 2
    return {
        "algo": "page_hinkley" if algo_n == "page_hinkley" else "adwin",
        "drift": drift,
        "votes": votes,
        "metrics": per_metric,
    }


def _simple_sharpe(returns: list[float]) -> float:
    if not returns:
        return 0.0
    mu = mean(returns)
    sigma = pstdev(returns)
    if sigma <= 1e-12:
        return 0.0
    return float((mu / sigma) * math.sqrt(252.0))


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def deflated_sharpe_ratio(returns: list[float], *, trials: int = 1) -> dict[str, float]:
    n = len(returns)
    sharpe = _simple_sharpe(returns)
    if n < 3:
        return {"sharpe": round(sharpe, 6), "dsr": 0.0, "sr_deflated": round(sharpe, 6)}
    sr_std = math.sqrt((1.0 + 0.5 * (sharpe**2)) / max(1.0, n - 1.0))
    trial_penalty = math.sqrt(max(0.0, 2.0 * math.log(max(1, trials))))
    sr_deflated = sharpe - (trial_penalty * sr_std)
    z = 0.0 if sr_std <= 1e-12 else (sr_deflated / sr_std)
    dsr = _normal_cdf(z)
    return {"sharpe": round(sharpe, 6), "dsr": round(float(dsr), 6), "sr_deflated": round(float(sr_deflated), 6)}


def pbo_cscv(candidate_returns: dict[str, list[float]], *, slices: int = 8) -> dict[str, Any]:
    clean = {k: [float(x) for x in v if isinstance(x, (int, float))] for k, v in candidate_returns.items() if v}
    if len(clean) < 2:
        return {"pbo": None, "trials": 0, "implemented": True, "reason": "need_at_least_2_candidates"}
    min_len = min(len(v) for v in clean.values())
    if min_len < max(16, slices):
        return {"pbo": None, "trials": 0, "implemented": True, "reason": "insufficient_return_history"}

    slice_size = min_len // slices
    if slice_size < 2:
        return {"pbo": None, "trials": 0, "implemented": True, "reason": "slice_too_small"}
    usable = slice_size * slices
    partitions = {k: [vals[i * slice_size : (i + 1) * slice_size] for i in range(slices)] for k, vals in clean.items()}

    half = slices // 2
    combos = list(itertools.combinations(range(slices), half))
    lambda_logits: list[float] = []
    oos_percentiles: list[float] = []
    for ins_idx in combos:
        oos_idx = [i for i in range(slices) if i not in set(ins_idx)]
        in_scores: dict[str, float] = {}
        out_scores: dict[str, float] = {}
        for cand_id in partitions:
            ins_returns = [x for i in ins_idx for x in partitions[cand_id][i]]
            oos_returns = [x for i in oos_idx for x in partitions[cand_id][i]]
            in_scores[cand_id] = _simple_sharpe(ins_returns)
            out_scores[cand_id] = _simple_sharpe(oos_returns)
        best_is = max(in_scores, key=in_scores.get)
        ranked_oos = sorted(out_scores.items(), key=lambda kv: kv[1])
        rank = next((idx for idx, (cid, _val) in enumerate(ranked_oos) if cid == best_is), 0)
        percentile = (rank + 1) / max(1, len(ranked_oos))
        percentile = min(max(percentile, 1e-6), 1 - 1e-6)
        oos_percentiles.append(percentile)
        lambda_logits.append(math.log(percentile / (1.0 - percentile)))

    pbo = sum(1 for l in lambda_logits if l <= 0) / max(1, len(lambda_logits))
    return {
        "pbo": round(float(pbo), 6),
        "trials": len(lambda_logits),
        "implemented": True,
        "usable_points": usable,
        "avg_oos_percentile": round(float(mean(oos_percentiles)), 6) if oos_percentiles else None,
    }

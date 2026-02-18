from __future__ import annotations


def stress_metrics(metrics: dict[str, float], fees_mult: float, slippage_mult: float, param_variation: float) -> dict[str, float]:
    stressed = dict(metrics)
    expectancy_penalty = (fees_mult - 1.0) * 0.2 + (slippage_mult - 1.0) * 0.3 + param_variation * 0.5
    stressed["expectancy_stressed"] = float(metrics.get("expectancy", 0.0) * max(0.0, 1.0 - expectancy_penalty))
    stressed["max_drawdown_stressed"] = float(metrics.get("max_drawdown", 0.0) * (1.0 + 0.3 * param_variation))
    stressed["stress_pass"] = stressed["expectancy_stressed"] > 0 and stressed["max_drawdown_stressed"] <= 0.22
    return stressed

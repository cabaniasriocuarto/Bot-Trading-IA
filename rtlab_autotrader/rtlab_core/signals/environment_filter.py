from __future__ import annotations

from dataclasses import dataclass

from rtlab_core.types import CheckResult


@dataclass(slots=True)
class EnvironmentSnapshot:
    vol_24h_usd: float
    spread_bps: float
    vpin_percentile: float
    cost_budget_bps: float
    estimated_total_cost_bps: float


@dataclass(slots=True)
class EnvironmentLimits:
    min_volume_24h_usd: float
    max_spread_bps: float
    max_percentile_to_trade: float


def evaluate_environment(snapshot: EnvironmentSnapshot, limits: EnvironmentLimits) -> CheckResult:
    checks = {
        "liquidity": snapshot.vol_24h_usd >= limits.min_volume_24h_usd,
        "spread": snapshot.spread_bps <= limits.max_spread_bps,
        "toxicity": snapshot.vpin_percentile <= limits.max_percentile_to_trade,
        "cost_budget": snapshot.estimated_total_cost_bps <= snapshot.cost_budget_bps,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return CheckResult(ok=not failed, failed_checks=failed)

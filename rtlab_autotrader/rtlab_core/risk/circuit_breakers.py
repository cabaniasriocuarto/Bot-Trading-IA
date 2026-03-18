from __future__ import annotations

from dataclasses import dataclass

from rtlab_core.runtime_controls import health_scoring_policy
from rtlab_core.types import HealthMetrics


_HEALTH_SCORING = health_scoring_policy()
_CIRCUIT_BREAKERS = (
    _HEALTH_SCORING.get("circuit_breakers")
    if isinstance(_HEALTH_SCORING.get("circuit_breakers"), dict)
    else {}
)


@dataclass(slots=True)
class CircuitBreakerThresholds:
    max_error_streak: int = int(_CIRCUIT_BREAKERS.get("max_error_streak", 3) or 3)
    max_ws_lag_ms: int = int(_CIRCUIT_BREAKERS.get("max_ws_lag_ms", 5000) or 5000)
    max_desync_count: int = int(_CIRCUIT_BREAKERS.get("max_desync_count", 2) or 2)
    max_spread_spike_bps: float = float(_CIRCUIT_BREAKERS.get("max_spread_spike_bps", 25.0) or 25.0)
    max_vpin_percentile: float = float(_CIRCUIT_BREAKERS.get("max_vpin_percentile", 90.0) or 90.0)


class CircuitBreakers:
    def __init__(self, thresholds: CircuitBreakerThresholds) -> None:
        self.thresholds = thresholds

    def evaluate(
        self,
        health: HealthMetrics,
        spread_bps: float,
        vpin_percentile: float,
    ) -> list[str]:
        triggers: list[str] = []
        if health.error_streak >= self.thresholds.max_error_streak:
            triggers.append("error_streak")
        if health.ws_lag_ms >= self.thresholds.max_ws_lag_ms:
            triggers.append("ws_lag")
        if health.desync_count >= self.thresholds.max_desync_count:
            triggers.append("desync")
        if spread_bps >= self.thresholds.max_spread_spike_bps:
            triggers.append("spread_spike")
        if vpin_percentile >= self.thresholds.max_vpin_percentile:
            triggers.append("vpin_spike")
        return triggers

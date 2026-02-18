from __future__ import annotations

from dataclasses import dataclass

from rtlab_core.risk.circuit_breakers import CircuitBreakers
from rtlab_core.risk.kill_switch import KillSwitch
from rtlab_core.risk.safe_mode import SafeModeController
from rtlab_core.types import HealthMetrics


@dataclass(slots=True)
class ExecGuardDecision:
    safe_mode: bool
    kill: bool
    triggers: list[str]


class ExecutionGuard:
    def __init__(
        self,
        circuit_breakers: CircuitBreakers,
        safe_mode: SafeModeController,
        kill_switch: KillSwitch,
        critical_error_limit: int = 5,
    ) -> None:
        self.circuit_breakers = circuit_breakers
        self.safe_mode = safe_mode
        self.kill_switch = kill_switch
        self.critical_error_limit = critical_error_limit

    def evaluate(
        self,
        health: HealthMetrics,
        spread_bps: float,
        vpin_percentile: float,
        critical_errors: int,
    ) -> ExecGuardDecision:
        triggers = self.circuit_breakers.evaluate(health=health, spread_bps=spread_bps, vpin_percentile=vpin_percentile)
        safe = bool(triggers)
        kill = False

        if safe:
            self.safe_mode.enable(";".join(triggers))

        if critical_errors >= self.critical_error_limit:
            kill = True
            self.kill_switch.trigger("critical_errors")

        if "desync" in triggers and health.desync_count >= self.critical_error_limit:
            kill = True
            self.kill_switch.trigger("repeated_desync")

        return ExecGuardDecision(safe_mode=safe, kill=kill, triggers=triggers)

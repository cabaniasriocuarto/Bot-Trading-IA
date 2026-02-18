from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class SafeModeState:
    enabled: bool
    reason: str | None = None
    force_spot_only: bool = True
    disable_shorts: bool = True
    risk_multiplier: float = 0.5
    max_positions: int = 5
    vpin_max_percentile: float = 70.0
    adx_min: float = 20.0
    spread_max_bps: float = 8.0


class SafeModeController:
    def __init__(self, safe_factor: float = 0.5) -> None:
        self.state = SafeModeState(enabled=False, risk_multiplier=safe_factor)

    def enable(self, reason: str) -> SafeModeState:
        self.state.enabled = True
        self.state.reason = reason
        return self.state

    def disable(self) -> SafeModeState:
        self.state.enabled = False
        self.state.reason = None
        return self.state

    def snapshot(self) -> dict[str, object]:
        return asdict(self.state)

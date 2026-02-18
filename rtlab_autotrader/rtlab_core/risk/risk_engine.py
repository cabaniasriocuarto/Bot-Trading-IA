from __future__ import annotations

from dataclasses import dataclass

from rtlab_core.types import RiskDecision


@dataclass(slots=True)
class RiskLimits:
    daily_loss_limit_pct: float
    max_drawdown_pct: float
    max_positions: int
    max_total_exposure_pct: float
    max_asset_exposure_pct: float
    risk_per_trade: float
    safe_factor: float = 0.5


class RiskEngine:
    def __init__(self, limits: RiskLimits, starting_equity: float) -> None:
        self.limits = limits
        self.starting_equity = starting_equity
        self.peak_equity = starting_equity

    def update_peak_equity(self, equity: float) -> None:
        self.peak_equity = max(self.peak_equity, equity)

    def drawdown_pct(self, equity: float) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - equity) / self.peak_equity)

    def daily_loss_pct(self, daily_pnl: float, equity: float) -> float:
        if equity <= 0:
            return 0.0
        return max(0.0, -daily_pnl / equity)

    def position_size(self, equity: float, entry: float, stop: float, confidence: float = 1.0) -> float:
        stop_distance = abs(entry - stop)
        if stop_distance <= 0:
            return 0.0
        risk_budget = equity * self.limits.risk_per_trade * max(0.0, confidence)
        return max(0.0, risk_budget / stop_distance)

    def can_trade(
        self,
        equity: float,
        daily_pnl: float,
        open_positions: int,
        total_exposure_pct: float,
        asset_exposure_pct: float,
        safe_mode: bool = False,
    ) -> RiskDecision:
        self.update_peak_equity(equity)
        max_positions = self.limits.max_positions if not safe_mode else min(self.limits.max_positions, 5)

        if self.daily_loss_pct(daily_pnl, equity) >= self.limits.daily_loss_limit_pct:
            return RiskDecision(False, reason="daily_loss_limit", safe_mode=safe_mode)

        if self.drawdown_pct(equity) >= self.limits.max_drawdown_pct:
            return RiskDecision(False, reason="max_drawdown", safe_mode=safe_mode, kill=True)

        if open_positions >= max_positions:
            return RiskDecision(False, reason="max_positions", safe_mode=safe_mode)

        if total_exposure_pct > self.limits.max_total_exposure_pct:
            return RiskDecision(False, reason="total_exposure", safe_mode=safe_mode)

        if asset_exposure_pct > self.limits.max_asset_exposure_pct:
            return RiskDecision(False, reason="asset_exposure", safe_mode=safe_mode)

        return RiskDecision(True, safe_mode=safe_mode)

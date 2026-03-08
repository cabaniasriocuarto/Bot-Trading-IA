from __future__ import annotations

import numpy as np
import pandas as pd

from rtlab_core.src.backtest.engine import BacktestCosts, BacktestRequest, StrategyRunner


def _request(strategy_id: str) -> BacktestRequest:
    return BacktestRequest(
        market="crypto",
        symbol="BTCUSDT",
        timeframe="5m",
        start="2024-01-01",
        end="2024-12-31",
        strategy_id=strategy_id,
        validation_mode="walk-forward",
        costs=BacktestCosts(
            fees_bps=8.0,
            spread_bps=6.0,
            slippage_bps=4.0,
            funding_bps=0.0,
        ),
    )


def _dataset(periods: int = 320) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01T00:00:00Z", periods=periods, freq="5min")
    close = 100.0 + np.linspace(0.0, 1.6, periods)
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + 0.20
    low = np.minimum(open_, close) - 0.20
    volume = np.full(periods, 1000.0)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


def test_execution_profile_by_family_matches_strategy_contract() -> None:
    runner = StrategyRunner(_request("trend_pullback_orderflow_v2"))
    trend = runner._execution_profile("trend_pullback")
    breakout = runner._execution_profile("breakout")
    meanrev = runner._execution_profile("meanreversion")
    defensive = runner._execution_profile("defensive")

    assert trend.stop_atr_mult == 2.0
    assert trend.take_atr_mult == 3.0
    assert trend.time_stop_bars == 20

    assert breakout.stop_atr_mult == 1.8
    assert breakout.take_atr_mult == 3.2
    assert breakout.trail_activate_atr_mult == 1.2
    assert breakout.trail_distance_atr_mult == 1.8
    assert breakout.time_stop_bars == 16

    assert meanrev.stop_atr_mult == 1.4
    assert meanrev.take_atr_mult == 1.6
    assert meanrev.trailing_enabled is False
    assert meanrev.use_ema20_take_profit is True
    assert meanrev.time_stop_bars == 10

    assert defensive.stop_atr_mult == 2.2
    assert defensive.take_atr_mult == 2.8
    assert defensive.trail_activate_atr_mult == 1.0
    assert defensive.trail_distance_atr_mult == 1.8
    assert defensive.time_stop_bars == 18


def test_trend_scanning_signal_reports_effective_family_for_profile_selection() -> None:
    runner = StrategyRunner(_request("trend_scanning_regime_v2"))
    prev = pd.Series(
        {
            "close": 100.0,
            "high": 103.0,
            "low": 99.0,
            "prev_high": 99.0,
            "prev_low": 98.0,
            "atr14": 2.0,
            "adx14": 17.0,
            "rsi14": 50.0,
            "ema20": 100.0,
            "ema50": 100.0,
            "ema200": 100.0,
        }
    )

    signal, family = runner._signal_with_family(prev)
    assert signal == "long"
    assert family == "breakout"


def test_trades_store_effective_reason_code_family_instead_of_hardcoded_trend() -> None:
    runner = StrategyRunner(_request("trend_scanning_regime_v2"))
    calls = {"n": 0}

    def _fake_signal(_prev: pd.Series) -> tuple[str | None, str]:
        if calls["n"] == 0:
            calls["n"] += 1
            return "long", "breakout"
        return None, "breakout"

    runner._signal_with_family = _fake_signal  # type: ignore[method-assign]
    payload = runner.run(_dataset())
    trades = payload["trades"]
    assert trades, "Se esperaba al menos un trade para validar reason_code por familia"
    assert trades[0]["reason_code"] == "breakout"

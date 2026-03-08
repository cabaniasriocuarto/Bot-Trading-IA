from __future__ import annotations

import pandas as pd
import pytest

from rtlab_core.src.backtest.engine import BacktestCosts, BacktestRequest, StrategyRunner


def _request(strategy_id: str, *, strict_strategy_id: bool = False) -> BacktestRequest:
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
        strict_strategy_id=bool(strict_strategy_id),
    )


def test_breakout_strategy_is_not_evaluated_as_trend_pullback() -> None:
    prev = pd.Series(
        {
            "close": 119.0,
            "high": 120.0,
            "low": 118.0,
            "prev_high": 117.0,
            "prev_low": 116.0,
            "atr14": 1.0,
            "ema20": 100.0,
            "ema50": 101.0,
            "ema200": 102.0,
            "adx14": 10.0,
            "rsi14": 50.0,
        }
    )

    trend_signal = StrategyRunner(_request("trend_pullback_orderflow_v2"))._signal(prev)
    breakout_signal = StrategyRunner(_request("breakout_volatility_v2"))._signal(prev)

    assert trend_signal is None
    assert breakout_signal == "long"


def test_meanreversion_strategy_is_not_evaluated_as_trend_pullback() -> None:
    prev = pd.Series(
        {
            "close": 94.0,
            "high": 95.0,
            "low": 93.0,
            "prev_high": 96.0,
            "prev_low": 92.0,
            "atr14": 5.0,
            "ema20": 100.0,
            "ema50": 100.0,
            "ema200": 99.0,
            "adx14": 15.0,
            "rsi14": 25.0,
        }
    )

    trend_signal = StrategyRunner(_request("trend_pullback_orderflow_v2"))._signal(prev)
    meanrev_signal = StrategyRunner(_request("meanreversion_range_v2"))._signal(prev)

    assert trend_signal is None
    assert meanrev_signal == "long"


def test_trend_scanning_routes_to_breakout_when_high_volatility() -> None:
    prev = pd.Series(
        {
            "close": 100.0,
            "high": 103.0,
            "low": 99.0,
            "prev_high": 99.0,
            "prev_low": 98.0,
            "atr14": 2.0,
            "ema20": 100.0,
            "ema50": 100.0,
            "ema200": 100.0,
            "adx14": 17.0,
            "rsi14": 50.0,
        }
    )

    signal = StrategyRunner(_request("trend_scanning_regime_v2"))._signal(prev)
    assert signal == "long"


def test_defensive_liquidity_applies_obi_gate_when_available() -> None:
    base = {
        "close": 105.0,
        "ema50": 100.0,
        "adx14": 15.0,
        "rsi14": 52.0,
    }
    signal_ok = StrategyRunner(_request("defensive_liquidity_v2"))._signal(pd.Series({**base, "obi_topn": 0.60}))
    signal_blocked = StrategyRunner(_request("defensive_liquidity_v2"))._signal(pd.Series({**base, "obi_topn": 0.40}))

    assert signal_ok == "long"
    assert signal_blocked is None


def test_unknown_strategy_falls_back_to_trend_pullback_when_not_strict() -> None:
    prev = pd.Series(
        {
            "close": 105.0,
            "high": 106.0,
            "low": 99.0,
            "prev_high": 100.0,
            "prev_low": 98.0,
            "atr14": 1.0,
            "ema20": 100.0,
            "ema50": 95.0,
            "ema200": 90.0,
            "adx14": 25.0,
            "rsi14": 55.0,
        }
    )
    trend_signal = StrategyRunner(_request("trend_pullback_orderflow_v2"))._signal(prev)
    unknown_signal = StrategyRunner(_request("rollout_candidate_strategy"))._signal(prev)

    assert trend_signal == "long"
    assert unknown_signal == trend_signal


def test_unknown_strategy_fails_closed_when_strict_mode_enabled() -> None:
    with pytest.raises(ValueError, match="no soportado por BacktestEngine en modo estricto"):
        StrategyRunner(_request("rollout_candidate_strategy", strict_strategy_id=True))

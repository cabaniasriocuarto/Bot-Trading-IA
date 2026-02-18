from __future__ import annotations

import pandas as pd

try:
    from freqtrade.strategy import IStrategy
except Exception:  # pragma: no cover
    class IStrategy:  # type: ignore[override]
        pass


class MicrostructureTrendPullbackStrategy(IStrategy):
    """
    Trend-Pullback + Toxicity Filter + Meta-labeling (size)
    Version simplificada para Freqtrade con filtros robustos.
    """

    timeframe = "5m"
    can_short = True
    startup_candle_count = 240
    process_only_new_candles = True

    minimal_roi = {"0": 0.02}
    stoploss = -0.02

    orderflow_gating_enabled = False  # TESTNET: OFF por defecto

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = dataframe
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
        df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / 14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / 14, adjust=False).mean().replace(0, pd.NA)
        rs = avg_gain / avg_loss
        df["rsi"] = (100 - (100 / (1 + rs))).fillna(50)

        prev_close = df["close"].shift(1)
        tr = pd.concat(
            [
                (df["high"] - df["low"]).abs(),
                (df["high"] - prev_close).abs(),
                (df["low"] - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        df["atr"] = tr.rolling(14, min_periods=1).mean()

        up_move = df["high"].diff()
        down_move = -df["low"].diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        atr_sm = tr.rolling(14, min_periods=1).mean().replace(0, pd.NA)
        plus_di = 100 * (plus_dm.rolling(14, min_periods=1).sum() / atr_sm)
        minus_di = 100 * (minus_dm.rolling(14, min_periods=1).sum() / atr_sm)
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, pd.NA)) * 100
        df["adx"] = dx.rolling(14, min_periods=1).mean().fillna(0)

        df["trend_long"] = (df["ema20"] > df["ema50"]) & (df["close"] > df["ema200"]) & (df["adx"] >= 18)
        df["trend_short"] = (df["ema20"] < df["ema50"]) & (df["close"] < df["ema200"]) & (df["adx"] >= 18)

        df["pullback_long"] = (df["close"] - df["ema20"]).abs() <= 0.7 * df["atr"]
        df["pullback_long"] &= (df["rsi"] >= 45) & (df["rsi"] <= 70)

        df["pullback_short"] = (df["close"] - df["ema20"]).abs() <= 0.7 * df["atr"]
        df["pullback_short"] &= (df["rsi"] >= 30) & (df["rsi"] <= 55)
        return df

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["trend_long"] & dataframe["pullback_long"], "enter_long"] = 1
        dataframe.loc[dataframe["trend_short"] & dataframe["pullback_short"], "enter_short"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["rsi"] > 75, "exit_long"] = 1
        dataframe.loc[dataframe["rsi"] < 25, "exit_short"] = 1
        return dataframe

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class MarketSnapshot:
    symbol: str
    timeframe: str
    ohlcv: pd.DataFrame


def ensure_datetime_index(df: pd.DataFrame, ts_col: str = "timestamp") -> pd.DataFrame:
    out = df.copy()
    if ts_col in out.columns:
        out[ts_col] = pd.to_datetime(out[ts_col], utc=True)
        out = out.set_index(ts_col)
    if not isinstance(out.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have a DatetimeIndex or a timestamp column")
    return out.sort_index()


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    source = ensure_datetime_index(df)
    rule = timeframe.upper().replace("M", "T")
    aggregated = source.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return aggregated.dropna(how="any")


def align_timeframes(base: pd.DataFrame, *others: pd.DataFrame) -> list[pd.DataFrame]:
    aligned = [ensure_datetime_index(base)]
    for frame in others:
        current = ensure_datetime_index(frame)
        current = current.reindex(aligned[0].index, method="ffill")
        aligned.append(current)
    return aligned

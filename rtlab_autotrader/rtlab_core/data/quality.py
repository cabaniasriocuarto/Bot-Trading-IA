from __future__ import annotations

import pandas as pd


REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def check_ohlcv_quality(df: pd.DataFrame) -> dict[str, float | int | bool]:
    missing_columns = [c for c in REQUIRED_OHLCV_COLUMNS if c not in df.columns]
    if missing_columns:
        return {
            "ok": False,
            "missing_columns": len(missing_columns),
            "nan_ratio": 1.0,
            "duplicate_timestamps": 0,
            "negative_prices": 0,
        }

    nan_ratio = float(df[list(REQUIRED_OHLCV_COLUMNS)].isna().mean().mean())
    duplicate_timestamps = int(df.index.duplicated().sum()) if isinstance(df.index, pd.DatetimeIndex) else 0
    negative_prices = int((df[["open", "high", "low", "close"]] <= 0).sum().sum())

    ok = nan_ratio < 0.01 and duplicate_timestamps == 0 and negative_prices == 0
    return {
        "ok": ok,
        "missing_columns": 0,
        "nan_ratio": nan_ratio,
        "duplicate_timestamps": duplicate_timestamps,
        "negative_prices": negative_prices,
    }


def clip_outliers(series: pd.Series, z: float = 4.0) -> pd.Series:
    mean = series.mean()
    std = series.std(ddof=0)
    if std == 0 or pd.isna(std):
        return series.copy()
    lo = mean - z * std
    hi = mean + z * std
    return series.clip(lower=lo, upper=hi)

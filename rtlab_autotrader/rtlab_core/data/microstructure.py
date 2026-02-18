from __future__ import annotations

import numpy as np
import pandas as pd


def spread_bps(bid: float, ask: float) -> float:
    mid = (bid + ask) / 2.0
    if mid <= 0:
        return 0.0
    return ((ask - bid) / mid) * 10000.0


def order_book_imbalance(bids: list[tuple[float, float]], asks: list[tuple[float, float]], depth: int = 5) -> float:
    bid_vol = sum(v for _, v in bids[:depth])
    ask_vol = sum(v for _, v in asks[:depth])
    total = bid_vol + ask_vol
    if total <= 0:
        return 0.5
    return bid_vol / total


def cumulative_volume_delta(trades: pd.DataFrame, window: int = 30) -> pd.Series:
    required = {"side", "volume"}
    if not required.issubset(trades.columns):
        raise ValueError("Trades data must contain side and volume columns")
    signed = np.where(trades["side"].str.lower().eq("buy"), trades["volume"], -trades["volume"])
    signed_series = pd.Series(signed, index=trades.index)
    return signed_series.rolling(window=window, min_periods=1).sum()


def vpin_proxy(buy_volume: pd.Series, sell_volume: pd.Series, window: int = 50) -> pd.Series:
    total = (buy_volume + sell_volume).replace(0, np.nan)
    imbalance = (buy_volume - sell_volume).abs() / total
    min_periods = max(1, min(window, 5))
    raw = imbalance.rolling(window=window, min_periods=min_periods).mean().fillna(0.0)
    percentile = raw.rank(pct=True) * 100.0
    return percentile.clip(lower=0.0, upper=100.0)


def estimate_slippage_bps(volume_share: float, base_bps: float = 3.0, k: float = 0.8) -> float:
    return max(0.0, base_bps + k * max(0.0, volume_share))

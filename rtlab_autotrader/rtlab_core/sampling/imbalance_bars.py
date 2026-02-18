from __future__ import annotations

import pandas as pd


def build_imbalance_bars(signed_volume: pd.Series, threshold: float) -> list[pd.Index]:
    if threshold <= 0:
        raise ValueError("threshold must be > 0")
    cumulative = 0.0
    bars: list[pd.Index] = []
    current_bar: list = []

    for idx, value in signed_volume.items():
        cumulative += float(value)
        current_bar.append(idx)
        if abs(cumulative) >= threshold:
            bars.append(pd.Index(current_bar))
            current_bar = []
            cumulative = 0.0

    if current_bar:
        bars.append(pd.Index(current_bar))
    return bars

from __future__ import annotations

import pandas as pd


def cusum_filter(prices: pd.Series, threshold: float) -> list[pd.Timestamp]:
    if threshold <= 0:
        raise ValueError("threshold must be > 0")
    changes = prices.diff().fillna(0.0)
    s_pos = 0.0
    s_neg = 0.0
    events: list[pd.Timestamp] = []

    for idx, value in changes.items():
        s_pos = max(0.0, s_pos + value)
        s_neg = min(0.0, s_neg + value)
        if s_pos > threshold:
            s_pos = 0.0
            events.append(idx)
        elif abs(s_neg) > threshold:
            s_neg = 0.0
            events.append(idx)
    return events

from __future__ import annotations

import pandas as pd


def label_triple_barrier(
    close: pd.Series,
    events: pd.Index,
    pt_mult: float,
    sl_mult: float,
    horizon: int,
) -> pd.Series:
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    labels = pd.Series(index=events, dtype=int)

    for ts in events:
        if ts not in close.index:
            continue
        start_loc = close.index.get_loc(ts)
        entry = float(close.iloc[start_loc])
        pt = entry * (1.0 + pt_mult)
        sl = entry * (1.0 - sl_mult)

        end_loc = min(start_loc + horizon, len(close) - 1)
        window = close.iloc[start_loc + 1 : end_loc + 1]
        label = 0
        for price in window:
            if price >= pt:
                label = 1
                break
            if price <= sl:
                label = -1
                break
        labels.loc[ts] = label

    return labels.fillna(0).astype(int)

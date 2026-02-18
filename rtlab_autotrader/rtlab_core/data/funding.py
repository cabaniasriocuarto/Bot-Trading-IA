from __future__ import annotations

import pandas as pd


def funding_cost_bps(position_notional: float, funding_rate: float) -> float:
    if position_notional <= 0:
        return 0.0
    return abs(funding_rate) * 10000.0


def funding_proxy_series(index: pd.Index, proxy_bps: float = 1.0) -> pd.Series:
    return pd.Series(proxy_bps, index=index, dtype=float)

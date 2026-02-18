from __future__ import annotations

import numpy as np
import pandas as pd


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = (equity - peak) / peak.replace(0, np.nan)
    return float(abs(dd.min())) if not dd.empty else 0.0


def sharpe_ratio(returns: pd.Series, annualization: int = 365) -> float:
    if returns.empty:
        return 0.0
    mean = returns.mean()
    std = returns.std(ddof=0)
    if std == 0 or np.isnan(std):
        return 0.0
    return float((mean / std) * np.sqrt(annualization))


def compute_metrics(net_pnl: pd.Series, equity_start: float = 10000.0) -> dict[str, float]:
    equity = equity_start + net_pnl.cumsum()
    returns = equity.pct_change().fillna(0.0)
    wins = (net_pnl > 0).sum()
    losses = (net_pnl < 0).sum()
    expectancy = float(net_pnl.mean()) if len(net_pnl) else 0.0
    return {
        "trades": float(len(net_pnl)),
        "win_rate": float(wins / max(1, wins + losses)),
        "expectancy": expectancy,
        "total_return": float((equity.iloc[-1] - equity_start) / equity_start) if len(equity) else 0.0,
        "max_drawdown": max_drawdown(equity),
        "sharpe": sharpe_ratio(returns),
    }

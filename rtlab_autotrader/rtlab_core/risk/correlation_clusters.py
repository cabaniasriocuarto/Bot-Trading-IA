from __future__ import annotations

from collections import defaultdict, deque

import numpy as np
import pandas as pd


def rolling_correlation_matrix(returns: pd.DataFrame, lookback: int) -> pd.DataFrame:
    if len(returns) < lookback:
        window = returns
    else:
        window = returns.iloc[-lookback:]
    return window.corr().fillna(0.0)


def correlation_clusters(returns: pd.DataFrame, threshold: float = 0.7, lookback: int = 250) -> list[list[str]]:
    corr = rolling_correlation_matrix(returns, lookback)
    symbols = list(corr.columns)
    graph: dict[str, set[str]] = defaultdict(set)

    for i, left in enumerate(symbols):
        for right in symbols[i + 1 :]:
            if corr.loc[left, right] >= threshold:
                graph[left].add(right)
                graph[right].add(left)

    visited: set[str] = set()
    clusters: list[list[str]] = []

    for sym in symbols:
        if sym in visited:
            continue
        component: list[str] = []
        queue = deque([sym])
        while queue:
            cur = queue.popleft()
            if cur in visited:
                continue
            visited.add(cur)
            component.append(cur)
            queue.extend(graph[cur] - visited)
        clusters.append(sorted(component))

    return clusters


def btc_beta(asset_returns: pd.Series, btc_returns: pd.Series) -> float:
    aligned = pd.concat([asset_returns, btc_returns], axis=1).dropna()
    if aligned.empty:
        return 0.0
    x = aligned.iloc[:, 1]
    y = aligned.iloc[:, 0]
    var = float(np.var(x, ddof=0))
    if var == 0:
        return 0.0
    cov = float(np.cov(y, x, ddof=0)[0, 1])
    return cov / var


def cluster_position_limit_ok(clusters: list[list[str]], active_symbols: list[str], max_positions_per_cluster: int) -> bool:
    symbol_set = set(active_symbols)
    for cluster in clusters:
        count = len(symbol_set.intersection(cluster))
        if count > max_positions_per_cluster:
            return False
    return True

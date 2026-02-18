import numpy as np
import pandas as pd

from rtlab_core.risk.correlation_clusters import btc_beta, cluster_position_limit_ok, correlation_clusters


def test_clusters_and_btc_beta() -> None:
    rng = np.random.default_rng(42)
    btc = pd.Series(rng.normal(0, 0.01, 300))
    eth = btc * 0.9 + pd.Series(rng.normal(0, 0.003, 300))
    sol = pd.Series(rng.normal(0, 0.01, 300))

    returns = pd.DataFrame({"BTC": btc, "ETH": eth, "SOL": sol})
    clusters = correlation_clusters(returns, threshold=0.6, lookback=250)
    assert any({"BTC", "ETH"}.issubset(set(cluster)) for cluster in clusters)

    beta = btc_beta(eth, btc)
    assert beta > 0

    assert cluster_position_limit_ok(clusters, ["BTC", "ETH"], max_positions_per_cluster=3)
    assert not cluster_position_limit_ok(clusters, ["BTC", "ETH"], max_positions_per_cluster=1)

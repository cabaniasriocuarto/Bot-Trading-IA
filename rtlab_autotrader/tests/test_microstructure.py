import pandas as pd

from rtlab_core.data.microstructure import cumulative_volume_delta, order_book_imbalance, spread_bps, vpin_proxy


def test_spread_bps() -> None:
    assert round(spread_bps(99, 101), 2) == 200.0


def test_order_book_imbalance() -> None:
    bids = [(100, 5), (99.5, 5)]
    asks = [(100.5, 2), (101, 2)]
    obi = order_book_imbalance(bids, asks, depth=2)
    assert 0.0 <= obi <= 1.0
    assert obi > 0.5


def test_cvd_and_vpin_proxy() -> None:
    trades = pd.DataFrame(
        {
            "side": ["buy", "sell", "buy", "buy", "sell"],
            "volume": [2, 1, 3, 4, 2],
        }
    )
    cvd = cumulative_volume_delta(trades, window=3)
    assert len(cvd) == len(trades)

    buy = pd.Series([10, 12, 11, 13, 12, 10, 9, 11])
    sell = pd.Series([9, 8, 10, 9, 10, 11, 12, 10])
    vpin = vpin_proxy(buy, sell, window=4)
    assert (vpin >= 0).all()
    assert (vpin <= 100).all()

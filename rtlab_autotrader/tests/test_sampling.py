import pandas as pd

from rtlab_core.sampling.cusum import cusum_filter
from rtlab_core.sampling.imbalance_bars import build_imbalance_bars


def test_cusum_filter_emits_events() -> None:
    prices = pd.Series([100, 101, 103, 99, 105, 108])
    events = cusum_filter(prices, threshold=2)
    assert len(events) > 0


def test_imbalance_bars() -> None:
    signed_volume = pd.Series([1, 2, -1, 3, -2, -2, 1])
    bars = build_imbalance_bars(signed_volume, threshold=3)
    assert len(bars) >= 2
    assert all(len(bar) >= 1 for bar in bars)

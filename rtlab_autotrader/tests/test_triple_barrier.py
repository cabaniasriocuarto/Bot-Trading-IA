import pandas as pd

from rtlab_core.labeling.triple_barrier import label_triple_barrier


def test_triple_barrier_labels() -> None:
    close = pd.Series([100, 102, 105, 103, 101, 99, 98], index=pd.RangeIndex(0, 7))
    labels = label_triple_barrier(close, events=pd.Index([0, 3]), pt_mult=0.03, sl_mult=0.03, horizon=3)
    assert set(labels.values).issubset({-1, 0, 1})
    assert labels.loc[0] == 1

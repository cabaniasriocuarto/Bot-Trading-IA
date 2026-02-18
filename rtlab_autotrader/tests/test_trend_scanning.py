import numpy as np
import pandas as pd

from rtlab_core.signals.trend_scanning import direction_from_tvalue, trend_scan_tvalue


def test_trend_scan_detects_positive_trend() -> None:
    x = np.linspace(100, 140, 120)
    close = pd.Series(x)
    result = trend_scan_tvalue(close, l_candidates=[20, 40, 80])
    assert result["tvalue_max"] > 0
    assert direction_from_tvalue(result["tvalue_max"], threshold=1.0) == "LONG"

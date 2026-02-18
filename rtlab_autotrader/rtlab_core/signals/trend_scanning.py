from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_L_CANDIDATES = (20, 30, 45, 60, 90)


def _slope_tvalue(y: np.ndarray) -> float:
    n = y.shape[0]
    if n < 3:
        return 0.0
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    y_mean = y.mean()

    cov = np.sum((x - x_mean) * (y - y_mean))
    var_x = np.sum((x - x_mean) ** 2)
    if var_x == 0:
        return 0.0
    slope = cov / var_x
    intercept = y_mean - slope * x_mean

    y_hat = slope * x + intercept
    resid = y - y_hat
    dof = n - 2
    if dof <= 0:
        return 0.0
    sigma2 = np.sum(resid**2) / dof
    se_slope = math.sqrt(sigma2 / var_x) if sigma2 > 0 else 0.0
    if se_slope == 0:
        return 0.0
    return float(slope / se_slope)


def trend_scan_tvalue(close: pd.Series, l_candidates: Iterable[int] = DEFAULT_L_CANDIDATES) -> dict[str, float | int]:
    log_close = np.log(close.dropna().astype(float).to_numpy())
    best_t = 0.0
    best_l = 0

    for length in l_candidates:
        if length <= 2 or log_close.shape[0] < length:
            continue
        window = log_close[-length:]
        tval = _slope_tvalue(window)
        if abs(tval) > abs(best_t):
            best_t = tval
            best_l = length

    return {"tvalue_max": float(best_t), "best_window": int(best_l)}


def direction_from_tvalue(tvalue_max: float, threshold: float) -> str:
    if tvalue_max >= threshold:
        return "LONG"
    if tvalue_max <= -threshold:
        return "SHORT"
    return "FLAT"

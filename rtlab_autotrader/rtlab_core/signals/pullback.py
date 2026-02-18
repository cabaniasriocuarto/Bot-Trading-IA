from __future__ import annotations


def pullback_long(close: float, ema20: float, atr: float, pb_atr: float, rsi_value: float) -> bool:
    return abs(close - ema20) <= pb_atr * atr and 45 <= rsi_value <= 70


def pullback_short(close: float, ema20: float, atr: float, pb_atr: float, rsi_value: float) -> bool:
    return abs(close - ema20) <= pb_atr * atr and 30 <= rsi_value <= 55

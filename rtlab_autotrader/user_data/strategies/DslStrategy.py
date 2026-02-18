from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

try:
    from freqtrade.strategy import IStrategy
except Exception:  # pragma: no cover
    class IStrategy:  # type: ignore[override]
        pass


class DslStrategy(IStrategy):
    """
    Estrategia puente para packs DSL compilados.
    Lee el artefacto JSON desde `RTLAB_DSL_ARTIFACT` y usa reglas basicas.
    """

    timeframe = "5m"
    can_short = True
    startup_candle_count = 240

    minimal_roi = {"0": 0.015}
    stoploss = -0.02

    def _load_artifact(self) -> dict:
        path = Path(os.environ.get("RTLAB_DSL_ARTIFACT", ""))
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["ema20"] = dataframe["close"].ewm(span=20, adjust=False).mean()
        dataframe["ema50"] = dataframe["close"].ewm(span=50, adjust=False).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        _ = self._load_artifact()
        dataframe.loc[dataframe["ema20"] > dataframe["ema50"], "enter_long"] = 1
        dataframe.loc[dataframe["ema20"] < dataframe["ema50"], "enter_short"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe.loc[dataframe["ema20"] < dataframe["ema50"], "exit_long"] = 1
        dataframe.loc[dataframe["ema20"] > dataframe["ema50"], "exit_short"] = 1
        return dataframe

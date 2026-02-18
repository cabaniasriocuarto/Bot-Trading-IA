from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class RealismConfig:
    maker_fee_bps: float
    taker_fee_bps: float
    spread_proxy_bps: float
    slippage_base_bps: float
    slippage_vol_k: float
    funding_proxy_bps: float


class RealismGate:
    def __init__(self, config: RealismConfig) -> None:
        self.config = config

    def _confidence(self, trades: pd.DataFrame) -> str:
        has_spread = "spread_bps" in trades.columns
        has_slippage = "slippage_bps" in trades.columns
        has_funding = "funding_bps" in trades.columns
        score = int(has_spread) + int(has_slippage) + int(has_funding)
        if score == 3:
            return "HIGH"
        if score == 2:
            return "MED"
        return "LOW"

    def apply(self, trades: pd.DataFrame) -> dict[str, object]:
        if trades.empty:
            return {
                "trades": trades.copy(),
                "summary": {
                    "gross_pnl": 0.0,
                    "net_pnl": 0.0,
                    "fees_cost": 0.0,
                    "slippage_cost": 0.0,
                    "funding_cost": 0.0,
                    "cost_pct_of_gross": 0.0,
                    "confidence_level": "LOW",
                },
            }

        df = trades.copy()
        if "notional" not in df.columns:
            df["notional"] = 1.0

        fee_bps = df.get("fee_bps", pd.Series(self.config.taker_fee_bps, index=df.index, dtype=float))
        spread_bps = df.get("spread_bps", pd.Series(self.config.spread_proxy_bps, index=df.index, dtype=float))

        if "slippage_bps" in df.columns:
            slippage_bps = df["slippage_bps"]
        else:
            volume_share = df.get("volume_share", pd.Series(0.0, index=df.index, dtype=float))
            slippage_bps = self.config.slippage_base_bps + self.config.slippage_vol_k * volume_share

        funding_bps = df.get("funding_bps", pd.Series(self.config.funding_proxy_bps, index=df.index, dtype=float))
        gross_pnl = df.get("raw_pnl", pd.Series(0.0, index=df.index, dtype=float))

        fees_cost = df["notional"] * fee_bps / 10000.0
        spread_cost = df["notional"] * spread_bps / 10000.0
        slippage_cost = df["notional"] * slippage_bps / 10000.0
        funding_cost = df["notional"] * funding_bps / 10000.0

        total_cost = fees_cost + spread_cost + slippage_cost + funding_cost
        net_pnl = gross_pnl - total_cost

        df["gross_pnl"] = gross_pnl
        df["net_pnl"] = net_pnl
        df["fees_cost"] = fees_cost
        df["spread_cost"] = spread_cost
        df["slippage_cost"] = slippage_cost
        df["funding_cost"] = funding_cost

        gross_sum = float(gross_pnl.sum())
        net_sum = float(net_pnl.sum())
        fees_sum = float(fees_cost.sum())
        slippage_sum = float((spread_cost + slippage_cost).sum())
        funding_sum = float(funding_cost.sum())
        cost_pct = 0.0 if gross_sum == 0 else float((gross_sum - net_sum) / abs(gross_sum))

        return {
            "trades": df,
            "summary": {
                "gross_pnl": gross_sum,
                "net_pnl": net_sum,
                "fees_cost": fees_sum,
                "slippage_cost": slippage_sum,
                "funding_cost": funding_sum,
                "cost_pct_of_gross": cost_pct,
                "confidence_level": self._confidence(df),
            },
        }

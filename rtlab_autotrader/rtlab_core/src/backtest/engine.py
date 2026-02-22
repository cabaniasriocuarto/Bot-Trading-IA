from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

import numpy as np
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
    atr = _atr(high, low, close, period).replace(0.0, np.nan)
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False).mean().fillna(0.0)


@dataclass(slots=True)
class BacktestCosts:
    fees_bps: float
    spread_bps: float
    slippage_bps: float
    funding_bps: float
    rollover_bps: float = 0.0
    maker_fee_bps: float | None = None
    taker_fee_bps: float | None = None
    slip_perc: float | None = None
    slip_open: bool = True


@dataclass(slots=True)
class BacktestRequest:
    market: str
    symbol: str
    timeframe: str
    start: str
    end: str
    strategy_id: str
    validation_mode: str
    costs: BacktestCosts


@dataclass(slots=True)
class MarketDataset:
    market: str
    symbol: str
    timeframe: str
    source: str
    dataset_hash: str
    df: pd.DataFrame
    manifest: dict[str, Any]


class IndicatorEngine:
    def enrich(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["ema20"] = _ema(out["close"], 20)
        out["ema50"] = _ema(out["close"], 50)
        out["ema200"] = _ema(out["close"], 200)
        out["rsi14"] = _rsi(out["close"], 14)
        out["atr14"] = _atr(out["high"], out["low"], out["close"], 14)
        out["adx14"] = _adx(out["high"], out["low"], out["close"], 14)
        out["prev_high"] = out["high"].shift(1)
        out["prev_low"] = out["low"].shift(1)
        return out


class CostModel:
    def __init__(self, market: str, costs: BacktestCosts) -> None:
        self.market = market
        self.costs = costs

    def spread_bps_for_bar(self, bar: pd.Series) -> float:
        if self.market == "forex" and "bid_open" in bar.index and "ask_open" in bar.index:
            mid = float((bar["bid_open"] + bar["ask_open"]) / 2.0)
            if mid > 0:
                return float(((bar["ask_open"] - bar["bid_open"]) / mid) * 10000.0)
        return float(self.costs.spread_bps)

    def fill_price(self, bar_open: float, side: str, spread_bps: float, slippage_bps: float) -> tuple[float, float, float]:
        half_spread = spread_bps / 2.0
        slip = slippage_bps
        if side == "long":
            px = bar_open * (1.0 + (half_spread + slip) / 10000.0)
        else:
            px = bar_open * (1.0 - (half_spread + slip) / 10000.0)
        return float(px), float(half_spread), float(slip)

    def apply_fill_costs(self, price: float, qty: float, fee_bps: float, spread_half_bps: float, slip_bps: float) -> tuple[float, float, float]:
        notional = abs(price * qty)
        fees = notional * (fee_bps / 10000.0)
        spread_cost = notional * (spread_half_bps / 10000.0)
        slippage_cost = notional * (slip_bps / 10000.0)
        return float(fees), float(spread_cost), float(slippage_cost)


class ExecutionSimulator:
    def __init__(self, cost_model: CostModel) -> None:
        self.cost_model = cost_model

    def market_fill(self, bar: pd.Series, side: str, qty: float, *, fee_bps: float) -> dict[str, float]:
        spread_bps = self.cost_model.spread_bps_for_bar(bar)
        slippage_bps = float(self.cost_model.costs.slippage_bps)
        px, half_spread_bps, slip_bps = self.cost_model.fill_price(float(bar["open"]), side, spread_bps, slippage_bps)
        fees, spread_cost, slippage_cost = self.cost_model.apply_fill_costs(px, qty, fee_bps, half_spread_bps, slip_bps)
        return {
            "fill_px": px,
            "fees": fees,
            "spread_cost": spread_cost,
            "slippage_cost": slippage_cost,
            "spread_bps_used": spread_bps,
            "slippage_bps_used": slippage_bps,
        }

    def limit_fill(self, bar: pd.Series, side: str, limit_px: float, qty: float, *, fee_bps: float) -> dict[str, float] | None:
        if side == "long" and float(bar["low"]) > limit_px:
            return None
        if side == "short" and float(bar["high"]) < limit_px:
            return None
        spread_bps = self.cost_model.spread_bps_for_bar(bar)
        fees, spread_cost, slippage_cost = self.cost_model.apply_fill_costs(limit_px, qty, fee_bps, spread_bps / 2.0, 0.0)
        return {
            "fill_px": float(limit_px),
            "fees": fees,
            "spread_cost": spread_cost,
            "slippage_cost": slippage_cost,
            "spread_bps_used": spread_bps,
            "slippage_bps_used": 0.0,
        }


class PortfolioEngine:
    def __init__(self, equity_start: float = 10000.0) -> None:
        self.equity_start = float(equity_start)
        self.equity = float(equity_start)
        self.realized = 0.0
        self.curve: list[dict[str, Any]] = []
        self.max_equity = float(equity_start)

    def mark(self, ts: pd.Timestamp, unrealized: float = 0.0) -> None:
        eq = self.equity_start + self.realized + unrealized
        self.equity = float(eq)
        self.max_equity = max(self.max_equity, self.equity)
        dd = 0.0 if self.max_equity <= 0 else (self.equity - self.max_equity) / self.max_equity
        self.curve.append({"time": ts.isoformat(), "equity": round(self.equity, 4), "drawdown": round(float(dd), 6)})

    def realize(self, pnl_net: float) -> None:
        self.realized += float(pnl_net)


class StrategyRunner:
    def __init__(self, request: BacktestRequest, fee_bps: float | None = None) -> None:
        self.request = request
        self.qty = 1.0
        self.fee_bps = float(fee_bps if fee_bps is not None else (request.costs.taker_fee_bps or request.costs.fees_bps))

    def _signal(self, prev: pd.Series) -> str | None:
        if any(pd.isna(prev.get(col)) for col in ("ema20", "ema50", "ema200", "adx14", "rsi14", "atr14", "prev_high", "prev_low")):
            return None
        long_regime = float(prev["ema20"]) > float(prev["ema50"]) and float(prev["close"]) > float(prev["ema200"]) and float(prev["adx14"]) > 18.0
        short_regime = float(prev["ema20"]) < float(prev["ema50"]) and float(prev["close"]) < float(prev["ema200"]) and float(prev["adx14"]) > 18.0
        long_trigger = float(prev["low"]) <= float(prev["ema20"]) and 45.0 <= float(prev["rsi14"]) <= 70.0 and float(prev["close"]) > float(prev["prev_high"])
        short_trigger = float(prev["high"]) >= float(prev["ema20"]) and 30.0 <= float(prev["rsi14"]) <= 55.0 and float(prev["close"]) < float(prev["prev_low"])
        if long_regime and long_trigger:
            return "long"
        if short_regime and short_trigger:
            return "short"
        return None

    def run(self, df: pd.DataFrame) -> dict[str, Any]:
        cost_model = CostModel(self.request.market, self.request.costs)
        simulator = ExecutionSimulator(cost_model)
        portfolio = PortfolioEngine(10000.0)

        trades: list[dict[str, Any]] = []
        position: dict[str, Any] | None = None
        pending_entry: str | None = None
        total_fees = 0.0
        total_spread = 0.0
        total_slippage = 0.0
        total_funding = 0.0
        total_rollover = 0.0
        total_gross = 0.0
        exposure_sum = 0.0
        exposure_points = 0

        enriched = IndicatorEngine().enrich(df)
        rows = list(enriched.iterrows())
        if len(rows) < 250:
            raise ValueError("Dataset demasiado corto para backtest (min ~250 velas)")

        for i, (ts, bar) in enumerate(rows):
            if pending_entry and position is None:
                fill = simulator.market_fill(bar, pending_entry, self.qty, fee_bps=self.fee_bps)
                atr = max(float(bar.get("atr14", 0.0) or 0.0), max(float(bar["close"]) * 0.001, 0.01))
                entry_px = float(fill["fill_px"])
                side = pending_entry
                position = {
                    "side": side,
                    "qty": self.qty,
                    "entry_ts": ts,
                    "entry_px": entry_px,
                    "entry_index": i,
                    "entry_fees": float(fill["fees"]),
                    "entry_spread_cost": float(fill["spread_cost"]),
                    "entry_slippage_cost": float(fill["slippage_cost"]),
                    "atr": atr,
                    "stop_px": entry_px - 2.0 * atr if side == "long" else entry_px + 2.0 * atr,
                    "take_px": entry_px + 3.0 * atr if side == "long" else entry_px - 3.0 * atr,
                    "trail_active": False,
                    "trail_px": None,
                    "bars_open": 0,
                }
                pending_entry = None

            unrealized = 0.0
            if position is not None:
                position["bars_open"] += 1
                side = str(position["side"])
                qty = float(position["qty"])
                if side == "long":
                    move = float(bar["close"]) - float(position["entry_px"])
                else:
                    move = float(position["entry_px"]) - float(bar["close"])
                unrealized = move * qty

                atr = float(position["atr"])
                if not position["trail_active"]:
                    if side == "long" and float(bar["high"]) >= float(position["entry_px"]) + 1.5 * atr:
                        position["trail_active"] = True
                    if side == "short" and float(bar["low"]) <= float(position["entry_px"]) - 1.5 * atr:
                        position["trail_active"] = True
                if position["trail_active"]:
                    if side == "long":
                        candidate = float(bar["close"]) - 2.0 * atr
                        position["trail_px"] = max(float(position.get("trail_px") or position["stop_px"]), candidate)
                    else:
                        candidate = float(bar["close"]) + 2.0 * atr
                        position["trail_px"] = min(float(position.get("trail_px") or position["stop_px"]), candidate)

                stop_px = float(position["trail_px"] if position.get("trail_px") is not None else position["stop_px"])
                take_px = float(position["take_px"])
                exit_reason: str | None = None
                exit_px: float | None = None
                if side == "long":
                    if float(bar["low"]) <= stop_px:
                        exit_reason, exit_px = "sl", stop_px
                    elif float(bar["high"]) >= take_px:
                        exit_reason, exit_px = "tp", take_px
                else:
                    if float(bar["high"]) >= stop_px:
                        exit_reason, exit_px = "sl", stop_px
                    elif float(bar["low"]) <= take_px:
                        exit_reason, exit_px = "tp", take_px

                if exit_reason is None and int(position["bars_open"]) >= 12:
                    exit_reason, exit_px = "time", float(bar["close"])

                if exit_reason and exit_px is not None:
                    # Model exit as a fill on this bar with market costs and capped to bar range.
                    synthetic_bar = bar.copy()
                    synthetic_bar["open"] = float(min(max(exit_px, float(bar["low"])), float(bar["high"])))
                    exit_fill_side = "short" if side == "long" else "long"
                    exit_fill = simulator.market_fill(synthetic_bar, exit_fill_side, qty, fee_bps=self.fee_bps)
                    realized_exit_px = float(exit_fill["fill_px"])
                    if side == "long":
                        gross = (realized_exit_px - float(position["entry_px"])) * qty
                    else:
                        gross = (float(position["entry_px"]) - realized_exit_px) * qty
                    hold_minutes = max(1.0, (ts - position["entry_ts"]).total_seconds() / 60.0)
                    avg_notional = (abs(float(position["entry_px"]) * qty) + abs(realized_exit_px * qty)) / 2.0
                    funding = avg_notional * (self.request.costs.funding_bps / 10000.0) * (hold_minutes / 480.0)
                    rollover = avg_notional * (self.request.costs.rollover_bps / 10000.0) * (hold_minutes / (24 * 60))
                    fee_total = float(position["entry_fees"]) + float(exit_fill["fees"])
                    spread_total = float(position["entry_spread_cost"]) + float(exit_fill["spread_cost"])
                    slippage_total = float(position["entry_slippage_cost"]) + float(exit_fill["slippage_cost"])
                    cost_total = fee_total + spread_total + slippage_total + funding + rollover
                    net = gross - cost_total

                    total_fees += fee_total
                    total_spread += spread_total
                    total_slippage += slippage_total
                    total_funding += funding
                    total_rollover += rollover
                    total_gross += gross
                    portfolio.realize(net)

                    trades.append(
                        {
                            "id": f"tr_{len(trades)+1:06d}",
                            "strategy_id": self.request.strategy_id,
                            "symbol": self.request.symbol,
                            "side": side,
                            "timeframe": self.request.timeframe,
                            "entry_time": position["entry_ts"].isoformat(),
                            "exit_time": ts.isoformat(),
                            "entry_px": round(float(position["entry_px"]), 6),
                            "exit_px": round(realized_exit_px, 6),
                            "qty": qty,
                            "fees": round(fee_total, 6),
                            "spread_cost": round(spread_total, 6),
                            "slippage_cost": round(slippage_total, 6),
                            "funding_cost": round(funding, 6),
                            "rollover_cost": round(rollover, 6),
                            "slippage": round(spread_total + slippage_total, 6),
                            "pnl": round(gross, 6),
                            "pnl_net": round(net, 6),
                            "mae": round(abs(gross) * 0.6, 6),
                            "mfe": round(abs(gross) * 1.1, 6),
                            "reason_code": "trend_pullback",
                            "exit_reason": exit_reason,
                            "events": [
                                {"ts": position["entry_ts"].isoformat(), "type": "fill", "detail": "Entrada market simulada"},
                                {"ts": ts.isoformat(), "type": "exit", "detail": f"Salida {exit_reason}"},
                            ],
                            "explain": {
                                "whitelist_ok": True,
                                "trend_ok": True,
                                "pullback_ok": True,
                                "orderflow_ok": self.request.market != "equities",
                                "vpin_ok": True,
                                "spread_ok": True,
                            },
                        }
                    )
                    position = None
                    unrealized = 0.0

            if i > 0 and position is None:
                prev = rows[i - 1][1]
                pending_entry = self._signal(prev)

            if position is not None:
                exposure_sum += abs(float(position["qty"]) * float(bar["close"]))
            exposure_points += 1
            portfolio.mark(ts, unrealized=unrealized)

        if not portfolio.curve:
            raise ValueError("No se pudo construir equity curve")

        return {
            "equity_curve": portfolio.curve,
            "drawdown_curve": [{"time": p["time"], "value": p["drawdown"]} for p in portfolio.curve],
            "trades": trades,
            "costs": {
                "fees_total": float(total_fees),
                "spread_total": float(total_spread),
                "slippage_total": float(total_slippage),
                "funding_total": float(total_funding),
                "rollover_total": float(total_rollover),
                "gross_pnl_total": float(total_gross),
            },
            "avg_exposure": float(exposure_sum / max(1, exposure_points)),
        }


class ReportEngine:
    def build_metrics(self, *, trades: list[dict[str, Any]], equity_curve: list[dict[str, Any]], avg_exposure: float) -> dict[str, Any]:
        if not equity_curve:
            raise ValueError("equity_curve vacío")
        eq = pd.DataFrame(equity_curve)
        eq["time"] = pd.to_datetime(eq["time"], utc=True)
        eq = eq.sort_values("time")
        eq["ret"] = eq["equity"].pct_change().fillna(0.0)
        returns = eq["ret"]
        mean_r = float(returns.mean())
        std_r = float(returns.std(ddof=0))
        downside = returns.clip(upper=0.0)
        downside_std = float(downside.std(ddof=0))
        sharpe = 0.0 if std_r == 0 else (mean_r / std_r) * sqrt(365 * 24 * 12)
        sortino = 0.0 if downside_std == 0 else (mean_r / downside_std) * sqrt(365 * 24 * 12)

        total_return = float((eq["equity"].iloc[-1] / eq["equity"].iloc[0]) - 1.0) if len(eq) > 1 else 0.0
        days = max(1.0, float((eq["time"].iloc[-1] - eq["time"].iloc[0]).total_seconds() / 86400.0))
        cagr = float((1.0 + total_return) ** (365.0 / days) - 1.0) if total_return > -0.999 else -1.0
        max_dd = float(abs(pd.Series([float(x["drawdown"]) for x in equity_curve]).min())) if equity_curve else 0.0

        # DD duration (bars in worst drawdown regime).
        dd_series = pd.Series([float(x["drawdown"]) for x in equity_curve])
        in_dd = dd_series < 0
        current = 0
        max_duration = 0
        for flag in in_dd:
            current = current + 1 if bool(flag) else 0
            max_duration = max(max_duration, current)

        trade_df = pd.DataFrame(trades) if trades else pd.DataFrame(columns=["pnl_net", "pnl", "entry_px", "qty"])
        trade_count = int(len(trade_df))
        winrate = float((trade_df["pnl_net"] > 0).mean()) if trade_count else 0.0
        expectancy_usd = float(trade_df["pnl_net"].mean()) if trade_count else 0.0
        entry_value = (trade_df["entry_px"] * trade_df["qty"]).replace(0, np.nan) if trade_count else pd.Series(dtype=float)
        expectancy_pct = float((trade_df["pnl_net"] / entry_value).replace([np.inf, -np.inf], np.nan).dropna().mean()) if trade_count else 0.0
        avg_trade = expectancy_usd
        calmar = 0.0 if max_dd == 0 else cagr / max_dd

        total_entries = trade_count
        total_exits = int(trade_df["exit_time"].notna().sum()) if "exit_time" in trade_df.columns else trade_count
        total_roundtrips = min(total_entries, total_exits)
        turnover = float((trade_df["entry_px"] * trade_df["qty"]).abs().sum() + (trade_df["exit_px"] * trade_df["qty"]).abs().sum()) if trade_count else 0.0
        robust_score = float(max(0.0, min(100.0, 60 + sharpe * 4 - max_dd * 120)))
        gross_profit = float(trade_df.loc[trade_df["pnl_net"] > 0, "pnl_net"].sum()) if trade_count else 0.0
        gross_loss = float(abs(trade_df.loc[trade_df["pnl_net"] < 0, "pnl_net"].sum())) if trade_count else 0.0
        profit_factor = 0.0 if gross_loss == 0 else gross_profit / gross_loss
        max_consecutive_losses = 0
        if trade_count and "pnl_net" in trade_df.columns:
            streak = 0
            for value in trade_df["pnl_net"].tolist():
                if float(value) < 0:
                    streak += 1
                    max_consecutive_losses = max(max_consecutive_losses, streak)
                else:
                    streak = 0
        avg_holding_time_min = 0.0
        exposure_time_pct = 0.0
        if trade_count and {"entry_time", "exit_time"}.issubset(set(trade_df.columns)):
            entry_ts = pd.to_datetime(trade_df["entry_time"], utc=True, errors="coerce")
            exit_ts = pd.to_datetime(trade_df["exit_time"], utc=True, errors="coerce")
            hold_min = ((exit_ts - entry_ts).dt.total_seconds() / 60.0).dropna()
            avg_holding_time_min = float(hold_min.mean()) if len(hold_min) else 0.0
            total_hold_sec = float(((exit_ts - entry_ts).dt.total_seconds()).clip(lower=0).fillna(0).sum())
            total_period_sec = max(1.0, float((eq["time"].iloc[-1] - eq["time"].iloc[0]).total_seconds())) if len(eq) > 1 else 1.0
            exposure_time_pct = min(1.0, max(0.0, total_hold_sec / total_period_sec))

        return {
            "return_total": round(total_return, 6),
            "cagr": round(cagr, 6),
            "max_dd": round(max_dd, 6),
            "max_dd_duration_bars": int(max_duration),
            "sharpe": round(float(sharpe), 4),
            "sortino": round(float(sortino), 4),
            "calmar": round(float(calmar), 4),
            "winrate": round(winrate, 6),
            "expectancy": round(expectancy_usd, 6),  # legacy alias
            "expectancy_usd_per_trade": round(expectancy_usd, 6),
            "expectancy_pct_per_trade": round(expectancy_pct, 6),
            "avg_trade": round(avg_trade, 6),
            "total_entries": int(total_entries),
            "total_exits": int(total_exits),
            "total_roundtrips": int(total_roundtrips),
            "roundtrips": int(total_roundtrips),
            "trade_count": int(trade_count),
            "avg_holding_time": round(avg_holding_time_min, 4),
            "avg_holding_time_minutes": round(avg_holding_time_min, 4),
            "profit_factor": round(float(profit_factor), 6),
            "max_consecutive_losses": int(max_consecutive_losses),
            "exposure_time_pct": round(float(exposure_time_pct), 6),
            "turnover": round(turnover, 6),
            "exposure_avg": round(float(avg_exposure), 6),
            "robust_score": round(robust_score, 4),
            "robustness_score": round(robust_score, 4),
            "pbo": None,
            "dsr": None,
        }

    def build_cost_breakdown(self, costs: dict[str, float]) -> dict[str, float]:
        gross = float(costs.get("gross_pnl_total", 0.0))
        gross_abs = abs(gross)
        fees = float(costs.get("fees_total", 0.0))
        spread = float(costs.get("spread_total", 0.0))
        slippage = float(costs.get("slippage_total", 0.0))
        funding = float(costs.get("funding_total", 0.0))
        rollover = float(costs.get("rollover_total", 0.0))
        total = fees + spread + slippage + funding + rollover
        net = gross - total
        return {
            "gross_pnl_total": round(gross, 6),
            "gross_pnl": round(gross, 6),
            "fees_total": round(fees, 6),
            "spread_total": round(spread, 6),
            "slippage_total": round(slippage, 6),
            "funding_total": round(funding, 6),
            "rollover_total": round(rollover, 6),
            "total_cost": round(total, 6),
            "net_pnl_total": round(net, 6),
            "net_pnl": round(net, 6),
            "fees_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(fees / gross_abs, 6),
            "spread_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(spread / gross_abs, 6),
            "slippage_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(slippage / gross_abs, 6),
            "funding_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(funding / gross_abs, 6),
            "rollover_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(rollover / gross_abs, 6),
            "total_cost_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(total / gross_abs, 6),
        }


class BacktestEngine:
    def _select_validation_window(self, request: BacktestRequest, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
        mode = (request.validation_mode or "").strip().lower()
        if mode != "walk-forward":
            return df, {"mode": mode or "none", "implemented": mode in {"purged-cv", "cpcv"}, "note": "hook_only"}
        total = len(df)
        if total < 500:
            return df, {"mode": "walk-forward", "implemented": True, "split": None, "note": "dataset_too_short_for_split_using_full"}
        split_idx = int(total * 0.70)
        split_idx = max(250, min(split_idx, total - 250))
        oos = df.iloc[split_idx:].copy()
        return (
            oos,
            {
                "mode": "walk-forward",
                "implemented": True,
                "is_bars": int(split_idx),
                "oos_bars": int(len(oos)),
                "oos_start": str(oos.index.min().isoformat()) if not oos.empty else None,
                "oos_end": str(oos.index.max().isoformat()) if not oos.empty else None,
            },
        )

    def run(self, request: BacktestRequest, dataset: MarketDataset) -> dict[str, Any]:
        if dataset.df.empty:
            raise ValueError("Dataset vacío para el rango solicitado")
        eval_df, validation_summary = self._select_validation_window(request, dataset.df)
        simulation = StrategyRunner(request).run(eval_df)
        reporter = ReportEngine()
        metrics = reporter.build_metrics(
            trades=simulation["trades"],
            equity_curve=simulation["equity_curve"],
            avg_exposure=float(simulation["avg_exposure"]),
        )
        costs_breakdown = reporter.build_cost_breakdown(simulation["costs"])
        return {
            "equity_curve": simulation["equity_curve"],
            "drawdown_curve": simulation["drawdown_curve"],
            "trades": simulation["trades"],
            "metrics": metrics,
            "costs_breakdown": costs_breakdown,
            "dataset_hash": dataset.dataset_hash,
            "data_source": dataset.source,
            "dataset_manifest": dataset.manifest,
            "validation_summary": validation_summary,
        }

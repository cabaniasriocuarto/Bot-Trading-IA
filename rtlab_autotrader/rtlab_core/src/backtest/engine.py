from __future__ import annotations

import itertools
from dataclasses import dataclass
from math import sqrt
import re
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
    use_orderflow_data: bool = True
    strict_strategy_id: bool = False
    purge_bars: int | None = None
    embargo_bars: int | None = None
    cpcv_n_splits: int | None = None
    cpcv_k_test_groups: int | None = None
    cpcv_max_paths: int | None = None


@dataclass(slots=True)
class MarketDataset:
    market: str
    symbol: str
    timeframe: str
    source: str
    dataset_hash: str
    df: pd.DataFrame
    manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    stop_atr_mult: float
    take_atr_mult: float
    trail_activate_atr_mult: float
    trail_distance_atr_mult: float
    time_stop_bars: int
    trailing_enabled: bool = True
    use_ema20_take_profit: bool = False


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
        self._strategy_id = str(request.strategy_id or "").strip().lower()
        self._strict_strategy_id = bool(getattr(request, "strict_strategy_id", False))
        self.fee_bps = float(fee_bps if fee_bps is not None else (request.costs.taker_fee_bps or request.costs.fees_bps))
        self._family, self._strategy_supported = self._resolve_strategy_family()
        self._fallback_profile_family = "trend_pullback"
        self._profiles: dict[str, ExecutionProfile] = {
            "trend_pullback": ExecutionProfile(
                stop_atr_mult=2.0,
                take_atr_mult=3.0,
                trail_activate_atr_mult=1.5,
                trail_distance_atr_mult=2.0,
                time_stop_bars=20,
                trailing_enabled=True,
            ),
            "breakout": ExecutionProfile(
                stop_atr_mult=1.8,
                take_atr_mult=3.2,
                trail_activate_atr_mult=1.2,
                trail_distance_atr_mult=1.8,
                time_stop_bars=16,
                trailing_enabled=True,
            ),
            "meanreversion": ExecutionProfile(
                stop_atr_mult=1.4,
                take_atr_mult=1.6,
                trail_activate_atr_mult=0.0,
                trail_distance_atr_mult=0.0,
                time_stop_bars=10,
                trailing_enabled=False,
                use_ema20_take_profit=True,
            ),
            "defensive": ExecutionProfile(
                stop_atr_mult=2.2,
                take_atr_mult=2.8,
                trail_activate_atr_mult=1.0,
                trail_distance_atr_mult=1.8,
                time_stop_bars=18,
                trailing_enabled=True,
            ),
            # Trend-scanning hereda del sub-setup segun regimen en cada entrada.
            "trend_scanning": ExecutionProfile(
                stop_atr_mult=2.0,
                take_atr_mult=3.0,
                trail_activate_atr_mult=1.5,
                trail_distance_atr_mult=2.0,
                time_stop_bars=20,
                trailing_enabled=True,
            ),
        }
        if self._strict_strategy_id and not self._strategy_supported:
            raise ValueError(
                f"strategy_id='{self.request.strategy_id}' no soportado por BacktestEngine en modo estricto. "
                "Permitidos: trend_pullback, breakout, meanreversion, trend_scanning, defensive."
            )

    def _has_fields(self, prev: pd.Series, fields: tuple[str, ...]) -> bool:
        return not any(pd.isna(prev.get(col)) for col in fields)

    def _resolve_strategy_family(self) -> tuple[str, bool]:
        sid = self._strategy_id
        if sid in {"breakout_volatility_v2"} or "breakout" in sid:
            return "breakout", True
        if sid in {"meanreversion_range_v2"} or "meanreversion" in sid or "mean_reversion" in sid:
            return "meanreversion", True
        if sid in {"trend_scanning_regime_v2"} or "trend_scanning" in sid:
            return "trend_scanning", True
        if sid in {"defensive_liquidity_v2"} or "defensive" in sid or "liquidity" in sid:
            return "defensive", True
        if sid in {"trend_pullback_orderflow_v2", "trend_pullback_orderflow_confirm_v1"} or "trend_pullback" in sid:
            return "trend_pullback", True
        return "trend_pullback", False

    def _execution_profile(self, family: str | None = None) -> ExecutionProfile:
        key = str(family or "").strip().lower()
        if key in self._profiles:
            return self._profiles[key]
        return self._profiles[self._fallback_profile_family]

    def _signal_trend_pullback(self, prev: pd.Series) -> str | None:
        if not self._has_fields(prev, ("ema20", "ema50", "ema200", "adx14", "rsi14", "atr14", "prev_high", "prev_low")):
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

    def _signal_breakout_volatility(self, prev: pd.Series) -> str | None:
        if not self._has_fields(prev, ("close", "high", "low", "prev_high", "prev_low", "atr14")):
            return None
        atr = float(prev["atr14"])
        if atr <= 0:
            return None
        range_expansion = (float(prev["high"]) - float(prev["low"])) >= (1.1 * atr)
        if not range_expansion:
            return None
        if float(prev["close"]) > float(prev["prev_high"]):
            return "long"
        if float(prev["close"]) < float(prev["prev_low"]):
            return "short"
        return None

    def _signal_meanreversion_range(self, prev: pd.Series) -> str | None:
        if not self._has_fields(prev, ("close", "ema20", "rsi14", "atr14", "adx14")):
            return None
        adx = float(prev["adx14"])
        if adx > 18.0:
            return None
        close = float(prev["close"])
        ema20 = float(prev["ema20"])
        atr = max(float(prev["atr14"]), 0.0001)
        dist = close - ema20
        if float(prev["rsi14"]) <= 30.0 and dist <= (-0.6 * atr):
            return "long"
        if float(prev["rsi14"]) >= 70.0 and dist >= (0.6 * atr):
            return "short"
        return None

    def _signal_defensive_liquidity(self, prev: pd.Series) -> str | None:
        if not self._has_fields(prev, ("close", "ema50", "rsi14", "adx14")):
            return None
        close = float(prev["close"])
        ema50 = float(prev["ema50"])
        adx = float(prev["adx14"])
        rsi = float(prev["rsi14"])
        obi = prev.get("obi_topn")
        obi_gate = None if pd.isna(obi) else float(obi)
        long_ok = close > ema50 and adx >= 12.0 and 45.0 <= rsi <= 65.0 and (obi_gate is None or obi_gate >= 0.55)
        short_ok = close < ema50 and adx >= 12.0 and 35.0 <= rsi <= 55.0 and (obi_gate is None or obi_gate <= 0.45)
        if long_ok:
            return "long"
        if short_ok:
            return "short"
        return None

    def _signal_trend_scanning_regime(self, prev: pd.Series) -> str | None:
        signal, _signal_family = self._signal_trend_scanning_with_family(prev)
        return signal

    def _signal_trend_scanning_with_family(self, prev: pd.Series) -> tuple[str | None, str]:
        if not self._has_fields(prev, ("close", "adx14", "atr14")):
            return None, "trend_pullback"
        close = max(float(prev["close"]), 0.0001)
        atr = float(prev["atr14"])
        adx = float(prev["adx14"])
        high_vol = atr >= (close * 0.01)
        if high_vol:
            breakout = self._signal_breakout_volatility(prev)
            if breakout is not None:
                return breakout, "breakout"
        if adx >= 20.0:
            return self._signal_trend_pullback(prev), "trend_pullback"
        if adx <= 18.0:
            return self._signal_meanreversion_range(prev), "meanreversion"
        return None, "trend_pullback"

    def _signal(self, prev: pd.Series) -> str | None:
        signal, _family = self._signal_with_family(prev)
        return signal

    def _signal_with_family(self, prev: pd.Series) -> tuple[str | None, str]:
        family = self._family
        if family == "breakout":
            return self._signal_breakout_volatility(prev), "breakout"
        if family == "meanreversion":
            return self._signal_meanreversion_range(prev), "meanreversion"
        if family == "trend_scanning":
            return self._signal_trend_scanning_with_family(prev)
        if family == "defensive":
            return self._signal_defensive_liquidity(prev), "defensive"
        return self._signal_trend_pullback(prev), "trend_pullback"

    def run(self, df: pd.DataFrame) -> dict[str, Any]:
        cost_model = CostModel(self.request.market, self.request.costs)
        simulator = ExecutionSimulator(cost_model)
        portfolio = PortfolioEngine(10000.0)

        trades: list[dict[str, Any]] = []
        position: dict[str, Any] | None = None
        pending_entry: str | None = None
        pending_profile_family = self._fallback_profile_family
        pending_profile: ExecutionProfile | None = None
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
                profile = pending_profile or self._execution_profile(pending_profile_family)
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
                    "strategy_family": pending_profile_family,
                    "stop_atr_mult": float(profile.stop_atr_mult),
                    "take_atr_mult": float(profile.take_atr_mult),
                    "trail_activate_atr_mult": float(profile.trail_activate_atr_mult),
                    "trail_distance_atr_mult": float(profile.trail_distance_atr_mult),
                    "time_stop_bars": int(profile.time_stop_bars),
                    "trailing_enabled": bool(profile.trailing_enabled),
                    "use_ema20_take_profit": bool(profile.use_ema20_take_profit),
                    "stop_px": entry_px - float(profile.stop_atr_mult) * atr if side == "long" else entry_px + float(profile.stop_atr_mult) * atr,
                    "take_px": entry_px + float(profile.take_atr_mult) * atr if side == "long" else entry_px - float(profile.take_atr_mult) * atr,
                    "trail_active": False,
                    "trail_px": None,
                    "bars_open": 0,
                }
                pending_entry = None
                pending_profile = None

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
                trail_enabled = bool(position.get("trailing_enabled", True))
                trail_activate_mult = max(0.0, float(position.get("trail_activate_atr_mult") or 0.0))
                trail_distance_mult = max(0.0, float(position.get("trail_distance_atr_mult") or 0.0))
                if trail_enabled and not position["trail_active"]:
                    if side == "long" and float(bar["high"]) >= float(position["entry_px"]) + trail_activate_mult * atr:
                        position["trail_active"] = True
                    if side == "short" and float(bar["low"]) <= float(position["entry_px"]) - trail_activate_mult * atr:
                        position["trail_active"] = True
                if trail_enabled and position["trail_active"]:
                    if side == "long":
                        candidate = float(bar["close"]) - trail_distance_mult * atr
                        position["trail_px"] = max(float(position.get("trail_px") or position["stop_px"]), candidate)
                    else:
                        candidate = float(bar["close"]) + trail_distance_mult * atr
                        position["trail_px"] = min(float(position.get("trail_px") or position["stop_px"]), candidate)

                stop_px = float(position["trail_px"] if position.get("trail_px") is not None else position["stop_px"])
                take_px = float(position["take_px"])
                exit_reason: str | None = None
                exit_px: float | None = None
                bar_open = float(bar["open"])
                if side == "long":
                    if float(bar["low"]) <= stop_px:
                        exit_reason = "sl"
                        # Gap-pessimistic: if bar opens below stop, fill at open (worse than stop)
                        exit_px = min(stop_px, bar_open)
                    elif float(bar["high"]) >= take_px:
                        exit_reason, exit_px = "tp", take_px
                else:
                    if float(bar["high"]) >= stop_px:
                        exit_reason = "sl"
                        # Gap-pessimistic: if bar opens above stop, fill at open (worse than stop)
                        exit_px = max(stop_px, bar_open)
                    elif float(bar["low"]) <= take_px:
                        exit_reason, exit_px = "tp", take_px

                if exit_reason is None and bool(position.get("use_ema20_take_profit", False)):
                    # Use previous bar's EMA to avoid look-ahead bias (signal on bar i-1, fill on bar i)
                    _prev_bar = rows[i - 1][1] if i > 0 else bar
                    ema20 = _prev_bar.get("ema20")
                    if ema20 is not None and not pd.isna(ema20):
                        ema_target = float(ema20)
                        if side == "long" and float(bar["high"]) >= ema_target:
                            exit_reason, exit_px = "tp_ema20", ema_target
                        elif side == "short" and float(bar["low"]) <= ema_target:
                            exit_reason, exit_px = "tp_ema20", ema_target

                if exit_reason is None and int(position["bars_open"]) >= int(position.get("time_stop_bars") or 12):
                    exit_reason, exit_px = "time", float(bar["close"])

                if exit_reason and exit_px is not None:
                    # ERR-005: Exits (SL/TP/time/EMA) are stop/limit-type fills at exit_px.
                    # market_fill would displace fill_px by spread/slippage AND produce
                    # spread_cost/slippage_cost records — double-counting the same cost.
                    # Fix: apply costs at exit_px without price displacement.
                    realized_exit_px = exit_px
                    _exit_spread_bps = simulator.cost_model.spread_bps_for_bar(bar)
                    _exit_slip_bps = float(simulator.cost_model.costs.slippage_bps)
                    _exit_fees, _exit_spread_cost, _exit_slip_cost = simulator.cost_model.apply_fill_costs(
                        realized_exit_px, qty, self.fee_bps, _exit_spread_bps / 2.0, _exit_slip_bps
                    )
                    if side == "long":
                        gross = (realized_exit_px - float(position["entry_px"])) * qty
                    else:
                        gross = (float(position["entry_px"]) - realized_exit_px) * qty
                    hold_minutes = max(1.0, (ts - position["entry_ts"]).total_seconds() / 60.0)
                    avg_notional = (abs(float(position["entry_px"]) * qty) + abs(realized_exit_px * qty)) / 2.0
                    funding = avg_notional * (self.request.costs.funding_bps / 10000.0) * (hold_minutes / 480.0)
                    rollover = avg_notional * (self.request.costs.rollover_bps / 10000.0) * (hold_minutes / (24 * 60))
                    fee_total = float(position["entry_fees"]) + _exit_fees
                    spread_total = float(position["entry_spread_cost"]) + _exit_spread_cost
                    slippage_total = float(position["entry_slippage_cost"]) + _exit_slip_cost
                    cost_total = fee_total + spread_total + slippage_total + funding + rollover
                    net = gross - cost_total

                    # ERR-002: MAE/MFE from actual bar extremes during holding period,
                    # not fake 0.6x/1.1x gross multipliers.
                    _entry_idx = int(position["entry_index"])
                    _entry_px = float(position["entry_px"])
                    _hold_bars = rows[_entry_idx : i + 1]
                    _hold_lows = [float(r[1]["low"]) for r in _hold_bars]
                    _hold_highs = [float(r[1]["high"]) for r in _hold_bars]
                    if side == "long":
                        _mae = max(0.0, _entry_px - min(_hold_lows)) * qty
                        _mfe = max(0.0, max(_hold_highs) - _entry_px) * qty
                    else:
                        _mae = max(0.0, max(_hold_highs) - _entry_px) * qty
                        _mfe = max(0.0, _entry_px - min(_hold_lows)) * qty

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
                            "mae": round(_mae, 6),
                            "mfe": round(_mfe, 6),
                            "reason_code": str(position.get("strategy_family") or self._family),
                            "exit_reason": exit_reason,
                            "events": [
                                {"ts": position["entry_ts"].isoformat(), "type": "fill", "detail": "Entrada market simulada"},
                                {"ts": ts.isoformat(), "type": "exit", "detail": f"Salida {exit_reason}"},
                            ],
                            "explain": {
                                "whitelist_ok": True,
                                "trend_ok": True,
                                "pullback_ok": True,
                                "orderflow_ok": bool(self.request.use_orderflow_data and self.request.market != "equities"),
                                "vpin_ok": bool(self.request.use_orderflow_data and self.request.market != "equities"),
                                "spread_ok": True,
                            },
                        }
                    )
                    position = None
                    unrealized = 0.0

            if i > 0 and position is None:
                prev = rows[i - 1][1]
                pending_entry, pending_profile_family = self._signal_with_family(prev)
                pending_profile = self._execution_profile(pending_profile_family) if pending_entry else None

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
    @staticmethod
    def _periods_per_year(timeframe: str) -> float:
        tf = str(timeframe or "").strip().lower()
        known = {
            "1m": 365 * 24 * 60,
            "5m": 365 * 24 * 12,
            "10m": 365 * 24 * 6,
            "15m": 365 * 24 * 4,
            "1h": 365 * 24,
            "1d": 365,
        }
        if tf in known:
            return float(known[tf])
        match = re.fullmatch(r"(\d+)([mhd])", tf)
        if not match:
            return float(known["5m"])
        value = max(1, int(match.group(1)))
        unit = match.group(2)
        if unit == "m":
            periods_per_day = (24 * 60) / value
        elif unit == "h":
            periods_per_day = 24 / value
        else:
            periods_per_day = 1 / value
        return float(365 * periods_per_day)

    def build_metrics(
        self,
        *,
        trades: list[dict[str, Any]],
        equity_curve: list[dict[str, Any]],
        avg_exposure: float,
        timeframe: str,
    ) -> dict[str, Any]:
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
        annualization = sqrt(self._periods_per_year(timeframe))
        sharpe = 0.0 if std_r == 0 else (mean_r / std_r) * annualization
        sortino = 0.0 if downside_std == 0 else (mean_r / downside_std) * annualization

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
    def _resolve_purge_embargo(self, request: BacktestRequest, total: int) -> tuple[int, int]:
        purge_default = max(5, int(total * 0.02))
        embargo_default = max(5, int(total * 0.01))
        purge = int(request.purge_bars if isinstance(request.purge_bars, int) else purge_default)
        embargo = int(request.embargo_bars if isinstance(request.embargo_bars, int) else embargo_default)
        return max(0, purge), max(0, embargo)

    def _select_purged_cv_window(self, request: BacktestRequest, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
        total = len(df)
        min_train_bars = 250
        min_oos_bars = 250
        if total < (min_train_bars + min_oos_bars):
            raise ValueError(
                "validation_mode='purged-cv' requiere al menos 500 velas para respetar train/oos minimos."
            )

        split_idx = int(total * 0.70)
        split_idx = max(min_train_bars, min(split_idx, total - min_oos_bars))
        purge_bars, embargo_bars = self._resolve_purge_embargo(request, total)

        max_purge = max(0, split_idx - min_train_bars)
        max_embargo = max(0, (total - split_idx) - min_oos_bars)
        effective_purge = min(purge_bars, max_purge)
        effective_embargo = min(embargo_bars, max_embargo)

        train_end_exclusive = split_idx - effective_purge
        oos_start = split_idx + effective_embargo
        oos = df.iloc[oos_start:].copy()
        if len(oos) < min_oos_bars:
            raise ValueError(
                "validation_mode='purged-cv' no pudo reservar OOS minimo tras aplicar purge/embargo."
            )
        if train_end_exclusive < min_train_bars:
            raise ValueError(
                "validation_mode='purged-cv' no pudo reservar train minimo tras aplicar purge/embargo."
            )
        return (
            oos,
            {
                "mode": "purged-cv",
                "implemented": True,
                "folds": 1,
                "split_bars": int(split_idx),
                "is_bars": int(train_end_exclusive),
                "purge_bars": int(effective_purge),
                "embargo_bars": int(effective_embargo),
                "oos_bars": int(len(oos)),
                "train_end_exclusive": str(df.index[train_end_exclusive - 1].isoformat()) if train_end_exclusive > 0 else None,
                "oos_start": str(oos.index.min().isoformat()) if not oos.empty else None,
                "oos_end": str(oos.index.max().isoformat()) if not oos.empty else None,
                "note": "single_split_purged_holdout",
            },
        )

    def _resolve_cpcv_config(self, request: BacktestRequest) -> tuple[int, int, int]:
        n_splits = int(request.cpcv_n_splits if isinstance(request.cpcv_n_splits, int) else 6)
        k_test_groups = int(request.cpcv_k_test_groups if isinstance(request.cpcv_k_test_groups, int) else 2)
        max_paths = int(request.cpcv_max_paths if isinstance(request.cpcv_max_paths, int) else 8)
        n_splits = max(4, min(n_splits, 12))
        k_test_groups = max(1, min(k_test_groups, n_splits - 1))
        max_paths = max(1, min(max_paths, 32))
        return n_splits, k_test_groups, max_paths

    def _build_cpcv_paths(self, request: BacktestRequest, df: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        total = len(df)
        min_total_bars = 1000
        if total < min_total_bars:
            raise ValueError("validation_mode='cpcv' requiere al menos 1000 velas para generar paths robustos.")
        n_splits, k_test_groups, max_paths = self._resolve_cpcv_config(request)
        purge_bars, embargo_bars = self._resolve_purge_embargo(request, total)
        trim_bars = purge_bars + embargo_bars
        bounds = np.linspace(0, total, n_splits + 1, dtype=int)
        groups: list[tuple[int, int]] = []
        for idx in range(n_splits):
            start = int(bounds[idx])
            end = int(bounds[idx + 1])
            if end <= start:
                continue
            groups.append((start, end))
        if len(groups) < 4:
            raise ValueError("validation_mode='cpcv' no pudo construir grupos temporales suficientes.")

        combos = list(itertools.combinations(range(len(groups)), k_test_groups))
        if not combos:
            raise ValueError("validation_mode='cpcv' sin combinaciones validas para grupos de test.")

        min_path_bars = 250
        valid_paths: list[dict[str, Any]] = []
        for combo in combos:
            segments: list[tuple[int, int]] = []
            combo_raw_bars = 0
            for group_idx in combo:
                g_start, g_end = groups[group_idx]
                combo_raw_bars += int(g_end - g_start)
                seg_start = min(g_end, g_start + trim_bars)
                seg_end = max(seg_start, g_end - trim_bars)
                if seg_end <= seg_start:
                    continue
                segments.append((seg_start, seg_end))
            if not segments:
                continue
            parts = [df.iloc[s:e].copy() for s, e in segments if e > s]
            if not parts:
                continue
            path_df = pd.concat(parts, axis=0).sort_index()
            if len(path_df) < min_path_bars:
                continue
            valid_paths.append(
                {
                    "combo": [int(x) for x in combo],
                    "segments": [{"start_idx": int(s), "end_idx_exclusive": int(e)} for s, e in segments],
                    "raw_bars": int(combo_raw_bars),
                    "bars": int(len(path_df)),
                    "df": path_df,
                }
            )
            if len(valid_paths) >= max_paths:
                break

        if not valid_paths:
            raise ValueError(
                "validation_mode='cpcv' no pudo generar paths validos con los parametros actuales (n_splits/k_test_groups/purge/embargo)."
            )
        summary_base = {
            "mode": "cpcv",
            "implemented": True,
            "n_splits": int(n_splits),
            "k_test_groups": int(k_test_groups),
            "max_paths": int(max_paths),
            "purge_bars": int(purge_bars),
            "embargo_bars": int(embargo_bars),
            "trim_bars": int(trim_bars),
            "dataset_bars": int(total),
        }
        return valid_paths, summary_base

    def _run_cpcv(self, request: BacktestRequest, df: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
        paths, summary_base = self._build_cpcv_paths(request, df)
        reporter = ReportEngine()
        runner = StrategyRunner(request)
        merged_trades: list[dict[str, Any]] = []
        merged_equity: list[dict[str, Any]] = []
        merged_drawdown: list[dict[str, Any]] = []
        current_equity = 10000.0
        max_equity = current_equity
        total_costs = {
            "gross_pnl_total": 0.0,
            "fees_total": 0.0,
            "spread_total": 0.0,
            "slippage_total": 0.0,
            "funding_total": 0.0,
            "rollover_total": 0.0,
        }
        avg_exposure_values: list[float] = []
        path_summaries: list[dict[str, Any]] = []

        for path_idx, path in enumerate(paths, start=1):
            path_df = path.get("df")
            if not isinstance(path_df, pd.DataFrame) or path_df.empty:
                continue
            simulation = runner.run(path_df)
            avg_exposure_values.append(float(simulation.get("avg_exposure", 0.0)))
            path_curve = simulation.get("equity_curve") or []
            if not path_curve:
                continue

            curve_start_equity = float(path_curve[0].get("equity", 10000.0))
            curve_offset = current_equity - curve_start_equity
            for point in path_curve:
                ts = str(point.get("time") or "")
                eq = float(point.get("equity", current_equity)) + curve_offset
                max_equity = max(max_equity, eq)
                dd = 0.0 if max_equity <= 0 else (eq - max_equity) / max_equity
                merged_equity.append({"time": ts, "equity": round(eq, 4), "drawdown": round(float(dd), 6)})
                merged_drawdown.append({"time": ts, "value": round(float(dd), 6)})
            current_equity = float(merged_equity[-1]["equity"])

            for trade in simulation.get("trades", []) or []:
                if not isinstance(trade, dict):
                    continue
                row = dict(trade)
                row["cpcv_path_id"] = int(path_idx)
                merged_trades.append(row)

            costs = simulation.get("costs") if isinstance(simulation.get("costs"), dict) else {}
            for key in total_costs:
                total_costs[key] += float(costs.get(key, 0.0))

            path_metrics = reporter.build_metrics(
                trades=simulation.get("trades") if isinstance(simulation.get("trades"), list) else [],
                equity_curve=path_curve if isinstance(path_curve, list) else [],
                avg_exposure=float(simulation.get("avg_exposure", 0.0)),
                timeframe=request.timeframe,
            )
            path_summaries.append(
                {
                    "path_id": int(path_idx),
                    "combo": path.get("combo") if isinstance(path.get("combo"), list) else [],
                    "bars": int(path.get("bars") or len(path_df)),
                    "raw_bars": int(path.get("raw_bars") or 0),
                    "trades": int(path_metrics.get("trade_count", 0)),
                    "return_total": float(path_metrics.get("return_total", 0.0)),
                }
            )

        if not merged_equity:
            raise ValueError("validation_mode='cpcv' no produjo curvas de equity validas.")

        summary = {
            **summary_base,
            "paths_evaluated": int(len(path_summaries)),
            "path_bars_total": int(sum(int(row.get("bars", 0)) for row in path_summaries)),
            "oos_bars": int(sum(int(row.get("bars", 0)) for row in path_summaries)),
            "path_summaries": path_summaries,
            "note": "combinatorial_purged_cross_validation",
        }
        simulation_merged = {
            "equity_curve": merged_equity,
            "drawdown_curve": merged_drawdown,
            "trades": merged_trades,
            "costs": total_costs,
            "avg_exposure": float(sum(avg_exposure_values) / max(1, len(avg_exposure_values))),
        }
        return simulation_merged, summary

    def _select_validation_window(self, request: BacktestRequest, df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
        mode = (request.validation_mode or "").strip().lower()
        if mode == "cpcv":
            raise ValueError(
                "validation_mode='cpcv' requiere ejecucion por paths y se resuelve en BacktestEngine.run()."
            )
        if mode == "purged-cv":
            return self._select_purged_cv_window(request, df)
        if mode != "walk-forward":
            return df, {"mode": mode or "none", "implemented": False, "note": "unsupported_using_full_dataset"}
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
        if not dataset.dataset_hash:
            raise ValueError("Dataset sin hash de integridad — no se puede ejecutar un backtest sin identificador reproducible")
        mode = (request.validation_mode or "").strip().lower()
        if mode == "cpcv":
            simulation, validation_summary = self._run_cpcv(request, dataset.df)
        else:
            eval_df, validation_summary = self._select_validation_window(request, dataset.df)
            simulation = StrategyRunner(request).run(eval_df)
        reporter = ReportEngine()
        metrics = reporter.build_metrics(
            trades=simulation["trades"],
            equity_curve=simulation["equity_curve"],
            avg_exposure=float(simulation["avg_exposure"]),
            timeframe=request.timeframe,
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

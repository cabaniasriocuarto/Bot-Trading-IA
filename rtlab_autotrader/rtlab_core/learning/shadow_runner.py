from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from rtlab_core.data.marketdata import resample_ohlcv
from rtlab_core.src.backtest.engine import BacktestCosts, BacktestEngine, BacktestRequest, MarketDataset

BINANCE_PUBLIC_MARKETDATA_BASE_URL = "https://api.binance.com"
SUPPORTED_SHADOW_TIMEFRAMES = {"5m", "10m", "15m"}


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").replace("/", "").replace("-", "").strip().upper()


def _binance_interval(timeframe: str) -> str:
    tf = str(timeframe or "5m").strip().lower()
    if tf == "10m":
        return "5m"
    if tf in {"5m", "15m"}:
        return tf
    raise ValueError(f"timeframe no soportado para shadow: {timeframe}")


@dataclass(slots=True)
class ShadowRunConfig:
    strategy_id: str
    symbol: str
    timeframe: str = "5m"
    market: str = "crypto"
    lookback_bars: int = 300
    use_orderflow_data: bool = True
    validation_mode: str = "shadow_live"
    costs: BacktestCosts = field(
        default_factory=lambda: BacktestCosts(
            fees_bps=5.5,
            spread_bps=4.0,
            slippage_bps=3.0,
            funding_bps=1.0,
            rollover_bps=0.0,
        )
    )


class ShadowRunner:
    def __init__(
        self,
        *,
        marketdata_base_url: str = BINANCE_PUBLIC_MARKETDATA_BASE_URL,
        timeout_sec: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.marketdata_base_url = str(marketdata_base_url or BINANCE_PUBLIC_MARKETDATA_BASE_URL).rstrip("/")
        self.timeout_sec = max(3.0, float(timeout_sec))
        self.session = session or requests.Session()
        self.engine = BacktestEngine()

    def _klines_url(self) -> str:
        return f"{self.marketdata_base_url}/api/v3/klines"

    def _book_ticker_url(self) -> str:
        return f"{self.marketdata_base_url}/api/v3/ticker/bookTicker"

    def _fetch_klines(self, *, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        response = self.session.get(
            self._klines_url(),
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list) or not payload:
            raise ValueError("Binance public klines devolvio vacio para shadow.")
        rows: list[dict[str, Any]] = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 6:
                continue
            rows.append(
                {
                    "timestamp": pd.to_datetime(int(row[0]), unit="ms", utc=True),
                    "open": _to_float(row[1]),
                    "high": _to_float(row[2]),
                    "low": _to_float(row[3]),
                    "close": _to_float(row[4]),
                    "volume": _to_float(row[5]),
                }
            )
        frame = pd.DataFrame(rows)
        if frame.empty:
            raise ValueError("No se pudo construir OHLCV shadow desde Binance public.")
        return frame.set_index("timestamp").sort_index()

    def _fetch_spread_bps(self, *, symbol: str) -> float | None:
        try:
            response = self.session.get(
                self._book_ticker_url(),
                params={"symbol": symbol},
                timeout=self.timeout_sec,
            )
            response.raise_for_status()
            payload = response.json()
            bid = _to_float((payload or {}).get("bidPrice"), 0.0)
            ask = _to_float((payload or {}).get("askPrice"), 0.0)
            if bid <= 0 or ask <= 0 or ask < bid:
                return None
            mid = (bid + ask) / 2.0
            if mid <= 0:
                return None
            return ((ask - bid) / mid) * 10000.0
        except Exception:
            return None

    def build_dataset(self, *, symbol: str, timeframe: str, lookback_bars: int) -> tuple[MarketDataset, dict[str, Any]]:
        tf = str(timeframe or "5m").strip().lower()
        if tf not in SUPPORTED_SHADOW_TIMEFRAMES:
            raise ValueError(f"timeframe no soportado para shadow: {timeframe}")
        symbol_n = _normalize_symbol(symbol)
        base_interval = _binance_interval(tf)
        raw_limit = max(120, int(lookback_bars) * (2 if tf == "10m" else 1) + 10)
        raw = self._fetch_klines(symbol=symbol_n, interval=base_interval, limit=raw_limit)
        if tf == "10m":
            frame = resample_ohlcv(raw.reset_index(), tf)
        else:
            frame = raw
        frame = frame.dropna(how="any")
        frame = frame.tail(max(60, int(lookback_bars)))
        if frame.empty:
            raise ValueError("Dataset shadow vacio despues de filtrar velas.")
        last_closed_ts = frame.index[-1].isoformat()
        first_ts = frame.index[0].isoformat()
        dataset_hash = hashlib.sha256(
            f"shadow|binance_public_klines|{symbol_n}|{tf}|{first_ts}|{last_closed_ts}|{len(frame)}".encode("utf-8")
        ).hexdigest()[:16]
        observed_spread_bps = self._fetch_spread_bps(symbol=symbol_n)
        manifest = {
            "dataset_source": "binance_public_klines",
            "market": "crypto",
            "symbol": symbol_n,
            "timeframe": tf,
            "bars": int(len(frame)),
            "start": first_ts,
            "end": last_closed_ts,
            "fetched_at": _utc_iso(),
            "marketdata_base_url": self.marketdata_base_url,
            "observed_spread_bps": observed_spread_bps,
            "base_interval": base_interval,
            "resampled": bool(tf != base_interval),
        }
        dataset = MarketDataset(
            market="crypto",
            symbol=symbol_n,
            timeframe=tf,
            source="binance_public_klines",
            dataset_hash=dataset_hash,
            df=frame,
            manifest=manifest,
        )
        return dataset, manifest

    def simulate(self, config: ShadowRunConfig) -> dict[str, Any]:
        dataset, manifest = self.build_dataset(
            symbol=config.symbol,
            timeframe=config.timeframe,
            lookback_bars=config.lookback_bars,
        )
        spread_bps = manifest.get("observed_spread_bps")
        costs = BacktestCosts(
            fees_bps=float(config.costs.fees_bps),
            spread_bps=float(spread_bps if isinstance(spread_bps, (int, float)) and spread_bps > 0 else config.costs.spread_bps),
            slippage_bps=float(config.costs.slippage_bps),
            funding_bps=float(config.costs.funding_bps),
            rollover_bps=float(config.costs.rollover_bps),
        )
        result = self.engine.run(
            BacktestRequest(
                market=config.market,
                symbol=dataset.symbol,
                timeframe=dataset.timeframe,
                start=str(manifest.get("start") or ""),
                end=str(manifest.get("end") or ""),
                strategy_id=config.strategy_id,
                validation_mode=config.validation_mode,
                use_orderflow_data=bool(config.use_orderflow_data),
                costs=costs,
            ),
            dataset,
        )
        return {
            "dataset": dataset,
            "manifest": manifest,
            "engine_result": result,
            "costs": {
                "fees_bps": float(costs.fees_bps),
                "spread_bps": float(costs.spread_bps),
                "slippage_bps": float(costs.slippage_bps),
                "funding_bps": float(costs.funding_bps),
                "rollover_bps": float(costs.rollover_bps),
            },
        }

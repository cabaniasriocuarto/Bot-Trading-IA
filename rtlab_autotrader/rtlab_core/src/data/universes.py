from __future__ import annotations

from typing import Final


SUPPORTED_MARKETS: Final[tuple[str, ...]] = ("crypto", "forex", "equities")
SUPPORTED_TIMEFRAMES: Final[tuple[str, ...]] = ("5m", "10m", "15m")

MARKET_UNIVERSES: Final[dict[str, list[str]]] = {
    "crypto": [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT",
    ],
    "forex": [
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "USDCHF",
        "AUDUSD",
        "USDCAD",
        "NZDUSD",
    ],
    "equities": [
        "AAPL",
        "MSFT",
        "AMZN",
        "GOOGL",
        "META",
        "NVDA",
        "TSLA",
    ],
}

DEFAULT_SOURCES: Final[dict[str, str]] = {
    "crypto": "binance_public",
    "forex": "dukascopy",
    "equities": "alpaca",
}


def normalize_market(value: str) -> str:
    market = (value or "").strip().lower()
    if market not in SUPPORTED_MARKETS:
        raise ValueError(f"Unsupported market: {value}")
    return market


def normalize_symbol(value: str) -> str:
    return (value or "").strip().upper().replace("/", "")


def normalize_timeframe(value: str) -> str:
    tf = (value or "").strip().lower()
    if tf not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {value}")
    return tf


def market_symbols(market: str) -> list[str]:
    return list(MARKET_UNIVERSES[normalize_market(market)])


from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Mode(str, Enum):
    BACKTEST = "backtest"
    DRYRUN = "dryrun"
    PAPER = "paper"
    TESTNET = "testnet"
    LIVE = "live"
    CAPTURE_ONLY = "capture_only"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class OrderStatus(str, Enum):
    NEW = "new"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    STALE = "stale"
    REJECTED = "rejected"


@dataclass(slots=True)
class CheckResult:
    ok: bool
    failed_checks: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SignalDecision:
    side: Side
    score: float
    checks: CheckResult


@dataclass(slots=True)
class RiskDecision:
    allow_new_positions: bool
    reason: str | None = None
    safe_mode: bool = False
    kill: bool = False


@dataclass(slots=True)
class HealthMetrics:
    ws_lag_ms: int = 0
    api_errors: int = 0
    desync_count: int = 0
    error_streak: int = 0


@dataclass(slots=True)
class OrderRecord:
    order_id: str
    symbol: str
    side: Side
    quantity: float
    filled_quantity: float
    status: OrderStatus
    price: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestResult:
    strategy: str
    timerange: str
    exchange: str
    pairs: list[str]
    metrics: dict[str, Any]
    artifacts_path: str

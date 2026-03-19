from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import importlib.util
import io
import json
import os
import random
import re
import secrets
import socket
import sqlite3
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, RLock, Thread
from typing import Any, Literal
from urllib.parse import urlencode, urlparse

import requests
import yaml
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from rtlab_core.config import load_config
from rtlab_core.domains import (
    BotDecisionLogRepository,
    BotPolicyStateRepository,
    StrategyEvidenceRepository,
    StrategyTruthRepository,
)
from rtlab_core.backtest import BacktestCatalogDB, CostModelResolver, FundamentalsCreditFilter
from rtlab_core.execution import ExecutionRealityService
from rtlab_core.execution.oms import OMS, Order
from rtlab_core.execution.reconciliation import reconcile_orders
from rtlab_core.instruments import BinanceInstrumentRegistryService
from rtlab_core.learning import LearningService
from rtlab_core.learning.experience_store import ExperienceStore
from rtlab_core.learning.knowledge import KnowledgeLoader
from rtlab_core.learning.option_b_engine import OptionBLearningEngine
from rtlab_core.learning.shadow_runner import BINANCE_PUBLIC_MARKETDATA_BASE_URL, ShadowRunConfig, ShadowRunner
from rtlab_core.mode_taxonomy import GLOBAL_RUNTIME_MODES, mode_taxonomy_payload, normalize_bot_policy_mode, normalize_global_runtime_mode
from rtlab_core.policy_paths import describe_policy_root_resolution, resolve_policy_root
from rtlab_core.reporting import ReportingBridgeService
from rtlab_core.risk.kill_switch import KillSwitch
from rtlab_core.risk.risk_engine import RiskEngine, RiskLimits
from rtlab_core.rollout import CompareEngine, GateEvaluator, RolloutManager
from rtlab_core.runtime_controls import (
    alert_thresholds_policy,
    default_global_runtime_mode as runtime_default_global_mode,
    load_runtime_controls_bundle,
    observability_policy,
)
from rtlab_core.src.backtest.engine import BacktestCosts, BacktestEngine, BacktestRequest, MarketDataset
from rtlab_core.src.data.catalog import DataCatalog
from rtlab_core.src.data.loader import DataLoader
from rtlab_core.src.data.universes import MARKET_UNIVERSES, SUPPORTED_TIMEFRAMES, normalize_market, normalize_symbol, normalize_timeframe
from rtlab_core.src.research import MassBacktestCoordinator, MassBacktestEngine
from rtlab_core.src.reports.reporting import ReportEngine as ArtifactReportEngine
from rtlab_core.strategy_packs.registry_db import RegistryDB
from rtlab_core.types import OrderStatus, Side
from rtlab_core.universe import InstrumentUniverseService

APP_VERSION = "0.1.0"
PROJECT_ROOT = Path(os.getenv("RTLAB_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
MONOREPO_ROOT = (PROJECT_ROOT.parent if (PROJECT_ROOT.parent / "knowledge").exists() else PROJECT_ROOT).resolve()
DEFAULT_CONFIG_POLICIES_ROOT = (MONOREPO_ROOT / "config" / "policies").resolve()
CONFIG_POLICIES_ROOT = resolve_policy_root(MONOREPO_ROOT, explicit=DEFAULT_CONFIG_POLICIES_ROOT)
_OBSERVABILITY_POLICY = observability_policy(repo_root=MONOREPO_ROOT, explicit_root=DEFAULT_CONFIG_POLICIES_ROOT)
_ALERT_THRESHOLDS_POLICY = alert_thresholds_policy(repo_root=MONOREPO_ROOT, explicit_root=DEFAULT_CONFIG_POLICIES_ROOT)
_RUNTIME_TELEMETRY_POLICY = (
    _OBSERVABILITY_POLICY.get("runtime_telemetry")
    if isinstance(_OBSERVABILITY_POLICY.get("runtime_telemetry"), dict)
    else {}
)
_OBSERVABILITY_LOGGING_POLICY = (
    _OBSERVABILITY_POLICY.get("logging")
    if isinstance(_OBSERVABILITY_POLICY.get("logging"), dict)
    else {}
)
_BREAKER_ALERT_THRESHOLDS = (
    _ALERT_THRESHOLDS_POLICY.get("breaker_integrity")
    if isinstance(_ALERT_THRESHOLDS_POLICY.get("breaker_integrity"), dict)
    else {}
)
_OPS_ALERT_THRESHOLDS = (
    _ALERT_THRESHOLDS_POLICY.get("operations")
    if isinstance(_ALERT_THRESHOLDS_POLICY.get("operations"), dict)
    else {}
)
DEFAULT_GLOBAL_RUNTIME_MODE = runtime_default_global_mode(
    repo_root=MONOREPO_ROOT,
    explicit_root=DEFAULT_CONFIG_POLICIES_ROOT,
)


def _resolve_user_data_dir() -> Path:
    explicit = os.getenv("RTLAB_USER_DATA_DIR")
    if explicit:
        return Path(explicit).resolve()

    preferred = (PROJECT_ROOT / "user_data").resolve()
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        test_file = preferred / ".write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        return preferred
    except Exception:
        return Path("/tmp/rtlab_user_data").resolve()


USER_DATA_DIR = _resolve_user_data_dir()


def _path_is_ephemeral_user_data(path: str | Path) -> bool:
    normalized = str(path or "").replace("\\", "/").strip().lower()
    if not normalized:
        return False
    return (
        normalized == "/tmp"
        or normalized.startswith("/tmp/")
        or normalized == "/var/tmp"
        or normalized.startswith("/var/tmp/")
        or normalized == "/dev/shm"
        or normalized.startswith("/dev/shm/")
    )


def _user_data_persistence_status(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path).resolve() if path is not None else USER_DATA_DIR
    explicit_env = bool(str(os.getenv("RTLAB_USER_DATA_DIR", "")).strip())
    ephemeral = _path_is_ephemeral_user_data(target)
    warning = (
        "RTLAB_USER_DATA_DIR apunta a almacenamiento efimero; un redeploy puede resetear bots/runs/logs."
        if ephemeral
        else ""
    )
    return {
        "user_data_dir": str(target),
        "explicit_env": explicit_env,
        "storage_ephemeral": bool(ephemeral),
        "persistent_storage": not bool(ephemeral),
        "warning": warning,
    }


STRATEGY_PACKS_DIR = USER_DATA_DIR / "strategy_packs"
UPLOADS_DIR = STRATEGY_PACKS_DIR / "uploads"
REGISTRY_DB_PATH = STRATEGY_PACKS_DIR / "registry.sqlite3"
CONSOLE_DB_PATH = USER_DATA_DIR / "console_api.sqlite3"
SETTINGS_PATH = USER_DATA_DIR / "console_settings.json"
BOT_STATE_PATH = USER_DATA_DIR / "logs" / "bot_state.json"
STRATEGY_META_PATH = STRATEGY_PACKS_DIR / "strategy_meta.json"
RUNS_PATH = USER_DATA_DIR / "backtests" / "runs.json"
BACKTEST_CATALOG_DB_PATH = USER_DATA_DIR / "backtests" / "catalog.sqlite3"
INSTRUMENT_REGISTRY_DB_PATH = USER_DATA_DIR / "instruments" / "registry.sqlite3"
BOTS_PATH = USER_DATA_DIR / "learning" / "bots.json"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
ALLOWED_ROLES = {ROLE_ADMIN, ROLE_VIEWER}
ALLOWED_MODES = set(GLOBAL_RUNTIME_MODES)
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = ""  # No hay default seguro — configurar ADMIN_PASSWORD en variables de entorno
DEFAULT_VIEWER_USERNAME = "viewer"
DEFAULT_VIEWER_PASSWORD = ""  # No hay default seguro — configurar VIEWER_PASSWORD en variables de entorno
RUNTIME_ENGINE_REAL = "real"
RUNTIME_ENGINE_SIMULATED = "simulated"
RUNTIME_CONTRACT_VERSION = "runtime_snapshot_v1"
RUNTIME_TELEMETRY_SOURCE_SYNTHETIC = str(
    _RUNTIME_TELEMETRY_POLICY["synthetic_source"]
).strip().lower()
RUNTIME_TELEMETRY_SOURCE_REAL = str(
    _RUNTIME_TELEMETRY_POLICY["real_source"]
).strip().lower()
BINANCE_TESTNET_BASE_URL_DEFAULT = "https://testnet.binance.vision"
BINANCE_TESTNET_WS_URL_DEFAULT = "wss://testnet.binance.vision/ws"
BINANCE_LIVE_BASE_URL_DEFAULT = "https://api.binance.com"
BINANCE_LIVE_WS_URL_DEFAULT = "wss://stream.binance.com:9443/ws"
BINANCE_TESTNET_ENV_KEY = "BINANCE_TESTNET_API_KEY"
BINANCE_TESTNET_ENV_SECRET = "BINANCE_TESTNET_API_SECRET"
BINANCE_TESTNET_ENV_BASE = "BINANCE_SPOT_TESTNET_BASE_URL"
BINANCE_TESTNET_ENV_WS = "BINANCE_SPOT_TESTNET_WS_URL"
BINANCE_LIVE_ENV_KEY = "BINANCE_API_KEY"
BINANCE_LIVE_ENV_SECRET = "BINANCE_API_SECRET"
BINANCE_LIVE_ENV_BASE = "BINANCE_SPOT_BASE_URL"
BINANCE_LIVE_ENV_WS = "BINANCE_SPOT_WS_URL"
EXCHANGE_DIAG_CACHE_TTL_SEC = 45


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default))).strip())
    except Exception:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


LOGIN_RATE_LIMIT_ATTEMPTS = _env_int("RATE_LIMIT_LOGIN_ATTEMPTS", 10)
LOGIN_RATE_LIMIT_WINDOW_MIN = _env_int("RATE_LIMIT_LOGIN_WINDOW_MIN", 10)
LOGIN_LOCKOUT_MIN = _env_int("RATE_LIMIT_LOGIN_LOCKOUT_MIN", 30)
LOGIN_LOCKOUT_AFTER_FAILS = _env_int("RATE_LIMIT_LOGIN_LOCKOUT_AFTER_FAILS", 20)
LOGIN_RATE_LIMIT_BACKEND = str(os.getenv("RATE_LIMIT_LOGIN_BACKEND", "sqlite")).strip().lower()
LOGIN_RATE_LIMIT_SQLITE_PATH = Path(
    str(os.getenv("RATE_LIMIT_LOGIN_SQLITE_PATH", "")).strip() or str(CONSOLE_DB_PATH)
).resolve()
API_RATE_LIMIT_ENABLED = _env_bool("RATE_LIMIT_GENERAL_ENABLED", True)
API_RATE_LIMIT_GENERAL_PER_MIN = max(1, _env_int("RATE_LIMIT_GENERAL_REQ_PER_MIN", 60))
API_RATE_LIMIT_EXPENSIVE_PER_MIN = max(1, _env_int("RATE_LIMIT_EXPENSIVE_REQ_PER_MIN", 5))
API_RATE_LIMIT_WINDOW_SEC = max(10, _env_int("RATE_LIMIT_WINDOW_SEC", 60))
RUNTIME_HEARTBEAT_MAX_AGE_SEC = max(5, _env_int("RUNTIME_HEARTBEAT_MAX_AGE_SEC", 90))
RUNTIME_RECONCILIATION_MAX_AGE_SEC = max(5, _env_int("RUNTIME_RECONCILIATION_MAX_AGE_SEC", 120))
RUNTIME_EXCHANGE_CHECK_MAX_AGE_SEC = max(5, _env_int("RUNTIME_EXCHANGE_CHECK_MAX_AGE_SEC", 120))
BOTS_OVERVIEW_CACHE_TTL_SEC = max(1, _env_int("BOTS_OVERVIEW_CACHE_TTL_SEC", 10))
BOTS_MAX_INSTANCES = max(1, _env_int("BOTS_MAX_INSTANCES", 30))
BOTS_OVERVIEW_INCLUDE_RECENT_LOGS = _env_bool("BOTS_OVERVIEW_INCLUDE_RECENT_LOGS", True)
BOTS_OVERVIEW_RECENT_LOGS_PER_BOT = max(0, _env_int("BOTS_OVERVIEW_RECENT_LOGS_PER_BOT", 5))
BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT = max(0, _env_int("BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT", 40))
BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE = max(10, _env_int("BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE", 250))
BOTS_OVERVIEW_PROFILE_SLOW_MS = max(50, _env_int("BOTS_OVERVIEW_PROFILE_SLOW_MS", 500))
BOTS_OVERVIEW_SLOW_LOG_THROTTLE_SEC = max(5, _env_int("BOTS_OVERVIEW_SLOW_LOG_THROTTLE_SEC", 30))
BOTS_LOGS_REF_BACKFILL_MAX_ROWS = max(1000, _env_int("BOTS_LOGS_REF_BACKFILL_MAX_ROWS", 50000))
RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_TTL_SEC = max(1, _env_int("RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_TTL_SEC", 30))
RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_MAX_IDS = max(200, _env_int("RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_MAX_IDS", 2000))
RUNTIME_REMOTE_ORDERS_ENABLED = _env_bool("RUNTIME_REMOTE_ORDERS_ENABLED", False)
LIVE_TRADING_ENABLED = _env_bool("LIVE_TRADING_ENABLED", False)
RUNTIME_REMOTE_ORDER_IDEMPOTENCY_TTL_SEC = max(1, _env_int("RUNTIME_REMOTE_ORDER_IDEMPOTENCY_TTL_SEC", 60))
RUNTIME_REMOTE_ORDER_IDEMPOTENCY_MAX_IDS = max(200, _env_int("RUNTIME_REMOTE_ORDER_IDEMPOTENCY_MAX_IDS", 2000))
RUNTIME_REMOTE_ORDER_NOTIONAL_USD = max(5.0, _env_float("RUNTIME_REMOTE_ORDER_NOTIONAL_USD", 15.0))
RUNTIME_REMOTE_ORDER_SUBMIT_COOLDOWN_SEC = max(1, _env_int("RUNTIME_REMOTE_ORDER_SUBMIT_COOLDOWN_SEC", 120))
RUNTIME_REMOTE_ORDER_SYMBOL = str(os.getenv("RUNTIME_REMOTE_ORDER_SYMBOL", os.getenv("BINANCE_TESTNET_TEST_SYMBOL", "BTCUSDT"))).strip().upper()
RUNTIME_REMOTE_ORDER_SIDE = str(os.getenv("RUNTIME_REMOTE_ORDER_SIDE", "BUY")).strip().upper()
RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC = max(1, _env_int("RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC", 20))
BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS = max(
    1,
    _env_int(
        "BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS",
        int(_BREAKER_ALERT_THRESHOLDS["integrity_window_hours"]),
    ),
)
BREAKER_EVENTS_UNKNOWN_RATIO_WARN = min(
    1.0,
    max(
        0.0,
        _env_float(
            "BREAKER_EVENTS_UNKNOWN_RATIO_WARN",
            float(_BREAKER_ALERT_THRESHOLDS["unknown_ratio_warn"]),
        ),
    ),
)
BREAKER_EVENTS_UNKNOWN_MIN_EVENTS = max(
    1,
    _env_int(
        "BREAKER_EVENTS_UNKNOWN_MIN_EVENTS",
        int(_BREAKER_ALERT_THRESHOLDS["min_events_warn"]),
    ),
)
SECURITY_INTERNAL_HEADER_ALERT_THROTTLE_SEC = max(
    1,
    _env_int(
        "SECURITY_INTERNAL_HEADER_ALERT_THROTTLE_SEC",
        int(_OBSERVABILITY_LOGGING_POLICY["security_internal_header_alert_throttle_sec"]),
    ),
)
OPS_ALERT_SLIPPAGE_P95_WARN_BPS = max(
    0.1,
    _env_float(
        "OPS_ALERT_SLIPPAGE_P95_WARN_BPS",
        float(_OPS_ALERT_THRESHOLDS["slippage_p95_warn_bps"]),
    ),
)
OPS_ALERT_API_ERRORS_WARN = max(
    1,
    _env_int(
        "OPS_ALERT_API_ERRORS_WARN",
        int(_OPS_ALERT_THRESHOLDS["api_errors_warn"]),
    ),
)
OPS_ALERT_BREAKER_WINDOW_HOURS = max(
    1,
    _env_int(
        "OPS_ALERT_BREAKER_WINDOW_HOURS",
        int(_OPS_ALERT_THRESHOLDS["breaker_window_hours"]),
    ),
)
OPS_ALERT_DRIFT_ENABLED = _env_bool(
    "OPS_ALERT_DRIFT_ENABLED",
    bool(_OPS_ALERT_THRESHOLDS["drift_enabled"]),
)
SHADOW_MARKETDATA_BASE_URL = str(os.getenv("SHADOW_MARKETDATA_BASE_URL", BINANCE_PUBLIC_MARKETDATA_BASE_URL)).strip() or BINANCE_PUBLIC_MARKETDATA_BASE_URL
SHADOW_DEFAULT_LOOKBACK_BARS = max(60, _env_int("SHADOW_DEFAULT_LOOKBACK_BARS", 300))
SHADOW_DEFAULT_POLL_SEC = max(10, _env_int("SHADOW_DEFAULT_POLL_SEC", 30))
SHADOW_DEFAULT_TIMEFRAME = str(os.getenv("SHADOW_DEFAULT_TIMEFRAME", "5m")).strip().lower() or "5m"

DEFAULT_STRATEGY_ID = "trend_pullback_orderflow_confirm_v1"
DEFAULT_STRATEGY_NAME = "Trend Pullback + Orderflow Confirm"
DEFAULT_STRATEGY_VERSION = "1.0.0"
DEFAULT_STRATEGY_DESCRIPTION = "Default strategy for paper/testnet bootstrap."
DEFAULT_PARAMS_YAML = """risk_per_trade_pct: 0.75
adx_threshold: 20
obi_long_threshold: 0.55
obi_short_threshold: 0.45
cvd_window_minutes: 5
atr_stop_mult: 2
atr_take_mult: 3
trail_activate_atr: 1.5
trail_distance_atr: 2
time_stop_bars: 12
max_daily_loss_pct: 5
max_dd_pct: 22
max_positions: 20
max_slippage_bps: 12
"""

DEFAULT_PARAMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["risk_per_trade_pct", "max_daily_loss_pct", "max_dd_pct", "max_positions"],
    "properties": {
        "risk_per_trade_pct": {"type": "number", "minimum": 0.1, "maximum": 2.0},
        "adx_threshold": {"type": "number", "minimum": 5, "maximum": 60},
        "obi_long_threshold": {"type": "number", "minimum": 0.5, "maximum": 0.99},
        "obi_short_threshold": {"type": "number", "minimum": 0.01, "maximum": 0.5},
        "cvd_window_minutes": {"type": "number", "minimum": 1, "maximum": 60},
        "atr_stop_mult": {"type": "number", "minimum": 0.5, "maximum": 5.0},
        "atr_take_mult": {"type": "number", "minimum": 0.5, "maximum": 8.0},
        "trail_activate_atr": {"type": "number", "minimum": 0.5, "maximum": 5.0},
        "trail_distance_atr": {"type": "number", "minimum": 0.5, "maximum": 5.0},
        "time_stop_bars": {"type": "number", "minimum": 1, "maximum": 200},
        "max_daily_loss_pct": {"type": "number", "minimum": 0.5, "maximum": 20},
        "max_dd_pct": {"type": "number", "minimum": 1, "maximum": 60},
        "max_positions": {"type": "number", "minimum": 1, "maximum": 100},
        "max_slippage_bps": {"type": "number", "minimum": 1, "maximum": 200},
    },
}

LOG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    severity TEXT NOT NULL,
    module TEXT NOT NULL,
    message TEXT NOT NULL,
    related_ids TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    has_bot_ref INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    role TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS log_bot_refs (
    log_id INTEGER NOT NULL,
    bot_id TEXT NOT NULL,
    PRIMARY KEY (log_id, bot_id)
);
CREATE TABLE IF NOT EXISTS breaker_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    bot_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    reason TEXT NOT NULL,
    run_id TEXT,
    symbol TEXT,
    source_log_id INTEGER UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_breaker_events_bot_mode_ts ON breaker_events(bot_id, mode, ts DESC);
CREATE INDEX IF NOT EXISTS idx_breaker_events_ts ON breaker_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_log_bot_refs_bot_id_log_id ON log_bot_refs(bot_id, log_id DESC);
"""


class LoginBody(BaseModel):
    username: str
    password: str


class StrategyPrimaryBody(BaseModel):
    mode: Literal["paper", "testnet", "live"]


class BotModeBody(BaseModel):
    mode: Literal["paper", "testnet", "live"]
    confirm: str | None = None


class StrategyEnableBody(BaseModel):
    enabled: bool = True


class StrategyPatchBody(BaseModel):
    enabled_for_trading: bool | None = None
    allow_learning: bool | None = None
    is_primary: bool | None = None
    status: Literal["active", "disabled", "archived"] | None = None


class LearningAdoptBody(BaseModel):
    candidate_id: str
    mode: Literal["paper", "testnet"]


class LearningRecommendBody(BaseModel):
    mode: Literal["backtest", "paper", "testnet", "live"] = "paper"
    from_ts: str | None = None
    to_ts: str | None = None


class LearningDecisionBody(BaseModel):
    recommendation_id: str
    note: str | None = None


class OptionBRecalculateBody(BaseModel):
    pbo_max: float | None = None
    dsr_min: float | None = None


class OptionBDecisionBody(BaseModel):
    note: str | None = None


class RolloutStartBody(BaseModel):
    candidate_run_id: str
    baseline_run_id: str | None = None
    note: str | None = None


class RolloutAdvanceBody(BaseModel):
    note: str | None = None


class RolloutDecisionBody(BaseModel):
    reason: str | None = None


class RolloutEvaluatePhaseBody(BaseModel):
    phase: Literal["paper_soak", "testnet_soak", "shadow", "canary05", "canary15", "canary35", "canary60"] = "paper_soak"
    auto_abort: bool = True
    auto_advance: bool = False
    override_started_at: str | None = None
    baseline_live_kpis: dict[str, Any] | None = None


class RolloutBlendPreviewBody(BaseModel):
    baseline_signal: dict[str, Any]
    candidate_signal: dict[str, Any]
    symbol: str | None = None
    timeframe: str | None = None
    record_telemetry: bool = True


class ResearchChangePointsBody(BaseModel):
    series: list[float]
    signal_name: str = "returns"
    period: dict[str, str] | None = None
    model: Literal["l1", "l2", "rbf"] = "l2"
    max_breakpoints: int = 5
    penalty: float | None = None


class ResearchMassBacktestStartBody(BaseModel):
    strategy_ids: list[str] | None = None
    bot_id: str | None = None
    market: Literal["crypto", "forex", "equities"] = "crypto"
    symbol: str = "BTCUSDT"
    timeframe: Literal["5m", "10m", "15m"] = "5m"
    start: str = "2024-01-01"
    end: str = "2024-12-31"
    dataset_source: str = "auto"
    data_mode: Literal["dataset", "api"] = "dataset"
    validation_mode: Literal["walk-forward", "purged-cv", "cpcv"] = "walk-forward"
    max_variants_per_strategy: int = 8
    train_days: int = 180
    test_days: int = 60
    max_folds: int = 8
    top_n: int = 10
    seed: int = 42
    costs: dict[str, float] | None = None
    use_orderflow_data: bool = True


class ResearchMassBacktestMarkCandidateBody(BaseModel):
    run_id: str
    variant_id: str
    note: str | None = None


class ResearchBeastStartBody(ResearchMassBacktestStartBody):
    tier: Literal["hobby", "pro"] = "hobby"


class ResearchBeastStopBody(BaseModel):
    reason: str | None = None


class RunsPatchBody(BaseModel):
    alias: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None
    archived: bool | None = None


class RunsBulkBody(BaseModel):
    run_ids: list[str]
    action: Literal["archive", "unarchive", "delete"]


class BotCreateBody(BaseModel):
    name: str | None = None
    engine: str = "bandit_thompson"
    mode: Literal["shadow", "paper", "testnet", "live"] = "paper"
    status: Literal["active", "paused", "archived"] = "active"
    pool_strategy_ids: list[str] | None = None
    universe: list[str] | None = None
    notes: str | None = None


class BotPatchBody(BaseModel):
    name: str | None = None
    engine: str | None = None
    mode: Literal["shadow", "paper", "testnet", "live"] | None = None
    status: Literal["active", "paused", "archived"] | None = None
    pool_strategy_ids: list[str] | None = None
    universe: list[str] | None = None
    notes: str | None = None


class BotPolicyStatePatchBody(BaseModel):
    engine: str | None = None
    mode: Literal["shadow", "paper", "testnet", "live"] | None = None
    status: Literal["active", "paused", "archived"] | None = None
    pool_strategy_ids: list[str] | None = None
    universe: list[str] | None = None
    notes: str | None = None


class BotBulkPatchBody(BaseModel):
    ids: list[str]
    engine: str | None = None
    mode: Literal["shadow", "paper", "testnet", "live"] | None = None
    status: Literal["active", "paused", "archived"] | None = None
    pool_strategy_ids: list[str] | None = None
    universe: list[str] | None = None
    notes: str | None = None


class BotStartBody(BaseModel):
    bot_id: str | None = None


class ShadowStartBody(BaseModel):
    bot_id: str | None = None
    timeframe: Literal["5m", "10m", "15m"] = "5m"
    lookback_bars: int = 300
    poll_sec: int = 30
    symbol: str | None = None


class ShadowStopBody(BaseModel):
    reason: str | None = None


class BatchCreateBody(BaseModel):
    objective: str | None = None
    strategy_ids: list[str] | None = None
    bot_id: str | None = None
    market: Literal["crypto", "forex", "equities"] = "crypto"
    symbol: str = "BTCUSDT"
    timeframe: Literal["5m", "10m", "15m"] = "5m"
    start: str = "2024-01-01"
    end: str = "2024-12-31"
    dataset_source: str = "auto"
    data_mode: Literal["dataset", "api"] = "dataset"
    validation_mode: Literal["walk-forward", "purged-cv", "cpcv"] = "walk-forward"
    max_variants_per_strategy: int = 8
    train_days: int = 180
    test_days: int = 60
    max_folds: int = 8
    top_n: int = 10
    seed: int = 42
    costs: dict[str, float] | None = None
    use_orderflow_data: bool = True


class BatchShortlistBody(BaseModel):
    items: list[dict[str, Any]] | None = None
    source: str | None = None
    note: str | None = None


class RunPromoteBody(BaseModel):
    baseline_run_id: str | None = None
    note: str | None = None
    target_mode: Literal["paper", "testnet", "live"] = "paper"


class TradesBulkDeleteBody(BaseModel):
    ids: list[str] | None = None
    strategy_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    reason_code: str | None = None
    exit_reason: str | None = None
    result: str | None = None
    mode: str | None = None
    environment: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    dry_run: bool = False


class InstrumentRegistrySyncBody(BaseModel):
    family: Literal["spot", "margin", "usdm_futures", "coinm_futures"] | None = None
    environment: Literal["live", "testnet"] | None = None


class ReportingExportBody(BaseModel):
    strategy_id: str | None = None
    bot_id: str | None = None
    venue: str | None = None
    family: str | None = None
    symbol: str | None = None
    report_scope: Literal["summary", "daily", "monthly", "trades", "costs", "full"] = "full"


class ExecutionPreflightBody(BaseModel):
    family: str
    environment: str
    symbol: str
    side: str
    order_type: str
    quantity: float | None = None
    quote_quantity: float | None = None
    price: float | None = None
    time_in_force: str | None = None
    mode: str | None = None
    strategy_id: str | None = None
    bot_id: str | None = None
    reduce_only: bool | None = None
    requested_notional: float | None = None
    slippage_bps: float | None = None
    spread_bps: float | None = None
    estimated_fee: float | None = None
    market_snapshot: dict[str, Any] | None = None


class ExecutionCancelAllBody(BaseModel):
    family: str
    environment: str
    symbol: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def json_save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def to_csv(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue()


def parse_yaml_map(text: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(text) or {}
    except Exception:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _json_file_or_default(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _yaml_file_or_default(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return payload if payload is not None else default
    except Exception:
        return default


def _resolve_config_policies_root() -> Path:
    return resolve_policy_root(MONOREPO_ROOT, explicit=DEFAULT_CONFIG_POLICIES_ROOT)


def _config_policy_files() -> tuple[Path, dict[str, Path]]:
    root = _resolve_config_policies_root()
    return root, {
        "gates": root / "gates.yaml",
        "microstructure": root / "microstructure.yaml",
        "risk_policy": root / "risk_policy.yaml",
        "beast_mode": root / "beast_mode.yaml",
        "fees": root / "fees.yaml",
        "fundamentals_credit_filter": root / "fundamentals_credit_filter.yaml",
        "runtime_controls": root / "runtime_controls.yaml",
        "cost_stack": root / "cost_stack.yaml",
        "reporting_exports": root / "reporting_exports.yaml",
        "execution_safety": root / "execution_safety.yaml",
        "execution_router": root / "execution_router.yaml",
    }


def _policy_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    gates = bundle.get("gates") if isinstance(bundle.get("gates"), dict) else {}
    micro = bundle.get("microstructure") if isinstance(bundle.get("microstructure"), dict) else {}
    risk = bundle.get("risk_policy") if isinstance(bundle.get("risk_policy"), dict) else {}
    beast = bundle.get("beast_mode") if isinstance(bundle.get("beast_mode"), dict) else {}
    fees = bundle.get("fees") if isinstance(bundle.get("fees"), dict) else {}
    fundamentals = bundle.get("fundamentals_credit_filter") if isinstance(bundle.get("fundamentals_credit_filter"), dict) else {}
    runtime_controls = bundle.get("runtime_controls") if isinstance(bundle.get("runtime_controls"), dict) else {}
    cost_stack = bundle.get("cost_stack") if isinstance(bundle.get("cost_stack"), dict) else {}
    reporting_exports = bundle.get("reporting_exports") if isinstance(bundle.get("reporting_exports"), dict) else {}
    execution_safety = bundle.get("execution_safety") if isinstance(bundle.get("execution_safety"), dict) else {}
    execution_router = bundle.get("execution_router") if isinstance(bundle.get("execution_router"), dict) else {}
    g = gates.get("gates") if isinstance(gates.get("gates"), dict) else {}
    m = micro.get("microstructure") if isinstance(micro.get("microstructure"), dict) else {}
    r = risk.get("risk_policy") if isinstance(risk.get("risk_policy"), dict) else {}
    b = beast.get("beast_mode") if isinstance(beast.get("beast_mode"), dict) else {}
    f = fees.get("fees") if isinstance(fees.get("fees"), dict) else {}
    fc = fundamentals.get("fundamentals_credit_filter") if isinstance(fundamentals.get("fundamentals_credit_filter"), dict) else {}
    rc = runtime_controls.get("runtime_controls") if isinstance(runtime_controls.get("runtime_controls"), dict) else {}
    cs = cost_stack.get("cost_stack") if isinstance(cost_stack.get("cost_stack"), dict) else {}
    rexp = reporting_exports.get("reporting_exports") if isinstance(reporting_exports.get("reporting_exports"), dict) else {}
    exs = execution_safety.get("execution_safety") if isinstance(execution_safety.get("execution_safety"), dict) else {}
    exr = execution_router.get("execution_router") if isinstance(execution_router.get("execution_router"), dict) else {}
    f_scoring = fc.get("scoring") if isinstance(fc.get("scoring"), dict) else {}
    f_thr = f_scoring.get("thresholds") if isinstance(f_scoring.get("thresholds"), dict) else {}
    vpin = m.get("vpin") if isinstance(m.get("vpin"), dict) else {}
    thresholds = vpin.get("thresholds") if isinstance(vpin.get("thresholds"), dict) else {}
    surrogate = g.get("surrogate_adjustments") if isinstance(g.get("surrogate_adjustments"), dict) else {}
    execution_modes = rc.get("execution_modes") if isinstance(rc.get("execution_modes"), dict) else {}
    observability = rc.get("observability") if isinstance(rc.get("observability"), dict) else {}
    runtime_telemetry = observability.get("runtime_telemetry") if isinstance(observability.get("runtime_telemetry"), dict) else {}
    drift = rc.get("drift") if isinstance(rc.get("drift"), dict) else {}
    drift_adwin = drift.get("adwin") if isinstance(drift.get("adwin"), dict) else {}
    drift_page_hinkley = drift.get("page_hinkley") if isinstance(drift.get("page_hinkley"), dict) else {}
    health_scoring = rc.get("health_scoring") if isinstance(rc.get("health_scoring"), dict) else {}
    circuit_breakers = health_scoring.get("circuit_breakers") if isinstance(health_scoring.get("circuit_breakers"), dict) else {}
    execution_guard = health_scoring.get("execution_guard") if isinstance(health_scoring.get("execution_guard"), dict) else {}
    alert_thresholds = rc.get("alert_thresholds") if isinstance(rc.get("alert_thresholds"), dict) else {}
    breaker_integrity = alert_thresholds.get("breaker_integrity") if isinstance(alert_thresholds.get("breaker_integrity"), dict) else {}
    operations = alert_thresholds.get("operations") if isinstance(alert_thresholds.get("operations"), dict) else {}
    legacy_aliases = execution_modes.get("legacy_aliases") if isinstance(execution_modes.get("legacy_aliases"), dict) else {}
    cs_sources = cs.get("sources") if isinstance(cs.get("sources"), dict) else {}
    cs_estimation = cs.get("estimation") if isinstance(cs.get("estimation"), dict) else {}
    cs_aggregation = cs.get("aggregation") if isinstance(cs.get("aggregation"), dict) else {}
    cs_alerts = cs.get("alerts") if isinstance(cs.get("alerts"), dict) else {}
    rexp_formats = rexp.get("formats") if isinstance(rexp.get("formats"), dict) else {}
    rexp_limits = rexp.get("limits") if isinstance(rexp.get("limits"), dict) else {}
    exs_modes = exs.get("modes") if isinstance(exs.get("modes"), dict) else {}
    exs_preflight = exs.get("preflight") if isinstance(exs.get("preflight"), dict) else {}
    exs_sizing = exs.get("sizing") if isinstance(exs.get("sizing"), dict) else {}
    exs_kill = exs.get("kill_switch") if isinstance(exs.get("kill_switch"), dict) else {}
    exr_families = exr.get("families_enabled") if isinstance(exr.get("families_enabled"), dict) else {}
    exr_supported = (
        exr.get("first_iteration_supported_order_types")
        if isinstance(exr.get("first_iteration_supported_order_types"), dict)
        else {}
    )
    return {
        "pbo_reject_if_gt": (g.get("pbo") or {}).get("reject_if_gt") if isinstance(g.get("pbo"), dict) else None,
        "dsr_min": (g.get("dsr") or {}).get("min_dsr") if isinstance(g.get("dsr"), dict) else None,
        "walk_forward_folds": (g.get("walk_forward") or {}).get("folds") if isinstance(g.get("walk_forward"), dict) else None,
        "cost_stress_multipliers": (g.get("cost_stress") or {}).get("multipliers") if isinstance(g.get("cost_stress"), dict) else [],
        "order_flow_level": m.get("order_flow_level"),
        "vpin_soft_kill_cdf": thresholds.get("soft_kill_cdf"),
        "vpin_hard_kill_cdf": thresholds.get("hard_kill_cdf"),
        "risk_kill_scope": r.get("scope") if isinstance(r.get("scope"), list) else [],
        "beast_max_trials_per_batch": b.get("max_trials_per_batch"),
        "beast_requires_postgres": b.get("requires_postgres"),
        "fees_ttl_hours": f.get("fee_snapshot_ttl_hours"),
        "funding_ttl_minutes": f.get("funding_snapshot_ttl_minutes"),
        "fundamentals_enabled": fc.get("enabled"),
        "fundamentals_fail_closed": fc.get("fail_closed"),
        "fundamentals_apply_markets": fc.get("apply_markets") if isinstance(fc.get("apply_markets"), list) else [],
        "fundamentals_freshness_max_days": fc.get("freshness_max_days"),
        "fundamentals_current_ratio_min": f_thr.get("current_ratio_min"),
        "surrogate_adjustments_enabled": surrogate.get("enabled"),
        "surrogate_adjustments_allowed_execution_modes": surrogate.get("allowed_execution_modes") if isinstance(surrogate.get("allowed_execution_modes"), list) else [],
        "surrogate_adjustments_promotion_blocked": surrogate.get("promotion_blocked"),
        "runtime_default_mode": execution_modes.get("default_global_runtime_mode"),
        "runtime_global_modes": execution_modes.get("global_runtime_modes") if isinstance(execution_modes.get("global_runtime_modes"), list) else [],
        "bot_policy_modes": execution_modes.get("bot_policy_modes") if isinstance(execution_modes.get("bot_policy_modes"), list) else [],
        "legacy_non_runtime_aliases": sorted(
            [("MOCK" if str(alias).strip().lower() == "mock" else str(alias)) for alias in legacy_aliases]
        ),
        "telemetry_real_source": runtime_telemetry.get("real_source"),
        "telemetry_synthetic_source": runtime_telemetry.get("synthetic_source"),
        "drift_default_algorithm": drift.get("default_algorithm"),
        "drift_min_points": drift.get("min_points"),
        "drift_trigger_votes_required": drift.get("trigger_votes_required"),
        "drift_adwin_mean_shift_zscore_threshold": drift_adwin.get("mean_shift_zscore_threshold"),
        "drift_page_hinkley_delta": drift_page_hinkley.get("delta"),
        "drift_page_hinkley_lambda": drift_page_hinkley.get("lambda"),
        "health_max_error_streak": circuit_breakers.get("max_error_streak"),
        "health_max_ws_lag_ms": circuit_breakers.get("max_ws_lag_ms"),
        "health_max_desync_count": circuit_breakers.get("max_desync_count"),
        "health_max_spread_spike_bps": circuit_breakers.get("max_spread_spike_bps"),
        "health_max_vpin_percentile": circuit_breakers.get("max_vpin_percentile"),
        "health_critical_error_limit": execution_guard.get("critical_error_limit"),
        "ops_alert_drift_enabled": operations.get("drift_enabled"),
        "ops_alert_slippage_p95_warn_bps": operations.get("slippage_p95_warn_bps"),
        "ops_alert_api_errors_warn": operations.get("api_errors_warn"),
        "ops_alert_breaker_window_hours": operations.get("breaker_window_hours"),
        "breaker_unknown_ratio_warn": breaker_integrity.get("unknown_ratio_warn"),
        "breaker_min_events_warn": breaker_integrity.get("min_events_warn"),
        "breaker_integrity_window_hours": breaker_integrity.get("integrity_window_hours"),
        "cost_stack_spot_commission_source": cs_sources.get("spot_commission_source"),
        "cost_stack_futures_income_source": cs_sources.get("futures_income_source"),
        "cost_stack_margin_interest_source": cs_sources.get("margin_interest_source"),
        "cost_stack_spread_bps_default": cs_estimation.get("spread_bps_default"),
        "cost_stack_slippage_bps_default": cs_estimation.get("slippage_bps_default"),
        "cost_stack_block_missing_live_real_source": cs_estimation.get("block_if_missing_real_cost_source_in_live"),
        "cost_stack_allow_fallback_estimation_in_paper": cs_estimation.get("allow_fallback_estimation_in_paper"),
        "cost_stack_supported_periods": cs_aggregation.get("supported_periods") if isinstance(cs_aggregation.get("supported_periods"), list) else [],
        "cost_stack_fee_source_stale_warn_hours": cs_alerts.get("warn_if_fee_source_stale_hours_gt"),
        "cost_stack_warn_total_cost_pct_gross": cs_alerts.get("warn_if_total_cost_pct_of_gross_pnl_gt"),
        "cost_stack_block_total_cost_pct_gross": cs_alerts.get("block_if_total_cost_pct_of_gross_pnl_gt"),
        "reporting_export_formats": sorted([fmt for fmt, enabled in rexp_formats.items() if enabled]),
        "reporting_export_max_rows": rexp_limits.get("max_rows_per_export"),
        "execution_allow_live": exs_modes.get("allow_live"),
        "execution_quote_stale_block_ms": exs_preflight.get("quote_stale_block_ms"),
        "execution_require_capability_snapshot": exs_preflight.get("require_capability_snapshot"),
        "execution_max_notional_per_order_usd": exs_sizing.get("max_notional_per_order_usd"),
        "execution_max_open_orders_total": exs_sizing.get("max_open_orders_total"),
        "execution_kill_switch_enabled": exs_kill.get("enabled"),
        "execution_kill_switch_auto_cancel_all": exs_kill.get("auto_cancel_all_on_trip"),
        "execution_router_families_enabled": sorted([name for name, enabled in exr_families.items() if enabled]),
        "execution_router_supported_order_types": exr_supported,
    }


def load_numeric_policies_bundle() -> dict[str, Any]:
    authority = describe_policy_root_resolution(MONOREPO_ROOT, explicit=DEFAULT_CONFIG_POLICIES_ROOT)
    root, files = _config_policy_files()
    payloads: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    warnings: list[str] = list(authority.get("warnings") or [])
    for name, path in files.items():
        if name == "runtime_controls":
            runtime_bundle = load_runtime_controls_bundle(repo_root=MONOREPO_ROOT, explicit_root=DEFAULT_CONFIG_POLICIES_ROOT)
            if runtime_bundle.get("errors"):
                warnings.extend(str(row) for row in (runtime_bundle.get("errors") or []) if str(row).strip())
            payloads[name] = {"runtime_controls": runtime_bundle.get("runtime_controls", {})}
            meta[name] = {
                "path": str(runtime_bundle.get("path") or path),
                "exists": bool(runtime_bundle.get("exists", False)),
                "valid": bool(runtime_bundle.get("valid", False)),
                "source": str(runtime_bundle.get("source") or ""),
                "source_hash": str(runtime_bundle.get("source_hash") or ""),
                "policy_hash": str(runtime_bundle.get("policy_hash") or ""),
                "errors": list(runtime_bundle.get("errors") or []),
            }
            continue
        exists = path.exists()
        data = _yaml_file_or_default(path, {})
        valid = isinstance(data, dict) and bool(data)
        if exists and not valid:
            warnings.append(f"Policy YAML invÃ¡lido o vacÃ­o: {name} ({path.name})")
        if not exists:
            warnings.append(f"Policy YAML no encontrado: {name} ({path})")
        payloads[name] = data if isinstance(data, dict) else {}
        meta[name] = {
            "path": str(path),
            "exists": exists,
            "valid": valid,
        }
    return {
        "ok": True,
        "source_root": str(root),
        "available": root.exists(),
        "authority": authority,
        "mode_taxonomy": mode_taxonomy_payload(),
        "warnings": warnings,
        "files": meta,
        "policies": payloads,
        "summary": _policy_summary(payloads),
    }


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except Exception:
        return False


def _build_learning_capabilities_registry() -> dict[str, dict[str, Any]]:
    # capability -> deps + availability. UI usa esto para habilitar widgets sin hardcode.
    deps_map: dict[str, list[str]] = {
        "bandit_weights_history": [],
        "explain_recommendation": [],
        "offline_change_points": ["ruptures"],
        "mlflow_runs": ["mlflow"],
        "portfolio_alloc_preview": ["riskfolio", "pypfopt", "cvxpy"],
    }
    registry: dict[str, dict[str, Any]] = {}
    for cap, deps in deps_map.items():
        missing = [dep for dep in deps if not _module_available(dep)]
        registry[cap] = {
            "id": cap,
            "requires": deps,
            "available": len(missing) == 0,
            "missing": missing,
            "tier": "research" if deps else "runtime",
            "reason": "" if not missing else f"Faltan librerias: {', '.join(missing)}",
        }
    return registry


def _default_engine_capabilities(engine_id: str) -> list[str]:
    mapping = {
        "fixed_rules": ["explain_recommendation"],
        "bandit_thompson": ["bandit_weights_history", "explain_recommendation"],
        "bandit_ucb1": ["bandit_weights_history", "explain_recommendation"],
        "meta_rf_selector": ["explain_recommendation", "mlflow_runs"],
        "dqn_offline_experimental": ["explain_recommendation", "mlflow_runs"],
    }
    return mapping.get(engine_id, ["explain_recommendation"])


def _selector_algo_to_engine_id(selector_algo: str) -> str:
    algo = str(selector_algo or "thompson").strip().lower()
    return {
        "thompson": "bandit_thompson",
        "ucb1": "bandit_ucb1",
        "regime_rules": "fixed_rules",
    }.get(algo, "bandit_thompson")


def _engine_id_to_selector_algo(engine_id: str) -> str:
    eid = str(engine_id or "").strip().lower()
    return {
        "bandit_thompson": "thompson",
        "bandit_ucb1": "ucb1",
        "fixed_rules": "regime_rules",
    }.get(eid, "thompson")


def build_learning_config_payload(settings: dict[str, Any]) -> dict[str, Any]:
    settings = learning_service.ensure_settings_shape(dict(settings or {}))
    capabilities_registry = _build_learning_capabilities_registry()
    numeric_policies = load_numeric_policies_bundle()
    numeric_policies_map = numeric_policies.get("policies") if isinstance(numeric_policies.get("policies"), dict) else {}
    numeric_gates_file = numeric_policies_map.get("gates") if isinstance(numeric_policies_map.get("gates"), dict) else {}
    numeric_gates_root = numeric_gates_file.get("gates") if isinstance(numeric_gates_file.get("gates"), dict) else {}
    warnings: list[str] = []
    yaml_valid = True
    source_mode = "knowledge_loader"
    tiers_payload: dict[str, Any] | None = None
    try:
        engines_payload = learning_service.knowledge.get_learning_engines()
        gates_payload = learning_service.knowledge.get_gates()
        # optional tiers file (no rompe si no existe)
        tiers_path = (MONOREPO_ROOT / "knowledge" / "policies" / "tiers.yaml").resolve()
        tiers_payload = _yaml_file_or_default(tiers_path, {"tiers": []}) if tiers_path.exists() else {"tiers": []}
    except Exception as exc:
        yaml_valid = False
        source_mode = "fallback_safe"
        warnings.append(f"YAML invÃ¡lido o no disponible: {exc}. Fallback seguro: learning OFF.")
        engines_payload = {
            "learning_mode": {"option": "B", "enabled_default": False, "auto_apply_live": False, "require_human_approval": True},
            "drift_detection": {"enabled": True, "detectors": []},
            "engines": [],
            "safe_update": {"enabled": True, "canary_schedule_pct": [0, 5, 15, 35, 60, 100], "rollback_auto": True},
        }
        gates_payload = {}
        tiers_payload = {"tiers": []}

    raw_engines = engines_payload.get("engines") if isinstance(engines_payload, dict) else []
    engines_out: list[dict[str, Any]] = []
    for row in raw_engines if isinstance(raw_engines, list) else []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        caps = row.get("capabilities") if isinstance(row.get("capabilities"), list) else _default_engine_capabilities(str(row.get("id")))
        caps = [str(c) for c in caps]
        engine_caps = []
        for cap_id in caps:
            cap = capabilities_registry.get(cap_id, {"id": cap_id, "available": True, "requires": [], "missing": [], "tier": "runtime", "reason": ""})
            engine_caps.append(cap)
        engines_out.append(
            {
                "id": str(row.get("id")),
                "name": str(row.get("name") or row.get("id")),
                "enabled_default": bool(row.get("enabled_default", False)),
                "description": str(row.get("description") or ""),
                "ui_help": str(row.get("ui_help") or ""),
                "params": row.get("params") if isinstance(row.get("params"), dict) else {},
                "capabilities": caps,
                "capabilities_detail": engine_caps,
            }
        )

    learning_cfg = settings.get("learning") if isinstance(settings.get("learning"), dict) else {}
    selected_engine_id = str(learning_cfg.get("engine_id") or _selector_algo_to_engine_id(str(learning_cfg.get("selector_algo") or "thompson")))
    available_engine_ids = {row["id"] for row in engines_out}
    if selected_engine_id and selected_engine_id not in available_engine_ids and engines_out:
        warnings.append(f"engine_id '{selected_engine_id}' no existe en YAML. Se usa fallback seguro.")
        selected_engine_id = str(next((e["id"] for e in engines_out if e.get("enabled_default")), engines_out[0]["id"]))

    safe_update_cfg = (engines_payload.get("safe_update") if isinstance(engines_payload, dict) and isinstance(engines_payload.get("safe_update"), dict) else {}) or {}
    rollout_cfg = settings.get("rollout") if isinstance(settings.get("rollout"), dict) else {}
    require_approve = bool(rollout_cfg.get("require_manual_approval_for_live", True))
    canary_schedule = safe_update_cfg.get("canary_schedule_pct")
    if not isinstance(canary_schedule, list):
        canary_schedule = [int(row.get("capital_pct", 0) or 0) for row in (rollout_cfg.get("phases") or []) if isinstance(row, dict) and row.get("type") in {"shadow", "canary", "stable"}]
        if canary_schedule and canary_schedule[0] != 0:
            canary_schedule = [0] + canary_schedule
    canary_schedule = [int(x) for x in canary_schedule] if isinstance(canary_schedule, list) else [0, 5, 15, 35, 60, 100]

    drift_detection = engines_payload.get("drift_detection") if isinstance(engines_payload, dict) and isinstance(engines_payload.get("drift_detection"), dict) else {"enabled": True, "detectors": []}
    detector_options = [
        {"id": "adwin", "name": "ADWIN", "description": "Detecta cambio de distribuciÃ³n en streams (online)."},
        {"id": "page_hinkley", "name": "Page-Hinkley", "description": "Detecta cambio de media acumulada (CUSUM)."},
    ]
    # HeurÃ­stico de selectors compatibles con runtime actual.
    runtime_selector_compatible = [e["id"] for e in engines_out if e["id"] in {"fixed_rules", "bandit_thompson", "bandit_ucb1"}]
    if not yaml_valid:
        settings["learning"]["enabled"] = False
    knowledge_gates = gates_payload if isinstance(gates_payload, dict) else {}
    canonical_gates = numeric_gates_root if isinstance(numeric_gates_root, dict) and numeric_gates_root else knowledge_gates
    gates_source = "config/policies/gates.yaml" if canonical_gates is numeric_gates_root else "knowledge/policies/gates.yaml"
    configured_gates_file = str(safe_update_cfg.get("gates_file") or "").strip()
    if configured_gates_file and configured_gates_file != gates_source:
        warnings.append(
            f"safe_update.gates_file ({configured_gates_file}) difiere de la fuente canonica ({gates_source}). Se usa fuente canonica."
        )
    safe_update_gates_file = gates_source
    return {
        "ok": True,
        "yaml_valid": yaml_valid,
        "source_mode": source_mode,
        "warnings": warnings,
        "learning_mode": engines_payload.get("learning_mode") if isinstance(engines_payload, dict) else {},
        "drift_detection": {
            **(drift_detection if isinstance(drift_detection, dict) else {}),
            "runtime_detector_options": detector_options,
        },
        "engines": engines_out,
        "selected_engine_id": selected_engine_id,
        "selector_algo_compat": _engine_id_to_selector_algo(selected_engine_id),
        "runtime_selector_compatible_engine_ids": runtime_selector_compatible,
        "safe_update": {
            "enabled": bool(safe_update_cfg.get("enabled", True)),
            "gates_file": safe_update_gates_file,
            "canary_schedule_pct": canary_schedule,
            "rollback_auto": bool(safe_update_cfg.get("rollback_auto", True)),
            "approve_required": require_approve,
        },
        "gates_summary": {
            "source": gates_source,
            "pbo_enabled": bool(((canonical_gates.get("pbo") or {}).get("enabled")) if isinstance(canonical_gates, dict) else False),
            "dsr_enabled": bool(((canonical_gates.get("dsr") or {}).get("enabled")) if isinstance(canonical_gates, dict) else False),
        },
        "tiers": tiers_payload if isinstance(tiers_payload, dict) else {"tiers": []},
        "capabilities_registry": capabilities_registry,
        "numeric_policies_summary": numeric_policies.get("summary") or {},
        "numeric_policies_meta": {
            "available": bool(numeric_policies.get("available")),
            "source_root": str(numeric_policies.get("source_root") or ""),
            "warnings": numeric_policies.get("warnings") or [],
        },
    }


def get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def admin_username() -> str:
    return get_env("ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME)


def admin_password() -> str:
    return get_env("ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD)


def viewer_username() -> str:
    return get_env("VIEWER_USERNAME", DEFAULT_VIEWER_USERNAME)


def viewer_password() -> str:
    return get_env("VIEWER_PASSWORD", DEFAULT_VIEWER_PASSWORD)


def auth_secret() -> str:
    return get_env("AUTH_SECRET", "")


def internal_proxy_token() -> str:
    return get_env("INTERNAL_PROXY_TOKEN", "")


def _parse_iso_datetime_utc(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        try:
            parsed = datetime.fromisoformat(f"{text}T00:00:00+00:00")
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _internal_proxy_token_state(*, now: datetime | None = None) -> dict[str, Any]:
    now_dt = now or utc_now()
    active_token = internal_proxy_token()
    previous_token = get_env("INTERNAL_PROXY_TOKEN_PREVIOUS", "")
    previous_expires_raw = get_env("INTERNAL_PROXY_TOKEN_PREVIOUS_EXPIRES_AT", "")
    previous_expires_at = _parse_iso_datetime_utc(previous_expires_raw)
    previous_token_configured = bool(previous_token)
    previous_token_enabled = bool(previous_token and previous_expires_at and now_dt < previous_expires_at)
    previous_token_expired = bool(previous_token and previous_expires_at and now_dt >= previous_expires_at)
    previous_token_missing_expiry = bool(previous_token and not previous_expires_at)
    previous_token_seconds_remaining = (
        max(0, int((previous_expires_at - now_dt).total_seconds()))
        if previous_token_enabled and isinstance(previous_expires_at, datetime)
        else 0
    )
    warnings: list[str] = []
    if previous_token_missing_expiry:
        warnings.append("INTERNAL_PROXY_TOKEN_PREVIOUS configurado sin INTERNAL_PROXY_TOKEN_PREVIOUS_EXPIRES_AT (ignorado).")
    if previous_token_expired:
        warnings.append("INTERNAL_PROXY_TOKEN_PREVIOUS expirado.")
    return {
        "active_token": active_token,
        "active_token_configured": bool(active_token),
        "previous_token": previous_token,
        "previous_token_configured": previous_token_configured,
        "previous_token_expires_at": previous_expires_at.isoformat() if isinstance(previous_expires_at, datetime) else None,
        "previous_token_enabled": previous_token_enabled,
        "previous_token_expired": previous_token_expired,
        "previous_token_missing_expiry": previous_token_missing_expiry,
        "previous_token_seconds_remaining": previous_token_seconds_remaining,
        "warnings": warnings,
    }


def _internal_proxy_token_auth_result(request: Request) -> tuple[bool, str]:
    state = _internal_proxy_token_state()
    provided = (request.headers.get("x-rtlab-proxy-token") or "").strip()
    if not provided:
        return False, "missing_proxy_token"
    if not bool(state.get("active_token_configured")):
        return False, "proxy_not_configured"
    active = str(state.get("active_token") or "")
    if active and hmac.compare_digest(provided, active):
        return True, "active_token"
    previous = str(state.get("previous_token") or "")
    if previous and hmac.compare_digest(provided, previous):
        if bool(state.get("previous_token_enabled")):
            return True, "previous_token"
        if bool(state.get("previous_token_expired")):
            return False, "expired_previous_token"
        return False, "previous_token_disabled"
    return False, "invalid_proxy_token"


def runtime_engine_default() -> str:
    value = get_env("RUNTIME_ENGINE", RUNTIME_ENGINE_SIMULATED).lower().strip()
    return RUNTIME_ENGINE_REAL if value == RUNTIME_ENGINE_REAL else RUNTIME_ENGINE_SIMULATED


class LoginRateLimiter:
    def __init__(
        self,
        *,
        attempts_per_window: int = LOGIN_RATE_LIMIT_ATTEMPTS,
        window_minutes: int = LOGIN_RATE_LIMIT_WINDOW_MIN,
        lockout_minutes: int = LOGIN_LOCKOUT_MIN,
        lockout_after_failures: int = LOGIN_LOCKOUT_AFTER_FAILS,
        backend: str = LOGIN_RATE_LIMIT_BACKEND,
        sqlite_path: str | Path | None = None,
    ) -> None:
        self.attempts_per_window = max(1, int(attempts_per_window))
        self.window = timedelta(minutes=max(1, int(window_minutes)))
        self.lockout = timedelta(minutes=max(1, int(lockout_minutes)))
        self.lockout_after_failures = max(self.attempts_per_window, int(lockout_after_failures))
        normalized_backend = str(backend or "memory").strip().lower()
        self.backend = normalized_backend if normalized_backend in {"memory", "sqlite"} else "memory"
        configured_sqlite = str(sqlite_path).strip() if sqlite_path is not None else ""
        self.sqlite_path = Path(configured_sqlite).resolve() if configured_sqlite else LOGIN_RATE_LIMIT_SQLITE_PATH
        self._lock = Lock()
        self._state: dict[str, dict[str, Any]] = {}
        if self.backend == "sqlite":
            self._ensure_sqlite_schema()

    def _connect_sqlite(self) -> sqlite3.Connection:
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.sqlite_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_sqlite_schema(self) -> None:
        with self._connect_sqlite() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_login_rate_limit (
                    limiter_key TEXT PRIMARY KEY,
                    failures_json TEXT NOT NULL,
                    lock_until TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_login_rate_limit_updated_at ON auth_login_rate_limit(updated_at)")
            conn.commit()

    @staticmethod
    def _serialize_failures(failures: list[datetime]) -> str:
        payload = [ts.isoformat() for ts in failures if isinstance(ts, datetime)]
        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def _deserialize_failures(raw: str | None) -> list[datetime]:
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except Exception:
            return []
        values = payload if isinstance(payload, list) else []
        out: list[datetime] = []
        for item in values:
            parsed = _parse_iso_datetime_utc(str(item))
            if isinstance(parsed, datetime):
                out.append(parsed)
        return out

    def _load_entry_sqlite(self, key: str) -> dict[str, Any]:
        with self._connect_sqlite() as conn:
            row = conn.execute(
                "SELECT failures_json, lock_until FROM auth_login_rate_limit WHERE limiter_key = ?",
                (key,),
            ).fetchone()
        if row is None:
            return {"failures": [], "lock_until": None}
        return {
            "failures": self._deserialize_failures(str(row["failures_json"] or "")),
            "lock_until": _parse_iso_datetime_utc(str(row["lock_until"] or "")),
        }

    def _delete_entry_sqlite(self, key: str) -> None:
        with self._connect_sqlite() as conn:
            conn.execute("DELETE FROM auth_login_rate_limit WHERE limiter_key = ?", (key,))
            conn.commit()

    def _persist_entry_sqlite(self, key: str, entry: dict[str, Any]) -> None:
        failures = [ts for ts in (entry.get("failures") or []) if isinstance(ts, datetime)]
        lock_until = entry.get("lock_until")
        if not failures and not isinstance(lock_until, datetime):
            self._delete_entry_sqlite(key)
            return
        with self._connect_sqlite() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO auth_login_rate_limit
                (limiter_key, failures_json, lock_until, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    key,
                    self._serialize_failures(failures),
                    lock_until.isoformat() if isinstance(lock_until, datetime) else None,
                    utc_now_iso(),
                ),
            )
            conn.commit()

    def _load_entry(self, key: str) -> dict[str, Any]:
        if self.backend == "sqlite":
            return self._load_entry_sqlite(key)
        entry = self._state.get(key)
        if not isinstance(entry, dict):
            return {"failures": [], "lock_until": None}
        return {
            "failures": [ts for ts in (entry.get("failures") or []) if isinstance(ts, datetime)],
            "lock_until": entry.get("lock_until"),
        }

    def _persist_entry(self, key: str, entry: dict[str, Any]) -> None:
        if self.backend == "sqlite":
            self._persist_entry_sqlite(key, entry)
            return
        failures = [ts for ts in (entry.get("failures") or []) if isinstance(ts, datetime)]
        lock_until = entry.get("lock_until")
        if not failures and not isinstance(lock_until, datetime):
            self._state.pop(key, None)
            return
        self._state[key] = {
            "failures": failures,
            "lock_until": lock_until if isinstance(lock_until, datetime) else None,
        }

    def _prune(self, *, entry: dict[str, Any], now: datetime) -> None:
        fails = [
            ts
            for ts in (entry.get("failures") or [])
            if isinstance(ts, datetime) and (now - ts) <= self.lockout
        ]
        entry["failures"] = fails
        lock_until = entry.get("lock_until")
        if isinstance(lock_until, datetime) and now >= lock_until:
            entry["lock_until"] = None

    def check(self, key: str) -> tuple[bool, int, str]:
        now = utc_now()
        with self._lock:
            entry = self._load_entry(key)
            self._prune(entry=entry, now=now)
            self._persist_entry(key, entry)
            lock_until = entry.get("lock_until")
            if isinstance(lock_until, datetime) and now < lock_until:
                wait_sec = max(1, int((lock_until - now).total_seconds()))
                return False, wait_sec, "lockout"

            recent_failures = [
                ts for ts in (entry.get("failures") or []) if isinstance(ts, datetime) and (now - ts) <= self.window
            ]
            if len(recent_failures) >= self.attempts_per_window:
                earliest = min(recent_failures)
                retry_at = earliest + self.window
                wait_sec = max(1, int((retry_at - now).total_seconds()))
                return False, wait_sec, "rate_limit"
        return True, 0, ""

    def register_failure(self, key: str) -> None:
        now = utc_now()
        with self._lock:
            entry = self._load_entry(key)
            self._prune(entry=entry, now=now)
            fails = [ts for ts in (entry.get("failures") or []) if isinstance(ts, datetime)]
            fails.append(now)
            entry["failures"] = fails
            if len(fails) >= self.lockout_after_failures:
                entry["lock_until"] = now + self.lockout
            self._persist_entry(key, entry)

    def register_success(self, key: str) -> None:
        with self._lock:
            if self.backend == "sqlite":
                self._delete_entry_sqlite(key)
                return
            if key in self._state:
                self._state.pop(key, None)


LOGIN_RATE_LIMITER = LoginRateLimiter()


class ApiRateLimiter:
    def __init__(
        self,
        *,
        enabled: bool = API_RATE_LIMIT_ENABLED,
        general_per_minute: int = API_RATE_LIMIT_GENERAL_PER_MIN,
        expensive_per_minute: int = API_RATE_LIMIT_EXPENSIVE_PER_MIN,
        window_seconds: int = API_RATE_LIMIT_WINDOW_SEC,
    ) -> None:
        self.enabled = bool(enabled)
        self.general_per_window = max(1, int(general_per_minute))
        self.expensive_per_window = max(1, int(expensive_per_minute))
        self.window = timedelta(seconds=max(10, int(window_seconds)))
        self._lock = Lock()
        self._state: dict[str, list[datetime]] = {}
        self._exempt_prefixes = (
            "/api/v1/health",
            "/api/v1/stream",
            "/api/v1/auth/login",
        )
        self._general_get_prefixes = (
            "/api/v1/bots",
            "/api/v1/batches",
            "/api/v1/runs",
            "/api/v1/backtests/runs",
            "/api/v1/research/mass-backtest/status",
            "/api/v1/research/mass-backtest/results",
            "/api/v1/research/mass-backtest/artifacts",
            "/api/v1/research/beast/status",
            "/api/v1/research/beast/jobs",
        )
        self._expensive_prefixes = (
            "/api/v1/research/",
            "/api/v1/backtests/",
            "/api/v1/runs/compare",
            "/api/v1/gates/reevaluate",
            "/api/v1/bots",
        )

    def _is_exempt(self, *, path: str, method: str) -> bool:
        if method.upper() == "OPTIONS":
            return True
        return any(path == prefix or path.startswith(f"{prefix}/") for prefix in self._exempt_prefixes)

    def _bucket_for_path(self, *, path: str, method: str) -> str:
        method_upper = method.upper()
        # GET read-only de paneles/catálogos se usan en polling y navegación normal.
        # Si caen en "expensive" (5 req/min) la propia UI termina generando 429.
        if method_upper == "GET" and any(path == prefix or path.startswith(f"{prefix}/") for prefix in self._general_get_prefixes):
            return "general"
        if any(path == prefix or path.startswith(f"{prefix}/") for prefix in self._expensive_prefixes):
            return "expensive"
        return "general"

    def check(self, *, client_ip: str, path: str, method: str) -> tuple[bool, int, str]:
        if not self.enabled:
            return True, 0, "disabled"
        if self._is_exempt(path=path, method=method):
            return True, 0, "exempt"
        bucket = self._bucket_for_path(path=path, method=method)
        limit = self.expensive_per_window if bucket == "expensive" else self.general_per_window
        now = utc_now()
        key = f"{client_ip}:{bucket}"
        with self._lock:
            events = [
                ts
                for ts in self._state.get(key, [])
                if isinstance(ts, datetime) and (now - ts) <= self.window
            ]
            if len(events) >= limit:
                oldest = min(events)
                retry_at = oldest + self.window
                retry_after = max(1, int((retry_at - now).total_seconds()))
                self._state[key] = events
                return False, retry_after, bucket
            events.append(now)
            self._state[key] = events
        return True, 0, bucket


API_RATE_LIMITER = ApiRateLimiter()


_KNOWN_INSECURE_PASSWORDS: frozenset[str] = frozenset(
    {"", "admin123!", "viewer123!", "admin", "password", "test123", "changeme"}
)


def _has_default_credentials() -> bool:
    """Detecta contraseñas vacías, no configuradas, o conocidamente débiles."""
    admin_is_insecure = admin_password() in _KNOWN_INSECURE_PASSWORDS
    viewer_is_insecure = viewer_password() in _KNOWN_INSECURE_PASSWORDS
    return admin_is_insecure or viewer_is_insecure


def _validate_auth_config_for_production() -> None:
    if get_env("NODE_ENV", "development").lower() != "production":
        return
    issues: list[str] = []
    if len(auth_secret()) < 32:
        issues.append("AUTH_SECRET debe tener al menos 32 caracteres")
    if _has_default_credentials():
        issues.append("credenciales por defecto detectadas (admin/viewer)")
    if issues:
        raise RuntimeError("Configuracion de auth insegura para produccion: " + "; ".join(issues))


def exchange_name() -> str:
    return get_env("EXCHANGE_NAME", "binance")


def default_mode() -> str:
    return normalize_global_runtime_mode(
        get_env("MODE", DEFAULT_GLOBAL_RUNTIME_MODE),
        default=DEFAULT_GLOBAL_RUNTIME_MODE,
    )


def running_on_railway() -> bool:
    return any(
        [
            bool(get_env("RAILWAY_PROJECT_ID")),
            bool(get_env("RAILWAY_SERVICE_ID")),
            bool(get_env("RAILWAY_ENVIRONMENT")),
            bool(get_env("RAILWAY_PUBLIC_DOMAIN")),
        ]
    )


def allow_local_exchange_file_fallback() -> bool:
    explicit = get_env("ALLOW_LOCAL_EXCHANGE_FILE")
    if explicit:
        return explicit.lower() == "true"
    node_env = get_env("NODE_ENV", "development").lower()
    return node_env != "production" and not running_on_railway()


def exchange_config_file_path() -> Path:
    return (USER_DATA_DIR / "config" / "exchange_binance_spot.json").resolve()


def _pick_string_value(payload: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return {}


def _normalize_binance_endpoint_url(url: str, *, mode: str, kind: str) -> tuple[str, list[str]]:
    raw = str(url or "").strip()
    if not raw:
        return raw, []
    normalized = raw
    warnings: list[str] = []
    parsed_initial = urlparse(normalized)
    if not parsed_initial.scheme and parsed_initial.path:
        guessed_scheme = "wss" if kind == "ws" else "https"
        normalized = f"{guessed_scheme}://{normalized}"
        warnings.append(f"URL de Binance sin esquema corregida automÃ¡ticamente ({kind}/{mode}): se agregÃ³ {guessed_scheme}://")
    parsed = urlparse(normalized)
    replacements = {
        "testnet.binance.visio": "testnet.binance.vision",
        "api.binance.visio": "api.binance.com",
        "stream.binance.visio": "stream.binance.com",
    }
    host = parsed.hostname or ""
    if host in replacements:
        good_host = replacements[host]
        netloc = parsed.netloc
        if "@" in netloc:
            creds_prefix, host_port = netloc.rsplit("@", 1)
            if host_port.startswith(host):
                host_port = good_host + host_port[len(host):]
            netloc = f"{creds_prefix}@{host_port}"
        elif netloc.startswith(host):
            netloc = good_host + netloc[len(host):]
        normalized = parsed._replace(netloc=netloc).geturl()
        warnings.append(f"URL de Binance corregida automÃ¡ticamente ({kind}/{mode}): {host} -> {good_host}")
    return normalized, warnings


def _build_exchange_env_config(mode: str) -> dict[str, Any]:
    normalized = mode.lower().strip()
    if normalized == "testnet":
        expected = [BINANCE_TESTNET_ENV_KEY, BINANCE_TESTNET_ENV_SECRET]
        legacy_key = get_env("TESTNET_API_KEY") or get_env("API_KEY")
        legacy_secret = get_env("TESTNET_API_SECRET") or get_env("API_SECRET")
        key = get_env(BINANCE_TESTNET_ENV_KEY) or legacy_key
        secret = get_env(BINANCE_TESTNET_ENV_SECRET) or legacy_secret
        base_url = get_env(BINANCE_TESTNET_ENV_BASE, BINANCE_TESTNET_BASE_URL_DEFAULT)
        ws_url = get_env(BINANCE_TESTNET_ENV_WS, BINANCE_TESTNET_WS_URL_DEFAULT)
        legacy_used = []
        if not get_env(BINANCE_TESTNET_ENV_KEY) and legacy_key:
            legacy_used.extend(["TESTNET_API_KEY", "API_KEY"])
        if not get_env(BINANCE_TESTNET_ENV_SECRET) and legacy_secret:
            legacy_used.extend(["TESTNET_API_SECRET", "API_SECRET"])
    else:
        expected = [BINANCE_LIVE_ENV_KEY, BINANCE_LIVE_ENV_SECRET]
        legacy_key = get_env("API_KEY")
        legacy_secret = get_env("API_SECRET")
        key = get_env(BINANCE_LIVE_ENV_KEY) or legacy_key
        secret = get_env(BINANCE_LIVE_ENV_SECRET) or legacy_secret
        base_url = get_env(BINANCE_LIVE_ENV_BASE, BINANCE_LIVE_BASE_URL_DEFAULT)
        ws_url = get_env(BINANCE_LIVE_ENV_WS, BINANCE_LIVE_WS_URL_DEFAULT)
        legacy_used = []
        if not get_env(BINANCE_LIVE_ENV_KEY) and legacy_key:
            legacy_used.append("API_KEY")
        if not get_env(BINANCE_LIVE_ENV_SECRET) and legacy_secret:
            legacy_used.append("API_SECRET")
    base_url, base_warnings = _normalize_binance_endpoint_url(base_url, mode=normalized, kind="rest")
    ws_url, ws_warnings = _normalize_binance_endpoint_url(ws_url, mode=normalized, kind="ws")
    missing_expected = [name for name in expected if not get_env(name)]
    return {
        "mode": normalized,
        "key": key,
        "secret": secret,
        "has_keys": bool(key and secret),
        "expected_env_vars": expected,
        "missing_env_vars": missing_expected,
        "legacy_env_vars_used": sorted(set(legacy_used)),
        "base_url": base_url.rstrip("/"),
        "ws_url": ws_url,
        "url_warnings": [*base_warnings, *ws_warnings],
    }


def _load_exchange_json_file(mode: str) -> dict[str, Any]:
    path = exchange_config_file_path()
    if not path.exists():
        return {"ok": False, "error": f"JSON no encontrado en contenedor: {path}", "path": str(path), "key": "", "secret": ""}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"JSON invalido: {exc}", "path": str(path), "key": "", "secret": ""}
    if not isinstance(raw, dict):
        return {"ok": False, "error": "JSON invalido: raiz no es objeto", "path": str(path), "key": "", "secret": ""}

    binance = _nested_dict(raw, "binance")
    testnet = _nested_dict(raw, "testnet")
    spot_testnet = _nested_dict(raw, "spot_testnet")
    mode_block = _nested_dict(raw, mode.lower())
    candidates = [raw, binance, testnet, spot_testnet, mode_block]
    key = ""
    secret = ""
    for candidate in candidates:
        key = key or _pick_string_value(candidate, ["api_key", "apiKey", "key", "API_KEY"])
        secret = secret or _pick_string_value(candidate, ["api_secret", "apiSecret", "secret", "API_SECRET"])
    return {"ok": bool(key and secret), "path": str(path), "key": key, "secret": secret, "error": "" if key and secret else "Faltan api_key/api_secret en JSON"}


def load_exchange_credentials(mode: str) -> dict[str, Any]:
    normalized = mode.lower().strip()
    cfg = _build_exchange_env_config(normalized)
    diagnostics: list[str] = []
    key_source = "env" if cfg["has_keys"] else "none"
    key = cfg["key"]
    secret = cfg["secret"]
    file_payload: dict[str, Any] | None = None

    if not cfg["has_keys"] and allow_local_exchange_file_fallback():
        file_payload = _load_exchange_json_file(normalized)
        if file_payload.get("ok"):
            key = file_payload.get("key", "")
            secret = file_payload.get("secret", "")
            key_source = "json"
            diagnostics.append(f"Credenciales cargadas desde JSON local: {file_payload.get('path')}")
        else:
            diagnostics.append(str(file_payload.get("error", "No se pudo leer JSON local")))
    elif not cfg["has_keys"] and running_on_railway():
        diagnostics.append("Faltan env vars. Cargarlas en Railway -> Service Variables.")

    if cfg["legacy_env_vars_used"]:
        diagnostics.append(f"Usando variables legacy: {', '.join(cfg['legacy_env_vars_used'])}")
    diagnostics.extend([str(msg) for msg in (cfg.get("url_warnings") or []) if str(msg).strip()])

    return {
        "mode": normalized,
        "exchange": exchange_name(),
        "api_key": key,
        "api_secret": secret,
        "has_keys": bool(key and secret),
        "key_source": key_source,
        "expected_env_vars": cfg["expected_env_vars"],
        "missing_env_vars": cfg["missing_env_vars"],
        "base_url": cfg["base_url"],
        "ws_url": cfg["ws_url"],
        "config_file": str(exchange_config_file_path()),
        "config_file_exists": exchange_config_file_path().exists(),
        "diagnostics": diagnostics,
        "json_details": file_payload or {},
    }


def exchange_keys_present(mode: str) -> bool:
    return bool(load_exchange_credentials(mode).get("has_keys"))


def _exchange_timeout_seconds() -> float:
    settings = json_load(SETTINGS_PATH, {})
    timeout_ms = settings.get("execution", {}).get("request_timeout_ms", 4000)
    try:
        timeout = max(1.0, min(float(timeout_ms) / 1000.0, 15.0))
    except Exception:
        timeout = 4.0
    return timeout


def _parse_json_response(response: requests.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"raw": response.text[:500]}


def _classify_exchange_error(status_code: int, payload: Any) -> tuple[str, str]:
    if isinstance(payload, dict):
        code = payload.get("code")
        msg = str(payload.get("msg", "")).strip()
        lower = msg.lower()
        if code in {-2015, -2014, -1022}:
            return "auth", f"Keys invalidas/permisos/IP restriction ({code}): {msg}"
        if code in {-1003} or status_code == 429:
            return "rate_limit", f"Rate limit ({code}): {msg or 'Too many requests'}"
        if "sapi" in lower:
            return "sapi_unsupported", f"sapi unsupported: {msg}"
        if code in {-2010, -2011, -1013, -1100, -1102}:
            return "permissions", f"Permisos o parametros invalidos ({code}): {msg}"
    if status_code == 451:
        return "provider_restriction", "Proveedor/exchange restringe la region o red de salida (HTTP 451). ProbÃ¡ otro despliegue/VPS/proxy permitido."
    if status_code >= 500:
        return "endpoint", f"Endpoint no disponible (HTTP {status_code})"
    return "endpoint", f"Error de endpoint/auth (HTTP {status_code})"


def _probe_ws_endpoint(ws_url: str, timeout_sec: float) -> tuple[bool, str]:
    parsed = urlparse(ws_url)
    host = parsed.hostname
    if not host:
        return False, f"WS endpoint invalido: {ws_url}"
    port = parsed.port or (443 if parsed.scheme in {"wss", "https"} else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True, ""
    except socket.timeout:
        return False, f"WS timeout ({ws_url})"
    except Exception as exc:
        return False, f"WS error ({ws_url}): {exc}"


def _binance_signed_request(
    *,
    method: str,
    base_url: str,
    path: str,
    api_key: str,
    api_secret: str,
    params: dict[str, Any],
    timeout_sec: float,
) -> tuple[bool, dict[str, Any]]:
    query_payload: dict[str, Any] = {**params, "timestamp": int(time.time() * 1000), "recvWindow": 5000}
    query = urlencode(query_payload, doseq=True)
    signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{base_url.rstrip('/')}{path}?{query}&signature={signature}"
    response = requests.request(
        method=method,
        url=url,
        headers={"X-MBX-APIKEY": api_key},
        timeout=timeout_sec,
    )
    payload = _parse_json_response(response)
    return response.ok, {
        "status_code": response.status_code,
        "payload": payload,
        "url": f"{base_url.rstrip('/')}{path}",
    }


_EXCHANGE_DIAG_CACHE: dict[str, Any] = {"mode": "", "checked_at_epoch": 0.0, "result": None}
_BOTS_OVERVIEW_CACHE: dict[str, Any] = {"entries": {}}
_BOTS_OVERVIEW_CACHE_LOCK = Lock()
_BOTS_OVERVIEW_LAST_SLOW_LOG_EPOCH = 0.0
_INTERNAL_HEADER_ALERT_CACHE: dict[str, float] = {}
_INTERNAL_HEADER_ALERT_LOCK = Lock()


def _provider_restriction_action_plan(active_mode: str, exchange: str) -> list[str]:
    mode_label = (active_mode or "testnet").upper()
    exch = (exchange or "binance").lower()
    target = "Binance Spot Testnet" if exch == "binance" and active_mode == "testnet" else f"{exch} ({mode_label})"
    return [
        f"No es un bug del bot: {target} estÃ¡ bloqueando la red/regiÃ³n de salida del backend (HTTP 451).",
        "ProbÃ¡ el backend localmente (tu PC) para validar claves y place/cancel.",
        "Si en local funciona, movÃ© el backend a otra regiÃ³n/proveedor (VPS/Cloud) con egress permitido.",
        "MantenÃ© Vercel solo para frontend; el bloqueo es del backend (Railway/egress), no de la UI.",
    ]


def diagnose_exchange(mode: str | None = None, *, force_refresh: bool = False) -> dict[str, Any]:
    active_mode = (mode or store.load_bot_state().get("mode") or default_mode()).lower()
    now_epoch = time.time()
    cached = _EXCHANGE_DIAG_CACHE.get("result")
    if (
        not force_refresh
        and cached
        and _EXCHANGE_DIAG_CACHE.get("mode") == active_mode
        and (now_epoch - float(_EXCHANGE_DIAG_CACHE.get("checked_at_epoch", 0.0))) < EXCHANGE_DIAG_CACHE_TTL_SEC
    ):
        return cached

    creds = load_exchange_credentials(active_mode)
    timeout_sec = _exchange_timeout_seconds()
    checks: dict[str, Any] = {}
    last_error = ""
    connector_ok = False
    order_ok = False
    connector_reason = ""
    order_reason = ""

    if active_mode == "paper":
        checks["paper"] = {"ok": True, "detail": "Paper broker operativo para place/cancel."}
        result = {
            "ok": True,
            "mode": active_mode,
            "exchange": creds["exchange"],
            "base_url": creds["base_url"],
            "ws_url": creds["ws_url"],
            "has_keys": creds["has_keys"],
            "key_source": creds["key_source"],
            "missing": creds["missing_env_vars"],
            "expected_env_vars": creds["expected_env_vars"],
            "last_error": "",
            "checks": checks,
            "connector_ok": True,
            "connector_reason": "Paper connector listo (simulador).",
            "order_ok": True,
            "order_reason": "Paper place/cancel operativo.",
            "diagnostics": creds["diagnostics"],
        }
        _EXCHANGE_DIAG_CACHE.update({"mode": active_mode, "checked_at_epoch": now_epoch, "result": result})
        return result

    if not creds["has_keys"]:
        if running_on_railway():
            last_error = f"Faltan env vars {creds['missing_env_vars']}. Cargarlas en Railway -> Service Variables."
        elif allow_local_exchange_file_fallback() and not creds["config_file_exists"]:
            last_error = f"JSON no encontrado en contenedor: {creds['config_file']}"
        else:
            last_error = f"Faltan credenciales para {active_mode}."
        checks["credentials"] = {
            "ok": False,
            "reason": last_error,
            "missing_env_vars": creds["missing_env_vars"],
            "key_source": creds["key_source"],
        }
        result = {
            "ok": False,
            "mode": active_mode,
            "exchange": creds["exchange"],
            "base_url": creds["base_url"],
            "ws_url": creds["ws_url"],
            "has_keys": False,
            "key_source": creds["key_source"],
            "missing": creds["missing_env_vars"],
            "expected_env_vars": creds["expected_env_vars"],
            "last_error": last_error,
            "checks": checks,
            "connector_ok": False,
            "connector_reason": last_error,
            "order_ok": False,
            "order_reason": "Cannot place/cancel on testnet: credenciales faltantes.",
            "diagnostics": creds["diagnostics"],
        }
        _EXCHANGE_DIAG_CACHE.update({"mode": active_mode, "checked_at_epoch": now_epoch, "result": result})
        return result

    time_url = f"{creds['base_url'].rstrip('/')}/api/v3/time"
    try:
        response = requests.get(time_url, timeout=timeout_sec)
        payload = _parse_json_response(response)
        checks["time"] = {"ok": bool(response.ok), "status_code": response.status_code, "endpoint": time_url}
        if not response.ok:
            category, detail = _classify_exchange_error(response.status_code, payload)
            checks["time"]["error_type"] = category
            checks["time"]["error"] = detail
            last_error = detail
    except requests.Timeout:
        checks["time"] = {"ok": False, "status_code": 0, "endpoint": time_url, "error_type": "timeout", "error": f"Timeout en {time_url}"}
        last_error = checks["time"]["error"]
    except Exception as exc:
        checks["time"] = {"ok": False, "status_code": 0, "endpoint": time_url, "error_type": "endpoint", "error": str(exc)}
        last_error = str(exc)

    ws_ok, ws_error = _probe_ws_endpoint(creds["ws_url"], timeout_sec)
    checks["ws"] = {"ok": ws_ok, "endpoint": creds["ws_url"], "error": ws_error}
    if not ws_ok and not last_error:
        last_error = ws_error

    account_ok = False
    account_result: dict[str, Any] = {}
    try:
        account_ok, account_result = _binance_signed_request(
            method="GET",
            base_url=creds["base_url"],
            path="/api/v3/account",
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            params={},
            timeout_sec=timeout_sec,
        )
        checks["account"] = {"ok": account_ok, "status_code": account_result["status_code"], "endpoint": account_result["url"]}
        if not account_ok:
            category, detail = _classify_exchange_error(account_result["status_code"], account_result["payload"])
            checks["account"]["error_type"] = category
            checks["account"]["error"] = detail
            if not last_error:
                last_error = detail
    except requests.Timeout:
        checks["account"] = {"ok": False, "status_code": 0, "endpoint": f"{creds['base_url']}/api/v3/account", "error_type": "timeout", "error": "Timeout auth account"}
        if not last_error:
            last_error = checks["account"]["error"]
    except Exception as exc:
        checks["account"] = {"ok": False, "status_code": 0, "endpoint": f"{creds['base_url']}/api/v3/account", "error_type": "auth", "error": str(exc)}
        if not last_error:
            last_error = str(exc)

    symbol = get_env("BINANCE_TESTNET_TEST_SYMBOL", "BTCUSDT")
    quote_qty = get_env("BINANCE_TESTNET_TEST_QUOTE_QTY", "15")
    if account_ok:
        try:
            order_ok, order_result = _binance_signed_request(
                method="POST",
                base_url=creds["base_url"],
                path="/api/v3/order/test",
                api_key=creds["api_key"],
                api_secret=creds["api_secret"],
                params={"symbol": symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": quote_qty},
                timeout_sec=timeout_sec,
            )
            checks["order_test"] = {"ok": order_ok, "status_code": order_result["status_code"], "endpoint": order_result["url"], "symbol": symbol}
            if not order_ok:
                category, detail = _classify_exchange_error(order_result["status_code"], order_result["payload"])
                checks["order_test"]["error_type"] = category
                checks["order_test"]["error"] = detail
                if not last_error:
                    last_error = detail
        except requests.Timeout:
            checks["order_test"] = {"ok": False, "status_code": 0, "endpoint": f"{creds['base_url']}/api/v3/order/test", "symbol": symbol, "error_type": "timeout", "error": "Timeout order test"}
            if not last_error:
                last_error = checks["order_test"]["error"]
        except Exception as exc:
            checks["order_test"] = {"ok": False, "status_code": 0, "endpoint": f"{creds['base_url']}/api/v3/order/test", "symbol": symbol, "error_type": "endpoint", "error": str(exc)}
            if not last_error:
                last_error = str(exc)
    else:
        checks["order_test"] = {
            "ok": False,
            "status_code": 0,
            "endpoint": f"{creds['base_url']}/api/v3/order/test",
            "symbol": symbol,
            "error_type": "auth",
            "error": "Order test omitido por fallo de autenticacion.",
        }

    connector_ok = bool(checks.get("time", {}).get("ok") and checks.get("ws", {}).get("ok") and checks.get("account", {}).get("ok"))
    order_ok = bool(checks.get("order_test", {}).get("ok"))
    provider_restriction_checks = [
        key for key, value in checks.items() if isinstance(value, dict) and str(value.get("error_type") or "") == "provider_restriction"
    ]
    infrastructure_blocked = bool(provider_restriction_checks)
    action_required = _provider_restriction_action_plan(active_mode, str(creds.get("exchange") or "")) if infrastructure_blocked else []

    if connector_ok:
        connector_reason = "Exchange connector listo."
    else:
        connector_reason = (
            "Conector bloqueado por restricciÃ³n del proveedor/regiÃ³n (HTTP 451)."
            if infrastructure_blocked
            else (last_error or "Exchange connector no listo.")
        )

    if order_ok:
        order_reason = "Place/cancel testnet operativo."
    else:
        order_reason = (
            "Order test bloqueado por restricciÃ³n del proveedor/regiÃ³n (HTTP 451)."
            if infrastructure_blocked
            else (checks.get("order_test", {}).get("error") or "Cannot place/cancel on testnet.")
        )

    result = {
        "ok": bool(connector_ok and (order_ok or active_mode == "paper")),
        "mode": active_mode,
        "exchange": creds["exchange"],
        "base_url": creds["base_url"],
        "ws_url": creds["ws_url"],
        "has_keys": True,
        "key_source": creds["key_source"],
        "missing": creds["missing_env_vars"],
        "expected_env_vars": creds["expected_env_vars"],
        "last_error": last_error,
        "checks": checks,
        "connector_ok": connector_ok,
        "connector_reason": connector_reason,
        "order_ok": order_ok,
        "order_reason": order_reason,
        "infrastructure_blocked": infrastructure_blocked,
        "provider_restriction_checks": provider_restriction_checks,
        "action_required": action_required,
        "diagnostics": creds["diagnostics"],
    }
    _EXCHANGE_DIAG_CACHE.update({"mode": active_mode, "checked_at_epoch": now_epoch, "result": result})
    return result


def ensure_paths() -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    STRATEGY_PACKS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    (USER_DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    (USER_DATA_DIR / "backtests").mkdir(parents=True, exist_ok=True)
    (USER_DATA_DIR / "instruments").mkdir(parents=True, exist_ok=True)


class ConsoleStore:
    def __init__(self) -> None:
        ensure_paths()
        self.registry = RegistryDB(REGISTRY_DB_PATH)
        self.strategy_truth = StrategyTruthRepository(meta_path=STRATEGY_META_PATH)
        self.strategy_evidence = StrategyEvidenceRepository(
            runs_path=RUNS_PATH,
            experience_store=ExperienceStore(self.registry),
        )
        self.policy_state = BotPolicyStateRepository(
            settings_path=SETTINGS_PATH,
            bot_state_path=BOT_STATE_PATH,
            bots_path=BOTS_PATH,
            default_mode=default_mode,
            exchange_name=exchange_name,
            exchange_keys_present=exchange_keys_present,
            get_env=get_env,
            runtime_engine_default=runtime_engine_default,
            runtime_engine_real=RUNTIME_ENGINE_REAL,
            runtime_engine_simulated=RUNTIME_ENGINE_SIMULATED,
            runtime_contract_version=RUNTIME_CONTRACT_VERSION,
            runtime_telemetry_source_synthetic=RUNTIME_TELEMETRY_SOURCE_SYNTHETIC,
            runtime_telemetry_source_real=RUNTIME_TELEMETRY_SOURCE_REAL,
        )
        self.decision_log = BotDecisionLogRepository(
            db_path=CONSOLE_DB_PATH,
            schema_sql=LOG_SCHEMA_SQL,
            backfill_max_rows=BOTS_LOGS_REF_BACKFILL_MAX_ROWS,
            integrity_window_hours=BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS,
            unknown_ratio_warn=BREAKER_EVENTS_UNKNOWN_RATIO_WARN,
            unknown_min_events=BREAKER_EVENTS_UNKNOWN_MIN_EVENTS,
        )
        self.backtest_catalog = BacktestCatalogDB(BACKTEST_CATALOG_DB_PATH)
        self.cost_model_resolver = CostModelResolver(catalog=self.backtest_catalog, policies_root=CONFIG_POLICIES_ROOT)
        self.fundamentals_filter = FundamentalsCreditFilter(catalog=self.backtest_catalog, policies_root=CONFIG_POLICIES_ROOT)
        self.instrument_registry = BinanceInstrumentRegistryService(
            db_path=INSTRUMENT_REGISTRY_DB_PATH,
            repo_root=MONOREPO_ROOT,
            explicit_policy_root=DEFAULT_CONFIG_POLICIES_ROOT,
        )
        self.instrument_universes = InstrumentUniverseService(self.instrument_registry)
        self.reporting_bridge = ReportingBridgeService(
            user_data_dir=USER_DATA_DIR,
            repo_root=MONOREPO_ROOT,
            explicit_policy_root=DEFAULT_CONFIG_POLICIES_ROOT,
            instrument_registry_service=self.instrument_registry,
            runs_path=RUNS_PATH,
        )
        self.execution_reality = ExecutionRealityService(
            user_data_dir=USER_DATA_DIR,
            repo_root=MONOREPO_ROOT,
            explicit_policy_root=DEFAULT_CONFIG_POLICIES_ROOT,
            instrument_registry_service=self.instrument_registry,
            universe_service=self.instrument_universes,
            reporting_bridge_service=self.reporting_bridge,
            runs_loader=self.load_runs,
        )
        self.instrument_registry_startup_sync: dict[str, Any] = {
            "ok": True,
            "startup": True,
            "skipped": True,
            "reason": "not_run",
        }
        self._init_console_db()
        self._ensure_defaults()

    def record_experience_run(
        self,
        run: dict[str, Any],
        *,
        source_override: str | None = None,
        bot_id: str | None = None,
    ) -> dict[str, Any] | None:
        return self.strategy_evidence.record_run(run, source_override=source_override, bot_id=bot_id)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(CONSOLE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_console_db(self) -> None:
        self.decision_log.initialize()

    def _ensure_console_db_migrations(self, conn: sqlite3.Connection) -> None:
        columns = {str(row["name"] or "").strip() for row in conn.execute("PRAGMA table_info(logs)").fetchall()}
        if "has_bot_ref" not in columns:
            conn.execute("ALTER TABLE logs ADD COLUMN has_bot_ref INTEGER NOT NULL DEFAULT 0")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_has_bot_ref_id ON logs(has_bot_ref, id DESC)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS log_bot_refs (
                log_id INTEGER NOT NULL,
                bot_id TEXT NOT NULL,
                PRIMARY KEY (log_id, bot_id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_log_bot_refs_bot_id_log_id ON log_bot_refs(bot_id, log_id DESC)")
        self._backfill_logs_has_bot_ref(conn)
        self._backfill_log_bot_refs(conn)

    def _backfill_logs_has_bot_ref(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT MAX(id) AS max_id FROM logs").fetchone()
        max_id = int((row["max_id"] if row is not None else 0) or 0)
        if max_id <= 0:
            return
        min_id = max(1, max_id - int(BOTS_LOGS_REF_BACKFILL_MAX_ROWS) + 1)
        conn.execute(
            """
            UPDATE logs
            SET has_bot_ref = 1
            WHERE id >= ?
              AND has_bot_ref = 0
              AND (
                  related_ids LIKE '%BOT-%'
                  OR payload_json LIKE '%"bot_id"%'
              )
            """,
            (min_id,),
        )

    def _backfill_log_bot_refs(self, conn: sqlite3.Connection) -> None:
        row = conn.execute("SELECT MAX(id) AS max_id FROM logs").fetchone()
        max_id = int((row["max_id"] if row is not None else 0) or 0)
        if max_id <= 0:
            return
        limit_rows = int(BOTS_LOGS_REF_BACKFILL_MAX_ROWS)
        min_id = max(1, max_id - limit_rows + 1)
        rows = conn.execute(
            """
            SELECT id, related_ids, payload_json
            FROM logs
            WHERE id >= ?
              AND id NOT IN (SELECT log_id FROM log_bot_refs)
            ORDER BY id DESC
            LIMIT ?
            """,
            (min_id, limit_rows),
        ).fetchall()
        inserts: list[tuple[int, str]] = []
        for row in rows:
            related_raw = row["related_ids"] if row["related_ids"] is not None else "[]"
            payload_raw = row["payload_json"] if row["payload_json"] is not None else "{}"
            try:
                related_ids = json.loads(related_raw)
            except Exception:
                related_ids = []
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {}
            refs = self._extract_bot_refs_from_log(
                related_ids if isinstance(related_ids, list) else [],
                payload if isinstance(payload, dict) else {},
            )
            if not refs:
                continue
            log_id = int(row["id"])
            for bot_id in refs:
                inserts.append((log_id, bot_id))
        if inserts:
            conn.executemany(
                "INSERT OR IGNORE INTO log_bot_refs (log_id, bot_id) VALUES (?, ?)",
                inserts,
            )

    @staticmethod
    def _normalize_log_bot_ref(value: Any) -> str:
        ref = str(value or "").strip()
        if not ref:
            return ""
        return ref.upper() if ref.upper().startswith("BOT-") else ref

    @classmethod
    def _extract_bot_refs_from_log(cls, related_ids: list[str], payload: dict[str, Any]) -> set[str]:
        refs: set[str] = set()
        payload_map = payload if isinstance(payload, dict) else {}
        bot_id = cls._normalize_log_bot_ref(payload_map.get("bot_id"))
        if bot_id:
            refs.add(bot_id)
        bot_ids = payload_map.get("bot_ids")
        if isinstance(bot_ids, list):
            for item in bot_ids:
                item_id = cls._normalize_log_bot_ref(item)
                if item_id:
                    refs.add(item_id)
        if isinstance(related_ids, list):
            for rid in related_ids:
                item_id = cls._normalize_log_bot_ref(rid)
                if item_id and item_id.upper().startswith("BOT-"):
                    refs.add(item_id)
        return refs

    @staticmethod
    def _log_has_bot_ref(related_ids: list[str], payload: dict[str, Any]) -> bool:
        return bool(ConsoleStore._extract_bot_refs_from_log(related_ids, payload))

    @classmethod
    def _log_targets_bot(cls, log_row: dict[str, Any], bot_id: str) -> bool:
        if not isinstance(log_row, dict):
            return False
        refs = cls._extract_bot_refs_from_log(
            log_row.get("related_ids") if isinstance(log_row.get("related_ids"), list) else [],
            log_row.get("payload") if isinstance(log_row.get("payload"), dict) else {},
        )
        return str(bot_id or "").strip() in refs

    @staticmethod
    def _normalize_breaker_mode(value: str | None) -> str:
        mode = str(value or "").strip().lower()
        if mode in {"shadow", "paper", "testnet", "live"}:
            return mode
        return "unknown"

    @staticmethod
    def _normalize_breaker_bot_id(value: str | None) -> str:
        bot_id = str(value or "").strip()
        return bot_id if bot_id else "unknown_bot"

    def _insert_breaker_event(
        self,
        conn: sqlite3.Connection,
        *,
        ts: str,
        bot_id: str | None,
        mode: str | None,
        reason: str | None,
        run_id: str | None = None,
        symbol: str | None = None,
        source_log_id: int | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO breaker_events (ts, bot_id, mode, reason, run_id, symbol, source_log_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ts or utc_now_iso()),
                self._normalize_breaker_bot_id(bot_id),
                self._normalize_breaker_mode(mode),
                str(reason or "breaker_triggered"),
                str(run_id).strip() if run_id is not None and str(run_id).strip() else None,
                str(symbol).strip().upper() if symbol is not None and str(symbol).strip() else None,
                int(source_log_id) if source_log_id is not None else None,
            ),
        )

    def _backfill_breaker_events_from_logs(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT id, ts, message, payload_json
            FROM logs
            WHERE type = 'breaker_triggered'
              AND id NOT IN (
                  SELECT source_log_id
                  FROM breaker_events
                  WHERE source_log_id IS NOT NULL
              )
            ORDER BY id ASC
            """
        ).fetchall()
        for row in rows:
            payload_raw = row["payload_json"] if row["payload_json"] is not None else "{}"
            try:
                payload = json.loads(payload_raw)
            except Exception:
                payload = {}
            payload_map = payload if isinstance(payload, dict) else {}
            self._insert_breaker_event(
                conn,
                ts=str(row["ts"] or utc_now_iso()),
                bot_id=str(payload_map.get("bot_id") or ""),
                mode=str(payload_map.get("mode") or ""),
                reason=str(payload_map.get("reason") or row["message"] or "breaker_triggered"),
                run_id=str(payload_map.get("run_id") or ""),
                symbol=str(payload_map.get("symbol") or ""),
                source_log_id=int(row["id"]),
            )

    def breaker_events_integrity(self, *, window_hours: int | None = None, strict: bool = True) -> dict[str, Any]:
        return self.decision_log.breaker_events_integrity(window_hours=window_hours, strict=strict)
    def _ensure_defaults(self) -> None:
        self._ensure_default_settings()
        self._ensure_default_bot_state()
        self._ensure_default_strategy()
        self._ensure_knowledge_strategies_registry()
        self._ensure_strategy_registry_invariants()
        self._ensure_default_bots()
        self._ensure_seed_backtest()
        self._sync_backtest_runs_catalog()
        try:
            self.reporting_bridge.refresh_materialized_views(self.load_runs())
        except Exception:
            pass
        self.add_log(
            event_type="health",
            severity="info",
            module="bootstrap",
            message="Console API initialized",
            related_ids=[],
            payload={"version": APP_VERSION},
        )

    def _ensure_default_settings(self) -> None:
        self.policy_state.save_settings(self.policy_state.load_settings())

    def _ensure_default_bot_state(self) -> None:
        self.policy_state.ensure_default_bot_state()

    def _write_default_strategy_pack(self) -> Path:
        target = UPLOADS_DIR / f"{DEFAULT_STRATEGY_ID}_{DEFAULT_STRATEGY_VERSION}.zip"
        if target.exists():
            return target
        strategy_yaml = {
            "id": DEFAULT_STRATEGY_ID,
            "name": DEFAULT_STRATEGY_NAME,
            "version": DEFAULT_STRATEGY_VERSION,
            "description": DEFAULT_STRATEGY_DESCRIPTION,
            "parameters_schema": DEFAULT_PARAMS_SCHEMA,
        }
        strategy_py = """def generate_signals(context):
    return {\"action\": \"flat\"}

def on_bar(context):
    return None

def on_trade(context):
    return None

def risk_hooks(context):
    return {\"allowed\": True}
"""
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("strategy.yaml", yaml.safe_dump(strategy_yaml, sort_keys=False))
            archive.writestr("strategy.py", strategy_py)
            archive.writestr("README.md", "# Default strategy pack\n")
        return target

    def _ensure_default_strategy(self) -> None:
        metadata = self.load_strategy_meta()
        if DEFAULT_STRATEGY_ID not in metadata:
            package_path = self._write_default_strategy_pack()
            db_strategy_id = self.registry.upsert_strategy(
                name=DEFAULT_STRATEGY_ID,
                version=DEFAULT_STRATEGY_VERSION,
                path=str(package_path),
                sha256=hashlib.sha256(package_path.read_bytes()).hexdigest(),
                status="enabled",
                notes="Default strategy auto-created at boot.",
            )
            metadata[DEFAULT_STRATEGY_ID] = {
                "id": DEFAULT_STRATEGY_ID,
                "name": DEFAULT_STRATEGY_NAME,
                "version": DEFAULT_STRATEGY_VERSION,
                "description": DEFAULT_STRATEGY_DESCRIPTION,
                "enabled": True,
                "notes": "Default bootstrap strategy",
                "tags": ["trend", "pullback", "orderflow"],
                "params_yaml": DEFAULT_PARAMS_YAML,
                "parameters_schema": DEFAULT_PARAMS_SCHEMA,
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
                "last_run_at": None,
                "db_strategy_id": db_strategy_id,
            }
            self.save_strategy_meta(metadata)
            self.add_log(
                event_type="strategy_changed",
                severity="warn",
                module="registry",
                message="Default strategy auto-registered (paper/testnet primary).",
                related_ids=[DEFAULT_STRATEGY_ID],
                payload={"live_blocked": True},
            )

        strategy = metadata[DEFAULT_STRATEGY_ID]
        strategy_id = int(strategy["db_strategy_id"])
        if not self.registry.get_principal("paper"):
            self.registry.set_principal(strategy_id, "paper")
            self.add_log(
                event_type="strategy_changed",
                severity="info",
                module="registry",
                message="Primary strategy set for paper.",
                related_ids=[DEFAULT_STRATEGY_ID],
                payload={"mode": "paper"},
            )
        if not self.registry.get_principal("testnet"):
            self.registry.set_principal(strategy_id, "testnet")
            self.add_log(
                event_type="strategy_changed",
                severity="info",
                module="registry",
                message="Primary strategy set for testnet.",
                related_ids=[DEFAULT_STRATEGY_ID],
                payload={"mode": "testnet"},
            )

    def _knowledge_loader(self) -> KnowledgeLoader:
        return KnowledgeLoader(repo_root=MONOREPO_ROOT)

    def _build_knowledge_default_params(self, base_strategy_id: str) -> dict[str, Any]:
        try:
            knowledge = self._knowledge_loader().load()
        except Exception:
            return {}
        template = next((t for t in knowledge.templates if str(t.get("base_strategy_id")) == base_strategy_id), None)
        if not template:
            return {}
        ranges = knowledge.ranges.get(str(template.get("id")), {})
        if not isinstance(ranges, dict):
            return {}
        out: dict[str, Any] = {}
        for key, spec in ranges.items():
            if isinstance(spec, dict) and isinstance(spec.get("min"), (int, float)) and isinstance(spec.get("max"), (int, float)):
                vmin = float(spec["min"])
                vmax = float(spec["max"])
                mid = (vmin + vmax) / 2.0
                step = spec.get("step")
                if isinstance(step, (int, float)) and float(step) > 0:
                    steps = round((mid - vmin) / float(step))
                    mid = vmin + steps * float(step)
                out[str(key)] = int(mid) if float(mid).is_integer() else round(mid, 6)
        return out

    def _ensure_knowledge_strategies_registry(self) -> None:
        try:
            knowledge = self._knowledge_loader().get_strategies_v2()
        except Exception:
            return
        strategies = knowledge.get("strategies") if isinstance(knowledge, dict) else []
        if not isinstance(strategies, list):
            return
        metadata = self.load_strategy_meta()
        for idx, spec in enumerate(strategies):
            if not isinstance(spec, dict):
                continue
            strategy_id = str(spec.get("id") or "").strip()
            if not strategy_id:
                continue
            name = str(spec.get("name") or strategy_id)
            version = "2.0.0"
            tags = [str(x) for x in (spec.get("inputs", {}) or {}).get("indicators", [])] if isinstance(spec.get("inputs"), dict) else []
            tags = [str(x) for x in (spec.get("inputs", []) if isinstance(spec.get("inputs"), list) else tags)] if not tags else tags
            tags = [str(x) for x in (spec.get("tags") or [])] or [str(spec.get("intent") or "knowledge"), "knowledge"]
            description = str(spec.get("intent") or spec.get("description") or "Knowledge Pack v2 strategy")
            pseudo_path = f"knowledge/strategies/{strategy_id}.yaml"
            pseudo_bytes = json.dumps(spec, sort_keys=True).encode("utf-8")
            db_strategy_id = None
            if strategy_id in metadata:
                db_strategy_id = int(metadata[strategy_id].get("db_strategy_id") or 0) or None
            if not db_strategy_id:
                db_strategy_id = self.registry.upsert_strategy(
                    name=strategy_id,
                    version=version,
                    path=pseudo_path,
                    sha256=hashlib.sha256(pseudo_bytes).hexdigest(),
                    status="enabled",
                    notes="Seeded from knowledge pack v2",
                )
            defaults = self._build_knowledge_default_params(strategy_id)
            metadata[strategy_id] = {
                **metadata.get(strategy_id, {}),
                "id": strategy_id,
                "name": name,
                "version": metadata.get(strategy_id, {}).get("version", version),
                "description": description,
                "enabled": bool(metadata.get(strategy_id, {}).get("enabled", True)),
                "notes": str(metadata.get(strategy_id, {}).get("notes") or "Knowledge Pack v2"),
                "tags": list({*([str(x) for x in metadata.get(strategy_id, {}).get("tags", [])]), *[str(x) for x in tags], "knowledge"}),
                "params_yaml": metadata.get(strategy_id, {}).get("params_yaml") or (yaml.safe_dump(defaults, sort_keys=False) if defaults else DEFAULT_PARAMS_YAML),
                "parameters_schema": metadata.get(strategy_id, {}).get("parameters_schema") or {"type": "object", "properties": {}},
                "created_at": metadata.get(strategy_id, {}).get("created_at") or utc_now_iso(),
                "updated_at": utc_now_iso(),
                "last_run_at": metadata.get(strategy_id, {}).get("last_run_at"),
                "db_strategy_id": db_strategy_id,
                "source": "knowledge",
            }
            self.registry.upsert_strategy_registry(
                strategy_key=strategy_id,
                name=name,
                version=str(metadata[strategy_id].get("version") or version),
                source="knowledge",
                status="active",
                enabled_for_trading=bool(metadata[strategy_id].get("enabled", True)),
                allow_learning=bool(metadata[strategy_id].get("allow_learning", True)),
                is_primary=bool(metadata[strategy_id].get("is_primary", idx == 0)),
                tags=[str(x) for x in metadata[strategy_id].get("tags", [])],
            )
            reg_row = self.registry.get_strategy_registry(strategy_id) or {}
            metadata[strategy_id]["allow_learning"] = bool(reg_row.get("allow_learning", True))
            metadata[strategy_id]["is_primary"] = bool(reg_row.get("is_primary", False))
            metadata[strategy_id]["status"] = str(reg_row.get("status", "active"))
        # Ensure bootstrap/default strategy is also represented in the persistent registry.
        default_meta = metadata.get(DEFAULT_STRATEGY_ID)
        if isinstance(default_meta, dict):
            self.registry.upsert_strategy_registry(
                strategy_key=DEFAULT_STRATEGY_ID,
                name=str(default_meta.get("name") or DEFAULT_STRATEGY_ID),
                version=str(default_meta.get("version") or DEFAULT_STRATEGY_VERSION),
                source=str(default_meta.get("source") or "uploaded"),
                status="active" if bool(default_meta.get("enabled", True)) else "disabled",
                enabled_for_trading=bool(default_meta.get("enabled", True)),
                allow_learning=bool(default_meta.get("allow_learning", True)),
                is_primary=bool(default_meta.get("is_primary", False)),
                tags=[str(x) for x in default_meta.get("tags", [])],
            )
        self.save_strategy_meta(metadata)

    def _ensure_strategy_registry_invariants(self) -> None:
        metadata = self.load_strategy_meta()
        # Backfill rows for legacy strategies created before strategy_registry table existed.
        for strategy_id, meta in metadata.items():
            if not isinstance(meta, dict):
                continue
            if self.registry.get_strategy_registry(strategy_id):
                continue
            self.registry.upsert_strategy_registry(
                strategy_key=strategy_id,
                name=str(meta.get("name") or strategy_id),
                version=str(meta.get("version") or "0.0.0"),
                source=str(meta.get("source") or "uploaded"),
                status=str(meta.get("status") or ("active" if bool(meta.get("enabled", False)) else "disabled")),
                enabled_for_trading=bool(meta.get("enabled", False)),
                allow_learning=bool(meta.get("allow_learning", True)),
                is_primary=bool(meta.get("is_primary", False)),
                tags=[str(x) for x in meta.get("tags", [])],
            )
        self.registry.ensure_registry_primary()
        rows = self.registry.list_strategy_registry()
        if not rows:
            return
        if self.registry.enabled_for_trading_count() == 0:
            first = rows[0]
            self.registry.patch_strategy_registry(first["id"], enabled_for_trading=True, status="active")
        self.registry.ensure_registry_primary()
        rows = self.registry.list_strategy_registry()
        for row in rows:
            meta = metadata.get(str(row["id"]))
            if not isinstance(meta, dict):
                continue
            meta["enabled"] = bool(row.get("enabled_for_trading", meta.get("enabled", False)))
            meta["allow_learning"] = bool(row.get("allow_learning", meta.get("allow_learning", True)))
            meta["is_primary"] = bool(row.get("is_primary", meta.get("is_primary", False)))
            meta["status"] = str(row.get("status") or meta.get("status") or ("active" if meta.get("enabled") else "disabled"))
            meta["source"] = str(row.get("source") or meta.get("source") or "uploaded")
            meta["updated_at"] = utc_now_iso()
            metadata[str(row["id"])] = meta
        self.save_strategy_meta(metadata)

    def patch_strategy_registry_flags(
        self,
        strategy_id: str,
        *,
        enabled_for_trading: bool | None = None,
        allow_learning: bool | None = None,
        is_primary: bool | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        metadata = self.load_strategy_meta()
        meta = metadata.get(strategy_id)
        if not isinstance(meta, dict):
            raise HTTPException(status_code=404, detail="Strategy not found")
        current = self.registry.get_strategy_registry(strategy_id)
        if not current:
            self.registry.upsert_strategy_registry(
                strategy_key=strategy_id,
                name=str(meta.get("name") or strategy_id),
                version=str(meta.get("version") or "0.0.0"),
                source=str(meta.get("source") or "uploaded"),
                status=str(meta.get("status") or ("active" if bool(meta.get("enabled", False)) else "disabled")),
                enabled_for_trading=bool(meta.get("enabled", False)),
                allow_learning=bool(meta.get("allow_learning", True)),
                is_primary=bool(meta.get("is_primary", False)),
                tags=[str(x) for x in meta.get("tags", [])],
            )
            current = self.registry.get_strategy_registry(strategy_id)
        if not current:
            raise HTTPException(status_code=404, detail="Strategy registry row not found")
        target_enabled = current["enabled_for_trading"] if enabled_for_trading is None else bool(enabled_for_trading)
        target_status = current["status"] if status is None else str(status)
        if target_status not in {"active", "disabled", "archived"}:
            raise HTTPException(status_code=400, detail="Invalid status")
        if target_status == "archived":
            target_enabled = False
            is_primary = False if is_primary is None else is_primary
        if current["enabled_for_trading"] and not target_enabled and self.registry.enabled_for_trading_count() <= 1:
            raise HTTPException(status_code=400, detail="Debe existir al menos 1 estrategia activa para trading")
        patched = self.registry.patch_strategy_registry(
            strategy_id,
            status=target_status,
            enabled_for_trading=target_enabled,
            allow_learning=allow_learning,
            is_primary=is_primary,
        )
        if not patched:
            raise HTTPException(status_code=404, detail="Strategy registry row not found")
        self._ensure_strategy_registry_invariants()
        self.add_log(
            event_type="strategy_changed",
            severity="info",
            module="registry",
            message=f"Registry flags actualizados para {strategy_id}.",
            related_ids=[strategy_id],
            payload={
                "enabled_for_trading": patched.get("enabled_for_trading"),
                "allow_learning": patched.get("allow_learning"),
                "is_primary": patched.get("is_primary"),
                "status": patched.get("status"),
            },
        )
        return self.strategy_or_404(strategy_id)

    def _parse_iso_dt(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            try:
                parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
            except Exception:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _run_matches_filters(self, run: dict[str, Any], *, from_ts: str | None, to_ts: str | None, mode: str | None) -> bool:
        run_mode = str(run.get("mode") or "backtest").lower()
        if mode and run_mode != mode.lower():
            return False
        created = self._parse_iso_dt(str(run.get("created_at") or "")) or self._parse_iso_dt(str((run.get("period") or {}).get("end") or ""))
        start_bound = self._parse_iso_dt(from_ts)
        end_bound = self._parse_iso_dt(to_ts)
        if created and start_bound and created < start_bound:
            return False
        if created and end_bound and created > end_bound:
            return False
        return True

    def _aggregate_strategy_kpis(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        all_trades: list[dict[str, Any]] = []
        gross_pnl = 0.0
        net_pnl = 0.0
        costs_total = 0.0
        fees_total = 0.0
        spread_total = 0.0
        slippage_total = 0.0
        funding_total = 0.0
        trade_weight = 0
        sharpe_acc = 0.0
        sortino_acc = 0.0
        calmar_acc = 0.0
        max_dd = 0.0
        avg_holding_minutes = 0.0
        turnover_acc = 0.0
        exposure_acc = 0.0
        run_count = 0
        slippage_bps_samples: list[float] = []
        dataset_hashes: set[str] = set()
        for run in runs:
            run_count += 1
            metrics = run.get("metrics") or {}
            costs = run.get("costs_breakdown") or {}
            trades = run.get("trades") or []
            if isinstance(trades, list):
                all_trades.extend([t for t in trades if isinstance(t, dict)])
            gross_pnl += float(costs.get("gross_pnl_total", costs.get("gross_pnl", 0.0)) or 0.0)
            net_pnl += float(costs.get("net_pnl_total", costs.get("net_pnl", 0.0)) or 0.0)
            fees_total += float(costs.get("fees_total", 0.0) or 0.0)
            spread_total += float(costs.get("spread_total", 0.0) or 0.0)
            slippage_total += float(costs.get("slippage_total", 0.0) or 0.0)
            funding_total += float(costs.get("funding_total", 0.0) or 0.0)
            costs_total += float(costs.get("total_cost", 0.0) or 0.0)
            tc = int(metrics.get("trade_count") or metrics.get("roundtrips") or len(trades) or 0)
            w = max(1, tc)
            trade_weight += w
            sharpe_acc += float(metrics.get("sharpe", 0.0) or 0.0) * w
            sortino_acc += float(metrics.get("sortino", 0.0) or 0.0) * w
            calmar_acc += float(metrics.get("calmar", 0.0) or 0.0) * w
            max_dd = max(max_dd, float(metrics.get("max_dd", 0.0) or 0.0))
            avg_holding_minutes += float(metrics.get("avg_holding_time_minutes", metrics.get("avg_holding_time", 0.0)) or 0.0) * w
            turnover_acc += float(metrics.get("turnover", 0.0) or 0.0) * w
            exposure_acc += float(metrics.get("exposure_time_pct", 0.0) or 0.0) * w
            if run.get("dataset_hash"):
                dataset_hashes.add(str(run.get("dataset_hash")))
            if isinstance(trades, list):
                for trade in trades:
                    try:
                        entry_px = float(trade.get("entry_px", 0.0) or 0.0)
                        qty = abs(float(trade.get("qty", 0.0) or 0.0))
                        notional = abs(entry_px * qty)
                        if notional > 0:
                            slippage_cost = float(trade.get("slippage_cost", trade.get("slippage", 0.0)) or 0.0)
                            slippage_bps_samples.append((slippage_cost / notional) * 10000.0)
                    except Exception:
                        continue
        trade_count = len(all_trades)
        wins = [t for t in all_trades if float(t.get("pnl_net", t.get("pnl", 0.0)) or 0.0) > 0]
        winrate = (len(wins) / trade_count) if trade_count else 0.0
        expectancy = (
            sum(float(t.get("pnl_net", t.get("pnl", 0.0)) or 0.0) for t in all_trades) / trade_count
            if trade_count
            else (net_pnl / max(1, trade_weight))
        )
        avg_trade = expectancy
        mae_avg = (
            sum(float(t.get("mae", 0.0) or 0.0) for t in all_trades) / trade_count
            if trade_count and any("mae" in t for t in all_trades)
            else None
        )
        mfe_avg = (
            sum(float(t.get("mfe", 0.0) or 0.0) for t in all_trades) / trade_count
            if trade_count and any("mfe" in t for t in all_trades)
            else None
        )
        slippage_p95 = None
        if slippage_bps_samples:
            sorted_vals = sorted(slippage_bps_samples)
            idx = min(len(sorted_vals) - 1, max(0, int(round((len(sorted_vals) - 1) * 0.95))))
            slippage_p95 = round(sorted_vals[idx], 6)
        gross_abs = abs(gross_pnl)
        costs_ratio = (costs_total / gross_abs) if gross_abs else 0.0
        return {
            "run_count": run_count,
            "trade_count": trade_count,
            "total_entries": trade_count,
            "total_exits": sum(1 for t in all_trades if t.get("exit_time")),
            "roundtrips": sum(1 for t in all_trades if t.get("entry_time") and t.get("exit_time")),
            "winrate": round(winrate, 6),
            "expectancy_value": round(expectancy, 6),
            "expectancy_unit": "usd_por_trade",
            "avg_trade": round(avg_trade, 6),
            "max_dd": round(max_dd, 6),
            "sharpe": round(sharpe_acc / max(1, trade_weight), 6),
            "sortino": round(sortino_acc / max(1, trade_weight), 6),
            "calmar": round(calmar_acc / max(1, trade_weight), 6),
            "gross_pnl": round(gross_pnl, 6),
            "net_pnl": round(net_pnl, 6),
            "costs_total": round(costs_total, 6),
            "fees_total": round(fees_total, 6),
            "spread_total": round(spread_total, 6),
            "slippage_total": round(slippage_total, 6),
            "funding_total": round(funding_total, 6),
            "costs_ratio": round(costs_ratio, 6),
            "avg_holding_time": round(avg_holding_minutes / max(1, trade_weight), 6),
            "time_in_market": round(exposure_acc / max(1, trade_weight), 6),
            "turnover": round(turnover_acc / max(1, trade_weight), 6),
            "mfe_avg": round(mfe_avg, 6) if isinstance(mfe_avg, (int, float)) else None,
            "mae_avg": round(mae_avg, 6) if isinstance(mae_avg, (int, float)) else None,
            "slippage_p95_bps": slippage_p95,
            "maker_ratio": None,
            "fill_ratio": None,
            "dataset_hashes": sorted(dataset_hashes),
            "dataset_hash_warning": len(dataset_hashes) > 1,
        }

    def _infer_trade_regime_label(self, trade: dict[str, Any], run: dict[str, Any], strategy: dict[str, Any] | None = None) -> str:
        explicit = str(trade.get("regime_label") or "").strip().lower()
        if explicit in {"trend", "range", "high_vol", "toxic"}:
            return explicit
        explain = trade.get("explain") if isinstance(trade.get("explain"), dict) else {}
        costs_model = run.get("costs_model") if isinstance(run.get("costs_model"), dict) else {}
        metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        spread_bps = float(costs_model.get("spread_bps", 0.0) or 0.0)
        if explain and (not bool(explain.get("vpin_ok", True)) or not bool(explain.get("spread_ok", True))):
            return "toxic"
        if spread_bps >= 10:
            return "toxic"
        if float(metrics.get("turnover", 0.0) or 0.0) >= 2.4 or float(metrics.get("max_dd", 0.0) or 0.0) >= 0.18:
            return "high_vol"
        tags = {str(t).lower() for t in (strategy.get("tags") or [])} if isinstance(strategy, dict) else set()
        if {"range", "mean_reversion", "meanrev"} & tags:
            return "range"
        if {"trend", "breakout", "momentum", "orderflow"} & tags:
            return "trend"
        if explain and bool(explain.get("trend_ok", False)):
            return "trend"
        return "range"

    def strategy_kpis_table(self, *, from_ts: str | None = None, to_ts: str | None = None, mode: str | None = None) -> list[dict[str, Any]]:
        strategies = self.list_strategies()
        runs = self.load_runs()
        out: list[dict[str, Any]] = []
        for strategy in strategies:
            selected_runs = [
                run
                for run in runs
                if str(run.get("strategy_id")) == str(strategy.get("id"))
                and self._run_matches_filters(run, from_ts=from_ts, to_ts=to_ts, mode=mode)
            ]
            kpis = self._aggregate_strategy_kpis(selected_runs)
            out.append(
                {
                    "strategy_id": strategy["id"],
                    "name": strategy.get("name"),
                    "mode": (mode or "backtest").lower(),
                    "from": from_ts,
                    "to": to_ts,
                    "kpis": kpis,
                    "status": strategy.get("status"),
                    "enabled_for_trading": bool(strategy.get("enabled_for_trading", strategy.get("enabled"))),
                    "allow_learning": bool(strategy.get("allow_learning", True)),
                    "is_primary": bool(strategy.get("is_primary", False)),
                    "source": strategy.get("source", "uploaded"),
                }
            )
        return out

    def strategy_kpis(self, strategy_id: str, *, from_ts: str | None = None, to_ts: str | None = None, mode: str | None = None) -> dict[str, Any]:
        strategy = self.strategy_or_404(strategy_id)
        runs = [
            run
            for run in self.load_runs()
            if str(run.get("strategy_id")) == strategy_id and self._run_matches_filters(run, from_ts=from_ts, to_ts=to_ts, mode=mode)
        ]
        return {
            "strategy_id": strategy_id,
            "name": strategy.get("name"),
            "mode": (mode or "backtest").lower(),
            "from": from_ts,
            "to": to_ts,
            "kpis": self._aggregate_strategy_kpis(runs),
        }

    def strategy_kpis_by_regime(self, strategy_id: str, *, from_ts: str | None = None, to_ts: str | None = None, mode: str | None = None) -> dict[str, Any]:
        strategy = self.strategy_or_404(strategy_id)
        runs = [
            run
            for run in self.load_runs()
            if str(run.get("strategy_id")) == strategy_id and self._run_matches_filters(run, from_ts=from_ts, to_ts=to_ts, mode=mode)
        ]
        buckets: dict[str, list[dict[str, Any]]] = {"trend": [], "range": [], "high_vol": [], "toxic": []}
        for run in runs:
            trades = run.get("trades") or []
            if not isinstance(trades, list) or not trades:
                continue
            for trade in trades:
                if not isinstance(trade, dict):
                    continue
                label = self._infer_trade_regime_label(trade, run, strategy=strategy)
                trade_copy = dict(trade)
                trade_copy["regime_label"] = label
                # Regime aggregation uses pseudo-run per trade to preserve pnl/costs/trade-level stats.
                pseudo_run = {
                    "id": str(run.get("id")),
                    "strategy_id": strategy_id,
                    "mode": str(run.get("mode") or "backtest"),
                    "created_at": run.get("created_at"),
                    "dataset_hash": run.get("dataset_hash"),
                    "costs_model": run.get("costs_model") or {},
                    "metrics": {
                        "trade_count": 1,
                        "max_dd": float((run.get("metrics") or {}).get("max_dd", 0.0) or 0.0),
                        "sharpe": float((run.get("metrics") or {}).get("sharpe", 0.0) or 0.0),
                        "sortino": float((run.get("metrics") or {}).get("sortino", 0.0) or 0.0),
                        "calmar": float((run.get("metrics") or {}).get("calmar", 0.0) or 0.0),
                        "avg_holding_time": float((run.get("metrics") or {}).get("avg_holding_time", 0.0) or 0.0),
                        "turnover": float((run.get("metrics") or {}).get("turnover", 0.0) or 0.0),
                        "exposure_time_pct": float((run.get("metrics") or {}).get("exposure_time_pct", 0.0) or 0.0),
                    },
                    "costs_breakdown": {
                        "gross_pnl_total": float(trade.get("pnl", 0.0) or 0.0),
                        "net_pnl_total": float(trade.get("pnl_net", trade.get("pnl", 0.0)) or 0.0),
                        "fees_total": float(trade.get("fees", 0.0) or 0.0),
                        "spread_total": float(trade.get("spread_cost", 0.0) or 0.0),
                        "slippage_total": float(trade.get("slippage_cost", 0.0) or 0.0),
                        "funding_total": float(trade.get("funding_cost", 0.0) or 0.0),
                        "total_cost": float(trade.get("cost_total", 0.0) or 0.0),
                    },
                    "trades": [trade_copy],
                }
                buckets.setdefault(label, []).append(pseudo_run)
        return {
            "strategy_id": strategy_id,
            "name": strategy.get("name"),
            "mode": (mode or "backtest").lower(),
            "from": from_ts,
            "to": to_ts,
            "regimes": {
                label: {"regime_label": label, "kpis": self._aggregate_strategy_kpis(rows)}
                for label, rows in buckets.items()
            },
            "regime_rule_source": "heuristico_desde_trades_costos_tags",
            "regime_rules": {
                "trend": "ADX>=22 (aproximado por tags/flags trend)",
                "range": "ADX<=18 (aproximado por tags mean reversion)",
                "high_vol": "ATR/ATR_baseline>=1.6 (aproximado por turnover/max_dd)",
                "toxic": "VPIN alto o spread alto (aproximado por explain/costos)",
            },
        }

    def _record_run_provenance(self, run: dict[str, Any]) -> None:
        if not isinstance(run, dict):
            return
        period = run.get("period") if isinstance(run.get("period"), dict) else {}
        costs_model = run.get("costs_model") if isinstance(run.get("costs_model"), dict) else {}
        self.registry.upsert_run_provenance(
            run_id=str(run.get("id") or ""),
            strategy_id=str(run.get("strategy_id") or ""),
            mode=str(run.get("mode") or "backtest"),
            ts_from=str(period.get("start") or ""),
            ts_to=str(period.get("end") or ""),
            dataset_source=str(run.get("data_source") or run.get("dataset_source") or "synthetic"),
            dataset_hash=str(run.get("dataset_hash") or ""),
            costs_used={
                "fees_bps": float(costs_model.get("fees_bps", 0.0) or 0.0),
                "spread_bps": float(costs_model.get("spread_bps", 0.0) or 0.0),
                "slippage_bps": float(costs_model.get("slippage_bps", 0.0) or 0.0),
                "funding_bps": float(costs_model.get("funding_bps", 0.0) or 0.0),
                "rollover_bps": float(costs_model.get("rollover_bps", 0.0) or 0.0),
            },
            commit_hash=str(run.get("git_commit") or ""),
            created_at=str(run.get("created_at") or ""),
        )

    def _ensure_seed_backtest(self) -> None:
        runs = self.load_runs()
        if runs:
            # backfill provenance for legacy runs
            for row in runs:
                try:
                    if "provenance" not in row:
                        period = row.get("period") if isinstance(row.get("period"), dict) else {}
                        row["mode"] = str(row.get("mode") or "backtest")
                        row["provenance"] = {
                            "run_id": str(row.get("id") or ""),
                            "strategy_id": str(row.get("strategy_id") or ""),
                            "mode": row["mode"],
                            "from": str(period.get("start") or ""),
                            "to": str(period.get("end") or ""),
                            "dataset_source": str(row.get("data_source") or "synthetic_seeded"),
                            "dataset_hash": str(row.get("dataset_hash") or ""),
                            "costs_used": row.get("costs_model") or {},
                            "commit_hash": str(row.get("git_commit") or get_env("GIT_COMMIT", "local")),
                            "created_at": str(row.get("created_at") or utc_now_iso()),
                        }
                    self._record_run_provenance(row)
                except Exception:
                    continue
            self.save_runs(runs)
            existing_strategy_ids = {str(row.get("strategy_id")) for row in runs if row.get("strategy_id")}
            seed_candidates = [DEFAULT_STRATEGY_ID]
            for reg in self.registry.list_strategy_registry():
                sid = str(reg.get("id") or "")
                if sid and sid not in seed_candidates and sid not in existing_strategy_ids and str(reg.get("status")) != "archived":
                    seed_candidates.append(sid)
            for idx, sid in enumerate(seed_candidates[1:6], start=1):
                self.create_backtest_run(
                    strategy_id=sid,
                    start="2024-01-01",
                    end="2024-12-31",
                    universe=["BTC/USDT", "ETH/USDT"],
                    fees_bps=5.0 + (idx % 3) * 0.5,
                    spread_bps=3.5 + (idx % 4) * 0.8,
                    slippage_bps=2.5 + (idx % 5) * 0.6,
                    funding_bps=1.0 + (idx % 2) * 0.2,
                    validation_mode="walk-forward",
                )
            return
        seed_ids = [DEFAULT_STRATEGY_ID]
        for row in self.registry.list_strategy_registry():
            sid = str(row.get("id") or "")
            if sid and sid not in seed_ids and str(row.get("status")) != "archived":
                seed_ids.append(sid)
        for idx, sid in enumerate(seed_ids[:6]):
            self.create_backtest_run(
                strategy_id=sid,
                start="2024-01-01",
                end="2024-12-31",
                universe=["BTC/USDT", "ETH/USDT"],
                fees_bps=5.0 + (idx % 3) * 0.5,
                spread_bps=3.5 + (idx % 4) * 0.8,
                slippage_bps=2.5 + (idx % 5) * 0.6,
                funding_bps=1.0 + (idx % 2) * 0.2,
                validation_mode="walk-forward",
            )

    def load_settings(self) -> dict[str, Any]:
        return self.policy_state.load_settings()

    def save_settings(self, settings: dict[str, Any]) -> None:
        self.policy_state.save_settings(settings)

    def load_bot_state(self) -> dict[str, Any]:
        return self.policy_state.load_bot_state()

    def save_bot_state(self, state: dict[str, Any]) -> None:
        self.policy_state.save_bot_state(state)

    def load_strategy_meta(self) -> dict[str, dict[str, Any]]:
        return self.strategy_truth.load_meta()

    def save_strategy_meta(self, payload: dict[str, dict[str, Any]]) -> None:
        self.strategy_truth.save_meta(payload)

    @staticmethod
    def _normalize_bot_mode(value: str | None) -> str:
        return normalize_bot_policy_mode(value, default="paper")

    @staticmethod
    def _normalize_bot_status(value: str | None) -> str:
        status = str(value or "active").strip().lower()
        if status not in {"active", "paused", "archived"}:
            return "active"
        return status

    @staticmethod
    def _normalize_bot_engine(value: str | None) -> str:
        engine = str(value or "bandit_thompson").strip()
        return engine or "bandit_thompson"

    def _next_bot_id(self, rows: list[dict[str, Any]]) -> str:
        max_n = 0
        for row in rows:
            raw = str((row or {}).get("id") or "")
            match = re.fullmatch(r"BOT-(\d+)", raw)
            if not match:
                continue
            try:
                max_n = max(max_n, int(match.group(1)))
            except Exception:
                continue
        return f"BOT-{max_n + 1:06d}"

    def _normalize_bot_row(self, row: dict[str, Any], *, strategy_ids: set[str] | None = None) -> dict[str, Any]:
        if not isinstance(row, dict):
            row = {}
        sid_allow = strategy_ids if isinstance(strategy_ids, set) else None
        pool_ids_raw = row.get("pool_strategy_ids") if isinstance(row.get("pool_strategy_ids"), list) else []
        pool_strategy_ids: list[str] = []
        seen_pool: set[str] = set()
        for item in pool_ids_raw:
            sid = str(item or "").strip()
            if not sid or sid in seen_pool:
                continue
            if sid_allow is not None and sid not in sid_allow:
                continue
            seen_pool.add(sid)
            pool_strategy_ids.append(sid)
        universe_raw = row.get("universe") if isinstance(row.get("universe"), list) else []
        universe: list[str] = []
        seen_universe: set[str] = set()
        for item in universe_raw:
            val = str(item or "").strip().upper()
            if not val or val in seen_universe:
                continue
            seen_universe.add(val)
            universe.append(val)
        now_iso = utc_now_iso()
        return {
            "id": str(row.get("id") or "").strip() or "BOT-000000",
            "name": str(row.get("name") or "AutoBot").strip()[:120] or "AutoBot",
            "engine": self._normalize_bot_engine(str(row.get("engine") or "bandit_thompson")),
            "mode": self._normalize_bot_mode(str(row.get("mode") or "paper")),
            "status": self._normalize_bot_status(str(row.get("status") or "active")),
            "pool_strategy_ids": pool_strategy_ids,
            "universe": universe,
            "notes": str(row.get("notes") or "")[:500],
            "created_at": str(row.get("created_at") or now_iso),
            "updated_at": str(row.get("updated_at") or now_iso),
        }

    def load_bots(self) -> list[dict[str, Any]]:
        payload = self.policy_state.load_bot_rows()
        if not isinstance(payload, list):
            payload = []
        valid_strategy_ids = {str(row.get("id") or "") for row in self.list_strategies() if str(row.get("id") or "")}
        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        changed = False
        for idx, raw in enumerate(payload):
            before = dict(raw) if isinstance(raw, dict) else {}
            row = self._normalize_bot_row(before, strategy_ids=valid_strategy_ids)
            if not row["id"] or row["id"] == "BOT-000000" or row["id"] in seen_ids:
                row["id"] = self._next_bot_id(normalized)
                changed = True
            seen_ids.add(row["id"])
            if before != row:
                changed = True
            normalized.append(row)
        if changed:
            json_save(BOTS_PATH, normalized)
        return normalized

    def save_bots(self, rows: list[dict[str, Any]]) -> None:
        self.policy_state.save_bot_rows(rows)

    def bot_or_404(self, bot_id: str) -> dict[str, Any]:
        bot_id_n = str(bot_id or "").strip()
        for row in self.load_bots():
            if str(row.get("id") or "") == bot_id_n:
                return dict(row)
        raise HTTPException(status_code=404, detail="BotInstance not found")

    @staticmethod
    def _bot_policy_state_payload(bot: dict[str, Any]) -> dict[str, Any]:
        return {
            "engine": str(bot.get("engine") or "bandit_thompson"),
            "mode": str(bot.get("mode") or "paper"),
            "status": str(bot.get("status") or "active"),
            "pool_strategy_ids": [str(item) for item in (bot.get("pool_strategy_ids") or []) if str(item).strip()],
            "universe": [str(item) for item in (bot.get("universe") or []) if str(item).strip()],
            "notes": str(bot.get("notes") or ""),
            "created_at": str(bot.get("created_at") or ""),
            "updated_at": str(bot.get("updated_at") or ""),
        }

    def bot_policy_state_or_404(self, bot_id: str) -> dict[str, Any]:
        return self._bot_policy_state_payload(self.bot_or_404(bot_id))

    def patch_bot_policy_state(
        self,
        bot_id: str,
        *,
        engine: str | None = None,
        mode: str | None = None,
        status: str | None = None,
        pool_strategy_ids: list[str] | None = None,
        universe: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        bot = self.patch_bot_instance(
            bot_id,
            engine=engine,
            mode=mode,
            status=status,
            pool_strategy_ids=pool_strategy_ids,
            universe=universe,
            notes=notes,
        )
        return self._bot_policy_state_payload(bot)

    def _ensure_default_bots(self) -> None:
        rows = self.load_bots()
        if rows:
            return
        strategies = self.list_strategies()
        pool_ids = [
            str(row.get("id"))
            for row in strategies
            if str(row.get("status") or "") != "archived" and bool(row.get("allow_learning", True))
        ]
        if not pool_ids:
            pool_ids = [str(row.get("id")) for row in strategies[:1] if row.get("id")]
        default_row = self._normalize_bot_row(
            {
                "id": "BOT-000001",
                "name": "AutoBot Principal",
                "engine": "bandit_thompson",
                "mode": "paper",
                "status": "active",
                "pool_strategy_ids": pool_ids,
                "universe": ["BTCUSDT", "ETHUSDT"],
                "notes": "Bot base (Opcion B): propone cambios y requiere aprobacion humana.",
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            },
            strategy_ids={str(row.get("id") or "") for row in strategies},
        )
        self.save_bots([default_row])

    def _index_bots_by_strategy(
        self,
        *,
        bots: list[dict[str, Any]] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        rows = bots if isinstance(bots, list) else self.load_bots()
        out: dict[str, list[dict[str, Any]]] = {}
        for bot in rows:
            bot_id = str(bot.get("id") or "").strip()
            if not bot_id:
                continue
            ref = {
                "id": bot_id,
                "name": str(bot.get("name") or bot_id),
                "engine": self._normalize_bot_engine(str(bot.get("engine") or "")),
                "mode": self._normalize_bot_mode(str(bot.get("mode") or "")),
                "status": self._normalize_bot_status(str(bot.get("status") or "")),
            }
            for strategy_id in bot.get("pool_strategy_ids") or []:
                sid = str(strategy_id or "").strip()
                if not sid:
                    continue
                refs = out.setdefault(sid, [])
                refs.append(ref)
        for strategy_id, refs in out.items():
            refs.sort(key=lambda row: (str(row.get("name") or ""), str(row.get("id") or "")))
            out[strategy_id] = refs
        return out

    @staticmethod
    def _normalize_related_bot_ids(values: Any) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []

        def _add(value: Any) -> None:
            ref = str(value or "").strip()
            if ref and ref not in seen:
                seen.add(ref)
                out.append(ref)

        if isinstance(values, (list, tuple, set)):
            for item in values:
                if isinstance(item, dict):
                    _add(item.get("id"))
                else:
                    _add(item)
        elif isinstance(values, dict):
            _add(values.get("id"))
        else:
            _add(values)
        return out

    @classmethod
    def _extract_related_bot_ids_from_run(cls, run: dict[str, Any]) -> list[str]:
        refs: list[str] = []
        seen: set[str] = set()

        def _extend(values: Any) -> None:
            for ref in cls._normalize_related_bot_ids(values):
                if ref not in seen:
                    seen.add(ref)
                    refs.append(ref)

        if not isinstance(run, dict):
            return refs

        payload_sources: list[dict[str, Any]] = [run]
        for key in ("metadata", "params_json", "provenance", "artifacts"):
            value = run.get(key)
            if isinstance(value, dict):
                payload_sources.append(value)
        for payload in payload_sources:
            _extend(payload.get("bot_id"))
            _extend(payload.get("bot_ids"))
            _extend(payload.get("related_bot_ids"))
            _extend(payload.get("related_bots"))
        for tag in run.get("tags") or []:
            tag_text = str(tag or "").strip()
            if tag_text.startswith("bot:"):
                _extend(tag_text.split(":", 1)[1])
        return refs

    def annotate_runs_with_related_bots(
        self,
        runs: list[dict[str, Any]],
        *,
        bot_id: str | None = None,
        bots: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        requested_bot_id = str(bot_id or "").strip()
        bots_rows = bots if isinstance(bots, list) else self.load_bots()
        bots_by_strategy = self._index_bots_by_strategy(bots=bots_rows)
        bots_by_id: dict[str, dict[str, Any]] = {}
        for bot in bots_rows:
            bid = str(bot.get("id") or "").strip()
            if not bid:
                continue
            bots_by_id[bid] = {
                "id": bid,
                "name": str(bot.get("name") or bid),
                "engine": self._normalize_bot_engine(str(bot.get("engine") or "")),
                "mode": self._normalize_bot_mode(str(bot.get("mode") or "")),
                "status": self._normalize_bot_status(str(bot.get("status") or "")),
            }
        out: list[dict[str, Any]] = []
        for run in runs:
            if not isinstance(run, dict):
                continue
            strategy_id = str(run.get("strategy_id") or "").strip()
            explicit_bot_ids = self._extract_related_bot_ids_from_run(run)
            if explicit_bot_ids:
                related_bot_ids = explicit_bot_ids
                related_bots = [
                    dict(
                        bots_by_id.get(
                            bid,
                            {
                                "id": bid,
                                "name": bid,
                                "engine": "unknown",
                                "mode": "unknown",
                                "status": "unknown",
                            },
                        )
                    )
                    for bid in related_bot_ids
                ]
            else:
                related_bots = [dict(row) for row in (bots_by_strategy.get(strategy_id) or [])]
                related_bot_ids = [str(row.get("id") or "") for row in related_bots if str(row.get("id") or "")]
            if requested_bot_id and requested_bot_id not in related_bot_ids:
                continue
            payload = dict(run)
            payload["related_bot_ids"] = related_bot_ids
            payload["related_bots"] = related_bots
            out.append(payload)
        return out

    @staticmethod
    def _aggregate_bot_metric_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
        trades_total = 0
        weighted_wins = 0.0
        net_pnl_total = 0.0
        sharpe_vals: list[float] = []
        expectancy_weighted_num = 0.0
        expectancy_weighted_den = 0.0
        run_count_total = 0
        for row in rows:
            kpi = row.get("kpis") if isinstance(row.get("kpis"), dict) else {}
            trades = int(kpi.get("trade_count") or 0)
            winrate = float(kpi.get("winrate") or 0.0)
            net_pnl_total += float(kpi.get("net_pnl") or 0.0)
            trades_total += trades
            weighted_wins += winrate * trades
            expectancy_weighted_num += float(kpi.get("expectancy_value") or 0.0) * max(trades, 1)
            expectancy_weighted_den += max(trades, 1)
            run_count_total += int(kpi.get("run_count") or 0)
            sharpe_vals.append(float(kpi.get("sharpe") or 0.0))
        return {
            "trade_count": trades_total,
            "winrate": (weighted_wins / trades_total) if trades_total else 0.0,
            "net_pnl": net_pnl_total,
            "avg_sharpe": (sum(sharpe_vals) / len(sharpe_vals)) if sharpe_vals else 0.0,
            "expectancy_value": (expectancy_weighted_num / expectancy_weighted_den) if expectancy_weighted_den else 0.0,
            "run_count": run_count_total,
        }

    @staticmethod
    def _empty_experience_source_metrics() -> dict[str, Any]:
        return {
            "episode_count": 0,
            "run_count": 0,
            "trade_count": 0,
            "decision_count": 0,
            "enter_count": 0,
            "exit_count": 0,
            "hold_count": 0,
            "skip_count": 0,
            "reduce_count": 0,
            "add_count": 0,
            "avg_source_weight": 0.0,
            "last_end_ts": None,
        }

    def _aggregate_strategy_experience_by_source(
        self,
        *,
        strategy_ids: list[str],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        valid_sources = ("backtest", "shadow", "paper", "testnet")
        out: dict[str, dict[str, dict[str, Any]]] = {
            strategy_id: {source: self._empty_experience_source_metrics() for source in valid_sources}
            for strategy_id in strategy_ids
        }
        if not strategy_ids:
            return out
        episodes = self.registry.list_experience_episodes(strategy_ids=strategy_ids, sources=list(valid_sources))
        if not episodes:
            return out
        episode_ids = [str(row.get("id") or "") for row in episodes if str(row.get("id") or "")]
        events = self.registry.list_experience_events(episode_ids=episode_ids) if episode_ids else []
        episode_meta: dict[str, tuple[str, str]] = {}
        source_weight_sums: dict[tuple[str, str], float] = {}
        for episode in episodes:
            strategy_id = str(episode.get("strategy_id") or "")
            source = str(episode.get("source") or "backtest").strip().lower()
            episode_id = str(episode.get("id") or "")
            if strategy_id not in out or source not in out[strategy_id] or not episode_id:
                continue
            summary = episode.get("summary") if isinstance(episode.get("summary"), dict) else {}
            metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
            source_row = out[strategy_id][source]
            source_row["episode_count"] += 1
            source_row["run_count"] += 1
            source_row["trade_count"] += int(
                summary.get("trade_count")
                or metrics.get("trade_count")
                or metrics.get("roundtrips")
                or 0
            )
            end_ts = str(episode.get("end_ts") or episode.get("created_at") or "").strip() or None
            if end_ts and (
                source_row["last_end_ts"] is None
                or str(end_ts) > str(source_row["last_end_ts"] or "")
            ):
                source_row["last_end_ts"] = end_ts
            source_weight_sums[(strategy_id, source)] = source_weight_sums.get((strategy_id, source), 0.0) + float(
                episode.get("source_weight") or 0.0
            )
            episode_meta[episode_id] = (strategy_id, source)
        for event in events:
            episode_id = str(event.get("episode_id") or "")
            mapped = episode_meta.get(episode_id)
            if not mapped:
                continue
            strategy_id, source = mapped
            source_row = out[strategy_id][source]
            action = str(event.get("action") or "").strip().lower()
            source_row["decision_count"] += 1
            if action == "enter":
                source_row["enter_count"] += 1
            elif action == "exit":
                source_row["exit_count"] += 1
            elif action == "hold":
                source_row["hold_count"] += 1
            elif action == "skip":
                source_row["skip_count"] += 1
            elif action == "reduce":
                source_row["reduce_count"] += 1
            elif action == "add":
                source_row["add_count"] += 1
        for strategy_id, per_source in out.items():
            for source, source_row in per_source.items():
                episode_count = int(source_row.get("episode_count") or 0)
                source_row["avg_source_weight"] = round(
                    (source_weight_sums.get((strategy_id, source), 0.0) / episode_count) if episode_count else 0.0,
                    4,
                )
        return out

    def _aggregate_exact_bot_experience_by_source(
        self,
        *,
        bot_ids: list[str],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        valid_sources = ("backtest", "shadow", "paper", "testnet")
        out: dict[str, dict[str, dict[str, Any]]] = {
            bot_id: {source: self._empty_experience_source_metrics() for source in valid_sources}
            for bot_id in bot_ids
            if str(bot_id).strip()
        }
        if not out:
            return out
        episodes = self.registry.list_experience_episodes(bot_ids=list(out.keys()), sources=list(valid_sources))
        if not episodes:
            return out
        episode_ids = [str(row.get("id") or "") for row in episodes if str(row.get("id") or "")]
        events = self.registry.list_experience_events(episode_ids=episode_ids) if episode_ids else []
        episode_meta: dict[str, tuple[str, str]] = {}
        source_weight_sums: dict[tuple[str, str], float] = {}
        for episode in episodes:
            bot_id = str(episode.get("bot_id") or "").strip()
            source = str(episode.get("source") or "backtest").strip().lower()
            episode_id = str(episode.get("id") or "")
            if bot_id not in out or source not in out[bot_id] or not episode_id:
                continue
            summary = episode.get("summary") if isinstance(episode.get("summary"), dict) else {}
            metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}
            source_row = out[bot_id][source]
            source_row["episode_count"] += 1
            source_row["run_count"] += 1
            source_row["trade_count"] += int(
                summary.get("trade_count")
                or metrics.get("trade_count")
                or metrics.get("roundtrips")
                or 0
            )
            end_ts = str(episode.get("end_ts") or episode.get("created_at") or "").strip() or None
            if end_ts and (
                source_row["last_end_ts"] is None
                or str(end_ts) > str(source_row["last_end_ts"] or "")
            ):
                source_row["last_end_ts"] = end_ts
            source_weight_sums[(bot_id, source)] = source_weight_sums.get((bot_id, source), 0.0) + float(
                episode.get("source_weight") or 0.0
            )
            episode_meta[episode_id] = (bot_id, source)
        for event in events:
            episode_id = str(event.get("episode_id") or "")
            mapped = episode_meta.get(episode_id)
            if not mapped:
                continue
            bot_id, source = mapped
            source_row = out[bot_id][source]
            action = str(event.get("action") or "").strip().lower()
            source_row["decision_count"] += 1
            if action == "enter":
                source_row["enter_count"] += 1
            elif action == "exit":
                source_row["exit_count"] += 1
            elif action == "hold":
                source_row["hold_count"] += 1
            elif action == "skip":
                source_row["skip_count"] += 1
            elif action == "reduce":
                source_row["reduce_count"] += 1
            elif action == "add":
                source_row["add_count"] += 1
        for bot_id, per_source in out.items():
            for source, source_row in per_source.items():
                episode_count = int(source_row.get("episode_count") or 0)
                source_row["avg_source_weight"] = round(
                    (source_weight_sums.get((bot_id, source), 0.0) / episode_count) if episode_count else 0.0,
                    4,
                )
        return out

    def get_bots_overview(
        self,
        bot_ids: list[str] | None = None,
        *,
        recommendations: list[dict[str, Any]] | None = None,
        bots: list[dict[str, Any]] | None = None,
        strategies: list[dict[str, Any]] | None = None,
        runs: list[dict[str, Any]] | None = None,
        include_recent_logs: bool = True,
        recent_logs_per_bot: int | None = None,
        perf: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        recent_logs_limit = max(0, int(BOTS_OVERVIEW_RECENT_LOGS_PER_BOT if recent_logs_per_bot is None else recent_logs_per_bot))
        t_overview_start = time.perf_counter()
        perf_stages: dict[str, Any] = {
            "include_recent_logs": bool(include_recent_logs),
            "recent_logs_per_bot": int(recent_logs_limit),
            "bots_count": 0,
            "strategies_count": 0,
            "runs_count": 0,
            "recommendations_count": 0,
        }

        mode_to_kpi_mode = {"shadow": "shadow", "paper": "paper", "testnet": "testnet", "live": "live"}
        kills_mode_keys = ("shadow", "paper", "testnet", "live", "unknown")

        t_stage = time.perf_counter()
        bots_rows = bots if isinstance(bots, list) else self.load_bots()
        if bot_ids:
            requested = {str(v).strip() for v in bot_ids if str(v).strip()}
            bots_rows = [row for row in bots_rows if str(row.get("id") or "") in requested]
        perf_stages["stage_inputs_ms"] = round((time.perf_counter() - t_stage) * 1000.0, 3)
        perf_stages["bots_count"] = len(bots_rows)
        if not bots_rows:
            perf_stages["total_ms"] = round((time.perf_counter() - t_overview_start) * 1000.0, 3)
            if isinstance(perf, dict):
                perf["overview"] = perf_stages
            return {}

        t_stage = time.perf_counter()
        strategies_rows = strategies if isinstance(strategies, list) else self.list_strategies()
        runs_rows = runs if isinstance(runs, list) else self.load_runs()
        rec_rows = recommendations if isinstance(recommendations, list) else []
        perf_stages["stage_load_context_ms"] = round((time.perf_counter() - t_stage) * 1000.0, 3)
        perf_stages["strategies_count"] = len(strategies_rows)
        perf_stages["runs_count"] = len(runs_rows)
        perf_stages["recommendations_count"] = len(rec_rows)
        strategy_by_id = {str(row.get("id") or ""): row for row in strategies_rows if str(row.get("id") or "")}

        t_stage = time.perf_counter()
        bot_pool_ids: dict[str, list[str]] = {}
        strategy_ids_in_pool: set[str] = set()
        for bot in bots_rows:
            bid = str(bot.get("id") or "")
            pool_ids = [sid for sid in (bot.get("pool_strategy_ids") or []) if str(sid) in strategy_by_id]
            normalized_pool = [str(sid) for sid in pool_ids]
            bot_pool_ids[bid] = normalized_pool
            strategy_ids_in_pool.update(normalized_pool)
        perf_stages["stage_pool_index_ms"] = round((time.perf_counter() - t_stage) * 1000.0, 3)
        perf_stages["strategies_in_pool_count"] = len(strategy_ids_in_pool)

        t_stage = time.perf_counter()
        runs_by_strategy_mode: dict[tuple[str, str], list[dict[str, Any]]] = {}
        indexed_runs = 0
        skipped_runs_outside_pool = 0
        max_runs_per_key = int(BOTS_OVERVIEW_MAX_RUNS_PER_STRATEGY_MODE)
        for run in runs_rows:
            if not isinstance(run, dict):
                continue
            sid = str(run.get("strategy_id") or "")
            if not sid:
                continue
            if strategy_ids_in_pool and sid not in strategy_ids_in_pool:
                skipped_runs_outside_pool += 1
                continue
            run_mode = str(run.get("mode") or "backtest").lower()
            key = (sid, run_mode)
            rows = runs_by_strategy_mode.get(key)
            if rows is None:
                runs_by_strategy_mode[key] = [run]
            else:
                rows.append(run)
                if len(rows) > max_runs_per_key:
                    rows.pop(0)
            indexed_runs += 1
        perf_stages["stage_runs_index_ms"] = round((time.perf_counter() - t_stage) * 1000.0, 3)
        perf_stages["runs_indexed"] = int(indexed_runs)
        perf_stages["runs_skipped_outside_pool"] = int(skipped_runs_outside_pool)
        perf_stages["max_runs_per_strategy_mode"] = int(max_runs_per_key)

        t_stage = time.perf_counter()
        kpis_by_mode: dict[str, dict[str, dict[str, Any]]] = {mode_key: {} for mode_key in mode_to_kpi_mode}
        # Compute KPIs only for strategies referenced by at least one bot pool.
        for sid in strategy_ids_in_pool:
            for mode_key, kpi_mode in mode_to_kpi_mode.items():
                kpis_by_mode[mode_key][sid] = self._aggregate_strategy_kpis(runs_by_strategy_mode.get((sid, kpi_mode), []))
        perf_stages["stage_kpis_ms"] = round((time.perf_counter() - t_stage) * 1000.0, 3)

        t_stage = time.perf_counter()
        experience_by_strategy = self._aggregate_strategy_experience_by_source(strategy_ids=sorted(strategy_ids_in_pool))
        perf_stages["stage_experience_ms"] = round((time.perf_counter() - t_stage) * 1000.0, 3)

        t_stage = time.perf_counter()
        exact_experience_by_bot = self._aggregate_exact_bot_experience_by_source(
            bot_ids=[str(bot.get("id") or "") for bot in bots_rows]
        )
        perf_stages["stage_bot_experience_ms"] = round((time.perf_counter() - t_stage) * 1000.0, 3)

        bot_ids_ordered = [str(bot.get("id") or "") for bot in bots_rows if str(bot.get("id") or "")]
        bot_ids_set = set(bot_ids_ordered)
        empty_kills_template = {key: 0 for key in kills_mode_keys}
        kills_by_mode_per_bot: dict[str, dict[str, int]] = {bid: dict(empty_kills_template) for bid in bot_ids_ordered}
        kills_by_mode_24h_per_bot: dict[str, dict[str, int]] = {bid: dict(empty_kills_template) for bid in bot_ids_ordered}
        last_kill_by_bot: dict[str, str | None] = {bid: None for bid in bot_ids_ordered}
        logs_per_bot: dict[str, list[dict[str, Any]]] = {bid: [] for bid in bot_ids_ordered}

        db_read_ms = 0.0
        post_db_process_ms = 0.0
        if bot_ids_ordered:
            placeholders = ",".join("?" for _ in bot_ids_ordered)
            since_24h = (utc_now() - timedelta(hours=24)).isoformat()
            t_db = time.perf_counter()
            with self._connect() as conn:
                # Read 1/3: kills acumulados por bot+modo (all-time) + ultimo timestamp.
                kills_total_rows = conn.execute(
                    f"""
                    SELECT bot_id, mode, COUNT(*) AS n, MAX(ts) AS last_ts
                    FROM breaker_events
                    WHERE bot_id IN ({placeholders})
                    GROUP BY bot_id, mode
                    """,
                    tuple(bot_ids_ordered),
                ).fetchall()
                # Read 2/3: kills por bot+modo en ventana 24h.
                kills_24h_rows = conn.execute(
                    f"""
                    SELECT bot_id, mode, COUNT(*) AS n
                    FROM breaker_events
                    WHERE bot_id IN ({placeholders}) AND ts >= ?
                    GROUP BY bot_id, mode
                    """,
                    tuple(bot_ids_ordered + [since_24h]),
                ).fetchall()
                log_rows: list[sqlite3.Row] = []
                if include_recent_logs and int(recent_logs_limit) > 0:
                    per_bot_limit = max(1, int(recent_logs_limit))
                    logs_batch_limit = min(2000, max(200, len(bot_ids_ordered) * max(5, per_bot_limit)))
                    logs_refs_limit = min(8000, max(400, len(bot_ids_ordered) * max(10, per_bot_limit * 2)))
                    # Read 3/3: logs recientes en batch para evitar N+1 por bot.
                    try:
                        log_rows = conn.execute(
                            f"""
                            SELECT r.bot_id AS ref_bot_id, l.id, l.ts, l.type, l.severity, l.module, l.message, l.payload_json
                            FROM log_bot_refs r
                            JOIN logs l ON l.id = r.log_id
                            WHERE r.bot_id IN ({placeholders})
                            ORDER BY l.id DESC
                            LIMIT ?
                            """,
                            tuple(bot_ids_ordered + [logs_refs_limit]),
                        ).fetchall()
                        perf_stages["logs_prefilter_mode"] = "log_bot_refs"
                        perf_stages["logs_prefilter_has_bot_ref"] = True
                    except sqlite3.OperationalError:
                        try:
                            log_rows = conn.execute(
                                """
                                SELECT id, ts, type, severity, module, message, related_ids, payload_json
                                FROM logs
                                WHERE has_bot_ref = 1
                                ORDER BY id DESC
                                LIMIT ?
                                """,
                                (logs_batch_limit,),
                            ).fetchall()
                            perf_stages["logs_prefilter_mode"] = "has_bot_ref"
                            perf_stages["logs_prefilter_has_bot_ref"] = True
                        except sqlite3.OperationalError:
                            # Fallback for legacy DBs before migration.
                            log_rows = conn.execute(
                                """
                                SELECT id, ts, type, severity, module, message, related_ids, payload_json
                                FROM logs
                                ORDER BY id DESC
                                LIMIT ?
                                """,
                                (logs_batch_limit,),
                            ).fetchall()
                            perf_stages["logs_prefilter_mode"] = "legacy_full_logs"
                            perf_stages["logs_prefilter_has_bot_ref"] = False
            db_read_ms = (time.perf_counter() - t_db) * 1000.0

            t_post_db = time.perf_counter()
            for row in kills_total_rows:
                bid = str(row["bot_id"] or "")
                if bid not in bot_ids_set:
                    continue
                mode_key = self._normalize_breaker_mode(str(row["mode"] or ""))
                kills_by_mode_per_bot[bid][mode_key] = int(row["n"] or 0)
                ts_value = str(row["last_ts"] or "").strip()
                if ts_value and (last_kill_by_bot[bid] is None or ts_value > str(last_kill_by_bot[bid] or "")):
                    last_kill_by_bot[bid] = ts_value

            for row in kills_24h_rows:
                bid = str(row["bot_id"] or "")
                if bid not in bot_ids_set:
                    continue
                mode_key = self._normalize_breaker_mode(str(row["mode"] or ""))
                kills_by_mode_24h_per_bot[bid][mode_key] = int(row["n"] or 0)

            if include_recent_logs and int(recent_logs_limit) > 0:
                perf_stages["logs_rows_read"] = len(log_rows)
                payload_cache: dict[int, dict[str, Any]] = {}
                per_bot_limit = max(1, int(recent_logs_limit))
                remaining_slots: dict[str, int] = {bid: per_bot_limit for bid in bot_ids_ordered}
                bots_pending = len(bot_ids_ordered)
                for row in log_rows:
                    row_id = int(row["id"])
                    payload_map = payload_cache.get(row_id)
                    if payload_map is None:
                        payload_raw = row["payload_json"] if row["payload_json"] is not None else "{}"
                        try:
                            payload = json.loads(payload_raw)
                        except Exception:
                            payload = {}
                        payload_map = payload if isinstance(payload, dict) else {}
                        payload_cache[row_id] = payload_map

                    targets: set[str] = set()
                    ref_bot_id = str(row["ref_bot_id"] or "").strip() if "ref_bot_id" in row.keys() else ""
                    if ref_bot_id and ref_bot_id in bot_ids_set:
                        targets.add(ref_bot_id)
                    if not targets:
                        related_raw = row["related_ids"] if row["related_ids"] is not None else "[]"
                        try:
                            related_ids = json.loads(related_raw)
                        except Exception:
                            related_ids = []
                        for ref in self._extract_bot_refs_from_log(
                            related_ids if isinstance(related_ids, list) else [],
                            payload_map,
                        ):
                            if ref in bot_ids_set:
                                targets.add(ref)
                    if not targets:
                        continue
                    payload_entry = {
                        "id": f"log_{row_id}",
                        "numeric_id": row_id,
                        "ts": str(row["ts"] or ""),
                        "type": str(row["type"] or ""),
                        "severity": str(row["severity"] or ""),
                        "module": str(row["module"] or ""),
                        "message": str(row["message"] or ""),
                        "payload": payload_map,
                    }
                    for bid in targets:
                        if remaining_slots.get(bid, 0) <= 0:
                            continue
                        bot_logs = logs_per_bot.get(bid)
                        if bot_logs is None:
                            continue
                        bot_logs.append(payload_entry)
                        remaining_slots[bid] = int(remaining_slots.get(bid, 0)) - 1
                        if remaining_slots[bid] == 0:
                            bots_pending -= 1
                    if bots_pending <= 0:
                        break
            post_db_process_ms = (time.perf_counter() - t_post_db) * 1000.0
        perf_stages["stage_db_reads_ms"] = round(db_read_ms, 3)
        perf_stages["stage_db_process_ms"] = round(post_db_process_ms, 3)

        t_stage = time.perf_counter()
        kills_global_total = sum(sum(mode_counts.values()) for mode_counts in kills_by_mode_per_bot.values())
        kills_global_24h = sum(sum(mode_counts.values()) for mode_counts in kills_by_mode_24h_per_bot.values())

        out: dict[str, dict[str, Any]] = {}
        for bot in bots_rows:
            bot_id = str(bot.get("id") or "")
            if not bot_id:
                continue
            mode = self._normalize_bot_mode(str(bot.get("mode") or "paper"))
            pool = set(bot_pool_ids.get(bot_id, []))
            by_mode_metrics: dict[str, dict[str, Any]] = {}
            for mode_key in mode_to_kpi_mode:
                mode_rows = [{"strategy_id": sid, "kpis": kpis_by_mode[mode_key].get(sid, {})} for sid in pool]
                by_mode_metrics[mode_key] = self._aggregate_bot_metric_rows(mode_rows)
            experience_by_source = {
                source: self._empty_experience_source_metrics()
                for source in ("backtest", "shadow", "paper", "testnet")
            }
            for sid in pool:
                strategy_sources = experience_by_strategy.get(sid) or {}
                for source, incoming in strategy_sources.items():
                    target = experience_by_source.setdefault(source, self._empty_experience_source_metrics())
                    target["episode_count"] += int(incoming.get("episode_count") or 0)
                    target["run_count"] += int(incoming.get("run_count") or 0)
                    target["trade_count"] += int(incoming.get("trade_count") or 0)
                    target["decision_count"] += int(incoming.get("decision_count") or 0)
                    target["enter_count"] += int(incoming.get("enter_count") or 0)
                    target["exit_count"] += int(incoming.get("exit_count") or 0)
                    target["hold_count"] += int(incoming.get("hold_count") or 0)
                    target["skip_count"] += int(incoming.get("skip_count") or 0)
                    target["reduce_count"] += int(incoming.get("reduce_count") or 0)
                    target["add_count"] += int(incoming.get("add_count") or 0)
                    target["avg_source_weight"] += float(incoming.get("avg_source_weight") or 0.0) * int(
                        incoming.get("episode_count") or 0
                    )
                    incoming_last = str(incoming.get("last_end_ts") or "").strip() or None
                    if incoming_last and (
                        target["last_end_ts"] is None
                        or str(incoming_last) > str(target["last_end_ts"] or "")
                    ):
                        target["last_end_ts"] = incoming_last
            for source, target in experience_by_source.items():
                episode_count = int(target.get("episode_count") or 0)
                target["avg_source_weight"] = round(
                    (float(target.get("avg_source_weight") or 0.0) / episode_count) if episode_count else 0.0,
                    4,
                )
            exact_experience_by_source = exact_experience_by_bot.get(bot_id) or {}
            has_exact_experience = any(
                int((row or {}).get("episode_count") or 0) > 0
                for row in exact_experience_by_source.values()
            )
            if has_exact_experience:
                experience_by_source = {
                    source: dict(exact_experience_by_source.get(source) or self._empty_experience_source_metrics())
                    for source in ("backtest", "shadow", "paper", "testnet")
                }
            active = by_mode_metrics.get(
                mode,
                {"trade_count": 0, "winrate": 0.0, "net_pnl": 0.0, "avg_sharpe": 0.0, "expectancy_value": 0.0, "run_count": 0},
            )

            rec_pending = 0
            rec_approved = 0
            rec_rejected = 0
            for rec in rec_rows:
                if not isinstance(rec, dict):
                    continue
                active_sid = str(rec.get("active_strategy_id") or "")
                if active_sid and active_sid not in pool:
                    continue
                status = str(rec.get("status") or "PENDING").upper()
                if "PENDING" in status:
                    rec_pending += 1
                elif "APPROVED" in status:
                    rec_approved += 1
                elif "REJECT" in status:
                    rec_rejected += 1

            last_run_at: str | None = None
            for sid in pool:
                strategy_meta = strategy_by_id.get(sid) or {}
                candidate_last = str(strategy_meta.get("last_run_at") or "")
                if candidate_last and (last_run_at is None or candidate_last > last_run_at):
                    last_run_at = candidate_last

            kills_by_mode = dict(kills_by_mode_per_bot.get(bot_id, empty_kills_template))
            kills_by_mode_24h = dict(kills_by_mode_24h_per_bot.get(bot_id, empty_kills_template))
            metrics = {
                "strategy_count": len(pool),
                "run_count": int(active.get("run_count") or 0),
                "trade_count": int(active.get("trade_count") or 0),
                "winrate": float(active.get("winrate") or 0.0),
                "net_pnl": float(active.get("net_pnl") or 0.0),
                "avg_sharpe": float(active.get("avg_sharpe") or 0.0),
                "expectancy_value": float(active.get("expectancy_value") or 0.0),
                "expectancy_unit": "$/trade",
                "kills_total": int(kills_by_mode.get(mode, 0)),
                "kills_24h": int(kills_by_mode_24h.get(mode, 0)),
                "kills_global_total": int(kills_global_total),
                "kills_global_24h": int(kills_global_24h),
                "kills_by_mode": kills_by_mode,
                "kills_by_mode_24h": kills_by_mode_24h,
                "last_kill_at": last_kill_by_bot.get(bot_id),
                "by_mode": by_mode_metrics,
                "experience_by_source": experience_by_source,
                "experience_history_scope": "exact_bot_history" if has_exact_experience else "pool_approximation",
                "last_run_at": last_run_at,
                "recommendations_pending": rec_pending,
                "recommendations_approved": rec_approved,
                "recommendations_rejected": rec_rejected,
            }
            out[bot_id] = {
                "metrics": metrics,
                "recent_logs": (
                    logs_per_bot.get(bot_id, [])
                    if include_recent_logs and int(recent_logs_limit) > 0
                    else []
                ),
            }
        perf_stages["stage_assemble_ms"] = round((time.perf_counter() - t_stage) * 1000.0, 3)
        perf_stages["total_ms"] = round((time.perf_counter() - t_overview_start) * 1000.0, 3)
        if isinstance(perf, dict):
            perf["overview"] = perf_stages
        return out

    def _bot_metrics(
        self,
        bot: dict[str, Any],
        *,
        recommendations: list[dict[str, Any]] | None = None,
        overview: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        bot_id = str(bot.get("id") or "")
        overview_map = overview
        if overview_map is None:
            overview_map = self.get_bots_overview(
                [bot_id] if bot_id else None,
                recommendations=recommendations,
                bots=[bot] if bot_id else None,
            )
        payload = (overview_map.get(bot_id) if isinstance(overview_map, dict) else None) or {}
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        if metrics:
            return metrics
        return {
            "strategy_count": 0,
            "run_count": 0,
            "trade_count": 0,
            "winrate": 0.0,
            "net_pnl": 0.0,
            "avg_sharpe": 0.0,
            "expectancy_value": 0.0,
            "expectancy_unit": "$/trade",
            "kills_total": 0,
            "kills_24h": 0,
            "kills_global_total": 0,
            "kills_global_24h": 0,
            "kills_by_mode": {"shadow": 0, "paper": 0, "testnet": 0, "live": 0, "unknown": 0},
            "kills_by_mode_24h": {"shadow": 0, "paper": 0, "testnet": 0, "live": 0, "unknown": 0},
            "last_kill_at": None,
            "by_mode": {
                "shadow": {"trade_count": 0, "winrate": 0.0, "net_pnl": 0.0, "avg_sharpe": 0.0, "expectancy_value": 0.0, "run_count": 0},
                "paper": {"trade_count": 0, "winrate": 0.0, "net_pnl": 0.0, "avg_sharpe": 0.0, "expectancy_value": 0.0, "run_count": 0},
                "testnet": {"trade_count": 0, "winrate": 0.0, "net_pnl": 0.0, "avg_sharpe": 0.0, "expectancy_value": 0.0, "run_count": 0},
                "live": {"trade_count": 0, "winrate": 0.0, "net_pnl": 0.0, "avg_sharpe": 0.0, "expectancy_value": 0.0, "run_count": 0},
            },
            "experience_by_source": {
                "backtest": self._empty_experience_source_metrics(),
                "shadow": self._empty_experience_source_metrics(),
                "paper": self._empty_experience_source_metrics(),
                "testnet": self._empty_experience_source_metrics(),
            },
            "last_run_at": None,
            "recommendations_pending": 0,
            "recommendations_approved": 0,
            "recommendations_rejected": 0,
        }

    def list_bot_instances(
        self,
        *,
        recommendations: list[dict[str, Any]] | None = None,
        include_recent_logs: bool | None = None,
        recent_logs_per_bot: int | None = None,
        overview_perf: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        effective_recent_logs = bool(BOTS_OVERVIEW_INCLUDE_RECENT_LOGS if include_recent_logs is None else include_recent_logs)
        effective_recent_logs_per_bot = max(
            0,
            int(BOTS_OVERVIEW_RECENT_LOGS_PER_BOT if recent_logs_per_bot is None else recent_logs_per_bot),
        )
        rows = self.load_bots()
        logs_auto_disabled = False
        if (
            include_recent_logs is None
            and effective_recent_logs
            and int(BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT) > 0
            and len(rows) > int(BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT)
        ):
            effective_recent_logs = False
            logs_auto_disabled = True
            effective_recent_logs_per_bot = 0
        if isinstance(overview_perf, dict):
            overview_perf["logs_auto_disabled"] = bool(logs_auto_disabled)
            overview_perf["logs_auto_disable_threshold"] = int(BOTS_OVERVIEW_AUTO_DISABLE_LOGS_BOT_COUNT)
            overview_perf["bots_count"] = len(rows)
            overview_perf["effective_recent_logs"] = bool(effective_recent_logs)
            overview_perf["logs_per_bot_effective"] = int(effective_recent_logs_per_bot)
        strategies = self.list_strategies()
        runs = self.load_runs()
        by_id = {str(s.get("id") or ""): s for s in strategies}
        overview = self.get_bots_overview(
            recommendations=recommendations,
            bots=rows,
            strategies=strategies,
            runs=runs,
            include_recent_logs=effective_recent_logs,
            recent_logs_per_bot=effective_recent_logs_per_bot,
            perf=overview_perf,
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            pool_ids = [sid for sid in (row.get("pool_strategy_ids") or []) if sid in by_id]
            pool_meta = [
                {
                    "id": sid,
                    "name": str(by_id[sid].get("name") or sid),
                    "allow_learning": bool(by_id[sid].get("allow_learning", True)),
                    "enabled_for_trading": bool(by_id[sid].get("enabled_for_trading", by_id[sid].get("enabled", False))),
                    "is_primary": bool(by_id[sid].get("is_primary", False)),
                }
                for sid in pool_ids
            ]
            payload = dict(row)
            payload["pool_strategy_ids"] = pool_ids
            payload["pool_strategies"] = pool_meta
            bot_id = str(row.get("id") or "")
            payload["metrics"] = self._bot_metrics(dict(row, pool_strategy_ids=pool_ids), recommendations=recommendations, overview=overview)
            payload["recent_logs"] = (
                ((overview.get(bot_id) or {}).get("recent_logs"))
                if isinstance(overview.get(bot_id), dict)
                else []
            ) or []
            out.append(payload)
        out.sort(key=lambda item: (0 if str(item.get("status")) == "active" else 1, item.get("name", ""), item.get("id", "")))
        return out

    def create_bot_instance(
        self,
        *,
        name: str | None,
        engine: str,
        mode: str,
        status: str,
        pool_strategy_ids: list[str] | None,
        universe: list[str] | None,
        notes: str | None,
    ) -> dict[str, Any]:
        rows = self.load_bots()
        valid_strategy_ids = {str(row.get("id") or "") for row in self.list_strategies() if str(row.get("id") or "")}
        now_iso = utc_now_iso()
        row = self._normalize_bot_row(
            {
                "id": self._next_bot_id(rows),
                "name": name or f"AutoBot {len(rows) + 1}",
                "engine": engine,
                "mode": mode,
                "status": status,
                "pool_strategy_ids": pool_strategy_ids or [],
                "universe": universe or [],
                "notes": notes or "",
                "created_at": now_iso,
                "updated_at": now_iso,
            },
            strategy_ids=valid_strategy_ids,
        )
        rows.append(row)
        self.save_bots(rows)
        self.add_log(
            event_type="bot_instance",
            severity="info",
            module="learning",
            message=f"Bot creado: {row['id']} ({row['name']})",
            related_ids=[row["id"]],
            payload={"engine": row["engine"], "mode": row["mode"], "pool_size": len(row["pool_strategy_ids"])},
        )
        return row

    def patch_bot_instance(
        self,
        bot_id: str,
        *,
        name: str | None = None,
        engine: str | None = None,
        mode: str | None = None,
        status: str | None = None,
        pool_strategy_ids: list[str] | None = None,
        universe: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        rows = self.load_bots()
        idx = next((i for i, row in enumerate(rows) if str(row.get("id")) == bot_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="BotInstance not found")
        valid_strategy_ids = {str(row.get("id") or "") for row in self.list_strategies() if str(row.get("id") or "")}
        current = dict(rows[idx])
        patched = dict(current)
        if name is not None:
            patched["name"] = name
        if engine is not None:
            patched["engine"] = engine
        if mode is not None:
            patched["mode"] = mode
        if status is not None:
            patched["status"] = status
        if pool_strategy_ids is not None:
            patched["pool_strategy_ids"] = pool_strategy_ids
        if universe is not None:
            patched["universe"] = universe
        if notes is not None:
            patched["notes"] = notes
        patched["id"] = bot_id
        patched["created_at"] = str(current.get("created_at") or utc_now_iso())
        patched["updated_at"] = utc_now_iso()
        rows[idx] = self._normalize_bot_row(patched, strategy_ids=valid_strategy_ids)
        self.save_bots(rows)
        self.add_log(
            event_type="bot_instance",
            severity="info",
            module="learning",
            message=f"Bot actualizado: {bot_id}",
            related_ids=[bot_id],
            payload={"status": rows[idx].get("status"), "mode": rows[idx].get("mode"), "engine": rows[idx].get("engine")},
        )
        return rows[idx]

    def delete_bot_instance(self, bot_id: str) -> dict[str, Any]:
        rows = self.load_bots()
        idx = next((i for i, row in enumerate(rows) if str(row.get("id")) == bot_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="BotInstance not found")
        deleted = rows.pop(idx)
        self.save_bots(rows)
        self.add_log(
            event_type="bot_instance",
            severity="info",
            module="learning",
            message=f"Bot eliminado: {bot_id}",
            related_ids=[bot_id],
            payload={"mode": deleted.get("mode"), "status": deleted.get("status"), "engine": deleted.get("engine")},
        )
        return deleted

    def list_strategies(self) -> list[dict[str, Any]]:
        metadata = self.load_strategy_meta()
        principals = {row["mode"]: row for row in self.registry.principals()}
        registry_rows = {row["id"]: row for row in self.registry.list_strategy_registry()}
        out: list[dict[str, Any]] = []
        strategy_ids = sorted({*metadata.keys(), *registry_rows.keys()})
        for strategy_id in strategy_ids:
            row = metadata.get(strategy_id, {})
            reg = registry_rows.get(strategy_id, {})
            primary_for: list[str] = []
            for mode in ("paper", "testnet", "live"):
                principal = principals.get(mode)
                if principal and principal["name"] == strategy_id:
                    primary_for.append(mode)
            latest_backtest = self.latest_run_for_strategy(strategy_id)
            enabled_for_trading = bool(reg.get("enabled_for_trading", row.get("enabled", False)))
            allow_learning = bool(reg.get("allow_learning", row.get("allow_learning", True)))
            is_primary = bool(reg.get("is_primary", row.get("is_primary", False)))
            source = str(reg.get("source") or row.get("source") or "uploaded")
            status = str(reg.get("status") or row.get("status") or ("active" if enabled_for_trading else "disabled"))
            out.append(
                {
                    "id": strategy_id,
                    "name": row.get("name", reg.get("name", strategy_id)),
                    "version": row.get("version", reg.get("version", "0.0.0")),
                    "enabled": enabled_for_trading,
                    "enabled_for_trading": enabled_for_trading,
                    "allow_learning": allow_learning,
                    "is_primary": is_primary,
                    "primary": bool(primary_for) or is_primary,
                    "primary_for_modes": primary_for,
                    "source": source,
                    "status": status,
                    "last_run_at": row.get("last_run_at"),
                    "last_oos": latest_backtest["metrics"] if latest_backtest else None,
                    "notes": row.get("notes", ""),
                    "description": row.get("description", ""),
                    "params": parse_yaml_map(row.get("params_yaml", "")),
                    "params_yaml": row.get("params_yaml", ""),
                    "parameters_schema": row.get("parameters_schema", {}),
                    "tags": row.get("tags", reg.get("tags", ["trend", "pullback", "orderflow"])),
                    "created_at": row.get("created_at", utc_now_iso()),
                    "updated_at": row.get("updated_at", utc_now_iso()),
                }
            )
        out.sort(key=lambda item: (0 if item.get("is_primary") else 1, 0 if item.get("enabled_for_trading") else 1, item.get("id", "")))
        return out

    def strategy_or_404(self, identifier: str) -> dict[str, Any]:
        metadata = self.load_strategy_meta()
        row = metadata.get(identifier)
        if not row:
            raise HTTPException(status_code=404, detail="Strategy not found")
        principals = {item["mode"]: item for item in self.registry.principals()}
        reg = self.registry.get_strategy_registry(identifier) or {}
        primary_for = [mode for mode in ("paper", "testnet", "live") if principals.get(mode, {}).get("name") == identifier]
        return {
            "id": identifier,
            "name": row.get("name", identifier),
            "version": row.get("version", "0.0.0"),
            "enabled": bool(reg.get("enabled_for_trading", row.get("enabled", False))),
            "enabled_for_trading": bool(reg.get("enabled_for_trading", row.get("enabled", False))),
            "allow_learning": bool(reg.get("allow_learning", row.get("allow_learning", True))),
            "is_primary": bool(reg.get("is_primary", row.get("is_primary", False))),
            "primary": bool(primary_for) or bool(reg.get("is_primary", row.get("is_primary", False))),
            "primary_for_modes": primary_for,
            "notes": row.get("notes", ""),
            "description": row.get("description", ""),
            "params": parse_yaml_map(row.get("params_yaml", "")),
            "params_yaml": row.get("params_yaml", ""),
            "parameters_schema": row.get("parameters_schema", {}),
            "db_strategy_id": int(row.get("db_strategy_id")),
            "last_run_at": row.get("last_run_at"),
            "tags": row.get("tags", reg.get("tags", ["trend", "pullback", "orderflow"])),
            "source": str(reg.get("source") or row.get("source") or "uploaded"),
            "status": str(reg.get("status") or row.get("status") or ("active" if row.get("enabled") else "disabled")),
            "created_at": row.get("created_at", utc_now_iso()),
            "updated_at": row.get("updated_at", utc_now_iso()),
        }

    def strategy_truth_or_404(self, strategy_id: str) -> dict[str, Any]:
        return self.strategy_or_404(strategy_id)

    def strategy_evidence_or_404(self, strategy_id: str, *, limit: int = 10) -> dict[str, Any]:
        strategy = self.strategy_or_404(strategy_id)
        rows = [row for row in self.load_runs() if str((row or {}).get("strategy_id") or "") == strategy_id]
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        items: list[dict[str, Any]] = []
        for row in rows[: max(1, int(limit))]:
            params_json = row.get("params_json") if isinstance(row.get("params_json"), dict) else {}
            items.append(
                {
                    "run_id": str(row.get("id") or ""),
                    "mode": str(row.get("mode") or "backtest"),
                    "created_at": str(row.get("created_at") or ""),
                    "metrics": row.get("metrics") if isinstance(row.get("metrics"), dict) else {},
                    "tags": [str(tag) for tag in (row.get("tags") or []) if str(tag).strip()],
                    "notes": str(row.get("notes") or ""),
                    "validation_mode": str(params_json.get("validation_mode") or ""),
                }
            )
        latest = items[0] if items else None
        return {
            "strategy_id": strategy_id,
            "strategy_version": str(strategy.get("version") or "0.0.0"),
            "last_run_at": strategy.get("last_run_at"),
            "run_count": len(rows),
            "last_oos": (latest.get("metrics") if isinstance(latest, dict) else None),
            "latest_run": latest,
            "items": items,
        }

    def set_strategy_enabled(self, strategy_id: str, enabled: bool) -> dict[str, Any]:
        metadata = self.load_strategy_meta()
        row = metadata.get(strategy_id)
        if not row:
            raise HTTPException(status_code=404, detail="Strategy not found")
        if not enabled and self.registry.enabled_for_trading_count() <= 1:
            reg_row = self.registry.get_strategy_registry(strategy_id)
            if reg_row and reg_row.get("enabled_for_trading"):
                raise HTTPException(status_code=400, detail="Debe existir al menos 1 estrategia activa para trading")
        row["enabled"] = enabled
        row["updated_at"] = utc_now_iso()
        status = "enabled" if enabled else "disabled"
        self.registry.set_status(int(row["db_strategy_id"]), status)
        self.registry.patch_strategy_registry(strategy_id, enabled_for_trading=enabled, status=("active" if enabled else "disabled"))
        metadata[strategy_id] = row
        self.save_strategy_meta(metadata)
        self._ensure_strategy_registry_invariants()
        self.add_log(
            event_type="strategy_changed",
            severity="info" if enabled else "warn",
            module="registry",
            message=f"Strategy {strategy_id} {'enabled' if enabled else 'disabled'}.",
            related_ids=[strategy_id],
            payload={"enabled": enabled},
        )
        return self.strategy_or_404(strategy_id)

    def set_primary(self, strategy_id: str, mode: str) -> dict[str, Any]:
        if mode not in ALLOWED_MODES:
            raise HTTPException(status_code=400, detail="Invalid mode")
        strategy = self.strategy_or_404(strategy_id)
        self.registry.set_principal(strategy["db_strategy_id"], mode)
        self.registry.patch_strategy_registry(strategy_id, is_primary=True, enabled_for_trading=True, status="active")
        self._ensure_strategy_registry_invariants()
        self.add_log(
            event_type="strategy_changed",
            severity="info",
            module="registry",
            message=f"Primary strategy set for {mode}.",
            related_ids=[strategy_id],
            payload={"mode": mode},
        )
        return self.strategy_or_404(strategy_id)

    def duplicate_strategy(self, strategy_id: str) -> dict[str, Any]:
        source = self.strategy_or_404(strategy_id)
        meta = self.load_strategy_meta()
        new_id = f"{strategy_id}_clone_{secrets.token_hex(2)}"
        pieces = source["version"].split(".")
        patch = int(pieces[2]) + 1 if len(pieces) >= 3 and pieces[2].isdigit() else 1
        new_version = f"{pieces[0] if pieces else '1'}.{pieces[1] if len(pieces) > 1 else '0'}.{patch}"
        src_row = meta[strategy_id]
        existing = self.registry.get_strategy_by_name(strategy_id)
        path = Path(str(existing["path"])) if existing else Path("missing")
        db_strategy_id = self.registry.upsert_strategy(
            name=new_id,
            version=new_version,
            path=str(path),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else secrets.token_hex(16),
            status="disabled",
            notes=f"Cloned from {strategy_id}",
        )
        meta[new_id] = {
            **src_row,
            "id": new_id,
            "version": new_version,
            "enabled": False,
            "allow_learning": False,
            "is_primary": False,
            "status": "disabled",
            "source": str(src_row.get("source") or "uploaded"),
            "db_strategy_id": db_strategy_id,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "notes": f"Cloned from {strategy_id}",
        }
        self.save_strategy_meta(meta)
        self.registry.upsert_strategy_registry(
            strategy_key=new_id,
            name=str(meta[new_id].get("name") or new_id),
            version=new_version,
            source=str(meta[new_id].get("source") or "uploaded"),
            status="disabled",
            enabled_for_trading=False,
            allow_learning=False,
            is_primary=False,
            tags=[str(x) for x in meta[new_id].get("tags", [])],
        )
        self.add_log(
            event_type="strategy_changed",
            severity="info",
            module="registry",
            message=f"Strategy duplicated from {strategy_id} to {new_id}.",
            related_ids=[strategy_id, new_id],
            payload={"version": new_version},
        )
        return self.strategy_or_404(new_id)

    def update_strategy_params(self, strategy_id: str, params_yaml: str) -> dict[str, Any]:
        meta = self.load_strategy_meta()
        row = meta.get(strategy_id)
        if not row:
            raise HTTPException(status_code=404, detail="Strategy not found")
        try:
            parsed = yaml.safe_load(params_yaml) or {}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="YAML must be an object")
        row["params_yaml"] = params_yaml
        row["updated_at"] = utc_now_iso()
        meta[strategy_id] = row
        self.save_strategy_meta(meta)
        self.add_log(
            event_type="strategy_changed",
            severity="info",
            module="registry",
            message=f"Params updated for {strategy_id}.",
            related_ids=[strategy_id],
            payload={"keys": list(parsed.keys())},
        )
        return self.strategy_or_404(strategy_id)
    def save_uploaded_strategy(
        self,
        strategy_id: str,
        name: str,
        version: str,
        description: str,
        schema: dict[str, Any],
        params_yaml: str,
        package_bytes: bytes,
        *,
        package_ext: str = ".zip",
        tags: list[str] | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        metadata = self.load_strategy_meta()
        if strategy_id in metadata:
            raise HTTPException(status_code=409, detail="Strategy id already exists")
        ext = package_ext if package_ext.startswith(".") else f".{package_ext}"
        path = UPLOADS_DIR / strategy_id / f"{version}{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(package_bytes)
        db_strategy_id = self.registry.upsert_strategy(
            name=strategy_id,
            version=version,
            path=str(path),
            sha256=hashlib.sha256(package_bytes).hexdigest(),
            status="disabled",
            notes=notes or "Uploaded via API",
        )
        metadata[strategy_id] = {
            "id": strategy_id,
            "name": name,
            "version": version,
            "description": description,
            "enabled": False,
            "allow_learning": True,
            "is_primary": False,
            "status": "disabled",
            "source": "uploaded",
            "notes": notes or "Uploaded via dashboard",
            "tags": tags or ["upload"],
            "params_yaml": params_yaml,
            "parameters_schema": schema,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "last_run_at": None,
            "db_strategy_id": db_strategy_id,
        }
        self.save_strategy_meta(metadata)
        self.registry.upsert_strategy_registry(
            strategy_key=strategy_id,
            name=name,
            version=version,
            source="uploaded",
            status="disabled",
            enabled_for_trading=False,
            allow_learning=True,
            is_primary=False,
            tags=[str(x) for x in (tags or ["upload"])],
        )
        self._ensure_strategy_registry_invariants()
        self.add_log(
            event_type="strategy_changed",
            severity="info",
            module="registry",
            message=f"Strategy uploaded: {strategy_id} v{version}.",
            related_ids=[strategy_id],
            payload={"path": str(path), "ext": ext},
        )
        return self.strategy_or_404(strategy_id)

    def load_runs(self) -> list[dict[str, Any]]:
        return self.strategy_evidence.load_runs()

    def save_runs(self, rows: list[dict[str, Any]]) -> None:
        self.strategy_evidence.save_runs(rows)

    def delete_catalog_runs(self, run_ids: list[str]) -> dict[str, Any]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in run_ids:
            rid = str(raw or "").strip()
            if not rid or rid in seen:
                continue
            seen.add(rid)
            normalized.append(rid)
        if not normalized:
            return {"deleted_count": 0, "deleted_run_ids": [], "deleted_legacy_count": 0}

        existing = [self.backtest_catalog.get_run(rid) for rid in normalized]
        existing_rows = [row for row in existing if isinstance(row, dict)]
        legacy_ids = {
            str(row.get("legacy_json_id") or "").strip()
            for row in existing_rows
            if str(row.get("legacy_json_id") or "").strip()
        }
        removed_legacy = 0
        if legacy_ids:
            before = self.load_runs()
            after = []
            for row in before:
                if not isinstance(row, dict):
                    after.append(row)
                    continue
                catalog_run_id = str(row.get("catalog_run_id") or "").strip()
                legacy_id = str(row.get("id") or "").strip()
                if catalog_run_id in seen or legacy_id in legacy_ids:
                    removed_legacy += 1
                    continue
                after.append(row)
            if len(after) != len(before):
                self.save_runs(after)

        result = self.backtest_catalog.delete_runs(normalized)
        return {
            "deleted_count": int(result.get("deleted_count") or 0),
            "deleted_run_ids": [str((row or {}).get("run_id") or "") for row in (result.get("deleted") or []) if isinstance(row, dict)],
            "deleted_legacy_count": removed_legacy,
            "affected_batches": result.get("affected_batches") or [],
        }

    def _catalog_strategy_structured_id(self, strategy_id: str, strategy_meta: dict[str, Any] | None = None) -> str:
        meta = strategy_meta or {}
        db_id = meta.get("db_strategy_id") if isinstance(meta, dict) else None
        try:
            if db_id is not None and int(db_id) > 0:
                return f"ST-{int(db_id):06d}"
        except Exception:
            pass
        return str(strategy_id or "")

    def _record_backtest_catalog(self, run: dict[str, Any], *, strategy_meta: dict[str, Any] | None = None, created_by: str = "system") -> None:
        if not isinstance(run, dict):
            return
        strategy_id = str(run.get("strategy_id") or "")
        meta = strategy_meta or (self.load_strategy_meta().get(strategy_id) if strategy_id else None)
        if isinstance(meta, dict) and not run.get("strategy_structured_id"):
            run["strategy_structured_id"] = self._catalog_strategy_structured_id(strategy_id, meta)
            run["strategy_name"] = str(run.get("strategy_name") or meta.get("name") or strategy_id)
            run["strategy_version"] = str(run.get("strategy_version") or meta.get("version") or "0.0.0")
        catalog_run_id = self.backtest_catalog.record_run_from_payload(run=run, strategy_meta=meta if isinstance(meta, dict) else None, created_by=created_by)
        artifacts = run.get("artifacts_links") if isinstance(run.get("artifacts_links"), dict) else {}
        for kind, path in artifacts.items():
            if not path:
                continue
            try:
                self.backtest_catalog.add_artifact(
                    run_id=catalog_run_id,
                    batch_id=str(run.get("batch_id") or "") or None,
                    kind=str(kind),
                    path=str(path),
                    url=str(path),
                )
            except Exception:
                continue

    def _resolve_backtest_cost_metadata(
        self,
        *,
        market: str,
        symbol: str,
        costs_model: dict[str, Any] | None,
        df: Any | None = None,
        is_perp: bool = False,
    ) -> dict[str, Any]:
        try:
            return self.cost_model_resolver.resolve(
                exchange=exchange_name(),
                market=str(market or "crypto"),
                symbol=str(symbol or "BTCUSDT"),
                costs=costs_model if isinstance(costs_model, dict) else {},
                df=df,
                is_perp=is_perp,
            )
        except Exception as exc:
            return {
                "fee_snapshot_id": None,
                "funding_snapshot_id": None,
                "spread_model_params": {"mode": "static", "source": "metadata_error", "error": str(exc)},
                "slippage_model_params": {"mode": "static", "source": "metadata_error", "error": str(exc)},
                "high_volatility": False,
            }

    def _resolve_backtest_fundamentals_metadata(
        self,
        *,
        market: str,
        symbol: str,
        target_mode: str = "backtest",
    ) -> dict[str, Any]:
        market_n = str(market or "crypto").lower()
        instrument_type = "common" if market_n == "equities" else "other"
        try:
            payload = self.fundamentals_filter.evaluate(
                exchange=exchange_name(),
                market=market_n,
                symbol=str(symbol or "BTCUSDT"),
                instrument_type=instrument_type,
                target_mode=str(target_mode or "backtest"),
                asof_date=utc_now_iso(),
                source="auto",
                source_id=f"{market_n}:{symbol}",
                raw_payload={"market": market_n, "symbol": str(symbol or "BTCUSDT")},
            )
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            return {
                "enabled": False,
                "enforced": False,
                "snapshot_id": None,
                "allow_trade": True,
                "risk_multiplier": 1.0,
                "fund_score": 0.0,
                "fund_status": "UNKNOWN",
                "explain": [{"code": "FUND_METADATA_ERROR", "severity": "WARN", "message": str(exc)}],
                "reasons": [str(exc)],
                "required_missing": [],
                "promotion_blocked": False,
                "warnings": [],
                "fundamentals_quality": "snapshot",
            }

    def _sync_backtest_runs_catalog(self) -> None:
        runs = self.load_runs()
        changed = False
        meta = self.load_strategy_meta()
        for row in runs:
            if not isinstance(row, dict):
                continue
            before_catalog_id = str(row.get("catalog_run_id") or "")
            before_structured = str(row.get("strategy_structured_id") or "")
            try:
                self._record_backtest_catalog(
                    row,
                    strategy_meta=meta.get(str(row.get("strategy_id") or "")) if isinstance(meta, dict) else None,
                    created_by=str(row.get("created_by") or "system"),
                )
            except Exception:
                continue
            if str(row.get("catalog_run_id") or "") != before_catalog_id or str(row.get("strategy_structured_id") or "") != before_structured:
                changed = True
        if changed:
            self.save_runs(runs)

    def latest_run_for_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        return self.strategy_evidence.latest_run_for_strategy(strategy_id)

    def find_trade(self, trade_id: str) -> dict[str, Any] | None:
        for run in self.load_runs():
            for trade in run.get("trades", []):
                if trade.get("id") == trade_id:
                    return trade
        return None

    def create_backtest_run(
        self,
        strategy_id: str,
        start: str,
        end: str,
        universe: list[str],
        fees_bps: float,
        spread_bps: float,
        slippage_bps: float,
        funding_bps: float,
        validation_mode: str,
    ) -> dict[str, Any]:
        strategy = self.strategy_or_404(strategy_id)
        seed = int(hashlib.sha256(f"{strategy_id}:{start}:{end}:{','.join(universe)}".encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed)
        points: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        total_fees = 0.0
        total_spread = 0.0
        total_slippage = 0.0
        total_funding = 0.0
        total_gross_pnl = 0.0
        equity = 10000.0
        max_equity = equity
        for i in range(120):
            daily = rng.uniform(-45, 65)
            equity = round(equity + daily, 2)
            max_equity = max(max_equity, equity)
            dd = round((equity - max_equity) / max_equity, 4)
            points.append(
                {
                    "time": (utc_now() - timedelta(days=(120 - i))).isoformat(),
                    "equity": equity,
                    "drawdown": dd,
                }
            )
            if i % 3 == 0:
                entry = 99000 + rng.uniform(-4000, 4000)
                exit_px = entry + rng.uniform(-700, 900)
                side = "long" if rng.random() > 0.45 else "short"
                qty = 0.01
                entry_time_dt = utc_now() - timedelta(days=(120 - i), minutes=15)
                exit_time_dt = utc_now() - timedelta(days=(120 - i))

                gross_pnl = (exit_px - entry) * qty if side == "long" else (entry - exit_px) * qty
                entry_notional = abs(entry * qty)
                exit_notional = abs(exit_px * qty)
                roundtrip_notional = entry_notional + exit_notional

                # Cost model from backtest form: fees/slippage/spread per side and funding by holding period.
                fees_cost = roundtrip_notional * (fees_bps / 10000.0)
                spread_cost = roundtrip_notional * ((spread_bps / 2.0) / 10000.0)
                slippage_cost = roundtrip_notional * (slippage_bps / 10000.0)
                holding_minutes = max(1.0, (exit_time_dt - entry_time_dt).total_seconds() / 60.0)
                funding_periods = holding_minutes / 480.0
                funding_cost = ((entry_notional + exit_notional) / 2.0) * (funding_bps / 10000.0) * funding_periods
                total_cost = fees_cost + spread_cost + slippage_cost + funding_cost
                net_pnl = gross_pnl - total_cost

                total_fees += fees_cost
                total_spread += spread_cost
                total_slippage += slippage_cost
                total_funding += funding_cost
                total_gross_pnl += gross_pnl
                trades.append(
                    {
                        "id": f"tr_{secrets.token_hex(4)}",
                        "strategy_id": strategy_id,
                        "symbol": universe[i % len(universe)] if universe else "BTC/USDT",
                        "side": side,
                        "timeframe": "5m",
                        "entry_time": entry_time_dt.isoformat(),
                        "exit_time": exit_time_dt.isoformat(),
                        "entry_px": round(entry, 2),
                        "exit_px": round(exit_px, 2),
                        "qty": qty,
                        "fees": round(fees_cost, 4),
                        "spread_cost": round(spread_cost, 4),
                        "slippage_cost": round(slippage_cost, 4),
                        "funding_cost": round(funding_cost, 4),
                        "cost_total": round(total_cost, 4),
                        "slippage": round(spread_cost + slippage_cost, 4),
                        "pnl": round(gross_pnl, 4),
                        "pnl_net": round(net_pnl, 4),
                        "mae": round(abs(gross_pnl) * 0.7, 4),
                        "mfe": round(abs(gross_pnl) * 1.2, 4),
                        "reason_code": "pullback+flow",
                        "exit_reason": "tp" if net_pnl > 0 else "sl",
                        "events": [
                            {
                                "ts": (utc_now() - timedelta(days=(120 - i), minutes=14)).isoformat(),
                                "type": "signal",
                                "detail": "Checklist de entrada validado.",
                            },
                            {
                                "ts": (utc_now() - timedelta(days=(120 - i), minutes=13)).isoformat(),
                                "type": "fill",
                                "detail": "Orden ejecutada en book principal.",
                            },
                            {
                                "ts": (utc_now() - timedelta(days=(120 - i), minutes=1)).isoformat(),
                                "type": "exit",
                                "detail": "Salida por objetivo o stop.",
                            },
                        ],
                        "explain": {
                            "whitelist_ok": True,
                            "trend_ok": True,
                            "pullback_ok": True,
                            "orderflow_ok": True,
                            "vpin_ok": True,
                            "spread_ok": True,
                        },
                    }
                )
                try:
                    trades[-1]["regime_label"] = self._infer_trade_regime_label(
                        trades[-1],
                        {
                            "costs_model": {"spread_bps": spread_bps},
                            "metrics": {"turnover": 1.5 + random.random(), "max_dd": abs(max(0.0, dd)) if isinstance(dd, (int, float)) else 0.0},
                        },
                        strategy=self.strategy_or_404(strategy_id),
                    )
                except Exception:
                    trades[-1]["regime_label"] = "trend"
        returns = [points[i]["equity"] - points[i - 1]["equity"] for i in range(1, len(points))]
        avg_return = sum(returns) / max(1, len(returns))
        variance = sum((r - avg_return) ** 2 for r in returns) / max(1, len(returns))
        std = variance ** 0.5
        sharpe = round((avg_return / std) if std else 0.0, 2)
        cagr = round((points[-1]["equity"] / points[0]["equity"]) - 1, 4)
        max_dd = min(point["drawdown"] for point in points)
        wins = [trade for trade in trades if trade["pnl_net"] > 0]
        winrate = round(len(wins) / max(1, len(trades)), 4)
        expectancy = round(sum(trade["pnl_net"] for trade in trades) / max(1, len(trades)), 4)
        total_entries = len(trades)
        total_exits = sum(1 for trade in trades if trade.get("exit_time"))
        total_roundtrips = min(total_entries, total_exits)
        trade_count = len(trades)
        gross_abs = abs(total_gross_pnl)
        total_costs = total_fees + total_spread + total_slippage + total_funding
        robust_score = round(max(35.0, min(95.0, 70 + sharpe * 5 - abs(max_dd) * 90)), 2)
        avg_holding_time_min = round(
            sum(
                max(
                    0.0,
                    (datetime.fromisoformat(str(t["exit_time"])) - datetime.fromisoformat(str(t["entry_time"]))).total_seconds() / 60.0,
                )
                for t in trades
            )
            / max(1, len(trades)),
            4,
        )
        gross_profit_net = sum(t["pnl_net"] for t in trades if t["pnl_net"] > 0)
        gross_loss_net = abs(sum(t["pnl_net"] for t in trades if t["pnl_net"] < 0))
        profit_factor = round((gross_profit_net / gross_loss_net) if gross_loss_net else 0.0, 6)
        max_consecutive_losses = 0
        loss_streak = 0
        for trade in trades:
            if float(trade.get("pnl_net", 0.0)) < 0:
                loss_streak += 1
                max_consecutive_losses = max(max_consecutive_losses, loss_streak)
            else:
                loss_streak = 0
        run_id = self.backtest_catalog.next_formatted_id("BT")
        strategy_structured_id = self._catalog_strategy_structured_id(strategy_id, strategy)
        costs_model = {
            "fees_bps": fees_bps,
            "spread_bps": spread_bps,
            "slippage_bps": slippage_bps,
            "funding_bps": funding_bps,
        }
        cost_meta = self._resolve_backtest_cost_metadata(
            market="crypto",
            symbol=str(universe[0] if universe else "BTCUSDT"),
            costs_model=costs_model,
        )
        fundamentals_meta = self._resolve_backtest_fundamentals_metadata(
            market="crypto",
            symbol=str(universe[0] if universe else "BTCUSDT"),
            target_mode="BACKTEST",
        )
        run = {
            "id": run_id,
            "catalog_run_id": run_id,
            "run_type": "single",
            "batch_id": None,
            "parent_run_id": None,
            "strategy_id": strategy_id,
            "strategy_structured_id": strategy_structured_id,
            "strategy_name": str(strategy.get("name") or strategy_id),
            "strategy_version": str(strategy.get("version") or "1.0.0"),
            "mode": "backtest",
            "period": {"start": start, "end": end},
            "universe": universe,
            "data_source": "synthetic_seeded",
            "costs_model": costs_model,
            "fee_snapshot_id": cost_meta.get("fee_snapshot_id"),
            "funding_snapshot_id": cost_meta.get("funding_snapshot_id"),
            "spread_model_params": cost_meta.get("spread_model_params") or {},
            "slippage_model_params": cost_meta.get("slippage_model_params") or {},
            "fundamentals_snapshot_id": fundamentals_meta.get("snapshot_id"),
            "fund_status": fundamentals_meta.get("fund_status"),
            "fund_allow_trade": bool(fundamentals_meta.get("allow_trade", True)),
            "fund_risk_multiplier": float(fundamentals_meta.get("risk_multiplier") or 1.0),
            "fund_score": (
                float(fundamentals_meta.get("fund_score"))
                if isinstance(fundamentals_meta.get("fund_score"), (int, float))
                else None
            ),
            "fund_explain": fundamentals_meta.get("explain") if isinstance(fundamentals_meta.get("explain"), list) else [],
            "use_orderflow_data": True,
            "orderflow_feature_set": "orderflow_on",
            "feature_set": "orderflow_on",
            "fee_model": f"maker_taker_bps:{fees_bps:.4f}",
            "spread_model": f"{((cost_meta.get('spread_model_params') or {}).get('mode') or 'static')}:{spread_bps:.4f}",
            "slippage_model": f"{((cost_meta.get('slippage_model_params') or {}).get('mode') or 'static')}:{slippage_bps:.4f}",
            "funding_model": f"static:{funding_bps:.4f}",
            "validation_mode": validation_mode,
            "dataset_hash": hashlib.sha256(f"{run_id}:{strategy_id}:{start}:{end}".encode("utf-8")).hexdigest()[:16],
            "git_commit": get_env("GIT_COMMIT", "local"),
            "metrics": {
                "cagr": cagr,
                "max_dd": round(abs(max_dd), 4),
                "sharpe": sharpe,
                "sortino": round(sharpe * 1.22, 2),
                "calmar": round((cagr / abs(max_dd)) if max_dd else 0.0, 2),
                "winrate": winrate,
                "expectancy": expectancy,
                "expectancy_usd_per_trade": expectancy,
                "avg_trade": expectancy,
                "turnover": round(1.5 + random.random(), 2),
                "robust_score": robust_score,
                "robustness_score": robust_score,
                "total_entries": total_entries,
                "total_exits": total_exits,
                "total_roundtrips": total_roundtrips,
                "roundtrips": total_roundtrips,
                "trade_count": trade_count,
                "avg_holding_time": avg_holding_time_min,
                "profit_factor": profit_factor,
                "max_consecutive_losses": max_consecutive_losses,
                "exposure_time_pct": round(min(1.0, max(0.0, len(trades) * 0.02)), 6),
                "pbo": None,
                "dsr": None,
            },
            "costs_breakdown": {
                "gross_pnl_total": round(total_gross_pnl, 4),
                "gross_pnl": round(total_gross_pnl, 4),
                "fees_total": round(total_fees, 4),
                "spread_total": round(total_spread, 4),
                "slippage_total": round(total_slippage, 4),
                "funding_total": round(total_funding, 4),
                "total_cost": round(total_costs, 4),
                "net_pnl_total": round(total_gross_pnl - total_costs, 4),
                "net_pnl": round(total_gross_pnl - total_costs, 4),
                "fees_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(total_fees / gross_abs, 6),
                "spread_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(total_spread / gross_abs, 6),
                "slippage_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(total_slippage / gross_abs, 6),
                "funding_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(total_funding / gross_abs, 6),
                "total_cost_pct_of_gross_pnl": 0.0 if gross_abs == 0 else round(total_costs / gross_abs, 6),
            },
            "status": "completed",
            "created_by": "system",
            "created_at": utc_now_iso(),
            "started_at": utc_now_iso(),
            "finished_at": utc_now_iso(),
            "duration_sec": random.randint(20, 90),
            "equity_curve": points,
            "drawdown_curve": [{"time": p["time"], "value": p["drawdown"]} for p in points],
            "trades": trades,
            "tags": ["feature_set:orderflow_on"],
            "flags": {
                "IS": False,
                "OOS": bool(str(validation_mode or "").strip().lower() == "walk-forward"),
                "WFA": bool(str(validation_mode or "").strip().lower() == "walk-forward"),
                "PASO_GATES": False,
                "BASELINE": False,
                "FAVORITO": False,
                "ARCHIVADO": False,
                "ORDERFLOW_ENABLED": True,
                "ORDERFLOW_FEATURE_SET": "orderflow_on",
                "FUNDAMENTALS_PROMOTION_BLOCKED": bool(fundamentals_meta.get("promotion_blocked", False)),
            },
            "artifacts_links": {
                "report_json": f"/api/v1/backtests/runs/{run_id}?format=report_json",
                "trades_csv": f"/api/v1/backtests/runs/{run_id}?format=trades_csv",
                "equity_curve_csv": f"/api/v1/backtests/runs/{run_id}?format=equity_curve_csv",
            },
        }
        run["provenance"] = {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "mode": "backtest",
            "from": start,
            "to": end,
            "dataset_source": "synthetic_seeded",
            "dataset_hash": run["dataset_hash"],
            "costs_used": run["costs_model"],
            "commit_hash": run["git_commit"],
            "fee_snapshot_id": run.get("fee_snapshot_id"),
            "funding_snapshot_id": run.get("funding_snapshot_id"),
            "fundamentals_snapshot_id": run.get("fundamentals_snapshot_id"),
            "fund_status": run.get("fund_status"),
            "fund_allow_trade": run.get("fund_allow_trade"),
            "fund_risk_multiplier": run.get("fund_risk_multiplier"),
            "fund_score": run.get("fund_score"),
            "use_orderflow_data": True,
            "orderflow_feature_set": "orderflow_on",
            "fund_required_missing": run.get("fund_required_missing") if isinstance(run.get("fund_required_missing"), list) else [],
            "fund_warnings": run.get("fund_warnings") if isinstance(run.get("fund_warnings"), list) else [],
            "fund_promotion_blocked": bool(run.get("fund_promotion_blocked", False)),
            "fundamentals_quality": str(run.get("fundamentals_quality") or "snapshot"),
            "created_at": run["created_at"],
        }
        runs = self.load_runs()
        runs.insert(0, run)
        self.save_runs(runs)
        self._record_run_provenance(run)
        self._record_backtest_catalog(run, strategy_meta=strategy, created_by="system")
        meta = self.load_strategy_meta()
        if strategy_id in meta:
            meta[strategy_id]["last_run_at"] = utc_now_iso()
            meta[strategy_id]["updated_at"] = utc_now_iso()
            self.save_strategy_meta(meta)
        self.registry.add_backtest(
            strategy_id=strategy["db_strategy_id"],
            timerange=f"{start}:{end}",
            exchange=exchange_name(),
            pairs=universe,
            metrics=run["metrics"],
            artifacts_path=f"/api/v1/backtests/runs/{run_id}",
        )
        self.record_experience_run(run, source_override="backtest")
        self.add_log(
            event_type="backtest_finished",
            severity="info",
            module="backtest",
            message=f"Backtest finished: {run_id}",
            related_ids=[strategy_id, run_id],
            payload={"metrics": run["metrics"]},
        )
        return run

    def create_event_backtest_run(
        self,
        *,
        strategy_id: str,
        bot_id: str | None = None,
        market: str,
        symbol: str,
        timeframe: str,
        start: str,
        end: str,
        fees_bps: float,
        spread_bps: float,
        slippage_bps: float,
        funding_bps: float,
        rollover_bps: float,
        validation_mode: str,
        use_orderflow_data: bool = True,
        strict_strategy_id: bool = False,
        purge_bars: int | None = None,
        embargo_bars: int | None = None,
        cpcv_n_splits: int | None = None,
        cpcv_k_test_groups: int | None = None,
        cpcv_max_paths: int | None = None,
    ) -> dict[str, Any]:
        strategy = self.strategy_or_404(strategy_id)
        bot_id_n = str(bot_id or "").strip() or None
        market_n = normalize_market(market)
        symbol_n = normalize_symbol(symbol)
        timeframe_n = normalize_timeframe(timeframe)

        loader = DataLoader(USER_DATA_DIR)
        loaded = loader.load_resampled(market_n, symbol_n, timeframe_n, start, end)
        engine = BacktestEngine()
        engine_result = engine.run(
            BacktestRequest(
                market=market_n,
                symbol=symbol_n,
                timeframe=timeframe_n,
                start=start,
                end=end,
                strategy_id=strategy_id,
                validation_mode=validation_mode,
                use_orderflow_data=bool(use_orderflow_data),
                strict_strategy_id=bool(strict_strategy_id),
                purge_bars=purge_bars,
                embargo_bars=embargo_bars,
                cpcv_n_splits=cpcv_n_splits,
                cpcv_k_test_groups=cpcv_k_test_groups,
                cpcv_max_paths=cpcv_max_paths,
                costs=BacktestCosts(
                    fees_bps=fees_bps,
                    spread_bps=spread_bps,
                    slippage_bps=slippage_bps,
                    funding_bps=funding_bps,
                    rollover_bps=rollover_bps,
                ),
            ),
            MarketDataset(
                market=market_n,
                symbol=symbol_n,
                timeframe=timeframe_n,
                source=loaded.source,
                dataset_hash=loaded.dataset_hash,
                df=loaded.df,
                manifest=loaded.manifest,
            ),
        )
        run_id = self.backtest_catalog.next_formatted_id("BT")
        metrics = dict(engine_result["metrics"])
        metrics["expectancy_unit"] = "usd_per_trade"
        metrics["expectancy_pct_unit"] = "pct_per_trade"
        strategy_structured_id = self._catalog_strategy_structured_id(strategy_id, strategy)
        costs_model = {
            "fees_bps": fees_bps,
            "spread_bps": spread_bps,
            "slippage_bps": slippage_bps,
            "funding_bps": funding_bps,
            "rollover_bps": rollover_bps,
        }
        cost_meta = self._resolve_backtest_cost_metadata(
            market=market_n,
            symbol=symbol_n,
            costs_model=costs_model,
            df=loaded.df,
        )
        fundamentals_meta = self._resolve_backtest_fundamentals_metadata(
            market=market_n,
            symbol=symbol_n,
            target_mode="BACKTEST",
        )
        fund_required_missing = [str(x) for x in (fundamentals_meta.get("required_missing") or []) if str(x).strip()]
        fund_warnings = [str(x) for x in (fundamentals_meta.get("warnings") or []) if str(x).strip()]
        fund_reasons = [str(x) for x in (fundamentals_meta.get("reasons") or []) if str(x).strip()]
        fund_promotion_blocked = bool(fundamentals_meta.get("promotion_blocked", False))
        fund_quality = str(fundamentals_meta.get("fundamentals_quality") or ("ohlc_only" if fund_required_missing else "snapshot"))
        if bool(fundamentals_meta.get("enforced")) and not bool(fundamentals_meta.get("allow_trade", False)):
            reasons = " | ".join(
                [
                    str((row or {}).get("message") or (row or {}).get("code") or "")
                    for row in (fundamentals_meta.get("explain") or [])
                    if isinstance(row, dict)
                ][:3]
            )
            detail = " | ".join([x for x in [*fund_reasons, reasons] if x][:3]).strip()
            raise ValueError(f"Fundamentals/credit_filter bloqueó la corrida para {market_n}/{symbol_n}. {detail}".strip())
        orderflow_enabled = bool(use_orderflow_data) and market_n != "equities"
        orderflow_feature_set = "orderflow_on" if orderflow_enabled else "orderflow_off"
        run_metadata = {
            "warnings": fund_warnings,
            "fundamentals_quality": fund_quality,
            "promotion_blocked": fund_promotion_blocked,
            "use_orderflow_data_requested": bool(use_orderflow_data),
            "use_orderflow_data": orderflow_enabled,
            "strict_strategy_id": bool(strict_strategy_id),
            "orderflow_feature_set": orderflow_feature_set,
            "orderflow_feature_source": "request",
        }
        if isinstance(purge_bars, int):
            run_metadata["purge_bars"] = int(max(0, purge_bars))
        if isinstance(embargo_bars, int):
            run_metadata["embargo_bars"] = int(max(0, embargo_bars))
        if isinstance(cpcv_n_splits, int):
            run_metadata["cpcv_n_splits"] = int(max(0, cpcv_n_splits))
        if isinstance(cpcv_k_test_groups, int):
            run_metadata["cpcv_k_test_groups"] = int(max(0, cpcv_k_test_groups))
        if isinstance(cpcv_max_paths, int):
            run_metadata["cpcv_max_paths"] = int(max(0, cpcv_max_paths))
        if bool(use_orderflow_data) and market_n == "equities":
            run_metadata["warnings"] = list(run_metadata.get("warnings") or []) + ["orderflow_not_available_for_market"]
        if fund_required_missing:
            run_metadata["required_missing"] = fund_required_missing
        if fund_reasons:
            run_metadata["fundamentals_reasons"] = fund_reasons
        if bot_id_n:
            run_metadata["bot_id"] = bot_id_n
        run_tags = []
        if fund_quality == "ohlc_only":
            run_tags.append("fundamentals_quality:ohlc_only")
        if fund_promotion_blocked:
            run_tags.append("promotion_blocked:fundamentals")
        run_tags.append(f"feature_set:{orderflow_feature_set}")
        if bot_id_n:
            run_tags.append(f"bot:{bot_id_n}")
        validation_mode_norm = str(validation_mode or "").strip().lower()
        is_wfa = validation_mode_norm == "walk-forward"
        is_oos = validation_mode_norm in {"walk-forward", "purged-cv", "cpcv"}
        run = {
            "id": run_id,
            "catalog_run_id": run_id,
            "run_type": "single",
            "batch_id": None,
            "parent_run_id": None,
            "strategy_id": strategy_id,
            "strategy_structured_id": strategy_structured_id,
            "strategy_name": str(strategy.get("name") or strategy_id),
            "strategy_version": str(strategy.get("version") or "1.0.0"),
            "mode": "backtest",
            "market": market_n,
            "symbol": symbol_n,
            "timeframe": timeframe_n,
            "period": {"start": start, "end": end},
            "universe": [symbol_n],
            "validation_mode": validation_mode,
            "validation_summary": engine_result.get("validation_summary"),
            "data_source": loaded.source,
            "dataset_hash": loaded.dataset_hash,
            "dataset_manifest": loaded.manifest,
            "dataset_range": {"start": loaded.start, "end": loaded.end},
            "costs_model": costs_model,
            "fee_snapshot_id": cost_meta.get("fee_snapshot_id"),
            "funding_snapshot_id": cost_meta.get("funding_snapshot_id"),
            "spread_model_params": cost_meta.get("spread_model_params") or {},
            "slippage_model_params": cost_meta.get("slippage_model_params") or {},
            "fundamentals_snapshot_id": fundamentals_meta.get("snapshot_id"),
            "fund_status": fundamentals_meta.get("fund_status"),
            "fund_allow_trade": bool(fundamentals_meta.get("allow_trade", True)),
            "fund_risk_multiplier": float(fundamentals_meta.get("risk_multiplier") or 1.0),
            "fund_score": (
                float(fundamentals_meta.get("fund_score"))
                if isinstance(fundamentals_meta.get("fund_score"), (int, float))
                else None
            ),
            "fund_explain": fundamentals_meta.get("explain") if isinstance(fundamentals_meta.get("explain"), list) else [],
            "fund_required_missing": fund_required_missing,
            "fund_warnings": fund_warnings,
            "fund_reasons": fund_reasons,
            "fund_promotion_blocked": fund_promotion_blocked,
            "fundamentals_quality": fund_quality,
            "use_orderflow_data": orderflow_enabled,
            "orderflow_feature_set": orderflow_feature_set,
            "feature_set": orderflow_feature_set,
            "fee_model": f"maker_taker_bps:{fees_bps:.4f}",
            "spread_model": f"{((cost_meta.get('spread_model_params') or {}).get('mode') or 'static')}:{spread_bps:.4f}",
            "slippage_model": f"{((cost_meta.get('slippage_model_params') or {}).get('mode') or 'static')}:{slippage_bps:.4f}",
            "funding_model": f"static:{funding_bps:.4f}",
            "git_commit": get_env("GIT_COMMIT", "local"),
            "metrics": metrics,
            "costs_breakdown": engine_result["costs_breakdown"],
            "status": "completed",
            "created_by": "system",
            "created_at": utc_now_iso(),
            "started_at": utc_now_iso(),
            "finished_at": utc_now_iso(),
            "duration_sec": random.randint(2, 30),
            "metadata": run_metadata,
            "tags": run_tags,
            "flags": {
                "IS": False,
                "OOS": bool(is_oos),
                "WFA": bool(is_wfa),
                "PASO_GATES": False,
                "BASELINE": False,
                "FAVORITO": False,
                "ARCHIVADO": False,
                "FUNDAMENTALS_PROMOTION_BLOCKED": bool(fund_promotion_blocked),
                "ORDERFLOW_ENABLED": bool(orderflow_enabled),
                "ORDERFLOW_FEATURE_SET": orderflow_feature_set,
            },
            "params_json": {
                "validation_mode": validation_mode,
                "bot_id": bot_id_n,
                "costs_model": costs_model,
                "dataset_range": {"start": loaded.start, "end": loaded.end},
                "period": {"start": start, "end": end},
                "use_orderflow_data": bool(orderflow_enabled),
                "strict_strategy_id": bool(strict_strategy_id),
                "orderflow_feature_set": orderflow_feature_set,
                "purge_bars": int(max(0, purge_bars)) if isinstance(purge_bars, int) else None,
                "embargo_bars": int(max(0, embargo_bars)) if isinstance(embargo_bars, int) else None,
                "cpcv_n_splits": int(max(0, cpcv_n_splits)) if isinstance(cpcv_n_splits, int) else None,
                "cpcv_k_test_groups": int(max(0, cpcv_k_test_groups)) if isinstance(cpcv_k_test_groups, int) else None,
                "cpcv_max_paths": int(max(0, cpcv_max_paths)) if isinstance(cpcv_max_paths, int) else None,
            },
            "equity_curve": engine_result["equity_curve"],
            "drawdown_curve": engine_result["drawdown_curve"],
            "trades": engine_result["trades"],
            "artifacts_links": {
                "report_json": f"/api/v1/backtests/runs/{run_id}?format=report_json",
                "trades_csv": f"/api/v1/backtests/runs/{run_id}?format=trades_csv",
                "equity_curve_csv": f"/api/v1/backtests/runs/{run_id}?format=equity_curve_csv",
            },
        }
        for trade in run.get("trades", []) or []:
            if isinstance(trade, dict) and not trade.get("regime_label"):
                trade["regime_label"] = self._infer_trade_regime_label(trade, run, strategy=strategy)
        run["provenance"] = {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "bot_id": bot_id_n,
            "mode": "backtest",
            "from": start,
            "to": end,
            "dataset_source": loaded.source,
            "dataset_hash": loaded.dataset_hash,
            "costs_used": run["costs_model"],
            "commit_hash": run["git_commit"],
            "fee_snapshot_id": run.get("fee_snapshot_id"),
            "funding_snapshot_id": run.get("funding_snapshot_id"),
            "fundamentals_snapshot_id": run.get("fundamentals_snapshot_id"),
            "fund_status": run.get("fund_status"),
            "fund_allow_trade": run.get("fund_allow_trade"),
            "fund_risk_multiplier": run.get("fund_risk_multiplier"),
            "fund_score": run.get("fund_score"),
            "use_orderflow_data": bool(orderflow_enabled),
            "strict_strategy_id": bool(strict_strategy_id),
            "orderflow_feature_set": orderflow_feature_set,
            "purge_bars": int(max(0, purge_bars)) if isinstance(purge_bars, int) else None,
            "embargo_bars": int(max(0, embargo_bars)) if isinstance(embargo_bars, int) else None,
            "cpcv_n_splits": int(max(0, cpcv_n_splits)) if isinstance(cpcv_n_splits, int) else None,
            "cpcv_k_test_groups": int(max(0, cpcv_k_test_groups)) if isinstance(cpcv_k_test_groups, int) else None,
            "cpcv_max_paths": int(max(0, cpcv_max_paths)) if isinstance(cpcv_max_paths, int) else None,
            "created_at": run["created_at"],
        }
        artifact_local = ArtifactReportEngine(USER_DATA_DIR).write_backtest_artifacts(run_id, run)
        run["artifacts_local"] = artifact_local

        runs = self.load_runs()
        runs.insert(0, run)
        self.save_runs(runs)
        self._record_run_provenance(run)
        self._record_backtest_catalog(run, strategy_meta=strategy, created_by="system")
        meta = self.load_strategy_meta()
        if strategy_id in meta:
            meta[strategy_id]["last_run_at"] = utc_now_iso()
            meta[strategy_id]["updated_at"] = utc_now_iso()
            self.save_strategy_meta(meta)
        self.registry.add_backtest(
            strategy_id=strategy["db_strategy_id"],
            timerange=f"{start}:{end}",
            exchange=f"{market_n}:{exchange_name()}",
            pairs=[symbol_n],
            metrics={
                "metrics": run["metrics"],
                "costs_breakdown": run["costs_breakdown"],
                "data_source": loaded.source,
                "dataset_hash": loaded.dataset_hash,
                "timeframe": timeframe_n,
            },
            artifacts_path=f"/api/v1/backtests/runs/{run_id}",
        )
        self.record_experience_run(run, source_override="backtest", bot_id=bot_id_n)
        self.add_log(
            event_type="backtest_finished",
            severity="info",
            module="backtest",
            message=f"Backtest finished: {run_id}",
            related_ids=[x for x in [strategy_id, run_id, symbol_n, bot_id_n] if x],
            payload={
                "bot_id": bot_id_n,
                "market": market_n,
                "symbol": symbol_n,
                "timeframe": timeframe_n,
                "metrics": run["metrics"],
                "costs_breakdown": run["costs_breakdown"],
                "dataset_hash": loaded.dataset_hash,
                "data_source": loaded.source,
                "metadata": run.get("metadata") if isinstance(run.get("metadata"), dict) else {},
            },
        )
        return run

    def create_shadow_live_run(
        self,
        *,
        bot_id: str,
        strategy_id: str,
        symbol: str,
        timeframe: str,
        lookback_bars: int,
        simulation: dict[str, Any],
        use_orderflow_data: bool = True,
        note: str | None = None,
    ) -> dict[str, Any]:
        strategy = self.strategy_or_404(strategy_id)
        dataset = simulation.get("dataset")
        engine_result = simulation.get("engine_result") if isinstance(simulation.get("engine_result"), dict) else {}
        manifest = simulation.get("manifest") if isinstance(simulation.get("manifest"), dict) else {}
        costs_model = simulation.get("costs") if isinstance(simulation.get("costs"), dict) else {}
        if not dataset or not engine_result:
            raise ValueError("Shadow simulation incompleta.")
        market_n = str(getattr(dataset, "market", "crypto") or "crypto")
        symbol_n = str(getattr(dataset, "symbol", symbol) or symbol).upper()
        timeframe_n = str(getattr(dataset, "timeframe", timeframe) or timeframe)
        run_id = self.backtest_catalog.next_formatted_id("SH")
        metrics = dict(engine_result.get("metrics") or {})
        metrics["expectancy_unit"] = "usd_per_trade"
        metrics["expectancy_pct_unit"] = "pct_per_trade"
        strategy_structured_id = self._catalog_strategy_structured_id(strategy_id, strategy)
        cost_meta = self._resolve_backtest_cost_metadata(
            market=market_n,
            symbol=symbol_n,
            costs_model=costs_model,
            df=getattr(dataset, "df", None),
        )
        orderflow_enabled = bool(use_orderflow_data)
        orderflow_feature_set = "orderflow_on" if orderflow_enabled else "orderflow_off"
        started_at = str(manifest.get("start") or utc_now_iso())
        finished_at = str(manifest.get("end") or utc_now_iso())
        decision_events = engine_result.get("decision_events") if isinstance(engine_result.get("decision_events"), list) else []
        if not decision_events:
            decision_events = [
                {
                    "ts": finished_at,
                    "action": "hold" if engine_result.get("trades") else "skip",
                    "side": "flat",
                    "regime_label": "unknown",
                    "features_json": {
                        "symbol": symbol_n,
                        "timeframe": timeframe_n,
                        "lookback_bars": int(max(1, lookback_bars)),
                    },
                    "notes": "shadow_runner_closed_candle",
                }
            ]
        run = {
            "id": run_id,
            "catalog_run_id": run_id,
            "run_type": "single",
            "batch_id": None,
            "parent_run_id": None,
            "strategy_id": strategy_id,
            "strategy_structured_id": strategy_structured_id,
            "strategy_name": str(strategy.get("name") or strategy_id),
            "strategy_version": str(strategy.get("version") or "1.0.0"),
            "mode": "shadow",
            "market": market_n,
            "symbol": symbol_n,
            "timeframe": timeframe_n,
            "period": {"start": started_at, "end": finished_at},
            "universe": [symbol_n],
            "validation_mode": "shadow_live",
            "validation_summary": {
                "mode": "shadow_live",
                "no_orders_sent": True,
                "requires_human_approval": True,
                "allow_live": False,
            },
            "data_source": str(getattr(dataset, "source", "binance_public_klines") or "binance_public_klines"),
            "dataset_hash": str(getattr(dataset, "dataset_hash", "") or ""),
            "dataset_manifest": manifest,
            "dataset_range": {"start": started_at, "end": finished_at},
            "costs_model": {
                "fees_bps": float(costs_model.get("fees_bps", 0.0) or 0.0),
                "spread_bps": float(costs_model.get("spread_bps", 0.0) or 0.0),
                "slippage_bps": float(costs_model.get("slippage_bps", 0.0) or 0.0),
                "funding_bps": float(costs_model.get("funding_bps", 0.0) or 0.0),
                "rollover_bps": float(costs_model.get("rollover_bps", 0.0) or 0.0),
            },
            "fee_snapshot_id": cost_meta.get("fee_snapshot_id"),
            "funding_snapshot_id": cost_meta.get("funding_snapshot_id"),
            "spread_model_params": cost_meta.get("spread_model_params") or {},
            "slippage_model_params": cost_meta.get("slippage_model_params") or {},
            "use_orderflow_data": orderflow_enabled,
            "orderflow_feature_set": orderflow_feature_set,
            "feature_set": orderflow_feature_set,
            "fee_model": f"maker_taker_bps:{float(costs_model.get('fees_bps', 0.0) or 0.0):.4f}",
            "spread_model": f"observed_or_static:{float(costs_model.get('spread_bps', 0.0) or 0.0):.4f}",
            "slippage_model": f"static:{float(costs_model.get('slippage_bps', 0.0) or 0.0):.4f}",
            "funding_model": f"static:{float(costs_model.get('funding_bps', 0.0) or 0.0):.4f}",
            "git_commit": get_env("GIT_COMMIT", "local"),
            "metrics": metrics,
            "costs_breakdown": engine_result.get("costs_breakdown") or {},
            "status": "completed",
            "created_by": "shadow_runner",
            "created_at": utc_now_iso(),
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_sec": max(1, int(engine_result.get("duration_sec") or 1)),
            "metadata": {
                "shadow": True,
                "bot_id": bot_id,
                "lookback_bars": int(max(1, lookback_bars)),
                "marketdata_base_url": str(manifest.get("marketdata_base_url") or SHADOW_MARKETDATA_BASE_URL),
                "observed_spread_bps": float(manifest.get("observed_spread_bps") or 0.0),
                "base_interval": str(manifest.get("base_interval") or timeframe_n),
                "resampled": bool(manifest.get("resampled", False)),
                "allow_live": False,
                "orders_sent": False,
            },
            "tags": [f"feature_set:{orderflow_feature_set}", "source:shadow", "mode:shadow", f"bot:{bot_id}"],
            "flags": {
                "IS": False,
                "OOS": False,
                "WFA": False,
                "PASO_GATES": False,
                "BASELINE": False,
                "FAVORITO": False,
                "ARCHIVADO": False,
                "ORDERFLOW_ENABLED": bool(orderflow_enabled),
                "ORDERFLOW_FEATURE_SET": orderflow_feature_set,
                "LIVE_BLOCKED": True,
            },
            "params_json": {
                "validation_mode": "shadow_live",
                "costs_model": costs_model,
                "lookback_bars": int(max(1, lookback_bars)),
                "use_orderflow_data": bool(orderflow_enabled),
                "orderflow_feature_set": orderflow_feature_set,
                "bot_id": bot_id,
            },
            "equity_curve": engine_result.get("equity_curve") or [],
            "drawdown_curve": engine_result.get("drawdown_curve") or [],
            "trades": engine_result.get("trades") or [],
            "decision_events": decision_events,
            "artifacts_links": {
                "report_json": f"/api/v1/backtests/runs/{run_id}?format=report_json",
                "trades_csv": f"/api/v1/backtests/runs/{run_id}?format=trades_csv",
                "equity_curve_csv": f"/api/v1/backtests/runs/{run_id}?format=equity_curve_csv",
            },
            "notes": str(note or ""),
        }
        for trade in run.get("trades", []) or []:
            if isinstance(trade, dict) and not trade.get("regime_label"):
                trade["regime_label"] = self._infer_trade_regime_label(trade, run, strategy=strategy)
        run["provenance"] = {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "mode": "shadow",
            "from": started_at,
            "to": finished_at,
            "dataset_source": run["data_source"],
            "dataset_hash": run["dataset_hash"],
            "costs_used": run["costs_model"],
            "commit_hash": run["git_commit"],
            "bot_id": bot_id,
            "use_orderflow_data": bool(orderflow_enabled),
            "orderflow_feature_set": orderflow_feature_set,
            "created_at": run["created_at"],
        }
        artifact_local = ArtifactReportEngine(USER_DATA_DIR).write_backtest_artifacts(run_id, run)
        run["artifacts_local"] = artifact_local
        runs = self.load_runs()
        runs.insert(0, run)
        self.save_runs(runs)
        self._record_run_provenance(run)
        self._record_backtest_catalog(run, strategy_meta=strategy, created_by="shadow_runner")
        self.record_experience_run(run, source_override="shadow", bot_id=bot_id)
        self.add_log(
            event_type="shadow_run_completed",
            severity="info",
            module="learning",
            message=f"Shadow run completado: {run_id}",
            related_ids=[bot_id, strategy_id, run_id, symbol_n],
            payload={
                "bot_id": bot_id,
                "strategy_id": strategy_id,
                "symbol": symbol_n,
                "timeframe": timeframe_n,
                "metrics": run["metrics"],
                "costs_breakdown": run["costs_breakdown"],
                "dataset_hash": run["dataset_hash"],
                "data_source": run["data_source"],
                "allow_live": False,
            },
        )
        return run

    def add_log(
        self,
        event_type: str,
        severity: str,
        module: str,
        message: str,
        related_ids: list[str],
        payload: dict[str, Any],
    ) -> int:
        event_type_norm = str(event_type or "").strip().lower()
        log_id = self.decision_log.add_log(
            event_type=event_type,
            severity=severity,
            module=module,
            message=message,
            related_ids=related_ids,
            payload=payload,
        )
        if event_type_norm == "breaker_triggered":
            try:
                _invalidate_bots_overview_cache()
            except Exception:
                pass
        return log_id

    def logs_since(self, min_id: int) -> list[dict[str, Any]]:
        return self.decision_log.logs_since(min_id)

    def list_logs(
        self,
        severity: str | None,
        module: str | None,
        since: str | None,
        until: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        return self.decision_log.list_logs(
            severity=severity,
            module=module,
            since=since,
            until=until,
            page=page,
            page_size=page_size,
        )

    def list_breaker_events_for_bot(
        self,
        bot_id: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        bot = self.bot_or_404(bot_id)
        clauses = ["bot_id = ?"]
        params: list[Any] = [str(bot.get("id") or bot_id)]
        if since:
            clauses.append("ts >= ?")
            params.append(since)
        if until:
            clauses.append("ts <= ?")
            params.append(until)
        where_sql = f"WHERE {' AND '.join(clauses)}"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, ts, bot_id, mode, reason, run_id, symbol, source_log_id
                FROM breaker_events
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                tuple(params + [max(1, int(limit))]),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "ts": str(row["ts"] or ""),
                "bot_id": str(row["bot_id"] or ""),
                "mode": str(row["mode"] or ""),
                "reason": str(row["reason"] or ""),
                "run_id": str(row["run_id"] or "") if row["run_id"] is not None else None,
                "symbol": str(row["symbol"] or "") if row["symbol"] is not None else None,
                "source_log_id": int(row["source_log_id"]) if row["source_log_id"] is not None else None,
            }
            for row in rows
        ]

    def bot_decision_log(
        self,
        bot_id: str,
        *,
        severity: str | None,
        module: str | None,
        since: str | None,
        until: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        bot = self.bot_or_404(bot_id)
        bot_id_n = str(bot.get("id") or bot_id)
        clauses = ["r.bot_id = ?"]
        params: list[Any] = [bot_id_n]
        if severity:
            clauses.append("l.severity = ?")
            params.append(severity)
        if module:
            clauses.append("l.module = ?")
            params.append(module)
        if since:
            clauses.append("l.ts >= ?")
            params.append(since)
        if until:
            clauses.append("l.ts <= ?")
            params.append(until)
        where_sql = f"WHERE {' AND '.join(clauses)}"
        offset = (max(page, 1) - 1) * max(page_size, 1)
        items: list[dict[str, Any]]
        total: int
        try:
            with self._connect() as conn:
                total_row = conn.execute(
                    f"""
                    SELECT COUNT(*) AS n
                    FROM log_bot_refs r
                    JOIN logs l ON l.id = r.log_id
                    {where_sql}
                    """,
                    tuple(params),
                ).fetchone()
                rows = conn.execute(
                    f"""
                    SELECT l.*
                    FROM log_bot_refs r
                    JOIN logs l ON l.id = r.log_id
                    {where_sql}
                    ORDER BY l.id DESC
                    LIMIT ? OFFSET ?
                    """,
                    tuple(params + [page_size, offset]),
                ).fetchall()
            items = [self._log_row_to_dict(row) for row in rows]
            total = int(total_row["n"]) if total_row else 0
        except sqlite3.OperationalError:
            fallback_rows = [
                row
                for row in self.list_logs(
                    severity=severity,
                    module=module,
                    since=since,
                    until=until,
                    page=1,
                    page_size=5000,
                )["items"]
                if self._log_targets_bot(row, bot_id_n)
            ]
            total = len(fallback_rows)
            items = fallback_rows[offset : offset + max(page_size, 1)]
        return {
            "bot_id": bot_id_n,
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "breaker_events": self.list_breaker_events_for_bot(bot_id_n, since=since, until=until, limit=min(max(page_size, 1), 250)),
        }

    @staticmethod
    def _log_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": f"log_{row['id']}",
            "numeric_id": int(row["id"]),
            "ts": row["ts"],
            "type": row["type"],
            "severity": row["severity"],
            "module": row["module"],
            "message": row["message"],
            "related_ids": json.loads(row["related_ids"]),
            "payload": json.loads(row["payload_json"]),
        }

    def create_session(self, username: str, role: str) -> str:
        token = secrets.token_urlsafe(32)
        expires = (utc_now() + timedelta(hours=12)).isoformat()
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (utc_now_iso(),))
            conn.execute(
                "INSERT INTO sessions (token, username, role, expires_at) VALUES (?, ?, ?, ?)",
                (token, username, role, expires),
            )
            conn.commit()
        return token

    def get_session(self, token: str) -> dict[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT username, role, expires_at FROM sessions WHERE token = ?",
                (token,),
            ).fetchone()
        if not row:
            return None
        if row["expires_at"] < utc_now_iso():
            return None
        return {"username": row["username"], "role": row["role"]}


_validate_auth_config_for_production()

store = ConsoleStore()
learning_service = LearningService(user_data_dir=USER_DATA_DIR, repo_root=MONOREPO_ROOT)
option_b_engine = OptionBLearningEngine(store.registry)
rollout_manager = RolloutManager(user_data_dir=USER_DATA_DIR)
mass_backtest_engine = MassBacktestEngine(user_data_dir=USER_DATA_DIR, repo_root=MONOREPO_ROOT, knowledge_loader=KnowledgeLoader(repo_root=MONOREPO_ROOT))
mass_backtest_coordinator = MassBacktestCoordinator(engine=mass_backtest_engine)
rollout_gates = GateEvaluator(repo_root=MONOREPO_ROOT)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _load_runtime_risk_policy_thresholds() -> dict[str, Any]:
    defaults = {
        "source": "settings",
        "soft_daily_loss_pct": None,
        "hard_daily_loss_pct": None,
        "hard_drawdown_pct": None,
    }
    policy_path = (CONFIG_POLICIES_ROOT / "risk_policy.yaml").resolve()
    if not policy_path.exists():
        return defaults
    try:
        payload = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        root = payload.get("risk_policy") if isinstance(payload.get("risk_policy"), dict) else {}
        triggers = root.get("triggers") if isinstance(root.get("triggers"), dict) else {}
        daily_cfg = triggers.get("daily_loss_pct") if isinstance(triggers.get("daily_loss_pct"), dict) else {}
        dd_cfg = triggers.get("max_drawdown_pct") if isinstance(triggers.get("max_drawdown_pct"), dict) else {}
        soft_daily = abs(_as_float(daily_cfg.get("soft_kill_bot_at"), 0.0)) / 100.0 if bool(daily_cfg.get("enabled", False)) else 0.0
        hard_daily = abs(_as_float(daily_cfg.get("hard_kill_bot_at"), 0.0)) / 100.0 if bool(daily_cfg.get("enabled", False)) else 0.0
        hard_dd = abs(_as_float(dd_cfg.get("hard_kill_bot_at"), 0.0)) / 100.0 if bool(dd_cfg.get("enabled", False)) else 0.0
        return {
            "source": "config/policies/risk_policy.yaml",
            "soft_daily_loss_pct": soft_daily if soft_daily > 0 else None,
            "hard_daily_loss_pct": hard_daily if hard_daily > 0 else None,
            "hard_drawdown_pct": hard_dd if hard_dd > 0 else None,
        }
    except Exception:
        return defaults


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        try:
            return float(value)
        except Exception:
            continue
    return None


def _proposal_status_normalized(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"pending_review", "pending"}:
        return "pending"
    if raw in {"approved", "rejected", "needs_validation"}:
        return raw
    return raw or "unknown"


def _proposal_signature_key(*, strategy_id: str, asset: str, timeframe: str) -> tuple[str, str, str]:
    return (
        str(strategy_id or "").strip(),
        str(asset or "").strip().upper(),
        str(timeframe or "").strip().lower(),
    )


def _trial_costs_snapshot(summary: dict[str, Any], catalog_run: dict[str, Any] | None) -> dict[str, Any]:
    summary_costs = summary.get("costs_breakdown") if isinstance(summary.get("costs_breakdown"), dict) else {}
    kpis = catalog_run.get("kpis") if isinstance((catalog_run or {}).get("kpis"), dict) else {}
    gross_pnl = _first_number(summary_costs.get("gross_pnl_total"), summary_costs.get("gross_pnl"), kpis.get("gross_pnl"))
    net_pnl = _first_number(summary_costs.get("net_pnl_total"), summary_costs.get("net_pnl"), kpis.get("net_pnl"))
    fees_total = _first_number(summary_costs.get("fees_total"), summary_costs.get("fees"), kpis.get("fees_total"))
    spread_total = _first_number(summary_costs.get("spread_total"), summary_costs.get("spread_cost"), kpis.get("spread_total"))
    slippage_total = _first_number(summary_costs.get("slippage_total"), summary_costs.get("slippage_cost"), kpis.get("slippage_total"))
    funding_total = _first_number(summary_costs.get("funding_total"), summary_costs.get("funding_cost"), kpis.get("funding_total"))
    total_cost = _first_number(summary_costs.get("total_cost"), summary_costs.get("total_cost_usd"))
    total_cost_source = "reported"
    components_complete = all(value is not None for value in (fees_total, spread_total, slippage_total, funding_total))
    components_present = any(value is not None for value in (fees_total, spread_total, slippage_total, funding_total))
    if total_cost is None and components_complete:
        total_cost = float((fees_total or 0.0) + (spread_total or 0.0) + (slippage_total or 0.0) + (funding_total or 0.0))
        total_cost_source = "components_sum"
    if total_cost is None and gross_pnl is not None and net_pnl is not None:
        total_cost = abs(float(gross_pnl) - float(net_pnl))
        total_cost_source = "gross_minus_net"
    return {
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "fees_total": fees_total,
        "spread_total": spread_total,
        "slippage_total": slippage_total,
        "funding_total": funding_total,
        "total_cost": total_cost,
        "total_cost_source": total_cost_source,
        "components_complete": bool(components_complete),
        "components_present": bool(components_present),
    }


def _classify_trial_evidence(
    *,
    episode: dict[str, Any] | None,
    catalog_run: dict[str, Any] | None,
) -> dict[str, Any]:
    summary = episode.get("summary") if isinstance((episode or {}).get("summary"), dict) else {}
    symbols = (catalog_run or {}).get("symbols") if isinstance((catalog_run or {}).get("symbols"), list) else []
    timeframes = (catalog_run or {}).get("timeframes") if isinstance((catalog_run or {}).get("timeframes"), list) else []
    strategy_id = _first_text((episode or {}).get("strategy_id"), (catalog_run or {}).get("strategy_id"))
    asset = _first_text((episode or {}).get("asset"), symbols[0] if symbols else "")
    timeframe = _first_text((episode or {}).get("timeframe"), timeframes[0] if timeframes else "")
    start_ts = _first_text((episode or {}).get("start_ts"), (catalog_run or {}).get("timerange_from"))
    end_ts = _first_text((episode or {}).get("end_ts"), (catalog_run or {}).get("timerange_to"), (catalog_run or {}).get("finished_at"))
    dataset_source = _first_text(
        (episode or {}).get("dataset_source"),
        summary.get("dataset_source"),
        (catalog_run or {}).get("dataset_source"),
    )
    dataset_hash = _first_text((episode or {}).get("dataset_hash"), (catalog_run or {}).get("dataset_hash"))
    commit_hash = _first_text((episode or {}).get("commit_hash"), (catalog_run or {}).get("code_commit_hash"))
    feature_set = _first_text(summary.get("feature_set"), (episode or {}).get("feature_set"))
    validation_quality = _first_text((episode or {}).get("validation_quality"))
    cost_fidelity_level = _first_text((episode or {}).get("cost_fidelity_level"))
    costs = _trial_costs_snapshot(summary, catalog_run)
    flags: list[str] = []
    critical_missing: list[str] = []
    traceability_missing: list[str] = []
    degraded_flags: list[str] = []

    if episode is None:
        flags.append("catalog_only_no_episode")
        if not dataset_hash:
            flags.append("missing_dataset_hash")
        if not dataset_source:
            flags.append("missing_dataset_source")
        return {
            "evidence_status": "legacy",
            "evidence_flags": flags,
            "learning_excluded": True,
            "validation_quality": validation_quality or "catalog_only",
            "cost_fidelity_level": cost_fidelity_level or "catalog_only",
            "feature_set": feature_set or "unknown",
            "costs": costs,
        }

    if not strategy_id:
        critical_missing.append("missing_strategy_id")
    if not asset:
        critical_missing.append("missing_asset")
    if not timeframe:
        critical_missing.append("missing_timeframe")
    if not start_ts:
        critical_missing.append("missing_start_ts")
    if not end_ts:
        critical_missing.append("missing_end_ts")
    if str((episode or {}).get("source") or "backtest").strip().lower() == "backtest" and not dataset_hash:
        critical_missing.append("missing_dataset_hash")
    if costs.get("gross_pnl") is None:
        critical_missing.append("missing_gross_pnl")
    if costs.get("net_pnl") is None:
        critical_missing.append("missing_net_pnl")
    if costs.get("total_cost") is None:
        critical_missing.append("missing_total_cost")

    if not dataset_source:
        traceability_missing.append("missing_dataset_source")
    if not commit_hash or commit_hash.lower() == "local":
        traceability_missing.append("missing_commit_hash")

    if feature_set.lower() in {"", "unknown"}:
        degraded_flags.append("unknown_feature_set")
    if validation_quality.lower() in {"", "unknown", "synthetic_or_bootstrap"}:
        degraded_flags.append("validation_quality_degraded")
    if cost_fidelity_level.lower() in {"", "unknown", "synthetic_seeded"}:
        degraded_flags.append("cost_fidelity_degraded")
    if bool(costs.get("components_present")) and not bool(costs.get("components_complete")):
        degraded_flags.append("partial_cost_components")
    if costs.get("total_cost") is not None and str(costs.get("total_cost_source") or "reported") != "reported":
        degraded_flags.append(f"reconstructed_total_cost:{costs.get('total_cost_source')}")
    if catalog_run is None:
        degraded_flags.append("episode_without_catalog")

    flags.extend(critical_missing)
    flags.extend(traceability_missing)
    flags.extend(degraded_flags)
    if critical_missing:
        status = "quarantine"
        learning_excluded = True
    elif traceability_missing or degraded_flags:
        status = "legacy"
        learning_excluded = False
    else:
        status = "trusted"
        learning_excluded = False
    return {
        "evidence_status": status,
        "evidence_flags": flags,
        "learning_excluded": learning_excluded,
        "validation_quality": validation_quality or "unknown",
        "cost_fidelity_level": cost_fidelity_level or "unknown",
        "feature_set": feature_set or "unknown",
        "costs": costs,
    }


def _trial_candidate_stage(run_row: dict[str, Any] | None, *, shortlisted: bool) -> str:
    if not isinstance(run_row, dict):
        return "episode_only"
    params = run_row.get("params_json") if isinstance(run_row.get("params_json"), dict) else {}
    flags = run_row.get("flags") if isinstance(run_row.get("flags"), dict) else {}
    artifacts = run_row.get("artifacts") if isinstance(run_row.get("artifacts"), dict) else {}
    strict_strategy_id = bool(params.get("strict_strategy_id") or artifacts.get("strict_strategy_id"))
    if strict_strategy_id:
        return "candidate_ready"
    if shortlisted:
        return "shortlisted"
    if bool(flags.get("PASO_GATES")) or bool(flags.get("GATES_ADV_PASS")):
        return "gates_pass"
    status = str(run_row.get("status") or "").strip().lower()
    if status in {"failed", "canceled", "archived"}:
        return status
    return "catalogued"


def _collect_research_trial_ledger_items() -> list[dict[str, Any]]:
    catalog_runs = store.backtest_catalog.list_runs()
    batches = store.backtest_catalog.list_batches()
    proposals = option_b_engine.list_proposals()
    shortlisted_run_ids: set[str] = set()
    for batch in batches:
        shortlist = batch.get("best_runs_cache") if isinstance(batch.get("best_runs_cache"), list) else []
        for item in shortlist:
            if not isinstance(item, dict):
                continue
            run_id = _first_text(item.get("run_id"), item.get("id"))
            if run_id:
                shortlisted_run_ids.add(run_id)

    proposal_index: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for proposal in proposals:
        if not isinstance(proposal, dict):
            continue
        key = _proposal_signature_key(
            strategy_id=str(proposal.get("proposed_strategy_id") or ""),
            asset=str(proposal.get("asset") or ""),
            timeframe=str(proposal.get("timeframe") or ""),
        )
        if key[0]:
            proposal_index.setdefault(key, []).append(proposal)

    episodes = store.registry.list_experience_episodes(sources=["backtest"])
    episode_by_run_id: dict[str, dict[str, Any]] = {}
    for episode in episodes:
        run_id = str(episode.get("run_id") or "").strip()
        if not run_id:
            continue
        existing = episode_by_run_id.get(run_id)
        if existing is None or str(episode.get("created_at") or "") > str(existing.get("created_at") or ""):
            episode_by_run_id[run_id] = episode

    matched_episode_ids: set[str] = set()
    rows: list[dict[str, Any]] = []
    for catalog_run in catalog_runs:
        if not isinstance(catalog_run, dict):
            continue
        run_id = str(catalog_run.get("run_id") or "").strip()
        legacy_json_id = str(catalog_run.get("legacy_json_id") or "").strip()
        episode = episode_by_run_id.get(run_id) or (episode_by_run_id.get(legacy_json_id) if legacy_json_id else None)
        if isinstance(episode, dict):
            episode_id = str(episode.get("id") or "").strip()
            if episode_id:
                matched_episode_ids.add(episode_id)
        summary = episode.get("summary") if isinstance((episode or {}).get("summary"), dict) else {}
        classification = _classify_trial_evidence(episode=episode, catalog_run=catalog_run)
        symbols = catalog_run.get("symbols") if isinstance(catalog_run.get("symbols"), list) else []
        timeframes = catalog_run.get("timeframes") if isinstance(catalog_run.get("timeframes"), list) else []
        asset = _first_text((episode or {}).get("asset"), symbols[0] if symbols else "")
        timeframe = _first_text((episode or {}).get("timeframe"), timeframes[0] if timeframes else "")
        strategy_id = _first_text((episode or {}).get("strategy_id"), catalog_run.get("strategy_id"))
        linked_proposals = proposal_index.get(
            _proposal_signature_key(strategy_id=strategy_id, asset=asset, timeframe=timeframe),
            [],
        )
        proposal_statuses = sorted({_proposal_status_normalized(row.get("status")) for row in linked_proposals if isinstance(row, dict)})
        candidate_stage = _trial_candidate_stage(catalog_run, shortlisted=(run_id in shortlisted_run_ids))
        flags = catalog_run.get("flags") if isinstance(catalog_run.get("flags"), dict) else {}
        params = catalog_run.get("params_json") if isinstance(catalog_run.get("params_json"), dict) else {}
        kpis = catalog_run.get("kpis") if isinstance(catalog_run.get("kpis"), dict) else {}
        rows.append(
            {
                "run_id": run_id,
                "legacy_json_id": legacy_json_id or None,
                "batch_id": str(catalog_run.get("batch_id") or "").strip() or None,
                "run_type": str(catalog_run.get("run_type") or "single"),
                "run_status": str(catalog_run.get("status") or ""),
                "created_at": _first_text(catalog_run.get("created_at"), (episode or {}).get("created_at")),
                "started_at": _first_text(catalog_run.get("started_at"), (episode or {}).get("start_ts")),
                "finished_at": _first_text(catalog_run.get("finished_at"), (episode or {}).get("end_ts")),
                "strategy_id": strategy_id,
                "strategy_name": _first_text(catalog_run.get("strategy_name"), strategy_id),
                "asset": asset,
                "timeframe": timeframe,
                "dataset_source": _first_text((episode or {}).get("dataset_source"), summary.get("dataset_source"), catalog_run.get("dataset_source")),
                "dataset_hash": _first_text((episode or {}).get("dataset_hash"), catalog_run.get("dataset_hash")),
                "commit_hash": _first_text((episode or {}).get("commit_hash"), catalog_run.get("code_commit_hash")),
                "source": _first_text((episode or {}).get("source"), "backtest"),
                "evidence_status": classification.get("evidence_status"),
                "evidence_flags": classification.get("evidence_flags"),
                "learning_excluded": bool(classification.get("learning_excluded")),
                "validation_quality": classification.get("validation_quality"),
                "cost_fidelity_level": classification.get("cost_fidelity_level"),
                "feature_set": classification.get("feature_set"),
                "candidate_stage": candidate_stage,
                "candidate_flags": {
                    "shortlisted": run_id in shortlisted_run_ids,
                    "paso_gates": bool(flags.get("PASO_GATES")),
                    "strict_strategy_id": bool(params.get("strict_strategy_id")),
                },
                "proposal_count": len(linked_proposals),
                "proposal_statuses": proposal_statuses,
                "proposal_needs_validation": any(bool((row or {}).get("needs_validation")) for row in linked_proposals if isinstance(row, dict)),
                "metrics": {
                    "trade_count": int(
                        (summary.get("trade_count") if isinstance(summary, dict) else 0)
                        or kpis.get("trade_count")
                        or kpis.get("roundtrips")
                        or 0
                    ),
                    "sharpe": _first_number((summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}).get("sharpe"), kpis.get("sharpe")),
                    "winrate": _first_number((summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}).get("winrate"), kpis.get("winrate")),
                    "max_dd": _first_number((summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}).get("max_dd"), kpis.get("max_dd")),
                    "net_pnl": classification.get("costs", {}).get("net_pnl"),
                },
                "costs": classification.get("costs"),
                "catalog_present": True,
            }
        )

    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        episode_id = str(episode.get("id") or "").strip()
        if episode_id and episode_id in matched_episode_ids:
            continue
        summary = episode.get("summary") if isinstance(episode.get("summary"), dict) else {}
        classification = _classify_trial_evidence(episode=episode, catalog_run=None)
        strategy_id = str(episode.get("strategy_id") or "").strip()
        asset = str(episode.get("asset") or "").strip().upper()
        timeframe = str(episode.get("timeframe") or "").strip().lower()
        linked_proposals = proposal_index.get(
            _proposal_signature_key(strategy_id=strategy_id, asset=asset, timeframe=timeframe),
            [],
        )
        rows.append(
            {
                "run_id": str(episode.get("run_id") or episode_id),
                "legacy_json_id": None,
                "batch_id": None,
                "run_type": "episode_only",
                "run_status": "episode_only",
                "created_at": _first_text(episode.get("created_at"), episode.get("end_ts"), episode.get("start_ts")),
                "started_at": _first_text(episode.get("start_ts")),
                "finished_at": _first_text(episode.get("end_ts")),
                "strategy_id": strategy_id,
                "strategy_name": strategy_id,
                "asset": asset,
                "timeframe": timeframe,
                "dataset_source": _first_text(episode.get("dataset_source"), summary.get("dataset_source")),
                "dataset_hash": _first_text(episode.get("dataset_hash")),
                "commit_hash": _first_text(episode.get("commit_hash")),
                "source": _first_text(episode.get("source"), "backtest"),
                "evidence_status": classification.get("evidence_status"),
                "evidence_flags": classification.get("evidence_flags"),
                "learning_excluded": bool(classification.get("learning_excluded")),
                "validation_quality": classification.get("validation_quality"),
                "cost_fidelity_level": classification.get("cost_fidelity_level"),
                "feature_set": classification.get("feature_set"),
                "candidate_stage": "episode_only",
                "candidate_flags": {"shortlisted": False, "paso_gates": False, "strict_strategy_id": False},
                "proposal_count": len(linked_proposals),
                "proposal_statuses": sorted({_proposal_status_normalized(row.get("status")) for row in linked_proposals if isinstance(row, dict)}),
                "proposal_needs_validation": any(bool((row or {}).get("needs_validation")) for row in linked_proposals if isinstance(row, dict)),
                "metrics": {
                    "trade_count": int(summary.get("trade_count") or 0),
                    "sharpe": _first_number((summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}).get("sharpe")),
                    "winrate": _first_number((summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}).get("winrate")),
                    "max_dd": _first_number((summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}).get("max_dd")),
                    "net_pnl": classification.get("costs", {}).get("net_pnl"),
                },
                "costs": classification.get("costs"),
                "catalog_present": False,
            }
        )

    rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("run_id") or "")), reverse=True)
    return rows


def _research_funnel_payload() -> dict[str, Any]:
    items = _collect_research_trial_ledger_items()
    batches = store.backtest_catalog.list_batches()
    proposals = [row for row in option_b_engine.list_proposals() if isinstance(row, dict)]
    evidence_counts = {
        "trusted": sum(1 for row in items if str(row.get("evidence_status") or "") == "trusted"),
        "legacy": sum(1 for row in items if str(row.get("evidence_status") or "") == "legacy"),
        "quarantine": sum(1 for row in items if str(row.get("evidence_status") or "") == "quarantine"),
        "learning_eligible": sum(1 for row in items if not bool(row.get("learning_excluded"))),
        "learning_excluded": sum(1 for row in items if bool(row.get("learning_excluded"))),
    }
    counts = {
        "runs_total": sum(1 for row in items if bool(row.get("catalog_present"))),
        "episode_only": sum(1 for row in items if not bool(row.get("catalog_present"))),
        "quick_runs": sum(1 for row in items if str(row.get("run_type") or "") == "single"),
        "batch_child_runs": sum(1 for row in items if str(row.get("run_type") or "") == "batch_child"),
        "runs_completed": sum(1 for row in items if str(row.get("run_status") or "") in {"completed", "completed_warn"}),
        "runs_failed": sum(1 for row in items if str(row.get("run_status") or "") == "failed"),
        "batches_total": len(batches),
        "batches_active": sum(1 for row in batches if str((row or {}).get("status") or "").lower() in {"queued", "preparing", "running"}),
        "shortlisted": sum(1 for row in items if str(row.get("candidate_stage") or "") == "shortlisted"),
        "gates_pass": sum(1 for row in items if str(row.get("candidate_stage") or "") in {"gates_pass", "shortlisted", "candidate_ready"}),
        "candidate_ready": sum(1 for row in items if str(row.get("candidate_stage") or "") == "candidate_ready"),
        "proposals_total": len(proposals),
        "proposals_pending": sum(1 for row in proposals if _proposal_status_normalized(row.get("status")) == "pending"),
        "proposals_needs_validation": sum(1 for row in proposals if _proposal_status_normalized(row.get("status")) == "needs_validation"),
        "proposals_approved": sum(1 for row in proposals if _proposal_status_normalized(row.get("status")) == "approved"),
        "proposals_rejected": sum(1 for row in proposals if _proposal_status_normalized(row.get("status")) == "rejected"),
    }
    recent_candidates = [
        {
            "run_id": row.get("run_id"),
            "strategy_name": row.get("strategy_name"),
            "asset": row.get("asset"),
            "timeframe": row.get("timeframe"),
            "candidate_stage": row.get("candidate_stage"),
            "evidence_status": row.get("evidence_status"),
        }
        for row in items
        if str(row.get("candidate_stage") or "") in {"gates_pass", "shortlisted", "candidate_ready"}
    ][:8]
    return {
        "generated_at": utc_now_iso(),
        "counts": counts,
        "evidence": evidence_counts,
        "stages": [
            {
                "id": "runs_catalogued",
                "label": "Runs catalogados",
                "count": counts["runs_total"],
                "tone": "neutral",
                "description": "Quick backtests y child runs visibles en catalogo.",
            },
            {
                "id": "trusted_evidence",
                "label": "Evidence trusted",
                "count": evidence_counts["trusted"],
                "tone": "success",
                "description": "Metadata, costos y trazabilidad completas.",
            },
            {
                "id": "legacy_evidence",
                "label": "Evidence legacy",
                "count": evidence_counts["legacy"],
                "tone": "warn",
                "description": "Usable con degradacion o solo catalogo; no vender como evidence fuerte.",
            },
            {
                "id": "quarantine_evidence",
                "label": "Evidence quarantine",
                "count": evidence_counts["quarantine"],
                "tone": "danger",
                "description": "Falta metadata critica, costos o trazabilidad suficiente.",
            },
            {
                "id": "candidate_ready",
                "label": "Candidate ready",
                "count": counts["candidate_ready"],
                "tone": "info",
                "description": "Runs con gating/research suficientemente avanzados para seguimiento humano.",
            },
        ],
        "recent_candidates": recent_candidates,
        "compatibility": {
            "legacy_catalog_runs_visible": True,
            "learning_excluded_is_operational_flag": True,
            "status_is_derived_when_registry_has_no_explicit_evidence_status": True,
        },
    }


class RuntimeBridge:
    def __init__(self) -> None:
        self._lock = RLock()
        self._oms = OMS()
        self._kill_switch = KillSwitch()
        self._risk_engine: RiskEngine | None = None
        self._risk_limits_fingerprint: tuple[float, float, int, float, float, float] | None = None
        self._risk_policy_thresholds: dict[str, Any] = _load_runtime_risk_policy_thresholds()
        self._series: list[dict[str, Any]] = []
        self._stats: dict[str, int] = {
            "requotes": 0,
            "rate_limit_hits": 0,
            "api_errors": 0,
        }
        self._last_reconcile: dict[str, Any] = {
            "desync_count": 0,
            "missing_local": [],
            "missing_exchange": [],
            "qty_mismatches": [],
        }
        self._last_risk: dict[str, Any] = {
            "allow_new_positions": True,
            "reason": "",
            "safe_mode": False,
            "kill": False,
            "open_positions": 0,
            "total_exposure_pct": 0.0,
            "asset_exposure_pct": 0.0,
        }
        self._recent_remote_cancel_request_at: dict[str, float] = {}
        self._recent_remote_submit_request_at: dict[str, float] = {}
        self._remote_positions: list[dict[str, Any]] = []
        self._active_mode: str = "paper"
        self._last_filled_qty_by_order: dict[str, float] = {}
        self._runtime_costs: dict[str, float] = {
            "fills_count": 0.0,
            "fills_notional_usd": 0.0,
            "fees_total_usd": 0.0,
            "spread_total_usd": 0.0,
            "slippage_total_usd": 0.0,
            "funding_total_usd": 0.0,
            "total_cost_usd": 0.0,
        }

    @staticmethod
    def _symbol_mark_price(symbol: str) -> float:
        text = str(symbol or "").upper()
        if "BTC" in text:
            return 100000.0
        if "ETH" in text:
            return 3500.0
        if "SOL" in text:
            return 150.0
        return 100.0

    @staticmethod
    def _safe_positive(value: Any, default: float) -> float:
        parsed = _as_float(value, default)
        if parsed <= 0:
            return float(default)
        return parsed

    def _reset_runtime_costs(self) -> None:
        self._last_filled_qty_by_order = {}
        self._runtime_costs = {
            "fills_count": 0.0,
            "fills_notional_usd": 0.0,
            "fees_total_usd": 0.0,
            "spread_total_usd": 0.0,
            "slippage_total_usd": 0.0,
            "funding_total_usd": 0.0,
            "total_cost_usd": 0.0,
        }

    def _estimate_runtime_fill_costs(
        self,
        *,
        symbol: str,
        fill_qty: float,
        settings: dict[str, Any],
    ) -> dict[str, float]:
        qty = max(0.0, float(fill_qty))
        if qty <= 0.0:
            return {
                "notional_usd": 0.0,
                "fees_usd": 0.0,
                "spread_usd": 0.0,
                "slippage_usd": 0.0,
                "funding_usd": 0.0,
                "total_cost_usd": 0.0,
            }
        execution_cfg = settings.get("execution") if isinstance(settings.get("execution"), dict) else {}
        post_only = bool(execution_cfg.get("post_only", True))
        maker_fee_bps = max(0.0, RuntimeBridge._safe_positive(execution_cfg.get("maker_fee_bps"), 2.0))
        taker_fee_bps = max(0.0, RuntimeBridge._safe_positive(execution_cfg.get("taker_fee_bps"), 5.5))
        spread_bps = max(0.0, RuntimeBridge._safe_positive(execution_cfg.get("spread_proxy_bps"), 4.0))
        slippage_bps = max(0.0, RuntimeBridge._safe_positive(execution_cfg.get("slippage_base_bps"), 3.0))
        funding_bps = max(0.0, RuntimeBridge._safe_positive(execution_cfg.get("funding_proxy_bps"), 1.0))
        fee_bps = maker_fee_bps if post_only else taker_fee_bps
        mark_price = max(0.0001, RuntimeBridge._symbol_mark_price(symbol))
        notional_usd = qty * mark_price
        fees_usd = notional_usd * (fee_bps / 10000.0)
        spread_usd = notional_usd * ((spread_bps / 2.0) / 10000.0)
        slippage_usd = notional_usd * (slippage_bps / 10000.0)
        funding_usd = notional_usd * (funding_bps / 10000.0) * 0.1
        total_cost_usd = fees_usd + spread_usd + slippage_usd + funding_usd
        return {
            "notional_usd": float(notional_usd),
            "fees_usd": float(fees_usd),
            "spread_usd": float(spread_usd),
            "slippage_usd": float(slippage_usd),
            "funding_usd": float(funding_usd),
            "total_cost_usd": float(total_cost_usd),
        }

    def _capture_runtime_fill_costs(self, *, settings: dict[str, Any]) -> None:
        active_ids: set[str] = set()
        for order in self._oms.orders.values():
            order_id = str(order.order_id or "").strip()
            if not order_id:
                continue
            active_ids.add(order_id)
            filled_now = max(0.0, float(order.filled_qty))
            filled_prev = max(0.0, float(self._last_filled_qty_by_order.get(order_id, 0.0) or 0.0))
            fill_delta = max(0.0, filled_now - filled_prev)
            self._last_filled_qty_by_order[order_id] = filled_now
            if fill_delta <= 0.0:
                continue
            estimate = self._estimate_runtime_fill_costs(symbol=str(order.symbol or "BTCUSDT"), fill_qty=fill_delta, settings=settings)
            self._runtime_costs["fills_count"] = self._runtime_costs.get("fills_count", 0.0) + 1.0
            self._runtime_costs["fills_notional_usd"] = self._runtime_costs.get("fills_notional_usd", 0.0) + float(
                estimate.get("notional_usd", 0.0)
            )
            self._runtime_costs["fees_total_usd"] = self._runtime_costs.get("fees_total_usd", 0.0) + float(
                estimate.get("fees_usd", 0.0)
            )
            self._runtime_costs["spread_total_usd"] = self._runtime_costs.get("spread_total_usd", 0.0) + float(
                estimate.get("spread_usd", 0.0)
            )
            self._runtime_costs["slippage_total_usd"] = self._runtime_costs.get("slippage_total_usd", 0.0) + float(
                estimate.get("slippage_usd", 0.0)
            )
            self._runtime_costs["funding_total_usd"] = self._runtime_costs.get("funding_total_usd", 0.0) + float(
                estimate.get("funding_usd", 0.0)
            )
            self._runtime_costs["total_cost_usd"] = self._runtime_costs.get("total_cost_usd", 0.0) + float(
                estimate.get("total_cost_usd", 0.0)
            )

        if active_ids:
            self._last_filled_qty_by_order = {
                oid: qty for oid, qty in self._last_filled_qty_by_order.items() if oid in active_ids
            }
        else:
            self._last_filled_qty_by_order = {}

    def _risk_limits_from_settings(self, settings: dict[str, Any]) -> RiskLimits:
        risk_defaults = settings.get("risk_defaults") if isinstance(settings.get("risk_defaults"), dict) else {}
        self._risk_policy_thresholds = _load_runtime_risk_policy_thresholds()
        soft_daily = _as_float(self._risk_policy_thresholds.get("soft_daily_loss_pct"), 0.0)
        hard_daily = _as_float(self._risk_policy_thresholds.get("hard_daily_loss_pct"), 0.0)
        hard_dd = _as_float(self._risk_policy_thresholds.get("hard_drawdown_pct"), 0.0)
        settings_daily = abs(_as_float(risk_defaults.get("max_daily_loss"), 5.0)) / 100.0
        settings_dd = abs(_as_float(risk_defaults.get("max_dd"), 22.0)) / 100.0
        daily_limit = settings_daily
        if soft_daily > 0:
            daily_limit = min(daily_limit, soft_daily)
        if hard_daily > 0:
            daily_limit = min(daily_limit, hard_daily)
        dd_limit = settings_dd
        if hard_dd > 0:
            dd_limit = min(dd_limit, hard_dd)
        safe_factor = RuntimeBridge._safe_positive((settings.get("safety") or {}).get("safe_factor"), 0.5)
        return RiskLimits(
            daily_loss_limit_pct=max(0.001, daily_limit),
            max_drawdown_pct=max(0.001, dd_limit),
            max_positions=max(1, _as_int(risk_defaults.get("max_positions"), 20)),
            max_total_exposure_pct=max(0.01, RuntimeBridge._safe_positive(risk_defaults.get("max_total_exposure_pct"), 1.0)),
            max_asset_exposure_pct=max(0.01, RuntimeBridge._safe_positive(risk_defaults.get("max_asset_exposure_pct"), 0.2)),
            risk_per_trade=max(0.0001, abs(_as_float(risk_defaults.get("risk_per_trade"), 0.5)) / 100.0),
            safe_factor=max(0.05, safe_factor),
        )

    def _ensure_risk_engine(self, settings: dict[str, Any], state: dict[str, Any]) -> RiskEngine:
        limits = self._risk_limits_from_settings(settings)
        fingerprint = (
            limits.daily_loss_limit_pct,
            limits.max_drawdown_pct,
            limits.max_positions,
            limits.max_total_exposure_pct,
            limits.max_asset_exposure_pct,
            limits.risk_per_trade,
        )
        starting_equity = max(1.0, RuntimeBridge._safe_positive(state.get("equity"), 10000.0))
        if self._risk_engine is None or self._risk_limits_fingerprint != fingerprint:
            self._risk_engine = RiskEngine(limits=limits, starting_equity=starting_equity)
            self._risk_limits_fingerprint = fingerprint
        return self._risk_engine

    def _set_state_value(self, state: dict[str, Any], key: str, value: Any) -> bool:
        if state.get(key) == value:
            return False
        state[key] = value
        return True

    def _runtime_exchange_ready(self, *, mode: str) -> dict[str, Any]:
        mode_n = str(mode or "paper").strip().lower()
        checked_at = utc_now_iso()
        if mode_n == "paper":
            return {
                "ok": True,
                "mode": mode_n,
                "connector_ok": True,
                "order_ok": True,
                "reason": "Paper connector operativo (simulador).",
                "source": "paper_simulator",
                "checked_at": checked_at,
            }
        diag = diagnose_exchange(mode_n, force_refresh=False)
        # Evita quedar pegado al cache negativo: si el check cacheado falla,
        # se fuerza un refresh inmediato para capturar recuperaciones de exchange.
        if not (bool(diag.get("connector_ok", False)) and bool(diag.get("order_ok", False))):
            diag = diagnose_exchange(mode_n, force_refresh=True)
        connector_ok = bool(diag.get("connector_ok", False))
        order_ok = bool(diag.get("order_ok", False))
        ok = connector_ok and order_ok
        reason = str(diag.get("order_reason") or diag.get("connector_reason") or diag.get("last_error") or "")
        return {
            "ok": ok,
            "mode": mode_n,
            "connector_ok": connector_ok,
            "order_ok": order_ok,
            "reason": reason if reason else ("Exchange runtime check ok" if ok else "Exchange runtime check failed"),
            "source": "exchange_diagnose_v1",
            "checked_at": checked_at,
        }

    def _cancel_open_orders(self) -> int:
        canceled = 0
        for order in list(self._oms.orders.values()):
            if order.status in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
                self._oms.cancel(order.order_id)
                canceled += 1
        return canceled

    @staticmethod
    def _exchange_side_to_runtime(value: Any) -> Side:
        side_text = str(value or "").strip().upper()
        if side_text == "SELL":
            return Side.SHORT
        return Side.LONG

    def _sync_oms_with_exchange_open_orders(self, exchange_orders: dict[str, dict[str, Any]]) -> None:
        # Runtime real: el estado local de OMS no debe inventar fills; refleja openOrders del exchange.
        for order_id, payload in exchange_orders.items():
            if not order_id:
                continue
            remote_qty = max(0.0, _as_float(payload.get("qty"), 0.0))
            remote_filled = max(0.0, _as_float(payload.get("filled_qty"), 0.0))
            if remote_qty <= 0.0:
                continue
            existing = self._oms.orders.get(order_id)
            if existing is None:
                symbol = str(payload.get("symbol") or "BTCUSDT")
                side = RuntimeBridge._exchange_side_to_runtime(payload.get("side"))
                self._oms.submit(Order(order_id=order_id, symbol=symbol, side=side, qty=remote_qty))
                existing = self._oms.orders.get(order_id)
            if existing is None:
                continue
            if abs(float(existing.qty) - remote_qty) > 1e-9:
                existing.qty = float(remote_qty)
                existing.updated_at = utc_now()
            delta = max(0.0, remote_filled - float(existing.filled_qty))
            if delta > 0.0:
                self._oms.apply_fill(order_id, delta)

    def _close_absent_local_open_orders(
        self,
        *,
        mode: str,
        exchange_orders: dict[str, dict[str, Any]],
    ) -> int:
        if not isinstance(exchange_orders, dict):
            return 0
        mode_n = str(mode or "").strip().lower()
        remote_ids = {str(oid) for oid in exchange_orders.keys() if str(oid)}
        if not remote_ids and not self._oms.open_orders():
            return 0
        now_dt = utc_now()
        grace_sec = int(RUNTIME_OPEN_ORDER_ABSENCE_GRACE_SEC)
        closed = 0
        for order in list(self._oms.open_orders()):
            order_id = str(order.order_id or "")
            if not order_id or order_id in remote_ids:
                continue
            age_sec = max(0.0, (now_dt - order.updated_at).total_seconds())
            if age_sec < float(grace_sec):
                continue
            status_payload: dict[str, Any] = {}
            status_ok = False
            if mode_n in {"testnet", "live"}:
                symbol = RuntimeBridge._sanitize_exchange_symbol(order.symbol)
                client_order_id = order_id
                exchange_order_id = ""
                if re.fullmatch(r"\d+", order_id):
                    client_order_id = ""
                    exchange_order_id = order_id
                status_payload, _status_source, status_ok, status_reason = self._fetch_exchange_order_status(
                    mode=mode_n,
                    symbol=symbol,
                    client_order_id=client_order_id,
                    exchange_order_id=exchange_order_id,
                )
                if status_ok and status_payload:
                    terminal = RuntimeBridge._apply_remote_order_status_to_local(order, status_payload)
                    if terminal:
                        closed += 1
                    else:
                        exchange_orders[order_id] = {
                            "filled_qty": float(_as_float(status_payload.get("filled_qty"), order.filled_qty)),
                            "qty": float(_as_float(status_payload.get("qty"), order.qty)),
                            "symbol": str(status_payload.get("symbol") or order.symbol),
                            "side": str(status_payload.get("side") or ("BUY" if order.side == Side.LONG else "SELL")),
                            "status": str(status_payload.get("status") or ""),
                            "client_order_id": str(status_payload.get("client_order_id") or client_order_id),
                            "exchange_order_id": str(status_payload.get("exchange_order_id") or exchange_order_id),
                        }
                    continue
                if not status_ok and str(status_reason or "").strip():
                    self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
                # Fail-closed: si no podemos confirmar estado remoto, no cerrar localmente.
                order.updated_at = now_dt
                continue
            self._oms.cancel(order_id)
            closed += 1
        return int(closed)

    @staticmethod
    def _parse_exchange_open_orders_payload(payload: list[Any]) -> dict[str, dict[str, Any]]:
        parsed_orders: dict[str, dict[str, Any]] = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            client_order_id = str(row.get("clientOrderId") or "").strip()
            exchange_order_id = str(row.get("orderId") or "").strip()
            oid = client_order_id or exchange_order_id
            if not oid:
                continue
            parsed_orders[oid] = {
                "filled_qty": float(_as_float(row.get("executedQty"), 0.0)),
                "qty": float(_as_float(row.get("origQty"), 0.0)),
                "symbol": str(row.get("symbol") or ""),
                "side": str(row.get("side") or ""),
                "status": str(row.get("status") or "NEW").strip().upper(),
                "client_order_id": client_order_id,
                "exchange_order_id": exchange_order_id,
            }
        return parsed_orders

    def _fetch_exchange_open_orders(self, *, mode: str) -> tuple[dict[str, dict[str, Any]], str, bool, str]:
        mode_n = str(mode or "").strip().lower()
        if mode_n not in {"testnet", "live"}:
            return {}, "exchange_api_skip_mode", False, f"Modo no soportado para exchange open orders: {mode_n or 'unknown'}"
        creds = load_exchange_credentials(mode_n)
        if not bool(creds.get("has_keys", False)):
            return {}, "exchange_api_missing_keys", False, "Credenciales de exchange faltantes para cancel/reconcile real."
        timeout_sec = _exchange_timeout_seconds()
        try:
            request_ok, result = _binance_signed_request(
                method="GET",
                base_url=str(creds.get("base_url") or ""),
                path="/api/v3/openOrders",
                api_key=str(creds.get("api_key") or ""),
                api_secret=str(creds.get("api_secret") or ""),
                params={},
                timeout_sec=timeout_sec,
            )
            payload = result.get("payload")
            if request_ok and isinstance(payload, list):
                return RuntimeBridge._parse_exchange_open_orders_payload(payload), "exchange_api", True, ""
            status_code = int(_as_int(result.get("status_code"), 0))
            category, detail = _classify_exchange_error(status_code, payload)
            reason = detail if detail else f"Exchange openOrders failed ({category})"
            return {}, "exchange_api_error", False, reason
        except Exception as exc:
            return {}, "exchange_api_exception", False, str(exc)

    @staticmethod
    def _parse_exchange_account_positions_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        balances = payload.get("balances") if isinstance(payload.get("balances"), list) else []
        positions: list[dict[str, Any]] = []
        for row in balances:
            if not isinstance(row, dict):
                continue
            asset = str(row.get("asset") or "").strip().upper()
            if not asset or asset in {"USDT", "USDC", "BUSD", "FDUSD"}:
                continue
            free_qty = max(0.0, _as_float(row.get("free"), 0.0))
            locked_qty = max(0.0, _as_float(row.get("locked"), 0.0))
            qty = free_qty + locked_qty
            if qty <= 0.0:
                continue
            symbol = f"{asset}USDT"
            mark_px = RuntimeBridge._symbol_mark_price(symbol)
            entry_px = mark_px * 0.998
            pnl_unrealized = (mark_px - entry_px) * qty
            positions.append(
                {
                    "symbol": symbol,
                    "side": "long",
                    "qty": round(qty, 8),
                    "entry_px": round(entry_px, 6),
                    "mark_px": round(mark_px, 6),
                    "pnl_unrealized": round(pnl_unrealized, 6),
                    "exposure_usd": round(abs(qty * mark_px), 6),
                    "strategy_id": DEFAULT_STRATEGY_ID,
                    "order_id": f"BAL-{asset}",
                }
            )
        positions.sort(key=lambda row: str(row.get("symbol") or ""))
        return positions

    def _fetch_exchange_account_positions(self, *, mode: str) -> tuple[list[dict[str, Any]], str, bool, str]:
        mode_n = str(mode or "").strip().lower()
        if mode_n not in {"testnet", "live"}:
            return [], "exchange_api_skip_mode", False, f"Modo no soportado para exchange account: {mode_n or 'unknown'}"
        creds = load_exchange_credentials(mode_n)
        if not bool(creds.get("has_keys", False)):
            return [], "exchange_api_missing_keys", False, "Credenciales de exchange faltantes para account snapshot."
        timeout_sec = _exchange_timeout_seconds()
        try:
            request_ok, result = _binance_signed_request(
                method="GET",
                base_url=str(creds.get("base_url") or ""),
                path="/api/v3/account",
                api_key=str(creds.get("api_key") or ""),
                api_secret=str(creds.get("api_secret") or ""),
                params={},
                timeout_sec=timeout_sec,
            )
            payload = result.get("payload")
            if request_ok and isinstance(payload, dict):
                return RuntimeBridge._parse_exchange_account_positions_payload(payload), "exchange_api", True, ""
            status_code = int(_as_int(result.get("status_code"), 0))
            category, detail = _classify_exchange_error(status_code, payload)
            reason = detail if detail else f"Exchange account failed ({category})"
            return [], "exchange_api_error", False, reason
        except Exception as exc:
            return [], "exchange_api_exception", False, str(exc)

    def _fetch_exchange_order_status(
        self,
        *,
        mode: str,
        symbol: str,
        client_order_id: str,
        exchange_order_id: str,
    ) -> tuple[dict[str, Any], str, bool, str]:
        mode_n = str(mode or "").strip().lower()
        if mode_n not in {"testnet", "live"}:
            return {}, "exchange_api_skip_mode", False, f"Modo no soportado para exchange order status: {mode_n or 'unknown'}"
        symbol_n = RuntimeBridge._sanitize_exchange_symbol(symbol)
        client_id_n = str(client_order_id or "").strip()
        exchange_id_n = str(exchange_order_id or "").strip()
        if not symbol_n:
            return {}, "exchange_api_missing_symbol", False, "symbol missing for exchange order status."
        if not client_id_n and not exchange_id_n:
            return {}, "exchange_api_missing_order_id", False, "order identifier missing for exchange order status."
        creds = load_exchange_credentials(mode_n)
        if not bool(creds.get("has_keys", False)):
            return {}, "exchange_api_missing_keys", False, "Credenciales de exchange faltantes para order status."

        timeout_sec = _exchange_timeout_seconds()
        params: dict[str, Any] = {"symbol": symbol_n}
        if client_id_n:
            params["origClientOrderId"] = client_id_n
        else:
            params["orderId"] = exchange_id_n
        try:
            request_ok, result = _binance_signed_request(
                method="GET",
                base_url=str(creds.get("base_url") or ""),
                path="/api/v3/order",
                api_key=str(creds.get("api_key") or ""),
                api_secret=str(creds.get("api_secret") or ""),
                params=params,
                timeout_sec=timeout_sec,
            )
            payload = result.get("payload")
            if request_ok and isinstance(payload, dict):
                return {
                    "status": str(payload.get("status") or "").strip().upper(),
                    "filled_qty": float(_as_float(payload.get("executedQty"), 0.0)),
                    "qty": float(_as_float(payload.get("origQty"), 0.0)),
                    "symbol": str(payload.get("symbol") or symbol_n).strip().upper(),
                    "side": str(payload.get("side") or "").strip().upper(),
                    "client_order_id": str(payload.get("clientOrderId") or client_id_n).strip(),
                    "exchange_order_id": str(payload.get("orderId") or exchange_id_n).strip(),
                }, "exchange_api", True, ""
            status_code = int(_as_int(result.get("status_code"), 0))
            category, detail = _classify_exchange_error(status_code, payload)
            reason = detail if detail else f"Exchange order status failed ({category})"
            return {}, "exchange_api_error", False, reason
        except Exception as exc:
            return {}, "exchange_api_exception", False, str(exc)

    @staticmethod
    def _apply_remote_order_status_to_local(order: Order, status_payload: dict[str, Any]) -> bool:
        remote_qty = max(0.0, _as_float(status_payload.get("qty"), 0.0))
        remote_filled = max(0.0, _as_float(status_payload.get("filled_qty"), 0.0))
        remote_status = str(status_payload.get("status") or "").strip().upper()
        if remote_qty > 0.0 and abs(float(order.qty) - remote_qty) > 1e-9:
            order.qty = float(remote_qty)
            order.updated_at = utc_now()
        if remote_filled > float(order.filled_qty):
            delta = max(0.0, remote_filled - float(order.filled_qty))
            if delta > 0.0:
                order.filled_qty = min(float(order.qty), float(order.filled_qty) + delta)
                order.status = OrderStatus.FILLED if order.filled_qty >= order.qty else OrderStatus.PARTIALLY_FILLED
                order.updated_at = utc_now()
        if remote_status == "FILLED":
            if float(order.filled_qty) < float(order.qty):
                remaining = max(0.0, float(order.qty) - float(order.filled_qty))
                if remaining > 0.0:
                    order.filled_qty = float(order.qty)
            order.status = OrderStatus.FILLED
            order.updated_at = utc_now()
            return True
        if remote_status in {"CANCELED", "EXPIRED", "EXPIRED_IN_MATCH"}:
            if float(order.filled_qty) >= float(order.qty) and float(order.qty) > 0.0:
                order.status = OrderStatus.FILLED
            else:
                order.status = OrderStatus.CANCELED
            order.updated_at = utc_now()
            return True
        if remote_status == "REJECTED":
            order.status = OrderStatus.REJECTED
            order.updated_at = utc_now()
            return True
        if remote_status == "PARTIALLY_FILLED":
            order.status = OrderStatus.PARTIALLY_FILLED
            order.updated_at = utc_now()
            return False
        if remote_status in {"NEW", "PENDING_CANCEL"}:
            if float(order.filled_qty) >= float(order.qty) and float(order.qty) > 0.0:
                order.status = OrderStatus.FILLED
                order.updated_at = utc_now()
                return True
            if float(order.filled_qty) > 0.0:
                order.status = OrderStatus.PARTIALLY_FILLED
            else:
                order.status = OrderStatus.SUBMITTED
            order.updated_at = utc_now()
            return False
        return False

    def _remember_remote_cancel_request(self, order_id: str) -> bool:
        text = str(order_id or "").strip()
        if not text:
            return False
        now_epoch = time.time()
        ttl_sec = float(RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_TTL_SEC)
        last = float(self._recent_remote_cancel_request_at.get(text, 0.0) or 0.0)
        if last > 0.0 and (now_epoch - last) < ttl_sec:
            return False
        self._recent_remote_cancel_request_at[text] = now_epoch
        if len(self._recent_remote_cancel_request_at) > int(RUNTIME_REMOTE_CANCEL_IDEMPOTENCY_MAX_IDS):
            floor = now_epoch - ttl_sec
            self._recent_remote_cancel_request_at = {
                key: value for key, value in self._recent_remote_cancel_request_at.items() if float(value) >= floor
            }
        return True

    @staticmethod
    def _sanitize_exchange_symbol(value: Any) -> str:
        return str(value or "").strip().upper().replace("/", "").replace("-", "")

    def _runtime_order_intent(self, *, mode: str) -> dict[str, Any]:
        mode_n = str(mode or "").strip().lower()
        principal = store.registry.get_principal(mode_n)
        strategy_id = str((principal or {}).get("name") or "").strip()
        if not strategy_id:
            return {
                "action": "flat",
                "reason": "no_primary_strategy",
                "strategy_id": "",
                "symbol": "",
                "side": "",
                "notional_usd": float(RUNTIME_REMOTE_ORDER_NOTIONAL_USD),
            }

        try:
            strategy = store.strategy_or_404(strategy_id)
        except Exception:
            return {
                "action": "flat",
                "reason": "primary_strategy_not_found",
                "strategy_id": strategy_id,
                "symbol": "",
                "side": "",
                "notional_usd": float(RUNTIME_REMOTE_ORDER_NOTIONAL_USD),
            }

        enabled_for_trading = bool(strategy.get("enabled_for_trading", strategy.get("enabled", False)))
        if not enabled_for_trading:
            return {
                "action": "flat",
                "reason": "primary_strategy_disabled",
                "strategy_id": strategy_id,
                "symbol": "",
                "side": "",
                "notional_usd": float(RUNTIME_REMOTE_ORDER_NOTIONAL_USD),
            }

        params = strategy.get("params") if isinstance(strategy.get("params"), dict) else {}
        tags = {str(tag or "").strip().lower() for tag in (strategy.get("tags") or []) if str(tag or "").strip()}

        symbol = RuntimeBridge._sanitize_exchange_symbol(
            params.get("runtime_symbol")
            or params.get("symbol")
            or params.get("pair")
            or params.get("market_symbol")
            or RUNTIME_REMOTE_ORDER_SYMBOL
            or get_env("BINANCE_TESTNET_TEST_SYMBOL", "BTCUSDT")
        )
        if not symbol:
            symbol = "BTCUSDT"

        action_override = str(params.get("runtime_action") or params.get("action") or "").strip().lower()
        side_override = str(params.get("runtime_side") or params.get("side") or "").strip().upper()

        action = "trade"
        side = "SELL" if str(RUNTIME_REMOTE_ORDER_SIDE or "BUY").strip().upper() == "SELL" else "BUY"
        reason = "strategy_default_side"

        if action_override in {"flat", "hold", "none", "pause"}:
            action = "flat"
            side = ""
            reason = "strategy_action_override_flat"
        elif side_override in {"BUY", "SELL"}:
            side = side_override
            reason = "strategy_side_override"
        else:
            defensive_tags = {"defensive", "liquidity", "cash", "safe_mode", "capital_preservation"}
            meanrev_tags = {"meanreversion", "mean_reversion", "reversion", "range"}
            trend_tags = {"trend", "breakout", "momentum", "orderflow", "trend_scanning"}
            if tags & defensive_tags:
                action = "flat"
                side = ""
                reason = "strategy_tags_defensive_flat"
            elif tags & meanrev_tags:
                side = "SELL"
                reason = "strategy_tags_meanreversion"
            elif tags & trend_tags:
                side = "BUY"
                reason = "strategy_tags_trend"

        notional = float(RUNTIME_REMOTE_ORDER_NOTIONAL_USD)
        for key in ("runtime_notional_usd", "order_notional_usd", "notional_usd"):
            if key in params:
                notional = RuntimeBridge._safe_positive(params.get(key), notional)
                break
        notional = max(5.0, float(notional))

        return {
            "action": action,
            "reason": reason,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "side": side,
            "notional_usd": notional,
        }

    def _remember_remote_submit_request(self, client_order_id: str) -> bool:
        text = str(client_order_id or "").strip()
        if not text:
            return False
        now_epoch = time.time()
        ttl_sec = float(RUNTIME_REMOTE_ORDER_IDEMPOTENCY_TTL_SEC)
        last = float(self._recent_remote_submit_request_at.get(text, 0.0) or 0.0)
        if last > 0.0 and (now_epoch - last) < ttl_sec:
            return False
        self._recent_remote_submit_request_at[text] = now_epoch
        if len(self._recent_remote_submit_request_at) > int(RUNTIME_REMOTE_ORDER_IDEMPOTENCY_MAX_IDS):
            floor = now_epoch - ttl_sec
            self._recent_remote_submit_request_at = {
                key: value for key, value in self._recent_remote_submit_request_at.items() if float(value) >= floor
            }
        return True

    def _build_remote_client_order_id(self, *, mode: str, symbol: str, side: str) -> str:
        mode_n = str(mode or "testnet").strip().lower()
        symbol_n = RuntimeBridge._sanitize_exchange_symbol(symbol)
        side_n = "buy" if str(side or "").strip().upper() != "SELL" else "sell"
        slot = int(time.time() // max(1, int(RUNTIME_REMOTE_ORDER_IDEMPOTENCY_TTL_SEC)))
        base = re.sub(r"[^a-z0-9_-]", "", f"rt-{mode_n}-{symbol_n.lower()}-{side_n}-{slot}")
        if len(base) <= 36:
            return base
        digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
        trimmed = base[:27].rstrip("-_")
        return f"{trimmed}-{digest}"[:36]

    def _submit_exchange_market_order(
        self,
        *,
        mode: str,
        symbol: str,
        side: str,
        qty: float,
        client_order_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        mode_n = str(mode or "").strip().lower()
        creds = load_exchange_credentials(mode_n)
        if not bool(creds.get("has_keys", False)):
            return False, {"error": "missing_keys"}
        side_n = "SELL" if str(side or "").strip().upper() == "SELL" else "BUY"
        symbol_n = RuntimeBridge._sanitize_exchange_symbol(symbol)
        qty_n = max(0.000001, float(qty))
        qty_text = f"{qty_n:.8f}".rstrip("0").rstrip(".")
        params: dict[str, Any] = {
            "symbol": symbol_n,
            "side": side_n,
            "type": "MARKET",
            "quantity": qty_text,
            "newClientOrderId": str(client_order_id),
        }
        timeout_sec = _exchange_timeout_seconds()
        request_ok, result = _binance_signed_request(
            method="POST",
            base_url=str(creds.get("base_url") or ""),
            path="/api/v3/order",
            api_key=str(creds.get("api_key") or ""),
            api_secret=str(creds.get("api_secret") or ""),
            params=params,
            timeout_sec=timeout_sec,
        )
        payload = result.get("payload")
        if request_ok and isinstance(payload, dict):
            return True, {
                "client_order_id": str(payload.get("clientOrderId") or client_order_id),
                "exchange_order_id": str(payload.get("orderId") or ""),
                "executed_qty": float(_as_float(payload.get("executedQty"), 0.0)),
                "orig_qty": float(_as_float(payload.get("origQty"), qty_n)),
                "symbol": symbol_n,
                "side": side_n,
                "raw": payload,
            }
        error_code = int(_as_int((payload.get("code") if isinstance(payload, dict) else 0), 0))
        error_text = str((payload.get("msg") if isinstance(payload, dict) else "") or "").strip().lower()
        # Binance duplicate submit (idempotent semantics).
        if error_code == -2010 and "duplicate order" in error_text:
            return True, {
                "client_order_id": str(client_order_id),
                "exchange_order_id": "",
                "executed_qty": 0.0,
                "orig_qty": float(qty_n),
                "symbol": symbol_n,
                "side": side_n,
                "idempotent_duplicate": True,
                "raw": payload if isinstance(payload, dict) else {},
            }
        status_code = int(_as_int(result.get("status_code"), 0))
        category, detail = _classify_exchange_error(status_code, payload)
        return False, {"error": detail, "error_type": category, "status_code": status_code, "raw": payload}

    def _maybe_submit_exchange_runtime_order(
        self,
        *,
        state: dict[str, Any],
        mode: str,
        account_positions: list[dict[str, Any]] | None = None,
        account_positions_ok: bool | None = None,
        account_positions_reason: str | None = None,
    ) -> dict[str, Any]:
        mode_n = str(mode or "").strip().lower()
        if mode_n not in {"testnet", "live"}:
            return {"submitted": False, "reason": "skip_mode"}
        if not bool(RUNTIME_REMOTE_ORDERS_ENABLED):
            return {"submitted": False, "reason": "remote_orders_disabled"}

        intent = self._runtime_order_intent(mode=mode_n)
        signal_strategy_id = str(intent.get("strategy_id") or "")
        signal_symbol = RuntimeBridge._sanitize_exchange_symbol(intent.get("symbol") or "")
        signal_side = str(intent.get("side") or "").strip().upper()
        signal_action = str(intent.get("action") or "flat").strip().lower()
        signal_reason = str(intent.get("reason") or "").strip()

        if mode_n == "live" and not bool(LIVE_TRADING_ENABLED):
            return {
                "submitted": False,
                "reason": "live_trading_disabled",
                "error": "LIVE_TRADING_ENABLED=false",
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }

        if signal_action != "trade":
            return {
                "submitted": False,
                "reason": "strategy_signal_flat",
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }

        if not bool((self._last_risk or {}).get("allow_new_positions", True)):
            return {
                "submitted": False,
                "reason": "risk_blocked",
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }
        if not bool(state.get("runtime_reconciliation_ok", False)):
            return {
                "submitted": False,
                "reason": "reconciliation_not_ok",
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }

        last_submit_at_raw = str(state.get("runtime_last_remote_submit_at") or "").strip()
        if last_submit_at_raw:
            try:
                if last_submit_at_raw.endswith("Z"):
                    last_submit_at_raw = last_submit_at_raw.replace("Z", "+00:00")
                last_submit_dt = datetime.fromisoformat(last_submit_at_raw)
                cooldown_sec = int(RUNTIME_REMOTE_ORDER_SUBMIT_COOLDOWN_SEC)
                age_sec = max(0.0, (utc_now() - last_submit_dt).total_seconds())
                if age_sec < float(cooldown_sec):
                    return {
                        "submitted": False,
                        "reason": "submit_cooldown_active",
                        "signal_action": signal_action,
                        "signal_reason": signal_reason,
                        "signal_strategy_id": signal_strategy_id,
                        "signal_symbol": signal_symbol,
                        "signal_side": signal_side,
                    }
            except Exception:
                pass

        account_rows: list[dict[str, Any]]
        account_ok: bool
        account_reason: str
        if account_positions is not None:
            account_rows = list(account_positions)
            account_ok = bool(account_positions_ok) if account_positions_ok is not None else True
            account_reason = str(account_positions_reason or "")
        else:
            account_rows, _account_source, account_ok, _account_reason = self._fetch_exchange_account_positions(mode=mode_n)
            account_reason = str(_account_reason or _account_source or "")
        if not account_ok:
            return {
                "submitted": False,
                "reason": "account_positions_fetch_failed",
                "error": account_reason or "account_positions_fetch_failed",
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }
        if account_ok and account_rows:
            self._remote_positions = account_rows
            return {
                "submitted": False,
                "reason": "account_positions_open",
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }

        exchange_orders, _source, source_ok, source_reason = self._fetch_exchange_open_orders(mode=mode_n)
        if not source_ok:
            self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
            return {
                "submitted": False,
                "reason": "open_orders_fetch_failed",
                "error": source_reason,
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }
        self._sync_oms_with_exchange_open_orders(exchange_orders)
        if exchange_orders:
            return {
                "submitted": False,
                "reason": "open_orders_present",
                "open_orders": len(exchange_orders),
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }
        local_open_orders = self._oms.open_orders()
        if local_open_orders:
            return {
                "submitted": False,
                "reason": "local_open_orders_present",
                "open_orders": len(local_open_orders),
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": signal_symbol,
                "signal_side": signal_side,
            }

        symbol = signal_symbol or RuntimeBridge._sanitize_exchange_symbol(
            RUNTIME_REMOTE_ORDER_SYMBOL or get_env("BINANCE_TESTNET_TEST_SYMBOL", "BTCUSDT")
        )
        if not symbol:
            symbol = "BTCUSDT"
        side = signal_side if signal_side in {"BUY", "SELL"} else (
            "SELL" if str(RUNTIME_REMOTE_ORDER_SIDE or "BUY").strip().upper() == "SELL" else "BUY"
        )
        mark_price = max(0.0001, RuntimeBridge._symbol_mark_price(symbol))
        notional = max(5.0, float(intent.get("notional_usd") or RUNTIME_REMOTE_ORDER_NOTIONAL_USD))
        qty = max(0.000001, round(notional / mark_price, 8))
        client_order_id = self._build_remote_client_order_id(mode=mode_n, symbol=symbol, side=side)
        if not self._remember_remote_submit_request(client_order_id):
            return {
                "submitted": False,
                "reason": "idempotent_skip",
                "client_order_id": client_order_id,
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": symbol,
                "signal_side": side,
            }

        submitted, payload = self._submit_exchange_market_order(
            mode=mode_n,
            symbol=symbol,
            side=side,
            qty=qty,
            client_order_id=client_order_id,
        )
        if not submitted:
            self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
            return {
                "submitted": False,
                "reason": "submit_failed",
                "error": str(payload.get("error") or ""),
                "client_order_id": client_order_id,
                "signal_action": signal_action,
                "signal_reason": signal_reason,
                "signal_strategy_id": signal_strategy_id,
                "signal_symbol": symbol,
                "signal_side": side,
            }

        order_id = str(payload.get("client_order_id") or client_order_id)
        existing = self._oms.orders.get(order_id)
        if existing is None:
            self._oms.submit(
                Order(
                    order_id=order_id,
                    symbol=symbol,
                    side=RuntimeBridge._exchange_side_to_runtime(side),
                    qty=max(0.000001, float(payload.get("orig_qty") or qty)),
                )
            )
            existing = self._oms.orders.get(order_id)
        if existing is not None:
            executed_qty = max(0.0, float(payload.get("executed_qty") or 0.0))
            delta = max(0.0, executed_qty - float(existing.filled_qty))
            if delta > 0.0:
                self._oms.apply_fill(order_id, delta)

        return {
            "submitted": True,
            "reason": "submitted",
            "client_order_id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": float(payload.get("orig_qty") or qty),
            "idempotent_duplicate": bool(payload.get("idempotent_duplicate", False)),
            "signal_action": signal_action,
            "signal_reason": signal_reason,
            "signal_strategy_id": signal_strategy_id,
            "signal_symbol": symbol,
            "signal_side": side,
        }

    def _maybe_submit_exchange_seed_order(
        self,
        *,
        state: dict[str, Any],
        mode: str,
        account_positions: list[dict[str, Any]] | None = None,
        account_positions_ok: bool | None = None,
        account_positions_reason: str | None = None,
    ) -> dict[str, Any]:
        # Backward-compatible wrapper: seed order logic now strategy-intent driven.
        return self._maybe_submit_exchange_runtime_order(
            state=state,
            mode=mode,
            account_positions=account_positions,
            account_positions_ok=account_positions_ok,
            account_positions_reason=account_positions_reason,
        )

    def _cancel_exchange_open_orders(self, *, mode: str) -> int:
        mode_n = str(mode or "").strip().lower()
        exchange_orders, source, source_ok, source_reason = self._fetch_exchange_open_orders(mode=mode_n)
        if not source_ok:
            if mode_n in {"testnet", "live"}:
                self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
            return 0
        creds = load_exchange_credentials(mode_n)
        timeout_sec = _exchange_timeout_seconds()
        canceled_remote = 0
        for oid, payload in exchange_orders.items():
            if not self._remember_remote_cancel_request(oid):
                continue
            symbol = str(payload.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            client_order_id = str(payload.get("client_order_id") or "").strip()
            exchange_order_id = str(payload.get("exchange_order_id") or "").strip()
            cancel_params: dict[str, Any] = {"symbol": symbol}
            if client_order_id:
                cancel_params["origClientOrderId"] = client_order_id
            elif exchange_order_id:
                cancel_params["orderId"] = exchange_order_id
            else:
                continue
            try:
                request_ok, result = _binance_signed_request(
                    method="DELETE",
                    base_url=str(creds.get("base_url") or ""),
                    path="/api/v3/order",
                    api_key=str(creds.get("api_key") or ""),
                    api_secret=str(creds.get("api_secret") or ""),
                    params=cancel_params,
                    timeout_sec=timeout_sec,
                )
                payload_raw = result.get("payload")
                if request_ok:
                    canceled_remote += 1
                    continue
                error_code = int(_as_int((payload_raw.get("code") if isinstance(payload_raw, dict) else 0), 0))
                error_text = str((payload_raw.get("msg") if isinstance(payload_raw, dict) else "") or "").strip().lower()
                # Idempotencia remota: si ya no existe, treat as already canceled.
                if error_code == -2011 or "unknown order" in error_text:
                    canceled_remote += 1
                    continue
                self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
            except Exception:
                self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
        self._last_reconcile["cancel_source"] = source
        self._last_reconcile["cancel_source_reason"] = source_reason
        return canceled_remote

    def _ensure_seed_order(self, state: dict[str, Any]) -> None:
        if str(state.get("mode") or "paper").strip().lower() != "paper":
            return
        if self._oms.open_orders():
            return
        qty = max(0.001, round(RuntimeBridge._safe_positive(state.get("equity"), 10000.0) / 1_000_000.0, 6))
        seed = Order(
            order_id=f"RT-{int(time.time() * 1000)}",
            symbol="BTC/USDT",
            side=Side.LONG,
            qty=qty,
        )
        self._oms.submit(seed)

    def _positions_snapshot(self, *, mode: str | None = None) -> list[dict[str, Any]]:
        mode_n = str(mode or self._active_mode or "paper").strip().lower()
        if mode_n in {"testnet", "live"} and self._remote_positions:
            return [dict(row) for row in self._remote_positions]
        rows: list[dict[str, Any]] = []
        for order in self._oms.open_orders():
            remaining = max(0.0, float(order.qty) - float(order.filled_qty))
            if remaining <= 0:
                continue
            mark_px = RuntimeBridge._symbol_mark_price(order.symbol)
            entry_px = mark_px * 0.998
            sign = 1.0 if order.side == Side.LONG else -1.0
            pnl_unrealized = (mark_px - entry_px) * remaining * sign
            rows.append(
                {
                    "symbol": order.symbol,
                    "side": "long" if order.side == Side.LONG else "short",
                    "qty": round(remaining, 8),
                    "entry_px": round(entry_px, 6),
                    "mark_px": round(mark_px, 6),
                    "pnl_unrealized": round(pnl_unrealized, 6),
                    "exposure_usd": round(abs(remaining * mark_px), 6),
                    "strategy_id": DEFAULT_STRATEGY_ID,
                    "order_id": order.order_id,
                }
            )
        return rows

    @staticmethod
    def _aggregate_exposure(positions: list[dict[str, Any]]) -> tuple[float, list[dict[str, Any]], float]:
        exposure_total = 0.0
        by_symbol: dict[str, float] = {}
        for row in positions:
            symbol = str(row.get("symbol") or "")
            exposure = abs(_as_float(row.get("exposure_usd"), 0.0))
            exposure_total += exposure
            if symbol:
                by_symbol[symbol] = by_symbol.get(symbol, 0.0) + exposure
        exposure_rows = [{"symbol": symbol, "exposure": round(value, 6)} for symbol, value in sorted(by_symbol.items())]
        max_symbol_exposure = max(by_symbol.values()) if by_symbol else 0.0
        return exposure_total, exposure_rows, max_symbol_exposure

    def _reconcile(self, *, mode: str) -> dict[str, Any]:
        mode_n = str(mode or "paper").strip().lower()
        source = "local_mirror"
        source_ok = True
        source_reason = ""
        exchange_orders: dict[str, dict[str, Any]] = {}
        if mode_n == "paper":
            exchange_orders = {
                str(order.order_id): {
                    "filled_qty": float(order.filled_qty),
                    "qty": float(order.qty),
                    "symbol": str(order.symbol),
                    "side": "BUY" if order.side == Side.LONG else "SELL",
                }
                for order in self._oms.orders.values()
            }
        if mode_n in {"testnet", "live"}:
            exchange_orders, source, source_ok, source_reason = self._fetch_exchange_open_orders(mode=mode_n)
            if source_ok:
                self._sync_oms_with_exchange_open_orders(exchange_orders)
                closed_absent = self._close_absent_local_open_orders(mode=mode_n, exchange_orders=exchange_orders)
                if closed_absent > 0:
                    self._stats["requotes"] = self._stats.get("requotes", 0) + int(closed_absent)
        local_orders = {
            str(order.order_id): {"filled_qty": float(order.filled_qty)}
            for order in self._oms.open_orders()
        }
        report = reconcile_orders(exchange_orders=exchange_orders, local_orders=local_orders)
        self._last_reconcile = {
            "desync_count": int(report.desync_count),
            "missing_local": list(report.missing_local),
            "missing_exchange": list(report.missing_exchange),
            "qty_mismatches": list(report.qty_mismatches),
            "source": source,
            "source_ok": bool(source_ok),
            "source_reason": source_reason,
        }
        return dict(self._last_reconcile)

    def _append_execution_point(self, *, settings: dict[str, Any], mode: str) -> dict[str, Any]:
        execution_cfg = settings.get("execution") if isinstance(settings.get("execution"), dict) else {}
        spread_base = max(0.1, RuntimeBridge._safe_positive(execution_cfg.get("spread_proxy_bps"), 4.0))
        slip_base = max(0.1, RuntimeBridge._safe_positive(execution_cfg.get("slippage_base_bps"), 3.0))
        post_only = bool(execution_cfg.get("post_only", True))
        mode_n = str(mode or "paper").strip().lower()

        open_orders = len(self._oms.open_orders())
        filled = sum(1 for row in self._oms.orders.values() if row.status == OrderStatus.FILLED)
        partial = sum(1 for row in self._oms.orders.values() if row.status == OrderStatus.PARTIALLY_FILLED)
        total_orders = len(self._oms.orders)
        if total_orders <= 0:
            fill_ratio = 0.0 if mode_n in {"testnet", "live"} else 0.92
        else:
            fill_ratio = min(1.0, max(0.0, (filled + partial * 0.5) / total_orders))
        if total_orders <= 0 and mode_n in {"testnet", "live"}:
            maker_ratio = 0.0
        else:
            maker_ratio = 0.92 if post_only else 0.48
        latency_ms = 80.0 + (open_orders * 9.0) + (0.0 if post_only else 25.0)

        point = {
            "ts": utc_now_iso(),
            "latency_ms_p95": round(latency_ms, 3),
            "spread_bps": round(spread_base + (open_orders * 0.35), 3),
            "slippage_bps": round(slip_base + (open_orders * 0.2), 3),
            "maker_ratio": round(maker_ratio, 4),
            "fill_ratio": round(fill_ratio, 4),
        }
        self._series.append(point)
        if len(self._series) > 240:
            self._series = self._series[-240:]
        return point

    def sync_runtime_state(self, state: dict[str, Any], settings: dict[str, Any], *, event: str | None = None) -> bool:
        with self._lock:
            changed = False
            runtime_engine = _runtime_engine_from_state(state)
            running = bool(state.get("running")) and not bool(state.get("killed"))
            active_mode = str(state.get("mode") or default_mode()).strip().lower()
            self._active_mode = active_mode
            now_iso = utc_now_iso()
            max_age_for_stale = max(10, _as_int((settings.get("execution") or {}).get("order_timeout_sec"), 45))

            if event == "kill":
                self._kill_switch.trigger("admin_killswitch")
                self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
                changed = self._set_state_value(state, "running", False) or changed
                changed = self._set_state_value(state, "killed", True) or changed
                changed = self._set_state_value(state, "safe_mode", True) or changed
                changed = self._set_state_value(state, "bot_status", "KILLED") or changed

            if event in {"stop", "kill", "mode_change"}:
                canceled_remote = 0
                if runtime_engine == RUNTIME_ENGINE_REAL and active_mode in {"testnet", "live"}:
                    canceled_remote = self._cancel_exchange_open_orders(mode=active_mode)
                canceled_now = self._cancel_open_orders()
                canceled_total = int(canceled_now) + int(canceled_remote)
                if canceled_total > 0:
                    self._stats["requotes"] = self._stats.get("requotes", 0) + canceled_total

            if runtime_engine != RUNTIME_ENGINE_REAL or not running:
                changed = self._set_state_value(state, "runtime_telemetry_source", RUNTIME_TELEMETRY_SOURCE_SYNTHETIC) or changed
                changed = self._set_state_value(state, "runtime_loop_alive", False) or changed
                changed = self._set_state_value(state, "runtime_executor_connected", False) or changed
                changed = self._set_state_value(state, "runtime_reconciliation_ok", False) or changed
                changed = self._set_state_value(state, "runtime_exchange_connector_ok", False) or changed
                changed = self._set_state_value(state, "runtime_exchange_order_ok", False) or changed
                changed = self._set_state_value(state, "runtime_exchange_reason", "") or changed
                changed = self._set_state_value(state, "runtime_account_positions_ok", False) or changed
                changed = self._set_state_value(state, "runtime_account_positions_verified_at", "") or changed
                changed = self._set_state_value(state, "runtime_account_positions_reason", "") or changed
                if event in {"stop", "kill", "mode_change"} or runtime_engine != RUNTIME_ENGINE_REAL:
                    changed = self._set_state_value(state, "runtime_exchange_mode", "") or changed
                    changed = self._set_state_value(state, "runtime_exchange_verified_at", "") or changed
                    changed = self._set_state_value(state, "runtime_last_remote_submit_at", "") or changed
                    changed = self._set_state_value(state, "runtime_last_remote_client_order_id", "") or changed
                    changed = self._set_state_value(state, "runtime_last_remote_submit_error", "") or changed
                    changed = self._set_state_value(state, "runtime_last_remote_submit_reason", "") or changed
                    changed = self._set_state_value(state, "runtime_last_signal_action", "") or changed
                    changed = self._set_state_value(state, "runtime_last_signal_reason", "") or changed
                    changed = self._set_state_value(state, "runtime_last_signal_strategy_id", "") or changed
                    changed = self._set_state_value(state, "runtime_last_signal_symbol", "") or changed
                    changed = self._set_state_value(state, "runtime_last_signal_side", "") or changed
                if event in {"stop", "kill", "mode_change"} or runtime_engine != RUNTIME_ENGINE_REAL:
                    changed = self._set_state_value(state, "runtime_heartbeat_at", "") or changed
                    changed = self._set_state_value(state, "runtime_last_reconcile_at", "") or changed
                if runtime_engine != RUNTIME_ENGINE_REAL:
                    self._reset_runtime_costs()
                self._remote_positions = []
                self._append_execution_point(settings=settings, mode=active_mode)
                return changed

            exchange_ready = self._runtime_exchange_ready(mode=active_mode)
            changed = self._set_state_value(state, "runtime_exchange_connector_ok", bool(exchange_ready.get("connector_ok", False))) or changed
            changed = self._set_state_value(state, "runtime_exchange_order_ok", bool(exchange_ready.get("order_ok", False))) or changed
            changed = self._set_state_value(state, "runtime_exchange_mode", str(exchange_ready.get("mode") or active_mode)) or changed
            changed = self._set_state_value(state, "runtime_exchange_verified_at", str(exchange_ready.get("checked_at") or now_iso)) or changed
            changed = self._set_state_value(state, "runtime_exchange_reason", str(exchange_ready.get("reason") or "")) or changed
            if not bool(exchange_ready.get("ok", False)):
                changed = self._set_state_value(state, "runtime_telemetry_source", RUNTIME_TELEMETRY_SOURCE_SYNTHETIC) or changed
                changed = self._set_state_value(state, "runtime_loop_alive", False) or changed
                changed = self._set_state_value(state, "runtime_executor_connected", False) or changed
                changed = self._set_state_value(state, "runtime_reconciliation_ok", False) or changed
                changed = self._set_state_value(state, "runtime_account_positions_ok", False) or changed
                changed = self._set_state_value(state, "runtime_account_positions_verified_at", "") or changed
                changed = self._set_state_value(state, "runtime_account_positions_reason", "") or changed
                changed = self._set_state_value(state, "runtime_last_remote_submit_error", "") or changed
                changed = self._set_state_value(state, "runtime_last_remote_submit_reason", "") or changed
                changed = self._set_state_value(state, "runtime_last_signal_action", "") or changed
                changed = self._set_state_value(state, "runtime_last_signal_reason", "") or changed
                changed = self._set_state_value(state, "runtime_last_signal_strategy_id", "") or changed
                changed = self._set_state_value(state, "runtime_last_signal_symbol", "") or changed
                changed = self._set_state_value(state, "runtime_last_signal_side", "") or changed
                changed = self._set_state_value(state, "runtime_heartbeat_at", "") or changed
                changed = self._set_state_value(state, "runtime_last_reconcile_at", "") or changed
                self._remote_positions = []
                self._append_execution_point(settings=settings, mode=active_mode)
                return changed

            if event in {"start", "mode_change"} and self._kill_switch.is_triggered():
                self._kill_switch.reset()
            if event in {"start", "mode_change"}:
                self._reset_runtime_costs()
            self._ensure_seed_order(state)
            stale_ids = self._oms.cancel_stale(max_age_seconds=max_age_for_stale)
            if stale_ids:
                self._stats["requotes"] = self._stats.get("requotes", 0) + len(stale_ids)
            open_orders = self._oms.open_orders()
            if active_mode == "paper" and open_orders:
                target = open_orders[0]
                remaining = max(0.0, float(target.qty) - float(target.filled_qty))
                if remaining > 0:
                    fill_step = min(remaining, max(0.0001, remaining * 0.25))
                    self._oms.apply_fill(target.order_id, fill_step)

            reconcile = self._reconcile(mode=active_mode)
            reconciliation_ok = int(reconcile.get("desync_count") or 0) == 0 and bool(reconcile.get("source_ok", False))
            changed = self._set_state_value(
                state,
                "runtime_telemetry_source",
                RUNTIME_TELEMETRY_SOURCE_REAL if reconciliation_ok else RUNTIME_TELEMETRY_SOURCE_SYNTHETIC,
            ) or changed
            changed = self._set_state_value(state, "runtime_loop_alive", True) or changed
            changed = self._set_state_value(state, "runtime_executor_connected", not self._kill_switch.is_triggered()) or changed
            changed = self._set_state_value(state, "runtime_reconciliation_ok", reconciliation_ok) or changed
            changed = self._set_state_value(state, "runtime_heartbeat_at", now_iso) or changed
            changed = self._set_state_value(state, "runtime_last_reconcile_at", now_iso) or changed
            if active_mode in {"testnet", "live"}:
                account_positions, account_source, account_ok, account_reason = self._fetch_exchange_account_positions(
                    mode=active_mode
                )
                if account_ok:
                    self._remote_positions = account_positions
                else:
                    self._remote_positions = []
                    self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
                changed = self._set_state_value(state, "runtime_account_positions_ok", bool(account_ok)) or changed
                changed = self._set_state_value(
                    state,
                    "runtime_account_positions_verified_at",
                    now_iso if bool(account_ok) else "",
                ) or changed
                changed = self._set_state_value(
                    state,
                    "runtime_account_positions_reason",
                    str(account_reason or account_source),
                ) or changed
            else:
                self._remote_positions = []
                changed = self._set_state_value(state, "runtime_account_positions_ok", False) or changed
                changed = self._set_state_value(state, "runtime_account_positions_verified_at", "") or changed
                changed = self._set_state_value(state, "runtime_account_positions_reason", "") or changed

            positions = self._positions_snapshot(mode=active_mode)
            self._capture_runtime_fill_costs(settings=settings)
            exposure_total, _exposure_rows, max_symbol_exposure = RuntimeBridge._aggregate_exposure(positions)
            equity = max(1.0, RuntimeBridge._safe_positive(state.get("equity"), 10000.0))
            total_exposure_pct = exposure_total / equity
            asset_exposure_pct = max_symbol_exposure / equity if equity > 0 else 0.0
            risk_engine = self._ensure_risk_engine(settings=settings, state=state)
            decision = risk_engine.can_trade(
                equity=equity,
                daily_pnl=_as_float(state.get("daily_pnl"), 0.0),
                open_positions=len(positions),
                total_exposure_pct=total_exposure_pct,
                asset_exposure_pct=asset_exposure_pct,
                safe_mode=bool(state.get("safe_mode", False)),
            )
            daily_loss_pct = risk_engine.daily_loss_pct(_as_float(state.get("daily_pnl"), 0.0), equity)
            drawdown_pct = risk_engine.drawdown_pct(equity)
            hard_daily_limit = _as_float(self._risk_policy_thresholds.get("hard_daily_loss_pct"), 0.0)
            hard_dd_limit = _as_float(self._risk_policy_thresholds.get("hard_drawdown_pct"), 0.0)
            policy_hard_trigger = ""
            if hard_daily_limit > 0 and daily_loss_pct >= hard_daily_limit:
                policy_hard_trigger = "policy_hard_daily_loss"
            elif hard_dd_limit > 0 and drawdown_pct >= hard_dd_limit:
                policy_hard_trigger = "policy_hard_drawdown"
            if policy_hard_trigger:
                decision = type(decision)(
                    allow_new_positions=False,
                    reason=policy_hard_trigger,
                    safe_mode=True,
                    kill=True,
                )
            self._last_risk = {
                "allow_new_positions": bool(decision.allow_new_positions),
                "reason": str(decision.reason or ""),
                "safe_mode": bool(decision.safe_mode),
                "kill": bool(decision.kill),
                "open_positions": len(positions),
                "total_exposure_pct": float(total_exposure_pct),
                "asset_exposure_pct": float(asset_exposure_pct),
                "daily_loss_pct": float(daily_loss_pct),
                "drawdown_pct": float(drawdown_pct),
                "policy_source": str(self._risk_policy_thresholds.get("source") or "settings"),
            }
            changed = self._set_state_value(state, "runtime_risk_allow_new_positions", bool(decision.allow_new_positions)) or changed
            changed = self._set_state_value(state, "runtime_risk_reason", str(decision.reason or "")) or changed
            if decision.kill:
                self._kill_switch.trigger(str(decision.reason or "risk_engine_kill"))
                changed = self._set_state_value(state, "running", False) or changed
                changed = self._set_state_value(state, "killed", True) or changed
                changed = self._set_state_value(state, "safe_mode", True) or changed
                changed = self._set_state_value(state, "bot_status", "KILLED") or changed
                changed = self._set_state_value(state, "runtime_loop_alive", False) or changed
                changed = self._set_state_value(state, "runtime_executor_connected", False) or changed
                changed = self._set_state_value(state, "runtime_telemetry_source", RUNTIME_TELEMETRY_SOURCE_SYNTHETIC) or changed
                self._stats["api_errors"] = self._stats.get("api_errors", 0) + 1
            if active_mode in {"testnet", "live"} and not bool(decision.kill) and bool(state.get("running")) and not bool(state.get("killed")):
                submit_result = self._maybe_submit_exchange_seed_order(
                    state=state,
                    mode=active_mode,
                    account_positions=account_positions,
                    account_positions_ok=account_ok,
                    account_positions_reason=account_reason,
                )
                submit_reason = str(submit_result.get("reason") or "")
                submit_error = str(submit_result.get("error") or "")
                submit_client_order_id = str(submit_result.get("client_order_id") or "")
                signal_action = str(submit_result.get("signal_action") or "")
                signal_reason = str(submit_result.get("signal_reason") or "")
                signal_strategy_id = str(submit_result.get("signal_strategy_id") or "")
                signal_symbol = str(submit_result.get("signal_symbol") or "")
                signal_side = str(submit_result.get("signal_side") or "")
                changed = self._set_state_value(state, "runtime_last_signal_action", signal_action) or changed
                changed = self._set_state_value(state, "runtime_last_signal_reason", signal_reason) or changed
                changed = self._set_state_value(state, "runtime_last_signal_strategy_id", signal_strategy_id) or changed
                changed = self._set_state_value(state, "runtime_last_signal_symbol", signal_symbol) or changed
                changed = self._set_state_value(state, "runtime_last_signal_side", signal_side) or changed
                changed = self._set_state_value(state, "runtime_last_remote_submit_reason", submit_reason) or changed
                if submit_client_order_id:
                    changed = self._set_state_value(
                        state,
                        "runtime_last_remote_client_order_id",
                        submit_client_order_id,
                    ) or changed
                if bool(submit_result.get("submitted", False)):
                    changed = self._set_state_value(state, "runtime_last_remote_submit_at", now_iso) or changed
                    changed = self._set_state_value(state, "runtime_last_remote_submit_error", "") or changed
                else:
                    changed = self._set_state_value(state, "runtime_last_remote_submit_error", submit_error) or changed
            self._append_execution_point(settings=settings, mode=active_mode)
            return changed

    def positions(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._positions_snapshot(mode=self._active_mode)

    def risk_snapshot(self, *, state: dict[str, Any], settings: dict[str, Any], gate_checklist: list[dict[str, Any]]) -> dict[str, Any]:
        with self._lock:
            mode = str(state.get("mode") or self._active_mode).strip().lower()
            positions = self._positions_snapshot(mode=mode)
            exposure_total, exposure_rows, max_symbol_exposure = RuntimeBridge._aggregate_exposure(positions)
            equity = max(1.0, RuntimeBridge._safe_positive(state.get("equity"), 10000.0))
            total_exposure_pct = exposure_total / equity
            asset_exposure_pct = max_symbol_exposure / equity if equity > 0 else 0.0
            risk_limits = self._risk_limits_from_settings(settings)
            decision = self._last_risk if isinstance(self._last_risk, dict) else {}
            breaker_flags: list[str] = []
            if bool(state.get("safe_mode", False)):
                breaker_flags.append("safe_mode")
            if self._kill_switch.is_triggered() or bool(state.get("killed", False)):
                breaker_flags.append("kill_switch")
            if not breaker_flags:
                breaker_flags.append("none")

            exec_snapshot = self.execution_metrics_snapshot()
            p95_slippage = _as_float(exec_snapshot.get("p95_slippage"), 0.0)
            p95_spread = _as_float(exec_snapshot.get("p95_spread"), 0.0)
            latency = _as_float(exec_snapshot.get("latency_ms_p95"), 0.0)
            robust_base = max(0.0, min(100.0, 100.0 - (p95_slippage * 2.0) - (p95_spread * 1.5) - (latency / 8.0)))
            daily_return = _as_float(state.get("daily_pnl"), 0.0) / equity
            forecast_band = {
                "return_p50_30d": round(daily_return * 10.0, 6),
                "return_p90_30d": round(daily_return * 16.0, 6),
                "dd_p90_30d": round(-abs(_as_float(state.get("max_dd"), -0.04)), 6),
            }

            return {
                "equity": float(equity),
                "dd": _as_float(state.get("max_dd"), -0.04),
                "daily_loss": _as_float(state.get("daily_loss"), -0.01),
                "exposure_total": round(exposure_total, 6),
                "exposure_total_pct": round(total_exposure_pct, 6),
                "exposure_by_symbol": exposure_rows,
                "open_positions": len(positions),
                "runtime_risk_decision": {
                    "allow_new_positions": bool(decision.get("allow_new_positions", True)),
                    "reason": str(decision.get("reason") or ""),
                    "kill": bool(decision.get("kill", False)),
                    "safe_mode": bool(decision.get("safe_mode", state.get("safe_mode", False))),
                    "asset_exposure_pct": round(asset_exposure_pct, 6),
                    "daily_loss_pct": round(_as_float(decision.get("daily_loss_pct"), 0.0), 6),
                    "drawdown_pct": round(_as_float(decision.get("drawdown_pct"), 0.0), 6),
                    "policy_source": str(decision.get("policy_source") or "settings"),
                },
                "circuit_breakers": breaker_flags,
                "limits": {
                    "daily_loss_limit": -abs(risk_limits.daily_loss_limit_pct),
                    "max_dd_limit": -abs(risk_limits.max_drawdown_pct),
                    "max_positions": int(risk_limits.max_positions),
                    "max_total_exposure": float(risk_limits.max_total_exposure_pct),
                    "max_asset_exposure": float(risk_limits.max_asset_exposure_pct),
                    "risk_per_trade": float(risk_limits.risk_per_trade),
                    "policy_hard_daily_loss_limit": -abs(_as_float(self._risk_policy_thresholds.get("hard_daily_loss_pct"), 0.0))
                    if _as_float(self._risk_policy_thresholds.get("hard_daily_loss_pct"), 0.0) > 0
                    else None,
                    "policy_hard_drawdown_limit": -abs(_as_float(self._risk_policy_thresholds.get("hard_drawdown_pct"), 0.0))
                    if _as_float(self._risk_policy_thresholds.get("hard_drawdown_pct"), 0.0) > 0
                    else None,
                },
                "stress_tests": [
                    {"scenario": "fees_x2", "robust_score": round(max(0.0, robust_base - 7.5), 3)},
                    {"scenario": "slippage_x2", "robust_score": round(max(0.0, robust_base - 10.0), 3)},
                    {"scenario": "spread_shock", "robust_score": round(max(0.0, robust_base - 12.5), 3)},
                ],
                "forecast_band": forecast_band,
                "gate_checklist": gate_checklist,
                "reconciliation": dict(self._last_reconcile),
            }

    def execution_metrics_snapshot(self) -> dict[str, Any]:
        with self._lock:
            points = list(self._series[-40:])
            if not points:
                points = [
                    {
                        "ts": utc_now_iso(),
                        "latency_ms_p95": 0.0,
                        "spread_bps": 0.0,
                        "slippage_bps": 0.0,
                        "maker_ratio": 0.0,
                        "fill_ratio": 0.0,
                    }
                ]
            spreads = [_as_float(row.get("spread_bps"), 0.0) for row in points]
            slips = [_as_float(row.get("slippage_bps"), 0.0) for row in points]
            lats = [_as_float(row.get("latency_ms_p95"), 0.0) for row in points]
            maker = [_as_float(row.get("maker_ratio"), 0.0) for row in points]
            fills = [_as_float(row.get("fill_ratio"), 0.0) for row in points]

            cancel_count = sum(
                1
                for row in self._oms.orders.values()
                if row.status in {OrderStatus.CANCELED, OrderStatus.STALE}
            )
            return {
                "maker_ratio": round(sum(maker) / len(maker), 6),
                "fill_ratio": round(sum(fills) / len(fills), 6),
                "requotes": int(self._stats.get("requotes", 0)),
                "cancels": int(cancel_count),
                "rate_limit_hits": int(self._stats.get("rate_limit_hits", 0)),
                "api_errors": int(self._stats.get("api_errors", 0)),
                "avg_spread": round(sum(spreads) / len(spreads), 6),
                "p95_spread": round(max(spreads), 6),
                "avg_slippage": round(sum(slips) / len(slips), 6),
                "p95_slippage": round(max(slips), 6),
                "latency_ms_p95": round(max(lats), 6),
                "requests_24h_estimate": max(1, len(points) * 6),
                "fills_count_runtime": int(round(self._runtime_costs.get("fills_count", 0.0))),
                "fills_notional_runtime_usd": round(_as_float(self._runtime_costs.get("fills_notional_usd"), 0.0), 6),
                "fees_total_runtime_usd": round(_as_float(self._runtime_costs.get("fees_total_usd"), 0.0), 6),
                "spread_total_runtime_usd": round(_as_float(self._runtime_costs.get("spread_total_usd"), 0.0), 6),
                "slippage_total_runtime_usd": round(_as_float(self._runtime_costs.get("slippage_total_usd"), 0.0), 6),
                "funding_total_runtime_usd": round(_as_float(self._runtime_costs.get("funding_total_usd"), 0.0), 6),
                "total_cost_runtime_usd": round(_as_float(self._runtime_costs.get("total_cost_usd"), 0.0), 6),
                "runtime_costs": {
                    "fills_count": int(round(self._runtime_costs.get("fills_count", 0.0))),
                    "fills_notional_usd": round(_as_float(self._runtime_costs.get("fills_notional_usd"), 0.0), 6),
                    "fees_total_usd": round(_as_float(self._runtime_costs.get("fees_total_usd"), 0.0), 6),
                    "spread_total_usd": round(_as_float(self._runtime_costs.get("spread_total_usd"), 0.0), 6),
                    "slippage_total_usd": round(_as_float(self._runtime_costs.get("slippage_total_usd"), 0.0), 6),
                    "funding_total_usd": round(_as_float(self._runtime_costs.get("funding_total_usd"), 0.0), 6),
                    "total_cost_usd": round(_as_float(self._runtime_costs.get("total_cost_usd"), 0.0), 6),
                },
                "series": points,
                "notes": [
                    "Metricas derivadas del runtime bridge (OMS/Reconciliation/Risk/KillSwitch).",
                    "Telemetry source: runtime_loop_v1 cuando engine=real y loop activo.",
                ],
            }


runtime_bridge = RuntimeBridge()


class ShadowRunCoordinator:
    def __init__(self, *, store: ConsoleStore) -> None:
        self.store = store
        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._last_closed_by_target: dict[str, str] = {}
        self._state = self._empty_state()

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "running": False,
            "thread_alive": False,
            "stop_requested": False,
            "stop_reason": "",
            "allow_live": False,
            "orders_sent": False,
            "marketdata_base_url": SHADOW_MARKETDATA_BASE_URL,
            "timeframe": SHADOW_DEFAULT_TIMEFRAME,
            "lookback_bars": int(SHADOW_DEFAULT_LOOKBACK_BARS),
            "poll_sec": int(SHADOW_DEFAULT_POLL_SEC),
            "symbol_requested": None,
            "active_bot_ids": [],
            "active_strategy_ids": [],
            "targets_count": 0,
            "warnings": [],
            "last_started_at": None,
            "last_cycle_at": None,
            "last_success_at": None,
            "last_error": "",
            "last_run_ids": [],
            "cycles_total": 0,
            "runs_created": 0,
            "episodes_written": 0,
            "skipped_duplicate_cycles": 0,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            payload = dict(self._state)
            payload["active_bot_ids"] = list(self._state.get("active_bot_ids") or [])
            payload["active_strategy_ids"] = list(self._state.get("active_strategy_ids") or [])
            payload["warnings"] = list(self._state.get("warnings") or [])
            payload["last_run_ids"] = list(self._state.get("last_run_ids") or [])
            thread_alive = bool(self._thread and self._thread.is_alive())
            payload["thread_alive"] = thread_alive
            payload["running"] = bool(self._state.get("running", False)) and thread_alive
            return payload

    def start(
        self,
        *,
        bot_id: str | None,
        timeframe: str,
        lookback_bars: int,
        poll_sec: int,
        symbol: str | None,
    ) -> dict[str, Any]:
        timeframe_n = str(timeframe or SHADOW_DEFAULT_TIMEFRAME).strip().lower() or SHADOW_DEFAULT_TIMEFRAME
        if timeframe_n not in {"5m", "10m", "15m"}:
            raise ValueError("Shadow solo soporta timeframes 5m, 10m o 15m.")
        poll_sec_n = max(10, int(poll_sec or SHADOW_DEFAULT_POLL_SEC))
        lookback_n = max(60, int(lookback_bars or SHADOW_DEFAULT_LOOKBACK_BARS))
        symbol_n = str(symbol or "").replace("/", "").replace("-", "").strip().upper() or None
        targets, warnings = self._resolve_targets(
            bot_id=(str(bot_id).strip() or None) if bot_id is not None else None,
            symbol=symbol_n,
            timeframe=timeframe_n,
            lookback_bars=lookback_n,
        )
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("Ya hay un shadow-run en ejecución.")
            self._stop_event = Event()
            self._state = self._empty_state()
            self._state.update(
                {
                    "running": True,
                    "thread_alive": True,
                    "stop_requested": False,
                    "stop_reason": "",
                    "marketdata_base_url": SHADOW_MARKETDATA_BASE_URL,
                    "timeframe": timeframe_n,
                    "lookback_bars": int(lookback_n),
                    "poll_sec": int(poll_sec_n),
                    "symbol_requested": symbol_n,
                    "active_bot_ids": sorted({str(target["bot_id"]) for target in targets}),
                    "active_strategy_ids": sorted({str(target["strategy_id"]) for target in targets}),
                    "targets_count": len(targets),
                    "warnings": warnings,
                    "last_started_at": utc_now_iso(),
                    "last_error": "",
                }
            )
            self._thread = Thread(
                target=self._run_loop,
                kwargs={
                    "targets": targets,
                    "timeframe": timeframe_n,
                    "lookback_bars": lookback_n,
                    "poll_sec": poll_sec_n,
                    "symbol": symbol_n,
                },
                name="rtlab-shadow-runner",
                daemon=True,
            )
            self._thread.start()
        self.store.add_log(
            event_type="shadow_runner_start",
            severity="info",
            module="learning",
            message="Shadow runner iniciado.",
            related_ids=[str(target["bot_id"]) for target in targets[:10]],
            payload={
                "bot_id": (str(bot_id).strip() or None) if bot_id is not None else None,
                "symbol": symbol_n,
                "timeframe": timeframe_n,
                "lookback_bars": int(lookback_n),
                "poll_sec": int(poll_sec_n),
                "targets_count": len(targets),
                "allow_live": False,
                "orders_sent": False,
            },
        )
        return self.status()

    def stop(self, *, reason: str | None = None) -> dict[str, Any]:
        stop_reason = str(reason or "manual_stop").strip() or "manual_stop"
        with self._lock:
            self._state["stop_requested"] = True
            self._state["stop_reason"] = stop_reason
            thread = self._thread
            self._stop_event.set()
        self.store.add_log(
            event_type="shadow_runner_stop",
            severity="info",
            module="learning",
            message="Shadow runner stop solicitado.",
            related_ids=[],
            payload={"reason": stop_reason, "allow_live": False, "orders_sent": False},
        )
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        return self.status()

    def _resolve_targets(
        self,
        *,
        bot_id: str | None,
        symbol: str | None,
        timeframe: str,
        lookback_bars: int,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        bots = self.store.load_bots()
        if bot_id:
            bots = [row for row in bots if str(row.get("id") or "") == bot_id]
            if not bots:
                raise ValueError("Bot no encontrado para shadow.")
        eligible_bots: list[dict[str, Any]] = []
        warnings: list[str] = []
        for row in bots:
            status = str(row.get("status") or "active").strip().lower()
            mode = str(row.get("mode") or "paper").strip().lower()
            if status != "active":
                continue
            if mode != "shadow":
                if bot_id and str(row.get("id") or "") == bot_id:
                    raise ValueError("Poné el bot en modo SHADOW para correr mock en vivo sin órdenes.")
                continue
            eligible_bots.append(row)
        if not eligible_bots:
            raise ValueError("No hay bots activos en modo SHADOW.")

        strategies = {str(row.get("id") or ""): row for row in self.store.list_strategies() if str(row.get("id") or "")}
        targets: list[dict[str, Any]] = []
        for bot in eligible_bots:
            pool_ids = [str(sid) for sid in (bot.get("pool_strategy_ids") or []) if str(sid) in strategies]
            allowed_ids: list[str] = []
            for strategy_id in pool_ids:
                strategy = strategies.get(strategy_id) or {}
                if str(strategy.get("status") or "active").strip().lower() == "archived":
                    continue
                if not bool(strategy.get("allow_learning", True)):
                    continue
                allowed_ids.append(strategy_id)
            if not allowed_ids:
                warnings.append(f"{bot.get('id')}: sin estrategias Pool=true para shadow.")
                continue
            resolved_symbol = symbol or next(
                (str(item).replace("/", "").replace("-", "").strip().upper() for item in (bot.get("universe") or []) if str(item).strip()),
                RUNTIME_REMOTE_ORDER_SYMBOL,
            )
            for strategy_id in allowed_ids:
                strategy = strategies.get(strategy_id) or {}
                params = strategy.get("params") if isinstance(strategy.get("params"), dict) else {}
                tags = {str(tag or "").strip().lower() for tag in (strategy.get("tags") or [])}
                use_orderflow = True
                if isinstance(params.get("use_orderflow_data"), bool):
                    use_orderflow = bool(params.get("use_orderflow_data"))
                elif "feature_set:orderflow_off" in tags or "orderflow_off" in tags:
                    use_orderflow = False
                targets.append(
                    {
                        "bot_id": str(bot.get("id") or ""),
                        "strategy_id": strategy_id,
                        "symbol": resolved_symbol,
                        "timeframe": timeframe,
                        "lookback_bars": int(lookback_bars),
                        "use_orderflow_data": bool(use_orderflow),
                    }
                )
        if not targets:
            raise ValueError("No hay estrategias elegibles (Pool=true) para correr shadow.")
        return targets, warnings

    def _run_loop(
        self,
        *,
        targets: list[dict[str, Any]],
        timeframe: str,
        lookback_bars: int,
        poll_sec: int,
        symbol: str | None,
    ) -> None:
        runner = ShadowRunner(marketdata_base_url=SHADOW_MARKETDATA_BASE_URL)
        while not self._stop_event.is_set():
            cycle_runs: list[str] = []
            cycle_errors: list[str] = []
            with self._lock:
                self._state["cycles_total"] = int(self._state.get("cycles_total") or 0) + 1
                self._state["last_cycle_at"] = utc_now_iso()
            for target in targets:
                if self._stop_event.is_set():
                    break
                try:
                    simulation = runner.simulate(
                        ShadowRunConfig(
                            strategy_id=str(target["strategy_id"]),
                            symbol=str(target["symbol"]),
                            timeframe=str(target["timeframe"]),
                            lookback_bars=int(target["lookback_bars"]),
                            use_orderflow_data=bool(target.get("use_orderflow_data", True)),
                        )
                    )
                    manifest = simulation.get("manifest") if isinstance(simulation.get("manifest"), dict) else {}
                    last_closed = str(manifest.get("end") or "").strip()
                    feature_set = "orderflow_on" if bool(target.get("use_orderflow_data", True)) else "orderflow_off"
                    target_key = "|".join(
                        [
                            str(target["bot_id"]),
                            str(target["strategy_id"]),
                            str(target["symbol"]).upper(),
                            str(target["timeframe"]).lower(),
                            feature_set,
                        ]
                    )
                    if last_closed:
                        with self._lock:
                            previous_closed = str(self._last_closed_by_target.get(target_key) or "")
                            if previous_closed == last_closed:
                                self._state["skipped_duplicate_cycles"] = int(self._state.get("skipped_duplicate_cycles") or 0) + 1
                                continue
                            self._last_closed_by_target[target_key] = last_closed
                    run = self.store.create_shadow_live_run(
                        bot_id=str(target["bot_id"]),
                        strategy_id=str(target["strategy_id"]),
                        symbol=str(target["symbol"]),
                        timeframe=str(target["timeframe"]),
                        lookback_bars=int(target["lookback_bars"]),
                        simulation=simulation,
                        use_orderflow_data=bool(target.get("use_orderflow_data", True)),
                        note="shadow_runner_closed_candle",
                    )
                    cycle_runs.append(str(run.get("id") or ""))
                except Exception as exc:
                    message = f"{target.get('bot_id')}:{target.get('strategy_id')} -> {exc}"
                    cycle_errors.append(message)
                    self.store.add_log(
                        event_type="shadow_runner_error",
                        severity="warn",
                        module="learning",
                        message="Shadow runner con error en simulación.",
                        related_ids=[str(target.get("bot_id") or ""), str(target.get("strategy_id") or "")],
                        payload={
                            "error": str(exc),
                            "symbol": str(target.get("symbol") or ""),
                            "timeframe": str(target.get("timeframe") or ""),
                            "allow_live": False,
                            "orders_sent": False,
                        },
                    )
            if cycle_runs:
                _invalidate_bots_overview_cache()
            with self._lock:
                if cycle_runs:
                    self._state["runs_created"] = int(self._state.get("runs_created") or 0) + len(cycle_runs)
                    self._state["episodes_written"] = int(self._state.get("episodes_written") or 0) + len(cycle_runs)
                    self._state["last_success_at"] = utc_now_iso()
                    self._state["last_run_ids"] = (cycle_runs + list(self._state.get("last_run_ids") or []))[:10]
                if cycle_errors:
                    self._state["last_error"] = " | ".join(cycle_errors[:3])
            if self._stop_event.wait(max(10, int(poll_sec))):
                break
        with self._lock:
            self._state["running"] = False
            self._state["thread_alive"] = False


shadow_coordinator = ShadowRunCoordinator(store=store)


def _invalidate_bots_overview_cache() -> None:
    with _BOTS_OVERVIEW_CACHE_LOCK:
        _BOTS_OVERVIEW_CACHE["entries"] = {}


def _get_bots_overview_payload_cached(
    *,
    recommendations: list[dict[str, Any]] | None = None,
    include_recent_logs: bool | None = None,
    recent_logs_per_bot: int | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    effective_recent_logs = bool(BOTS_OVERVIEW_INCLUDE_RECENT_LOGS if include_recent_logs is None else include_recent_logs)
    effective_recent_logs_per_bot = max(
        0,
        int(BOTS_OVERVIEW_RECENT_LOGS_PER_BOT if recent_logs_per_bot is None else recent_logs_per_bot),
    )
    recent_logs_source = "default" if include_recent_logs is None else "explicit"
    cache_key = (
        f"recent_logs={1 if effective_recent_logs else 0};"
        f"logs_per_bot={effective_recent_logs_per_bot};"
        f"source={recent_logs_source}"
    )
    now_epoch = time.time()
    with _BOTS_OVERVIEW_CACHE_LOCK:
        entries = _BOTS_OVERVIEW_CACHE.get("entries")
        if not isinstance(entries, dict):
            entries = {}
            _BOTS_OVERVIEW_CACHE["entries"] = entries
        cached_entry = entries.get(cache_key)
        if isinstance(cached_entry, dict) and now_epoch < float(cached_entry.get("expires_at_epoch", 0.0)):
            cached_payload = cached_entry.get("payload")
            cached_perf = cached_entry.get("perf")
            if isinstance(cached_payload, dict):
                return cached_payload, "hit", (cached_perf if isinstance(cached_perf, dict) else {})
    rec_rows = recommendations if isinstance(recommendations, list) else learning_service.load_all_recommendations()
    overview_perf: dict[str, Any] = {}
    items = store.list_bot_instances(
        recommendations=rec_rows,
        include_recent_logs=include_recent_logs,
        recent_logs_per_bot=recent_logs_per_bot,
        overview_perf=overview_perf,
    )
    payload = {"items": items, "total": len(items)}
    cache_perf = {"overview": dict(overview_perf.get("overview") or {})}
    for key in ("logs_auto_disabled", "logs_auto_disable_threshold", "bots_count", "effective_recent_logs", "logs_per_bot_effective"):
        if key in overview_perf:
            cache_perf[key] = overview_perf.get(key)
    with _BOTS_OVERVIEW_CACHE_LOCK:
        entries = _BOTS_OVERVIEW_CACHE.get("entries")
        if not isinstance(entries, dict):
            entries = {}
            _BOTS_OVERVIEW_CACHE["entries"] = entries
        entries[cache_key] = {
            "expires_at_epoch": now_epoch + float(BOTS_OVERVIEW_CACHE_TTL_SEC),
            "payload": payload,
            "perf": cache_perf,
        }
    return payload, "miss", cache_perf


def _should_log_bots_overview_slow(now_epoch: float) -> bool:
    global _BOTS_OVERVIEW_LAST_SLOW_LOG_EPOCH
    with _BOTS_OVERVIEW_CACHE_LOCK:
        if (now_epoch - float(_BOTS_OVERVIEW_LAST_SLOW_LOG_EPOCH)) < float(BOTS_OVERVIEW_SLOW_LOG_THROTTLE_SEC):
            return False
        _BOTS_OVERVIEW_LAST_SLOW_LOG_EPOCH = now_epoch
        return True


def _learning_reference_run() -> dict[str, Any] | None:
    for run in store.load_runs():
        if run.get("market") and run.get("symbol") and run.get("timeframe"):
            return run
    runs = store.load_runs()
    return runs[0] if runs else None


def _learning_eval_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    ref = _learning_reference_run()
    market = str((ref or {}).get("market") or "crypto")
    symbol = str((ref or {}).get("symbol") or "BTCUSDT")
    timeframe = str((ref or {}).get("timeframe") or "5m")
    period = (ref or {}).get("period") or {}
    start = str(period.get("start") or "2024-01-01")
    end = str(period.get("end") or "2024-12-31")
    ref_costs = (ref or {}).get("costs_model") or {}
    costs = {
        "fees_bps": float(ref_costs.get("fees_bps", 5.5)),
        "spread_bps": float(ref_costs.get("spread_bps", 4.0)),
        "slippage_bps": float(ref_costs.get("slippage_bps", 3.0)),
        "funding_bps": float(ref_costs.get("funding_bps", 1.0)),
        "rollover_bps": float(ref_costs.get("rollover_bps", 0.0)),
    }

    try:
        loader = DataLoader(USER_DATA_DIR)
        loaded = loader.load_resampled(market, symbol, timeframe, start, end)
    except Exception as exc:
        raise ValueError(
            f"Learning run-now fail-closed: no se pudo cargar dataset real para {market}/{symbol}/{timeframe} "
            f"({start}..{end}). Descargá o registrá el dataset y reintentá. cause={exc}"
        ) from exc

    loaded_source = str(getattr(loaded, "source", "") or "").strip().lower()
    if loaded_source in {"", "none", "synthetic", "synthetic_seeded", "synthetic_fallback"}:
        raise ValueError(
            f"Learning run-now fail-closed: dataset_source invalido para evaluacion ({loaded_source or 'none'}). "
            "Se requieren datos reales."
        )

    learning_cfg = (learning_service.ensure_settings_shape(store.load_settings()).get("learning") or {})
    validation_cfg = learning_cfg.get("validation") if isinstance(learning_cfg.get("validation"), dict) else {}
    configured_mode = str(validation_cfg.get("validation_mode") or "").strip().lower()
    if configured_mode in {"walk-forward", "purged-cv", "cpcv"}:
        validation_mode = configured_mode
    else:
        validation_mode = "walk-forward" if bool(validation_cfg.get("walk_forward", True)) else "purged-cv"

    def _optional_int_from_validation(name: str, min_value: int | None = None) -> int | None:
        raw = validation_cfg.get(name)
        if raw is None or raw == "":
            return None
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            return None
        if min_value is not None and parsed < int(min_value):
            return None
        return parsed

    cpcv_n_splits = _optional_int_from_validation("cpcv_n_splits", min_value=4)
    cpcv_k_test_groups = _optional_int_from_validation("cpcv_k_test_groups", min_value=1)
    cpcv_max_paths = _optional_int_from_validation("cpcv_max_paths", min_value=1)

    engine = BacktestEngine()
    result = engine.run(
        BacktestRequest(
            market=loaded.market,
            symbol=loaded.symbol,
            timeframe=loaded.timeframe,
            start=start,
            end=end,
            strategy_id=str(candidate.get("base_strategy_id") or DEFAULT_STRATEGY_ID),
            validation_mode=validation_mode,
            cpcv_n_splits=cpcv_n_splits,
            cpcv_k_test_groups=cpcv_k_test_groups,
            cpcv_max_paths=cpcv_max_paths,
            costs=BacktestCosts(
                fees_bps=costs["fees_bps"],
                spread_bps=costs["spread_bps"],
                slippage_bps=costs["slippage_bps"],
                funding_bps=costs["funding_bps"],
                rollover_bps=costs["rollover_bps"],
            ),
        ),
        MarketDataset(
            market=loaded.market,
            symbol=loaded.symbol,
            timeframe=loaded.timeframe,
            source=loaded.source,
            dataset_hash=loaded.dataset_hash,
            df=loaded.df,
            manifest=loaded.manifest,
        ),
    )
    result["costs_model"] = costs
    return result


def _mass_backtest_eval_fold(variant: dict[str, Any], fold: Any, costs: dict[str, Any], base_cfg: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(variant.get("strategy_id") or DEFAULT_STRATEGY_ID)
    market = str(base_cfg.get("market") or "crypto")
    symbol = str(base_cfg.get("symbol") or "BTCUSDT")
    timeframe = str(base_cfg.get("timeframe") or "5m")
    data_source = str(base_cfg.get("dataset_source") or "auto").lower()
    execution_mode = str(base_cfg.get("execution_mode") or "research").strip().lower()
    validation_mode = str(base_cfg.get("validation_mode") or "walk-forward")
    bot_id_n = str(base_cfg.get("bot_id") or "").strip() or None
    strict_strategy_id = execution_mode != "demo"
    if data_source in {"synthetic", "synthetic_seeded", "synthetic_fallback"}:
        raise ValueError(
            "Backtests masivos solo permiten datos reales. Usa dataset_source='auto' o 'dataset' y descarga el dataset."
        )
    return store.create_event_backtest_run(
        strategy_id=strategy_id,
        bot_id=bot_id_n,
        market=market,
        symbol=symbol,
        timeframe=timeframe,
        start=str(fold.test_start),
        end=str(fold.test_end),
        fees_bps=float(costs.get("fees_bps", 5.5)),
        spread_bps=float(costs.get("spread_bps", 4.0)),
        slippage_bps=float(costs.get("slippage_bps", 3.0)),
        funding_bps=float(costs.get("funding_bps", 1.0)),
        rollover_bps=float(costs.get("rollover_bps", 0.0)),
        validation_mode=validation_mode,
        strict_strategy_id=bool(strict_strategy_id),
    )


def _find_run_or_404(run_id: str) -> dict[str, Any]:
    run = next((row for row in store.load_runs() if str(row.get("id")) == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return run


def _pick_baseline_run(candidate_run: dict[str, Any], explicit_run_id: str | None = None) -> dict[str, Any]:
    if explicit_run_id:
        baseline = _find_run_or_404(explicit_run_id)
        return baseline

    runs = store.load_runs()
    candidate_id = str(candidate_run.get("id") or "")
    candidate_strategy_id = str(candidate_run.get("strategy_id") or "")
    dataset_hash = str(candidate_run.get("dataset_hash") or "")
    period = candidate_run.get("period") or {}

    # Prefer same dataset hash + period and different strategy (strict compare).
    for row in runs:
        if str(row.get("id")) == candidate_id:
            continue
        if dataset_hash and str(row.get("dataset_hash") or "") != dataset_hash:
            continue
        if period and (row.get("period") or {}) != period:
            continue
        if str(row.get("strategy_id") or "") != candidate_strategy_id:
            return row

    # Fallback: latest run of current primary strategy for active mode (even if dataset differs; compare will fail explicitly).
    bot_mode = str(store.load_bot_state().get("mode") or "paper")
    principal = store.registry.get_principal(bot_mode)
    if principal:
        principal_name = str(principal.get("name") or "")
        for row in runs:
            if str(row.get("strategy_id") or "") == principal_name and str(row.get("id") or "") != candidate_id:
                return row

    # Last fallback: any other run.
    for row in runs:
        if str(row.get("id") or "") != candidate_id:
            return row
    raise HTTPException(status_code=400, detail="No baseline run available to compare against candidate")


def _runtime_engine_from_state(state: dict[str, Any] | None) -> str:
    runtime_engine = str((state or {}).get("runtime_engine") or "").strip().lower()
    if runtime_engine in {RUNTIME_ENGINE_REAL, RUNTIME_ENGINE_SIMULATED}:
        return runtime_engine
    return runtime_engine_default()


def _runtime_ts_age_sec(value: str | None, *, now: datetime | None = None) -> int | None:
    parsed = _parse_iso_datetime_utc(value)
    if not isinstance(parsed, datetime):
        return None
    now_dt = now or utc_now()
    return max(0, int((now_dt - parsed).total_seconds()))


def _runtime_contract_snapshot(state: dict[str, Any] | None, *, target_mode: str | None = None) -> dict[str, Any]:
    snapshot = state if isinstance(state, dict) else {}
    now_dt = utc_now()
    mode_n = str(target_mode or snapshot.get("mode") or default_mode()).strip().lower()
    if mode_n not in ALLOWED_MODES:
        mode_n = default_mode()
    runtime_engine = _runtime_engine_from_state(snapshot)
    telemetry_source = str(snapshot.get("runtime_telemetry_source") or RUNTIME_TELEMETRY_SOURCE_SYNTHETIC).strip().lower()
    loop_alive = bool(snapshot.get("runtime_loop_alive", False))
    executor_connected = bool(snapshot.get("runtime_executor_connected", False))
    reconciliation_ok = bool(snapshot.get("runtime_reconciliation_ok", False))
    exchange_connector_ok = bool(snapshot.get("runtime_exchange_connector_ok", False))
    exchange_order_ok = bool(snapshot.get("runtime_exchange_order_ok", False))
    exchange_mode = str(snapshot.get("runtime_exchange_mode") or "").strip().lower()
    exchange_age_sec = _runtime_ts_age_sec(str(snapshot.get("runtime_exchange_verified_at") or ""), now=now_dt)
    exchange_required = mode_n in {"testnet", "live"}
    heartbeat_age_sec = _runtime_ts_age_sec(str(snapshot.get("runtime_heartbeat_at") or ""), now=now_dt)
    reconcile_age_sec = _runtime_ts_age_sec(str(snapshot.get("runtime_last_reconcile_at") or ""), now=now_dt)

    checks = {
        "engine_real": runtime_engine == RUNTIME_ENGINE_REAL,
        "telemetry_real": telemetry_source == RUNTIME_TELEMETRY_SOURCE_REAL,
        "runtime_loop_alive": loop_alive,
        "executor_connected": executor_connected,
        "reconciliation_ok": reconciliation_ok,
        "heartbeat_fresh": heartbeat_age_sec is not None and heartbeat_age_sec <= int(RUNTIME_HEARTBEAT_MAX_AGE_SEC),
        "reconciliation_fresh": reconcile_age_sec is not None and reconcile_age_sec <= int(RUNTIME_RECONCILIATION_MAX_AGE_SEC),
        "exchange_connector_ok": (not exchange_required) or exchange_connector_ok,
        "exchange_order_ok": (not exchange_required) or exchange_order_ok,
        "exchange_check_fresh": (not exchange_required)
        or (exchange_age_sec is not None and exchange_age_sec <= int(RUNTIME_EXCHANGE_CHECK_MAX_AGE_SEC)),
        "exchange_mode_match": (not exchange_required) or exchange_mode == mode_n,
    }
    missing_checks = [key for key, ok in checks.items() if not bool(ok)]
    ready_for_live = len(missing_checks) == 0

    return {
        "contract_version": RUNTIME_CONTRACT_VERSION,
        "mode": mode_n,
        "runtime_engine": runtime_engine,
        "telemetry_source": telemetry_source,
        "runtime_loop_alive": loop_alive,
        "executor_connected": executor_connected,
        "reconciliation_ok": reconciliation_ok,
        "runtime_exchange_connector_ok": exchange_connector_ok,
        "runtime_exchange_order_ok": exchange_order_ok,
        "runtime_exchange_mode": exchange_mode,
        "runtime_exchange_verified_at": str(snapshot.get("runtime_exchange_verified_at") or ""),
        "runtime_exchange_reason": str(snapshot.get("runtime_exchange_reason") or ""),
        "exchange_check_age_sec": exchange_age_sec,
        "exchange_check_max_age_sec": int(RUNTIME_EXCHANGE_CHECK_MAX_AGE_SEC),
        "runtime_heartbeat_at": str(snapshot.get("runtime_heartbeat_at") or ""),
        "runtime_last_reconcile_at": str(snapshot.get("runtime_last_reconcile_at") or ""),
        "heartbeat_age_sec": heartbeat_age_sec,
        "heartbeat_max_age_sec": int(RUNTIME_HEARTBEAT_MAX_AGE_SEC),
        "reconciliation_age_sec": reconcile_age_sec,
        "reconciliation_max_age_sec": int(RUNTIME_RECONCILIATION_MAX_AGE_SEC),
        "checks": checks,
        "missing_checks": missing_checks,
        "ready_for_live": ready_for_live,
        "evaluated_at": now_dt.isoformat(),
    }


def _runtime_gate_status_for_mode(mode: str, state: dict[str, Any] | None) -> tuple[str, str, dict[str, Any]]:
    mode_n = str(mode or "paper").strip().lower()
    snapshot = _runtime_contract_snapshot(state, target_mode=mode_n)
    missing = snapshot.get("missing_checks") if isinstance(snapshot.get("missing_checks"), list) else []
    if mode_n == "live":
        if bool(snapshot.get("ready_for_live")):
            return "PASS", "Runtime contract v1 completo para LIVE.", snapshot
        reason = "Runtime contract v1 incompleto para LIVE."
        if missing:
            reason = f"{reason} Faltan checks: {', '.join(str(x) for x in missing)}"
        return "FAIL", reason, snapshot
    if bool(snapshot.get("ready_for_live")):
        return "PASS", "Runtime contract v1 completo (paper/testnet).", snapshot
    return "WARN", "Runtime contract v1 incompleto (valido en no-live).", snapshot


def _runtime_telemetry_guard(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    telemetry_source = str((snapshot or {}).get("telemetry_source") or RUNTIME_TELEMETRY_SOURCE_SYNTHETIC).strip().lower()
    telemetry_real = telemetry_source == RUNTIME_TELEMETRY_SOURCE_REAL
    return {
        "telemetry_source": telemetry_source,
        "telemetry_real": telemetry_real,
        "ok": telemetry_real,
        "fail_closed": not telemetry_real,
        "reason": "" if telemetry_real else "telemetry_source sintetico: metricas no aptas para promotion/live",
    }


def _sync_runtime_state(
    state: dict[str, Any] | None,
    *,
    settings: dict[str, Any] | None = None,
    event: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    runtime_state = dict(state or {})
    runtime_state["runtime_engine"] = _runtime_engine_from_state(runtime_state)
    runtime_state.setdefault("runtime_contract_version", RUNTIME_CONTRACT_VERSION)
    runtime_state.setdefault("runtime_telemetry_source", RUNTIME_TELEMETRY_SOURCE_SYNTHETIC)
    runtime_state.setdefault("runtime_loop_alive", False)
    runtime_state.setdefault("runtime_executor_connected", False)
    runtime_state.setdefault("runtime_reconciliation_ok", False)
    runtime_state.setdefault("runtime_exchange_connector_ok", False)
    runtime_state.setdefault("runtime_exchange_order_ok", False)
    runtime_state.setdefault("runtime_exchange_mode", "")
    runtime_state.setdefault("runtime_exchange_verified_at", "")
    runtime_state.setdefault("runtime_exchange_reason", "")
    runtime_state.setdefault("runtime_account_positions_ok", False)
    runtime_state.setdefault("runtime_account_positions_verified_at", "")
    runtime_state.setdefault("runtime_account_positions_reason", "")
    runtime_state.setdefault("runtime_last_remote_submit_at", "")
    runtime_state.setdefault("runtime_last_remote_client_order_id", "")
    runtime_state.setdefault("runtime_last_remote_submit_error", "")
    runtime_state.setdefault("runtime_last_signal_action", "")
    runtime_state.setdefault("runtime_last_signal_reason", "")
    runtime_state.setdefault("runtime_last_signal_strategy_id", "")
    runtime_state.setdefault("runtime_last_signal_symbol", "")
    runtime_state.setdefault("runtime_last_signal_side", "")
    runtime_state.setdefault("runtime_heartbeat_at", "")
    runtime_state.setdefault("runtime_last_reconcile_at", "")
    runtime_settings = settings if isinstance(settings, dict) else store.load_settings()
    changed = runtime_bridge.sync_runtime_state(runtime_state, runtime_settings, event=event)
    if persist and changed:
        store.save_bot_state(runtime_state)
    return runtime_state


def _is_trusted_internal_proxy(request: Request) -> bool:
    trusted, _reason = _internal_proxy_token_auth_result(request)
    return trusted


def _request_client_ip(request: Request) -> str:
    try:
        client = request.client
        host = str(client.host or "").strip() if client else ""
        return host or "unknown"
    except Exception:
        return "unknown"


def _should_log_internal_header_alert(cache_key: str) -> bool:
    now_epoch = time.time()
    with _INTERNAL_HEADER_ALERT_LOCK:
        last = float(_INTERNAL_HEADER_ALERT_CACHE.get(cache_key, 0.0) or 0.0)
        if now_epoch - last < float(SECURITY_INTERNAL_HEADER_ALERT_THROTTLE_SEC):
            return False
        _INTERNAL_HEADER_ALERT_CACHE[cache_key] = now_epoch
        return True


def _log_internal_header_spoof_attempt(
    request: Request,
    *,
    reason: str,
    internal_role: str,
    internal_user: str,
) -> None:
    client_ip = _request_client_ip(request)
    cache_key = f"{client_ip}:{reason}:{internal_role}:{internal_user[:64]}"
    if not _should_log_internal_header_alert(cache_key):
        return
    try:
        store.add_log(
            event_type="security_auth",
            severity="warn",
            module="auth",
            message="Intento de headers internos sin token valido",
            related_ids=[],
            payload={
                "reason": reason,
                "client_ip": client_ip,
                "path": request.url.path,
                "method": request.method,
                "internal_role": internal_role,
                "internal_user": internal_user[:120],
                "has_proxy_token_header": bool((request.headers.get("x-rtlab-proxy-token") or "").strip()),
            },
        )
    except Exception:
        # Auth path must fail closed regardless of logging failures.
        return


def current_user(request: Request) -> dict[str, str]:
    internal_role = (request.headers.get("x-rtlab-role") or "").lower().strip()
    internal_user = (request.headers.get("x-rtlab-user") or "").strip()
    if internal_role in ALLOWED_ROLES and internal_user:
        trusted, reason = _internal_proxy_token_auth_result(request)
        if trusted:
            return {"username": internal_user, "role": internal_role}
        _log_internal_header_spoof_attempt(
            request,
            reason=reason,
            internal_role=internal_role,
            internal_user=internal_user,
        )

    auth_header = request.headers.get("authorization") or ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        session = store.get_session(token)
        if session:
            return session
    raise HTTPException(status_code=401, detail="Unauthorized")


def require_admin(user: dict[str, str] = Depends(current_user)) -> dict[str, str]:
    if user["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required")
    return user


def gate_row(gate_id: str, name: str, status: Literal["PASS", "FAIL", "WARN"], reason: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"id": gate_id, "name": name, "status": status, "reason": reason, "details": details}


def evaluate_gates(
    mode: str | None = None,
    *,
    force_exchange_check: bool = False,
    runtime_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_mode = (mode or store.load_bot_state().get("mode") or "paper").lower()
    settings = store.load_settings()
    gates: list[dict[str, Any]] = []

    config_path = get_env("RTLAB_CONFIG_PATH", str(PROJECT_ROOT / "rtlab_config.yaml"))
    try:
        load_config(config_path)
        gates.append(gate_row("G1_CONFIG_VALID", "Config valid", "PASS", "Config loaded", {"path": config_path}))
    except Exception as exc:
        gates.append(gate_row("G1_CONFIG_VALID", "Config valid", "FAIL", "Config parse failed", {"error": str(exc), "path": config_path}))

    has_users = bool(admin_username() and admin_password() and viewer_username() and viewer_password())
    auth_secret_ok = bool(auth_secret() and len(auth_secret()) >= 32)
    default_credentials = _has_default_credentials()
    auth_ok = bool(has_users and auth_secret_ok and not default_credentials)
    gates.append(
        gate_row(
            "G2_AUTH_READY",
            "Auth ready",
            "PASS" if auth_ok else "FAIL",
            "Auth env listo y seguro"
            if auth_ok
            else "AUTH_SECRET/admin/viewer invalidos o credenciales por defecto detectadas",
            {
                "admin": bool(admin_username()),
                "viewer": bool(viewer_username()),
                "secret_len": len(auth_secret()),
                "auth_secret_ok": auth_secret_ok,
                "no_default_credentials": not default_credentials,
            },
        )
    )

    db_ok = True
    db_error = ""
    try:
        with sqlite3.connect(CONSOLE_DB_PATH) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:
        db_ok = False
        db_error = str(exc)
    gates.append(gate_row("G3_BACKEND_HEALTH", "Backend health", "PASS" if db_ok else "FAIL", "DB ok" if db_ok else "DB unavailable", {"db_error": db_error}))

    exchange_diag = diagnose_exchange(active_mode, force_refresh=force_exchange_check)
    if active_mode == "paper":
        g4_status = "PASS"
        g4_reason = "Paper connector uses simulator"
    else:
        g4_status = "PASS" if exchange_diag.get("connector_ok") else "FAIL"
        g4_reason = str(exchange_diag.get("connector_reason") or "Exchange connector not ready")
    gates.append(
        gate_row(
            "G4_EXCHANGE_CONNECTOR_READY",
            "Exchange connector",
            g4_status,
            g4_reason,
            {
                "mode": active_mode,
                "exchange": exchange_name(),
                "missing_env_vars": exchange_diag.get("missing", []),
                "expected_env_vars": exchange_diag.get("expected_env_vars", []),
                "key_source": exchange_diag.get("key_source", "none"),
                "base_url": exchange_diag.get("base_url"),
                "ws_url": exchange_diag.get("ws_url"),
                "last_error": exchange_diag.get("last_error", ""),
                "ws_error": exchange_diag.get("checks", {}).get("ws", {}).get("error", ""),
                "infrastructure_blocked": bool(exchange_diag.get("infrastructure_blocked")),
                "provider_restriction_checks": exchange_diag.get("provider_restriction_checks", []),
                "action_required": exchange_diag.get("action_required", []),
            },
        )
    )

    principal = store.registry.get_principal(active_mode)
    gates.append(
        gate_row(
            "G5_STRATEGY_PRINCIPAL_SET",
            "Principal strategy",
            "PASS" if principal else "FAIL",
            "Principal configured" if principal else f"No principal configured for {active_mode}",
            {"mode": active_mode, "strategy": principal["name"] if principal else None},
        )
    )

    risk = settings.get("risk_defaults", {})
    risk_ok = all(
        [
            isinstance(risk.get("max_daily_loss"), (int, float)),
            isinstance(risk.get("max_dd"), (int, float)),
            isinstance(risk.get("max_positions"), (int, float)),
            isinstance(risk.get("risk_per_trade"), (int, float)),
            isinstance(settings.get("execution", {}).get("slippage_max_bps"), (int, float)),
        ]
    )
    gates.append(
        gate_row(
            "G6_RISK_LIMITS_SET",
            "Risk limits",
            "PASS" if risk_ok else "FAIL",
            "Risk limits configured" if risk_ok else "Missing risk defaults",
            {"risk_defaults": risk, "slippage_max_bps": settings.get("execution", {}).get("slippage_max_bps")},
        )
    )

    if active_mode == "paper":
        g7_status = "PASS"
        g7_reason = "Paper order simulator ready"
    else:
        g7_status = "PASS" if exchange_diag.get("order_ok") else "FAIL"
        g7_reason = str(exchange_diag.get("order_reason") or ("Cannot place/cancel on live" if active_mode == "live" else "Cannot place/cancel on testnet"))
    gates.append(
        gate_row(
            "G7_ORDER_SIM_OR_PAPER_OK",
            "Order pipeline",
            g7_status,
            g7_reason,
            {
                "mode": active_mode,
                "missing_env_vars": exchange_diag.get("missing", []),
                "base_url": exchange_diag.get("base_url"),
                "ws_url": exchange_diag.get("ws_url"),
                "last_error": exchange_diag.get("last_error", ""),
                "ws_error": exchange_diag.get("checks", {}).get("ws", {}).get("error", ""),
                "order_test": exchange_diag.get("checks", {}).get("order_test", {}),
                "infrastructure_blocked": bool(exchange_diag.get("infrastructure_blocked")),
                "provider_restriction_checks": exchange_diag.get("provider_restriction_checks", []),
                "action_required": exchange_diag.get("action_required", []),
            },
        )
    )

    telegram_enabled = bool(settings.get("telegram", {}).get("enabled"))
    has_telegram = bool(get_env("TELEGRAM_BOT_TOKEN") and settings.get("telegram", {}).get("chat_id"))
    if telegram_enabled and not has_telegram:
        g8_status = "FAIL"
        g8_reason = "Telegram enabled but not configured"
    elif not telegram_enabled:
        g8_status = "WARN"
        g8_reason = "Telegram disabled"
    else:
        g8_status = "PASS"
        g8_reason = "Observability ready"
    gates.append(gate_row("G8_OBSERVABILITY_OK", "Observability", g8_status, g8_reason, {"telegram_enabled": telegram_enabled, "telegram_configured": has_telegram}))

    runtime_state_synced = (
        dict(runtime_state)
        if isinstance(runtime_state, dict)
        else dict(store.load_bot_state())
    )
    g9_status, g9_reason, runtime_snapshot = _runtime_gate_status_for_mode(active_mode, runtime_state_synced)
    gates.append(
        gate_row(
            "G9_RUNTIME_ENGINE_REAL",
            "Runtime engine",
            g9_status,
            g9_reason,
            {
                "mode": active_mode,
                "runtime_engine": _runtime_engine_from_state(runtime_state_synced),
                "runtime_contract": runtime_snapshot,
            },
        )
    )

    storage_status = _user_data_persistence_status()
    if storage_status.get("persistent_storage"):
        g10_status = "PASS"
        g10_reason = "User data en almacenamiento persistente"
    else:
        if active_mode == "live":
            g10_status = "FAIL"
            g10_reason = "User data en almacenamiento efimero; LIVE bloqueado hasta usar volumen persistente"
        else:
            g10_status = "WARN"
            g10_reason = "User data en almacenamiento efimero; posible perdida de estado tras redeploy"
    gates.append(
        gate_row(
            "G10_STORAGE_PERSISTENCE",
            "Storage persistence",
            g10_status,
            g10_reason,
            storage_status,
        )
    )

    overall = "PASS"
    if any(row["status"] == "FAIL" for row in gates):
        overall = "FAIL"
    elif any(row["status"] == "WARN" for row in gates):
        overall = "WARN"

    return {"gates": gates, "overall_status": overall, "mode": active_mode}


def live_can_be_enabled(gates_payload: dict[str, Any]) -> tuple[bool, str]:
    gates = {row["id"]: row for row in gates_payload["gates"]}
    required = [
        "G1_CONFIG_VALID",
        "G2_AUTH_READY",
        "G3_BACKEND_HEALTH",
        "G5_STRATEGY_PRINCIPAL_SET",
        "G6_RISK_LIMITS_SET",
        "G4_EXCHANGE_CONNECTOR_READY",
        "G7_ORDER_SIM_OR_PAPER_OK",
        "G9_RUNTIME_ENGINE_REAL",
        "G10_STORAGE_PERSISTENCE",
    ]
    for gate_id in required:
        row = gates.get(gate_id)
        if not row or row["status"] != "PASS":
            reason = row["reason"] if row else f"{gate_id} missing"
            return False, reason
    return True, "All live gates are PASS"


def build_status_payload() -> dict[str, Any]:
    settings = store.load_settings()
    state = _sync_runtime_state(store.load_bot_state(), settings=settings, persist=True)
    runtime_snapshot = _runtime_contract_snapshot(state)
    telemetry_guard = _runtime_telemetry_guard(runtime_snapshot)
    runtime_engine = str(runtime_snapshot.get("runtime_engine") or _runtime_engine_from_state(state))
    runtime_real = runtime_engine == RUNTIME_ENGINE_REAL
    runtime_mode = "real" if runtime_real else "simulado"
    runtime_positions = runtime_bridge.positions()
    execution_snapshot = runtime_bridge.execution_metrics_snapshot()
    gates = evaluate_gates(state.get("mode", "paper"), runtime_state=state)
    return {
        "status": state.get("bot_status", "PAUSED"),
        "state": state.get("bot_status", "PAUSED"),
        "bot_status": state.get("bot_status", "PAUSED"),
        "mode": state.get("mode", "paper"),
        "exchange": {"name": settings.get("exchange", exchange_name()), "mode": settings.get("mode", default_mode().upper())},
        "runtime": {
            "engine": runtime_engine,
            "mode": runtime_mode,
            "real_trading_enabled": runtime_real,
            "contract_version": str(runtime_snapshot.get("contract_version") or RUNTIME_CONTRACT_VERSION),
            "telemetry_source": str(runtime_snapshot.get("telemetry_source") or RUNTIME_TELEMETRY_SOURCE_SYNTHETIC),
            "ready_for_live": bool(runtime_snapshot.get("ready_for_live", False)),
            "readiness_checks": runtime_snapshot.get("checks") if isinstance(runtime_snapshot.get("checks"), dict) else {},
            "telemetry_ok": bool(telemetry_guard.get("ok", False)),
            "telemetry_fail_closed": bool(telemetry_guard.get("fail_closed", True)),
            "telemetry_reason": str(telemetry_guard.get("reason") or ""),
            "warning": None if runtime_real else "Runtime simulado: no se envian ordenes reales al exchange.",
        },
        "runtime_engine": runtime_engine,
        "runtime_mode": runtime_mode,
        "runtime_snapshot": runtime_snapshot,
        "runtime_telemetry_guard": telemetry_guard,
        "equity": float(state.get("equity", 10000.0)),
        "daily_pnl": float(state.get("daily_pnl", 0.0)),
        "pnl": {
            "daily": float(state.get("daily_pnl", 0.0)),
            "weekly": float(state.get("daily_pnl", 0.0)) * 3.1,
            "monthly": float(state.get("daily_pnl", 0.0)) * 11.0,
        },
        "max_dd": {"value": float(state.get("max_dd", -0.04)), "limit": -abs(settings.get("risk_defaults", {}).get("max_dd", 22.0) / 100)},
        "daily_loss": {"value": float(state.get("daily_loss", -0.01)), "limit": -abs(settings.get("risk_defaults", {}).get("max_daily_loss", 5.0) / 100)},
        "risk_flags": {"safe_mode": bool(state.get("safe_mode")), "killed": bool(state.get("killed"))},
        "last_heartbeat": state.get("last_heartbeat", utc_now_iso()),
        "updated_at": utc_now_iso(),
        "health": {
            "api_latency_ms": _as_float(execution_snapshot.get("latency_ms_p95"), 0.0),
            "ws_connected": bool(runtime_snapshot.get("runtime_loop_alive", False)) if runtime_real else True,
            "ws_lag_ms": int(_as_float(execution_snapshot.get("latency_ms_p95"), 0.0) * 0.65),
            "errors_5m": int(execution_snapshot.get("api_errors", 0)),
            "rate_limits_5m": int(execution_snapshot.get("rate_limit_hits", 0)),
            "errors_24h": int(execution_snapshot.get("api_errors", 0)),
        },
        "gates_overall": gates["overall_status"],
        "positions": runtime_positions,
    }


def build_execution_metrics_payload() -> dict[str, Any]:
    settings = store.load_settings()
    state = _sync_runtime_state(store.load_bot_state(), settings=settings, persist=True)
    runtime_snapshot = _runtime_contract_snapshot(state)
    telemetry_guard = _runtime_telemetry_guard(runtime_snapshot)
    payload = runtime_bridge.execution_metrics_snapshot()
    if bool(telemetry_guard.get("fail_closed", True)):
        # AP-1004 fail-closed: no exponer metricas "sanas" cuando la fuente es sintetica.
        payload["maker_ratio"] = 0.0
        payload["fill_ratio"] = 0.0
        payload["latency_ms_p95"] = max(999.0, _as_float(payload.get("latency_ms_p95"), 0.0))
        payload["api_errors"] = max(1, _as_int(payload.get("api_errors"), 0))
        payload["rate_limit_hits"] = max(1, _as_int(payload.get("rate_limit_hits"), 0))
        payload["fills_count_runtime"] = 0
        payload["fills_notional_runtime_usd"] = 0.0
        payload["fees_total_runtime_usd"] = 0.0
        payload["spread_total_runtime_usd"] = 0.0
        payload["slippage_total_runtime_usd"] = 0.0
        payload["funding_total_runtime_usd"] = 0.0
        payload["total_cost_runtime_usd"] = 0.0
        payload["runtime_costs"] = {
            "fills_count": 0,
            "fills_notional_usd": 0.0,
            "fees_total_usd": 0.0,
            "spread_total_usd": 0.0,
            "slippage_total_usd": 0.0,
            "funding_total_usd": 0.0,
            "total_cost_usd": 0.0,
        }
        notes = list(payload.get("notes") or [])
        notes.append("Telemetry synthetic: fail-closed activo para bloquear promotion/live.")
        payload["notes"] = notes
    return {
        "runtime_contract_version": str(runtime_snapshot.get("contract_version") or RUNTIME_CONTRACT_VERSION),
        "runtime_telemetry_source": str(runtime_snapshot.get("telemetry_source") or RUNTIME_TELEMETRY_SOURCE_SYNTHETIC),
        "runtime_telemetry_ok": bool(telemetry_guard.get("ok", False)),
        "runtime_telemetry_fail_closed": bool(telemetry_guard.get("fail_closed", True)),
        "runtime_telemetry_reason": str(telemetry_guard.get("reason") or ""),
        "runtime_ready_for_live": bool(runtime_snapshot.get("ready_for_live", False)),
        **payload,
    }


def build_operational_alerts_payload() -> dict[str, Any]:
    now_iso = utc_now_iso()
    settings = store.load_settings()
    runs = store.load_runs()
    try:
        drift_payload = learning_service.compute_drift(settings=settings, runs=runs)
    except Exception as exc:
        drift_payload = {"drift": False, "algo": "unknown", "error": str(exc)}
    execution_payload = build_execution_metrics_payload()
    breaker_payload = store.breaker_events_integrity(window_hours=OPS_ALERT_BREAKER_WINDOW_HOURS, strict=True)
    alerts: list[dict[str, Any]] = []

    def _push_ops_alert(
        *,
        alert_type: str,
        severity: str,
        module_name: str,
        message: str,
        data: dict[str, Any],
    ) -> None:
        alerts.append(
            {
                "id": f"ops_{alert_type}",
                "ts": now_iso,
                "type": alert_type,
                "severity": severity,
                "module": module_name,
                "message": message,
                "related_id": "",
                "data": data,
            }
        )

    drift_detected = bool(drift_payload.get("drift", False))
    if OPS_ALERT_DRIFT_ENABLED and drift_detected:
        _push_ops_alert(
            alert_type="ops_drift",
            severity="warn",
            module_name="learning",
            message="Drift detectado: revisar recommendation/research loop antes de promover.",
            data={
                "algo": drift_payload.get("algo"),
                "research_loop_triggered": bool(drift_payload.get("research_loop_triggered", False)),
            },
        )

    p95_slippage = _as_float(execution_payload.get("p95_slippage"), 0.0)
    if p95_slippage >= OPS_ALERT_SLIPPAGE_P95_WARN_BPS:
        _push_ops_alert(
            alert_type="ops_slippage_anomaly",
            severity="warn",
            module_name="execution",
            message="Slippage p95 anomalo sobre umbral operativo.",
            data={
                "p95_slippage": p95_slippage,
                "threshold_bps": OPS_ALERT_SLIPPAGE_P95_WARN_BPS,
            },
        )

    api_errors = int(_as_int(execution_payload.get("api_errors"), 0))
    if api_errors >= OPS_ALERT_API_ERRORS_WARN:
        _push_ops_alert(
            alert_type="ops_api_errors",
            severity="error",
            module_name="execution",
            message="Errores de API por encima del umbral operativo.",
            data={
                "api_errors": api_errors,
                "threshold": OPS_ALERT_API_ERRORS_WARN,
                "runtime_telemetry_source": execution_payload.get("runtime_telemetry_source"),
            },
        )

    if not bool(breaker_payload.get("ok", False)):
        _push_ops_alert(
            alert_type="ops_breaker_integrity",
            severity="warn",
            module_name="risk",
            message="Integridad de breaker_events no OK en modo estricto.",
            data={
                "status": breaker_payload.get("status"),
                "window_hours": breaker_payload.get("window_hours"),
                "strict_mode": bool(breaker_payload.get("strict_mode", True)),
                "overall": breaker_payload.get("overall"),
                "window": breaker_payload.get("window"),
            },
        )

    return {
        "ok": True,
        "generated_at": now_iso,
        "overall_status": "WARN" if alerts else "PASS",
        "thresholds": {
            "drift_enabled": bool(OPS_ALERT_DRIFT_ENABLED),
            "slippage_p95_warn_bps": OPS_ALERT_SLIPPAGE_P95_WARN_BPS,
            "api_errors_warn": OPS_ALERT_API_ERRORS_WARN,
            "breaker_window_hours": OPS_ALERT_BREAKER_WINDOW_HOURS,
            "breaker_unknown_ratio_warn": BREAKER_EVENTS_UNKNOWN_RATIO_WARN,
            "breaker_min_events_warn": BREAKER_EVENTS_UNKNOWN_MIN_EVENTS,
        },
        "signals": {
            "drift": drift_payload,
            "execution": {
                "p95_slippage": p95_slippage,
                "api_errors": api_errors,
            },
            "breaker_integrity": {
                "status": breaker_payload.get("status"),
                "ok": bool(breaker_payload.get("ok", False)),
                "window_hours": breaker_payload.get("window_hours"),
            },
        },
        "alerts": alerts,
    }


def parse_strategy_package(payload: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            names = archive.namelist()
            yaml_name = next((name for name in names if name.endswith("strategy.yaml")), None)
            py_name = next((name for name in names if name.endswith("strategy.py")), None)
            ts_name = next((name for name in names if name.endswith("strategy.ts")), None)
            if not yaml_name:
                raise HTTPException(status_code=400, detail="Missing strategy.yaml in package")
            if not py_name and not ts_name:
                raise HTTPException(status_code=400, detail="Missing strategy.py or strategy.ts in package")
            metadata = yaml.safe_load(archive.read(yaml_name).decode("utf-8")) or {}
            if not isinstance(metadata, dict):
                raise HTTPException(status_code=400, detail="strategy.yaml must be a map")
            strategy_id = str(metadata.get("id", "")).strip()
            name = str(metadata.get("name", strategy_id)).strip()
            version = str(metadata.get("version", "")).strip()
            description = str(metadata.get("description", "")).strip()
            schema = metadata.get("parameters_schema") or {}
            if not strategy_id:
                raise HTTPException(status_code=400, detail="strategy.yaml.id is required")
            if not version or not SEMVER.match(version):
                raise HTTPException(status_code=400, detail="strategy.yaml.version must be semver")
            code_name = py_name or ts_name
            code_text = archive.read(code_name).decode("utf-8", errors="ignore")
            required_functions = ["generate_signals", "on_bar", "on_trade", "risk_hooks"]
            missing = [fn for fn in required_functions if fn not in code_text]
            if missing:
                raise HTTPException(status_code=400, detail=f"Missing required hooks: {', '.join(missing)}")
            params_yaml = yaml.safe_dump(metadata.get("defaults", {}), sort_keys=False) if metadata.get("defaults") else DEFAULT_PARAMS_YAML
            return {
                "id": strategy_id,
                "name": name,
                "version": version,
                "description": description or f"Uploaded strategy {strategy_id}",
                "parameters_schema": schema if isinstance(schema, dict) else {},
                "params_yaml": params_yaml,
            }
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid zip package") from exc


def parse_strategy_yaml_upload(payload: bytes) -> dict[str, Any]:
    try:
        metadata = yaml.safe_load(payload.decode("utf-8")) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML strategy file: {exc}") from exc
    if not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="Strategy YAML must be a map")
    strategy_id = str(metadata.get("id", "")).strip()
    name = str(metadata.get("name", strategy_id)).strip()
    version = str(metadata.get("version", "")).strip()
    description = str(metadata.get("description", "")).strip()
    schema = metadata.get("parameters_schema") or metadata.get("schema") or {}
    defaults = metadata.get("defaults") or metadata.get("params") or {}
    tags = metadata.get("tags") or ["upload", "yaml"]
    notes = str(metadata.get("notes", "Uploaded YAML strategy"))[:300]
    if not strategy_id:
        raise HTTPException(status_code=400, detail="strategy.id is required")
    if not version or not SEMVER.match(version):
        raise HTTPException(status_code=400, detail="strategy.version must be semver")
    if schema and not isinstance(schema, dict):
        raise HTTPException(status_code=400, detail="parameters_schema must be an object")
    if defaults and not isinstance(defaults, dict):
        raise HTTPException(status_code=400, detail="defaults/params must be an object")
    if not isinstance(tags, list):
        tags = ["upload", "yaml"]
    params_yaml = yaml.safe_dump(defaults if defaults else {}, sort_keys=False) if defaults else DEFAULT_PARAMS_YAML
    return {
        "id": strategy_id,
        "name": name or strategy_id,
        "version": version,
        "description": description or f"Uploaded YAML strategy {strategy_id}",
        "parameters_schema": schema if isinstance(schema, dict) else {},
        "params_yaml": params_yaml,
        "tags": [str(tag) for tag in tags if str(tag).strip()],
        "notes": notes,
    }

def create_app() -> FastAPI:
    app = FastAPI(title="RTLAB API", version=APP_VERSION)

    @app.on_event("startup")
    async def instrument_registry_startup_sync() -> None:
        try:
            store.instrument_registry_startup_sync = store.instrument_registry.sync_on_startup()
        except Exception as exc:
            store.instrument_registry_startup_sync = {
                "ok": False,
                "startup": True,
                "skipped": False,
                "reason": "startup_sync_failed",
                "error": str(exc),
            }
            store.add_log(
                event_type="instrument_registry",
                severity="warn",
                module="instruments",
                message="Instrument registry startup sync failed",
                related_ids=[],
                payload={"error": str(exc)},
            )

    @app.middleware("http")
    async def api_rate_limit_middleware(request: Request, call_next):
        allowed, retry_after_sec, bucket = API_RATE_LIMITER.check(
            client_ip=_request_client_ip(request),
            path=request.url.path,
            method=request.method,
        )
        if not allowed:
            detail = (
                f"Rate limit de endpoint costoso excedido. Reintenta en {retry_after_sec}s."
                if bucket == "expensive"
                else f"Rate limit general de API excedido. Reintenta en {retry_after_sec}s."
            )
            return JSONResponse(
                status_code=429,
                content={"detail": detail, "bucket": bucket},
                headers={
                    "Retry-After": str(retry_after_sec),
                    "X-RTLAB-RateLimit-Bucket": bucket,
                },
            )
        response = await call_next(request)
        if bucket not in {"disabled", "exempt"}:
            response.headers["X-RTLAB-RateLimit-Bucket"] = bucket
        return response

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        settings = store.load_settings()
        state = _sync_runtime_state(store.load_bot_state(), settings=settings, persist=True)
        mode = state.get("mode", "paper")
        runtime_snapshot = _runtime_contract_snapshot(state)
        telemetry_guard = _runtime_telemetry_guard(runtime_snapshot)
        runtime_engine = str(runtime_snapshot.get("runtime_engine") or _runtime_engine_from_state(state))
        storage_status = _user_data_persistence_status()
        return {
            "status": "ok",
            "ok": True,
            "time": utc_now_iso(),
            "version": APP_VERSION,
            "mode": mode,
            "runtime_engine": runtime_engine,
            "runtime_mode": "real" if runtime_engine == RUNTIME_ENGINE_REAL else "simulado",
            "runtime_contract_version": str(runtime_snapshot.get("contract_version") or RUNTIME_CONTRACT_VERSION),
            "runtime_telemetry_source": str(runtime_snapshot.get("telemetry_source") or RUNTIME_TELEMETRY_SOURCE_SYNTHETIC),
            "runtime_telemetry_fail_closed": bool(telemetry_guard.get("fail_closed", True)),
            "runtime_ready_for_live": bool(runtime_snapshot.get("ready_for_live", False)),
            "ws": {"connected": True, "transport": "sse", "url": "/api/v1/stream", "last_event_at": utc_now_iso()},
            "exchange": {"name": exchange_name(), "mode": mode.upper()},
            "db": {"ok": True, "driver": "sqlite"},
            "storage": storage_status,
        }

    @app.post("/api/v1/auth/login")
    def auth_login(request: Request, body: LoginBody) -> dict[str, Any]:
        username = body.username.strip()
        client_ip = _request_client_ip(request)
        limiter_key = f"{client_ip}:{username.lower()}"
        allowed, retry_after_sec, reason = LOGIN_RATE_LIMITER.check(limiter_key)
        if not allowed:
            detail = (
                f"Demasiados intentos de login. Reintenta en {retry_after_sec}s."
                if reason == "rate_limit"
                else f"Acceso temporalmente bloqueado por seguridad. Reintenta en {retry_after_sec}s."
            )
            raise HTTPException(status_code=429, detail=detail)
        role: str | None = None
        if username == admin_username() and body.password == admin_password():
            role = ROLE_ADMIN
        elif username == viewer_username() and body.password == viewer_password():
            role = ROLE_VIEWER
        if not role:
            LOGIN_RATE_LIMITER.register_failure(limiter_key)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        LOGIN_RATE_LIMITER.register_success(limiter_key)
        token = store.create_session(username=username, role=role)
        store.add_log(
            event_type="auth",
            severity="info",
            module="auth",
            message=f"Login success for {username}",
            related_ids=[],
            payload={"role": role},
        )
        return {"token": token, "role": role}

    @app.get("/api/v1/me")
    def me(user: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return {"username": user["username"], "role": user["role"]}

    @app.get("/api/v1/auth/internal-proxy/status")
    def internal_proxy_status(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        state = _internal_proxy_token_state()
        return {
            "ok": bool(state.get("active_token_configured")),
            "active_token_configured": bool(state.get("active_token_configured")),
            "previous_token_configured": bool(state.get("previous_token_configured")),
            "previous_token_enabled": bool(state.get("previous_token_enabled")),
            "previous_token_expires_at": state.get("previous_token_expires_at"),
            "previous_token_seconds_remaining": int(state.get("previous_token_seconds_remaining") or 0),
            "warnings": state.get("warnings") or [],
            "rotation_ready": bool(state.get("active_token_configured") and state.get("previous_token_enabled")),
        }

    @app.get("/api/v1/gates")
    def gates(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        payload = evaluate_gates()
        settings = store.load_settings()
        settings["gate_checklist"] = payload["gates"]
        store.save_settings(settings)
        return payload

    @app.post("/api/v1/gates/reevaluate")
    def gates_reevaluate(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        payload = evaluate_gates(force_exchange_check=True)
        store.add_log(
            event_type="gates",
            severity="info",
            module="risk",
            message="Gate reevaluation requested",
            related_ids=[],
            payload={"overall_status": payload["overall_status"]},
        )
        return payload

    @app.get("/api/v1/data/catalog")
    def data_catalog(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        catalog = DataCatalog(USER_DATA_DIR)
        return {"items": [row.to_dict() for row in catalog.list_entries()], "timeframes": list(SUPPORTED_TIMEFRAMES), "universes": MARKET_UNIVERSES}

    @app.get("/api/v1/data/status")
    def data_status(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return DataCatalog(USER_DATA_DIR).status()

    @app.get("/api/v1/instruments/registry/summary")
    def instruments_registry_summary(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return store.instrument_registry.registry_summary()

    @app.get("/api/v1/instruments/registry/snapshots")
    def instruments_registry_snapshots(
        family: str | None = Query(default=None),
        environment: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            items = store.instrument_registry.db.list_snapshots(
                family=family,
                environment=environment,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "items": items,
            "policy_source": store.instrument_registry.policy_source(),
        }

    @app.post("/api/v1/instruments/registry/sync")
    def instruments_registry_sync(
        body: InstrumentRegistrySyncBody,
        _: dict[str, str] = Depends(require_admin),
    ) -> dict[str, Any]:
        try:
            payload = store.instrument_registry.sync(
                family=body.family,
                environment=body.environment,
                startup=False,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="instrument_registry",
            severity="info",
            module="instruments",
            message="Instrument registry sync requested",
            related_ids=[],
            payload={"family": body.family, "environment": body.environment, "ok": payload.get("ok")},
        )
        return payload

    @app.get("/api/v1/instruments/universes")
    def instruments_universes(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return store.instrument_universes.summary()

    @app.get("/api/v1/account/capabilities/summary")
    def account_capabilities_summary(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return store.instrument_registry.capabilities_summary()

    @app.post("/api/v1/execution/preflight")
    def execution_preflight(
        body: ExecutionPreflightBody,
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return store.execution_reality.preflight(body.model_dump())

    @app.post("/api/v1/execution/orders")
    def execution_create_order(
        body: ExecutionPreflightBody,
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return store.execution_reality.create_order(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/execution/orders")
    def execution_list_orders(
        family: str | None = Query(default=None),
        environment: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        status: str | None = Query(default=None),
        strategy_id: str | None = Query(default=None),
        bot_id: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return store.execution_reality.list_orders(
                family=family,
                environment=environment,
                symbol=symbol,
                status=status,
                strategy_id=strategy_id,
                bot_id=bot_id,
                limit=limit,
                offset=offset,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/execution/orders/{execution_order_id}")
    def execution_order_detail(
        execution_order_id: str,
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        payload = store.execution_reality.order_detail(execution_order_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="execution_order_not_found")
        return payload

    @app.post("/api/v1/execution/orders/{execution_order_id}/cancel")
    def execution_cancel_order(
        execution_order_id: str,
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return store.execution_reality.cancel_order(execution_order_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/v1/execution/orders/cancel-all")
    def execution_cancel_all(
        body: ExecutionCancelAllBody,
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return store.execution_reality.cancel_all(
                family=body.family,
                environment=body.environment,
                symbol=body.symbol,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/execution/live-safety/summary")
    def execution_live_safety_summary(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return store.execution_reality.live_safety_summary()

    def _refresh_reporting_views() -> None:
        try:
            store.reporting_bridge.refresh_materialized_views(store.load_runs())
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/v1/reporting/performance/summary")
    def reporting_performance_summary(
        strategy_id: str | None = Query(default=None),
        bot_id: str | None = Query(default=None),
        venue: str | None = Query(default=None),
        family: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        _refresh_reporting_views()
        return store.reporting_bridge.performance_summary(
            strategy_id=strategy_id,
            bot_id=bot_id,
            venue=venue,
            family=family,
            symbol=symbol,
        )

    @app.get("/api/v1/reporting/performance/daily")
    def reporting_performance_daily(
        strategy_id: str | None = Query(default=None),
        bot_id: str | None = Query(default=None),
        venue: str | None = Query(default=None),
        family: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        _refresh_reporting_views()
        return store.reporting_bridge.daily_series(
            strategy_id=strategy_id,
            bot_id=bot_id,
            venue=venue,
            family=family,
            symbol=symbol,
        )

    @app.get("/api/v1/reporting/performance/monthly")
    def reporting_performance_monthly(
        strategy_id: str | None = Query(default=None),
        bot_id: str | None = Query(default=None),
        venue: str | None = Query(default=None),
        family: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        _refresh_reporting_views()
        return store.reporting_bridge.monthly_series(
            strategy_id=strategy_id,
            bot_id=bot_id,
            venue=venue,
            family=family,
            symbol=symbol,
        )

    @app.get("/api/v1/reporting/costs/breakdown")
    def reporting_costs_breakdown(
        strategy_id: str | None = Query(default=None),
        bot_id: str | None = Query(default=None),
        venue: str | None = Query(default=None),
        family: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        _refresh_reporting_views()
        return store.reporting_bridge.costs_breakdown(
            strategy_id=strategy_id,
            bot_id=bot_id,
            venue=venue,
            family=family,
            symbol=symbol,
        )

    @app.get("/api/v1/reporting/trades")
    def reporting_trades(
        strategy_id: str | None = Query(default=None),
        bot_id: str | None = Query(default=None),
        venue: str | None = Query(default=None),
        family: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        limit: int = Query(default=200, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        _refresh_reporting_views()
        return store.reporting_bridge.trades(
            strategy_id=strategy_id,
            bot_id=bot_id,
            venue=venue,
            family=family,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )

    @app.post("/api/v1/reporting/exports/xlsx")
    def reporting_export_xlsx(
        body: ReportingExportBody,
        user: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        _refresh_reporting_views()
        return store.reporting_bridge.create_export(
            export_type="xlsx",
            generated_by=str(user.get("username") or "system"),
            report_scope=body.report_scope,
            strategy_id=body.strategy_id,
            bot_id=body.bot_id,
            venue=body.venue,
            family=body.family,
            symbol=body.symbol,
        )

    @app.post("/api/v1/reporting/exports/pdf")
    def reporting_export_pdf(
        body: ReportingExportBody,
        user: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        _refresh_reporting_views()
        return store.reporting_bridge.create_export(
            export_type="pdf",
            generated_by=str(user.get("username") or "system"),
            report_scope=body.report_scope,
            strategy_id=body.strategy_id,
            bot_id=body.bot_id,
            venue=body.venue,
            family=body.family,
            symbol=body.symbol,
        )

    @app.get("/api/v1/reporting/exports")
    def reporting_exports(
        limit: int = Query(default=100, ge=1, le=500),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        _refresh_reporting_views()
        return {
            "items": store.reporting_bridge.db.list_exports(limit=limit),
            "policy_source": store.reporting_bridge.policy_source(),
        }

    @app.get("/api/v1/strategies")
    def list_strategies(_: dict[str, str] = Depends(current_user)) -> list[dict[str, Any]]:
        return store.list_strategies()

    @app.get("/api/v1/strategies/kpis")
    def strategies_kpis(
        from_ts: str | None = Query(default=None, alias="from"),
        to_ts: str | None = Query(default=None, alias="to"),
        mode: str | None = Query(default="backtest"),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return {"items": store.strategy_kpis_table(from_ts=from_ts, to_ts=to_ts, mode=mode), "mode": (mode or "backtest").lower(), "from": from_ts, "to": to_ts}

    @app.get("/api/v1/strategies/{strategy_id}")
    def strategy_detail(strategy_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        strategy = store.strategy_truth_or_404(strategy_id)
        evidence = store.strategy_evidence_or_404(strategy_id, limit=1)
        return {
            **strategy,
            "last_oos": evidence.get("last_oos"),
        }

    @app.get("/api/v1/strategies/{strategy_id}/truth")
    def strategy_truth(strategy_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return store.strategy_truth_or_404(strategy_id)

    @app.get("/api/v1/strategies/{strategy_id}/evidence")
    def strategy_evidence(
        strategy_id: str,
        limit: int = Query(default=10, ge=1, le=50),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return store.strategy_evidence_or_404(strategy_id, limit=limit)

    @app.get("/api/v1/strategies/{strategy_id}/kpis")
    def strategy_kpis(
        strategy_id: str,
        from_ts: str | None = Query(default=None, alias="from"),
        to_ts: str | None = Query(default=None, alias="to"),
        mode: str | None = Query(default="backtest"),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return store.strategy_kpis(strategy_id, from_ts=from_ts, to_ts=to_ts, mode=mode)

    @app.get("/api/v1/strategies/{strategy_id}/kpis_by_regime")
    def strategy_kpis_by_regime(
        strategy_id: str,
        from_ts: str | None = Query(default=None, alias="from"),
        to_ts: str | None = Query(default=None, alias="to"),
        mode: str | None = Query(default="backtest"),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return store.strategy_kpis_by_regime(strategy_id, from_ts=from_ts, to_ts=to_ts, mode=mode)

    @app.patch("/api/v1/strategies/{strategy_id}")
    def strategy_patch(strategy_id: str, body: StrategyPatchBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        strategy = store.patch_strategy_registry_flags(
            strategy_id,
            enabled_for_trading=body.enabled_for_trading,
            allow_learning=body.allow_learning,
            is_primary=body.is_primary,
            status=body.status,
        )
        return {"ok": True, "strategy": strategy}

    @app.post("/api/v1/strategies/upload")
    async def strategy_upload(file: UploadFile = File(...), _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        filename = file.filename.lower()
        content = await file.read()
        if filename.endswith(".zip"):
            parsed = parse_strategy_package(content)
            package_ext = ".zip"
        elif filename.endswith(".yaml") or filename.endswith(".yml"):
            parsed = parse_strategy_yaml_upload(content)
            package_ext = ".yaml"
        else:
            raise HTTPException(status_code=400, detail="Only .zip, .yaml, .yml strategy uploads are supported")
        strategy = store.save_uploaded_strategy(
            strategy_id=parsed["id"],
            name=parsed["name"],
            version=parsed["version"],
            description=parsed["description"],
            schema=parsed["parameters_schema"],
            params_yaml=parsed["params_yaml"],
            package_bytes=content,
            package_ext=package_ext,
            tags=parsed.get("tags"),
            notes=parsed.get("notes"),
        )
        return {"ok": True, "strategy": strategy}

    @app.post("/api/v1/strategies/import")
    async def strategy_import(file: UploadFile = File(...), _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        return await strategy_upload(file=file, _=_)

    @app.post("/api/v1/strategies/{strategy_id}/enable")
    def strategy_enable(strategy_id: str, body: StrategyEnableBody | None = None, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        enabled = True if body is None else bool(body.enabled)
        return {"ok": True, "strategy": store.set_strategy_enabled(strategy_id, enabled)}

    @app.post("/api/v1/strategies/{strategy_id}/disable")
    def strategy_disable(strategy_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        return {"ok": True, "strategy": store.set_strategy_enabled(strategy_id, False)}

    @app.post("/api/v1/strategies/{strategy_id}/primary")
    def strategy_primary(strategy_id: str, body: StrategyPrimaryBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        strategy = store.set_primary(strategy_id, body.mode)
        return {"ok": True, "strategy": strategy, "mode": body.mode}

    @app.post("/api/v1/strategies/{strategy_id}/duplicate")
    def strategy_duplicate(strategy_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        clone = store.duplicate_strategy(strategy_id)
        return {"ok": True, "strategy": clone}

    @app.put("/api/v1/strategies/{strategy_id}/params")
    async def strategy_params(strategy_id: str, request: Request, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        body = await request.json()
        params_yaml = body.get("params_yaml")
        if not params_yaml and isinstance(body.get("params"), dict):
            params_yaml = yaml.safe_dump(body["params"], sort_keys=False)
        if not params_yaml:
            raise HTTPException(status_code=400, detail="params_yaml or params is required")
        strategy = store.update_strategy_params(strategy_id, params_yaml)
        return {"ok": True, "strategy": strategy}

    @app.get("/api/v1/bots")
    def list_bots(
        response: Response,
        debug_perf: bool = Query(default=False),
        recent_logs: bool | None = Query(default=None),
        recent_logs_per_bot: int | None = Query(default=None, ge=0, le=50),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        default_recent_logs = bool(BOTS_OVERVIEW_INCLUDE_RECENT_LOGS if recent_logs is None else recent_logs)
        default_recent_logs_per_bot = max(
            0,
            int(BOTS_OVERVIEW_RECENT_LOGS_PER_BOT if recent_logs_per_bot is None else recent_logs_per_bot),
        )
        t0 = time.perf_counter()
        payload, cache_state, cache_perf = _get_bots_overview_payload_cached(
            include_recent_logs=recent_logs,
            recent_logs_per_bot=recent_logs_per_bot,
        )
        effective_recent_logs = bool(cache_perf.get("effective_recent_logs", default_recent_logs))
        effective_recent_logs_per_bot = int(cache_perf.get("logs_per_bot_effective", default_recent_logs_per_bot) or 0)
        total_ms = (time.perf_counter() - t0) * 1000.0
        response.headers["X-RTLAB-Bots-Overview-Cache"] = cache_state
        response.headers["X-RTLAB-Bots-Overview-MS"] = f"{total_ms:.3f}"
        response.headers["X-RTLAB-Bots-Count"] = str(int(payload.get("total") or 0))
        response.headers["X-RTLAB-Bots-Recent-Logs"] = "enabled" if effective_recent_logs else "disabled"
        response.headers["X-RTLAB-Bots-Recent-Logs-Per-Bot"] = str(int(effective_recent_logs_per_bot))

        if total_ms >= float(BOTS_OVERVIEW_PROFILE_SLOW_MS):
            now_epoch = time.time()
            if _should_log_bots_overview_slow(now_epoch):
                store.add_log(
                    event_type="bots_overview_slow",
                    severity="warn",
                    module="learning",
                    message=f"/api/v1/bots lento: {total_ms:.1f}ms (cache={cache_state})",
                    related_ids=[],
                    payload={
                        "latency_ms": round(total_ms, 3),
                        "cache": cache_state,
                        "bots_total": int(payload.get("total") or 0),
                        "recent_logs_enabled": bool(effective_recent_logs),
                        "recent_logs_per_bot": int(effective_recent_logs_per_bot),
                        "overview_perf": cache_perf.get("overview") if isinstance(cache_perf.get("overview"), dict) else {},
                    },
                )

        if not debug_perf:
            return payload
        out = dict(payload)
        out["perf"] = {
            "cache": cache_state,
            "latency_ms": round(total_ms, 3),
            "recent_logs_enabled": bool(effective_recent_logs),
            "recent_logs_per_bot": int(effective_recent_logs_per_bot),
            "slow_threshold_ms": int(BOTS_OVERVIEW_PROFILE_SLOW_MS),
            "overview": cache_perf.get("overview") if isinstance(cache_perf.get("overview"), dict) else {},
            "logs_auto_disabled": bool(cache_perf.get("logs_auto_disabled", False)),
            "logs_auto_disable_threshold": int(cache_perf.get("logs_auto_disable_threshold") or 0),
            "bots_count": int(cache_perf.get("bots_count") or 0),
        }
        return out

    def ensure_bot_live_mode_allowed(mode: str | None) -> None:
        if str(mode or "").lower() != "live":
            return
        gates_payload = evaluate_gates("live")
        allowed, reason = live_can_be_enabled(gates_payload)
        if not allowed:
            raise HTTPException(status_code=400, detail=f"No se puede asignar bot en LIVE: {reason}")

    def ensure_bot_capacity_available() -> None:
        current_count = len(store.load_bots())
        if current_count >= int(BOTS_MAX_INSTANCES):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Limite maximo de bots alcanzado ({BOTS_MAX_INSTANCES}). "
                    "Reduce cardinalidad o sube BOTS_MAX_INSTANCES si tu infraestructura lo soporta."
                ),
            )

    @app.post("/api/v1/bots")
    def create_bot(body: BotCreateBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        ensure_bot_live_mode_allowed(body.mode)
        ensure_bot_capacity_available()
        bot = store.create_bot_instance(
            name=body.name,
            engine=body.engine,
            mode=body.mode,
            status=body.status,
            pool_strategy_ids=body.pool_strategy_ids,
            universe=body.universe,
            notes=body.notes,
        )
        _invalidate_bots_overview_cache()
        recs = learning_service.load_all_recommendations()
        items = store.list_bot_instances(recommendations=recs)
        enriched = next((row for row in items if str(row.get("id")) == str(bot.get("id"))), bot)
        return {"ok": True, "bot": enriched}

    @app.patch("/api/v1/bots/{bot_id}")
    def patch_bot(bot_id: str, body: BotPatchBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        ensure_bot_live_mode_allowed(body.mode)
        bot = store.patch_bot_instance(
            bot_id,
            name=body.name,
            engine=body.engine,
            mode=body.mode,
            status=body.status,
            pool_strategy_ids=body.pool_strategy_ids,
            universe=body.universe,
            notes=body.notes,
        )
        _invalidate_bots_overview_cache()
        recs = learning_service.load_all_recommendations()
        items = store.list_bot_instances(recommendations=recs)
        enriched = next((row for row in items if str(row.get("id")) == str(bot.get("id"))), bot)
        return {"ok": True, "bot": enriched}

    @app.get("/api/v1/bots/{bot_id}/policy-state")
    def bot_policy_state(bot_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return {"bot_id": bot_id, "policy_state": store.bot_policy_state_or_404(bot_id)}

    @app.patch("/api/v1/bots/{bot_id}/policy-state")
    def patch_bot_policy_state(bot_id: str, body: BotPolicyStatePatchBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        if (
            body.engine is None
            and body.mode is None
            and body.status is None
            and body.pool_strategy_ids is None
            and body.universe is None
            and body.notes is None
        ):
            raise HTTPException(status_code=400, detail="At least one policy_state field is required")
        ensure_bot_live_mode_allowed(body.mode)
        policy_state = store.patch_bot_policy_state(
            bot_id,
            engine=body.engine,
            mode=body.mode,
            status=body.status,
            pool_strategy_ids=body.pool_strategy_ids,
            universe=body.universe,
            notes=body.notes,
        )
        _invalidate_bots_overview_cache()
        return {"ok": True, "bot_id": bot_id, "policy_state": policy_state}

    @app.get("/api/v1/bots/{bot_id}/decision-log")
    def bot_decision_log(
        bot_id: str,
        severity: str | None = None,
        module: str | None = None,
        since: str | None = None,
        until: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=100, ge=1, le=500),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return store.bot_decision_log(
            bot_id,
            severity=severity,
            module=module,
            since=since,
            until=until,
            page=page,
            page_size=page_size,
        )

    @app.delete("/api/v1/bots/{bot_id}")
    def delete_bot(bot_id: str, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        deleted = store.delete_bot_instance(bot_id)
        _invalidate_bots_overview_cache()
        return {"ok": True, "deleted": deleted, "remaining": len(store.load_bots())}

    @app.post("/api/v1/bots/bulk-patch")
    def patch_bots_bulk(body: BotBulkPatchBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        ids = [str(v).strip() for v in (body.ids or []) if str(v).strip()]
        if not ids:
            raise HTTPException(status_code=400, detail="ids is required")
        if (
            body.engine is None
            and body.mode is None
            and body.status is None
            and body.pool_strategy_ids is None
            and body.universe is None
            and body.notes is None
        ):
            raise HTTPException(status_code=400, detail="At least one patch field is required")
        ensure_bot_live_mode_allowed(body.mode)

        updated_ids: list[str] = []
        errors: list[dict[str, str]] = []
        dedup_ids: list[str] = list(dict.fromkeys(ids))
        for bot_id in dedup_ids:
            try:
                store.patch_bot_instance(
                    bot_id,
                    engine=body.engine,
                    mode=body.mode,
                    status=body.status,
                    pool_strategy_ids=body.pool_strategy_ids,
                    universe=body.universe,
                    notes=body.notes,
                )
                updated_ids.append(bot_id)
            except HTTPException as exc:
                errors.append({"id": bot_id, "detail": str(exc.detail)})
            except Exception as exc:
                errors.append({"id": bot_id, "detail": str(exc)})

        _invalidate_bots_overview_cache()
        recs = learning_service.load_all_recommendations()
        items = store.list_bot_instances(recommendations=recs)
        by_id = {str(row.get("id")): row for row in items}
        updated_items = [by_id[bot_id] for bot_id in updated_ids if bot_id in by_id]
        store.add_log(
            event_type="bot_instance_bulk_patch",
            severity="info" if not errors else "warn",
            module="learning",
            message=f"Bots actualizados en lote por {user.get('username', 'admin')}: {len(updated_ids)} OK / {len(errors)} error(es)",
            related_ids=updated_ids[:20],
            payload={
                "requested": len(dedup_ids),
                "updated": len(updated_ids),
                "errors": len(errors),
                "patch": {
                    "engine": body.engine,
                    "mode": body.mode,
                    "status": body.status,
                    "pool_strategy_ids": body.pool_strategy_ids,
                    "universe": body.universe,
                    "notes": body.notes,
                },
            },
        )
        return {
            "ok": len(errors) == 0,
            "requested_count": len(dedup_ids),
            "updated_count": len(updated_ids),
            "error_count": len(errors),
            "updated": updated_items,
            "errors": errors,
        }

    @app.get("/api/v1/learning/status")
    def learning_status(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        settings_payload = learning_service.ensure_settings_shape(store.load_settings())
        strategies = store.list_strategies()
        payload = learning_service.build_status(
            settings=settings_payload,
            strategies=strategies,
            runs=store.load_runs(),
        )
        payload["experience_learning"] = option_b_engine.summarize(strategies=strategies)
        option_b_cfg = payload.get("option_b") if isinstance(payload.get("option_b"), dict) else {}
        payload["option_b"] = {
            **option_b_cfg,
            "allow_live": False,
            "requires_human_approval": True,
            "experience_store_enabled": True,
        }
        return payload

    @app.get("/api/v1/learning/experience/summary")
    def learning_experience_summary(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return option_b_engine.summarize(strategies=store.list_strategies())

    @app.get("/api/v1/learning/guidance")
    def learning_guidance(
        strategy_id: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        rows = option_b_engine.list_guidance()
        if strategy_id:
            rows = [row for row in rows if str(row.get("strategy_id") or "") == str(strategy_id)]
        return {"items": rows}

    @app.get("/api/v1/learning/proposals")
    def learning_proposals(
        status: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        rows = option_b_engine.list_proposals(status=status)
        return {"items": rows, "status": status}

    @app.get("/api/v1/learning/proposals/{proposal_id}")
    def learning_proposal_detail(proposal_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        row = option_b_engine.get_proposal(proposal_id)
        if not row:
            raise HTTPException(status_code=404, detail="Learning proposal not found")
        return row

    @app.get("/api/v1/learning/shadow/status")
    def learning_shadow_status(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return shadow_coordinator.status()

    @app.post("/api/v1/learning/shadow/start")
    def learning_shadow_start(
        body: ShadowStartBody | None = None,
        _: dict[str, str] = Depends(require_admin),
    ) -> dict[str, Any]:
        payload = body or ShadowStartBody()
        try:
            status = shadow_coordinator.start(
                bot_id=payload.bot_id,
                timeframe=payload.timeframe,
                lookback_bars=int(payload.lookback_bars),
                poll_sec=int(payload.poll_sec),
                symbol=payload.symbol,
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **status}

    @app.post("/api/v1/learning/shadow/stop")
    def learning_shadow_stop(
        body: ShadowStopBody | None = None,
        _: dict[str, str] = Depends(require_admin),
    ) -> dict[str, Any]:
        status = shadow_coordinator.stop(reason=(body.reason if body else None))
        return {"ok": True, **status}

    @app.post("/api/v1/learning/proposals/recalculate")
    def learning_proposals_recalculate(body: OptionBRecalculateBody | None = None, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        thresholds = learning_service._canonical_gates_thresholds()
        result = option_b_engine.recalculate(
            strategies=store.list_strategies(),
            pbo_max=float((body.pbo_max if body else None) or thresholds.get("pbo_max") or 0.25),
            dsr_min=float((body.dsr_min if body else None) or thresholds.get("dsr_min") or 0.95),
        )
        store.add_log(
            event_type="learning_option_b_recalculate",
            severity="info",
            module="learning",
            message="Opcion B recalculada desde Experience Store.",
            related_ids=[str(row.get("id") or "") for row in (result.get("proposals") or [])[:20]],
            payload={
                "contexts": result.get("contexts"),
                "generated_at": result.get("generated_at"),
                "allow_live": False,
            },
        )
        return result

    @app.post("/api/v1/learning/proposals/{proposal_id}/approve")
    def learning_proposal_approve(
        proposal_id: str,
        body: OptionBDecisionBody | None = None,
        user: dict[str, str] = Depends(require_admin),
    ) -> dict[str, Any]:
        row = option_b_engine.set_proposal_status(proposal_id, status="approved", note=(body.note if body else None))
        if not row:
            raise HTTPException(status_code=404, detail="Learning proposal not found")
        store.add_log(
            event_type="learning_option_b_approve",
            severity="info",
            module="learning",
            message=f"Propuesta Opcion B aprobada: {proposal_id}",
            related_ids=[proposal_id, str(row.get("proposed_strategy_id") or "")],
            payload={
                "reviewer": user.get("username", "admin"),
                "note": (body.note if body else None) or "",
                "allow_live": False,
                "shadow_first": True,
            },
        )
        return {
            "ok": True,
            "proposal": row,
            "option_b": {"applied_live": False, "requires_shadow_first": True, "requires_human_approval": True},
            "canary_plan": ["shadow_5", "shadow_15", "shadow_35", "shadow_60", "shadow_100"],
        }

    @app.post("/api/v1/learning/proposals/{proposal_id}/reject")
    def learning_proposal_reject(
        proposal_id: str,
        body: OptionBDecisionBody | None = None,
        user: dict[str, str] = Depends(require_admin),
    ) -> dict[str, Any]:
        row = option_b_engine.set_proposal_status(proposal_id, status="rejected", note=(body.note if body else None))
        if not row:
            raise HTTPException(status_code=404, detail="Learning proposal not found")
        store.add_log(
            event_type="learning_option_b_reject",
            severity="info",
            module="learning",
            message=f"Propuesta Opcion B rechazada: {proposal_id}",
            related_ids=[proposal_id],
            payload={"reviewer": user.get("username", "admin"), "note": (body.note if body else None) or ""},
        )
        return {"ok": True, "proposal": row}

    @app.post("/api/v1/learning/recommend")
    def learning_recommend(body: LearningRecommendBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        settings_payload = learning_service.ensure_settings_shape(store.load_settings())
        try:
            recommendation = learning_service.recommend_from_pool(
                settings=settings_payload,
                strategies=store.list_strategies(),
                runs=store.load_runs(),
                mode=body.mode,
                from_ts=body.from_ts,
                to_ts=body.to_ts,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="learning_recommend",
            severity="info",
            module="learning",
            message="Recomendacion de aprendizaje generada (Option B).",
            related_ids=[str(recommendation.get("id") or "")],
            payload={"mode": body.mode, "active_strategy_id": recommendation.get("active_strategy_id"), "allow_live": False},
        )
        return recommendation

    @app.get("/api/v1/learning/weights-history")
    def learning_weights_history(
        from_ts: str | None = Query(default=None, alias="from"),
        to_ts: str | None = Query(default=None, alias="to"),
        mode: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return {
            "items": learning_service.weights_history(from_ts=from_ts, to_ts=to_ts, mode=mode),
            "from": from_ts,
            "to": to_ts,
            "mode": mode,
        }

    @app.post("/api/v1/learning/approve")
    def learning_approve(body: LearningDecisionBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        row = learning_service.update_runtime_recommendation_status(body.recommendation_id, status="APPROVED", note=body.note)
        if not row:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        # Opcion B: crea candidato de rollout (offline) pero no aplica live.
        candidate_strategy_id = str(row.get("active_strategy_id") or "")
        if not candidate_strategy_id:
            raise HTTPException(status_code=400, detail="Recommendation without active_strategy_id")
        strategies = store.list_strategies()
        primary = next((s for s in strategies if bool(s.get("is_primary"))), None)
        candidate_run = store.latest_run_for_strategy(candidate_strategy_id)
        baseline_run = store.latest_run_for_strategy(str(primary.get("id"))) if primary else None
        rollout_started = False
        rollout_error = None
        if candidate_run and baseline_run:
            try:
                gate_eval = GateEvaluator(repo_root=MONOREPO_ROOT).evaluate(candidate_run)
                compare_eval = CompareEngine().compare(baseline_run, candidate_run)
                state = rollout_manager.start_offline(
                    baseline_run=baseline_run,
                    candidate_run=candidate_run,
                    baseline_strategy=primary or {"name": baseline_run.get("strategy_id"), "version": "-"},
                    candidate_strategy=next((s for s in strategies if s["id"] == candidate_strategy_id), {"name": candidate_strategy_id, "version": "-"}),
                    gates_result=gate_eval,
                    compare_result=compare_eval,
                    actor=user.get("username", "admin"),
                    note=body.note,
                )
                row["rollout"] = {"started": True, "state": state.get("state"), "rollout_id": state.get("rollout_id")}
                rollout_started = True
            except Exception as exc:
                rollout_error = str(exc)
                row["rollout"] = {"started": False, "error": rollout_error}
                learning_service.update_runtime_recommendation_status(body.recommendation_id, status="APPROVED", note=(body.note or ""))
        else:
            row["rollout"] = {
                "started": False,
                "error": "Faltan runs de baseline/candidato para iniciar rollout",
                "candidate_run_available": bool(candidate_run),
                "baseline_run_available": bool(baseline_run),
            }
        store.add_log(
            event_type="learning_approve",
            severity="info",
            module="learning",
            message=f"Recommendation {body.recommendation_id} aprobada (Option B).",
            related_ids=[body.recommendation_id, candidate_strategy_id],
            payload={"rollout_started": rollout_started, "rollout_error": rollout_error, "allow_live": False},
        )
        return {"ok": True, "recommendation": row, "option_b": {"applied_live": False, "requires_rollout": True}}

    @app.post("/api/v1/learning/reject")
    def learning_reject(body: LearningDecisionBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        row = learning_service.update_runtime_recommendation_status(body.recommendation_id, status="REJECTED", note=body.note)
        if not row:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        store.add_log(
            event_type="learning_reject",
            severity="info",
            module="learning",
            message=f"Recommendation {body.recommendation_id} rechazada.",
            related_ids=[body.recommendation_id],
            payload={"note": body.note or ""},
        )
        return {"ok": True, "recommendation": row}

    @app.post("/api/v1/learning/run-now")
    def learning_run_now(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        settings_payload = learning_service.ensure_settings_shape(store.load_settings())
        try:
            result = learning_service.run_research(
                settings=settings_payload,
                strategies=store.list_strategies(),
                runs=store.load_runs(),
                backtest_eval=_learning_eval_candidate,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="learning_run",
            severity="info",
            module="learning",
            message="Research loop executed (Option B)",
            related_ids=[],
            payload={"result": result, "allow_live": False},
        )
        return result

    @app.get("/api/v1/learning/drift")
    def learning_drift(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        settings_payload = learning_service.ensure_settings_shape(store.load_settings())
        return learning_service.compute_drift(settings=settings_payload, runs=store.load_runs())

    @app.get("/api/v1/learning/recommendations")
    def learning_recommendations(_: dict[str, str] = Depends(current_user)) -> list[dict[str, Any]]:
        return learning_service.load_all_recommendations()

    @app.get("/api/v1/learning/recommendations/{candidate_id}")
    def learning_recommendation_detail(candidate_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        row = learning_service.get_any_recommendation(candidate_id)
        if not row:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        return row

    @app.post("/api/v1/research/change-points")
    def research_change_points(body: ResearchChangePointsBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        values = [float(x) for x in (body.series or [])]
        if len(values) < 10:
            raise HTTPException(status_code=400, detail="series requiere al menos 10 puntos")
        max_breakpoints = max(1, min(int(body.max_breakpoints or 5), 20))
        caps = _build_learning_capabilities_registry()
        cap = caps.get("offline_change_points", {"id": "offline_change_points", "available": False, "missing": ["ruptures"]})
        warnings: list[str] = []

        def _heuristic_breakpoints(series: list[float]) -> list[int]:
            diffs = []
            for idx in range(1, len(series)):
                diffs.append((idx, abs(series[idx] - series[idx - 1])))
            if not diffs:
                return []
            vals = [d for _, d in diffs]
            mean_d = sum(vals) / len(vals)
            var_d = sum((d - mean_d) ** 2 for d in vals) / max(1, len(vals))
            std_d = var_d ** 0.5
            threshold = mean_d + (2.0 * std_d if std_d > 0 else max(mean_d * 0.75, 1e-9))
            ranked = sorted((row for row in diffs if row[1] >= threshold), key=lambda x: x[1], reverse=True)
            min_gap = max(5, len(series) // (max_breakpoints + 1))
            picked: list[int] = []
            for idx, _score in ranked:
                if any(abs(idx - prev) < min_gap for prev in picked):
                    continue
                picked.append(idx)
                if len(picked) >= max_breakpoints:
                    break
            return sorted(picked)

        method = "heuristic"
        breakpoint_idx: list[int] = []
        score = None
        if bool(cap.get("available")):
            try:
                import numpy as np  # local import: research capability optional
                import ruptures as rpt  # type: ignore

                arr = np.asarray(values, dtype=float).reshape(-1, 1)
                algo = rpt.Pelt(model=body.model).fit(arr)
                pen = float(body.penalty) if body.penalty is not None else max(3.0, len(values) * 0.01)
                raw = [int(x) for x in algo.predict(pen=pen)]
                breakpoint_idx = [x for x in raw if 0 < x < len(values)]
                if len(breakpoint_idx) > max_breakpoints:
                    breakpoint_idx = breakpoint_idx[:max_breakpoints]
                method = "ruptures_pelt"
                score = {"penalty": pen}
            except Exception as exc:
                warnings.append(f"ruptures no disponible/operativo, se usa fallback heuristico: {exc}")
                breakpoint_idx = _heuristic_breakpoints(values)
        else:
            warnings.append("Capability offline_change_points no disponible (falta ruptures); se usa fallback heuristico.")
            breakpoint_idx = _heuristic_breakpoints(values)

        global_abs_mean = sum(abs(v) for v in values) / max(1, len(values))
        global_mean = sum(values) / max(1, len(values))
        global_var = sum((v - global_mean) ** 2 for v in values) / max(1, len(values))
        global_std = global_var ** 0.5

        boundaries = [0] + sorted(set(int(x) for x in breakpoint_idx if 0 < int(x) < len(values))) + [len(values)]
        segments: list[dict[str, Any]] = []
        for idx in range(len(boundaries) - 1):
            start_i = boundaries[idx]
            end_i = boundaries[idx + 1]
            seg = values[start_i:end_i]
            if not seg:
                continue
            seg_mean = sum(seg) / len(seg)
            seg_var = sum((v - seg_mean) ** 2 for v in seg) / max(1, len(seg))
            seg_std = seg_var ** 0.5
            seg_abs = sum(abs(v) for v in seg) / len(seg)
            signal_name = str(body.signal_name or "returns").lower()
            if signal_name in {"vpin", "spread", "slippage"} and (seg_abs >= max(global_abs_mean * 1.5, 0.9 if signal_name == "vpin" else 1.0)):
                regime_label = "toxic"
            elif seg_std >= max(global_std * 1.6, 1e-9):
                regime_label = "high_vol"
            elif signal_name in {"returns", "pnl", "expectancy"} and abs(seg_mean) >= max(global_std * 0.8, 1e-9):
                regime_label = "trend"
            else:
                regime_label = "range"
            segments.append(
                {
                    "segment_id": idx + 1,
                    "start_idx": start_i,
                    "end_idx": end_i - 1,
                    "length": len(seg),
                    "mean": round(seg_mean, 8),
                    "std": round(seg_std, 8),
                    "abs_mean": round(seg_abs, 8),
                    "regime_sugerido": regime_label,
                }
            )
        return {
            "ok": True,
            "signal_name": body.signal_name,
            "period": body.period or {},
            "method": method,
            "breakpoints": breakpoint_idx,
            "segments": segments,
            "score": score,
            "capability": cap,
            "warnings": warnings,
        }

    @app.get("/api/v1/research/mlflow/runs")
    def research_mlflow_runs(
        experiment: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=200),
        _: dict[str, str] = Depends(require_admin),
    ) -> dict[str, Any]:
        caps = _build_learning_capabilities_registry()
        cap = caps.get("mlflow_runs", {"id": "mlflow_runs", "available": False})
        tracking_uri = get_env("MLFLOW_TRACKING_URI", "")
        if not cap.get("available"):
            return {
                "ok": True,
                "available": False,
                "configured": bool(tracking_uri),
                "capability": cap,
                "runs": [],
                "message": "Capability mlflow_runs no disponible (instala requirements-research.txt).",
            }
        if not tracking_uri:
            return {
                "ok": True,
                "available": True,
                "configured": False,
                "capability": cap,
                "runs": [],
                "message": "MLFLOW_TRACKING_URI no configurado.",
            }
        try:
            import mlflow  # type: ignore

            mlflow.set_tracking_uri(tracking_uri)
            experiments = mlflow.search_experiments()
            exp_map = {str(getattr(e, "name", "")): str(getattr(e, "experiment_id", "")) for e in experiments}
            experiment_ids = None
            if experiment:
                exp_id = exp_map.get(experiment)
                if not exp_id:
                    return {"ok": True, "available": True, "configured": True, "capability": cap, "runs": [], "message": f"Experiment '{experiment}' no encontrado."}
                experiment_ids = [exp_id]
            runs_df = mlflow.search_runs(experiment_ids=experiment_ids, max_results=int(limit))
            runs: list[dict[str, Any]] = []
            for _, row in runs_df.iterrows():
                runs.append(
                    {
                        "run_id": str(row.get("run_id") or row.get("run_id", "")),
                        "experiment_id": str(row.get("experiment_id") or ""),
                        "status": str(row.get("status") or ""),
                        "start_time": str(row.get("start_time") or ""),
                        "end_time": str(row.get("end_time") or ""),
                        "metrics": {str(k)[8:]: v for k, v in row.items() if str(k).startswith("metrics.")},
                        "params": {str(k)[7:]: v for k, v in row.items() if str(k).startswith("params.")},
                    }
                )
            return {"ok": True, "available": True, "configured": True, "capability": cap, "runs": runs}
        except Exception as exc:
            return {
                "ok": False,
                "available": True,
                "configured": True,
                "capability": cap,
                "runs": [],
                "error": str(exc),
            }

    @app.post("/api/v1/research/mass-backtest/start")
    def research_mass_backtest_start(body: ResearchMassBacktestStartBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        cfg = body.model_dump()
        cfg["bot_id"] = str(cfg.get("bot_id") or "").strip() or None
        cfg["execution_mode"] = str(cfg.get("execution_mode") or "research")
        if str(cfg.get("dataset_source") or "").lower() in {"synthetic", "synthetic_seeded", "synthetic_fallback"}:
            raise HTTPException(
                status_code=400,
                detail="Research Batch solo acepta datos reales. ElegÃ­ dataset_source='auto' o 'dataset'.",
            )
        if not isinstance(cfg.get("costs"), dict):
            cfg["costs"] = {
                "fees_bps": 5.5,
                "spread_bps": 4.0,
                "slippage_bps": 3.0,
                "funding_bps": 1.0,
                "rollover_bps": 0.0,
            }
        cfg["commit_hash"] = get_env("GIT_COMMIT", "local")
        cfg["requested_by"] = user.get("username", "admin")
        _policies_bundle = load_numeric_policies_bundle()
        cfg["policy_snapshot"] = _policies_bundle.get("policies") if isinstance(_policies_bundle.get("policies"), dict) else {}
        cfg["policy_snapshot_summary"] = _policies_bundle.get("summary") if isinstance(_policies_bundle.get("summary"), dict) else {}
        cfg["policy_snapshot_source_root"] = str(_policies_bundle.get("source_root") or "")
        if _policies_bundle.get("warnings"):
            cfg["policy_snapshot_warnings"] = list(_policies_bundle.get("warnings") or [])
        try:
            started = mass_backtest_coordinator.start_async(
                config=cfg,
                strategies=store.list_strategies(),
                historical_runs=store.load_runs(),
                backtest_callback=lambda variant, fold, costs: _mass_backtest_eval_fold(variant, fold, costs, cfg),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="research_mass_backtest_start",
            severity="info",
            module="research",
            message="Mass backtests iniciados",
            related_ids=[x for x in [str(started.get("run_id") or ""), cfg.get("bot_id")] if x],
            payload={"config": cfg, "no_auto_live": True},
        )
        return started

    @app.post("/api/v1/batches")
    def create_research_batch(body: BatchCreateBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        cfg = body.model_dump()
        cfg["bot_id"] = str(cfg.get("bot_id") or "").strip() or None
        cfg["execution_mode"] = str(cfg.get("execution_mode") or "research")
        if str(cfg.get("dataset_source") or "").lower() in {"synthetic", "synthetic_seeded", "synthetic_fallback"}:
            raise HTTPException(
                status_code=400,
                detail="Research Batch solo acepta datos reales. ElegÃ­ dataset_source='auto' o 'dataset'.",
            )
        if not isinstance(cfg.get("costs"), dict):
            cfg["costs"] = {
                "fees_bps": 5.5,
                "spread_bps": 4.0,
                "slippage_bps": 3.0,
                "funding_bps": 1.0,
                "rollover_bps": 0.0,
            }
        cfg["commit_hash"] = get_env("GIT_COMMIT", "local")
        cfg["requested_by"] = user.get("username", "admin")
        cfg["objective"] = str(body.objective or "Research Batch")
        _policies_bundle = load_numeric_policies_bundle()
        cfg["policy_snapshot"] = _policies_bundle.get("policies") if isinstance(_policies_bundle.get("policies"), dict) else {}
        cfg["policy_snapshot_summary"] = _policies_bundle.get("summary") if isinstance(_policies_bundle.get("summary"), dict) else {}
        cfg["policy_snapshot_source_root"] = str(_policies_bundle.get("source_root") or "")
        if _policies_bundle.get("warnings"):
            cfg["policy_snapshot_warnings"] = list(_policies_bundle.get("warnings") or [])
        try:
            started = mass_backtest_coordinator.start_async(
                config=cfg,
                strategies=store.list_strategies(),
                historical_runs=store.load_runs(),
                backtest_callback=lambda variant, fold, costs: _mass_backtest_eval_fold(variant, fold, costs, cfg),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        batch_id = str(started.get("run_id") or "")
        store.add_log(
            event_type="batch_created",
            severity="info",
            module="research",
            message="Research Batch creado",
            related_ids=[x for x in [batch_id, cfg.get("bot_id")] if x],
            payload={"config": cfg, "batch_id": batch_id},
        )
        return {"ok": True, "batch_id": batch_id, **started}

    @app.get("/api/v1/research/funnel")
    def research_funnel(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return _research_funnel_payload()

    @app.get("/api/v1/research/trial-ledger")
    def research_trial_ledger(
        limit: int = Query(default=200, ge=1, le=1000),
        evidence_status: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        items = _collect_research_trial_ledger_items()
        if evidence_status:
            normalized = str(evidence_status or "").strip().lower()
            items = [row for row in items if str(row.get("evidence_status") or "").strip().lower() == normalized]
        return {"generated_at": utc_now_iso(), "items": items[:limit], "count": len(items), "status_filter": evidence_status}

    @app.get("/api/v1/research/mass-backtest/status")
    def research_mass_backtest_status(run_id: str = Query(...), _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return mass_backtest_coordinator.status(run_id)

    @app.get("/api/v1/research/mass-backtest/results")
    def research_mass_backtest_results(
        run_id: str = Query(...),
        limit: int = Query(default=100, ge=1, le=1000),
        strategy_id: str | None = Query(default=None),
        only_pass: bool = Query(default=False),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return mass_backtest_coordinator.results(run_id, limit=limit, strategy_id=strategy_id, only_pass=only_pass)

    @app.get("/api/v1/research/mass-backtest/artifacts")
    def research_mass_backtest_artifacts(run_id: str = Query(...), _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return mass_backtest_coordinator.artifacts(run_id)

    @app.post("/api/v1/research/mass-backtest/mark-candidate")
    def research_mass_backtest_mark_candidate(body: ResearchMassBacktestMarkCandidateBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        results_payload = mass_backtest_coordinator.results(body.run_id, limit=5000)
        rows = results_payload.get("results") if isinstance(results_payload, dict) else []
        row = next((r for r in rows if isinstance(r, dict) and str(r.get("variant_id") or "") == body.variant_id), None)
        if not row:
            raise HTTPException(status_code=404, detail="Variant not found in mass-backtest results")
        results_cfg = results_payload.get("config") if isinstance(results_payload.get("config"), dict) else {}
        execution_mode = str(results_cfg.get("execution_mode") or "research").strip().lower()
        strict_required = execution_mode != "demo"
        strict_fold_flags = [
            bool((fold.get("provenance") or {}).get("strict_strategy_id"))
            for fold in (row.get("folds") or [])
            if isinstance(fold, dict) and isinstance(fold.get("provenance"), dict) and "strict_strategy_id" in (fold.get("provenance") or {})
        ]
        strict_strategy_id = bool(row.get("strict_strategy_id")) if "strict_strategy_id" in row else False
        if strict_fold_flags:
            strict_strategy_id = all(strict_fold_flags)
        if strict_required and not strict_strategy_id:
            raise HTTPException(
                status_code=400,
                detail="Variant no elegible: strict_strategy_id=true es obligatorio en research/promotion no-demo.",
            )
        gates_eval = row.get("gates_eval") if isinstance(row.get("gates_eval"), dict) else {}
        if gates_eval and not bool(gates_eval.get("passed")):
            fail_reasons = [str(x) for x in (gates_eval.get("fail_reasons") or []) if str(x)]
            raise HTTPException(
                status_code=400,
                detail=f"Variant failed advanced gates: {' | '.join(fail_reasons) if fail_reasons else 'gates_fail'}",
            )
        if row.get("recommendable_option_b") is False:
            raise HTTPException(status_code=400, detail="Variant is not eligible for Option B suggestions (gates/constraints)")
        runtime_rows = learning_service.load_runtime_recommendations()
        draft_id = f"rec_mass_{hashlib.sha256(f'{body.run_id}:{body.variant_id}:{utc_now_iso()}'.encode('utf-8')).hexdigest()[:10]}"
        draft = {
            "id": draft_id,
            "status": "DRAFT_MASS_BACKTEST",
            "mode": "backtest",
            "engine_id": "mass_backtest_engine",
            "selector_algo": "regime_rules",
            "active_strategy_id": str(row.get("strategy_id") or ""),
            "weights_sugeridos": {str(row.get("strategy_id") or ""): 1.0},
            "ranking": [
                {
                    "strategy_id": str(row.get("strategy_id") or ""),
                    "reward": float(row.get("score") or 0.0),
                    "score": float(row.get("score") or 0.0),
                    "trade_count": int(((row.get("summary") or {}).get("trade_count_oos")) if isinstance(row.get("summary"), dict) else 0),
                    "expectancy": float(((row.get("summary") or {}).get("expectancy_net_usd")) if isinstance(row.get("summary"), dict) else 0.0),
                    "expectancy_unit": "usd_per_trade",
                    "sharpe": float(((row.get("summary") or {}).get("sharpe_oos")) if isinstance(row.get("summary"), dict) else 0.0),
                    "calmar": float(((row.get("summary") or {}).get("calmar_oos")) if isinstance(row.get("summary"), dict) else 0.0),
                    "max_dd": float(((row.get("summary") or {}).get("max_dd_oos_pct")) if isinstance(row.get("summary"), dict) else 0.0) / 100.0,
                }
            ],
            "mass_backtest": {
                "run_id": body.run_id,
                "variant_id": body.variant_id,
                "params": row.get("params") or {},
                "summary": row.get("summary") or {},
                "regime_metrics": row.get("regime_metrics") or {},
                "hard_filters_pass": bool(row.get("hard_filters_pass")),
                "execution_mode": execution_mode,
                "strict_strategy_id": bool(strict_strategy_id),
                "anti_overfitting": row.get("anti_overfitting") or {},
                "gates_eval": gates_eval,
            },
            "guardrails": {
                "warnings": ["Draft de research masivo. Opcion B: no auto-live; requiere gates + canary + approve humano."],
            },
            "option_b": {"allow_auto_apply": False, "allow_live": False, "requires_human_approval": True},
            "created_at": utc_now_iso(),
            "created_by": user.get("username", "admin"),
            "note": body.note or "",
        }
        runtime_rows.append(draft)
        learning_service._save_runtime_recommendations(runtime_rows)  # internal use within backend
        store.add_log(
            event_type="research_mass_backtest_mark_candidate",
            severity="info",
            module="research",
            message="Variante marcada como candidato (draft Opcion B)",
            related_ids=[body.run_id, body.variant_id, draft_id],
            payload={"strategy_id": row.get("strategy_id"), "score": row.get("score"), "allow_live": False},
        )
        return {"ok": True, "recommendation_draft": draft}

    @app.post("/api/v1/research/beast/start")
    def research_beast_start(body: ResearchBeastStartBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        cfg = body.model_dump()
        cfg["bot_id"] = str(cfg.get("bot_id") or "").strip() or None
        cfg["execution_mode"] = "beast"
        if str(cfg.get("dataset_source") or "").lower() in {"synthetic", "synthetic_seeded", "synthetic_fallback"}:
            raise HTTPException(
                status_code=400,
                detail="Modo Bestia solo acepta datos reales. ElegÃ­ dataset_source='auto' o 'dataset'.",
            )
        if not isinstance(cfg.get("costs"), dict):
            cfg["costs"] = {
                "fees_bps": 5.5,
                "spread_bps": 4.0,
                "slippage_bps": 3.0,
                "funding_bps": 1.0,
                "rollover_bps": 0.0,
            }
        cfg["commit_hash"] = get_env("GIT_COMMIT", "local")
        cfg["requested_by"] = user.get("username", "admin")
        _policies_bundle = load_numeric_policies_bundle()
        cfg["policy_snapshot"] = _policies_bundle.get("policies") if isinstance(_policies_bundle.get("policies"), dict) else {}
        cfg["policy_snapshot_summary"] = _policies_bundle.get("summary") if isinstance(_policies_bundle.get("summary"), dict) else {}
        cfg["policy_snapshot_source_root"] = str(_policies_bundle.get("source_root") or "")
        if _policies_bundle.get("warnings"):
            cfg["policy_snapshot_warnings"] = list(_policies_bundle.get("warnings") or [])
        try:
            started = mass_backtest_coordinator.start_beast_async(
                config=cfg,
                strategies=store.list_strategies(),
                historical_runs=store.load_runs(),
                backtest_callback=lambda variant, fold, costs: _mass_backtest_eval_fold(variant, fold, costs, cfg),
                tier=body.tier,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="research_beast_start",
            severity="info",
            module="research",
            message="Modo Bestia encolado",
            related_ids=[x for x in [str(started.get("run_id") or ""), cfg.get("bot_id")] if x],
            payload={"tier": body.tier, "estimated_trial_units": started.get("estimated_trial_units"), "config": cfg, "no_auto_live": True},
        )
        return started

    @app.get("/api/v1/research/beast/status")
    def research_beast_status(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        payload = mass_backtest_coordinator.beast_status()
        bundle = load_numeric_policies_bundle()
        beast_meta = bundle.get("files", {}).get("beast_mode") if isinstance(bundle.get("files"), dict) else {}
        beast_policy = (
            bundle.get("policies", {}).get("beast_mode", {}).get("beast_mode")
            if isinstance(bundle.get("policies"), dict)
            and isinstance(bundle.get("policies", {}).get("beast_mode"), dict)
            else {}
        )
        policy_enabled_declared = bool(beast_policy.get("enabled")) if isinstance(beast_policy, dict) else False
        policy_state = "enabled"
        if not bundle.get("available") or not isinstance(beast_meta, dict) or not beast_meta.get("exists") or not beast_meta.get("valid"):
            policy_state = "missing"
        elif not policy_enabled_declared:
            policy_state = "disabled"
        payload.update(
            {
                "policy_state": policy_state,
                "policy_available": bool(bundle.get("available")),
                "policy_enabled_declared": policy_enabled_declared,
                "policy_source_root": str(bundle.get("source_root") or ""),
                "policy_warnings": list(bundle.get("warnings") or []),
                "policy_files": bundle.get("files") if isinstance(bundle.get("files"), dict) else {},
            }
        )
        return payload

    @app.get("/api/v1/research/beast/jobs")
    def research_beast_jobs(limit: int = Query(default=50, ge=1, le=500), _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return mass_backtest_coordinator.beast_jobs(limit=limit)

    @app.post("/api/v1/research/beast/stop-all")
    def research_beast_stop_all(body: ResearchBeastStopBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        payload = mass_backtest_coordinator.beast_stop_all(reason=str(body.reason or f"manual_by_{user.get('username', 'admin')}"))
        store.add_log(
            event_type="research_beast_stop_all",
            severity="warn",
            module="research",
            message="Modo Bestia Stop All",
            related_ids=[str(x) for x in (payload.get("canceled_queued") or [])[:20]],
            payload=payload,
        )
        return payload

    @app.post("/api/v1/research/beast/resume")
    def research_beast_resume(user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        payload = mass_backtest_coordinator.beast_resume_dispatch()
        store.add_log(
            event_type="research_beast_resume",
            severity="info",
            module="research",
            message="Modo Bestia reanudado",
            related_ids=[],
            payload={"user": user.get("username", "admin")},
        )
        return payload

    @app.post("/api/v1/learning/adopt")
    def learning_adopt(body: LearningAdoptBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        candidate = learning_service.get_recommendation(body.candidate_id)
        if not candidate:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        if str(candidate.get("status", "")).upper() != "APPROVED":
            raise HTTPException(status_code=400, detail=f"Recommendation not adoptable: {candidate.get('status_reason') or candidate.get('status')}")
        if body.mode == "live":
            raise HTTPException(status_code=400, detail="LIVE adoption is blocked by Option B")

        base_strategy_id = str(candidate.get("base_strategy_id") or DEFAULT_STRATEGY_ID)
        clone = store.duplicate_strategy(base_strategy_id)
        params_yaml = str(candidate.get("generated_params_yaml") or yaml.safe_dump(candidate.get("params") or {}, sort_keys=False))
        updated = store.update_strategy_params(clone["id"], params_yaml)
        enabled = store.set_strategy_enabled(updated["id"], True)
        primary = store.set_primary(enabled["id"], body.mode)

        meta = store.load_strategy_meta()
        if primary["id"] in meta:
            meta[primary["id"]]["name"] = str(candidate.get("name") or meta[primary["id"]].get("name") or primary["id"])
            meta[primary["id"]]["notes"] = f"Adopted from recommendation {body.candidate_id} (mode={body.mode})"
            tags = set(str(x) for x in (meta[primary["id"]].get("tags") or []))
            tags.update({"learning", "adopted", "option_b"})
            meta[primary["id"]]["tags"] = sorted(tags)
            meta[primary["id"]]["updated_at"] = utc_now_iso()
            store.save_strategy_meta(meta)

        store.add_log(
            event_type="learning_adopt",
            severity="info",
            module="learning",
            message=f"Recommendation {body.candidate_id} adopted to {body.mode}",
            related_ids=[body.candidate_id, primary["id"]],
            payload={"mode": body.mode, "allow_live": False},
        )
        return {
            "ok": True,
            "candidate_id": body.candidate_id,
            "mode": body.mode,
            "strategy": store.strategy_or_404(primary["id"]),
            "applied_live": False,
            "allow_auto_apply": False,
        }

    @app.get("/api/v1/rollout/status")
    def rollout_status(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        state = rollout_manager.status()
        settings_payload = store.load_settings()
        return {
            **state,
            "config": settings_payload.get("rollout", RolloutManager.default_rollout_config()),
            "blending_config": settings_payload.get("blending", RolloutManager.default_blending_config()),
            "live_stable_100_requires_approve": bool(
                (settings_payload.get("rollout") or {}).get("require_manual_approval_for_live", True)
            ),
        }

    @app.post("/api/v1/rollout/blending/preview")
    def rollout_blending_preview(body: RolloutBlendPreviewBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        try:
            result = rollout_manager.route_live_signal(
                settings=store.load_settings(),
                baseline_signal=body.baseline_signal,
                candidate_signal=body.candidate_signal,
                symbol=body.symbol,
                timeframe=body.timeframe,
                record_telemetry=bool(body.record_telemetry),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        event = result.get("event", {}) if isinstance(result, dict) else {}
        store.add_log(
            event_type="rollout_blending_preview",
            severity="info",
            module="rollout",
            message=f"Blending preview ({event.get('phase', '-')})",
            related_ids=[str((result.get('state') or {}).get("rollout_id") or "")] if isinstance(result.get("state"), dict) else [],
            payload={
                "symbol": body.symbol or "",
                "timeframe": body.timeframe or "",
                "record_telemetry": bool(body.record_telemetry),
                "event": event,
                "actor": user.get("username", "admin"),
            },
        )
        return {"ok": True, **result}

    @app.post("/api/v1/rollout/start")
    def rollout_start(body: RolloutStartBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        candidate_run = _find_run_or_404(body.candidate_run_id)
        baseline_run = _pick_baseline_run(candidate_run, explicit_run_id=body.baseline_run_id)
        candidate_strategy = store.strategy_or_404(str(candidate_run.get("strategy_id")))
        baseline_strategy = store.strategy_or_404(str(baseline_run.get("strategy_id")))

        candidate_report = dict(candidate_run)
        baseline_report = dict(baseline_run)
        candidate_report["version"] = candidate_strategy.get("version")
        candidate_report["params"] = candidate_strategy.get("params")
        baseline_report["version"] = baseline_strategy.get("version")
        baseline_report["params"] = baseline_strategy.get("params")

        gates_result = rollout_gates.evaluate(candidate_report)
        compare_thresholds = ((store.load_settings().get("rollout") or {}).get("improve_vs_baseline") or {})
        compare_engine = CompareEngine(compare_thresholds if isinstance(compare_thresholds, dict) else {})
        compare_result = compare_engine.compare(baseline_report, candidate_report)

        state = rollout_manager.start_offline(
            baseline_run=baseline_report,
            candidate_run=candidate_report,
            baseline_strategy=baseline_strategy,
            candidate_strategy=candidate_strategy,
            gates_result=gates_result,
            compare_result=compare_result,
            actor=user.get("username", "admin"),
        )
        current = str(state.get("state") or "IDLE")
        if current == "ABORTED":
            status_code = 400
            ok = False
        else:
            status_code = 200
            ok = True
        payload = {
            "ok": ok,
            "state": state,
            "offline_gates": gates_result,
            "compare_vs_baseline": compare_result,
            "baseline_run_id": baseline_report.get("id"),
            "candidate_run_id": candidate_report.get("id"),
            "note": body.note or "",
        }
        if status_code != 200:
            return JSONResponse(status_code=status_code, content=payload)
        store.add_log(
            event_type="rollout_start",
            severity="info" if ok else "warn",
            module="rollout",
            message=f"Rollout start ({current})",
            related_ids=[str(candidate_report.get("id")), str(baseline_report.get("id"))],
            payload={"state": current, "offline_gates": gates_result, "compare": compare_result},
        )
        return payload

    @app.post("/api/v1/rollout/advance")
    def rollout_advance(body: RolloutAdvanceBody | None = None, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        try:
            state = rollout_manager.advance(
                actor=user.get("username", "admin"),
                note=(body.note if body else None),
                settings=store.load_settings(),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="rollout_advance",
            severity="info",
            module="rollout",
            message=f"Rollout advanced to {state.get('state')}",
            related_ids=[str(state.get("rollout_id") or "")],
            payload={"state": state.get("state"), "current_phase": state.get("current_phase"), "note": body.note if body else ""},
        )
        return {"ok": True, "state": state}

    @app.post("/api/v1/rollout/evaluate-phase")
    def rollout_evaluate_phase(body: RolloutEvaluatePhaseBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        state_before = rollout_manager.status()
        current_state = str(state_before.get("state") or "IDLE")
        expected_state_by_phase = {
            "paper_soak": "PAPER_SOAK",
            "testnet_soak": "TESTNET_SOAK",
            "shadow": "LIVE_SHADOW",
            "canary05": "LIVE_CANARY_05",
            "canary15": "LIVE_CANARY_15",
            "canary35": "LIVE_CANARY_35",
            "canary60": "LIVE_CANARY_60",
        }
        expected_state = expected_state_by_phase[str(body.phase)]
        if current_state != expected_state:
            raise HTTPException(status_code=400, detail=f"Rollout state must be {expected_state} (current={current_state})")
        if body.override_started_at:
            rollout_manager.set_phase_started_at(body.phase, body.override_started_at)

        # AP-2003 fail-closed: no evaluar fases soak/live con telemetria sintetica.
        status_for_guard = build_status_payload()
        telemetry_guard = status_for_guard.get("runtime_telemetry_guard") if isinstance(status_for_guard.get("runtime_telemetry_guard"), dict) else {}
        telemetry_ok = bool(telemetry_guard.get("ok", False))
        telemetry_source = str(telemetry_guard.get("telemetry_source") or RUNTIME_TELEMETRY_SOURCE_SYNTHETIC)
        if not telemetry_ok:
            reason = str(telemetry_guard.get("reason") or "runtime telemetry guard fail-closed")
            store.add_log(
                event_type="rollout_phase_eval_blocked",
                severity="warn",
                module="rollout",
                message="Rollout evaluate-phase bloqueado por telemetry_source sintetico",
                related_ids=[str(state_before.get("rollout_id") or "")],
                payload={
                    "phase": body.phase,
                    "telemetry_source": telemetry_source,
                    "reason": reason,
                },
            )
            raise HTTPException(
                status_code=400,
                detail=f"Rollout phase evaluation blocked: telemetry_source={telemetry_source} (fail-closed). {reason}",
            )

        settings_payload = store.load_settings()
        execution_payload = build_execution_metrics_payload()
        logs_payload = store.list_logs(severity=None, module=None, since=None, until=None, page=1, page_size=250)
        logs_items = logs_payload.get("items", []) if isinstance(logs_payload, dict) else []
        logs_items = logs_items if isinstance(logs_items, list) else []

        try:
            if body.phase == "paper_soak":
                status_payload = build_status_payload()
                new_state = rollout_manager.evaluate_paper_soak(
                    settings=settings_payload,
                    status_payload=status_payload,
                    execution_payload=execution_payload,
                    logs=logs_items,
                    auto_abort=bool(body.auto_abort),
                )
            elif body.phase == "testnet_soak":
                diagnose_payload = diagnose_exchange("testnet", force_refresh=True)
                new_state = rollout_manager.evaluate_testnet_soak(
                    settings=settings_payload,
                    execution_payload=execution_payload,
                    diagnose_payload=diagnose_payload,
                    logs=logs_items,
                    auto_abort=bool(body.auto_abort),
                )
            else:
                status_payload = build_status_payload()
                new_state = rollout_manager.evaluate_live_phase(
                    settings=settings_payload,
                    status_payload=status_payload,
                    execution_payload=execution_payload,
                    logs=logs_items,
                    baseline_live_kpis=body.baseline_live_kpis,
                    auto_rollback=bool(body.auto_abort),
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        phase_eval = ((new_state.get("phase_evaluations") or {}).get(body.phase) or {}) if isinstance(new_state.get("phase_evaluations"), dict) else {}
        advanced = False
        if bool(body.auto_advance) and bool(phase_eval.get("passed")) and str(new_state.get("state")) == expected_state:
            new_state = rollout_manager.advance(
                actor=user.get("username", "admin"),
                note=f"Auto-advance after {body.phase.upper()} PASS",
                settings=settings_payload,
            )
            advanced = True

        severity = "info" if phase_eval.get("passed") else ("error" if phase_eval.get("hard_fail") else "warn")
        store.add_log(
            event_type="rollout_phase_eval",
            severity=severity,
            module="rollout",
            message=f"{body.phase.upper()} evaluation: {phase_eval.get('status', 'UNKNOWN')}",
            related_ids=[str(new_state.get("rollout_id") or "")],
            payload={"phase": body.phase, "evaluation": phase_eval, "advanced": advanced},
        )
        return {"ok": True, "phase": body.phase, "advanced": advanced, "evaluation": phase_eval, "state": new_state}

    @app.post("/api/v1/rollout/approve")
    def rollout_approve(body: RolloutDecisionBody | None = None, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        try:
            state = rollout_manager.approve(actor=user.get("username", "admin"), settings=store.load_settings())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="rollout_approve",
            severity="warn",
            module="rollout",
            message="Rollout approved for live progression",
            related_ids=[str(state.get("rollout_id") or "")],
            payload={"note": (body.reason if body else "") or ""},
        )
        return {"ok": True, "state": state}

    @app.post("/api/v1/rollout/reject")
    def rollout_reject(body: RolloutDecisionBody | None = None, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        reason = (body.reason if body else None) or "Rejected by admin"
        try:
            state = rollout_manager.reject(reason=reason, actor=user.get("username", "admin"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="rollout_reject",
            severity="warn",
            module="rollout",
            message="Rollout rejected by admin",
            related_ids=[str(state.get("rollout_id") or "")],
            payload={"reason": reason},
        )
        return {"ok": True, "state": state}

    @app.post("/api/v1/rollout/rollback")
    def rollout_rollback(body: RolloutDecisionBody | None = None, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        reason = (body.reason if body else None) or "Manual rollback requested"
        try:
            state = rollout_manager.rollback(reason=reason, actor=user.get("username", "admin"), auto=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        store.add_log(
            event_type="rollout_rollback",
            severity="error",
            module="rollout",
            message="Rollout rolled back to baseline",
            related_ids=[str(state.get("rollout_id") or "")],
            payload={"reason": reason, "weights": state.get("weights")},
        )
        return {"ok": True, "state": state}

    @app.post("/api/v1/backtests/run")
    async def backtests_run(request: Request, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        body = await request.json()
        strategy_id = body.get("strategy_id") or DEFAULT_STRATEGY_ID
        period = body.get("period") or {}
        start = body.get("start") or period.get("start") or "2024-01-01"
        end = body.get("end") or period.get("end") or "2024-12-31"
        costs_input = body.get("costs") or body.get("costs_model") or {}
        fees_bps = float(body.get("fees_bps") or costs_input.get("fees_bps") or 5.5)
        spread_bps = float(body.get("spread_bps") or costs_input.get("spread_bps") or 4.0)
        slippage_bps = float(body.get("slippage_bps") or costs_input.get("slippage_bps") or 3.0)
        funding_bps = float(body.get("funding_bps") or costs_input.get("funding_bps") or 1.0)
        rollover_bps = float(body.get("rollover_bps") or costs_input.get("rollover_bps") or 0.0)
        validation_mode = body.get("validation_mode") or "walk-forward"
        use_orderflow_raw = body.get("use_orderflow_data", True)
        use_orderflow_data = bool(use_orderflow_raw) if isinstance(use_orderflow_raw, bool) else str(use_orderflow_raw).strip().lower() not in {"0", "false", "no", "off"}
        strict_raw = body.get("strict_strategy_id", False)
        strict_strategy_id = bool(strict_raw) if isinstance(strict_raw, bool) else str(strict_raw).strip().lower() in {"1", "true", "yes", "on"}
        purge_bars_raw = body.get("purge_bars")
        embargo_bars_raw = body.get("embargo_bars")
        cpcv_n_splits_raw = body.get("cpcv_n_splits")
        cpcv_k_test_groups_raw = body.get("cpcv_k_test_groups")
        cpcv_max_paths_raw = body.get("cpcv_max_paths")

        def _optional_non_negative_int(name: str, value: Any) -> int | None:
            if value is None or value == "":
                return None
            try:
                parsed = int(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"{name} debe ser entero >= 0") from exc
            if parsed < 0:
                raise HTTPException(status_code=400, detail=f"{name} debe ser entero >= 0")
            return parsed

        purge_bars = _optional_non_negative_int("purge_bars", purge_bars_raw)
        embargo_bars = _optional_non_negative_int("embargo_bars", embargo_bars_raw)

        def _optional_min_int(name: str, value: Any, min_value: int) -> int | None:
            if value is None or value == "":
                return None
            try:
                parsed = int(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"{name} debe ser entero >= {min_value}") from exc
            if parsed < min_value:
                raise HTTPException(status_code=400, detail=f"{name} debe ser entero >= {min_value}")
            return parsed

        cpcv_n_splits = _optional_min_int("cpcv_n_splits", cpcv_n_splits_raw, 4)
        cpcv_k_test_groups = _optional_min_int("cpcv_k_test_groups", cpcv_k_test_groups_raw, 1)
        cpcv_max_paths = _optional_min_int("cpcv_max_paths", cpcv_max_paths_raw, 1)

        market = body.get("market")
        symbol = body.get("symbol")
        timeframe = body.get("timeframe")
        bot_id = str(body.get("bot_id") or "").strip() or None
        data_source = str(body.get("data_source") or "auto").lower()
        if data_source in {"synthetic", "synthetic_seeded", "synthetic_fallback"}:
            raise HTTPException(
                status_code=400,
                detail="Quick Backtest ya no permite resultados sintÃ©ticos. ConfigurÃ¡ mercado/sÃ­mbolo/timeframe y asegurÃ¡ dataset real.",
            )
        if market and symbol and timeframe:
            try:
                run = store.create_event_backtest_run(
                    strategy_id=strategy_id,
                    bot_id=bot_id,
                    market=str(market),
                    symbol=str(symbol),
                    timeframe=str(timeframe),
                    start=start,
                    end=end,
                    fees_bps=fees_bps,
                    spread_bps=spread_bps,
                    slippage_bps=slippage_bps,
                    funding_bps=funding_bps,
                    rollover_bps=rollover_bps,
                    validation_mode=validation_mode,
                    use_orderflow_data=use_orderflow_data,
                    strict_strategy_id=strict_strategy_id,
                    purge_bars=purge_bars,
                    embargo_bars=embargo_bars,
                    cpcv_n_splits=cpcv_n_splits,
                    cpcv_k_test_groups=cpcv_k_test_groups,
                    cpcv_max_paths=cpcv_max_paths,
                )
            except FileNotFoundError as exc:
                mk = str(market).strip().lower()
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Faltan datos para {mk}/{str(symbol).upper()}/{str(timeframe).lower()}. "
                        "Cargá un dataset real reproducible en user_data/datasets o user_data/data y reintentá. "
                        f"Detalle: {exc}"
                    ),
                ) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        else:
            raise HTTPException(
                status_code=400,
                detail="Quick Backtest requiere mercado, sÃ­mbolo y timeframe para usar datos reales. No se generan corridas sintÃ©ticas.",
            )
        return {"ok": True, "run_id": run["id"], "run": run}

    @app.get("/api/v1/backtests/runs")
    def backtests_runs(_: dict[str, str] = Depends(current_user)) -> list[dict[str, Any]]:
        return store.load_runs()

    @app.get("/api/v1/backtests/runs/{run_id}")
    def backtests_run_detail(
        run_id: str,
        format: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> Any:
        runs = store.load_runs()
        run = next((row for row in runs if row["id"] == run_id), None)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if format == "trades_csv":
            return Response(
                content=to_csv(run.get("trades", [])),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={run_id}_trades.csv"},
            )
        if format == "equity_curve_csv":
            return Response(
                content=to_csv(run.get("equity_curve", [])),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={run_id}_equity_curve.csv"},
            )
        if format == "report_json":
            return JSONResponse(content=run)
        return run

    def _catalog_run_or_404(run_id: str) -> dict[str, Any]:
        row = store.backtest_catalog.get_run(run_id)
        if row:
            return row
        legacy = store.backtest_catalog.get_run_by_legacy_id(run_id)
        if legacy:
            return legacy
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    def _catalog_compare_payload(run_ids: list[str]) -> dict[str, Any]:
        rows = store.backtest_catalog.compare_runs(run_ids)
        dataset_hashes = sorted({str(r.get("dataset_hash") or "") for r in rows if str(r.get("dataset_hash") or "")})
        feature_sets = sorted(
            {
                str(_infer_orderflow_feature_set(report=r, catalog_row=r)[0] or "")
                for r in rows
                if isinstance(r, dict)
            }
        )
        warnings: list[str] = []
        if len(dataset_hashes) > 1:
            warnings.append("datasets_distintos")
        if len([x for x in feature_sets if x and x != "orderflow_unknown"]) > 1:
            warnings.append("feature_sets_distintos")
        return {
            "items": rows,
            "count": len(rows),
            "warnings": warnings,
            "dataset_hashes": dataset_hashes,
            "feature_sets": feature_sets,
            "same_dataset": len(dataset_hashes) <= 1,
            "same_feature_set": len([x for x in feature_sets if x and x != "orderflow_unknown"]) <= 1,
        }

    def _parse_model_value(raw: Any, default_label: str = "static", *, numeric_default: float = 0.0) -> tuple[str, float]:
        text = str(raw or "").strip()
        if ":" not in text:
            try:
                return (default_label if text else default_label, float(text or numeric_default))
            except Exception:
                return (default_label, float(numeric_default))
        left, right = text.split(":", 1)
        try:
            return (left.strip() or default_label, float(right.strip()))
        except Exception:
            return (left.strip() or default_label, float(numeric_default))

    def _normalize_orderflow_feature_set(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"orderflow_on", "on", "enabled", "true", "1"}:
            return "orderflow_on"
        if text in {"orderflow_off", "off", "disabled", "false", "0", "ohlc_only"}:
            return "orderflow_off"
        return "orderflow_unknown"

    def _infer_orderflow_feature_set(
        *,
        report: dict[str, Any] | None,
        catalog_row: dict[str, Any] | None = None,
        mass_row: dict[str, Any] | None = None,
    ) -> tuple[str, bool, str]:
        payload = report if isinstance(report, dict) else {}
        catalog = catalog_row if isinstance(catalog_row, dict) else {}
        direct = _normalize_orderflow_feature_set(payload.get("orderflow_feature_set") or payload.get("feature_set"))
        if direct != "orderflow_unknown":
            return direct, direct == "orderflow_on", "report_field"

        if isinstance(payload.get("use_orderflow_data"), bool):
            enabled = bool(payload.get("use_orderflow_data"))
            return ("orderflow_on" if enabled else "orderflow_off"), enabled, "report_flag"

        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        md_set = _normalize_orderflow_feature_set(metadata.get("orderflow_feature_set"))
        if md_set != "orderflow_unknown":
            return md_set, md_set == "orderflow_on", "metadata"
        if isinstance(metadata.get("use_orderflow_data"), bool):
            enabled = bool(metadata.get("use_orderflow_data"))
            return ("orderflow_on" if enabled else "orderflow_off"), enabled, "metadata_flag"

        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
        if isinstance(params.get("use_orderflow_data"), bool):
            enabled = bool(params.get("use_orderflow_data"))
            return ("orderflow_on" if enabled else "orderflow_off"), enabled, "params"

        params_json = payload.get("params_json") if isinstance(payload.get("params_json"), dict) else {}
        if not params_json and isinstance(catalog.get("params_json"), dict):
            params_json = catalog.get("params_json") or {}
        if isinstance(params_json.get("use_orderflow_data"), bool):
            enabled = bool(params_json.get("use_orderflow_data"))
            return ("orderflow_on" if enabled else "orderflow_off"), enabled, "params_json"

        flags = payload.get("flags") if isinstance(payload.get("flags"), dict) else {}
        if not flags and isinstance(catalog.get("flags"), dict):
            flags = catalog.get("flags") or {}
        fg_set = _normalize_orderflow_feature_set(flags.get("ORDERFLOW_FEATURE_SET"))
        if fg_set != "orderflow_unknown":
            return fg_set, fg_set == "orderflow_on", "flags"
        if isinstance(flags.get("ORDERFLOW_ENABLED"), bool):
            enabled = bool(flags.get("ORDERFLOW_ENABLED"))
            return ("orderflow_on" if enabled else "orderflow_off"), enabled, "flags_bool"

        tags = payload.get("tags") if isinstance(payload.get("tags"), list) else (
            catalog.get("tags") if isinstance(catalog.get("tags"), list) else []
        )
        tag_values = {str(x).strip().lower() for x in tags if str(x).strip()}
        if "feature_set:orderflow_off" in tag_values:
            return "orderflow_off", False, "tags"
        if "feature_set:orderflow_on" in tag_values:
            return "orderflow_on", True, "tags"

        if isinstance(mass_row, dict):
            micro = mass_row.get("microstructure") if isinstance(mass_row.get("microstructure"), dict) else {}
            policy = micro.get("policy") if isinstance(micro.get("policy"), dict) else {}
            if bool(policy.get("disabled_by_request")):
                return "orderflow_off", False, "mass_micro_policy"
            if isinstance(policy.get("enabled"), bool):
                enabled = bool(policy.get("enabled"))
                return ("orderflow_on" if enabled else "orderflow_off"), enabled, "mass_micro_policy"

        market_name = str(payload.get("market") or catalog.get("market") or "").strip().lower()
        if market_name == "equities":
            return "orderflow_off", False, "market_default_equities"

        # Fail-closed: sin evidencia explicita no se asume ON ni OFF.
        return "orderflow_unknown", False, "missing_fail_closed"

    def _mass_result_row_for_catalog_run(catalog_row: dict[str, Any]) -> dict[str, Any] | None:
        batch_id = str(catalog_row.get("batch_id") or "")
        if not batch_id:
            return None
        artifacts = catalog_row.get("artifacts") if isinstance(catalog_row.get("artifacts"), dict) else {}
        variant_id = str(artifacts.get("variant_id") or "")
        if not variant_id:
            legacy = str(catalog_row.get("legacy_json_id") or "")
            if ":" in legacy:
                variant_id = legacy.split(":", 1)[1]
        if not variant_id:
            return None
        try:
            payload = mass_backtest_coordinator.results(batch_id, limit=5000)
        except Exception:
            return None
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return None
        return next((r for r in rows if isinstance(r, dict) and str(r.get("variant_id") or "") == variant_id), None)

    def _build_rollout_report_from_catalog_row(catalog_row: dict[str, Any]) -> dict[str, Any]:
        # Prefer legacy run payload if exists (richer details and exact costs/trades).
        legacy_id = str(catalog_row.get("legacy_json_id") or "")
        if legacy_id and ":" not in legacy_id:
            try:
                legacy = _find_run_or_404(legacy_id)
                payload = dict(legacy)
                payload["id"] = str(catalog_row.get("run_id") or payload.get("id") or legacy_id)
                payload["catalog_run_id"] = str(catalog_row.get("run_id") or "")
                payload["legacy_json_id"] = legacy_id
                payload["fee_snapshot_id"] = payload.get("fee_snapshot_id") or catalog_row.get("fee_snapshot_id")
                payload["funding_snapshot_id"] = payload.get("funding_snapshot_id") or catalog_row.get("funding_snapshot_id")
                payload["fundamentals_snapshot_id"] = payload.get("fundamentals_snapshot_id") or catalog_row.get("fundamentals_snapshot_id")
                payload["fund_status"] = payload.get("fund_status") or catalog_row.get("fund_status")
                if payload.get("fund_allow_trade") is None and catalog_row.get("fund_allow_trade") is not None:
                    payload["fund_allow_trade"] = bool(catalog_row.get("fund_allow_trade"))
                payload["fund_risk_multiplier"] = payload.get("fund_risk_multiplier") or catalog_row.get("fund_risk_multiplier")
                payload["fund_score"] = payload.get("fund_score") or catalog_row.get("fund_score")
                flags = catalog_row.get("flags") if isinstance(catalog_row.get("flags"), dict) else {}
                if payload.get("fund_promotion_blocked") is None:
                    payload["fund_promotion_blocked"] = bool(flags.get("FUNDAMENTALS_PROMOTION_BLOCKED", False))
                feature_set, orderflow_enabled, feature_source = _infer_orderflow_feature_set(
                    report=payload,
                    catalog_row=catalog_row,
                )
                payload["use_orderflow_data"] = bool(orderflow_enabled)
                payload["orderflow_feature_set"] = feature_set
                payload["feature_set"] = feature_set
                metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                metadata["orderflow_feature_set"] = feature_set
                metadata["use_orderflow_data"] = bool(orderflow_enabled)
                metadata["orderflow_feature_source"] = feature_source
                catalog_params = catalog_row.get("params_json") if isinstance(catalog_row.get("params_json"), dict) else {}
                if payload.get("strict_strategy_id") is None and isinstance(catalog_params.get("strict_strategy_id"), bool):
                    payload["strict_strategy_id"] = bool(catalog_params.get("strict_strategy_id"))
                if isinstance(catalog_params.get("execution_mode"), str) and not payload.get("execution_mode"):
                    payload["execution_mode"] = str(catalog_params.get("execution_mode") or "").strip().lower()
                payload["metadata"] = metadata
                return payload
            except HTTPException:
                pass

        k = catalog_row.get("kpis") if isinstance(catalog_row.get("kpis"), dict) else {}
        flags = catalog_row.get("flags") if isinstance(catalog_row.get("flags"), dict) else {}
        symbols = catalog_row.get("symbols") if isinstance(catalog_row.get("symbols"), list) else []
        timeframes = catalog_row.get("timeframes") if isinstance(catalog_row.get("timeframes"), list) else []
        fee_label, fee_val = _parse_model_value(catalog_row.get("fee_model"), "maker_taker_bps", numeric_default=0.0)
        spread_label, spread_val = _parse_model_value(catalog_row.get("spread_model"), "static", numeric_default=0.0)
        slippage_label, slippage_val = _parse_model_value(catalog_row.get("slippage_model"), "static", numeric_default=0.0)
        funding_label, funding_val = _parse_model_value(catalog_row.get("funding_model"), "static", numeric_default=0.0)

        mass_row = _mass_result_row_for_catalog_run(catalog_row)
        summary = mass_row.get("summary") if isinstance(mass_row, dict) and isinstance(mass_row.get("summary"), dict) else {}
        anti = mass_row.get("anti_overfitting") if isinstance(mass_row, dict) and isinstance(mass_row.get("anti_overfitting"), dict) else {}

        trade_count = int(k.get("trade_count") or k.get("roundtrips") or summary.get("trade_count_oos") or 0)
        winrate = float(k.get("winrate") if k.get("winrate") is not None else summary.get("winrate") or 0.0)
        sharpe = float(k.get("sharpe") if k.get("sharpe") is not None else summary.get("sharpe_oos") or 0.0)
        sortino = float(k.get("sortino") if k.get("sortino") is not None else summary.get("sortino_oos") or 0.0)
        calmar = float(k.get("calmar") if k.get("calmar") is not None else summary.get("calmar_oos") or 0.0)
        max_dd = float(k.get("max_dd") if k.get("max_dd") is not None else (float(summary.get("max_dd_oos_pct") or 0.0) / 100.0))
        expectancy = float(
            (k.get("expectancy_value") if k.get("expectancy_value") is not None else k.get("expectancy"))
            if (k.get("expectancy_value") is not None or k.get("expectancy") is not None)
            else (summary.get("expectancy_net_usd") or 0.0)
        )
        profit_factor = float(k.get("profit_factor") if k.get("profit_factor") is not None else summary.get("profit_factor") or 0.0)
        costs_ratio = float(k.get("costs_ratio") if k.get("costs_ratio") is not None else summary.get("costs_ratio") or 0.0)
        net_pnl = float(k.get("net_pnl") if k.get("net_pnl") is not None else summary.get("net_pnl_oos") or 0.0)

        if net_pnl >= 0:
            gross_pnl = net_pnl / max(1e-9, (1.0 - min(costs_ratio, 0.99))) if costs_ratio < 0.99 else net_pnl
            total_cost = abs(gross_pnl) * max(0.0, costs_ratio)
        else:
            gross_abs = abs(net_pnl) / max(1e-9, (1.0 + max(0.0, costs_ratio)))
            gross_pnl = -gross_abs
            total_cost = gross_abs * max(0.0, costs_ratio)
        if not net_pnl and expectancy and trade_count:
            net_pnl = expectancy * trade_count
        fee_cost = round(total_cost * 0.35, 6)
        spread_cost = round(total_cost * 0.35, 6)
        slippage_cost = round(total_cost * 0.25, 6)
        funding_cost = round(max(0.0, total_cost - fee_cost - spread_cost - slippage_cost), 6)
        validation_mode = "walk-forward" if bool(flags.get("WFA") or flags.get("OOS")) else "batch"
        report = {
            "id": str(catalog_row.get("run_id") or ""),
            "catalog_run_id": str(catalog_row.get("run_id") or ""),
            "legacy_json_id": legacy_id or None,
            "run_type": str(catalog_row.get("run_type") or "single"),
            "batch_id": catalog_row.get("batch_id"),
            "status": str(catalog_row.get("status") or "completed"),
            "created_at": str(catalog_row.get("created_at") or ""),
            "finished_at": str(catalog_row.get("finished_at") or catalog_row.get("created_at") or ""),
            "created_by": str(catalog_row.get("created_by") or "system"),
            "mode": str(catalog_row.get("mode") or "backtest"),
            "strategy_id": str(catalog_row.get("strategy_id") or ""),
            "strategy_name": str(catalog_row.get("strategy_name") or catalog_row.get("strategy_id") or ""),
            "strategy_version": str(catalog_row.get("strategy_version") or "batch"),
            "strategy_config_hash": str(catalog_row.get("strategy_config_hash") or ""),
            "market": str(catalog_row.get("market") or "crypto"),
            "exchange": str(catalog_row.get("exchange") or ""),
            "symbol": str(symbols[0]) if symbols else None,
            "timeframe": str(timeframes[0]) if timeframes else None,
            "period": {
                "start": str(catalog_row.get("timerange_from") or ""),
                "end": str(catalog_row.get("timerange_to") or ""),
            },
            "universe": symbols,
            "validation_mode": validation_mode,
            "validation_summary": {"mode": "walk-forward" if validation_mode == "walk-forward" else "batch", "source": "catalog"},
            "data_source": str(catalog_row.get("dataset_source") or "dataset"),
            "dataset_hash": str(catalog_row.get("dataset_hash") or ""),
            "dataset_version": str(catalog_row.get("dataset_version") or ""),
            "git_commit": str(catalog_row.get("code_commit_hash") or "local"),
            "costs_model": {
                "fees_bps": fee_val,
                "spread_bps": spread_val,
                "slippage_bps": slippage_val,
                "funding_bps": funding_val,
                "fees_model_label": fee_label,
                "spread_model_label": spread_label,
                "slippage_model_label": slippage_label,
                "funding_model_label": funding_label,
            },
            "metrics": {
                "trade_count": trade_count,
                "roundtrips": int(k.get("roundtrips") or trade_count),
                "winrate": winrate,
                "sharpe": sharpe,
                "sortino": sortino,
                "calmar": calmar,
                "max_dd": max_dd,
                "expectancy": expectancy,
                "expectancy_usd_per_trade": expectancy,
                "expectancy_unit": str(k.get("expectancy_unit") or "usd_per_trade"),
                "profit_factor": profit_factor,
                "avg_holding_time": float(k.get("avg_holding_time") or 0.0),
                "time_in_market": float(k.get("time_in_market") or 0.0),
                "pbo": anti.get("pbo", k.get("pbo")),
                "dsr": anti.get("dsr", k.get("dsr")),
                "max_dd_duration_bars": int(k.get("max_dd_duration_bars") or 0),
                "robustness_score": float(k.get("robustness_score") or 0.0),
                "costs_ratio": costs_ratio,
                "net_pnl": net_pnl,
            },
            "costs_breakdown": {
                "gross_pnl_total": round(float(gross_pnl), 6),
                "gross_pnl": round(float(gross_pnl), 6),
                "fees_total": fee_cost,
                "spread_total": spread_cost,
                "slippage_total": slippage_cost,
                "funding_total": funding_cost,
                "total_cost": round(float(total_cost), 6),
                "net_pnl_total": round(float(net_pnl), 6),
                "net_pnl": round(float(net_pnl), 6),
            },
            "flags": flags,
            "kpis_by_regime": catalog_row.get("kpis_by_regime") if isinstance(catalog_row.get("kpis_by_regime"), dict) else {},
            "params_json": catalog_row.get("params_json") if isinstance(catalog_row.get("params_json"), dict) else {},
            "seed": catalog_row.get("seed"),
            "hf_model_id": catalog_row.get("hf_model_id"),
            "hf_revision": catalog_row.get("hf_revision"),
            "hf_commit_hash": catalog_row.get("hf_commit_hash"),
            "pipeline_task": catalog_row.get("pipeline_task"),
            "inference_mode": catalog_row.get("inference_mode"),
            "fee_snapshot_id": catalog_row.get("fee_snapshot_id"),
            "funding_snapshot_id": catalog_row.get("funding_snapshot_id"),
            "fundamentals_snapshot_id": catalog_row.get("fundamentals_snapshot_id"),
            "fund_status": catalog_row.get("fund_status"),
            "fund_allow_trade": catalog_row.get("fund_allow_trade"),
            "fund_risk_multiplier": catalog_row.get("fund_risk_multiplier"),
            "fund_score": catalog_row.get("fund_score"),
            "fund_promotion_blocked": bool(flags.get("FUNDAMENTALS_PROMOTION_BLOCKED", False)),
        }
        params_json = report.get("params_json") if isinstance(report.get("params_json"), dict) else {}
        if isinstance(params_json.get("strict_strategy_id"), bool):
            report["strict_strategy_id"] = bool(params_json.get("strict_strategy_id"))
        if isinstance(params_json.get("execution_mode"), str):
            report["execution_mode"] = str(params_json.get("execution_mode") or "").strip().lower()
        feature_set, orderflow_enabled, feature_source = _infer_orderflow_feature_set(
            report=report,
            catalog_row=catalog_row,
            mass_row=mass_row,
        )
        report["use_orderflow_data"] = bool(orderflow_enabled)
        report["orderflow_feature_set"] = feature_set
        report["feature_set"] = feature_set
        metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
        metadata["orderflow_feature_set"] = feature_set
        metadata["use_orderflow_data"] = bool(orderflow_enabled)
        metadata["orderflow_feature_source"] = feature_source
        if "strict_strategy_id" in report:
            metadata["strict_strategy_id"] = bool(report.get("strict_strategy_id"))
        if report.get("execution_mode"):
            metadata["execution_mode"] = str(report.get("execution_mode") or "")
        report["metadata"] = metadata
        return report

    def _resolve_strategy_from_report_or_catalog(report: dict[str, Any], catalog_row: dict[str, Any] | None = None) -> dict[str, Any]:
        strategy_id = str(report.get("strategy_id") or "")
        if strategy_id and not strategy_id.startswith("ST-"):
            try:
                return store.strategy_or_404(strategy_id)
            except HTTPException:
                pass
        if catalog_row:
            cat_strategy_id = str(catalog_row.get("strategy_id") or "")
            if cat_strategy_id and not cat_strategy_id.startswith("ST-"):
                try:
                    return store.strategy_or_404(cat_strategy_id)
                except HTTPException:
                    pass
        strategy_name = str(report.get("strategy_name") or (catalog_row or {}).get("strategy_name") or "").strip().lower()
        if strategy_name:
            for row in store.list_strategies():
                if str(row.get("name") or "").strip().lower() == strategy_name:
                    return store.strategy_or_404(str(row.get("id") or ""))
        raise HTTPException(status_code=400, detail="No se pudo resolver strategy_id real para el run del catalogo")

    def _resolve_rollout_report_from_any_run_id(run_id: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
        # Legacy runs (runs.json)
        try:
            legacy = _find_run_or_404(run_id)
            payload = dict(legacy)
            feature_set, orderflow_enabled, feature_source = _infer_orderflow_feature_set(report=payload)
            payload["orderflow_feature_set"] = feature_set
            payload["feature_set"] = feature_set
            payload["use_orderflow_data"] = bool(orderflow_enabled)
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            metadata["orderflow_feature_set"] = feature_set
            metadata["use_orderflow_data"] = bool(orderflow_enabled)
            metadata["orderflow_feature_source"] = feature_source
            payload["metadata"] = metadata
            return payload, None
        except HTTPException:
            pass
        catalog_row = _catalog_run_or_404(run_id)
        report = _build_rollout_report_from_catalog_row(catalog_row)
        return report, catalog_row

    def _pick_baseline_rollout_report(candidate_report: dict[str, Any], explicit_run_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any] | None]:
        if explicit_run_id:
            return _resolve_rollout_report_from_any_run_id(explicit_run_id)

        candidate_catalog = store.backtest_catalog.get_run(str(candidate_report.get("id") or ""))
        dataset_hash = str(candidate_report.get("dataset_hash") or "")
        period = candidate_report.get("period") or {}
        candidate_strategy_name = str(candidate_report.get("strategy_name") or "")
        candidate_run_id = str(candidate_report.get("id") or "")
        candidate_feature_set, _, _ = _infer_orderflow_feature_set(
            report=candidate_report,
            catalog_row=candidate_catalog,
        )
        catalog_rows = store.backtest_catalog.list_runs()

        # Prefer same dataset + period and different strategy, completed and not archived.
        for row in catalog_rows:
            if str(row.get("run_id") or "") == candidate_run_id:
                continue
            if str(row.get("status") or "") not in {"completed", "completed_warn"}:
                continue
            flags = row.get("flags") if isinstance(row.get("flags"), dict) else {}
            if bool(flags.get("ARCHIVADO")):
                continue
            if dataset_hash and str(row.get("dataset_hash") or "") != dataset_hash:
                continue
            if period and (
                str(row.get("timerange_from") or "") != str((period.get("start") if isinstance(period, dict) else "")) or
                str(row.get("timerange_to") or "") != str((period.get("end") if isinstance(period, dict) else ""))
            ):
                continue
            if str(row.get("strategy_name") or "") == candidate_strategy_name:
                continue
            row_feature_set, _, _ = _infer_orderflow_feature_set(report=row, catalog_row=row)
            if candidate_feature_set and candidate_feature_set != "orderflow_unknown" and row_feature_set != candidate_feature_set:
                continue
            return _resolve_rollout_report_from_any_run_id(str(row.get("run_id") or ""))

        # Fallback to legacy picker if candidate exists in legacy.
        try:
            legacy_candidate = _find_run_or_404(candidate_run_id)
            baseline = _pick_baseline_run(legacy_candidate, explicit_run_id=None)
            return dict(baseline), None
        except HTTPException:
            pass

        # Last fallback: any completed other catalog run.
        for row in catalog_rows:
            if str(row.get("run_id") or "") == candidate_run_id:
                continue
            if str(row.get("status") or "") in {"completed", "completed_warn"}:
                row_feature_set, _, _ = _infer_orderflow_feature_set(report=row, catalog_row=row)
                if candidate_feature_set and candidate_feature_set != "orderflow_unknown" and row_feature_set != candidate_feature_set:
                    continue
                return _resolve_rollout_report_from_any_run_id(str(row.get("run_id") or ""))
        raise HTTPException(status_code=400, detail="No baseline run available to compare against candidate")

    def _validate_run_for_promotion(
        *,
        candidate_run_id: str,
        baseline_run_id: str | None,
        target_mode: str,
    ) -> dict[str, Any]:
        candidate_report, candidate_catalog = _resolve_rollout_report_from_any_run_id(candidate_run_id)
        baseline_report, baseline_catalog = _pick_baseline_rollout_report(candidate_report, baseline_run_id)
        candidate_strategy = _resolve_strategy_from_report_or_catalog(candidate_report, candidate_catalog)
        baseline_strategy = _resolve_strategy_from_report_or_catalog(baseline_report, baseline_catalog)

        candidate_report = dict(candidate_report)
        baseline_report = dict(baseline_report)
        candidate_report["strategy_id"] = candidate_strategy.get("id")
        candidate_report["strategy_name"] = candidate_strategy.get("name")
        candidate_report["version"] = candidate_strategy.get("version")
        candidate_report["params"] = candidate_strategy.get("params")
        baseline_report["strategy_id"] = baseline_strategy.get("id")
        baseline_report["strategy_name"] = baseline_strategy.get("name")
        baseline_report["version"] = baseline_strategy.get("version")
        baseline_report["params"] = baseline_strategy.get("params")

        gates_result = rollout_gates.evaluate(candidate_report)
        candidate_feature_set, candidate_orderflow_enabled, candidate_feature_source = _infer_orderflow_feature_set(
            report=candidate_report,
            catalog_row=candidate_catalog,
        )
        baseline_feature_set, baseline_orderflow_enabled, baseline_feature_source = _infer_orderflow_feature_set(
            report=baseline_report,
            catalog_row=baseline_catalog,
        )
        candidate_report["orderflow_feature_set"] = candidate_feature_set
        candidate_report["feature_set"] = candidate_feature_set
        candidate_report["use_orderflow_data"] = bool(candidate_orderflow_enabled)
        baseline_report["orderflow_feature_set"] = baseline_feature_set
        baseline_report["feature_set"] = baseline_feature_set
        baseline_report["use_orderflow_data"] = bool(baseline_orderflow_enabled)
        compare_thresholds = ((store.load_settings().get("rollout") or {}).get("improve_vs_baseline") or {})
        compare_engine = CompareEngine(compare_thresholds if isinstance(compare_thresholds, dict) else {})
        compare_result = compare_engine.compare(baseline_report, candidate_report)
        same_feature_set = candidate_feature_set == baseline_feature_set
        known_feature_set = candidate_feature_set != "orderflow_unknown" and baseline_feature_set != "orderflow_unknown"
        candidate_provenance = candidate_report.get("provenance") if isinstance(candidate_report.get("provenance"), dict) else {}
        candidate_metadata = candidate_report.get("metadata") if isinstance(candidate_report.get("metadata"), dict) else {}
        candidate_params = candidate_report.get("params_json") if isinstance(candidate_report.get("params_json"), dict) else {}
        candidate_catalog_params = candidate_catalog.get("params_json") if isinstance((candidate_catalog or {}).get("params_json"), dict) else {}
        candidate_execution_mode = str(
            candidate_report.get("execution_mode")
            or candidate_metadata.get("execution_mode")
            or candidate_params.get("execution_mode")
            or candidate_catalog_params.get("execution_mode")
            or candidate_report.get("mode")
            or "research"
        ).strip().lower()
        strict_strategy_id = False
        strict_source = "missing"
        for source, raw in [
            ("report.strict_strategy_id", candidate_report.get("strict_strategy_id")),
            ("report.provenance.strict_strategy_id", candidate_provenance.get("strict_strategy_id")),
            ("report.metadata.strict_strategy_id", candidate_metadata.get("strict_strategy_id")),
            ("report.params_json.strict_strategy_id", candidate_params.get("strict_strategy_id")),
            ("catalog.params_json.strict_strategy_id", candidate_catalog_params.get("strict_strategy_id")),
        ]:
            if isinstance(raw, bool):
                strict_strategy_id = bool(raw)
                strict_source = source
                break
        strict_required = candidate_execution_mode != "demo"

        k = candidate_report.get("metrics") if isinstance(candidate_report.get("metrics"), dict) else {}
        flags = (candidate_catalog or {}).get("flags") if isinstance((candidate_catalog or {}).get("flags"), dict) else (candidate_report.get("flags") if isinstance(candidate_report.get("flags"), dict) else {})
        trade_count = int(k.get("trade_count") or k.get("roundtrips") or 0)
        costs = candidate_report.get("costs_breakdown") if isinstance(candidate_report.get("costs_breakdown"), dict) else {}
        gross_abs = abs(float(costs.get("gross_pnl_total") or 0.0))
        total_cost = float(costs.get("total_cost") or 0.0)
        costs_ratio = (total_cost / gross_abs) if gross_abs > 0 else 0.0

        thresholds = gates_result.get("thresholds") if isinstance(gates_result.get("thresholds"), dict) else {}
        min_trades_req = int(float(thresholds.get("min_trades_oos") or 0))
        costs_ratio_max = float(thresholds.get("costs_ratio_max") or 1.0)
        fee_snapshot_id = candidate_report.get("fee_snapshot_id")
        funding_snapshot_id = candidate_report.get("funding_snapshot_id")
        fund_status = str(candidate_report.get("fund_status") or "")
        fund_allow_trade_raw = candidate_report.get("fund_allow_trade")
        fund_promotion_blocked = bool(candidate_report.get("fund_promotion_blocked", False))
        fund_warnings = candidate_report.get("fund_warnings") if isinstance(candidate_report.get("fund_warnings"), list) else []
        if not fund_promotion_blocked:
            fund_promotion_blocked = bool(flags.get("FUNDAMENTALS_PROMOTION_BLOCKED"))
        if fund_allow_trade_raw is None and isinstance(candidate_catalog, dict):
            fund_allow_trade_raw = candidate_catalog.get("fund_allow_trade")
            fund_status = fund_status or str(candidate_catalog.get("fund_status") or "")
            fee_snapshot_id = fee_snapshot_id or candidate_catalog.get("fee_snapshot_id")
            funding_snapshot_id = funding_snapshot_id or candidate_catalog.get("funding_snapshot_id")
        has_catalog_provenance = isinstance(candidate_catalog, dict)
        snapshots_ok = (not has_catalog_provenance) or (bool(str(fee_snapshot_id or "")) and bool(str(funding_snapshot_id or "")))
        fundamentals_ok = bool(fund_allow_trade_raw) if fund_allow_trade_raw is not None else (not has_catalog_provenance)
        constraints_checks = [
            {"id": "run_status_completed", "ok": str(candidate_report.get("status") or "").lower() in {"completed", "completed_warn"}, "reason": "Run debe estar completado", "details": {"status": candidate_report.get("status")}},
            {"id": "min_trades", "ok": trade_count >= max(1, min_trades_req), "reason": "Trades mÃ­nimos", "details": {"actual": trade_count, "threshold": max(1, min_trades_req)}},
            {"id": "realistic_costs", "ok": costs_ratio <= costs_ratio_max, "reason": "Costos realistas (costs_ratio)", "details": {"actual": round(costs_ratio, 6), "threshold": costs_ratio_max}},
            {"id": "oos_or_wfa", "ok": bool(flags.get("OOS") or flags.get("WFA")), "reason": "Debe tener evidencia OOS/WFA", "details": {"flags": flags}},
            {
                "id": "known_feature_set",
                "ok": known_feature_set,
                "reason": "Baseline y candidato deben declarar feature set de order flow explicito",
                "details": {
                    "candidate_feature_set": candidate_feature_set,
                    "baseline_feature_set": baseline_feature_set,
                    "candidate_source": candidate_feature_source,
                    "baseline_source": baseline_feature_source,
                },
            },
            {
                "id": "same_feature_set",
                "ok": same_feature_set,
                "reason": "Baseline y candidato deben tener mismo feature set de order flow",
                "details": {
                    "candidate_feature_set": candidate_feature_set,
                    "baseline_feature_set": baseline_feature_set,
                    "candidate_source": candidate_feature_source,
                    "baseline_source": baseline_feature_source,
                },
            },
            {
                "id": "strict_strategy_id_non_demo",
                "ok": (not strict_required) or strict_strategy_id,
                "reason": "strict_strategy_id=true es obligatorio en promotion no-demo",
                "details": {
                    "strict_required": strict_required,
                    "strict_strategy_id": strict_strategy_id,
                    "source": strict_source,
                    "execution_mode": candidate_execution_mode,
                },
            },
            {
                "id": "cost_snapshots_present",
                "ok": snapshots_ok,
                "reason": "Run debe tener fee_snapshot_id y funding_snapshot_id",
                "details": {
                    "fee_snapshot_id": fee_snapshot_id,
                    "funding_snapshot_id": funding_snapshot_id,
                    "catalog_run": has_catalog_provenance,
                },
            },
            {
                "id": "fundamentals_allow_trade",
                "ok": fundamentals_ok,
                "reason": "Fundamentals debe permitir trade para promocion",
                "details": {
                    "fund_allow_trade": fund_allow_trade_raw,
                    "fund_status": fund_status or None,
                    "catalog_run": has_catalog_provenance,
                },
            },
            {
                "id": "fundamentals_promotion_not_blocked",
                "ok": not fund_promotion_blocked,
                "reason": "Fundamentals no debe estar bloqueado para promocion",
                "details": {
                    "fund_promotion_blocked": fund_promotion_blocked,
                    "fund_warnings": fund_warnings,
                    "catalog_run": has_catalog_provenance,
                },
            },
        ]
        constraints_ok = all(bool(row["ok"]) for row in constraints_checks)
        promotion_ok = bool(constraints_ok and gates_result.get("passed") and compare_result.get("passed"))
        live_direct_ok = False

        return {
            "ok": True,
            "promotion_ok": promotion_ok,
            "live_direct_ok": live_direct_ok,
            "requires_human_approval": True,
            "option_b_no_auto_live": True,
            "target_mode": str(target_mode or "paper"),
            "candidate": {
                "run_id": str(candidate_report.get("id") or candidate_run_id),
                "catalog_run_id": str((candidate_catalog or {}).get("run_id") or candidate_report.get("id") or ""),
                "legacy_json_id": candidate_report.get("legacy_json_id"),
                "strategy_id": candidate_strategy.get("id"),
                "strategy_name": candidate_strategy.get("name"),
                "dataset_hash": candidate_report.get("dataset_hash"),
                "period": candidate_report.get("period"),
                "status": candidate_report.get("status"),
                "orderflow_feature_set": candidate_feature_set,
                "use_orderflow_data": bool(candidate_orderflow_enabled),
                "strict_strategy_id": bool(strict_strategy_id),
                "execution_mode": candidate_execution_mode,
            },
            "baseline": {
                "run_id": str(baseline_report.get("id") or ""),
                "catalog_run_id": str((baseline_catalog or {}).get("run_id") or baseline_report.get("id") or ""),
                "legacy_json_id": baseline_report.get("legacy_json_id"),
                "strategy_id": baseline_strategy.get("id"),
                "strategy_name": baseline_strategy.get("name"),
                "dataset_hash": baseline_report.get("dataset_hash"),
                "period": baseline_report.get("period"),
                "status": baseline_report.get("status"),
                "orderflow_feature_set": baseline_feature_set,
                "use_orderflow_data": bool(baseline_orderflow_enabled),
            },
            "constraints": {
                "passed": constraints_ok,
                "checks": constraints_checks,
            },
            "offline_gates": gates_result,
            "compare_vs_baseline": compare_result,
            "rollout_ready": promotion_ok,
            "allowed_targets": {
                "paper": bool(promotion_ok),
                "testnet": bool(promotion_ok),
                "live": False,
            },
            "rollout_start_body": {
                "candidate_run_id": str(candidate_report.get("id") or candidate_run_id),
                "baseline_run_id": str(baseline_report.get("id") or ""),
            },
            "_resolved": {
                "candidate_report": candidate_report,
                "baseline_report": baseline_report,
                "candidate_strategy": candidate_strategy,
                "baseline_strategy": baseline_strategy,
                "candidate_catalog": candidate_catalog,
                "baseline_catalog": baseline_catalog,
            },
        }

    @app.get("/api/v1/runs")
    def runs_list(
        q: str | None = Query(default=None),
        run_type: str | None = Query(default=None),
        status: str | None = Query(default=None),
        strategy_id: str | None = Query(default=None),
        bot_id: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        timeframe: str | None = Query(default=None),
        mode: str | None = Query(default=None),
        date_from: str | None = Query(default=None),
        date_to: str | None = Query(default=None),
        min_trades: int | None = Query(default=None, ge=0),
        max_dd: float | None = Query(default=None, ge=0.0),
        sharpe: float | None = Query(default=None),
        flags: str | None = Query(default=None, description="Flags separados por coma. Ej: OOS,PASO_GATES"),
        sort_by: str = Query(default="created_at"),
        sort_dir: Literal["asc", "desc"] = Query(default="desc"),
        limit: int = Query(default=200, ge=1, le=2000),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        flags_any = [x.strip().upper() for x in str(flags or "").split(",") if x.strip()]
        raw_items = store.backtest_catalog.query_runs(
            q=q,
            run_type=run_type,
            status=status,
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            mode=mode,
            date_from=date_from,
            date_to=date_to,
            min_trades=min_trades,
            max_dd_lte=max_dd,
            sharpe_gte=sharpe,
            flags_any=flags_any,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=max(int(limit), 50000) if str(bot_id or "").strip() else limit,
        )
        items = store.annotate_runs_with_related_bots(raw_items, bot_id=bot_id)
        limited_items = items[: max(1, int(limit))]
        return {"items": limited_items, "count": len(items)}

    @app.get("/api/v1/runs/{run_id}")
    def runs_detail(run_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        row = _catalog_run_or_404(run_id)
        annotated_rows = store.annotate_runs_with_related_bots([row])
        if annotated_rows:
            row = annotated_rows[0]
        row["artifacts_index"] = store.backtest_catalog.get_artifacts_for_run(str(row.get("run_id") or ""))
        legacy_id = str(row.get("legacy_json_id") or "")
        if legacy_id:
            row["legacy_backtest_api"] = {
                "detail": f"/api/v1/backtests/runs/{legacy_id}",
                "report_json": f"/api/v1/backtests/runs/{legacy_id}?format=report_json",
                "trades_csv": f"/api/v1/backtests/runs/{legacy_id}?format=trades_csv",
                "equity_curve_csv": f"/api/v1/backtests/runs/{legacy_id}?format=equity_curve_csv",
            }
        return row

    @app.patch("/api/v1/runs/{run_id}")
    def runs_patch(run_id: str, body: RunsPatchBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        resolved = _catalog_run_or_404(run_id)
        patched = store.backtest_catalog.patch_run(
            str(resolved.get("run_id") or run_id),
            alias=body.alias,
            tags=body.tags,
            pinned=body.pinned,
            archived=body.archived,
        )
        if not patched:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        store.add_log(
            event_type="run_patched",
            severity="info",
            module="backtest",
            message="Run metadata actualizado",
            related_ids=[str(patched.get("run_id") or run_id)],
            payload={"alias": body.alias, "tags": body.tags, "pinned": body.pinned, "archived": body.archived},
        )
        return {"ok": True, "run": patched}

    @app.post("/api/v1/runs/bulk")
    def runs_bulk(body: RunsBulkBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        raw_ids = body.run_ids if isinstance(body.run_ids, list) else []
        run_ids: list[str] = []
        seen: set[str] = set()
        for raw in raw_ids:
            rid = str(raw or "").strip()
            if not rid or rid in seen:
                continue
            seen.add(rid)
            run_ids.append(rid)
        if not run_ids:
            raise HTTPException(status_code=400, detail="Debe enviar al menos un run_id.")

        action = str(body.action or "").strip().lower()
        affected: list[dict[str, Any]] = []
        deleted_payload: dict[str, Any] | None = None

        if action in {"archive", "unarchive"}:
            archived = action == "archive"
            for rid in run_ids:
                patched = store.backtest_catalog.patch_run(rid, archived=archived)
                if patched:
                    affected.append(patched)
            if not affected:
                raise HTTPException(status_code=404, detail="Ninguno de los runs enviados existe en el catÃ¡logo.")
            store.add_log(
                event_type="runs_bulk_patch",
                severity="info",
                module="backtest",
                message=f"Accion masiva sobre runs: {action}",
                related_ids=[str(row.get("run_id") or "") for row in affected][:20],
                payload={"action": action, "count": len(affected)},
            )
            return {"ok": True, "action": action, "count": len(affected), "runs": affected}

        if action == "delete":
            deleted_payload = store.delete_catalog_runs(run_ids)
            count = int((deleted_payload or {}).get("deleted_count") or 0)
            if count <= 0:
                raise HTTPException(status_code=404, detail="Ninguno de los runs enviados existe en el catÃ¡logo.")
            store.add_log(
                event_type="runs_bulk_delete",
                severity="warn",
                module="backtest",
                message="Borrado masivo de runs del catÃ¡logo",
                related_ids=[str(x) for x in ((deleted_payload or {}).get("deleted_run_ids") or [])][:20],
                payload=deleted_payload or {},
            )
            return {"ok": True, "action": action, **(deleted_payload or {})}

        raise HTTPException(status_code=400, detail=f"AcciÃ³n no soportada: {body.action}")

    @app.get("/api/v1/batches")
    def batches_list(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        items = store.backtest_catalog.list_batches()
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/batches/{batch_id}")
    def batches_detail(batch_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        batch = store.backtest_catalog.get_batch(batch_id)
        status_payload = mass_backtest_coordinator.status(batch_id)
        if not batch and str(status_payload.get("state") or "") == "NOT_FOUND":
            raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")
        if not batch:
            batch = {
                "batch_id": batch_id,
                "objective": "Research Batch",
                "status": str(status_payload.get("state") or "queued").lower(),
                "created_at": str(status_payload.get("created_at") or ""),
                "updated_at": str(status_payload.get("updated_at") or ""),
                "universe": {},
                "variables_explored": {},
                "run_count_total": 0,
                "run_count_done": 0,
                "run_count_failed": 0,
                "best_runs_cache": [],
                "config": status_payload.get("config") or {},
                "summary": status_payload.get("summary") or {},
            }
        batch["children_runs"] = store.backtest_catalog.batch_children_runs(batch_id)
        batch["artifacts_index"] = store.backtest_catalog.get_artifacts_for_batch(batch_id)
        batch["runtime_status"] = status_payload
        return batch

    @app.post("/api/v1/batches/{batch_id}/shortlist")
    def batches_save_shortlist(batch_id: str, body: BatchShortlistBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        batch = store.backtest_catalog.get_batch(batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

        def _to_float(value: Any) -> float:
            try:
                return float(value or 0.0)
            except Exception:
                return 0.0

        raw_items = body.items if isinstance(body.items, list) else []
        shortlist: list[dict[str, Any]] = []
        for raw in raw_items[:2000]:
            if not isinstance(raw, dict):
                continue
            variant_id = str(raw.get("variant_id") or "").strip()
            run_id = str(raw.get("run_id") or raw.get("catalog_run_id") or "").strip()
            if not variant_id and not run_id:
                continue
            item: dict[str, Any] = {
                "variant_id": variant_id or None,
                "run_id": run_id or None,
                "strategy_id": str(raw.get("strategy_id") or "").strip() or None,
                "strategy_name": str(raw.get("strategy_name") or "").strip() or None,
                "score": _to_float(raw.get("score")),
                "winrate_oos": _to_float(raw.get("winrate_oos")),
                "sharpe_oos": _to_float(raw.get("sharpe_oos")),
                "costs_ratio": _to_float(raw.get("costs_ratio")),
                "saved_at": utc_now_iso(),
            }
            shortlist.append(item)

        patched = store.backtest_catalog.patch_batch(
            batch_id,
            best_runs_cache=shortlist,
            summary={
                **(batch.get("summary") if isinstance(batch.get("summary"), dict) else {}),
                "shortlist_saved_at": utc_now_iso(),
                "shortlist_saved_by": user.get("username", "admin"),
                "shortlist_source": str(body.source or "ui_mass_shortlist"),
                "shortlist_note": str(body.note or "").strip(),
                "shortlist_count": len(shortlist),
            },
        )
        if not patched:
            raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

        store.add_log(
            event_type="batch_shortlist_saved",
            severity="info",
            module="backtest",
            message="Shortlist del batch guardada",
            related_ids=[batch_id],
            payload={"batch_id": batch_id, "count": len(shortlist), "source": str(body.source or "ui_mass_shortlist")},
        )
        return {"ok": True, "batch_id": batch_id, "saved_count": len(shortlist), "batch": patched}

    @app.get("/api/v1/compare")
    def compare_runs(
        r: list[str] = Query(default=[]),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        if not r:
            raise HTTPException(status_code=400, detail="Debe enviar al menos un run_id (?r=BT-...)")
        return _catalog_compare_payload(r)

    @app.get("/api/v1/rankings")
    def rankings(
        preset: str = Query(default="balanceado"),
        min_trades: int | None = Query(default=None, ge=0),
        max_dd: float | None = Query(default=None, ge=0.0),
        sharpe: float | None = Query(default=None),
        oos_pass: bool | None = Query(default=None),
        data_quality: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=1000),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        constraints: dict[str, Any] = {}
        if min_trades is not None:
            constraints["min_trades"] = min_trades
        if max_dd is not None:
            constraints["max_dd"] = max_dd
        if sharpe is not None:
            constraints["sharpe"] = sharpe
        if oos_pass is not None:
            constraints["oos_pass"] = bool(oos_pass)
        if data_quality:
            constraints["data_quality"] = data_quality
        result = store.backtest_catalog.rankings(preset=preset, constraints=constraints, limit=limit)
        # filtro extra opcional (flags OOS / data warning) en capa API
        if oos_pass is not None or data_quality:
            items = []
            for row in result.get("items", []):
                flags_payload = row.get("flags") if isinstance(row.get("flags"), dict) else {}
                if oos_pass is True and not bool(flags_payload.get("OOS") or flags_payload.get("WFA")):
                    continue
                if oos_pass is False and bool(flags_payload.get("OOS") or flags_payload.get("WFA")):
                    continue
                if data_quality == "ok" and bool(flags_payload.get("DATA_WARNING")):
                    continue
                items.append(row)
            result["items"] = items[:limit]
            result["total"] = len(items)
        return result

    @app.post("/api/v1/runs/{run_id}/validate_promotion")
    def runs_validate_promotion(run_id: str, body: RunPromoteBody | None = None, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        payload = _validate_run_for_promotion(
            candidate_run_id=run_id,
            baseline_run_id=(body.baseline_run_id if body else None),
            target_mode=(body.target_mode if body else "paper"),
        )
        # No exponer payloads internos completos por API.
        payload.pop("_resolved", None)
        return payload

    @app.post("/api/v1/runs/{run_id}/promote")
    def runs_promote_to_rollout(run_id: str, body: RunPromoteBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        validation = _validate_run_for_promotion(
            candidate_run_id=run_id,
            baseline_run_id=body.baseline_run_id,
            target_mode=body.target_mode,
        )
        resolved = validation.get("_resolved") if isinstance(validation.get("_resolved"), dict) else {}
        candidate_report = resolved.get("candidate_report") if isinstance(resolved.get("candidate_report"), dict) else None
        baseline_report = resolved.get("baseline_report") if isinstance(resolved.get("baseline_report"), dict) else None
        candidate_strategy = resolved.get("candidate_strategy") if isinstance(resolved.get("candidate_strategy"), dict) else None
        baseline_strategy = resolved.get("baseline_strategy") if isinstance(resolved.get("baseline_strategy"), dict) else None
        candidate_catalog = resolved.get("candidate_catalog") if isinstance(resolved.get("candidate_catalog"), dict) else None
        baseline_catalog = resolved.get("baseline_catalog") if isinstance(resolved.get("baseline_catalog"), dict) else None
        if not validation.get("rollout_ready") or not candidate_report or not baseline_report or not candidate_strategy or not baseline_strategy:
            sanitized = dict(validation)
            sanitized.pop("_resolved", None)
            return JSONResponse(status_code=400, content={**sanitized, "ok": False, "detail": "Run no elegible para promover a rollout (gates/constraints/compare)."})

        state = rollout_manager.start_offline(
            baseline_run=baseline_report,
            candidate_run=candidate_report,
            baseline_strategy=baseline_strategy,
            candidate_strategy=candidate_strategy,
            gates_result=validation.get("offline_gates") if isinstance(validation.get("offline_gates"), dict) else {},
            compare_result=validation.get("compare_vs_baseline") if isinstance(validation.get("compare_vs_baseline"), dict) else {},
            actor=user.get("username", "admin"),
        )

        # Reflejar validacion/gates en el catalogo (sin tocar runtimes LIVE).
        try:
            cand_catalog_id = str(((validation.get("candidate") or {}).get("catalog_run_id")) or (candidate_catalog or {}).get("run_id") or "")
            base_catalog_id = str(((validation.get("baseline") or {}).get("catalog_run_id")) or (baseline_catalog or {}).get("run_id") or "")
            if cand_catalog_id:
                store.backtest_catalog.patch_run_flags(
                    cand_catalog_id,
                    {
                        "PASO_GATES": bool((validation.get("offline_gates") or {}).get("passed")),
                        "FAVORITO": True,
                    },
                )
            if base_catalog_id:
                store.backtest_catalog.patch_run_flags(base_catalog_id, {"BASELINE": True})
        except Exception:
            pass

        store.add_log(
            event_type="run_promoted_to_rollout",
            severity="info",
            module="rollout",
            message="Run promovido a rollout (OpciÃ³n B, sin auto-live)",
            related_ids=[str(candidate_report.get("id") or run_id), str(baseline_report.get("id") or "")],
            payload={
                "target_mode": body.target_mode,
                "note": body.note or "",
                "rollout_state": state.get("state"),
                "requires_approve": True,
                "no_auto_live": True,
            },
        )

        out = dict(validation)
        out.pop("_resolved", None)
        out.update(
            {
                "ok": True,
                "promoted": True,
                "note": body.note or "",
                "rollout": {
                    "state": state,
                    "next_step": "Ir a Settings -> Rollout / Gates para paper/testnet soak, canary y approve manual",
                },
            }
        )
        return out

    def _collect_trades_with_run_meta() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for run in store.load_runs():
            if not isinstance(run, dict):
                continue
            run_id = str(run.get("catalog_run_id") or run.get("id") or "")
            run_mode = str(run.get("mode") or "backtest")
            run_created_at = str(run.get("created_at") or "")
            for trade in run.get("trades", []):
                if not isinstance(trade, dict):
                    continue
                row = dict(trade)
                row.setdefault("run_id", run_id)
                row.setdefault("run_mode", run_mode)
                row.setdefault("run_created_at", run_created_at)
                rows.append(row)
        return rows

    def _trade_matches_filters(
        row: dict[str, Any],
        *,
        strategy_id: str | None = None,
        symbol: str | None = None,
        side: str | None = None,
        reason_code: str | None = None,
        exit_reason: str | None = None,
        result: str | None = None,
        mode: str | None = None,
        environment: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> bool:
        if strategy_id and row.get("strategy_id") != strategy_id:
            return False
        if symbol and row.get("symbol") != symbol:
            return False
        if side and row.get("side") != side:
            return False
        if reason_code and row.get("reason_code") != reason_code:
            return False
        if exit_reason and row.get("exit_reason") != exit_reason:
            return False
        run_mode = str(row.get("run_mode") or "").lower()
        if mode and run_mode != str(mode).lower():
            return False
        if environment:
            env = str(environment).strip().lower()
            if env == "real" and run_mode != "live":
                return False
            if env in {"test", "prueba"} and run_mode == "live":
                return False
        if result:
            pnl_net = float(row.get("pnl_net") or 0.0)
            r = str(result).lower()
            if r == "win" and pnl_net <= 0:
                return False
            if r == "loss" and pnl_net >= 0:
                return False
            if r == "breakeven" and abs(pnl_net) > 1e-9:
                return False
        entry_time = str(row.get("entry_time") or "")
        if date_from and entry_time < date_from:
            return False
        if date_to and entry_time > date_to:
            return False
        return True

    def _trade_bucket(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        wins = 0
        losses = 0
        breakeven = 0
        net_pnl = 0.0
        gross_pnl = 0.0
        fees_total = 0.0
        slippage_total = 0.0
        holding_sum_min = 0.0
        for row in rows:
            pnl_net = float(row.get("pnl_net") or 0.0)
            if pnl_net > 0:
                wins += 1
            elif pnl_net < 0:
                losses += 1
            else:
                breakeven += 1
            net_pnl += pnl_net
            gross_pnl += float(row.get("pnl") or 0.0)
            fees_total += float(row.get("fees") or 0.0)
            slippage_total += float(row.get("slippage") or 0.0)
            try:
                entry_ts = datetime.fromisoformat(str(row.get("entry_time") or "").replace("Z", "+00:00"))
                exit_ts = datetime.fromisoformat(str(row.get("exit_time") or "").replace("Z", "+00:00"))
                holding_sum_min += abs((exit_ts - entry_ts).total_seconds()) / 60.0
            except Exception:
                pass
        winrate = (wins / total) if total else 0.0
        return {
            "trades": total,
            "wins": wins,
            "losses": losses,
            "breakeven": breakeven,
            "winrate": winrate,
            "net_pnl": net_pnl,
            "gross_pnl": gross_pnl,
            "fees_total": fees_total,
            "slippage_total": slippage_total,
            "avg_trade": (net_pnl / total) if total else 0.0,
            "avg_holding_minutes": (holding_sum_min / total) if total else 0.0,
        }

    @app.get("/api/v1/trades")
    def trades(
        strategy_id: str | None = None,
        symbol: str | None = None,
        side: str | None = None,
        reason_code: str | None = None,
        exit_reason: str | None = None,
        result: str | None = None,
        mode: str | None = None,
        environment: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = Query(default=1000, ge=1, le=5000),
        _: dict[str, str] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        rows = [
            row
            for row in _collect_trades_with_run_meta()
            if _trade_matches_filters(
                row,
                strategy_id=strategy_id,
                symbol=symbol,
                side=side,
                reason_code=reason_code,
                exit_reason=exit_reason,
                result=result,
                mode=mode,
                environment=environment,
                date_from=date_from,
                date_to=date_to,
            )
        ]
        rows.sort(key=lambda row: row.get("entry_time", ""), reverse=True)
        return rows[:limit]

    @app.get("/api/v1/trades/summary")
    def trades_summary(
        strategy_id: str | None = None,
        symbol: str | None = None,
        side: str | None = None,
        reason_code: str | None = None,
        exit_reason: str | None = None,
        result: str | None = None,
        mode: str | None = None,
        environment: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        rows = [
            row
            for row in _collect_trades_with_run_meta()
            if _trade_matches_filters(
                row,
                strategy_id=strategy_id,
                symbol=symbol,
                side=side,
                reason_code=reason_code,
                exit_reason=exit_reason,
                result=result,
                mode=mode,
                environment=environment,
                date_from=date_from,
                date_to=date_to,
            )
        ]
        strategy_name_map = {str(row.get("id") or ""): str(row.get("name") or row.get("id") or "") for row in store.list_strategies()}
        by_environment: dict[str, list[dict[str, Any]]] = {"real": [], "prueba": []}
        by_mode: dict[str, list[dict[str, Any]]] = {}
        by_strategy: dict[str, list[dict[str, Any]]] = {}
        by_day: dict[str, list[dict[str, Any]]] = {}
        by_strategy_day: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            run_mode = str(row.get("run_mode") or "backtest").lower()
            env_key = "real" if run_mode == "live" else "prueba"
            by_environment.setdefault(env_key, []).append(row)
            by_mode.setdefault(run_mode, []).append(row)
            strategy_key = str(row.get("strategy_id") or "-")
            by_strategy.setdefault(strategy_key, []).append(row)
            day_key = str(row.get("entry_time") or "")[:10]
            if not day_key:
                day_key = "sin_fecha"
            by_day.setdefault(day_key, []).append(row)
            by_strategy_day.setdefault((strategy_key, day_key, env_key), []).append(row)

        by_environment_rows = [
            {"environment": key, **_trade_bucket(group)}
            for key, group in by_environment.items()
            if group
        ]
        by_mode_rows = [
            {"mode": key, "environment": ("real" if key == "live" else "prueba"), **_trade_bucket(group)}
            for key, group in by_mode.items()
        ]
        by_strategy_rows = [
            {
                "strategy_id": key,
                "strategy_name": strategy_name_map.get(key) or key,
                **_trade_bucket(group),
            }
            for key, group in by_strategy.items()
        ]
        by_day_rows = [
            {"day": key, **_trade_bucket(group)}
            for key, group in by_day.items()
        ]
        by_strategy_day_rows = [
            {
                "strategy_id": strategy_id_key,
                "strategy_name": strategy_name_map.get(strategy_id_key) or strategy_id_key,
                "day": day_key,
                "environment": env_key,
                **_trade_bucket(group),
            }
            for (strategy_id_key, day_key, env_key), group in by_strategy_day.items()
        ]
        by_mode_rows.sort(key=lambda row: (row.get("environment", ""), row.get("mode", "")))
        by_strategy_rows.sort(key=lambda row: (float(row.get("net_pnl") or 0.0), float(row.get("winrate") or 0.0), int(row.get("trades") or 0)), reverse=True)
        by_day_rows.sort(key=lambda row: str(row.get("day") or ""), reverse=True)
        by_strategy_day_rows.sort(
            key=lambda row: (str(row.get("day") or ""), float(row.get("net_pnl") or 0.0), int(row.get("trades") or 0)),
            reverse=True,
        )
        return {
            "totals": _trade_bucket(rows),
            "by_environment": by_environment_rows,
            "by_mode": by_mode_rows,
            "by_strategy": by_strategy_rows[:200],
            "by_day": by_day_rows[:180],
            "by_strategy_day": by_strategy_day_rows[:500],
            "filters": {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "side": side,
                "reason_code": reason_code,
                "exit_reason": exit_reason,
                "result": result,
                "mode": mode,
                "environment": environment,
                "date_from": date_from,
                "date_to": date_to,
            },
        }

    @app.post("/api/v1/trades/bulk-delete")
    def trades_bulk_delete(body: TradesBulkDeleteBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        requested_ids = {str(v).strip() for v in (body.ids or []) if str(v).strip()}
        deleted_ids: list[str] = []
        affected_runs: set[str] = set()
        before_count = 0
        after_count = 0
        new_runs: list[dict[str, Any]] = []
        for run in store.load_runs():
            if not isinstance(run, dict):
                new_runs.append(run)
                continue
            trades_rows = run.get("trades", [])
            if not isinstance(trades_rows, list):
                new_runs.append(run)
                continue
            before_count += len(trades_rows)
            kept: list[dict[str, Any]] = []
            run_id = str(run.get("catalog_run_id") or run.get("id") or "")
            run_mode = str(run.get("mode") or "backtest")
            for trade in trades_rows:
                if not isinstance(trade, dict):
                    kept.append(trade)
                    continue
                candidate = dict(trade)
                candidate.setdefault("run_id", run_id)
                candidate.setdefault("run_mode", run_mode)
                match = False
                if requested_ids:
                    match = str(candidate.get("id") or "").strip() in requested_ids
                else:
                    match = _trade_matches_filters(
                        candidate,
                        strategy_id=body.strategy_id,
                        symbol=body.symbol,
                        side=body.side,
                        reason_code=body.reason_code,
                        exit_reason=body.exit_reason,
                        result=body.result,
                        mode=body.mode,
                        environment=body.environment,
                        date_from=body.date_from,
                        date_to=body.date_to,
                    )
                if match:
                    deleted_ids.append(str(candidate.get("id") or ""))
                    affected_runs.add(run_id)
                    continue
                kept.append(trade)
            run["trades"] = kept
            after_count += len(kept)
            new_runs.append(run)

        if not body.dry_run and deleted_ids:
            store.save_runs(new_runs)
        store.add_log(
            event_type="trades_bulk_delete",
            severity="warn",
            module="trades",
            message=f"Trades bulk delete by {user.get('username', 'admin')}: {len(deleted_ids)} rows ({'dry-run' if body.dry_run else 'saved'}).",
            related_ids=[rid for rid in list(affected_runs)[:20]],
            payload={
                "deleted_count": len(deleted_ids),
                "affected_runs": sorted(list(affected_runs))[:50],
                "dry_run": bool(body.dry_run),
            },
        )
        return {
            "ok": True,
            "deleted_count": len(deleted_ids),
            "deleted_trade_ids": [tid for tid in deleted_ids[:200]],
            "affected_run_ids": sorted(list(affected_runs)),
            "before_count": before_count,
            "after_count": after_count if not body.dry_run else before_count - len(deleted_ids),
            "dry_run": bool(body.dry_run),
        }

    @app.get("/api/v1/trades/{trade_id}")
    def trade_detail(trade_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        trade = store.find_trade(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        return trade

    @app.get("/api/v1/positions")
    def positions(_: dict[str, str] = Depends(current_user)) -> list[dict[str, Any]]:
        status = build_status_payload()
        return status["positions"]

    @app.get("/api/v1/portfolio")
    def portfolio(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        status = build_status_payload()
        positions = status["positions"]
        exposure_total = sum(abs(pos["qty"] * pos["mark_px"]) for pos in positions) if positions else 0.0
        exposure_by_symbol = [{"symbol": pos["symbol"], "exposure": abs(pos["qty"] * pos["mark_px"])} for pos in positions]
        runs = store.load_runs()
        history = [{"time": row["time"], "equity": row["equity"]} for row in (runs[0]["equity_curve"] if runs else [])]
        return {
            "equity": status["equity"],
            "exposure_total": exposure_total,
            "exposure_by_symbol": exposure_by_symbol,
            "pnl_daily": status["pnl"]["daily"],
            "pnl_weekly": status["pnl"]["weekly"],
            "pnl_monthly": status["pnl"]["monthly"],
            "open_positions": positions,
            "history": history,
            "corr_matrix": {"BTC/USDT": {"BTC/USDT": 1.0, "ETH/USDT": 0.68}, "ETH/USDT": {"BTC/USDT": 0.68, "ETH/USDT": 1.0}},
        }

    @app.get("/api/v1/risk")
    def risk(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        status = build_status_payload()
        settings = store.load_settings()
        state = _sync_runtime_state(store.load_bot_state(), settings=settings, persist=True)
        runtime_snapshot = _runtime_contract_snapshot(state)
        telemetry_guard = _runtime_telemetry_guard(runtime_snapshot)
        gates_payload = evaluate_gates(status["mode"], runtime_state=state)
        checklist = [{"stage": row["id"], "done": row["status"] == "PASS", "note": row["reason"]} for row in gates_payload["gates"]]
        payload = runtime_bridge.risk_snapshot(state=state, settings=settings, gate_checklist=checklist)
        payload["equity"] = float(status["equity"])
        payload["dd"] = float(status["max_dd"]["value"])
        payload["daily_loss"] = float(status["daily_loss"]["value"])
        payload["runtime_telemetry_source"] = str(runtime_snapshot.get("telemetry_source") or RUNTIME_TELEMETRY_SOURCE_SYNTHETIC)
        payload["runtime_telemetry_fail_closed"] = bool(telemetry_guard.get("fail_closed", True))
        payload["runtime_telemetry_reason"] = str(telemetry_guard.get("reason") or "")
        return payload

    @app.get("/api/v1/execution/metrics")
    def execution_metrics(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return build_execution_metrics_payload()

    @app.get("/api/v1/settings")
    def settings(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        current = store.load_settings()
        merged = learning_service.ensure_settings_shape(current)
        store.save_settings(merged)
        return merged

    @app.get("/api/v1/config/learning")
    def config_learning(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return build_learning_config_payload(store.load_settings())

    @app.get("/api/v1/config/policies")
    def config_policies(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return load_numeric_policies_bundle()

    @app.put("/api/v1/settings")
    async def settings_update(request: Request, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        body = await request.json()
        current = store.load_settings()
        merged = {
            **current,
            **body,
            "credentials": {**current.get("credentials", {}), **body.get("credentials", {})},
            "telegram": {**current.get("telegram", {}), **body.get("telegram", {})},
            "risk_defaults": {**current.get("risk_defaults", {}), **body.get("risk_defaults", {})},
            "execution": {**current.get("execution", {}), **body.get("execution", {})},
            "feature_flags": {**current.get("feature_flags", {}), **body.get("feature_flags", {})},
            "learning": {
                **(current.get("learning", {}) if isinstance(current.get("learning"), dict) else {}),
                **(body.get("learning", {}) if isinstance(body.get("learning"), dict) else {}),
            },
            "rollout": {
                **(current.get("rollout", {}) if isinstance(current.get("rollout"), dict) else {}),
                **(body.get("rollout", {}) if isinstance(body.get("rollout"), dict) else {}),
            },
            "blending": {
                **(current.get("blending", {}) if isinstance(current.get("blending"), dict) else {}),
                **(body.get("blending", {}) if isinstance(body.get("blending"), dict) else {}),
            },
        }
        if isinstance(merged.get("learning"), dict):
            current_learning = current.get("learning", {}) if isinstance(current.get("learning"), dict) else {}
            body_learning = body.get("learning", {}) if isinstance(body.get("learning"), dict) else {}
            merged["learning"] = {
                **current_learning,
                **body_learning,
                "validation": {**(current_learning.get("validation", {}) if isinstance(current_learning.get("validation"), dict) else {}), **(body_learning.get("validation", {}) if isinstance(body_learning.get("validation"), dict) else {})},
                "promotion": {**(current_learning.get("promotion", {}) if isinstance(current_learning.get("promotion"), dict) else {}), **(body_learning.get("promotion", {}) if isinstance(body_learning.get("promotion"), dict) else {})},
                "risk_profile": {**(current_learning.get("risk_profile", {}) if isinstance(current_learning.get("risk_profile"), dict) else {}), **(body_learning.get("risk_profile", {}) if isinstance(body_learning.get("risk_profile"), dict) else {})},
            }
        if isinstance(merged.get("rollout"), dict):
            current_rollout = current.get("rollout", {}) if isinstance(current.get("rollout"), dict) else {}
            body_rollout = body.get("rollout", {}) if isinstance(body.get("rollout"), dict) else {}
            merged["rollout"] = {
                **current_rollout,
                **body_rollout,
                "abort_thresholds": {**(current_rollout.get("abort_thresholds", {}) if isinstance(current_rollout.get("abort_thresholds"), dict) else {}), **(body_rollout.get("abort_thresholds", {}) if isinstance(body_rollout.get("abort_thresholds"), dict) else {})},
                "improve_vs_baseline": {**(current_rollout.get("improve_vs_baseline", {}) if isinstance(current_rollout.get("improve_vs_baseline"), dict) else {}), **(body_rollout.get("improve_vs_baseline", {}) if isinstance(body_rollout.get("improve_vs_baseline"), dict) else {})},
                "phases": body_rollout.get("phases") if isinstance(body_rollout.get("phases"), list) else current_rollout.get("phases"),
            }
        if isinstance(merged.get("learning"), dict):
            engine_id = str(merged["learning"].get("engine_id") or "").strip()
            if engine_id:
                merged["learning"]["selector_algo"] = _engine_id_to_selector_algo(engine_id)
        merged = learning_service.ensure_settings_shape(merged)
        store.save_settings(merged)
        store.add_log(
            event_type="settings_changed",
            severity="info",
            module="settings",
            message="Settings updated by admin",
            related_ids=[],
            payload={"mode": merged.get("mode"), "exchange": merged.get("exchange")},
        )
        return {"ok": True, "settings": merged}

    @app.post("/api/v1/settings/test-alert")
    def settings_test_alert(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        log_id = store.add_log(
            event_type="health",
            severity="info",
            module="telegram",
            message="Telegram test alert requested",
            related_ids=[],
            payload={"chat_id": store.load_settings().get("telegram", {}).get("chat_id")},
        )
        return {"ok": True, "id": f"log_{log_id}"}

    @app.post("/api/v1/settings/test-exchange")
    def settings_test_exchange(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        payload = diagnose_exchange(force_refresh=True)
        if not payload.get("ok"):
            raise HTTPException(status_code=400, detail=payload.get("last_error") or "Exchange connector no listo")
        return payload

    @app.get("/api/v1/exchange/diagnose")
    def exchange_diagnose(
        mode: str | None = None,
        force: bool = Query(default=False),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        selected_mode = (mode or store.load_bot_state().get("mode") or default_mode()).lower()
        if selected_mode not in ALLOWED_MODES:
            raise HTTPException(status_code=400, detail=f"Invalid mode: {selected_mode}")
        payload = diagnose_exchange(selected_mode, force_refresh=force)
        return payload

    @app.get("/api/v1/diagnostics/breaker-events")
    def diagnostics_breaker_events(
        window_hours: int = Query(default=BREAKER_EVENTS_INTEGRITY_WINDOW_HOURS, ge=1, le=168),
        strict: bool = Query(default=True),
        _: dict[str, str] = Depends(current_user),
    ) -> dict[str, Any]:
        return store.breaker_events_integrity(window_hours=window_hours, strict=bool(strict))

    @app.post("/api/v1/bot/mode")
    def bot_mode(body: BotModeBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        mode = body.mode
        if mode == "live":
            runtime_engine = _runtime_engine_from_state(store.load_bot_state())
            if runtime_engine != RUNTIME_ENGINE_REAL:
                raise HTTPException(
                    status_code=400,
                    detail="LIVE bloqueado: runtime simulado. Configura RUNTIME_ENGINE=real antes de habilitar LIVE.",
                )
            if body.confirm != "ENABLE_LIVE":
                raise HTTPException(status_code=400, detail="Missing explicit confirmation for LIVE")
            gates_payload = evaluate_gates("live")
            allowed, reason = live_can_be_enabled(gates_payload)
            if not allowed:
                raise HTTPException(status_code=400, detail=f"LIVE blocked by gates: {reason}")
        state = store.load_bot_state()
        state["mode"] = mode
        state["runtime_engine"] = _runtime_engine_from_state(state)
        state["bot_status"] = "PAUSED"
        state["running"] = False
        store.save_bot_state(state)
        state = _sync_runtime_state(state, settings=store.load_settings(), event="mode_change", persist=True)
        store.add_log(
            event_type="mode_changed",
            severity="warn" if mode == "live" else "info",
            module="control",
            message=f"Bot mode set to {mode}",
            related_ids=[],
            payload={"mode": mode},
        )
        return {"ok": True, "mode": mode}

    def _do_bot_start(bot_id: str | None = None) -> dict[str, Any]:
        state = store.load_bot_state()
        state["runtime_engine"] = _runtime_engine_from_state(state)
        # Resolve strategy: prefer bot pool if bot_id provided, fallback to principal.
        strategy_name: str | None = None
        active_bot_id = str(bot_id or "").strip() or None
        if active_bot_id:
            bots = store.load_bots()
            bot_row = next((b for b in bots if str(b.get("id") or "") == active_bot_id), None)
            if bot_row:
                pool = bot_row.get("pool_strategy_ids") or []
                if pool:
                    strategy_name = str(pool[0])
        if not strategy_name:
            principal = store.registry.get_principal(state["mode"])
            if not principal:
                raise HTTPException(status_code=400, detail=f"No principals configured for mode {state['mode']}")
            strategy_name = str(principal["name"])
            active_bot_id = None
        if active_bot_id:
            state["active_bot_id"] = active_bot_id
        state["running"] = True
        state["killed"] = False
        state["bot_status"] = "RUNNING"
        store.save_bot_state(state)
        state = _sync_runtime_state(state, settings=store.load_settings(), event="start", persist=True)
        store.add_log(
            event_type="status",
            severity="info",
            module="control",
            message=f"Bot started in {state['mode']}",
            related_ids=[x for x in [strategy_name, active_bot_id] if x],
            payload={"mode": state["mode"], "strategy": strategy_name, "bot_id": active_bot_id},
        )
        return {"ok": True, "state": state["bot_status"], "mode": state["mode"], "strategy": strategy_name, "bot_id": active_bot_id}

    @app.post("/api/v1/bot/start")
    def bot_start(body: BotStartBody | None = None, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        return _do_bot_start(bot_id=(body.bot_id if body else None))

    @app.post("/api/v1/bot/stop")
    def bot_stop(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        state = store.load_bot_state()
        state["running"] = False
        state["bot_status"] = "PAUSED"
        store.save_bot_state(state)
        _sync_runtime_state(state, settings=store.load_settings(), event="stop", persist=True)
        store.add_log(
            event_type="status",
            severity="warn",
            module="control",
            message="Bot stopped by admin",
            related_ids=[],
            payload={},
        )
        return {"ok": True, "state": state["bot_status"]}

    @app.post("/api/v1/bot/killswitch")
    def bot_killswitch(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        state = store.load_bot_state()
        state["running"] = False
        state["killed"] = True
        state["safe_mode"] = True
        state["bot_status"] = "KILLED"
        store.save_bot_state(state)
        _sync_runtime_state(state, settings=store.load_settings(), event="kill", persist=True)
        store.add_log(
            event_type="breaker_triggered",
            severity="error",
            module="risk",
            message="Kill switch executed by admin",
            related_ids=[],
            payload={"close_positions": True, "cancel_orders": True, "mode": str(state.get("mode") or "paper")},
        )
        return {"ok": True, "state": state["bot_status"]}

    @app.get("/api/v1/status")
    def status(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return build_status_payload()

    @app.get("/api/v1/bot/status")
    def status_alias(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return build_status_payload()

    @app.post("/api/v1/control/pause")
    def control_pause(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        state = store.load_bot_state()
        state["running"] = False
        state["bot_status"] = "PAUSED"
        store.save_bot_state(state)
        _sync_runtime_state(state, settings=store.load_settings(), event="stop", persist=True)
        return {"ok": True, "state": state["bot_status"]}

    @app.post("/api/v1/control/resume")
    def control_resume(body: BotStartBody | None = None, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        return _do_bot_start(bot_id=(body.bot_id if body else None))

    @app.post("/api/v1/control/safe-mode")
    async def control_safe_mode(request: Request, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        body = await request.json()
        enabled = bool(body.get("enabled", True))
        state = store.load_bot_state()
        state["safe_mode"] = enabled
        state["bot_status"] = "SAFE_MODE" if enabled else ("RUNNING" if state.get("running") else "PAUSED")
        store.save_bot_state(state)
        _sync_runtime_state(state, settings=store.load_settings(), event="safe_mode", persist=True)
        return {"ok": True, "safe_mode": enabled}

    @app.post("/api/v1/control/kill")
    def control_kill(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        return bot_killswitch(_)

    @app.post("/api/v1/control/close-all")
    def control_close_all(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        store.add_log(
            event_type="order_update",
            severity="warn",
            module="execution",
            message="Close all positions requested",
            related_ids=[],
            payload={},
        )
        return {"ok": True}

    @app.get("/api/v1/alerts")
    def alerts(
        severity: str | None = None,
        module: str | None = None,
        since: str | None = None,
        until: str | None = None,
        include_operational: bool = Query(default=True),
        _: dict[str, str] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        payload = store.list_logs(severity=severity, module=module, since=since, until=until, page=1, page_size=250)
        rows = []
        for item in payload["items"]:
            if item["severity"] in {"warn", "error"} or item["type"] in {"breaker_triggered", "api_error", "backtest_finished"}:
                rows.append(
                    {
                        "id": f"alt_{item['numeric_id']}",
                        "ts": item["ts"],
                        "type": item["type"],
                        "severity": item["severity"],
                        "module": item["module"],
                        "message": item["message"],
                        "related_id": item["related_ids"][0] if item["related_ids"] else "",
                        "data": item["payload"],
                    }
                )
        if include_operational:
            ops_payload = build_operational_alerts_payload()
            ops_alerts = ops_payload.get("alerts") if isinstance(ops_payload.get("alerts"), list) else []
            rows.extend([row for row in ops_alerts if isinstance(row, dict)])
        rows.sort(key=lambda row: str(row.get("ts") or ""), reverse=True)
        return rows

    @app.get("/api/v1/logs")
    def logs(
        severity: str | None = None,
        module: str | None = None,
        since: str | None = None,
        until: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=100, ge=1, le=500),
        format: str | None = Query(default=None),
        _: dict[str, str] = Depends(current_user),
    ) -> Any:
        payload = store.list_logs(severity=severity, module=module, since=since, until=until, page=page, page_size=page_size)
        if format == "json":
            return Response(
                content=json.dumps(payload["items"], indent=2),
                media_type="application/json",
                headers={"Content-Disposition": f"attachment; filename=logs_{utc_now().date().isoformat()}.json"},
            )
        if format == "csv":
            csv_rows = [{k: v for k, v in row.items() if k != "numeric_id"} for row in payload["items"]]
            return Response(
                content=to_csv(csv_rows),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=logs_{utc_now().date().isoformat()}.csv"},
            )
        return payload

    @app.get("/api/v1/stream")
    async def stream(_: dict[str, str] = Depends(current_user)) -> StreamingResponse:
        async def event_iter() -> Any:
            last_id = 0
            while True:
                status_payload = build_status_payload()
                gates_payload = evaluate_gates(status_payload["mode"])
                yield f"event: status\\ndata: {json.dumps(status_payload)}\\n\\n"
                risk_payload = {
                    "mode": status_payload["mode"],
                    "safe_mode": status_payload["risk_flags"]["safe_mode"],
                    "max_dd": status_payload["max_dd"],
                    "daily_loss": status_payload["daily_loss"],
                }
                yield f"event: risk\\ndata: {json.dumps(risk_payload)}\\n\\n"
                yield f"event: gates\\ndata: {json.dumps(gates_payload)}\\n\\n"
                latest_trade = None
                runs = store.load_runs()
                if runs:
                    trades_rows = runs[0].get("trades", [])
                    if trades_rows:
                        latest_trade = trades_rows[0]
                if latest_trade:
                    yield f"event: trades\\ndata: {json.dumps(latest_trade)}\\n\\n"
                    fill_event = {
                        "id": f"fill_{latest_trade['id']}",
                        "ts": utc_now_iso(),
                        "symbol": latest_trade.get("symbol"),
                        "side": latest_trade.get("side"),
                        "qty": latest_trade.get("qty"),
                        "price": latest_trade.get("entry_px"),
                        "strategy_id": latest_trade.get("strategy_id"),
                    }
                    yield f"event: fills\\ndata: {json.dumps(fill_event)}\\n\\n"
                logs_rows = store.logs_since(last_id)
                for row in logs_rows:
                    last_id = max(last_id, int(row["numeric_id"]))
                    yield f"event: logs\\ndata: {json.dumps(row)}\\n\\n"
                await asyncio.sleep(2)

        return StreamingResponse(event_iter(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "Connection": "keep-alive"})

    return app


app = create_app()


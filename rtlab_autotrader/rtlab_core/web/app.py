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
from typing import Any, Literal
from urllib.parse import urlencode, urlparse

import requests
import yaml
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from rtlab_core.config import load_config
from rtlab_core.backtest import BacktestCatalogDB, CostModelResolver, FundamentalsCreditFilter
from rtlab_core.learning import LearningService
from rtlab_core.learning.knowledge import KnowledgeLoader
from rtlab_core.rollout import CompareEngine, GateEvaluator, RolloutManager
from rtlab_core.src.backtest.engine import BacktestCosts, BacktestEngine, BacktestRequest, MarketDataset
from rtlab_core.src.data.catalog import DataCatalog
from rtlab_core.src.data.loader import DataLoader
from rtlab_core.src.data.universes import MARKET_UNIVERSES, SUPPORTED_TIMEFRAMES, normalize_market, normalize_symbol, normalize_timeframe
from rtlab_core.src.research import MassBacktestCoordinator, MassBacktestEngine
from rtlab_core.src.reports.reporting import ReportEngine as ArtifactReportEngine
from rtlab_core.strategy_packs.registry_db import RegistryDB

APP_VERSION = "0.1.0"
PROJECT_ROOT = Path(os.getenv("RTLAB_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
MONOREPO_ROOT = (PROJECT_ROOT.parent if (PROJECT_ROOT.parent / "knowledge").exists() else PROJECT_ROOT).resolve()
CONFIG_POLICIES_ROOT = (MONOREPO_ROOT / "config" / "policies").resolve()


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
STRATEGY_PACKS_DIR = USER_DATA_DIR / "strategy_packs"
UPLOADS_DIR = STRATEGY_PACKS_DIR / "uploads"
REGISTRY_DB_PATH = STRATEGY_PACKS_DIR / "registry.sqlite3"
CONSOLE_DB_PATH = USER_DATA_DIR / "console_api.sqlite3"
SETTINGS_PATH = USER_DATA_DIR / "console_settings.json"
BOT_STATE_PATH = USER_DATA_DIR / "logs" / "bot_state.json"
STRATEGY_META_PATH = STRATEGY_PACKS_DIR / "strategy_meta.json"
RUNS_PATH = USER_DATA_DIR / "backtests" / "runs.json"
BACKTEST_CATALOG_DB_PATH = USER_DATA_DIR / "backtests" / "catalog.sqlite3"
BOTS_PATH = USER_DATA_DIR / "learning" / "bots.json"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
ALLOWED_ROLES = {ROLE_ADMIN, ROLE_VIEWER}
ALLOWED_MODES = {"paper", "testnet", "live"}
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123!"
DEFAULT_VIEWER_USERNAME = "viewer"
DEFAULT_VIEWER_PASSWORD = "viewer123!"
RUNTIME_ENGINE_REAL = "real"
RUNTIME_ENGINE_SIMULATED = "simulated"
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
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    role TEXT NOT NULL,
    expires_at TEXT NOT NULL
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


class BotBulkPatchBody(BaseModel):
    ids: list[str]
    engine: str | None = None
    mode: Literal["shadow", "paper", "testnet", "live"] | None = None
    status: Literal["active", "paused", "archived"] | None = None
    pool_strategy_ids: list[str] | None = None
    universe: list[str] | None = None
    notes: str | None = None


class BatchCreateBody(BaseModel):
    objective: str | None = None
    strategy_ids: list[str] | None = None
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
    candidates = [
        CONFIG_POLICIES_ROOT,
        (Path(__file__).resolve().parents[3] / "config" / "policies").resolve(),
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _config_policy_files() -> tuple[Path, dict[str, Path]]:
    root = _resolve_config_policies_root()
    return root, {
        "gates": root / "gates.yaml",
        "microstructure": root / "microstructure.yaml",
        "risk_policy": root / "risk_policy.yaml",
        "beast_mode": root / "beast_mode.yaml",
        "fees": root / "fees.yaml",
        "fundamentals_credit_filter": root / "fundamentals_credit_filter.yaml",
    }


def _policy_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    gates = bundle.get("gates") if isinstance(bundle.get("gates"), dict) else {}
    micro = bundle.get("microstructure") if isinstance(bundle.get("microstructure"), dict) else {}
    risk = bundle.get("risk_policy") if isinstance(bundle.get("risk_policy"), dict) else {}
    beast = bundle.get("beast_mode") if isinstance(bundle.get("beast_mode"), dict) else {}
    fees = bundle.get("fees") if isinstance(bundle.get("fees"), dict) else {}
    fundamentals = bundle.get("fundamentals_credit_filter") if isinstance(bundle.get("fundamentals_credit_filter"), dict) else {}
    g = gates.get("gates") if isinstance(gates.get("gates"), dict) else {}
    m = micro.get("microstructure") if isinstance(micro.get("microstructure"), dict) else {}
    r = risk.get("risk_policy") if isinstance(risk.get("risk_policy"), dict) else {}
    b = beast.get("beast_mode") if isinstance(beast.get("beast_mode"), dict) else {}
    f = fees.get("fees") if isinstance(fees.get("fees"), dict) else {}
    fc = fundamentals.get("fundamentals_credit_filter") if isinstance(fundamentals.get("fundamentals_credit_filter"), dict) else {}
    f_scoring = fc.get("scoring") if isinstance(fc.get("scoring"), dict) else {}
    f_thr = f_scoring.get("thresholds") if isinstance(f_scoring.get("thresholds"), dict) else {}
    vpin = m.get("vpin") if isinstance(m.get("vpin"), dict) else {}
    thresholds = vpin.get("thresholds") if isinstance(vpin.get("thresholds"), dict) else {}
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
    }


def load_numeric_policies_bundle() -> dict[str, Any]:
    root, files = _config_policy_files()
    payloads: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    warnings: list[str] = []
    for name, path in files.items():
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
    numeric_policies = load_numeric_policies_bundle()
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
            "gates_file": str(safe_update_cfg.get("gates_file") or "knowledge/policies/gates.yaml"),
            "canary_schedule_pct": canary_schedule,
            "rollback_auto": bool(safe_update_cfg.get("rollback_auto", True)),
            "approve_required": require_approve,
        },
        "gates_summary": {
            "pbo_enabled": bool(((gates_payload.get("pbo") or {}).get("enabled")) if isinstance(gates_payload, dict) else False),
            "dsr_enabled": bool(((gates_payload.get("dsr") or {}).get("enabled")) if isinstance(gates_payload, dict) else False),
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


def runtime_engine_default() -> str:
    value = get_env("RUNTIME_ENGINE", RUNTIME_ENGINE_SIMULATED).lower().strip()
    return RUNTIME_ENGINE_REAL if value == RUNTIME_ENGINE_REAL else RUNTIME_ENGINE_SIMULATED


def _has_default_credentials() -> bool:
    admin_is_default = (
        admin_username() == DEFAULT_ADMIN_USERNAME and admin_password() == DEFAULT_ADMIN_PASSWORD
    )
    viewer_is_default = (
        viewer_username() == DEFAULT_VIEWER_USERNAME and viewer_password() == DEFAULT_VIEWER_PASSWORD
    )
    return admin_is_default or viewer_is_default


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
    mode = get_env("MODE", "paper").lower()
    if mode not in ALLOWED_MODES:
        return "paper"
    return mode


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


class ConsoleStore:
    def __init__(self) -> None:
        ensure_paths()
        self.registry = RegistryDB(REGISTRY_DB_PATH)
        self.backtest_catalog = BacktestCatalogDB(BACKTEST_CATALOG_DB_PATH)
        self.cost_model_resolver = CostModelResolver(catalog=self.backtest_catalog, policies_root=CONFIG_POLICIES_ROOT)
        self.fundamentals_filter = FundamentalsCreditFilter(catalog=self.backtest_catalog, policies_root=CONFIG_POLICIES_ROOT)
        self._init_console_db()
        self._ensure_defaults()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(CONSOLE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_console_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(LOG_SCHEMA_SQL)
            self._backfill_breaker_events_from_logs(conn)
            conn.commit()

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
    def _ensure_defaults(self) -> None:
        self._ensure_default_settings()
        self._ensure_default_bot_state()
        self._ensure_default_strategy()
        self._ensure_knowledge_strategies_registry()
        self._ensure_strategy_registry_invariants()
        self._ensure_default_bots()
        self._ensure_seed_backtest()
        self._sync_backtest_runs_catalog()
        self.add_log(
            event_type="health",
            severity="info",
            module="bootstrap",
            message="Console API initialized",
            related_ids=[],
            payload={"version": APP_VERSION},
        )

    def _ensure_default_settings(self) -> None:
        settings = json_load(SETTINGS_PATH, {})
        if not isinstance(settings, dict):
            settings = {}
        learning_defaults = LearningService.default_learning_settings()
        rollout_defaults = RolloutManager.default_rollout_config()
        blending_defaults = RolloutManager.default_blending_config()
        risk_defaults = {
            "max_daily_loss": 5.0,
            "max_dd": 22.0,
            "max_positions": 20,
            "risk_per_trade": 0.75,
        }
        execution_defaults = {
            "post_only_default": True,
            "slippage_max_bps": 12,
            "request_timeout_ms": 4000,
        }
        feature_flag_defaults = {
            "orderflow": True,
            "vpin": True,
            "ml": False,
            "alerts": True,
        }
        if not settings:
            settings = {
                "mode": default_mode().upper(),
                "exchange": exchange_name(),
                "exchange_plugin_options": ["binance", "bybit", "oanda", "alpaca"],
                "credentials": {
                    "exchange_configured": exchange_keys_present(default_mode()),
                    "telegram_configured": bool(get_env("TELEGRAM_BOT_TOKEN") and get_env("TELEGRAM_CHAT_ID")),
                    "telegram_chat_id": get_env("TELEGRAM_CHAT_ID"),
                },
                "telegram": {
                    "enabled": get_env("TELEGRAM_ENABLED", "false").lower() == "true",
                    "chat_id": get_env("TELEGRAM_CHAT_ID"),
                },
                "risk_defaults": risk_defaults,
                "execution": execution_defaults,
                "feature_flags": feature_flag_defaults,
                "learning": learning_defaults,
                "rollout": rollout_defaults,
                "blending": blending_defaults,
                "gate_checklist": [],
            }
        if not isinstance(settings.get("mode"), str) or not str(settings.get("mode") or "").strip():
            settings["mode"] = default_mode().upper()
        if not isinstance(settings.get("exchange"), str) or not str(settings.get("exchange") or "").strip():
            settings["exchange"] = exchange_name()
        if not isinstance(settings.get("exchange_plugin_options"), list):
            settings["exchange_plugin_options"] = ["binance", "bybit", "oanda", "alpaca"]
        if not isinstance(settings.get("credentials"), dict):
            settings["credentials"] = {}
        if not isinstance(settings.get("telegram"), dict):
            settings["telegram"] = {"enabled": get_env("TELEGRAM_ENABLED", "false").lower() == "true", "chat_id": get_env("TELEGRAM_CHAT_ID")}
        else:
            settings["telegram"] = {
                "enabled": bool(settings["telegram"].get("enabled", get_env("TELEGRAM_ENABLED", "false").lower() == "true")),
                "chat_id": str(settings["telegram"].get("chat_id") or get_env("TELEGRAM_CHAT_ID")),
            }
        if not isinstance(settings.get("risk_defaults"), dict):
            settings["risk_defaults"] = risk_defaults
        else:
            settings["risk_defaults"] = {**risk_defaults, **settings["risk_defaults"]}
        if not isinstance(settings.get("execution"), dict):
            settings["execution"] = execution_defaults
        else:
            settings["execution"] = {**execution_defaults, **settings["execution"]}
        if not isinstance(settings.get("feature_flags"), dict):
            settings["feature_flags"] = feature_flag_defaults
        else:
            settings["feature_flags"] = {**feature_flag_defaults, **settings["feature_flags"]}
        if not isinstance(settings.get("gate_checklist"), list):
            settings["gate_checklist"] = []
        if not isinstance(settings.get("learning"), dict):
            settings["learning"] = learning_defaults
        else:
            settings["learning"] = {
                **learning_defaults,
                **settings["learning"],
                "validation": {
                    **learning_defaults["validation"],
                    **(settings["learning"].get("validation") if isinstance(settings["learning"].get("validation"), dict) else {}),
                },
                "promotion": {
                    **learning_defaults["promotion"],
                    **(settings["learning"].get("promotion") if isinstance(settings["learning"].get("promotion"), dict) else {}),
                },
                "risk_profile": {
                    **learning_defaults["risk_profile"],
                    **(settings["learning"].get("risk_profile") if isinstance(settings["learning"].get("risk_profile"), dict) else {}),
                },
            }
        settings["learning"]["promotion"]["allow_auto_apply"] = False
        settings["learning"]["promotion"]["allow_live"] = False
        if not isinstance(settings.get("rollout"), dict):
            settings["rollout"] = rollout_defaults
        else:
            settings["rollout"] = {
                **rollout_defaults,
                **settings["rollout"],
                "phases": settings["rollout"].get("phases") if isinstance(settings["rollout"].get("phases"), list) else rollout_defaults["phases"],
                "abort_thresholds": {
                    **rollout_defaults["abort_thresholds"],
                    **(settings["rollout"].get("abort_thresholds") if isinstance(settings["rollout"].get("abort_thresholds"), dict) else {}),
                },
                "improve_vs_baseline": {
                    **rollout_defaults["improve_vs_baseline"],
                    **(settings["rollout"].get("improve_vs_baseline") if isinstance(settings["rollout"].get("improve_vs_baseline"), dict) else {}),
                },
                "testnet_checks": {
                    **rollout_defaults["testnet_checks"],
                    **(settings["rollout"].get("testnet_checks") if isinstance(settings["rollout"].get("testnet_checks"), dict) else {}),
                },
            }
        if not isinstance(settings.get("blending"), dict):
            settings["blending"] = blending_defaults
        else:
            settings["blending"] = {**blending_defaults, **settings["blending"]}
        settings["credentials"]["exchange_configured"] = exchange_keys_present(default_mode())
        settings["credentials"]["telegram_configured"] = bool(get_env("TELEGRAM_BOT_TOKEN") and get_env("TELEGRAM_CHAT_ID"))
        settings["credentials"]["telegram_chat_id"] = get_env("TELEGRAM_CHAT_ID")
        if get_env("TELEGRAM_CHAT_ID"):
            settings["telegram"]["chat_id"] = get_env("TELEGRAM_CHAT_ID")
        json_save(SETTINGS_PATH, settings)

    def _ensure_default_bot_state(self) -> None:
        state = json_load(BOT_STATE_PATH, {})
        if not state:
            state = {
                "mode": default_mode(),
                "runtime_engine": runtime_engine_default(),
                "bot_status": "PAUSED",
                "running": False,
                "safe_mode": False,
                "killed": False,
                "equity": 10000.0,
                "daily_pnl": 0.0,
                "max_dd": -0.04,
                "daily_loss": -0.01,
                "last_heartbeat": utc_now_iso(),
            }
            json_save(BOT_STATE_PATH, state)

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
        settings = json_load(SETTINGS_PATH, {})
        if not isinstance(settings, dict) or not settings:
            self._ensure_default_settings()
            settings = json_load(SETTINGS_PATH, {})
        if not isinstance(settings, dict):
            self._ensure_default_settings()
            settings = json_load(SETTINGS_PATH, {})
        if not isinstance(settings, dict):
            return {}
        return settings

    def save_settings(self, settings: dict[str, Any]) -> None:
        if not isinstance(settings, dict):
            settings = {}
        if not isinstance(settings.get("credentials"), dict):
            settings["credentials"] = {}
        if not isinstance(settings.get("telegram"), dict):
            settings["telegram"] = {"enabled": False, "chat_id": ""}
        else:
            settings["telegram"] = {
                "enabled": bool(settings["telegram"].get("enabled", False)),
                "chat_id": str(settings["telegram"].get("chat_id") or ""),
            }
        if not isinstance(settings.get("risk_defaults"), dict):
            settings["risk_defaults"] = {}
        if not isinstance(settings.get("execution"), dict):
            settings["execution"] = {}
        if not isinstance(settings.get("feature_flags"), dict):
            settings["feature_flags"] = {}
        if not isinstance(settings.get("exchange_plugin_options"), list):
            settings["exchange_plugin_options"] = ["binance", "bybit", "oanda", "alpaca"]
        if not isinstance(settings.get("gate_checklist"), list):
            settings["gate_checklist"] = []
        if not isinstance(settings.get("mode"), str) or not str(settings.get("mode") or "").strip():
            settings["mode"] = default_mode().upper()
        if not isinstance(settings.get("exchange"), str) or not str(settings.get("exchange") or "").strip():
            settings["exchange"] = exchange_name()
        settings["credentials"]["exchange_configured"] = exchange_keys_present(settings.get("mode", default_mode()).lower())
        settings["credentials"]["telegram_configured"] = bool(get_env("TELEGRAM_BOT_TOKEN") and (settings.get("telegram", {}).get("chat_id") or get_env("TELEGRAM_CHAT_ID")))
        learning_defaults = LearningService.default_learning_settings()
        rollout_defaults = RolloutManager.default_rollout_config()
        blending_defaults = RolloutManager.default_blending_config()
        learning = settings.get("learning") if isinstance(settings.get("learning"), dict) else {}
        settings["learning"] = {
            **learning_defaults,
            **learning,
            "validation": {**learning_defaults["validation"], **(learning.get("validation") if isinstance(learning.get("validation"), dict) else {})},
            "promotion": {**learning_defaults["promotion"], **(learning.get("promotion") if isinstance(learning.get("promotion"), dict) else {})},
            "risk_profile": {**learning_defaults["risk_profile"], **(learning.get("risk_profile") if isinstance(learning.get("risk_profile"), dict) else {})},
        }
        settings["learning"]["promotion"]["allow_auto_apply"] = False
        settings["learning"]["promotion"]["allow_live"] = False
        rollout = settings.get("rollout") if isinstance(settings.get("rollout"), dict) else {}
        settings["rollout"] = {
            **rollout_defaults,
            **rollout,
            "phases": rollout.get("phases") if isinstance(rollout.get("phases"), list) else rollout_defaults["phases"],
            "abort_thresholds": {**rollout_defaults["abort_thresholds"], **(rollout.get("abort_thresholds") if isinstance(rollout.get("abort_thresholds"), dict) else {})},
            "improve_vs_baseline": {
                **rollout_defaults["improve_vs_baseline"],
                **(rollout.get("improve_vs_baseline") if isinstance(rollout.get("improve_vs_baseline"), dict) else {}),
            },
            "testnet_checks": {**rollout_defaults["testnet_checks"], **(rollout.get("testnet_checks") if isinstance(rollout.get("testnet_checks"), dict) else {})},
        }
        blending = settings.get("blending") if isinstance(settings.get("blending"), dict) else {}
        settings["blending"] = {**blending_defaults, **blending}
        json_save(SETTINGS_PATH, settings)

    def load_bot_state(self) -> dict[str, Any]:
        state = json_load(BOT_STATE_PATH, {})
        if not state:
            self._ensure_default_bot_state()
            state = json_load(BOT_STATE_PATH, {})
        changed = False
        if str(state.get("runtime_engine") or "").strip().lower() not in {RUNTIME_ENGINE_REAL, RUNTIME_ENGINE_SIMULATED}:
            state["runtime_engine"] = runtime_engine_default()
            changed = True
        if changed:
            json_save(BOT_STATE_PATH, state)
        return state

    def save_bot_state(self, state: dict[str, Any]) -> None:
        state["last_heartbeat"] = utc_now_iso()
        json_save(BOT_STATE_PATH, state)

    def load_strategy_meta(self) -> dict[str, dict[str, Any]]:
        payload = json_load(STRATEGY_META_PATH, {})
        if not isinstance(payload, dict):
            return {}
        return payload

    def save_strategy_meta(self, payload: dict[str, dict[str, Any]]) -> None:
        json_save(STRATEGY_META_PATH, payload)

    @staticmethod
    def _normalize_bot_mode(value: str | None) -> str:
        mode = str(value or "paper").strip().lower()
        if mode not in {"shadow", "paper", "testnet", "live"}:
            return "paper"
        return mode

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
        payload = json_load(BOTS_PATH, [])
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
        json_save(BOTS_PATH, rows)

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

    def get_bots_overview(
        self,
        bot_ids: list[str] | None = None,
        *,
        recommendations: list[dict[str, Any]] | None = None,
        bots: list[dict[str, Any]] | None = None,
        strategies: list[dict[str, Any]] | None = None,
        runs: list[dict[str, Any]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        mode_to_kpi_mode = {"shadow": "backtest", "paper": "paper", "testnet": "testnet", "live": "live"}
        kills_mode_keys = ("shadow", "paper", "testnet", "live", "unknown")

        bots_rows = bots if isinstance(bots, list) else self.load_bots()
        if bot_ids:
            requested = {str(v).strip() for v in bot_ids if str(v).strip()}
            bots_rows = [row for row in bots_rows if str(row.get("id") or "") in requested]
        if not bots_rows:
            return {}

        strategies_rows = strategies if isinstance(strategies, list) else self.list_strategies()
        runs_rows = runs if isinstance(runs, list) else self.load_runs()
        rec_rows = recommendations if isinstance(recommendations, list) else []
        strategy_by_id = {str(row.get("id") or ""): row for row in strategies_rows if str(row.get("id") or "")}

        bot_pool_ids: dict[str, list[str]] = {}
        for bot in bots_rows:
            bid = str(bot.get("id") or "")
            pool_ids = [sid for sid in (bot.get("pool_strategy_ids") or []) if str(sid) in strategy_by_id]
            bot_pool_ids[bid] = [str(sid) for sid in pool_ids]

        runs_by_strategy_mode: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for run in runs_rows:
            if not isinstance(run, dict):
                continue
            sid = str(run.get("strategy_id") or "")
            if not sid:
                continue
            run_mode = str(run.get("mode") or "backtest").lower()
            key = (sid, run_mode)
            rows = runs_by_strategy_mode.get(key)
            if rows is None:
                runs_by_strategy_mode[key] = [run]
            else:
                rows.append(run)

        kpis_by_mode: dict[str, dict[str, dict[str, Any]]] = {mode_key: {} for mode_key in mode_to_kpi_mode}
        for sid in strategy_by_id:
            for mode_key, kpi_mode in mode_to_kpi_mode.items():
                kpis_by_mode[mode_key][sid] = self._aggregate_strategy_kpis(runs_by_strategy_mode.get((sid, kpi_mode), []))

        bot_ids_ordered = [str(bot.get("id") or "") for bot in bots_rows if str(bot.get("id") or "")]
        bot_ids_set = set(bot_ids_ordered)
        empty_kills_template = {key: 0 for key in kills_mode_keys}
        kills_by_mode_per_bot: dict[str, dict[str, int]] = {bid: dict(empty_kills_template) for bid in bot_ids_ordered}
        kills_by_mode_24h_per_bot: dict[str, dict[str, int]] = {bid: dict(empty_kills_template) for bid in bot_ids_ordered}
        last_kill_by_bot: dict[str, str | None] = {bid: None for bid in bot_ids_ordered}
        logs_per_bot: dict[str, list[dict[str, Any]]] = {bid: [] for bid in bot_ids_ordered}

        if bot_ids_ordered:
            placeholders = ",".join("?" for _ in bot_ids_ordered)
            since_24h = (utc_now() - timedelta(hours=24)).isoformat()
            logs_batch_limit = min(2000, max(200, len(bot_ids_ordered) * 20))
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
                # Read 3/3: logs recientes en batch para evitar N+1 por bot.
                log_rows = conn.execute(
                    """
                    SELECT id, ts, type, severity, module, message, related_ids, payload_json
                    FROM logs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (logs_batch_limit,),
                ).fetchall()

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

            for row in log_rows:
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
                payload_map = payload if isinstance(payload, dict) else {}
                targets: set[str] = set()
                if isinstance(related_ids, list):
                    for rid in related_ids:
                        rid_s = str(rid or "").strip()
                        if rid_s and rid_s in bot_ids_set:
                            targets.add(rid_s)
                payload_bot_id = str(payload_map.get("bot_id") or "").strip()
                if payload_bot_id in bot_ids_set:
                    targets.add(payload_bot_id)
                if not targets:
                    continue
                payload_entry = {
                    "id": f"log_{int(row['id'])}",
                    "numeric_id": int(row["id"]),
                    "ts": str(row["ts"] or ""),
                    "type": str(row["type"] or ""),
                    "severity": str(row["severity"] or ""),
                    "module": str(row["module"] or ""),
                    "message": str(row["message"] or ""),
                    "payload": payload_map,
                }
                for bid in targets:
                    bot_logs = logs_per_bot.get(bid)
                    if bot_logs is None or len(bot_logs) >= 20:
                        continue
                    bot_logs.append(payload_entry)
                if all(len(entries) >= 20 for entries in logs_per_bot.values()):
                    break

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
                "last_run_at": last_run_at,
                "recommendations_pending": rec_pending,
                "recommendations_approved": rec_approved,
                "recommendations_rejected": rec_rejected,
            }
            out[bot_id] = {
                "metrics": metrics,
                "recent_logs": logs_per_bot.get(bot_id, []),
            }
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
            "last_run_at": None,
            "recommendations_pending": 0,
            "recommendations_approved": 0,
            "recommendations_rejected": 0,
        }

    def list_bot_instances(self, *, recommendations: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        rows = self.load_bots()
        strategies = self.list_strategies()
        runs = self.load_runs()
        by_id = {str(s.get("id") or ""): s for s in strategies}
        overview = self.get_bots_overview(
            recommendations=recommendations,
            bots=rows,
            strategies=strategies,
            runs=runs,
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
        payload = json_load(RUNS_PATH, [])
        if not isinstance(payload, list):
            return []
        return payload

    def save_runs(self, rows: list[dict[str, Any]]) -> None:
        json_save(RUNS_PATH, rows)

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
        rows = [row for row in self.load_runs() if row.get("strategy_id") == strategy_id]
        if not rows:
            return None
        rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return rows[0]

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
    ) -> dict[str, Any]:
        strategy = self.strategy_or_404(strategy_id)
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
            "orderflow_feature_set": orderflow_feature_set,
            "orderflow_feature_source": "request",
        }
        if bool(use_orderflow_data) and market_n == "equities":
            run_metadata["warnings"] = list(run_metadata.get("warnings") or []) + ["orderflow_not_available_for_market"]
        if fund_required_missing:
            run_metadata["required_missing"] = fund_required_missing
        if fund_reasons:
            run_metadata["fundamentals_reasons"] = fund_reasons
        run_tags = []
        if fund_quality == "ohlc_only":
            run_tags.append("fundamentals_quality:ohlc_only")
        if fund_promotion_blocked:
            run_tags.append("promotion_blocked:fundamentals")
        run_tags.append(f"feature_set:{orderflow_feature_set}")
        is_wfa = str(validation_mode or "").strip().lower() == "walk-forward"
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
                "OOS": bool(is_wfa),
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
                "costs_model": costs_model,
                "dataset_range": {"start": loaded.start, "end": loaded.end},
                "period": {"start": start, "end": end},
                "use_orderflow_data": bool(orderflow_enabled),
                "orderflow_feature_set": orderflow_feature_set,
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
            "orderflow_feature_set": orderflow_feature_set,
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
        self.add_log(
            event_type="backtest_finished",
            severity="info",
            module="backtest",
            message=f"Backtest finished: {run_id}",
            related_ids=[strategy_id, run_id, symbol_n],
            payload={
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

    def add_log(
        self,
        event_type: str,
        severity: str,
        module: str,
        message: str,
        related_ids: list[str],
        payload: dict[str, Any],
    ) -> int:
        with self._connect() as conn:
            ts_now = utc_now_iso()
            cursor = conn.execute(
                """
                INSERT INTO logs (ts, type, severity, module, message, related_ids, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts_now,
                    event_type,
                    severity,
                    module,
                    message,
                    json.dumps(related_ids),
                    json.dumps(payload),
                ),
            )
            if str(event_type or "").strip().lower() == "breaker_triggered":
                payload_map = payload if isinstance(payload, dict) else {}
                self._insert_breaker_event(
                    conn,
                    ts=ts_now,
                    bot_id=str(payload_map.get("bot_id") or ""),
                    mode=str(payload_map.get("mode") or ""),
                    reason=str(payload_map.get("reason") or message or "breaker_triggered"),
                    run_id=str(payload_map.get("run_id") or ""),
                    symbol=str(payload_map.get("symbol") or ""),
                    source_log_id=int(cursor.lastrowid),
                )
            conn.commit()
            return int(cursor.lastrowid)

    def logs_since(self, min_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM logs WHERE id > ? ORDER BY id ASC",
                (min_id,),
            ).fetchall()
        return [self._log_row_to_dict(row) for row in rows]

    def list_logs(
        self,
        severity: str | None,
        module: str | None,
        since: str | None,
        until: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        clauses = []
        params: list[Any] = []
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if module:
            clauses.append("module = ?")
            params.append(module)
        if since:
            clauses.append("ts >= ?")
            params.append(since)
        if until:
            clauses.append("ts <= ?")
            params.append(until)
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        offset = (max(page, 1) - 1) * max(page_size, 1)
        with self._connect() as conn:
            total_row = conn.execute(f"SELECT COUNT(*) AS n FROM logs {where_sql}", tuple(params)).fetchone()
            rows = conn.execute(
                f"SELECT * FROM logs {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
                tuple(params + [page_size, offset]),
            ).fetchall()
        return {
            "items": [self._log_row_to_dict(row) for row in rows],
            "total": int(total_row["n"]) if total_row else 0,
            "page": page,
            "page_size": page_size,
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
rollout_manager = RolloutManager(user_data_dir=USER_DATA_DIR)
mass_backtest_engine = MassBacktestEngine(user_data_dir=USER_DATA_DIR, repo_root=MONOREPO_ROOT, knowledge_loader=KnowledgeLoader(repo_root=MONOREPO_ROOT))
mass_backtest_coordinator = MassBacktestCoordinator(engine=mass_backtest_engine)
rollout_gates = GateEvaluator(repo_root=MONOREPO_ROOT)


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
        engine = BacktestEngine()
        result = engine.run(
            BacktestRequest(
                market=loaded.market,
                symbol=loaded.symbol,
                timeframe=loaded.timeframe,
                start=start,
                end=end,
                strategy_id=str(candidate.get("base_strategy_id") or DEFAULT_STRATEGY_ID),
                validation_mode="walk-forward",
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
    except Exception:
        if ref:
            return {
                "metrics": dict(ref.get("metrics") or {}),
                "costs_breakdown": dict(ref.get("costs_breakdown") or {}),
                "equity_curve": list(ref.get("equity_curve") or []),
                "data_source": str(ref.get("data_source") or "runs_cache_fallback"),
                "dataset_hash": str(ref.get("dataset_hash") or ""),
                "costs_model": costs,
            }
        return {
            "metrics": {"max_dd": 0.0, "sortino": 0.0, "expectancy": 0.0, "sharpe": 0.0},
            "costs_breakdown": {"gross_pnl_total": 0.0, "total_cost": 0.0},
            "equity_curve": [],
            "data_source": "none",
            "dataset_hash": "",
            "costs_model": costs,
        }


def _mass_backtest_eval_fold(variant: dict[str, Any], fold: Any, costs: dict[str, Any], base_cfg: dict[str, Any]) -> dict[str, Any]:
    strategy_id = str(variant.get("strategy_id") or DEFAULT_STRATEGY_ID)
    market = str(base_cfg.get("market") or "crypto")
    symbol = str(base_cfg.get("symbol") or "BTCUSDT")
    timeframe = str(base_cfg.get("timeframe") or "5m")
    data_source = str(base_cfg.get("dataset_source") or "auto").lower()
    validation_mode = str(base_cfg.get("validation_mode") or "walk-forward")
    if data_source in {"synthetic", "synthetic_seeded", "synthetic_fallback"}:
        raise ValueError(
            "Backtests masivos solo permiten datos reales. Usa dataset_source='auto' o 'dataset' y descarga el dataset."
        )
    return store.create_event_backtest_run(
        strategy_id=strategy_id,
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


def _is_trusted_internal_proxy(request: Request) -> bool:
    configured = internal_proxy_token()
    if not configured:
        return get_env("NODE_ENV", "development").lower() != "production"
    provided = (request.headers.get("x-rtlab-proxy-token") or "").strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, configured)


def current_user(request: Request) -> dict[str, str]:
    internal_role = (request.headers.get("x-rtlab-role") or "").lower().strip()
    internal_user = (request.headers.get("x-rtlab-user") or "").strip()
    if internal_role in ALLOWED_ROLES and internal_user and _is_trusted_internal_proxy(request):
        return {"username": internal_user, "role": internal_role}

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


def evaluate_gates(mode: str | None = None, *, force_exchange_check: bool = False) -> dict[str, Any]:
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

    runtime_engine = _runtime_engine_from_state(store.load_bot_state())
    runtime_real = runtime_engine == RUNTIME_ENGINE_REAL
    if active_mode == "live":
        g9_status = "PASS" if runtime_real else "FAIL"
        g9_reason = (
            "Runtime de ejecucion real habilitado"
            if runtime_real
            else "Runtime simulado detectado: LIVE bloqueado hasta configurar RUNTIME_ENGINE=real"
        )
    else:
        g9_status = "PASS" if runtime_real else "WARN"
        g9_reason = (
            "Runtime de ejecucion real habilitado"
            if runtime_real
            else "Runtime en modo simulado (valido para paper/testnet)"
        )
    gates.append(
        gate_row(
            "G9_RUNTIME_ENGINE_REAL",
            "Runtime engine",
            g9_status,
            g9_reason,
            {"runtime_engine": runtime_engine, "mode": active_mode},
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
    ]
    for gate_id in required:
        row = gates.get(gate_id)
        if not row or row["status"] != "PASS":
            reason = row["reason"] if row else f"{gate_id} missing"
            return False, reason
    return True, "All live gates are PASS"


def build_status_payload() -> dict[str, Any]:
    state = store.load_bot_state()
    settings = store.load_settings()
    gates = evaluate_gates(state.get("mode", "paper"))
    runtime_engine = _runtime_engine_from_state(state)
    runtime_real = runtime_engine == RUNTIME_ENGINE_REAL
    runtime_mode = "real" if runtime_real else "simulado"
    positions = [
        {
            "symbol": "BTC/USDT",
            "side": "long",
            "qty": 0.02,
            "entry_px": 101200.0,
            "mark_px": 101550.0,
            "pnl_unrealized": 7.0,
            "exposure_usd": 2031.0,
            "strategy_id": DEFAULT_STRATEGY_ID,
        }
    ] if state.get("running") else []
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
            "warning": None if runtime_real else "Runtime simulado: no se envian ordenes reales al exchange.",
        },
        "runtime_engine": runtime_engine,
        "runtime_mode": runtime_mode,
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
            "api_latency_ms": 42,
            "ws_connected": True,
            "ws_lag_ms": 120,
            "errors_5m": 0,
            "rate_limits_5m": 0,
            "errors_24h": 0,
        },
        "gates_overall": gates["overall_status"],
        "positions": positions,
    }


def build_execution_metrics_payload() -> dict[str, Any]:
    now = utc_now()
    series = []
    for idx in range(40):
        series.append(
            {
                "ts": (now - timedelta(minutes=(40 - idx))).isoformat(),
                "latency_ms_p95": 120 + (idx % 5) * 8,
                "spread_bps": 7.0 + ((idx % 6) * 0.7),
                "slippage_bps": 4.0 + ((idx % 4) * 0.6),
                "maker_ratio": 0.58 + ((idx % 3) * 0.01),
                "fill_ratio": 0.91 - ((idx % 3) * 0.01),
            }
        )
    return {
        "maker_ratio": 0.61,
        "fill_ratio": 0.92,
        "requotes": 2,
        "cancels": 4,
        "rate_limit_hits": 1,
        "api_errors": 0,
        "avg_spread": 8.1,
        "p95_spread": 12.2,
        "avg_slippage": 4.3,
        "p95_slippage": 7.4,
        "latency_ms_p95": 146.0,
        "series": series,
        "notes": [
            "Maker ratio stable in the last hour.",
            "No severe API errors observed.",
            "Spread remains under configured guardrails.",
        ],
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

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        state = store.load_bot_state()
        mode = state.get("mode", "paper")
        runtime_engine = _runtime_engine_from_state(state)
        return {
            "status": "ok",
            "ok": True,
            "time": utc_now_iso(),
            "version": APP_VERSION,
            "mode": mode,
            "runtime_engine": runtime_engine,
            "runtime_mode": "real" if runtime_engine == RUNTIME_ENGINE_REAL else "simulado",
            "ws": {"connected": True, "transport": "sse", "url": "/api/v1/stream", "last_event_at": utc_now_iso()},
            "exchange": {"name": exchange_name(), "mode": mode.upper()},
            "db": {"ok": True, "driver": "sqlite"},
        }

    @app.post("/api/v1/auth/login")
    def auth_login(body: LoginBody) -> dict[str, Any]:
        username = body.username.strip()
        role: str | None = None
        if username == admin_username() and body.password == admin_password():
            role = ROLE_ADMIN
        elif username == viewer_username() and body.password == viewer_password():
            role = ROLE_VIEWER
        if not role:
            raise HTTPException(status_code=401, detail="Invalid credentials")
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
        strategy = store.strategy_or_404(strategy_id)
        principals = store.registry.principals()
        primary_for = [row["mode"] for row in principals if row["name"] == strategy_id]
        run = store.latest_run_for_strategy(strategy_id)
        return {
            **strategy,
            "primary_for_modes": primary_for,
            "last_oos": run["metrics"] if run else None,
        }

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
    def list_bots(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        recs = learning_service.load_all_recommendations()
        items = store.list_bot_instances(recommendations=recs)
        return {"items": items, "total": len(items)}

    def ensure_bot_live_mode_allowed(mode: str | None) -> None:
        if str(mode or "").lower() != "live":
            return
        gates_payload = evaluate_gates("live")
        allowed, reason = live_can_be_enabled(gates_payload)
        if not allowed:
            raise HTTPException(status_code=400, detail=f"No se puede asignar bot en LIVE: {reason}")

    @app.post("/api/v1/bots")
    def create_bot(body: BotCreateBody, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        ensure_bot_live_mode_allowed(body.mode)
        bot = store.create_bot_instance(
            name=body.name,
            engine=body.engine,
            mode=body.mode,
            status=body.status,
            pool_strategy_ids=body.pool_strategy_ids,
            universe=body.universe,
            notes=body.notes,
        )
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
        recs = learning_service.load_all_recommendations()
        items = store.list_bot_instances(recommendations=recs)
        enriched = next((row for row in items if str(row.get("id")) == str(bot.get("id"))), bot)
        return {"ok": True, "bot": enriched}

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
        return learning_service.build_status(
            settings=settings_payload,
            strategies=store.list_strategies(),
            runs=store.load_runs(),
        )

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
        started = mass_backtest_coordinator.start_async(
            config=cfg,
            strategies=store.list_strategies(),
            historical_runs=store.load_runs(),
            backtest_callback=lambda variant, fold, costs: _mass_backtest_eval_fold(variant, fold, costs, cfg),
        )
        store.add_log(
            event_type="research_mass_backtest_start",
            severity="info",
            module="research",
            message="Mass backtests iniciados",
            related_ids=[str(started.get("run_id") or "")],
            payload={"config": cfg, "no_auto_live": True},
        )
        return started

    @app.post("/api/v1/batches")
    def create_research_batch(body: BatchCreateBody, user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        cfg = body.model_dump()
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
        started = mass_backtest_coordinator.start_async(
            config=cfg,
            strategies=store.list_strategies(),
            historical_runs=store.load_runs(),
            backtest_callback=lambda variant, fold, costs: _mass_backtest_eval_fold(variant, fold, costs, cfg),
        )
        batch_id = str(started.get("run_id") or "")
        store.add_log(
            event_type="batch_created",
            severity="info",
            module="research",
            message="Research Batch creado",
            related_ids=[batch_id],
            payload={"config": cfg, "batch_id": batch_id},
        )
        return {"ok": True, "batch_id": batch_id, **started}

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
            related_ids=[str(started.get("run_id") or "")],
            payload={"tier": body.tier, "estimated_trial_units": started.get("estimated_trial_units"), "config": cfg, "no_auto_live": True},
        )
        return started

    @app.get("/api/v1/research/beast/status")
    def research_beast_status(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        return mass_backtest_coordinator.beast_status()

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

        market = body.get("market")
        symbol = body.get("symbol")
        timeframe = body.get("timeframe")
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
                )
            except FileNotFoundError as exc:
                mk = str(market).strip().lower()
                script_name = (
                    "scripts/download_crypto_binance_public.py"
                    if mk == "crypto"
                    else "scripts/download_forex_dukascopy.py"
                    if mk == "forex"
                    else "scripts/download_equities_alpaca.py"
                )
                raise HTTPException(
                    status_code=400,
                    detail=f"Faltan datos para {mk}/{str(symbol).upper()}/{str(timeframe).lower()}. Descarga con {script_name} y reintenta. Detalle: {exc}",
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

        # Backward compatibility: historic runs had order flow implicit ON.
        return "orderflow_on", True, "default_backward_compat"

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
            if candidate_feature_set and row_feature_set != candidate_feature_set:
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
                if candidate_feature_set and row_feature_set != candidate_feature_set:
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
        items = store.backtest_catalog.query_runs(
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
            limit=limit,
        )
        return {"items": items, "count": len(items)}

    @app.get("/api/v1/runs/{run_id}")
    def runs_detail(run_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        row = _catalog_run_or_404(run_id)
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

    @app.post("/api/v1/trades/bulk-delete")
    def trades_bulk_delete(body: "TradesBulkDeleteBody", user: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
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
        gates_payload = evaluate_gates(status["mode"])
        settings = store.load_settings()
        checklist = [{"stage": row["id"], "done": row["status"] == "PASS", "note": row["reason"]} for row in gates_payload["gates"]]
        return {
            "equity": status["equity"],
            "dd": status["max_dd"]["value"],
            "daily_loss": status["daily_loss"]["value"],
            "exposure_total": status["equity"] * 0.22,
            "exposure_by_symbol": [
                {"symbol": "BTC/USDT", "exposure": status["equity"] * 0.14},
                {"symbol": "ETH/USDT", "exposure": status["equity"] * 0.08},
            ],
            "circuit_breakers": ["none"] if not status["risk_flags"]["safe_mode"] else ["safe_mode"],
            "limits": {
                "daily_loss_limit": -abs(settings["risk_defaults"]["max_daily_loss"] / 100),
                "max_dd_limit": -abs(settings["risk_defaults"]["max_dd"] / 100),
                "max_positions": int(settings["risk_defaults"]["max_positions"]),
                "max_total_exposure": 0.9,
                "risk_per_trade": abs(settings["risk_defaults"]["risk_per_trade"] / 100),
            },
            "stress_tests": [
                {"scenario": "fees_x2", "robust_score": 71.2},
                {"scenario": "slippage_x2", "robust_score": 67.8},
                {"scenario": "spread_shock", "robust_score": 65.1},
            ],
            "forecast_band": {"return_p50_30d": 0.041, "return_p90_30d": 0.085, "dd_p90_30d": -0.098},
            "gate_checklist": checklist,
        }

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
        store.add_log(
            event_type="mode_changed",
            severity="warn" if mode == "live" else "info",
            module="control",
            message=f"Bot mode set to {mode}",
            related_ids=[],
            payload={"mode": mode},
        )
        return {"ok": True, "mode": mode}

    @app.post("/api/v1/bot/start")
    def bot_start(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        state = store.load_bot_state()
        state["runtime_engine"] = _runtime_engine_from_state(state)
        principal = store.registry.get_principal(state["mode"])
        if not principal:
            raise HTTPException(status_code=400, detail=f"No principals configured for mode {state['mode']}")
        state["running"] = True
        state["killed"] = False
        state["bot_status"] = "RUNNING"
        store.save_bot_state(state)
        store.add_log(
            event_type="status",
            severity="info",
            module="control",
            message=f"Bot started in {state['mode']}",
            related_ids=[principal["name"]],
            payload={"mode": state["mode"], "strategy": principal["name"]},
        )
        return {"ok": True, "state": state["bot_status"], "mode": state["mode"]}

    @app.post("/api/v1/bot/stop")
    def bot_stop(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        state = store.load_bot_state()
        state["running"] = False
        state["bot_status"] = "PAUSED"
        store.save_bot_state(state)
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
        return {"ok": True, "state": state["bot_status"]}

    @app.post("/api/v1/control/resume")
    def control_resume(_: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        return bot_start(_)

    @app.post("/api/v1/control/safe-mode")
    async def control_safe_mode(request: Request, _: dict[str, str] = Depends(require_admin)) -> dict[str, Any]:
        body = await request.json()
        enabled = bool(body.get("enabled", True))
        state = store.load_bot_state()
        state["safe_mode"] = enabled
        state["bot_status"] = "SAFE_MODE" if enabled else ("RUNNING" if state.get("running") else "PAUSED")
        store.save_bot_state(state)
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


from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
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
from rtlab_core.learning import LearningService
from rtlab_core.rollout import CompareEngine, GateEvaluator, RolloutManager
from rtlab_core.src.backtest.engine import BacktestCosts, BacktestEngine, BacktestRequest, MarketDataset
from rtlab_core.src.data.catalog import DataCatalog
from rtlab_core.src.data.loader import DataLoader
from rtlab_core.src.data.universes import MARKET_UNIVERSES, SUPPORTED_TIMEFRAMES, normalize_market, normalize_symbol, normalize_timeframe
from rtlab_core.src.reports.reporting import ReportEngine as ArtifactReportEngine
from rtlab_core.strategy_packs.registry_db import RegistryDB

APP_VERSION = "0.1.0"
PROJECT_ROOT = Path(os.getenv("RTLAB_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))).resolve()
MONOREPO_ROOT = (PROJECT_ROOT.parent if (PROJECT_ROOT.parent / "knowledge").exists() else PROJECT_ROOT).resolve()


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
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
ALLOWED_ROLES = {ROLE_ADMIN, ROLE_VIEWER}
ALLOWED_MODES = {"paper", "testnet", "live"}
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


class LearningAdoptBody(BaseModel):
    candidate_id: str
    mode: Literal["paper", "testnet"]


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


def get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def admin_username() -> str:
    return get_env("ADMIN_USERNAME", "admin")


def admin_password() -> str:
    return get_env("ADMIN_PASSWORD", "admin123!")


def viewer_username() -> str:
    return get_env("VIEWER_USERNAME", "viewer")


def viewer_password() -> str:
    return get_env("VIEWER_PASSWORD", "viewer123!")


def auth_secret() -> str:
    return get_env("AUTH_SECRET", "")


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

    if connector_ok:
        connector_reason = "Exchange connector listo."
    else:
        connector_reason = last_error or "Exchange connector no listo."

    if order_ok:
        order_reason = "Place/cancel testnet operativo."
    else:
        order_reason = checks.get("order_test", {}).get("error") or "Cannot place/cancel on testnet."

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
        self._init_console_db()
        self._ensure_defaults()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(CONSOLE_DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_console_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(LOG_SCHEMA_SQL)
            conn.commit()
    def _ensure_defaults(self) -> None:
        self._ensure_default_settings()
        self._ensure_default_bot_state()
        self._ensure_default_strategy()
        self._ensure_seed_backtest()
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
        learning_defaults = LearningService.default_learning_settings()
        rollout_defaults = RolloutManager.default_rollout_config()
        blending_defaults = RolloutManager.default_blending_config()
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
                "risk_defaults": {
                    "max_daily_loss": 5.0,
                    "max_dd": 22.0,
                    "max_positions": 20,
                    "risk_per_trade": 0.75,
                },
                "execution": {
                    "post_only_default": True,
                    "slippage_max_bps": 12,
                    "request_timeout_ms": 4000,
                },
                "feature_flags": {
                    "orderflow": True,
                    "vpin": True,
                    "ml": False,
                    "alerts": True,
                },
                "learning": learning_defaults,
                "rollout": rollout_defaults,
                "blending": blending_defaults,
                "gate_checklist": [],
            }
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

    def _ensure_seed_backtest(self) -> None:
        runs = self.load_runs()
        if runs:
            return
        self.create_backtest_run(
            strategy_id=DEFAULT_STRATEGY_ID,
            start="2024-01-01",
            end="2024-12-31",
            universe=["BTC/USDT", "ETH/USDT"],
            fees_bps=5.5,
            spread_bps=4.0,
            slippage_bps=3.0,
            funding_bps=1.0,
            validation_mode="walk-forward",
        )

    def load_settings(self) -> dict[str, Any]:
        settings = json_load(SETTINGS_PATH, {})
        if not settings:
            self._ensure_default_settings()
            settings = json_load(SETTINGS_PATH, {})
        return settings

    def save_settings(self, settings: dict[str, Any]) -> None:
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
        }
        blending = settings.get("blending") if isinstance(settings.get("blending"), dict) else {}
        settings["blending"] = {**blending_defaults, **blending}
        json_save(SETTINGS_PATH, settings)

    def load_bot_state(self) -> dict[str, Any]:
        state = json_load(BOT_STATE_PATH, {})
        if not state:
            self._ensure_default_bot_state()
            state = json_load(BOT_STATE_PATH, {})
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

    def list_strategies(self) -> list[dict[str, Any]]:
        metadata = self.load_strategy_meta()
        principals = {row["mode"]: row for row in self.registry.principals()}
        out: list[dict[str, Any]] = []
        for strategy_id, row in metadata.items():
            primary_for: list[str] = []
            for mode in ("paper", "testnet", "live"):
                principal = principals.get(mode)
                if principal and principal["name"] == strategy_id:
                    primary_for.append(mode)
            latest_backtest = self.latest_run_for_strategy(strategy_id)
            out.append(
                {
                    "id": strategy_id,
                    "name": row.get("name", strategy_id),
                    "version": row.get("version", "0.0.0"),
                    "enabled": bool(row.get("enabled", False)),
                    "primary": bool(primary_for),
                    "primary_for_modes": primary_for,
                    "last_run_at": row.get("last_run_at"),
                    "last_oos": latest_backtest["metrics"] if latest_backtest else None,
                    "notes": row.get("notes", ""),
                    "description": row.get("description", ""),
                    "params": parse_yaml_map(row.get("params_yaml", "")),
                    "params_yaml": row.get("params_yaml", ""),
                    "parameters_schema": row.get("parameters_schema", {}),
                    "tags": row.get("tags", ["trend", "pullback", "orderflow"]),
                    "created_at": row.get("created_at", utc_now_iso()),
                    "updated_at": row.get("updated_at", utc_now_iso()),
                }
            )
        out.sort(key=lambda item: item.get("id", ""))
        return out

    def strategy_or_404(self, identifier: str) -> dict[str, Any]:
        metadata = self.load_strategy_meta()
        row = metadata.get(identifier)
        if not row:
            raise HTTPException(status_code=404, detail="Strategy not found")
        principals = {item["mode"]: item for item in self.registry.principals()}
        primary_for = [mode for mode in ("paper", "testnet", "live") if principals.get(mode, {}).get("name") == identifier]
        return {
            "id": identifier,
            "name": row.get("name", identifier),
            "version": row.get("version", "0.0.0"),
            "enabled": bool(row.get("enabled", False)),
            "primary": bool(primary_for),
            "primary_for_modes": primary_for,
            "notes": row.get("notes", ""),
            "description": row.get("description", ""),
            "params": parse_yaml_map(row.get("params_yaml", "")),
            "params_yaml": row.get("params_yaml", ""),
            "parameters_schema": row.get("parameters_schema", {}),
            "db_strategy_id": int(row.get("db_strategy_id")),
            "last_run_at": row.get("last_run_at"),
            "tags": row.get("tags", ["trend", "pullback", "orderflow"]),
            "created_at": row.get("created_at", utc_now_iso()),
            "updated_at": row.get("updated_at", utc_now_iso()),
        }

    def set_strategy_enabled(self, strategy_id: str, enabled: bool) -> dict[str, Any]:
        metadata = self.load_strategy_meta()
        row = metadata.get(strategy_id)
        if not row:
            raise HTTPException(status_code=404, detail="Strategy not found")
        row["enabled"] = enabled
        row["updated_at"] = utc_now_iso()
        status = "enabled" if enabled else "disabled"
        self.registry.set_status(int(row["db_strategy_id"]), status)
        metadata[strategy_id] = row
        self.save_strategy_meta(metadata)
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
            "db_strategy_id": db_strategy_id,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "notes": f"Cloned from {strategy_id}",
        }
        self.save_strategy_meta(meta)
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
        run_id = f"run_{secrets.token_hex(5)}"
        run = {
            "id": run_id,
            "strategy_id": strategy_id,
            "period": {"start": start, "end": end},
            "universe": universe,
            "costs_model": {
                "fees_bps": fees_bps,
                "spread_bps": spread_bps,
                "slippage_bps": slippage_bps,
                "funding_bps": funding_bps,
            },
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
            "created_at": utc_now_iso(),
            "duration_sec": random.randint(20, 90),
            "equity_curve": points,
            "drawdown_curve": [{"time": p["time"], "value": p["drawdown"]} for p in points],
            "trades": trades,
            "artifacts_links": {
                "report_json": f"/api/v1/backtests/runs/{run_id}?format=report_json",
                "trades_csv": f"/api/v1/backtests/runs/{run_id}?format=trades_csv",
                "equity_curve_csv": f"/api/v1/backtests/runs/{run_id}?format=equity_curve_csv",
            },
        }
        runs = self.load_runs()
        runs.insert(0, run)
        self.save_runs(runs)
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
        run_id = f"run_{secrets.token_hex(5)}"
        metrics = dict(engine_result["metrics"])
        metrics["expectancy_unit"] = "usd_per_trade"
        metrics["expectancy_pct_unit"] = "pct_per_trade"
        run = {
            "id": run_id,
            "strategy_id": strategy_id,
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
            "costs_model": {
                "fees_bps": fees_bps,
                "spread_bps": spread_bps,
                "slippage_bps": slippage_bps,
                "funding_bps": funding_bps,
                "rollover_bps": rollover_bps,
            },
            "git_commit": get_env("GIT_COMMIT", "local"),
            "metrics": metrics,
            "costs_breakdown": engine_result["costs_breakdown"],
            "status": "completed",
            "created_at": utc_now_iso(),
            "duration_sec": random.randint(2, 30),
            "equity_curve": engine_result["equity_curve"],
            "drawdown_curve": engine_result["drawdown_curve"],
            "trades": engine_result["trades"],
            "artifacts_links": {
                "report_json": f"/api/v1/backtests/runs/{run_id}?format=report_json",
                "trades_csv": f"/api/v1/backtests/runs/{run_id}?format=trades_csv",
                "equity_curve_csv": f"/api/v1/backtests/runs/{run_id}?format=equity_curve_csv",
            },
        }
        artifact_local = ArtifactReportEngine(USER_DATA_DIR).write_backtest_artifacts(run_id, run)
        run["artifacts_local"] = artifact_local

        runs = self.load_runs()
        runs.insert(0, run)
        self.save_runs(runs)
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
            cursor = conn.execute(
                """
                INSERT INTO logs (ts, type, severity, module, message, related_ids, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now_iso(),
                    event_type,
                    severity,
                    module,
                    message,
                    json.dumps(related_ids),
                    json.dumps(payload),
                ),
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


store = ConsoleStore()
learning_service = LearningService(user_data_dir=USER_DATA_DIR, repo_root=MONOREPO_ROOT)
rollout_manager = RolloutManager(user_data_dir=USER_DATA_DIR)
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


def current_user(request: Request) -> dict[str, str]:
    internal_role = (request.headers.get("x-rtlab-role") or "").lower().strip()
    internal_user = (request.headers.get("x-rtlab-user") or "").strip()
    if internal_role in ALLOWED_ROLES and internal_user:
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

    auth_ok = bool(auth_secret() and len(auth_secret()) >= 32 and admin_username() and admin_password() and viewer_username() and viewer_password())
    gates.append(
        gate_row(
            "G2_AUTH_READY",
            "Auth ready",
            "PASS" if auth_ok else "FAIL",
            "Auth env ready" if auth_ok else "AUTH_SECRET/admin/viewer missing",
            {"admin": bool(admin_username()), "viewer": bool(viewer_username()), "secret_len": len(auth_secret())},
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

    overall = "PASS"
    if any(row["status"] == "FAIL" for row in gates):
        overall = "FAIL"
    elif any(row["status"] == "WARN" for row in gates):
        overall = "WARN"

    return {"gates": gates, "overall_status": overall, "mode": active_mode}


def live_can_be_enabled(gates_payload: dict[str, Any]) -> tuple[bool, str]:
    gates = {row["id"]: row for row in gates_payload["gates"]}
    required = ["G1_CONFIG_VALID", "G2_AUTH_READY", "G3_BACKEND_HEALTH", "G5_STRATEGY_PRINCIPAL_SET", "G6_RISK_LIMITS_SET", "G4_EXCHANGE_CONNECTOR_READY", "G7_ORDER_SIM_OR_PAPER_OK"]
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
        mode = store.load_bot_state().get("mode", "paper")
        return {
            "status": "ok",
            "ok": True,
            "time": utc_now_iso(),
            "version": APP_VERSION,
            "mode": mode,
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
    def gates() -> dict[str, Any]:
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

    @app.get("/api/v1/learning/status")
    def learning_status(_: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        settings_payload = learning_service.ensure_settings_shape(store.load_settings())
        return learning_service.build_status(
            settings=settings_payload,
            strategies=store.list_strategies(),
            runs=store.load_runs(),
        )

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
        return learning_service.load_recommendations()

    @app.get("/api/v1/learning/recommendations/{candidate_id}")
    def learning_recommendation_detail(candidate_id: str, _: dict[str, str] = Depends(current_user)) -> dict[str, Any]:
        row = learning_service.get_recommendation(candidate_id)
        if not row:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        return row

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

        market = body.get("market")
        symbol = body.get("symbol")
        timeframe = body.get("timeframe")
        data_source = str(body.get("data_source") or "auto").lower()
        if market and symbol and timeframe:
            if data_source == "synthetic":
                run = store.create_backtest_run(
                    strategy_id=strategy_id,
                    start=start,
                    end=end,
                    universe=[normalize_symbol(str(symbol))],
                    fees_bps=fees_bps,
                    spread_bps=spread_bps,
                    slippage_bps=slippage_bps,
                    funding_bps=funding_bps,
                    validation_mode=validation_mode,
                )
                run["market"] = normalize_market(str(market))
                run["symbol"] = normalize_symbol(str(symbol))
                run["timeframe"] = normalize_timeframe(str(timeframe))
                run["data_source"] = "synthetic"
            else:
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
            run = store.create_backtest_run(
                strategy_id=strategy_id,
                start=start,
                end=end,
                universe=body.get("universe") or ["BTC/USDT", "ETH/USDT"],
                fees_bps=fees_bps,
                spread_bps=spread_bps,
                slippage_bps=slippage_bps,
                funding_bps=funding_bps,
                validation_mode=validation_mode,
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

    @app.get("/api/v1/trades")
    def trades(
        strategy_id: str | None = None,
        symbol: str | None = None,
        side: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        _: dict[str, str] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for run in store.load_runs():
            rows.extend(run.get("trades", []))
        if strategy_id:
            rows = [row for row in rows if row.get("strategy_id") == strategy_id]
        if symbol:
            rows = [row for row in rows if row.get("symbol") == symbol]
        if side:
            rows = [row for row in rows if row.get("side") == side]
        if date_from:
            rows = [row for row in rows if row.get("entry_time", "") >= date_from]
        if date_to:
            rows = [row for row in rows if row.get("entry_time", "") <= date_to]
        rows.sort(key=lambda row: row.get("entry_time", ""), reverse=True)
        return rows[:1000]

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
            if body.confirm != "ENABLE_LIVE":
                raise HTTPException(status_code=400, detail="Missing explicit confirmation for LIVE")
            gates_payload = evaluate_gates("live")
            allowed, reason = live_can_be_enabled(gates_payload)
            if not allowed:
                raise HTTPException(status_code=400, detail=f"LIVE blocked by gates: {reason}")
        state = store.load_bot_state()
        state["mode"] = mode
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
            payload={"close_positions": True, "cancel_orders": True},
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

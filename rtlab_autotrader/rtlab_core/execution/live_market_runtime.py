from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import random
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import yaml
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed

from rtlab_core.policy_paths import describe_policy_root_resolution


BINANCE_LIVE_RUNTIME_FILENAME = "binance_live_runtime.yaml"
POLICY_EXPECTED_FILES: tuple[str, ...] = (
    "runtime_controls.yaml",
    "instrument_registry.yaml",
    "universes.yaml",
    "cost_stack.yaml",
    "reporting_exports.yaml",
    "execution_safety.yaml",
    "execution_router.yaml",
    "validation_gates.yaml",
    BINANCE_LIVE_RUNTIME_FILENAME,
)
PARSER_VERSION = "binance_live_runtime_v1"
SUPPORTED_CONNECTORS = {"binance_spot", "binance_um_futures"}
SUPPORTED_ENVIRONMENTS = {"live", "testnet"}
SUPPORTED_TRANSPORTS = {"combined", "raw"}

FAIL_CLOSED_MINIMAL_BINANCE_LIVE_RUNTIME_POLICY: dict[str, Any] = {
    "binance_live_runtime": {
        "connectors": {
            "binance_spot": {
                "vendor": "binance",
                "market_family": "spot",
                "repo_family": "spot",
                "execution_connector": "binance_spot",
                "account_scope": "spot_wallet",
                "cost_model": "spot_costs",
                "symbol_domain": "crypto",
                "live_capabilities": ["paper", "testnet", "live"],
                "user_stream_mode": "legacy_listenkey",
                "order_test_supported": True,
                "order_paths": {"paper": "dry_run", "testnet": "live_submit", "live": "live_submit"},
                "market_ws": {
                    "enabled": False,
                    "transport_modes_allowed": ["combined"],
                    "default_transport": "combined",
                    "live_ws_base_url": "wss://stream.binance.com:9443",
                    "testnet_ws_base_url": "wss://stream.testnet.binance.vision",
                    "ws_url_env_live": "BINANCE_SPOT_WS_URL",
                    "ws_url_env_testnet": "BINANCE_SPOT_TESTNET_WS_URL",
                    "raw_path": "/ws",
                    "combined_path_prefix": "/stream?streams=",
                    "required_streams": ["bookTicker", "aggTrade"],
                    "optional_streams": [],
                    "market_ws_backoff_seconds": [1, 2, 4],
                    "market_ws_jitter_pct": 0.0,
                    "market_ws_hard_recycle_hours": 1.0,
                    "ping_expectation_seconds": 20,
                    "pong_timeout_seconds": 60,
                    "stale_warn_ms": 1,
                    "stale_block_live_ms": 1,
                    "max_consecutive_ws_failures_before_block_live": 1,
                    "max_incoming_messages_per_sec": 5,
                    "max_streams_per_connection": 1024,
                    "max_connection_attempts_per_5m_per_ip": 300,
                },
            },
            "binance_um_futures": {
                "vendor": "binance",
                "market_family": "um_futures",
                "repo_family": "usdm_futures",
                "execution_connector": "binance_um_futures",
                "account_scope": "futures_wallet",
                "cost_model": "um_futures_costs",
                "symbol_domain": "crypto",
                "live_capabilities": ["paper", "testnet", "live"],
                "user_stream_mode": "futures_listenkey",
                "order_test_supported": False,
                "order_paths": {"paper": "dry_run", "testnet": "live_submit", "live": "live_submit"},
                "market_ws": {
                    "enabled": False,
                    "transport_modes_allowed": ["combined"],
                    "default_transport": "combined",
                    "live_ws_base_url": "wss://fstream.binance.com",
                    "testnet_ws_base_url": "wss://stream.binancefuture.com",
                    "ws_url_env_live": "BINANCE_USDM_WS_URL",
                    "ws_url_env_testnet": "BINANCE_USDM_TESTNET_WS_URL",
                    "raw_path": "/ws",
                    "combined_path_prefix": "/stream?streams=",
                    "required_streams": ["bookTicker", "aggTrade", "markPrice@1s"],
                    "optional_streams": [],
                    "market_ws_backoff_seconds": [1, 2, 4],
                    "market_ws_jitter_pct": 0.0,
                    "market_ws_hard_recycle_hours": 1.0,
                    "ping_expectation_seconds": 180,
                    "pong_timeout_seconds": 600,
                    "stale_warn_ms": 1,
                    "stale_block_live_ms": 1,
                    "max_consecutive_ws_failures_before_block_live": 1,
                    "max_incoming_messages_per_sec": 10,
                    "max_streams_per_connection": 1024,
                    "max_connection_attempts_per_5m_per_ip": 300,
                },
            },
        },
        "runtime_guardrails": {
            "block_live_on_stale_when_running": True,
            "block_live_after_failure_threshold": True,
            "mark_degraded_on_disconnect": True,
            "require_explicit_start": True,
            "public_smoke_supported": True,
        },
    }
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return _utc_now().isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _stable_payload_hash(value: Any) -> str:
    return hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalize_environment(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in SUPPORTED_ENVIRONMENTS else "live"


def _normalize_connector(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in SUPPORTED_CONNECTORS else ""


def _normalize_transport(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in SUPPORTED_TRANSPORTS else "combined"


def _canonical_symbol(value: Any) -> str:
    return str(value or "").replace("/", "").replace("-", "").strip().upper()


def _policy_source_label(repo_root: Path, policy_path: Path) -> str:
    try:
        return str(policy_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(policy_path.resolve())


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


def _require_dict(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{path}.{key} debe ser dict")
        return {}
    return value


def _require_bool(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        errors.append(f"{path}.{key} debe ser bool")
        return False
    return value


def _require_number(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> float:
    value = parent.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{path}.{key} debe ser numero")
        return 0.0
    return float(value)


def _require_string(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> str:
    value = str(parent.get(key) or "").strip()
    if not value:
        errors.append(f"{path}.{key} debe ser string no vacio")
        return ""
    return value


def _require_string_list(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> list[str]:
    value = parent.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not str(item).strip() for item in value):
        errors.append(f"{path}.{key} debe ser lista de strings no vacios")
        return []
    return [str(item).strip() for item in value]


def _validate_connector(connector_name: str, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    path = f"binance_live_runtime.connectors.{connector_name}"
    _require_string(payload, "vendor", errors=errors, path=path)
    _require_string(payload, "market_family", errors=errors, path=path)
    _require_string(payload, "repo_family", errors=errors, path=path)
    execution_connector = _require_string(payload, "execution_connector", errors=errors, path=path)
    if execution_connector and execution_connector != connector_name:
        errors.append(f"{path}.execution_connector debe coincidir con la clave del conector")
    _require_string(payload, "account_scope", errors=errors, path=path)
    _require_string(payload, "cost_model", errors=errors, path=path)
    _require_string(payload, "symbol_domain", errors=errors, path=path)
    _require_string(payload, "user_stream_mode", errors=errors, path=path)
    _require_bool(payload, "order_test_supported", errors=errors, path=path)
    live_capabilities = _require_string_list(payload, "live_capabilities", errors=errors, path=path)
    if live_capabilities and any(item not in {"paper", "testnet", "live"} for item in live_capabilities):
        errors.append(f"{path}.live_capabilities contiene valores invalidos")
    order_paths = _require_dict(payload, "order_paths", errors=errors, path=path)
    for key in ("paper", "testnet", "live"):
        order_path = _require_string(order_paths, key, errors=errors, path=f"{path}.order_paths")
        if order_path and order_path not in {"dry_run", "order_test", "live_submit"}:
            errors.append(f"{path}.order_paths.{key} debe ser dry_run, order_test o live_submit")
    market_ws = _require_dict(payload, "market_ws", errors=errors, path=path)
    _require_bool(market_ws, "enabled", errors=errors, path=f"{path}.market_ws")
    allowed_transports = _require_string_list(market_ws, "transport_modes_allowed", errors=errors, path=f"{path}.market_ws")
    if allowed_transports and any(item not in SUPPORTED_TRANSPORTS for item in allowed_transports):
        errors.append(f"{path}.market_ws.transport_modes_allowed contiene valores invalidos")
    default_transport = _require_string(market_ws, "default_transport", errors=errors, path=f"{path}.market_ws")
    if default_transport and default_transport not in SUPPORTED_TRANSPORTS:
        errors.append(f"{path}.market_ws.default_transport debe ser combined o raw")
    for key in (
        "live_ws_base_url",
        "testnet_ws_base_url",
        "ws_url_env_live",
        "ws_url_env_testnet",
        "raw_path",
        "combined_path_prefix",
    ):
        _require_string(market_ws, key, errors=errors, path=f"{path}.market_ws")
    required_streams = _require_string_list(market_ws, "required_streams", errors=errors, path=f"{path}.market_ws")
    if not required_streams:
        errors.append(f"{path}.market_ws.required_streams no puede quedar vacio")
    _require_string_list(market_ws, "optional_streams", errors=errors, path=f"{path}.market_ws")
    backoff = market_ws.get("market_ws_backoff_seconds")
    if not isinstance(backoff, list) or any(not isinstance(item, (int, float)) or float(item) <= 0 for item in backoff):
        errors.append(f"{path}.market_ws.market_ws_backoff_seconds debe ser lista de numeros positivos")
    for key in (
        "market_ws_jitter_pct",
        "market_ws_hard_recycle_hours",
        "ping_expectation_seconds",
        "pong_timeout_seconds",
        "stale_warn_ms",
        "stale_block_live_ms",
        "max_consecutive_ws_failures_before_block_live",
        "max_incoming_messages_per_sec",
        "max_streams_per_connection",
        "max_connection_attempts_per_5m_per_ip",
    ):
        _require_number(market_ws, key, errors=errors, path=f"{path}.market_ws")
    return errors


def _validate_binance_live_runtime_policy(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    root = payload.get("binance_live_runtime")
    if not isinstance(root, dict):
        return ["binance_live_runtime debe ser dict raiz"]
    connectors = _require_dict(root, "connectors", errors=errors, path="binance_live_runtime")
    for name in ("binance_spot", "binance_um_futures"):
        connector = _require_dict(connectors, name, errors=errors, path="binance_live_runtime.connectors")
        errors.extend(_validate_connector(name, connector))
    guardrails = _require_dict(root, "runtime_guardrails", errors=errors, path="binance_live_runtime")
    for key in (
        "block_live_on_stale_when_running",
        "block_live_after_failure_threshold",
        "mark_degraded_on_disconnect",
        "require_explicit_start",
        "public_smoke_supported",
    ):
        _require_bool(guardrails, key, errors=errors, path="binance_live_runtime.runtime_guardrails")
    return errors


def clear_binance_live_runtime_policy_cache() -> None:
    _load_binance_live_runtime_bundle_cached.cache_clear()


@lru_cache(maxsize=16)
def _load_binance_live_runtime_bundle_cached(repo_root_str: str, explicit_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    resolution = describe_policy_root_resolution(repo_root, explicit=explicit_root, expected_files=POLICY_EXPECTED_FILES)
    selected_root = Path(resolution["selected_root"]).resolve()
    policy_path = (selected_root / BINANCE_LIVE_RUNTIME_FILENAME).resolve()
    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    errors: list[str] = []
    warnings: list[str] = list(resolution.get("warnings") or [])
    if policy_path.exists():
        try:
            raw_bytes = policy_path.read_bytes()
            raw_text = raw_bytes.decode("utf-8")
            source_hash = hashlib.sha256(raw_bytes).hexdigest()
            raw = yaml.safe_load(raw_text) or {}
            validation_errors = _validate_binance_live_runtime_policy(raw) if isinstance(raw, dict) and raw else [
                f"{BINANCE_LIVE_RUNTIME_FILENAME} vacio o ausente"
            ]
            if isinstance(raw, dict) and raw and not validation_errors:
                payload = raw
                valid = True
            else:
                errors.extend(validation_errors)
        except Exception:
            errors.append(f"{BINANCE_LIVE_RUNTIME_FILENAME} no pudo parsearse como YAML valido")
    else:
        errors.append(f"{BINANCE_LIVE_RUNTIME_FILENAME} no existe en la raiz seleccionada")
    active_policy = copy.deepcopy(payload if valid else FAIL_CLOSED_MINIMAL_BINANCE_LIVE_RUNTIME_POLICY)
    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "fallback_used": bool(resolution.get("fallback_used")),
        "selected_role": resolution.get("selected_role"),
        "canonical_root": resolution.get("canonical_root"),
        "canonical_role": resolution.get("canonical_role"),
        "divergent_candidates": copy.deepcopy(resolution.get("divergent_candidates") or []),
        "source_hash": source_hash,
        "policy_hash": _stable_payload_hash(active_policy),
        "source": _policy_source_label(repo_root, policy_path) if valid else "default_fail_closed_minimal",
        "errors": errors,
        "warnings": warnings,
        "payload": active_policy,
    }


def load_binance_live_runtime_bundle(repo_root: Path | None = None, *, explicit_root: Path | None = None) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(_load_binance_live_runtime_bundle_cached(str(resolved_repo_root), explicit_root_str))


def binance_live_runtime_policy(repo_root: Path | None = None, *, explicit_root: Path | None = None) -> dict[str, Any]:
    bundle = load_binance_live_runtime_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("payload")
    return copy.deepcopy(payload if isinstance(payload, dict) else FAIL_CLOSED_MINIMAL_BINANCE_LIVE_RUNTIME_POLICY)


def _ws_root(base_url: str) -> tuple[str, str]:
    text = str(base_url or "").strip().rstrip("/")
    parsed = urlsplit(text)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}", parsed.path or ""
    return text, ""


def _stream_name(symbol: str, descriptor: str) -> str:
    return f"{str(symbol).lower()}@{descriptor}"


def _event_time_ms(payload: dict[str, Any]) -> int | None:
    for key in ("E", "T"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


class BinanceMarketWebSocketRuntime:
    def __init__(
        self,
        *,
        repo_root: Path,
        explicit_policy_root: Path | None = None,
        market_snapshot_writer: Callable[..., Any] | None = None,
        status_writer: Callable[..., Any] | None = None,
        connect_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.explicit_policy_root = explicit_policy_root.resolve() if explicit_policy_root is not None else None
        self._market_snapshot_writer = market_snapshot_writer
        self._status_writer = status_writer
        self._connect_factory = connect_factory or websocket_connect
        self._lock = threading.RLock()
        self._sessions: dict[tuple[str, str], dict[str, Any]] = {}

    def bundle(self) -> dict[str, Any]:
        return load_binance_live_runtime_bundle(self.repo_root, explicit_root=self.explicit_policy_root)

    def policy(self) -> dict[str, Any]:
        payload = binance_live_runtime_policy(self.repo_root, explicit_root=self.explicit_policy_root)
        return payload.get("binance_live_runtime") if isinstance(payload.get("binance_live_runtime"), dict) else {}

    def policy_source(self) -> dict[str, Any]:
        bundle = self.bundle()
        return {
            "path": bundle.get("path"),
            "source_root": bundle.get("source_root"),
            "source_hash": bundle.get("source_hash"),
            "policy_hash": bundle.get("policy_hash"),
            "source": bundle.get("source"),
            "valid": bool(bundle.get("valid")),
            "errors": list(bundle.get("errors") or []),
            "warnings": list(bundle.get("warnings") or []),
            "fallback_used": bool(bundle.get("fallback_used")),
            "selected_role": bundle.get("selected_role"),
            "canonical_root": bundle.get("canonical_root"),
            "canonical_role": bundle.get("canonical_role"),
            "divergent_candidates": copy.deepcopy(bundle.get("divergent_candidates") or []),
        }

    def policy_hash(self) -> str:
        return str(self.policy_source().get("policy_hash") or "")

    def policies_loaded(self) -> bool:
        return bool(self.policy_source().get("valid"))

    def _guardrails(self) -> dict[str, Any]:
        payload = self.policy().get("runtime_guardrails")
        return payload if isinstance(payload, dict) else {}

    def _connectors(self) -> dict[str, dict[str, Any]]:
        payload = self.policy().get("connectors")
        return payload if isinstance(payload, dict) else {}

    def connector_config(self, execution_connector: str) -> dict[str, Any]:
        payload = self._connectors().get(_normalize_connector(execution_connector))
        return copy.deepcopy(payload) if isinstance(payload, dict) else {}

    def family_split_summary(self) -> dict[str, Any]:
        connectors: dict[str, Any] = {}
        for name, payload in sorted(self._connectors().items()):
            if not isinstance(payload, dict):
                continue
            market_ws = payload.get("market_ws") if isinstance(payload.get("market_ws"), dict) else {}
            connectors[name] = {
                "vendor": payload.get("vendor"),
                "market_family": payload.get("market_family"),
                "repo_family": payload.get("repo_family"),
                "execution_connector": payload.get("execution_connector"),
                "account_scope": payload.get("account_scope"),
                "cost_model": payload.get("cost_model"),
                "symbol_domain": payload.get("symbol_domain"),
                "live_capabilities": list(payload.get("live_capabilities") or []),
                "user_stream_mode": payload.get("user_stream_mode"),
                "order_paths": copy.deepcopy(payload.get("order_paths") or {}),
                "order_test_supported": bool(payload.get("order_test_supported")),
                "market_ws_enabled": bool(market_ws.get("enabled")),
                "default_transport": market_ws.get("default_transport"),
                "required_streams": list(market_ws.get("required_streams") or []),
            }
        return {"source": self.policy_source(), "connectors": connectors}

    def _default_session_summary(
        self,
        *,
        connector: str,
        environment: str,
        cfg: dict[str, Any] | None = None,
        symbols: list[str] | None = None,
        transport_mode: str | None = None,
    ) -> dict[str, Any]:
        connector_cfg = cfg if isinstance(cfg, dict) else self.connector_config(connector)
        market_ws = connector_cfg.get("market_ws") if isinstance(connector_cfg.get("market_ws"), dict) else {}
        return {
            "execution_connector": connector,
            "vendor": connector_cfg.get("vendor"),
            "market_family": connector_cfg.get("market_family"),
            "repo_family": connector_cfg.get("repo_family"),
            "account_scope": connector_cfg.get("account_scope"),
            "cost_model": connector_cfg.get("cost_model"),
            "environment": environment,
            "policy_hash": self.policy_hash(),
            "policy_source": self.policy_source(),
            "configured": bool(connector_cfg),
            "available": False,
            "running": False,
            "connected": False,
            "degraded_mode": False,
            "block_live": False,
            "unsupported_mode": False,
            "reason": "not_started",
            "transport_mode": transport_mode or market_ws.get("default_transport") or "combined",
            "stream_names": [],
            "symbols_subscribed": list(symbols or []),
            "last_message_at": None,
            "last_message_kind": None,
            "last_message_stream": None,
            "stream_lag_estimate_ms": None,
            "reconnect_count": 0,
            "consecutive_failures": 0,
            "stale_ms": None,
            "stale_warn_ms": _safe_int(market_ws.get("stale_warn_ms"), 0),
            "stale_block_live_ms": _safe_int(market_ws.get("stale_block_live_ms"), 0),
            "ping_expectation_seconds": _safe_int(market_ws.get("ping_expectation_seconds"), 0),
            "pong_timeout_seconds": _safe_int(market_ws.get("pong_timeout_seconds"), 0),
            "hard_recycle_hours": _safe_float(market_ws.get("market_ws_hard_recycle_hours"), 0.0),
            "last_disconnect_reason": "",
            "last_connect_at": None,
            "last_disconnect_at": None,
            "message_limit_per_sec": _safe_int(market_ws.get("max_incoming_messages_per_sec"), 0),
            "max_streams_per_connection": _safe_int(market_ws.get("max_streams_per_connection"), 0),
            "max_connection_attempts_per_5m_per_ip": _safe_int(market_ws.get("max_connection_attempts_per_5m_per_ip"), 0),
            "transport_modes_allowed": list(market_ws.get("transport_modes_allowed") or []),
            "required_streams": list(market_ws.get("required_streams") or []),
            "mark_prices": {},
            "last_trade_prices": {},
            "best_quotes": {},
        }

    def _emit_status(self, summary: dict[str, Any]) -> None:
        if not callable(self._status_writer):
            return
        try:
            self._status_writer(
                family=str(summary.get("repo_family") or ""),
                environment=str(summary.get("environment") or ""),
                payload=copy.deepcopy(summary),
            )
        except Exception:
            return

    def _write_snapshot(self, summary: dict[str, Any], symbol: str, *, bid: Any, ask: Any, quote_ts_ms: int | None) -> None:
        if not callable(self._market_snapshot_writer):
            return
        try:
            self._market_snapshot_writer(
                family=str(summary.get("repo_family") or ""),
                environment=str(summary.get("environment") or ""),
                symbol=_canonical_symbol(symbol),
                bid=_safe_float(bid, 0.0) if bid is not None else None,
                ask=_safe_float(ask, 0.0) if ask is not None else None,
                quote_ts_ms=quote_ts_ms,
                orderbook_ts_ms=quote_ts_ms,
                source=f"market_ws:{summary.get('execution_connector')}:{summary.get('transport_mode')}:bookTicker",
            )
        except Exception:
            return

    def _stream_names(self, connector_cfg: dict[str, Any], symbols: list[str]) -> list[str]:
        market_ws = connector_cfg.get("market_ws") if isinstance(connector_cfg.get("market_ws"), dict) else {}
        descriptors = list(market_ws.get("required_streams") or [])
        out: list[str] = []
        for symbol in symbols:
            normalized = _canonical_symbol(symbol)
            for descriptor in descriptors:
                out.append(_stream_name(normalized, str(descriptor)))
        return out

    def _build_ws_url(self, connector_cfg: dict[str, Any], *, environment: str, transport_mode: str, stream_names: list[str]) -> str:
        market_ws = connector_cfg.get("market_ws") if isinstance(connector_cfg.get("market_ws"), dict) else {}
        env_key = str(market_ws.get("ws_url_env_testnet") if environment == "testnet" else market_ws.get("ws_url_env_live") or "").strip()
        override = str(os.getenv(env_key, "")).strip() if env_key else ""
        configured = str(market_ws.get("testnet_ws_base_url") if environment == "testnet" else market_ws.get("live_ws_base_url") or "").strip()
        root, path_hint = _ws_root(override or configured)
        raw_path = str(market_ws.get("raw_path") or "/ws").strip() or "/ws"
        combined_path_prefix = str(market_ws.get("combined_path_prefix") or "/stream?streams=").strip() or "/stream?streams="
        if transport_mode == "combined":
            return f"{root}{combined_path_prefix}{'/'.join(stream_names)}"
        return f"{root}{path_hint or raw_path}"

    def _update_message_state(
        self,
        summary: dict[str, Any],
        *,
        kind: str,
        stream: str,
        event_time_ms: int | None,
    ) -> None:
        now_ms = int(time.time() * 1000)
        summary["available"] = True
        summary["running"] = True
        summary["connected"] = True
        summary["degraded_mode"] = False
        summary["block_live"] = False
        summary["reason"] = "ok"
        summary["last_message_at"] = utc_now_iso()
        summary["last_message_kind"] = str(kind or "message")
        summary["last_message_stream"] = str(stream or "")
        summary["stream_lag_estimate_ms"] = None if event_time_ms is None else max(0, now_ms - int(event_time_ms))
        summary["stale_ms"] = 0
        summary["consecutive_failures"] = 0

    def _process_message(self, summary: dict[str, Any], message: Any, *, stream_names: list[str]) -> None:
        if isinstance(message, bytes):
            text = message.decode("utf-8", errors="ignore")
        else:
            text = str(message or "")
        if not text.strip():
            return
        try:
            parsed = json.loads(text)
        except Exception:
            summary["last_message_kind"] = "non_json"
            summary["last_message_at"] = utc_now_iso()
            return
        if isinstance(parsed, dict) and "stream" in parsed and isinstance(parsed.get("data"), dict):
            stream_name = str(parsed.get("stream") or "")
            payload = parsed.get("data") if isinstance(parsed.get("data"), dict) else {}
        else:
            stream_name = ""
            payload = parsed if isinstance(parsed, dict) else {}
        if not isinstance(payload, dict):
            return
        if "result" in payload and payload.get("result") is None and "id" in payload:
            self._update_message_state(summary, kind="subscribe_ack", stream=stream_name, event_time_ms=None)
            return

        symbol = _canonical_symbol(payload.get("s") or (stream_name.split("@", 1)[0] if "@" in stream_name else ""))
        event_name = str(payload.get("e") or "")
        event_time = _event_time_ms(payload)
        message_kind = event_name or ("bookTicker" if stream_name.endswith("@bookTicker") else "event")

        if symbol and (event_name == "bookTicker" or stream_name.endswith("@bookTicker")):
            bid = payload.get("b")
            ask = payload.get("a")
            summary["best_quotes"][symbol] = {
                "bid": _safe_float(bid, 0.0) if bid is not None else None,
                "ask": _safe_float(ask, 0.0) if ask is not None else None,
                "event_time_ms": event_time,
                "stream": stream_name,
            }
            self._write_snapshot(summary, symbol, bid=bid, ask=ask, quote_ts_ms=event_time)
        elif symbol and (event_name == "aggTrade" or stream_name.endswith("@aggTrade")):
            summary["last_trade_prices"][symbol] = {
                "price": _safe_float(payload.get("p"), 0.0) if payload.get("p") is not None else None,
                "quantity": _safe_float(payload.get("q"), 0.0) if payload.get("q") is not None else None,
                "event_time_ms": event_time,
                "stream": stream_name,
            }
        elif symbol and (event_name == "markPriceUpdate" or "markPrice" in stream_name):
            summary["mark_prices"][symbol] = {
                "mark_price": _safe_float(payload.get("p"), 0.0) if payload.get("p") is not None else None,
                "index_price": _safe_float(payload.get("i"), 0.0) if payload.get("i") is not None else None,
                "funding_rate": _safe_float(payload.get("r"), 0.0) if payload.get("r") is not None else None,
                "event_time_ms": event_time,
                "stream": stream_name,
            }

        self._update_message_state(summary, kind=message_kind, stream=stream_name or ",".join(stream_names), event_time_ms=event_time)

    def _backoff_schedule(self, connector_cfg: dict[str, Any]) -> list[float]:
        market_ws = connector_cfg.get("market_ws") if isinstance(connector_cfg.get("market_ws"), dict) else {}
        raw = market_ws.get("market_ws_backoff_seconds")
        if not isinstance(raw, list):
            return [1.0, 2.0, 4.0]
        values = [float(item) for item in raw if isinstance(item, (int, float)) and float(item) > 0.0]
        return values or [1.0, 2.0, 4.0]

    def _apply_runtime_flags(self, summary: dict[str, Any]) -> None:
        guardrails = self._guardrails()
        reference_dt = _parse_iso(summary.get("last_message_at")) or _parse_iso(summary.get("last_connect_at"))
        stale_ms = None
        if reference_dt is not None:
            stale_ms = max(0, int((_utc_now() - reference_dt).total_seconds() * 1000))
        summary["stale_ms"] = stale_ms
        stale_warn_ms = _safe_int(summary.get("stale_warn_ms"), 0)
        stale_block_ms = _safe_int(summary.get("stale_block_live_ms"), 0)
        failure_threshold = max(0, _safe_int(summary.get("failure_threshold"), 0))
        running = _bool(summary.get("running"))
        connected = _bool(summary.get("connected"))
        environment = _normalize_environment(summary.get("environment"))

        degraded = _bool(summary.get("degraded_mode"))
        block_live = _bool(summary.get("block_live"))
        reason = str(summary.get("reason") or "not_started")
        if running and not connected and _bool(guardrails.get("mark_degraded_on_disconnect")):
            degraded = True
            if reason in {"ok", "connected", "not_started"}:
                reason = "disconnected"
        if running and stale_ms is not None and stale_warn_ms > 0 and stale_ms >= stale_warn_ms:
            degraded = True
            if reason in {"ok", "connected", "not_started"}:
                reason = "stale_warn"
        if (
            running
            and environment == "live"
            and stale_ms is not None
            and stale_block_ms > 0
            and stale_ms >= stale_block_ms
            and _bool(guardrails.get("block_live_on_stale_when_running"))
        ):
            degraded = True
            block_live = True
            reason = "stale_block_live"
        if (
            running
            and environment == "live"
            and failure_threshold > 0
            and _safe_int(summary.get("consecutive_failures"), 0) >= failure_threshold
            and _bool(guardrails.get("block_live_after_failure_threshold"))
        ):
            degraded = True
            block_live = True
            reason = "failure_threshold_reached"
        summary["degraded_mode"] = degraded
        summary["block_live"] = block_live
        summary["reason"] = reason
        summary["available"] = _bool(summary.get("connected")) and not degraded and not block_live

    async def _session_loop(self, session_key: tuple[str, str]) -> None:
        with self._lock:
            session = self._sessions.get(session_key)
            if not isinstance(session, dict):
                return
            connector_cfg = copy.deepcopy(session.get("connector_cfg") or {})
            stream_names = list(session.get("stream_names") or [])
            stop_event = session.get("stop_event")
            summary = session.get("summary")
        if not isinstance(summary, dict) or not hasattr(stop_event, "is_set"):
            return
        market_ws = connector_cfg.get("market_ws") if isinstance(connector_cfg.get("market_ws"), dict) else {}
        backoff = self._backoff_schedule(connector_cfg)
        jitter_pct = max(0.0, _safe_float(market_ws.get("market_ws_jitter_pct"), 0.0))
        hard_recycle_seconds = max(0.0, _safe_float(summary.get("hard_recycle_hours"), 0.0) * 3600.0)

        with self._lock:
            summary["running"] = True
            summary["reason"] = "starting"
            self._apply_runtime_flags(summary)
            self._emit_status(summary)

        while not stop_event.is_set():
            transport_mode = _normalize_transport(summary.get("transport_mode"))
            ws_url = self._build_ws_url(
                connector_cfg,
                environment=_normalize_environment(summary.get("environment")),
                transport_mode=transport_mode,
                stream_names=stream_names,
            )
            try:
                async with self._connect_factory(
                    ws_url,
                    ping_interval=max(1, _safe_int(summary.get("ping_expectation_seconds"), 0)) or None,
                    ping_timeout=max(1, _safe_int(summary.get("pong_timeout_seconds"), 0)) or None,
                    close_timeout=5,
                    max_size=2**20,
                ) as websocket:
                    with self._lock:
                        summary["running"] = True
                        summary["connected"] = True
                        summary["available"] = True
                        summary["degraded_mode"] = False
                        summary["block_live"] = False
                        summary["reason"] = "connected"
                        summary["last_connect_at"] = utc_now_iso()
                        summary["consecutive_failures"] = 0
                        self._apply_runtime_flags(summary)
                        self._emit_status(summary)
                    if transport_mode == "raw":
                        await websocket.send(
                            _json_dumps(
                                {
                                    "method": "SUBSCRIBE",
                                    "params": stream_names,
                                    "id": int(time.time() * 1000),
                                }
                            )
                        )
                    connected_at = time.monotonic()
                    while not stop_event.is_set():
                        if hard_recycle_seconds > 0 and (time.monotonic() - connected_at) >= hard_recycle_seconds:
                            raise RuntimeError("hard_recycle")
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                            with self._lock:
                                self._process_message(summary, message, stream_names=stream_names)
                                self._apply_runtime_flags(summary)
                                self._emit_status(summary)
                        except asyncio.TimeoutError:
                            with self._lock:
                                self._apply_runtime_flags(summary)
                                self._emit_status(summary)
                            continue
                disconnect_reason = "closed"
            except ConnectionClosed as exc:
                disconnect_reason = f"connection_closed:{getattr(exc, 'code', '')}".rstrip(":")
            except Exception as exc:
                disconnect_reason = str(exc or exc.__class__.__name__).strip() or exc.__class__.__name__

            with self._lock:
                summary["connected"] = False
                summary["available"] = False
                summary["last_disconnect_at"] = utc_now_iso()
                summary["last_disconnect_reason"] = disconnect_reason
                if stop_event.is_set():
                    summary["reason"] = "stopped_by_operator"
                    summary["running"] = False
                    self._apply_runtime_flags(summary)
                    self._emit_status(summary)
                    break
                summary["reconnect_count"] = _safe_int(summary.get("reconnect_count"), 0) + 1
                summary["consecutive_failures"] = _safe_int(summary.get("consecutive_failures"), 0) + 1
                summary["reason"] = "reconnecting"
                self._apply_runtime_flags(summary)
                self._emit_status(summary)

            wait_seconds = backoff[min(max(_safe_int(summary.get("consecutive_failures"), 1) - 1, 0), len(backoff) - 1)]
            if jitter_pct > 0:
                wait_seconds = wait_seconds + (wait_seconds * jitter_pct * random.random())
            sleep_deadline = time.monotonic() + wait_seconds
            while not stop_event.is_set() and time.monotonic() < sleep_deadline:
                await asyncio.sleep(min(0.25, max(0.01, sleep_deadline - time.monotonic())))

        with self._lock:
            summary["running"] = False
            summary["connected"] = False
            if str(summary.get("reason") or "") in {"starting", "connected"}:
                summary["reason"] = "stopped_by_operator" if stop_event.is_set() else "stopped"
            self._apply_runtime_flags(summary)
            self._emit_status(summary)

    def start(
        self,
        *,
        execution_connector: str,
        environment: str,
        symbols: list[str],
        transport_mode: str | None = None,
    ) -> dict[str, Any]:
        connector = _normalize_connector(execution_connector)
        normalized_environment = _normalize_environment(environment)
        if not connector:
            raise ValueError("unsupported_execution_connector")
        if normalized_environment not in SUPPORTED_ENVIRONMENTS:
            raise ValueError("unsupported_environment")
        connector_cfg = self.connector_config(connector)
        if not connector_cfg:
            raise ValueError("connector_not_configured")
        market_ws = connector_cfg.get("market_ws") if isinstance(connector_cfg.get("market_ws"), dict) else {}
        if not _bool(market_ws.get("enabled")):
            raise RuntimeError("market_ws_disabled_by_policy")
        normalized_symbols = sorted({_canonical_symbol(symbol) for symbol in symbols if _canonical_symbol(symbol)})
        if not normalized_symbols:
            raise ValueError("symbols_required")
        stream_names = self._stream_names(connector_cfg, normalized_symbols)
        max_streams = max(0, _safe_int(market_ws.get("max_streams_per_connection"), 0))
        if max_streams > 0 and len(stream_names) > max_streams:
            raise ValueError("stream_limit_exceeded")
        selected_transport = _normalize_transport(transport_mode or market_ws.get("default_transport"))
        allowed = list(market_ws.get("transport_modes_allowed") or [])
        if allowed and selected_transport not in allowed:
            raise ValueError("transport_mode_not_allowed")
        session_key = (connector, normalized_environment)
        self.stop(execution_connector=connector, environment=normalized_environment, join_timeout_sec=0.5)
        summary = self._default_session_summary(
            connector=connector,
            environment=normalized_environment,
            cfg=connector_cfg,
            symbols=normalized_symbols,
            transport_mode=selected_transport,
        )
        summary["stream_names"] = list(stream_names)
        summary["failure_threshold"] = _safe_int(market_ws.get("max_consecutive_ws_failures_before_block_live"), 0)
        stop_event = threading.Event()

        def _runner() -> None:
            asyncio.run(self._session_loop(session_key))

        thread = threading.Thread(
            target=_runner,
            name=f"market-ws-{connector}-{normalized_environment}",
            daemon=True,
        )
        with self._lock:
            self._sessions[session_key] = {
                "connector_cfg": connector_cfg,
                "stream_names": list(stream_names),
                "stop_event": stop_event,
                "summary": summary,
                "thread": thread,
            }
            self._emit_status(summary)
        thread.start()
        return copy.deepcopy(summary)

    def stop(self, *, execution_connector: str, environment: str, join_timeout_sec: float = 2.0) -> dict[str, Any]:
        connector = _normalize_connector(execution_connector)
        normalized_environment = _normalize_environment(environment)
        if not connector:
            raise ValueError("unsupported_execution_connector")
        session_key = (connector, normalized_environment)
        with self._lock:
            session = self._sessions.get(session_key)
            if not isinstance(session, dict):
                return self._default_session_summary(connector=connector, environment=normalized_environment)
            stop_event = session.get("stop_event")
            thread = session.get("thread")
            summary = session.get("summary")
            if hasattr(stop_event, "set"):
                stop_event.set()
        if isinstance(thread, threading.Thread) and thread.is_alive():
            thread.join(timeout=max(0.1, float(join_timeout_sec)))
        with self._lock:
            session = self._sessions.get(session_key)
            if isinstance(session, dict) and isinstance(session.get("summary"), dict):
                summary = session["summary"]
                summary["running"] = False
                summary["connected"] = False
                summary["available"] = False
                summary["reason"] = "stopped_by_operator"
                summary["last_disconnect_at"] = utc_now_iso()
                self._apply_runtime_flags(summary)
                self._emit_status(summary)
                return copy.deepcopy(summary)
        return self._default_session_summary(connector=connector, environment=normalized_environment)

    def stop_all(self) -> list[dict[str, Any]]:
        with self._lock:
            keys = list(self._sessions.keys())
        return [self.stop(execution_connector=connector, environment=environment) for connector, environment in keys]

    def summary(self) -> dict[str, Any]:
        with self._lock:
            sessions = []
            for row in sorted(
                (copy.deepcopy(session.get("summary") or {}) for session in self._sessions.values() if isinstance(session, dict)),
                key=lambda item: (str(item.get("execution_connector") or ""), str(item.get("environment") or "")),
            ):
                if isinstance(row, dict):
                    self._apply_runtime_flags(row)
                    sessions.append(row)
        return {
            "policy_loaded": self.policies_loaded(),
            "policy_hash": self.policy_hash(),
            "policy_source": self.policy_source(),
            "runtime_guardrails": copy.deepcopy(self._guardrails()),
            "family_split": self.family_split_summary().get("connectors") or {},
            "sessions": sessions,
        }

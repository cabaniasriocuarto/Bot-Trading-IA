from __future__ import annotations

import asyncio
import copy
import json
import random
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosed

from rtlab_core.execution.live_market_runtime import (
    SUPPORTED_ENVIRONMENTS,
    SUPPORTED_USER_STREAM_MODES,
    _bool,
    _event_time_ms,
    _normalize_connector,
    _normalize_environment,
    _parse_iso,
    _safe_float,
    _safe_int,
    _ws_root,
    load_binance_live_runtime_bundle,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return _utc_now().isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


class BinanceUserStreamRuntime:
    def __init__(
        self,
        *,
        repo_root: Path,
        explicit_policy_root: Path | None = None,
        status_writer: Callable[[str, str, dict[str, Any]], Any] | None = None,
        event_ingestor: Callable[[str, str, dict[str, Any]], Any] | None = None,
        api_key_requester: Callable[..., tuple[Any, dict[str, Any]]] | None = None,
        signed_ws_params_builder: Callable[..., tuple[dict[str, Any] | None, dict[str, Any]]] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.explicit_policy_root = explicit_policy_root.resolve() if explicit_policy_root is not None else None
        self._status_writer = status_writer
        self._event_ingestor = event_ingestor
        self._api_key_requester = api_key_requester
        self._signed_ws_params_builder = signed_ws_params_builder
        self._connect_factory = websocket_connect
        self._lock = threading.RLock()
        self._sessions: dict[tuple[str, str], dict[str, Any]] = {}

    def bundle(self) -> dict[str, Any]:
        return load_binance_live_runtime_bundle(self.repo_root, explicit_root=self.explicit_policy_root)

    def policy(self) -> dict[str, Any]:
        bundle = self.bundle()
        payload = bundle.get("payload")
        runtime = payload.get("binance_live_runtime") if isinstance(payload, dict) else None
        return copy.deepcopy(runtime if isinstance(runtime, dict) else {})

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
        return copy.deepcopy(payload if isinstance(payload, dict) else {})

    def _user_stream_cfg(self, connector_cfg: dict[str, Any]) -> dict[str, Any]:
        payload = connector_cfg.get("user_stream")
        return payload if isinstance(payload, dict) else {}

    def _default_session_summary(
        self,
        *,
        connector: str,
        environment: str,
        cfg: dict[str, Any] | None = None,
        user_stream_mode: str | None = None,
    ) -> dict[str, Any]:
        connector_cfg = cfg if isinstance(cfg, dict) else self.connector_config(connector)
        user_cfg = self._user_stream_cfg(connector_cfg)
        selected_mode = str(user_stream_mode or connector_cfg.get("user_stream_mode") or user_cfg.get("default_mode") or "").strip()
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
            "user_stream_mode": selected_mode,
            "supported_modes": list(user_cfg.get("supported_modes") or []),
            "subscription_id": None,
            "listen_key": None,
            "last_message_at": None,
            "last_event_name": None,
            "last_disconnect_reason": "",
            "last_connect_at": None,
            "last_disconnect_at": None,
            "reconnect_count": 0,
            "consecutive_failures": 0,
            "failure_threshold": _safe_int(user_cfg.get("max_consecutive_failures_before_degraded"), 0),
            "stale_ms": None,
            "stale_warn_ms": _safe_int(user_cfg.get("stale_warn_ms"), 0),
            "stale_block_live_ms": _safe_int(user_cfg.get("stale_block_live_ms"), 0),
            "ping_expectation_seconds": _safe_int(user_cfg.get("ping_expectation_seconds"), 0),
            "pong_timeout_seconds": _safe_int(user_cfg.get("pong_timeout_seconds"), 0),
            "hard_recycle_hours": _safe_float(user_cfg.get("user_stream_hard_recycle_hours"), 0.0),
            "keepalive_interval_sec": _safe_float(user_cfg.get("keepalive_interval_sec"), 0.0),
            "last_keepalive_at": None,
            "last_keepalive_result": None,
            "last_keepalive_reason": "",
            "subscription_limit": _safe_int(user_cfg.get("max_subscriptions_per_connection"), 0),
            "subscription_lifetime_limit": _safe_int(user_cfg.get("max_lifetime_subscriptions_per_connection"), 0),
            "ws_url": None,
            "stream_lag_estimate_ms": None,
            "event_counters": {"order": 0, "account": 0, "other": 0},
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

    def _apply_runtime_flags(self, summary: dict[str, Any]) -> None:
        guardrails = self._guardrails()
        reference_dt = _parse_iso(summary.get("last_message_at")) or _parse_iso(summary.get("last_connect_at"))
        stale_ms = None
        if reference_dt is not None:
            stale_ms = max(0, int((_utc_now() - reference_dt).total_seconds() * 1000))
        summary["stale_ms"] = stale_ms
        stale_warn_ms = _safe_int(summary.get("stale_warn_ms"), 0)
        stale_block_ms = _safe_int(summary.get("stale_block_live_ms"), 0)
        failure_threshold = _safe_int(summary.get("failure_threshold"), 0)
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

    def _build_ws_url(self, user_cfg: dict[str, Any], *, environment: str, mode: str, listen_key: str | None = None) -> str:
        import os

        env_key = str(user_cfg.get("ws_url_env_testnet") if environment == "testnet" else user_cfg.get("ws_url_env_live") or "").strip()
        override = str(os.getenv(env_key, "")).strip() if env_key else ""
        configured = str(user_cfg.get("testnet_ws_base_url") if environment == "testnet" else user_cfg.get("live_ws_base_url") or "").strip()
        root, path_hint = _ws_root(override or configured)
        if mode == "futures_listenkey":
            if not listen_key:
                raise RuntimeError("listen_key_missing")
            return f"{root}/ws/{listen_key}"
        return f"{root}{path_hint or '/ws-api/v3'}"

    def _handle_spot_control_message(self, summary: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        if result and result.get("subscriptionId") is not None:
            summary["subscription_id"] = int(result.get("subscriptionId"))
            summary["available"] = True
            summary["running"] = True
            summary["connected"] = True
            summary["degraded_mode"] = False
            summary["block_live"] = False
            summary["reason"] = "ok"
            summary["last_message_at"] = utc_now_iso()
            summary["last_event_name"] = "subscribe_ack"
            return None, "subscribe_ack"
        if int(payload.get("status") or 0) >= 400:
            error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
            code = error.get("code")
            reason = str(error.get("msg") or payload.get("error") or f"ws_api_status_{payload.get('status')}").strip()
            raise RuntimeError(f"spot_ws_api_error:{code}:{reason}".rstrip(":"))
        event = payload.get("event") if isinstance(payload.get("event"), dict) else None
        if isinstance(event, dict):
            if payload.get("subscriptionId") is not None:
                summary["subscription_id"] = int(payload.get("subscriptionId"))
            return copy.deepcopy(event), str(event.get("e") or "event")
        if str(payload.get("e") or "").strip():
            return copy.deepcopy(payload), str(payload.get("e") or "event")
        return None, None

    def _process_event(self, summary: dict[str, Any], message: Any) -> None:
        if isinstance(message, bytes):
            text = message.decode("utf-8", errors="ignore")
        else:
            text = str(message or "")
        if not text.strip():
            return
        try:
            parsed = json.loads(text)
        except Exception:
            summary["last_message_at"] = utc_now_iso()
            summary["last_event_name"] = "non_json"
            return
        if not isinstance(parsed, dict):
            return

        mode = str(summary.get("user_stream_mode") or "").strip()
        raw_wrapper = copy.deepcopy(parsed)
        event_payload: dict[str, Any] | None = None
        event_name = None
        if mode == "websocket_api_spot":
            event_payload, event_name = self._handle_spot_control_message(summary, parsed)
        else:
            event_payload = copy.deepcopy(parsed)
            event_name = str(parsed.get("e") or "")
        if not isinstance(event_payload, dict):
            return

        summary["available"] = True
        summary["running"] = True
        summary["connected"] = True
        summary["degraded_mode"] = False
        summary["block_live"] = False
        summary["reason"] = "ok"
        summary["last_message_at"] = utc_now_iso()
        summary["last_event_name"] = event_name or "event"
        summary["consecutive_failures"] = 0

        event_time = _event_time_ms(event_payload)
        if event_time is not None:
            summary["stream_lag_estimate_ms"] = max(0, int(time.time() * 1000) - int(event_time))

        counters = summary.get("event_counters") if isinstance(summary.get("event_counters"), dict) else {}
        account_events = {"outboundAccountPosition", "balanceUpdate", "externalLockUpdate", "ACCOUNT_UPDATE", "MARGIN_CALL"}
        order_events = {"executionReport", "ORDER_TRADE_UPDATE", "TRADE_LITE"}
        if event_name in order_events:
            counters["order"] = _safe_int(counters.get("order"), 0) + 1
        elif event_name in account_events:
            counters["account"] = _safe_int(counters.get("account"), 0) + 1
        else:
            counters["other"] = _safe_int(counters.get("other"), 0) + 1
        summary["event_counters"] = counters

        if callable(self._event_ingestor):
            enriched = copy.deepcopy(event_payload)
            enriched["_rtlab_user_stream"] = {
                "execution_connector": summary.get("execution_connector"),
                "user_stream_mode": summary.get("user_stream_mode"),
                "subscription_id": summary.get("subscription_id"),
                "listen_key": summary.get("listen_key"),
                "raw_wrapper": raw_wrapper,
                "received_at": utc_now_iso(),
            }
            self._event_ingestor(
                str(summary.get("repo_family") or ""),
                str(summary.get("environment") or ""),
                enriched,
            )

        if event_name in {"eventStreamTerminated", "listenKeyExpired"}:
            raise RuntimeError(event_name)

    async def _spot_unsubscribe(self, websocket: Any, summary: dict[str, Any]) -> None:
        subscription_id = summary.get("subscription_id")
        if subscription_id is None:
            return
        payload = {
            "id": str(uuid4()),
            "method": "userDataStream.unsubscribe",
            "params": {"subscriptionId": int(subscription_id)},
        }
        await websocket.send(_json_dumps(payload))

    def _close_futures_listen_key(self, summary: dict[str, Any], control_endpoints: dict[str, str]) -> None:
        if not callable(self._api_key_requester):
            return
        close_endpoint = str(control_endpoints.get("close") or "").strip()
        if not close_endpoint or not str(summary.get("listen_key") or "").strip():
            return
        try:
            self._api_key_requester(
                "DELETE",
                close_endpoint,
                family=str(summary.get("repo_family") or ""),
                environment=str(summary.get("environment") or ""),
                params=None,
            )
        except Exception:
            return

    def _prepare_transport(
        self,
        *,
        connector_cfg: dict[str, Any],
        summary: dict[str, Any],
        control_endpoints: dict[str, str],
    ) -> tuple[str, dict[str, Any]]:
        mode = str(summary.get("user_stream_mode") or "").strip()
        user_cfg = self._user_stream_cfg(connector_cfg)
        family = str(summary.get("repo_family") or "")
        environment = str(summary.get("environment") or "")
        if mode == "websocket_api_spot":
            if not callable(self._signed_ws_params_builder):
                raise RuntimeError("signed_ws_params_builder_missing")
            signed_params, meta = self._signed_ws_params_builder(family=family, environment=environment, params={})
            if not meta.get("ok") or not isinstance(signed_params, dict):
                raise RuntimeError(str(meta.get("reason") or "spot_signature_failed"))
            return self._build_ws_url(user_cfg, environment=environment, mode=mode), {
                "subscribe_message": {
                    "id": str(uuid4()),
                    "method": "userDataStream.subscribe.signature",
                    "params": signed_params,
                }
            }
        if mode == "futures_listenkey":
            if not callable(self._api_key_requester):
                raise RuntimeError("api_key_requester_missing")
            start_endpoint = str(control_endpoints.get("start") or "").strip()
            if not start_endpoint:
                raise RuntimeError("futures_listenkey_endpoint_missing")
            payload, meta = self._api_key_requester(
                "POST",
                start_endpoint,
                family=family,
                environment=environment,
                params=None,
            )
            listen_key = str((payload or {}).get("listenKey") or "").strip() if isinstance(payload, dict) else ""
            if not meta.get("ok") or not listen_key:
                raise RuntimeError(str(meta.get("reason") or "listenkey_start_failed"))
            summary["listen_key"] = listen_key
            return self._build_ws_url(user_cfg, environment=environment, mode=mode, listen_key=listen_key), {}
        if mode == "legacy_listenkey":
            summary["unsupported_mode"] = True
            summary["degraded_mode"] = True
            summary["block_live"] = _normalize_environment(environment) == "live"
            summary["reason"] = "legacy_listenkey_not_implemented"
            raise RuntimeError("legacy_listenkey_not_implemented")
        raise RuntimeError("unsupported_user_stream_mode")

    async def _session_loop(self, session_key: tuple[str, str]) -> None:
        with self._lock:
            session = self._sessions.get(session_key)
            if not isinstance(session, dict):
                return
            connector_cfg = copy.deepcopy(session.get("connector_cfg") or {})
            control_endpoints = copy.deepcopy(session.get("control_endpoints") or {})
            stop_event = session.get("stop_event")
            summary = session.get("summary")
        if not isinstance(summary, dict) or not hasattr(stop_event, "is_set"):
            return
        user_cfg = self._user_stream_cfg(connector_cfg)
        backoff = [float(item) for item in list(user_cfg.get("user_stream_backoff_seconds") or []) if _safe_float(item, 0.0) > 0.0] or [1.0, 2.0, 4.0]
        jitter_pct = max(0.0, _safe_float(user_cfg.get("user_stream_jitter_pct"), 0.0))
        hard_recycle_seconds = max(0.0, _safe_float(summary.get("hard_recycle_hours"), 0.0) * 3600.0)
        keepalive_interval_sec = max(0.0, _safe_float(summary.get("keepalive_interval_sec"), 0.0))

        with self._lock:
            summary["running"] = True
            summary["reason"] = "starting"
            self._apply_runtime_flags(summary)
            self._emit_status(summary)

        while not stop_event.is_set():
            terminal_unsupported_mode = False
            try:
                ws_url, transport_meta = self._prepare_transport(
                    connector_cfg=connector_cfg,
                    summary=summary,
                    control_endpoints=control_endpoints,
                )
                summary["ws_url"] = ws_url
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
                    subscribe_message = transport_meta.get("subscribe_message") if isinstance(transport_meta, dict) else None
                    if isinstance(subscribe_message, dict):
                        await websocket.send(_json_dumps(subscribe_message))
                    connected_at = time.monotonic()
                    next_keepalive_at = time.monotonic() + keepalive_interval_sec if keepalive_interval_sec > 0 else None
                    while not stop_event.is_set():
                        if hard_recycle_seconds > 0 and (time.monotonic() - connected_at) >= hard_recycle_seconds:
                            raise RuntimeError("hard_recycle")
                        if (
                            str(summary.get("user_stream_mode") or "") == "futures_listenkey"
                            and next_keepalive_at is not None
                            and time.monotonic() >= next_keepalive_at
                        ):
                            if not callable(self._api_key_requester):
                                raise RuntimeError("api_key_requester_missing")
                            keepalive_endpoint = str(control_endpoints.get("keepalive") or "").strip()
                            if not keepalive_endpoint:
                                raise RuntimeError("listenkey_keepalive_endpoint_missing")
                            payload, meta = self._api_key_requester(
                                "PUT",
                                keepalive_endpoint,
                                family=str(summary.get("repo_family") or ""),
                                environment=str(summary.get("environment") or ""),
                                params=None,
                            )
                            with self._lock:
                                summary["last_keepalive_at"] = utc_now_iso()
                                summary["last_keepalive_result"] = bool(meta.get("ok"))
                                summary["last_keepalive_reason"] = str(meta.get("reason") or "ok")
                                if isinstance(payload, dict) and payload.get("listenKey"):
                                    summary["listen_key"] = str(payload.get("listenKey"))
                            if not meta.get("ok"):
                                raise RuntimeError(str(meta.get("reason") or "listenkey_keepalive_failed"))
                            next_keepalive_at = time.monotonic() + keepalive_interval_sec
                        try:
                            message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                            with self._lock:
                                self._process_event(summary, message)
                                self._apply_runtime_flags(summary)
                                self._emit_status(summary)
                        except asyncio.TimeoutError:
                            with self._lock:
                                self._apply_runtime_flags(summary)
                                self._emit_status(summary)
                            continue
                    if str(summary.get("user_stream_mode") or "") == "websocket_api_spot":
                        try:
                            await self._spot_unsubscribe(websocket, summary)
                        except Exception:
                            pass
                disconnect_reason = "closed"
            except ConnectionClosed as exc:
                disconnect_reason = f"connection_closed:{getattr(exc, 'code', '')}".rstrip(":")
            except Exception as exc:
                disconnect_reason = str(exc or exc.__class__.__name__).strip() or exc.__class__.__name__
                if disconnect_reason in {"legacy_listenkey_not_implemented", "unsupported_user_stream_mode"}:
                    terminal_unsupported_mode = True

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
                if terminal_unsupported_mode:
                    summary["running"] = False
                    summary["degraded_mode"] = True
                    summary["block_live"] = _normalize_environment(summary.get("environment")) == "live"
                    summary["unsupported_mode"] = True
                    summary["reason"] = disconnect_reason
                    self._apply_runtime_flags(summary)
                    self._emit_status(summary)
                    break
                summary["reconnect_count"] = _safe_int(summary.get("reconnect_count"), 0) + 1
                summary["consecutive_failures"] = _safe_int(summary.get("consecutive_failures"), 0) + 1
                summary["reason"] = "reconnecting"
                if disconnect_reason in {"listenKeyExpired", "eventStreamTerminated"}:
                    summary["degraded_mode"] = True
                self._apply_runtime_flags(summary)
                self._emit_status(summary)

            wait_seconds = backoff[min(max(_safe_int(summary.get("consecutive_failures"), 1) - 1, 0), len(backoff) - 1)]
            if jitter_pct > 0:
                wait_seconds = wait_seconds + (wait_seconds * jitter_pct * random.random())
            sleep_deadline = time.monotonic() + wait_seconds
            while not stop_event.is_set() and time.monotonic() < sleep_deadline:
                await asyncio.sleep(min(0.25, max(0.01, sleep_deadline - time.monotonic())))

        if str(summary.get("user_stream_mode") or "") == "futures_listenkey":
            self._close_futures_listen_key(summary, control_endpoints)
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
        user_stream_mode: str | None = None,
        control_endpoints: dict[str, str] | None = None,
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
        user_cfg = self._user_stream_cfg(connector_cfg)
        if not _bool(user_cfg.get("enabled")):
            raise RuntimeError("user_stream_disabled_by_policy")
        selected_mode = str(user_stream_mode or connector_cfg.get("user_stream_mode") or user_cfg.get("default_mode") or "").strip()
        if selected_mode not in SUPPORTED_USER_STREAM_MODES:
            raise ValueError("unsupported_user_stream_mode")
        supported_modes = list(user_cfg.get("supported_modes") or [])
        if supported_modes and selected_mode not in supported_modes:
            raise ValueError("user_stream_mode_not_allowed")

        session_key = (connector, normalized_environment)
        self.stop(execution_connector=connector, environment=normalized_environment, join_timeout_sec=0.5)
        summary = self._default_session_summary(
            connector=connector,
            environment=normalized_environment,
            cfg=connector_cfg,
            user_stream_mode=selected_mode,
        )
        stop_event = threading.Event()

        def _runner() -> None:
            asyncio.run(self._session_loop(session_key))

        thread = threading.Thread(
            target=_runner,
            name=f"user-stream-{connector}-{normalized_environment}",
            daemon=True,
        )
        with self._lock:
            self._sessions[session_key] = {
                "connector_cfg": connector_cfg,
                "control_endpoints": copy.deepcopy(control_endpoints or {}),
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
        family_split: dict[str, Any] = {}
        for name, payload in sorted(self._connectors().items()):
            if not isinstance(payload, dict):
                continue
            user_cfg = self._user_stream_cfg(payload)
            family_split[name] = {
                "vendor": payload.get("vendor"),
                "market_family": payload.get("market_family"),
                "repo_family": payload.get("repo_family"),
                "execution_connector": payload.get("execution_connector"),
                "account_scope": payload.get("account_scope"),
                "cost_model": payload.get("cost_model"),
                "live_capabilities": list(payload.get("live_capabilities") or []),
                "user_stream_mode": payload.get("user_stream_mode"),
                "user_stream_enabled": bool(user_cfg.get("enabled")),
                "user_stream_default_mode": user_cfg.get("default_mode"),
                "user_stream_supported_modes": list(user_cfg.get("supported_modes") or []),
            }
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
            "family_split": family_split,
            "sessions": sessions,
        }

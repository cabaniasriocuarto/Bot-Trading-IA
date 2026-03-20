from __future__ import annotations

import copy
import hashlib
import hmac
import time
from typing import Any, Callable
from urllib.parse import urlencode

import requests


MAX_RECV_WINDOW_MS = 60000


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _response_payload(response: requests.Response) -> Any:
    try:
        return response.json() if getattr(response, "content", b"") else {}
    except Exception:
        text = str(getattr(response, "text", "") or "").strip()
        return {"raw": text[:500]} if text else {}


def _normalize_family(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"spot", "margin", "usdm_futures", "coinm_futures"} else ""


def _normalize_environment(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"live", "testnet"} else "live"


def _clamp_recv_window_ms(value: Any) -> int:
    numeric = int(max(1.0, _safe_float(value, 5000.0)))
    return min(MAX_RECV_WINDOW_MS, numeric)


def _payload_error_fields(payload: Any) -> tuple[int | None, str]:
    if not isinstance(payload, dict):
        return None, ""
    code = payload.get("code")
    try:
        code_int = int(code) if code is not None else None
    except Exception:
        code_int = None
    return code_int, str(payload.get("msg") or "").strip()


def map_exchange_error(status_code: int, payload: Any) -> dict[str, Any]:
    code, message = _payload_error_fields(payload)
    lower = message.lower()
    if status_code == 451:
        return {
            "reason": "provider_restriction",
            "error_category": "provider_restriction",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "provider restriction",
        }
    if code in {-1021}:
        return {
            "reason": "invalid_timestamp",
            "error_category": "timing",
            "retryable": True,
            "exchange_code": code,
            "exchange_msg": message or "invalid timestamp",
        }
    if code in {-1022}:
        return {
            "reason": "invalid_signature",
            "error_category": "auth",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "invalid signature",
        }
    if code in {-1002, -2014, -2015} or status_code in {401, 403}:
        return {
            "reason": "auth_rejected",
            "error_category": "auth",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "auth rejected",
        }
    if code in {-1003, -1015} or status_code in {418, 429}:
        return {
            "reason": "rate_limit",
            "error_category": "rate_limit",
            "retryable": True,
            "exchange_code": code,
            "exchange_msg": message or "rate limit",
        }
    if code in {-2013}:
        return {
            "reason": "no_such_order",
            "error_category": "order_lifecycle",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "no such order",
        }
    if code in {-2011}:
        return {
            "reason": "cancel_rejected",
            "error_category": "order_lifecycle",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "cancel rejected",
        }
    if code in {-2010}:
        return {
            "reason": "new_order_rejected",
            "error_category": "order_lifecycle",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "new order rejected",
        }
    if code in {-2018}:
        return {
            "reason": "insufficient_balance",
            "error_category": "risk",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "insufficient balance",
        }
    if code in {-2019}:
        return {
            "reason": "insufficient_margin",
            "error_category": "risk",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "insufficient margin",
        }
    if code in {-1013} or "filter failure" in lower:
        return {
            "reason": "filter_rejected",
            "error_category": "filters",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "filter rejected",
        }
    if code in {
        -1100,
        -1101,
        -1102,
        -1103,
        -1104,
        -1105,
        -1106,
        -1111,
        -1115,
        -1116,
        -1117,
        -1121,
        -1128,
        -1130,
        -1145,
    }:
        return {
            "reason": "invalid_request",
            "error_category": "request",
            "retryable": False,
            "exchange_code": code,
            "exchange_msg": message or "invalid request",
        }
    if code in {-1000, -1001, -1006, -1007, -1008} or status_code >= 500:
        return {
            "reason": "exchange_unavailable",
            "error_category": "endpoint",
            "retryable": True,
            "exchange_code": code,
            "exchange_msg": message or f"HTTP {status_code}",
        }
    return {
        "reason": "exchange_rejected",
        "error_category": "endpoint",
        "retryable": 400 <= int(status_code or 0) < 500 and status_code not in {401, 403, 418, 429},
        "exchange_code": code,
        "exchange_msg": message or f"HTTP {status_code}",
    }


class BinanceLiveAdapter:
    def __init__(
        self,
        *,
        credential_resolver: Callable[[str, str], tuple[str, str, list[str]]],
        request_timeout_resolver: Callable[[], float],
        recv_window_resolver: Callable[[], float],
        server_time_url_resolver: Callable[[str, str], str],
        server_time_sync_enabled_resolver: Callable[[], bool],
        require_server_time_sync_resolver: Callable[[str], bool],
        server_time_cache_sec_resolver: Callable[[], float],
        max_clock_skew_ms_resolver: Callable[[], float],
        retry_invalid_timestamp_once_resolver: Callable[[], bool],
    ) -> None:
        self._credential_resolver = credential_resolver
        self._request_timeout_resolver = request_timeout_resolver
        self._recv_window_resolver = recv_window_resolver
        self._server_time_url_resolver = server_time_url_resolver
        self._server_time_sync_enabled_resolver = server_time_sync_enabled_resolver
        self._require_server_time_sync_resolver = require_server_time_sync_resolver
        self._server_time_cache_sec_resolver = server_time_cache_sec_resolver
        self._max_clock_skew_ms_resolver = max_clock_skew_ms_resolver
        self._retry_invalid_timestamp_once_resolver = retry_invalid_timestamp_once_resolver
        self._server_time_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def cache_status(self) -> list[dict[str, Any]]:
        now_ms = _now_ms()
        out: list[dict[str, Any]] = []
        for (family, environment), payload in sorted(self._server_time_cache.items()):
            synced_at_ms = int(payload.get("synced_at_ms") or now_ms)
            out.append(
                {
                    "family": family,
                    "environment": environment,
                    "server_time_ms": payload.get("server_time_ms"),
                    "offset_ms": payload.get("offset_ms"),
                    "synced_at_ms": synced_at_ms,
                    "age_ms": max(0, now_ms - synced_at_ms),
                    "within_threshold": bool(payload.get("within_threshold")),
                    "threshold_ms": payload.get("threshold_ms"),
                }
            )
        return out

    def public_request(
        self,
        method: str,
        endpoint_url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        if not endpoint_url:
            return None, {
                "ok": False,
                "reason": "missing_endpoint",
                "error_category": "endpoint",
                "retryable": False,
                "endpoint": endpoint_url,
                "method": str(method or "").upper(),
            }
        filtered = {
            str(key): value
            for key, value in (params or {}).items()
            if value is not None and str(value) != ""
        }
        try:
            response = requests.request(
                str(method or "GET").upper(),
                endpoint_url,
                params=filtered or None,
                timeout=float(self._request_timeout_resolver()),
            )
        except requests.RequestException as exc:
            return None, {
                "ok": False,
                "reason": "request_exception",
                "error_category": "endpoint",
                "retryable": True,
                "endpoint": endpoint_url,
                "method": str(method or "").upper(),
                "error": str(exc),
            }
        payload = _response_payload(response)
        if 200 <= int(response.status_code) < 300:
            return payload, {
                "ok": True,
                "reason": "ok",
                "error_category": None,
                "retryable": False,
                "endpoint": endpoint_url,
                "method": str(method or "").upper(),
                "status_code": int(response.status_code),
            }
        mapped = map_exchange_error(int(response.status_code), payload)
        return None, {
            "ok": False,
            "endpoint": endpoint_url,
            "method": str(method or "").upper(),
            "status_code": int(response.status_code),
            "exchange_payload": copy.deepcopy(payload),
            **mapped,
        }

    def sync_server_time(
        self,
        family: str,
        environment: str,
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        cache_key = (normalized_family, normalized_environment)
        now_ms = _now_ms()
        cache_ttl_ms = int(max(1.0, _safe_float(self._server_time_cache_sec_resolver(), 30.0)) * 1000.0)
        cached = copy.deepcopy(self._server_time_cache.get(cache_key) or {})
        if cached and not force:
            synced_at_ms = int(cached.get("synced_at_ms") or now_ms)
            age_ms = max(0, now_ms - synced_at_ms)
            if age_ms <= cache_ttl_ms:
                cached["ok"] = True
                cached["reason"] = "ok"
                cached["cached"] = True
                cached["age_ms"] = age_ms
                return cached

        endpoint_url = str(self._server_time_url_resolver(normalized_family, normalized_environment) or "").strip()
        if not endpoint_url:
            return {
                "ok": False,
                "reason": "missing_server_time_endpoint",
                "endpoint": endpoint_url,
                "family": normalized_family,
                "environment": normalized_environment,
            }
        try:
            local_before_ms = _now_ms()
            response = requests.request(
                "GET",
                endpoint_url,
                timeout=float(self._request_timeout_resolver()),
            )
            payload = _response_payload(response)
            if not (200 <= int(response.status_code) < 300):
                mapped = map_exchange_error(int(response.status_code), payload)
                if cached:
                    cached.update(
                        {
                            "ok": False,
                            "reason": mapped.get("reason"),
                            "cached": True,
                            "age_ms": max(0, now_ms - int(cached.get("synced_at_ms") or now_ms)),
                            "warning": "using_stale_server_time_cache",
                        }
                    )
                    return cached
                return {
                    "ok": False,
                    "endpoint": endpoint_url,
                    "family": normalized_family,
                    "environment": normalized_environment,
                    "exchange_payload": copy.deepcopy(payload),
                    **mapped,
                }
            server_time_ms = int(_safe_float((payload or {}).get("serverTime"), 0.0))
            if server_time_ms <= 0:
                if cached:
                    cached.update(
                        {
                            "ok": False,
                            "reason": "server_time_missing",
                            "cached": True,
                            "age_ms": max(0, now_ms - int(cached.get("synced_at_ms") or now_ms)),
                            "warning": "using_stale_server_time_cache",
                        }
                    )
                    return cached
                return {
                    "ok": False,
                    "reason": "server_time_missing",
                    "endpoint": endpoint_url,
                    "family": normalized_family,
                    "environment": normalized_environment,
                }
            local_after_ms = _now_ms()
            local_now_ms = int((local_before_ms + local_after_ms) / 2)
            offset_ms = int(server_time_ms - local_now_ms)
            threshold_ms = int(max(0.0, _safe_float(self._max_clock_skew_ms_resolver(), 1000.0)))
            payload_out = {
                "ok": True,
                "reason": "ok",
                "cached": False,
                "endpoint": endpoint_url,
                "family": normalized_family,
                "environment": normalized_environment,
                "server_time_ms": server_time_ms,
                "local_time_ms": local_now_ms,
                "offset_ms": offset_ms,
                "synced_at_ms": now_ms,
                "age_ms": 0,
                "within_threshold": abs(offset_ms) <= threshold_ms,
                "threshold_ms": threshold_ms,
            }
            self._server_time_cache[cache_key] = copy.deepcopy(payload_out)
            return payload_out
        except requests.RequestException as exc:
            if cached:
                cached.update(
                    {
                        "ok": False,
                        "reason": "server_time_sync_failed",
                        "cached": True,
                        "age_ms": max(0, now_ms - int(cached.get("synced_at_ms") or now_ms)),
                        "warning": "using_stale_server_time_cache",
                        "error": str(exc),
                    }
                )
                return cached
            return {
                "ok": False,
                "reason": "server_time_sync_failed",
                "endpoint": endpoint_url,
                "family": normalized_family,
                "environment": normalized_environment,
                "error": str(exc),
            }

    def signed_request(
        self,
        method: str,
        endpoint_url: str,
        *,
        family: str,
        environment: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        normalized_family = _normalize_family(family)
        normalized_environment = _normalize_environment(environment)
        api_key, api_secret, env_names = self._credential_resolver(normalized_family, normalized_environment)
        if not api_key or not api_secret or not endpoint_url:
            return None, {
                "ok": False,
                "reason": "missing_credentials",
                "error_category": "auth",
                "retryable": False,
                "credentials_present": False,
                "credential_envs_tried": env_names,
                "endpoint": endpoint_url,
                "method": str(method or "").upper(),
            }

        filtered = {
            str(key): value
            for key, value in (params or {}).items()
            if value is not None and str(value) != ""
        }
        recv_window_ms = _clamp_recv_window_ms(filtered.pop("recvWindow", self._recv_window_resolver()))
        sync_required = bool(self._require_server_time_sync_resolver(normalized_environment))
        sync_enabled = bool(self._server_time_sync_enabled_resolver())
        sync_meta: dict[str, Any] = {
            "ok": False,
            "reason": "disabled",
            "cached": False,
        }
        offset_ms = 0
        warnings: list[str] = []
        if sync_enabled and normalized_environment in {"live", "testnet"}:
            sync_meta = self.sync_server_time(normalized_family, normalized_environment)
            if sync_meta.get("ok") or sync_meta.get("cached"):
                offset_ms = int(sync_meta.get("offset_ms") or 0)
                if sync_meta.get("warning"):
                    warnings.append(str(sync_meta.get("warning")))
            elif sync_required:
                return None, {
                    "ok": False,
                    "reason": "server_time_sync_failed",
                    "error_category": "timing",
                    "retryable": True,
                    "credentials_present": True,
                    "credential_envs_tried": env_names,
                    "endpoint": endpoint_url,
                    "method": str(method or "").upper(),
                    "recv_window_ms": recv_window_ms,
                    "server_time_sync": sync_meta,
                    "warnings": warnings,
                }

        def _execute(attempt: int) -> tuple[Any, dict[str, Any]]:
            timestamp_ms = _now_ms() + int(offset_ms)
            signed_params = {**filtered, "timestamp": int(timestamp_ms), "recvWindow": recv_window_ms}
            query = urlencode(signed_params, doseq=True)
            signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
            url = f"{endpoint_url}?{query}&signature={signature}"
            try:
                response = requests.request(
                    str(method or "").upper(),
                    url,
                    headers={"X-MBX-APIKEY": api_key},
                    timeout=float(self._request_timeout_resolver()),
                )
            except requests.RequestException as exc:
                return None, {
                    "ok": False,
                    "reason": "request_exception",
                    "error_category": "endpoint",
                    "retryable": True,
                    "credentials_present": True,
                    "credential_envs_tried": env_names,
                    "endpoint": endpoint_url,
                    "method": str(method or "").upper(),
                    "error": str(exc),
                    "recv_window_ms": recv_window_ms,
                    "timestamp_ms": int(timestamp_ms),
                    "server_time_offset_ms": int(offset_ms),
                    "server_time_sync": copy.deepcopy(sync_meta),
                    "warnings": list(warnings),
                    "attempt": attempt,
                }
            payload = _response_payload(response)
            if 200 <= int(response.status_code) < 300:
                return payload, {
                    "ok": True,
                    "reason": "ok",
                    "error_category": None,
                    "retryable": False,
                    "credentials_present": True,
                    "credential_envs_tried": env_names,
                    "endpoint": endpoint_url,
                    "method": str(method or "").upper(),
                    "status_code": int(response.status_code),
                    "recv_window_ms": recv_window_ms,
                    "timestamp_ms": int(timestamp_ms),
                    "server_time_offset_ms": int(offset_ms),
                    "server_time_sync": copy.deepcopy(sync_meta),
                    "warnings": list(warnings),
                    "attempt": attempt,
                }
            mapped = map_exchange_error(int(response.status_code), payload)
            return None, {
                "ok": False,
                "credentials_present": True,
                "credential_envs_tried": env_names,
                "endpoint": endpoint_url,
                "method": str(method or "").upper(),
                "status_code": int(response.status_code),
                "recv_window_ms": recv_window_ms,
                "timestamp_ms": int(timestamp_ms),
                "server_time_offset_ms": int(offset_ms),
                "server_time_sync": copy.deepcopy(sync_meta),
                "warnings": list(warnings),
                "exchange_payload": copy.deepcopy(payload),
                "attempt": attempt,
                **mapped,
            }

        payload, meta = _execute(1)
        if (
            payload is None
            and bool(self._retry_invalid_timestamp_once_resolver())
            and str(meta.get("reason") or "") == "invalid_timestamp"
            and normalized_environment in {"live", "testnet"}
        ):
            sync_meta = self.sync_server_time(normalized_family, normalized_environment, force=True)
            if sync_meta.get("ok") or sync_meta.get("cached"):
                offset_ms = int(sync_meta.get("offset_ms") or 0)
                if sync_meta.get("warning"):
                    warnings.append(str(sync_meta.get("warning")))
                payload, meta = _execute(2)
        return payload, meta

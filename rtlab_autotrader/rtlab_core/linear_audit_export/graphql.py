from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .settings import ExporterSettings
from .utils import ensure_dir, now_utc_iso, write_json


LOGGER = logging.getLogger("linear_export")


@dataclass(slots=True)
class GraphQLExecution:
    data: dict[str, Any]
    errors: list[dict[str, Any]]
    status_code: int
    headers: dict[str, str]
    duration_ms: int
    attempt: int


class GraphQLExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        errors: list[dict[str, Any]] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.errors = errors or []
        self.retryable = retryable


class GraphQLClient:
    def __init__(self, settings: ExporterSettings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.request_log: list[dict[str, Any]] = []

    def _base_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", **self.settings.auth_headers()}
        if self.settings.public_file_urls_expire_in:
            headers["public-file-urls-expire-in"] = str(self.settings.public_file_urls_expire_in)
        return headers

    def _interesting_headers(self, headers: requests.structures.CaseInsensitiveDict[str]) -> dict[str, str]:
        interesting: dict[str, str] = {}
        for key, value in headers.items():
            lowered = key.lower()
            if "rate" in lowered or "limit" in lowered or "complex" in lowered or "cost" in lowered or lowered == "retry-after":
                interesting[key] = value
        return interesting

    def _classify_errors(self, errors: list[dict[str, Any]]) -> tuple[bool, bool, bool]:
        auth = False
        validation = False
        rate_limited = False
        for item in errors:
            extensions = item.get("extensions") if isinstance(item, dict) else {}
            code = str((extensions or {}).get("code") or "").upper()
            type_name = str((extensions or {}).get("type") or "").lower()
            status = int((((extensions or {}).get("http") or {}).get("status")) or 0)
            message = str(item.get("message") or "")
            if code == "AUTHENTICATION_ERROR" or "authentication error" in type_name or status == 401:
                auth = True
            if code == "GRAPHQL_VALIDATION_FAILED" or status == 400:
                validation = True
            if status == 429 or "rate" in message.lower():
                rate_limited = True
        return auth, validation, rate_limited

    def _log_request(
        self,
        *,
        kind: str,
        status_code: int,
        duration_ms: int,
        attempt: int,
        query: str | None = None,
        headers: dict[str, str] | None = None,
        errors: list[dict[str, Any]] | None = None,
        url: str | None = None,
    ) -> None:
        payload = {
            "ts": now_utc_iso(),
            "kind": kind,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "attempt": attempt,
            "headers": headers or {},
        }
        if query:
            payload["query_sha1"] = hashlib.sha1(query.encode("utf-8")).hexdigest()
        if url:
            payload["url"] = url
        if errors:
            payload["errors"] = errors
        self.request_log.append(payload)

    def execute(
        self,
        query: str,
        *,
        variables: dict[str, Any] | None = None,
        allow_unauthenticated: bool = False,
    ) -> GraphQLExecution:
        payload = {"query": query, "variables": variables or {}}
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                response = self.session.post(
                    self.settings.base_url,
                    headers=self._base_headers(),
                    json=payload,
                    timeout=self.settings.timeout_seconds,
                )
            except requests.RequestException as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                self._log_request(
                    kind="graphql",
                    status_code=0,
                    duration_ms=duration_ms,
                    attempt=attempt + 1,
                    query=query,
                    errors=[{"message": str(exc)}],
                )
                if attempt >= self.settings.retry_max:
                    raise GraphQLExecutionError(
                        f"Request GraphQL fallo por transporte: {exc}",
                        status_code=0,
                        retryable=True,
                    ) from exc
                time.sleep(min(30.0, (2**attempt) + 0.25))
                attempt += 1
                continue

            duration_ms = int((time.monotonic() - started) * 1000)
            header_meta = self._interesting_headers(response.headers)
            try:
                body = response.json()
            except json.JSONDecodeError as exc:
                self._log_request(
                    kind="graphql",
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    attempt=attempt + 1,
                    query=query,
                    headers=header_meta,
                    errors=[{"message": "response_not_json"}],
                )
                retryable = response.status_code in {429, 500, 502, 503, 504}
                if retryable and attempt < self.settings.retry_max:
                    time.sleep(min(30.0, (2**attempt) + 0.25))
                    attempt += 1
                    continue
                raise GraphQLExecutionError(
                    f"Respuesta GraphQL no JSON ({response.status_code}): {exc}",
                    status_code=response.status_code,
                    retryable=retryable,
                ) from exc

            errors = body.get("errors") if isinstance(body, dict) and isinstance(body.get("errors"), list) else []
            self._log_request(
                kind="graphql",
                status_code=response.status_code,
                duration_ms=duration_ms,
                attempt=attempt + 1,
                query=query,
                headers=header_meta,
                errors=errors,
            )
            if errors:
                auth, validation, rate_limited = self._classify_errors(errors)
                if allow_unauthenticated:
                    return GraphQLExecution(
                        data=body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {},
                        errors=errors,
                        status_code=response.status_code,
                        headers=header_meta,
                        duration_ms=duration_ms,
                        attempt=attempt + 1,
                    )
                retryable = response.status_code in {429, 500, 502, 503, 504} or rate_limited
                if retryable and attempt < self.settings.retry_max:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = float(retry_after) if retry_after else min(30.0, (2**attempt) + 0.25)
                    time.sleep(max(0.25, wait_seconds))
                    attempt += 1
                    continue
                if auth:
                    raise GraphQLExecutionError(
                        "Linear rechazo la query por autenticacion.",
                        status_code=response.status_code or 401,
                        errors=errors,
                        retryable=False,
                    )
                if validation:
                    raise GraphQLExecutionError(
                        "Linear rechazo la query por validacion GraphQL.",
                        status_code=response.status_code or 400,
                        errors=errors,
                        retryable=False,
                    )
                raise GraphQLExecutionError(
                    "Linear devolvio errores GraphQL.",
                    status_code=response.status_code,
                    errors=errors,
                    retryable=retryable,
                )
            if response.status_code >= 400:
                retryable = response.status_code in {429, 500, 502, 503, 504}
                if retryable and attempt < self.settings.retry_max:
                    retry_after = response.headers.get("Retry-After")
                    wait_seconds = float(retry_after) if retry_after else min(30.0, (2**attempt) + 0.25)
                    time.sleep(max(0.25, wait_seconds))
                    attempt += 1
                    continue
                raise GraphQLExecutionError(
                    f"HTTP {response.status_code} al ejecutar GraphQL.",
                    status_code=response.status_code,
                    retryable=retryable,
                )
            data = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else {}
            return GraphQLExecution(
                data=data,
                errors=[],
                status_code=response.status_code,
                headers=header_meta,
                duration_ms=duration_ms,
                attempt=attempt + 1,
            )

    def download_file(self, url: str, target_path: Path) -> dict[str, Any]:
        attempt = 0
        ensure_dir(target_path.parent)
        while True:
            started = time.monotonic()
            try:
                response = self.session.get(
                    url,
                    headers=self.settings.auth_headers(),
                    timeout=self.settings.timeout_seconds,
                    stream=True,
                )
            except requests.RequestException as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                self._log_request(
                    kind="download",
                    status_code=0,
                    duration_ms=duration_ms,
                    attempt=attempt + 1,
                    headers={},
                    errors=[{"message": str(exc)}],
                    url=url,
                )
                if attempt >= self.settings.retry_max:
                    return {"status": "failed", "error_message": str(exc), "downloaded": False}
                time.sleep(min(30.0, (2**attempt) + 0.25))
                attempt += 1
                continue

            duration_ms = int((time.monotonic() - started) * 1000)
            headers = self._interesting_headers(response.headers)
            self._log_request(
                kind="download",
                status_code=response.status_code,
                duration_ms=duration_ms,
                attempt=attempt + 1,
                headers=headers,
                url=url,
            )
            if response.status_code == 200:
                with target_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            handle.write(chunk)
                return {
                    "status": "downloaded",
                    "downloaded": True,
                    "size_bytes": target_path.stat().st_size,
                    "mime_type": response.headers.get("Content-Type", ""),
                }
            retryable = response.status_code in {429, 500, 502, 503, 504}
            if retryable and attempt < self.settings.retry_max:
                retry_after = response.headers.get("Retry-After")
                wait_seconds = float(retry_after) if retry_after else min(30.0, (2**attempt) + 0.25)
                time.sleep(max(0.25, wait_seconds))
                attempt += 1
                continue
            return {
                "status": "failed",
                "downloaded": False,
                "error_message": f"http_{response.status_code}",
                "mime_type": response.headers.get("Content-Type", ""),
            }

    def export_log(self, path: Path) -> None:
        write_json(path, self.request_log)


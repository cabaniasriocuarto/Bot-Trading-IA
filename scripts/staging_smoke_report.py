#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _normalize_url(value: str) -> str:
    url = str(value or "").strip()
    if url.endswith("/"):
        return url[:-1]
    return url


def _allow_insecure_password_cli() -> bool:
    raw = str(os.getenv("ALLOW_INSECURE_PASSWORD_CLI", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_password(cli_password: str) -> str:
    cli_value = str(cli_password or "").strip()
    if cli_value:
        if not _allow_insecure_password_cli():
            raise RuntimeError(
                "Uso de --password deshabilitado por seguridad. "
                "Usa RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD o token."
            )
        return cli_value
    for name in ("RTLAB_ADMIN_PASSWORD", "RTLAB_PASSWORD"):
        value = str(os.getenv(name, "")).strip()
        if value:
            return value
    return ""


def _http_get_json(url: str, timeout_sec: float, headers: dict[str, str] | None = None) -> tuple[dict[str, Any], str]:
    try:
        response = requests.get(url, headers=headers or {}, timeout=timeout_sec)
    except Exception as exc:
        return {}, f"request_error: {exc}"
    if response.status_code != 200:
        return {}, f"http_{response.status_code}"
    if "json" not in str(response.headers.get("content-type", "")).lower():
        return {}, "not_json"
    data = response.json()
    if not isinstance(data, dict):
        return {}, "json_not_object"
    return data, ""


def _http_get_status(url: str, timeout_sec: float) -> tuple[int, str]:
    try:
        response = requests.get(url, timeout=timeout_sec)
        return int(response.status_code), ""
    except Exception as exc:
        return 0, f"request_error: {exc}"


def _resolve_token(
    *,
    base_url: str,
    timeout_sec: float,
    username: str,
    password: str,
    auth_token: str,
) -> tuple[str, str]:
    token = str(auth_token or "").strip()
    if token:
        return token, "env_or_cli_token"
    if not password:
        return "", "NO_EVIDENCE_NO_SECRET"
    try:
        response = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=timeout_sec,
        )
    except Exception as exc:
        return "", f"login_request_error: {exc}"
    if response.status_code != 200:
        return "", f"login_http_{response.status_code}"
    if "json" not in str(response.headers.get("content-type", "")).lower():
        return "", "login_not_json"
    payload = response.json()
    token = str((payload or {}).get("token") or "").strip()
    if not token:
        return "", "login_no_token"
    return token, "login_password_env"


def _build_markdown(report: dict[str, Any]) -> str:
    checks = report.get("checks", {}) if isinstance(report.get("checks"), dict) else {}
    lines = [
        "# Staging Smoke Report",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- backend_base_url: `{report.get('backend_base_url')}`",
        f"- frontend_login_url: `{report.get('frontend_login_url')}`",
        "",
        "## Checks",
        f"- front_login_status_code: `{checks.get('front_login_status_code')}`",
        f"- front_login_ok: `{checks.get('front_login_ok')}`",
        f"- health_ok: `{checks.get('health_ok')}`",
        f"- health_mode: `{checks.get('health_mode')}`",
        f"- mode_is_non_live: `{checks.get('mode_is_non_live')}`",
        f"- runtime_ready_for_live: `{checks.get('runtime_ready_for_live')}`",
        f"- runtime_guard_ok: `{checks.get('runtime_guard_ok')}`",
        f"- storage_persistent: `{checks.get('storage_persistent')}`",
        f"- auth_source: `{checks.get('auth_source')}`",
        f"- bots_check_status: `{checks.get('bots_check_status')}`",
        f"- bots_http_ok: `{checks.get('bots_http_ok')}`",
        f"- overall_pass: `{checks.get('overall_pass')}`",
        "",
        "## Errors",
    ]
    errors = report.get("errors", {}) if isinstance(report.get("errors"), dict) else {}
    if not errors:
        lines.append("- none")
    else:
        for key, value in errors.items():
            lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smoke checks para staging (NO-LIVE).")
    parser.add_argument("--backend-base-url", default="https://bot-trading-ia-staging.up.railway.app")
    parser.add_argument("--frontend-login-url", default="https://bot-trading-ia-staging-2.vercel.app/login")
    parser.add_argument("--username", default=os.getenv("RTLAB_USERNAME", "Wadmin"))
    parser.add_argument(
        "--password",
        default="",
        help=(
            "DEPRECATED (inseguro): password por CLI. "
            "Usa RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD o token. "
            "Para habilitar CLI: ALLOW_INSECURE_PASSWORD_CLI=1."
        ),
    )
    parser.add_argument("--auth-token", default=os.getenv("RTLAB_AUTH_TOKEN", ""))
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--report-prefix", default="artifacts/staging_smoke")
    parser.add_argument(
        "--require-auth-checks",
        action="store_true",
        help="Falla si no hay token/password para validar endpoint autenticado /api/v1/bots.",
    )
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        default=True,
        help="Exit 2 si overall_pass=false (default: true).",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="No falla por overall_pass=false.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    timeout_sec = max(1.0, float(args.timeout_sec))
    backend_base_url = _normalize_url(args.backend_base_url)
    frontend_login_url = str(args.frontend_login_url or "").strip()
    if not backend_base_url or not frontend_login_url:
        raise RuntimeError("backend-base-url y frontend-login-url son obligatorios")

    errors: dict[str, str] = {}

    front_status, front_error = _http_get_status(frontend_login_url, timeout_sec)
    if front_error:
        errors["frontend_login"] = front_error

    health, health_error = _http_get_json(f"{backend_base_url}/api/v1/health", timeout_sec)
    if health_error:
        errors["health"] = health_error

    auth_token, auth_source = _resolve_token(
        base_url=backend_base_url,
        timeout_sec=timeout_sec,
        username=str(args.username or "Wadmin"),
        password=_resolve_password(str(args.password or "")),
        auth_token=str(args.auth_token or ""),
    )

    bots_http_ok = False
    bots_count = None
    if auth_token:
        bots_payload, bots_error = _http_get_json(
            f"{backend_base_url}/api/v1/bots",
            timeout_sec,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        if bots_error:
            errors["bots"] = bots_error
        else:
            bots_http_ok = True
            bots = bots_payload.get("bots")
            if isinstance(bots, list):
                bots_count = len(bots)
    else:
        if str(args.require_auth_checks).lower() == "true":
            errors["auth"] = auth_source

    health_mode = str(health.get("mode") or "").strip().lower() if health else ""
    runtime_ready_for_live = bool(health.get("runtime_ready_for_live")) if health else False
    storage = health.get("storage") if isinstance(health.get("storage"), dict) else {}

    checks = {
        "front_login_status_code": front_status,
        "front_login_ok": front_status == 200,
        "health_ok": bool(health.get("ok", False)) if health else False,
        "health_mode": health_mode or "unknown",
        "mode_is_non_live": health_mode in {"paper", "testnet"},
        "runtime_ready_for_live": runtime_ready_for_live,
        "runtime_guard_ok": runtime_ready_for_live is False,
        "storage_persistent": bool(storage.get("persistent_storage", False)),
        "auth_source": auth_source,
        "bots_check_status": "executed" if auth_token else "NO_EVIDENCE_NO_SECRET",
        "bots_http_ok": bots_http_ok if auth_token else (not args.require_auth_checks),
        "bots_count": bots_count,
    }
    checks["overall_pass"] = bool(
        checks["front_login_ok"]
        and checks["health_ok"]
        and checks["mode_is_non_live"]
        and checks["runtime_guard_ok"]
        and checks["bots_http_ok"]
    )

    report = {
        "generated_at_utc": _now_utc().isoformat(),
        "backend_base_url": backend_base_url,
        "frontend_login_url": frontend_login_url,
        "checks": checks,
        "errors": errors,
    }

    stamp = _now_utc().strftime("%Y%m%d_%H%M%S")
    report_prefix = str(args.report_prefix or "artifacts/staging_smoke").strip()
    json_out = (REPO_ROOT / f"{report_prefix}_{stamp}.json").resolve()
    md_out = (REPO_ROOT / f"{report_prefix}_{stamp}.md").resolve()
    json_out.parent.mkdir(parents=True, exist_ok=True)

    json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_out.write_text(_build_markdown(report), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"REPORT_JSON={json_out}")
    print(f"REPORT_MD={md_out}")

    if args.strict and not checks["overall_pass"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

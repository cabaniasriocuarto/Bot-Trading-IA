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


def _normalize_base_url(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        return value
    return value[:-1] if value.endswith("/") else value


def _allow_insecure_password_cli() -> bool:
    raw = str(os.getenv("ALLOW_INSECURE_PASSWORD_CLI", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_password(*, cli_password: str) -> str:
    cli_value = str(cli_password or "").strip()
    if cli_value:
        if not _allow_insecure_password_cli():
            raise RuntimeError(
                "Uso de --password deshabilitado por seguridad. "
                "Usa RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD o token."
            )
        return cli_value
    for env_name in ("RTLAB_ADMIN_PASSWORD", "RTLAB_PASSWORD"):
        value = str(os.getenv(env_name, "")).strip()
        if value:
            return value
    return ""


def _request_json(
    *,
    base_url: str,
    path: str,
    timeout_sec: float,
    token: str,
) -> tuple[dict[str, Any], str]:
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(f"{base_url}{path}", headers=headers, timeout=timeout_sec)
    except Exception as exc:
        return {}, f"request_error: {exc}"
    if res.status_code != 200:
        body = str(res.text or "")[:300]
        return {}, f"http_{res.status_code}: {body}"
    if "json" not in str(res.headers.get("content-type", "")).lower():
        return {}, "not_json"
    data = res.json()
    if not isinstance(data, dict):
        return {}, "json_not_object"
    return data, ""


def _resolve_token(
    *,
    base_url: str,
    timeout_sec: float,
    auth_token: str,
    username: str,
    password: str,
) -> str:
    token = str(auth_token or "").strip()
    if token:
        return token
    user = str(username or "").strip()
    pwd = str(password or "").strip()
    if not user or not pwd:
        raise RuntimeError("Falta auth: pasar --auth-token o RTLAB_ADMIN_PASSWORD.")
    login = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": user, "password": pwd},
        timeout=timeout_sec,
    )
    if login.status_code != 200:
        raise RuntimeError(f"Login fallo: {login.status_code} {str(login.text or '')[:300]}")
    payload = login.json() if "json" in str(login.headers.get("content-type", "")).lower() else {}
    token = str((payload or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError("Login exitoso pero sin token.")
    return token


def _gate_status(gates_payload: dict[str, Any], gate_id: str) -> str:
    rows = gates_payload.get("gates") if isinstance(gates_payload.get("gates"), list) else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("id") or "") == gate_id:
            return str(row.get("status") or "UNKNOWN").upper()
    return "UNKNOWN"


def _build_markdown(report: dict[str, Any]) -> str:
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    lines = [
        "# Protected Ops Checks",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- base_url: `{report.get('base_url')}`",
        "",
        "## Checks",
        f"- health_ok: `{checks.get('health_ok')}`",
        f"- storage_persistent: `{checks.get('storage_persistent')}`",
        f"- g10_status: `{checks.get('g10_status')}`",
        f"- g10_pass: `{checks.get('g10_pass')}`",
        f"- g9_status: `{checks.get('g9_status')}`",
        f"- g9_expected_runtime_guard: `{checks.get('g9_expected_runtime_guard')}`",
        f"- breaker_status: `{checks.get('breaker_status')}`",
        f"- breaker_strict_mode: `{checks.get('breaker_strict_mode')}`",
        f"- breaker_ok: `{checks.get('breaker_ok')}`",
        f"- allow_staging_warns_applied: `{checks.get('allow_staging_warns_applied')}`",
        f"- internal_proxy_status_ok: `{checks.get('internal_proxy_status_ok')}`",
        f"- protected_checks_complete: `{checks.get('protected_checks_complete')}`",
        f"- overall_pass: `{checks.get('overall_pass')}`",
        "",
        "## Endpoint Errors",
    ]
    endpoint_errors = report.get("endpoint_errors") if isinstance(report.get("endpoint_errors"), dict) else {}
    if endpoint_errors:
        for key in ["health", "gates", "breaker_events", "internal_proxy_status"]:
            err = endpoint_errors.get(key)
            lines.append(f"- {key}: `{err or ''}`")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run protected operational checks against deployed backend.")
    parser.add_argument("--base-url", default="https://bot-trading-ia-production.up.railway.app")
    parser.add_argument("--username", default=os.getenv("RTLAB_USERNAME", "Wadmin"))
    parser.add_argument(
        "--password",
        default="",
        help=(
            "DEPRECATED (inseguro): password por CLI. "
            "Usa RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD; para habilitar CLI setea ALLOW_INSECURE_PASSWORD_CLI=1."
        ),
    )
    parser.add_argument("--auth-token", default=os.getenv("RTLAB_AUTH_TOKEN", ""))
    parser.add_argument("--timeout-sec", type=float, default=15.0)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--expect-g9", choices=["WARN", "PASS", "ANY"], default="WARN")
    parser.add_argument(
        "--report-prefix",
        default="artifacts/ops_protected_checks",
        help="Output prefix without extension. Script writes <prefix>_<ts>.json/.md",
    )
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        default=True,
        help="Exit 2 when any required check is not passing (default: true).",
    )
    parser.add_argument(
        "--no-strict",
        dest="strict",
        action="store_false",
        help="Override and run in non-strict mode (compatibilidad legacy).",
    )
    parser.add_argument(
        "--allow-staging-warns",
        action="store_true",
        help=(
            "Solo para base_url de staging: permite G10=WARN y breaker NO_DATA "
            "como aprobacion operativa no-live."
        ),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    base_url = _normalize_base_url(args.base_url)
    if not base_url:
        raise RuntimeError("base-url vacia")

    token = _resolve_token(
        base_url=base_url,
        timeout_sec=max(1.0, float(args.timeout_sec)),
        auth_token=args.auth_token,
        username=args.username,
        password=_resolve_password(cli_password=str(args.password or "")),
    )

    endpoint_errors: dict[str, str] = {}
    timeout_sec = max(1.0, float(args.timeout_sec))

    health, err_health = _request_json(base_url=base_url, path="/api/v1/health", timeout_sec=timeout_sec, token=token)
    gates, err_gates = _request_json(base_url=base_url, path="/api/v1/gates", timeout_sec=timeout_sec, token=token)
    breaker, err_breaker = _request_json(
        base_url=base_url,
        path=f"/api/v1/diagnostics/breaker-events?window_hours={int(args.window_hours)}&strict={'true' if args.strict else 'false'}",
        timeout_sec=timeout_sec,
        token=token,
    )
    internal_proxy_status, err_internal = _request_json(
        base_url=base_url,
        path="/api/v1/auth/internal-proxy/status",
        timeout_sec=timeout_sec,
        token=token,
    )

    if err_health:
        endpoint_errors["health"] = err_health
    if err_gates:
        endpoint_errors["gates"] = err_gates
    if err_breaker:
        endpoint_errors["breaker_events"] = err_breaker
    if err_internal:
        endpoint_errors["internal_proxy_status"] = err_internal

    storage = health.get("storage") if isinstance(health.get("storage"), dict) else {}
    g10_status = _gate_status(gates, "G10_STORAGE_PERSISTENCE")
    g9_status = _gate_status(gates, "G9_RUNTIME_ENGINE_REAL")

    expect_g9 = str(args.expect_g9 or "WARN").upper()
    if expect_g9 == "ANY":
        g9_expected_guard = g9_status in {"WARN", "PASS"}
    else:
        g9_expected_guard = g9_status == expect_g9

    storage_persistent = bool(storage.get("persistent_storage"))
    breaker_status = str(breaker.get("status") or "UNKNOWN").upper() if breaker else "UNKNOWN"
    breaker_ok_base = bool(breaker.get("ok", False)) if breaker else False
    staging_target = "staging" in base_url.lower()
    allow_staging_warns = bool(args.allow_staging_warns and staging_target)
    g10_pass_base = g10_status == "PASS"
    g10_pass = g10_pass_base or (allow_staging_warns and g10_status == "WARN")
    breaker_ok = breaker_ok_base or (allow_staging_warns and breaker_status == "NO_DATA")

    checks = {
        "health_ok": bool(health.get("ok", False)),
        "storage_persistent": storage_persistent,
        "g10_status": g10_status,
        "g10_pass": g10_pass,
        "g10_pass_base": g10_pass_base,
        "g9_status": g9_status,
        "g9_expected_runtime_guard": bool(g9_expected_guard),
        "breaker_status": breaker_status,
        "breaker_strict_mode": bool(breaker.get("strict_mode", False)) if breaker else bool(args.strict),
        "breaker_ok": breaker_ok,
        "breaker_ok_base": breaker_ok_base,
        "allow_staging_warns_applied": allow_staging_warns,
        "internal_proxy_status_ok": bool(internal_proxy_status.get("ok", False)) if internal_proxy_status else False,
    }
    checks["protected_checks_complete"] = not endpoint_errors
    checks["overall_pass"] = bool(
        checks["health_ok"]
        and checks["g10_pass"]
        and checks["g9_expected_runtime_guard"]
        and checks["breaker_ok"]
        and checks["internal_proxy_status_ok"]
        and checks["protected_checks_complete"]
    )

    stamp = _now_utc().strftime("%Y%m%d_%H%M%S")
    report_prefix = str(args.report_prefix or "artifacts/ops_protected_checks").strip()
    json_out = (REPO_ROOT / f"{report_prefix}_{stamp}.json").resolve()
    md_out = (REPO_ROOT / f"{report_prefix}_{stamp}.md").resolve()
    json_out.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "generated_at_utc": _now_utc().isoformat(),
        "base_url": base_url,
        "checks": checks,
        "endpoint_errors": endpoint_errors,
        "health": health,
        "gates": gates,
        "breaker_events": breaker,
        "internal_proxy_status": internal_proxy_status,
    }

    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_build_markdown(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "json_report": str(json_out),
                "md_report": str(md_out),
                "checks": checks,
                "exit_code": 2 if (args.strict and not checks["overall_pass"]) else 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.strict and not checks["overall_pass"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

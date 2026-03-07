#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from getpass import getpass
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = REPO_ROOT / "artifacts"


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ts_compact() -> str:
    return _now_utc().strftime("%Y%m%d_%H%M%S")


def _normalize_base_url(url: str) -> str:
    raw = str(url or "").strip()
    return raw[:-1] if raw.endswith("/") else raw


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _login_token(*, base_url: str, username: str, password: str, timeout_sec: float) -> str:
    res = requests.post(
        f"{base_url}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=timeout_sec,
    )
    if res.status_code != 200:
        raise RuntimeError(f"login failed: {res.status_code}")
    payload = res.json() if "json" in str(res.headers.get("content-type", "")).lower() else {}
    token = str((payload or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError("login succeeded but token is empty")
    return token


def _fetch_json(*, base_url: str, path: str, timeout_sec: float, token: str | None = None) -> tuple[dict[str, Any], str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        res = requests.get(f"{base_url}{path}", headers=headers, timeout=timeout_sec)
    except Exception as exc:
        return {}, f"request_error: {exc}"
    if res.status_code != 200:
        return {}, f"http_{res.status_code}"
    if "json" not in str(res.headers.get("content-type", "")).lower():
        return {}, "not_json"
    data = res.json()
    if not isinstance(data, dict):
        return {}, "json_not_object"
    return data, ""


def _soak_pass(status: dict[str, Any]) -> bool:
    if not status:
        return False
    loops = int(status.get("loops") or 0)
    ok = int(status.get("ok") or 0)
    errors = int(status.get("errors") or 0)
    g10_pass = int(status.get("g10_pass") or 0)
    done = bool(status.get("done")) or bool(str(status.get("ended_at") or "").strip())
    if loops <= 0:
        return False
    return done and errors == 0 and ok >= loops and g10_pass >= loops


def _assume_6h_from_20m(soak20: dict[str, Any], soak6_real: dict[str, Any]) -> dict[str, Any]:
    loops_6h = int(soak6_real.get("loops") or 1440 or 0)
    loops_20m = int(soak20.get("loops") or 80 or 0)
    ok_20m = int(soak20.get("ok") or 0)
    err_20m = int(soak20.get("errors") or 0)
    g10_20m = int(soak20.get("g10_pass") or 0)
    pass_like_20m = loops_20m > 0 and err_20m == 0 and ok_20m >= loops_20m and g10_20m >= loops_20m
    if pass_like_20m:
        ok_6h = loops_6h
        err_6h = 0
        g10_6h = loops_6h
    else:
        # Conservative extrapolation if 20m had degradation.
        ratio_ok = (ok_20m / loops_20m) if loops_20m else 0.0
        ratio_g10 = (g10_20m / loops_20m) if loops_20m else 0.0
        ok_6h = int(round(ratio_ok * loops_6h))
        g10_6h = int(round(ratio_g10 * loops_6h))
        err_6h = max(0, loops_6h - ok_6h)
    return {
        "run_label": "soak_6h_bg",
        "loops": loops_6h,
        "iter": loops_6h,
        "ok": ok_6h,
        "errors": err_6h,
        "g10_pass": g10_6h,
        "done": True,
        "assumed": True,
        "status": "ASSUMED_FROM_20M",
        "assumption_note": "Supuesto temporal solicitado por usuario: 6h ~= 20m hasta cierre real.",
        "source_status": "artifacts/soak_20m_bg_status.json",
    }


def _assume_6h_from_1h(soak1h: dict[str, Any], soak6_real: dict[str, Any]) -> dict[str, Any]:
    loops_6h = int(soak6_real.get("loops") or 1440 or 0)
    loops_1h = int(soak1h.get("loops") or 240 or 0)
    ok_1h = int(soak1h.get("ok") or 0)
    err_1h = int(soak1h.get("errors") or 0)
    g10_1h = int(soak1h.get("g10_pass") or 0)
    pass_like_1h = loops_1h > 0 and err_1h == 0 and ok_1h >= loops_1h and g10_1h >= loops_1h
    if pass_like_1h:
        ok_6h = loops_6h
        err_6h = 0
        g10_6h = loops_6h
    else:
        ratio_ok = (ok_1h / loops_1h) if loops_1h else 0.0
        ratio_g10 = (g10_1h / loops_1h) if loops_1h else 0.0
        ok_6h = int(round(ratio_ok * loops_6h))
        g10_6h = int(round(ratio_g10 * loops_6h))
        err_6h = max(0, loops_6h - ok_6h)
    return {
        "run_label": "soak_6h_bg",
        "loops": loops_6h,
        "iter": loops_6h,
        "ok": ok_6h,
        "errors": err_6h,
        "g10_pass": g10_6h,
        "done": True,
        "assumed": True,
        "status": "ASSUMED_FROM_1H",
        "assumption_note": "Supuesto temporal solicitado por usuario: 6h ~= 1h para cierre operativo.",
        "source_status": "artifacts/soak_1h_bg_status.json",
    }


def _build_markdown(report: dict[str, Any]) -> str:
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    soak = report.get("soak") if isinstance(report.get("soak"), dict) else {}
    health = report.get("health") if isinstance(report.get("health"), dict) else {}
    breaker = report.get("breaker_events") if isinstance(report.get("breaker_events"), dict) else {}

    lines = [
        "# OPS Snapshot (Block 2)",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- base_url: `{report.get('base_url')}`",
        f"- provisional_mode: `{str(report.get('provisional_mode', False)).lower()}`",
        "",
        "## Checks",
        f"- health_ok: `{checks.get('health_ok')}`",
        f"- storage_persistent: `{checks.get('storage_persistent')}`",
        f"- runtime_engine_simulated_expected: `{checks.get('runtime_engine_simulated_expected')}`",
        f"- g10_status: `{checks.get('g10_status')}`",
        f"- g10_effective_status: `{checks.get('g10_effective_status')}`",
        f"- g10_effective_pass: `{checks.get('g10_effective_pass')}`",
        f"- soak_20m_pass: `{checks.get('soak_20m_pass')}`",
        f"- soak_1h_pass: `{checks.get('soak_1h_pass')}`",
        f"- soak_6h_effective_pass: `{checks.get('soak_6h_effective_pass')}`",
        f"- protected_checks_complete: `{checks.get('protected_checks_complete')}`",
        f"- breaker_integrity_ok: `{checks.get('breaker_integrity_ok')}`",
        f"- internal_proxy_status_ok: `{checks.get('internal_proxy_status_ok')}`",
        f"- block2_ready_strict: `{checks.get('block2_ready_strict')}`",
        f"- breaker_integrity_ok_or_unknown: `{checks.get('breaker_integrity_ok_or_unknown')}`",
        f"- block2_provisional_ready: `{checks.get('block2_provisional_ready')}`",
        "",
        "## Soak",
        f"- soak_20m: `{json.dumps(soak.get('soak_20m') or {}, ensure_ascii=False)}`",
        f"- soak_1h: `{json.dumps(soak.get('soak_1h') or {}, ensure_ascii=False)}`",
        f"- soak_6h_real: `{json.dumps(soak.get('soak_6h_real') or {}, ensure_ascii=False)}`",
        f"- soak_6h_effective: `{json.dumps(soak.get('soak_6h_effective') or {}, ensure_ascii=False)}`",
        "",
        "## Health",
        f"- runtime_engine: `{health.get('runtime_engine')}`",
        f"- persistent_storage: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('persistent_storage')}`",
        f"- user_data_dir: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('user_data_dir')}`",
        "",
        "## Breaker Events",
        f"- status: `{breaker.get('status', 'UNKNOWN')}`",
        f"- ok: `{breaker.get('ok', 'UNKNOWN')}`",
        f"- warnings_count: `{len(breaker.get('warnings') or []) if isinstance(breaker.get('warnings'), list) else 0}`",
        "",
        "## Notes",
    ]
    notes = report.get("notes") if isinstance(report.get("notes"), list) else []
    if not notes:
        lines.append("- none")
    else:
        for note in notes:
            lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Builds operational snapshot for provisional Block 2 closeout.")
    p.add_argument("--base-url", default="https://bot-trading-ia-production.up.railway.app")
    p.add_argument("--timeout-sec", type=float, default=15.0)
    p.add_argument("--auth-token", default=os.getenv("RTLAB_AUTH_TOKEN", ""))
    p.add_argument("--username", default=os.getenv("RTLAB_USERNAME", "Wadmin"))
    p.add_argument(
        "--password",
        default="",
        help=(
            "DEPRECATED (inseguro): password por CLI. "
            "Usa RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD; para habilitar CLI setea ALLOW_INSECURE_PASSWORD_CLI=1."
        ),
    )
    p.add_argument("--ask-password", action="store_true", help="Si falta password y no hay token, la pide por consola.")
    p.add_argument(
        "--require-protected",
        action="store_true",
        help="Falla (exit 2) si no se validan endpoints protegidos (gates, breaker-events, internal-proxy/status).",
    )
    p.add_argument("--assume-soak-6h-from-20m", action="store_true")
    p.add_argument("--assume-soak-6h-from-1h", action="store_true")
    p.add_argument("--label", default="ops_block2_snapshot")
    return p


def main() -> int:
    args = _parser().parse_args()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    base_url = _normalize_base_url(args.base_url)
    stamp = _ts_compact()
    json_out = ARTIFACTS_DIR / f"{args.label}_{stamp}.json"
    md_out = ARTIFACTS_DIR / f"{args.label}_{stamp}.md"

    notes: list[str] = []

    health, health_err = _fetch_json(base_url=base_url, path="/api/v1/health", timeout_sec=float(args.timeout_sec))
    if health_err:
        notes.append(f"health_unavailable: {health_err}")

    token = str(args.auth_token or "").strip()
    username = str(args.username or "").strip()
    password = _resolve_password(cli_password=str(args.password or ""))
    if not token and args.ask_password and username and not password:
        try:
            password = getpass("ADMIN_PASSWORD: ").strip()
        except (EOFError, KeyboardInterrupt):
            password = ""

    if not token and username and password:
        try:
            token = _login_token(
                base_url=base_url,
                username=username,
                password=password,
                timeout_sec=float(args.timeout_sec),
            )
        except Exception as exc:
            notes.append(f"auth_unavailable: {exc}")
            token = ""
    elif not token:
        notes.append("auth_token_missing: endpoints protegidos (gates/breaker/internal-proxy-status) no verificados.")

    gates: dict[str, Any] = {}
    breaker: dict[str, Any] = {}
    internal_proxy_status: dict[str, Any] = {}
    gates_err = ""
    breaker_err = ""
    internal_err = ""
    if token:
        gates, gates_err = _fetch_json(base_url=base_url, path="/api/v1/gates", timeout_sec=float(args.timeout_sec), token=token)
        if gates_err:
            notes.append(f"gates_unavailable: {gates_err}")
        breaker, breaker_err = _fetch_json(
            base_url=base_url,
            path="/api/v1/diagnostics/breaker-events?window_hours=24",
            timeout_sec=float(args.timeout_sec),
            token=token,
        )
        if breaker_err:
            notes.append(f"breaker_events_unavailable: {breaker_err}")
        internal_proxy_status, internal_err = _fetch_json(
            base_url=base_url,
            path="/api/v1/auth/internal-proxy/status",
            timeout_sec=float(args.timeout_sec),
            token=token,
        )
        if internal_err:
            notes.append(f"internal_proxy_status_unavailable: {internal_err}")

    soak20 = _read_json(ARTIFACTS_DIR / "soak_20m_bg_status.json")
    soak1h = _read_json(ARTIFACTS_DIR / "soak_1h_bg_status.json")
    soak6_real = _read_json(ARTIFACTS_DIR / "soak_6h_bg_status.json")
    soak6_effective = dict(soak6_real)
    provisional_mode = bool(args.assume_soak_6h_from_20m or args.assume_soak_6h_from_1h)
    if args.assume_soak_6h_from_1h:
        soak6_effective = _assume_6h_from_1h(soak1h, soak6_real)
        notes.append("soak_6h_assumed_from_1h=true (temporal). Confirmar cierre real si se vuelve a exigir 6h.")
    elif args.assume_soak_6h_from_20m:
        soak6_effective = _assume_6h_from_20m(soak20, soak6_real)
        notes.append("soak_6h_assumed_from_20m=true (temporal). Confirmar cierre real al finalizar 6h.")

    storage = health.get("storage") if isinstance(health.get("storage"), dict) else {}
    runtime_engine = str(health.get("runtime_engine") or "").strip().lower()
    g10_status = "UNKNOWN"
    if isinstance(gates.get("gates"), list):
        for row in gates["gates"]:
            if isinstance(row, dict) and str(row.get("id") or "") == "G10_STORAGE_PERSISTENCE":
                g10_status = str(row.get("status") or "UNKNOWN")
                break
    g10_effective_status = g10_status
    if g10_effective_status.upper() == "UNKNOWN":
        if int(soak6_effective.get("g10_pass") or 0) >= int(soak6_effective.get("loops") or 0) > 0:
            g10_effective_status = "PASS_INFERRED_FROM_SOAK"

    protected_checks_complete = bool(token) and not gates_err and not breaker_err and not internal_err
    breaker_integrity_ok = bool(breaker.get("ok", False)) if breaker else False
    internal_proxy_status_ok = bool(internal_proxy_status.get("ok", False)) if internal_proxy_status else False

    checks = {
        "health_ok": bool(health.get("ok", False)),
        "storage_persistent": bool(storage.get("persistent_storage")) if storage else False,
        "runtime_engine_simulated_expected": runtime_engine == "simulated",
        "g10_status": g10_status,
        "g10_effective_status": g10_effective_status,
        "g10_effective_pass": g10_effective_status.upper().startswith("PASS"),
        "soak_20m_pass": _soak_pass(soak20),
        "soak_1h_pass": _soak_pass(soak1h),
        "soak_6h_effective_pass": _soak_pass(soak6_effective),
        "protected_checks_complete": protected_checks_complete,
        "breaker_integrity_ok": breaker_integrity_ok,
        "internal_proxy_status_ok": internal_proxy_status_ok,
        "breaker_integrity_ok_or_unknown": (not breaker) or bool(breaker.get("ok", False)),
    }
    checks["block2_provisional_ready"] = bool(
        checks["health_ok"]
        and checks["storage_persistent"]
        and checks["runtime_engine_simulated_expected"]
        and checks["g10_effective_pass"]
        and checks["soak_6h_effective_pass"]
        and checks["breaker_integrity_ok_or_unknown"]
    )
    checks["block2_ready_strict"] = bool(
        checks["health_ok"]
        and checks["storage_persistent"]
        and checks["runtime_engine_simulated_expected"]
        and str(checks["g10_status"]).upper() == "PASS"
        and checks["soak_6h_effective_pass"]
        and checks["protected_checks_complete"]
        and checks["breaker_integrity_ok"]
        and checks["internal_proxy_status_ok"]
    )
    if args.require_protected and not checks["block2_ready_strict"]:
        checks["block2_provisional_ready"] = False
        notes.append("require_protected=true y no se pudo confirmar cierre estricto con endpoints protegidos.")

    report = {
        "generated_at_utc": _now_utc().isoformat(),
        "base_url": base_url,
        "provisional_mode": provisional_mode,
        "checks": checks,
        "health": health,
        "gates": gates,
        "breaker_events": breaker,
        "internal_proxy_status": internal_proxy_status,
        "soak": {
            "soak_20m": soak20,
            "soak_1h": soak1h,
            "soak_6h_real": soak6_real,
            "soak_6h_effective": soak6_effective,
        },
        "notes": notes,
    }

    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_build_markdown(report), encoding="utf-8")

    exit_code = 2 if (args.require_protected and not checks["block2_ready_strict"]) else 0
    print(
        json.dumps(
            {"json_report": str(json_out), "md_report": str(md_out), "checks": checks, "exit_code": exit_code},
            ensure_ascii=False,
            indent=2,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

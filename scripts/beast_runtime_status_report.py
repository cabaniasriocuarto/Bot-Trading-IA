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
    return url[:-1] if url.endswith("/") else url


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


def _http_json(
    *,
    method: str,
    url: str,
    timeout_sec: float,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, int]:
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers or {},
            json=json_body,
            timeout=timeout_sec,
        )
    except Exception as exc:
        return {}, f"request_error: {exc}", 0
    if response.status_code != 200:
        body = str(response.text or "")[:300]
        return {}, f"http_{response.status_code}: {body}", int(response.status_code)
    if "json" not in str(response.headers.get("content-type", "")).lower():
        return {}, "not_json", int(response.status_code)
    payload = response.json()
    if not isinstance(payload, dict):
        return {}, "json_not_object", int(response.status_code)
    return payload, "", int(response.status_code)


def _resolve_token(
    *,
    base_url: str,
    timeout_sec: float,
    username: str,
    password: str,
    auth_token: str,
) -> tuple[str, str, str]:
    token = str(auth_token or "").strip()
    if token:
        return token, "env_or_cli_token", ""
    if not password:
        return "", "missing_local_auth", "Falta RTLAB_AUTH_TOKEN o RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD."
    payload, error, status_code = _http_json(
        method="POST",
        url=f"{base_url}/api/v1/auth/login",
        timeout_sec=timeout_sec,
        json_body={"username": username, "password": password},
    )
    if error:
        return "", f"login_http_{status_code or 'error'}", error
    token = str((payload or {}).get("token") or (payload or {}).get("access_token") or "").strip()
    if not token:
        return "", "login_no_token", ""
    return token, "login_password_env", ""


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_crypto_public(
    *,
    base_url: str,
    timeout_sec: float,
    token: str,
    symbol: str,
    start_month: str,
    end_month: str,
) -> tuple[dict[str, Any], str, int]:
    return _http_json(
        method="POST",
        url=f"{base_url}/api/v1/data/bootstrap/crypto-binance-public",
        timeout_sec=timeout_sec,
        headers=_auth_headers(token),
        json_body={
            "symbols": [symbol],
            "start_month": start_month,
            "end_month": end_month,
        },
    )


def _bootstrap_futures_public(
    *,
    base_url: str,
    timeout_sec: float,
    token: str,
    market_family: str,
    symbol: str,
    start_month: str,
    end_month: str,
    resample_timeframes: list[str],
) -> tuple[dict[str, Any], str, int]:
    return _http_json(
        method="POST",
        url=f"{base_url}/api/v1/data/bootstrap/binance-futures-public",
        timeout_sec=timeout_sec,
        headers=_auth_headers(token),
        json_body={
            "market_family": market_family,
            "symbols": [symbol],
            "start_month": start_month,
            "end_month": end_month,
            "resample_timeframes": resample_timeframes,
        },
    )


def _find_exact_dataset(
    data_status: dict[str, Any],
    *,
    market: str,
    symbol: str,
    timeframe: str,
) -> dict[str, Any]:
    items = data_status.get("available") if isinstance(data_status.get("available"), list) else []
    market_norm = str(market or "").strip().lower()
    symbol_norm = str(symbol or "").strip().upper()
    timeframe_norm = str(timeframe or "").strip().lower()
    exact = [
        row for row in items
        if isinstance(row, dict)
        and str(row.get("market") or "").strip().lower() == market_norm
        and str(row.get("symbol") or "").strip().upper() == symbol_norm
        and str(row.get("timeframe") or "").strip().lower() == timeframe_norm
    ]
    fallback = [
        row for row in items
        if isinstance(row, dict)
        and str(row.get("market") or "").strip().lower() == market_norm
        and str(row.get("symbol") or "").strip().upper() == symbol_norm
    ]
    return {
        "exact_present": bool(exact),
        "exact_matches": exact,
        "fallback_symbol_matches": fallback,
    }


def _build_markdown(report: dict[str, Any]) -> str:
    auth = report.get("auth") if isinstance(report.get("auth"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
    health = report.get("health") if isinstance(report.get("health"), dict) else {}
    beast = report.get("beast_status") if isinstance(report.get("beast_status"), dict) else {}
    data = report.get("data_status") if isinstance(report.get("data_status"), dict) else {}
    dataset = report.get("dataset_probe") if isinstance(report.get("dataset_probe"), dict) else {}
    endpoint_errors = report.get("endpoint_errors") if isinstance(report.get("endpoint_errors"), dict) else {}
    lines = [
        "# Beast Runtime Status Report",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- base_url: `{report.get('base_url')}`",
        f"- target_dataset: `{report.get('market')}/{report.get('symbol')}/{report.get('timeframe')}`",
        "",
        "## Auth",
        f"- auth_source: `{auth.get('auth_source')}`",
        f"- auth_ok: `{auth.get('ok')}`",
        f"- auth_error: `{auth.get('error') or ''}`",
        "",
        "## Runtime",
        f"- health_ok: `{checks.get('health_ok')}`",
        f"- user_data_dir: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('user_data_dir')}`",
        f"- configured_user_data_dir: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('configured_user_data_dir')}`",
        f"- persistent_storage: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('persistent_storage')}`",
        f"- mount_detected: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('mount_detected')}`",
        f"- mount_point: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('mount_point')}`",
        f"- mount_source: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('mount_source')}`",
        f"- selection_drift: `{((health.get('storage') or {}) if isinstance(health.get('storage'), dict) else {}).get('selection_drift')}`",
        f"- runtime_engine: `{health.get('runtime_engine')}`",
        f"- bootstrap_attempted: `{checks.get('bootstrap_attempted')}`",
        f"- bootstrap_ok: `{checks.get('bootstrap_ok')}`",
        "",
        "## Beast",
        f"- beast_status_ok: `{checks.get('beast_status_ok')}`",
        f"- policy_state: `{beast.get('policy_state')}`",
        f"- policy_available: `{beast.get('policy_available')}`",
        f"- policy_enabled_declared: `{beast.get('policy_enabled_declared')}`",
        f"- policy_source_root: `{beast.get('policy_source_root')}`",
        f"- policy_warnings: `{json.dumps(beast.get('policy_warnings') or [], ensure_ascii=False)}`",
        "",
        "## Data",
        f"- data_status_ok: `{checks.get('data_status_ok')}`",
        f"- data_root: `{data.get('data_root')}`",
        f"- available_count: `{data.get('available_count')}`",
        f"- missing_count: `{data.get('missing_count')}`",
        f"- exact_dataset_present: `{dataset.get('exact_present')}`",
        f"- fallback_symbol_matches: `{len(dataset.get('fallback_symbol_matches') or [])}`",
        f"- post_wait_available_count: `{((report.get('post_wait_data_status') or {}) if isinstance(report.get('post_wait_data_status'), dict) else {}).get('available_count')}`",
        f"- post_wait_exact_dataset_present: `{((report.get('post_wait_dataset_probe') or {}) if isinstance(report.get('post_wait_dataset_probe'), dict) else {}).get('exact_present')}`",
        "",
        "## Overall",
        f"- overall_pass: `{checks.get('overall_pass')}`",
        "",
        "## Endpoint errors",
    ]
    if endpoint_errors:
        for key, value in endpoint_errors.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnostico autenticado de Beast/data status en staging.")
    parser.add_argument("--base-url", default="https://bot-trading-ia-staging.up.railway.app")
    parser.add_argument("--username", default=os.getenv("RTLAB_USERNAME", "Wadmin"))
    parser.add_argument("--password", default="")
    parser.add_argument("--auth-token", default=os.getenv("RTLAB_AUTH_TOKEN", ""))
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--market", default="crypto")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--bootstrap-crypto-public", action="store_true")
    parser.add_argument("--bootstrap-futures-public", action="store_true")
    parser.add_argument("--bootstrap-market-family", default="usdm")
    parser.add_argument("--bootstrap-start-month", default="")
    parser.add_argument("--bootstrap-end-month", default="")
    parser.add_argument("--bootstrap-resample-timeframes", nargs="*", default=["5m", "15m", "1h", "4h", "1d"])
    parser.add_argument("--post-bootstrap-wait-sec", type=float, default=0.0)
    parser.add_argument("--require-mounted-storage", action="store_true")
    parser.add_argument("--require-exact-dataset", action="store_true")
    parser.add_argument("--report-prefix", default="artifacts/beast_runtime_status")
    parser.add_argument("--strict", dest="strict", action="store_true", default=True)
    parser.add_argument("--no-strict", dest="strict", action="store_false")
    return parser


def main() -> int:
    args = _parser().parse_args()
    timeout_sec = max(1.0, float(args.timeout_sec))
    base_url = _normalize_url(args.base_url)
    market = str(args.market or "").strip().lower()
    symbol = str(args.symbol or "").strip().upper()
    timeframe = str(args.timeframe or "").strip().lower()

    password = _resolve_password(str(args.password or ""))
    token, auth_source, auth_error = _resolve_token(
        base_url=base_url,
        timeout_sec=timeout_sec,
        username=str(args.username or "Wadmin"),
        password=password,
        auth_token=str(args.auth_token or ""),
    )

    report: dict[str, Any] = {
        "generated_at_utc": _now_utc().isoformat(),
        "base_url": base_url,
        "market": market,
        "symbol": symbol,
        "timeframe": timeframe,
        "auth": {
            "auth_source": auth_source,
            "ok": bool(token),
            "error": auth_error,
        },
        "endpoint_errors": {},
        "health": {},
        "data_status": {},
        "beast_status": {},
        "bootstrap": {},
        "post_wait_data_status": {},
        "post_wait_dataset_probe": {},
        "dataset_probe": {},
        "checks": {
            "health_ok": False,
            "data_status_ok": False,
            "beast_status_ok": False,
            "bootstrap_attempted": bool(args.bootstrap_crypto_public or args.bootstrap_futures_public),
            "bootstrap_ok": False,
            "overall_pass": False,
        },
    }

    health, err_health, _ = _http_json(
        method="GET",
        url=f"{base_url}/api/v1/health",
        timeout_sec=timeout_sec,
    )
    if err_health:
        report["endpoint_errors"]["health"] = err_health
    else:
        report["health"] = health
        report["checks"]["health_ok"] = bool(health.get("ok"))

    if token:
        headers = _auth_headers(token)
        if args.bootstrap_crypto_public:
            bootstrap_start_month = str(args.bootstrap_start_month or "").strip()
            bootstrap_end_month = str(args.bootstrap_end_month or "").strip()
            bootstrap_payload, bootstrap_error, _ = _bootstrap_crypto_public(
                base_url=base_url,
                timeout_sec=timeout_sec,
                token=token,
                symbol=symbol,
                start_month=bootstrap_start_month,
                end_month=bootstrap_end_month,
            )
            if bootstrap_error:
                report["endpoint_errors"]["data_bootstrap_crypto_binance_public"] = bootstrap_error
            else:
                report["bootstrap"] = bootstrap_payload
                report["checks"]["bootstrap_ok"] = bool(bootstrap_payload.get("ok"))
        elif args.bootstrap_futures_public:
            bootstrap_start_month = str(args.bootstrap_start_month or "").strip()
            bootstrap_end_month = str(args.bootstrap_end_month or "").strip()
            bootstrap_payload, bootstrap_error, _ = _bootstrap_futures_public(
                base_url=base_url,
                timeout_sec=timeout_sec,
                token=token,
                market_family=str(args.bootstrap_market_family or "usdm").strip().lower(),
                symbol=symbol,
                start_month=bootstrap_start_month,
                end_month=bootstrap_end_month,
                resample_timeframes=[str(item).strip() for item in args.bootstrap_resample_timeframes if str(item).strip()],
            )
            if bootstrap_error:
                report["endpoint_errors"]["data_bootstrap_binance_futures_public"] = bootstrap_error
            else:
                report["bootstrap"] = bootstrap_payload
                report["checks"]["bootstrap_ok"] = bool(bootstrap_payload.get("ok"))
        data_status, err_data, _ = _http_json(
            method="GET",
            url=f"{base_url}/api/v1/data/status",
            timeout_sec=timeout_sec,
            headers=headers,
        )
        beast_status, err_beast, _ = _http_json(
            method="GET",
            url=f"{base_url}/api/v1/research/beast/status",
            timeout_sec=timeout_sec,
            headers=headers,
        )
        if err_data:
            report["endpoint_errors"]["data_status"] = err_data
        else:
            report["data_status"] = data_status
            report["dataset_probe"] = _find_exact_dataset(
                data_status,
                market=market,
                symbol=symbol,
                timeframe=timeframe,
            )
            report["checks"]["data_status_ok"] = True
        if err_beast:
            report["endpoint_errors"]["beast_status"] = err_beast
        else:
            report["beast_status"] = beast_status
            report["checks"]["beast_status_ok"] = True

        if float(args.post_bootstrap_wait_sec or 0.0) > 0:
            import time

            time.sleep(max(0.0, float(args.post_bootstrap_wait_sec)))
            post_wait_data_status, post_wait_err, _ = _http_json(
                method="GET",
                url=f"{base_url}/api/v1/data/status",
                timeout_sec=timeout_sec,
                headers=headers,
            )
            if post_wait_err:
                report["endpoint_errors"]["data_status_post_wait"] = post_wait_err
            else:
                report["post_wait_data_status"] = post_wait_data_status
                report["post_wait_dataset_probe"] = _find_exact_dataset(
                    post_wait_data_status,
                    market=market,
                    symbol=symbol,
                    timeframe=timeframe,
                )
    else:
        report["endpoint_errors"]["auth"] = auth_error or auth_source

    beast_policy_state = str((report.get("beast_status") or {}).get("policy_state") or "").strip().lower()
    storage = report.get("health", {}).get("storage") if isinstance(report.get("health"), dict) else {}
    storage_mount_detected = bool(storage.get("mount_detected")) if isinstance(storage, dict) else False
    dataset_probe = report.get("post_wait_dataset_probe") if isinstance(report.get("post_wait_dataset_probe"), dict) and report.get("post_wait_dataset_probe") else report.get("dataset_probe")
    exact_dataset_present = bool((dataset_probe or {}).get("exact_present")) if isinstance(dataset_probe, dict) else False
    report["checks"]["overall_pass"] = bool(
        report["checks"]["health_ok"]
        and report["checks"]["data_status_ok"]
        and report["checks"]["beast_status_ok"]
        and (not args.bootstrap_crypto_public or report["checks"]["bootstrap_ok"])
        and (not args.bootstrap_futures_public or report["checks"]["bootstrap_ok"])
        and (not args.require_mounted_storage or storage_mount_detected)
        and (not args.require_exact_dataset or exact_dataset_present)
        and beast_policy_state != "missing"
    )

    stamp = _now_utc().strftime("%Y%m%d_%H%M%S")
    report_prefix = str(args.report_prefix or "artifacts/beast_runtime_status").strip()
    json_out = (REPO_ROOT / f"{report_prefix}_{stamp}.json").resolve()
    md_out = (REPO_ROOT / f"{report_prefix}_{stamp}.md").resolve()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_build_markdown(report), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"REPORT_JSON={json_out}")
    print(f"REPORT_MD={md_out}")

    if args.strict and not report["checks"]["overall_pass"]:
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

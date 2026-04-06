#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELED"}


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
        body = str(response.text or "")[:1000]
        return {}, f"http_{response.status_code}: {body}", int(response.status_code)
    if "json" not in str(response.headers.get("content-type", "")).lower():
        return {}, "not_json", int(response.status_code)
    payload = response.json()
    if isinstance(payload, list):
        return {"items": payload}, "", int(response.status_code)
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


def _find_dataset_matches(data_status: dict[str, Any], *, market: str, symbol: str, timeframe: str) -> dict[str, Any]:
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


def _pick_strategy(strategies_payload: dict[str, Any], requested_strategy_id: str | None) -> tuple[dict[str, Any], str]:
    items_raw = strategies_payload.get("items")
    if isinstance(items_raw, list):
        items = [row for row in items_raw if isinstance(row, dict)]
    else:
        items = [row for row in strategies_payload.values() if isinstance(row, dict)]
    if not items and isinstance(strategies_payload, dict):
        if all(isinstance(row, dict) for row in strategies_payload.values()):
            items = list(strategies_payload.values())
    requested = str(requested_strategy_id or "").strip()
    if requested:
        for row in items:
            if str(row.get("id") or "") == requested:
                return row, requested
        raise RuntimeError(f"Estrategia requerida no encontrada: {requested}")
    preferred = "trend_pullback_orderflow_confirm_v1"
    for row in items:
        if str(row.get("id") or "") == preferred:
            return row, preferred
    if not items:
        raise RuntimeError("No hay estrategias disponibles en /api/v1/strategies")
    chosen = items[0]
    return chosen, str(chosen.get("id") or "")


def _safe_json(
    *,
    method: str,
    base_url: str,
    path: str,
    timeout_sec: float,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    payload, error, _ = _http_json(
        method=method,
        url=f"{base_url}{path}",
        timeout_sec=timeout_sec,
        headers=headers,
        json_body=json_body,
    )
    return payload, error


def _poll_run(
    *,
    base_url: str,
    headers: dict[str, str],
    run_id: str,
    timeout_sec: float,
    poll_interval_sec: float,
    max_wait_sec: float,
) -> dict[str, Any]:
    started = time.monotonic()
    history: list[dict[str, Any]] = []
    last_status: dict[str, Any] = {}
    last_jobs: dict[str, Any] = {}
    last_detail: dict[str, Any] = {}
    last_results: dict[str, Any] = {}
    terminal_state = ""
    last_error = ""
    while True:
        status_payload, status_error = _safe_json(
            method="GET",
            base_url=base_url,
            path=f"/api/v1/research/mass-backtest/status?run_id={run_id}",
            timeout_sec=timeout_sec,
            headers=headers,
        )
        jobs_payload, jobs_error = _safe_json(
            method="GET",
            base_url=base_url,
            path="/api/v1/research/beast/jobs?limit=20",
            timeout_sec=timeout_sec,
            headers=headers,
        )
        detail_payload, detail_error = _safe_json(
            method="GET",
            base_url=base_url,
            path=f"/api/v1/backtests/runs/{run_id}",
            timeout_sec=timeout_sec,
            headers=headers,
        )
        results_payload, results_error = _safe_json(
            method="GET",
            base_url=base_url,
            path=f"/api/v1/research/mass-backtest/results?run_id={run_id}&limit=10",
            timeout_sec=timeout_sec,
            headers=headers,
        )
        snapshot = {
            "observed_at_utc": _now_utc().isoformat(),
            "status_error": status_error,
            "jobs_error": jobs_error,
            "detail_error": detail_error,
            "results_error": results_error,
            "status_state": str(status_payload.get("state") or ""),
        }
        history.append(snapshot)
        if status_payload:
            last_status = status_payload
        if jobs_payload:
            last_jobs = jobs_payload
        if detail_payload:
            last_detail = detail_payload
        if results_payload:
            last_results = results_payload
        state = str((status_payload or {}).get("state") or "").upper()
        if state in TERMINAL_STATES:
            terminal_state = state
            break
        if status_error:
            last_error = status_error
        elapsed = time.monotonic() - started
        if elapsed >= max_wait_sec:
            break
        time.sleep(max(0.5, poll_interval_sec))
    return {
        "history": history,
        "status": last_status,
        "jobs": last_jobs,
        "detail": last_detail,
        "results": last_results,
        "terminal_state": terminal_state,
        "last_error": last_error,
        "timed_out": not bool(terminal_state),
    }


def _build_markdown(report: dict[str, Any]) -> str:
    auth = report.get("auth") if isinstance(report.get("auth"), dict) else {}
    target = report.get("target") if isinstance(report.get("target"), dict) else {}
    before = report.get("before") if isinstance(report.get("before"), dict) else {}
    run = report.get("run") if isinstance(report.get("run"), dict) else {}
    start_payload = run.get("start_response") if isinstance(run.get("start_response"), dict) else {}
    poll = run.get("poll") if isinstance(run.get("poll"), dict) else {}
    data_after = poll.get("data_status_after") if isinstance(poll.get("data_status_after"), dict) else {}
    dataset_after = poll.get("dataset_probe_after") if isinstance(poll.get("dataset_probe_after"), dict) else {}
    status = poll.get("status") if isinstance(poll.get("status"), dict) else {}
    detail = poll.get("detail") if isinstance(poll.get("detail"), dict) else {}
    results = poll.get("results") if isinstance(poll.get("results"), dict) else {}
    lines = [
        "# Beast Staging E2E Report",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- base_url: `{report.get('base_url')}`",
        f"- auth_source: `{auth.get('auth_source')}`",
        f"- auth_ok: `{auth.get('ok')}`",
        "",
        "## Target",
        f"- strategy_id: `{target.get('strategy_id')}`",
        f"- market/symbol/timeframe: `{target.get('market')}/{target.get('symbol')}/{target.get('timeframe')}`",
        f"- period: `{target.get('start')} -> {target.get('end')}`",
        f"- dataset_source: `{target.get('dataset_source')}`",
        f"- use_orderflow_data: `{target.get('use_orderflow_data')}`",
        "",
        "## Before",
        f"- beast_policy_state: `{((before.get('beast_status') or {}) if isinstance(before.get('beast_status'), dict) else {}).get('policy_state')}`",
        f"- data_root: `{((before.get('data_status') or {}) if isinstance(before.get('data_status'), dict) else {}).get('data_root')}`",
        f"- exact_dataset_present: `{((before.get('dataset_probe') or {}) if isinstance(before.get('dataset_probe'), dict) else {}).get('exact_present')}`",
        f"- fallback_symbol_matches: `{len((((before.get('dataset_probe') or {}) if isinstance(before.get('dataset_probe'), dict) else {}).get('fallback_symbol_matches') or []))}`",
        "",
        "## Run",
        f"- start_ok: `{start_payload.get('ok')}`",
        f"- run_id: `{start_payload.get('run_id')}`",
        f"- queue_state: `{start_payload.get('state')}`",
        f"- queue_position: `{start_payload.get('queue_position')}`",
        f"- terminal_state: `{poll.get('terminal_state')}`",
        f"- timed_out: `{poll.get('timed_out')}`",
        f"- results_count: `{len((results.get('results') or []) if isinstance(results.get('results'), list) else [])}`",
        "",
        "## Data After",
        f"- data_root: `{data_after.get('data_root')}`",
        f"- available_count: `{data_after.get('available_count')}`",
        f"- exact_dataset_present: `{dataset_after.get('exact_present')}`",
        f"- fallback_symbol_matches: `{len((dataset_after.get('fallback_symbol_matches') or []))}`",
        "",
        "## Summary",
        f"- status_state: `{status.get('state')}`",
        f"- detail_state: `{detail.get('state')}`",
        f"- overall_pass: `{report.get('checks', {}).get('overall_pass')}`",
        "",
        "## Errors",
    ]
    endpoint_errors = report.get("endpoint_errors") if isinstance(report.get("endpoint_errors"), dict) else {}
    if endpoint_errors:
        for key, value in endpoint_errors.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Testeo E2E de Beast en staging sobre BTCUSDT.")
    parser.add_argument("--base-url", default="https://bot-trading-ia-staging.up.railway.app")
    parser.add_argument("--username", default=os.getenv("RTLAB_USERNAME", "Wadmin"))
    parser.add_argument("--password", default="")
    parser.add_argument("--auth-token", default=os.getenv("RTLAB_AUTH_TOKEN", ""))
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--poll-interval-sec", type=float, default=2.0)
    parser.add_argument("--max-wait-sec", type=float, default=180.0)
    parser.add_argument("--market", default="crypto")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="5m")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2024-03-31")
    parser.add_argument("--dataset-source", default="auto")
    parser.add_argument("--data-mode", default="dataset")
    parser.add_argument("--validation-mode", default="walk-forward")
    parser.add_argument("--max-variants-per-strategy", type=int, default=1)
    parser.add_argument("--max-folds", type=int, default=2)
    parser.add_argument("--train-days", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--top-n", type=int, default=2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--tier", default="hobby")
    parser.add_argument("--strategy-id", default="")
    parser.add_argument("--use-orderflow-data", dest="use_orderflow_data", action="store_true", default=False)
    parser.add_argument("--no-orderflow-data", dest="use_orderflow_data", action="store_false")
    parser.add_argument("--bootstrap-crypto-public", action="store_true")
    parser.add_argument("--bootstrap-start-month", default="2024-01")
    parser.add_argument("--bootstrap-end-month", default="2024-12")
    parser.add_argument("--bootstrap-timeout-sec", type=float, default=180.0)
    parser.add_argument("--report-prefix", default="artifacts/beast_staging_e2e")
    parser.add_argument("--strict", dest="strict", action="store_true", default=True)
    parser.add_argument("--no-strict", dest="strict", action="store_false")
    return parser


def main() -> int:
    args = _parser().parse_args()
    timeout_sec = max(1.0, float(args.timeout_sec))
    base_url = _normalize_url(args.base_url)
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
        "auth": {
            "auth_source": auth_source,
            "ok": bool(token),
            "error": auth_error,
        },
        "target": {},
        "before": {},
        "run": {},
        "endpoint_errors": {},
        "checks": {
            "auth_ok": bool(token),
            "start_ok": False,
            "run_completed": False,
            "results_present": False,
            "overall_pass": False,
        },
    }
    if not token:
        report["endpoint_errors"]["auth"] = auth_error or auth_source
    else:
        headers = _auth_headers(token)
        health, health_error = _safe_json(method="GET", base_url=base_url, path="/api/v1/health", timeout_sec=timeout_sec, headers=headers)
        if health_error:
            report["endpoint_errors"]["health"] = health_error
        data_status_before, data_error = _safe_json(method="GET", base_url=base_url, path="/api/v1/data/status", timeout_sec=timeout_sec, headers=headers)
        if data_error:
            report["endpoint_errors"]["data_status_before"] = data_error
        beast_before, beast_error = _safe_json(method="GET", base_url=base_url, path="/api/v1/research/beast/status", timeout_sec=timeout_sec, headers=headers)
        if beast_error:
            report["endpoint_errors"]["beast_status_before"] = beast_error
        if args.bootstrap_crypto_public:
            bootstrap_payload, bootstrap_error, _ = _http_json(
                method="POST",
                url=f"{base_url}/api/v1/data/bootstrap/crypto-binance-public",
                timeout_sec=max(timeout_sec, float(args.bootstrap_timeout_sec)),
                headers=headers,
                json_body={
                    "symbols": [str(args.symbol or "BTCUSDT").strip().upper()],
                    "start_month": str(args.bootstrap_start_month or "").strip(),
                    "end_month": str(args.bootstrap_end_month or "").strip(),
                },
            )
            if bootstrap_error:
                report["endpoint_errors"]["bootstrap"] = bootstrap_error
            else:
                report["run"]["bootstrap"] = bootstrap_payload
        strategies_payload, strategies_error = _safe_json(
            method="GET",
            base_url=base_url,
            path="/api/v1/strategies",
            timeout_sec=timeout_sec,
            headers=headers,
        )
        if strategies_error:
            report["endpoint_errors"]["strategies"] = strategies_error
        else:
            strategy_row, strategy_id = _pick_strategy(strategies_payload, str(args.strategy_id or ""))
            dataset_probe_before = _find_dataset_matches(
                data_status_before,
                market=str(args.market or ""),
                symbol=str(args.symbol or ""),
                timeframe=str(args.timeframe or ""),
            )
            report["before"] = {
                "health": health,
                "data_status": data_status_before,
                "beast_status": beast_before,
                "dataset_probe": dataset_probe_before,
            }
            payload = {
                "bot_id": "BOT-STAGING-BEAST-E2E",
                "strategy_ids": [strategy_id],
                "market": str(args.market or "crypto"),
                "symbol": str(args.symbol or "BTCUSDT").strip().upper(),
                "timeframe": str(args.timeframe or "5m").strip().lower(),
                "start": str(args.start or "2024-01-01"),
                "end": str(args.end or "2024-03-31"),
                "dataset_source": str(args.dataset_source or "auto"),
                "data_mode": str(args.data_mode or "dataset"),
                "validation_mode": str(args.validation_mode or "walk-forward"),
                "max_variants_per_strategy": int(args.max_variants_per_strategy),
                "max_folds": int(args.max_folds),
                "train_days": int(args.train_days),
                "test_days": int(args.test_days),
                "top_n": int(args.top_n),
                "seed": int(args.seed),
                "tier": str(args.tier or "hobby"),
                "use_orderflow_data": bool(args.use_orderflow_data),
            }
            report["target"] = {
                "strategy_id": strategy_id,
                "strategy_name": str(strategy_row.get("name") or ""),
                "market": payload["market"],
                "symbol": payload["symbol"],
                "timeframe": payload["timeframe"],
                "start": payload["start"],
                "end": payload["end"],
                "dataset_source": payload["dataset_source"],
                "data_mode": payload["data_mode"],
                "validation_mode": payload["validation_mode"],
                "use_orderflow_data": payload["use_orderflow_data"],
            }
            start_payload, start_error = _safe_json(
                method="POST",
                base_url=base_url,
                path="/api/v1/research/beast/start",
                timeout_sec=timeout_sec,
                headers=headers,
                json_body=payload,
            )
            if start_error:
                report["endpoint_errors"]["research_beast_start"] = start_error
            else:
                report["run"]["start_response"] = start_payload
                report["checks"]["start_ok"] = bool(start_payload.get("ok"))
                run_id = str(start_payload.get("run_id") or "")
                if run_id:
                    poll = _poll_run(
                        base_url=base_url,
                        headers=headers,
                        run_id=run_id,
                        timeout_sec=timeout_sec,
                        poll_interval_sec=float(args.poll_interval_sec),
                        max_wait_sec=float(args.max_wait_sec),
                    )
                    data_status_after, data_after_error = _safe_json(
                        method="GET",
                        base_url=base_url,
                        path="/api/v1/data/status",
                        timeout_sec=timeout_sec,
                        headers=headers,
                    )
                    if data_after_error:
                        report["endpoint_errors"]["data_status_after"] = data_after_error
                    poll["data_status_after"] = data_status_after
                    poll["dataset_probe_after"] = _find_dataset_matches(
                        data_status_after,
                        market=payload["market"],
                        symbol=payload["symbol"],
                        timeframe=payload["timeframe"],
                    )
                    report["run"]["poll"] = poll
                    terminal_state = str(poll.get("terminal_state") or "").upper()
                    report["checks"]["run_completed"] = terminal_state == "COMPLETED"
                    results_payload = poll.get("results") if isinstance(poll.get("results"), dict) else {}
                    report["checks"]["results_present"] = bool(results_payload.get("results"))

    report["checks"]["overall_pass"] = bool(
        report["checks"]["auth_ok"]
        and report["checks"]["start_ok"]
        and report["checks"]["run_completed"]
        and report["checks"]["results_present"]
    )

    stamp = _now_utc().strftime("%Y%m%d_%H%M%S")
    report_prefix = str(args.report_prefix or "artifacts/beast_staging_e2e").strip()
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

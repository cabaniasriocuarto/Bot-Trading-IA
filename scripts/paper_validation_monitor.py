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


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ts_compact() -> str:
    return _now_utc().strftime("%Y%m%d_%H%M%S")


def _normalize_base_url(url: str) -> str:
    value = str(url or "").strip()
    return value[:-1] if value.endswith("/") else value


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


def _request_json(
    *,
    method: str,
    base_url: str,
    path: str,
    timeout_sec: float,
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, int]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.request(
            method=method.upper(),
            url=f"{base_url}{path}",
            headers=headers,
            json=body,
            timeout=timeout_sec,
        )
    except Exception as exc:
        return {}, f"request_error: {exc}", 0
    if response.status_code != 200:
        return {}, f"http_{response.status_code}: {str(response.text or '')[:300]}", int(response.status_code)
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
    if not username or not password:
        return "", "missing_local_auth", "Falta RTLAB_AUTH_TOKEN o RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD."
    try:
        response = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
            timeout=timeout_sec,
        )
    except Exception as exc:
        return "", "login_request_error", str(exc)
    if response.status_code != 200:
        return "", f"login_http_{response.status_code}", str(response.text or "")[:300]
    if "json" not in str(response.headers.get("content-type", "")).lower():
        return "", "login_not_json", ""
    payload = response.json()
    token = str((payload or {}).get("token") or (payload or {}).get("access_token") or "").strip()
    if not token:
        return "", "login_no_token", ""
    return token, "login_password_env", ""


def _items_count(payload: dict[str, Any]) -> int | None:
    if not isinstance(payload, dict):
        return None
    items = payload.get("items")
    if isinstance(items, list):
        return len(items)
    try:
        return int(payload.get("count"))
    except Exception:
        return None


def _parse_iso(value: Any) -> dt.datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        parsed = dt.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        return None


def _hours_between(start: dt.datetime | None, end: dt.datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return max(0.0, (end - start).total_seconds() / 3600.0)


def _status_summary(payload: dict[str, Any], *, status_code: int) -> dict[str, Any]:
    runtime_snapshot = payload.get("runtime_snapshot") if isinstance(payload.get("runtime_snapshot"), dict) else {}
    return {
        "ok": True,
        "status_code": status_code,
        "mode": payload.get("mode"),
        "bot_status": payload.get("bot_status"),
        "runtime_engine": payload.get("runtime_engine"),
        "runtime_ready_for_live": payload.get("runtime_ready_for_live"),
        "runtime_last_signal_strategy_id": runtime_snapshot.get("runtime_last_signal_strategy_id"),
        "runtime_last_signal_reason": runtime_snapshot.get("runtime_last_signal_reason"),
        "runtime_last_signal_symbol": runtime_snapshot.get("runtime_last_signal_symbol"),
        "runtime_last_signal_side": runtime_snapshot.get("runtime_last_signal_side"),
        "runtime_last_remote_submit_reason": runtime_snapshot.get("runtime_last_remote_submit_reason"),
        "runtime_last_remote_submit_error": runtime_snapshot.get("runtime_last_remote_submit_error"),
        "runtime_last_remote_client_order_id": runtime_snapshot.get("runtime_last_remote_client_order_id"),
    }


def _latest_paper_run(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    for row in items:
        if isinstance(row, dict) and str(row.get("stage") or "").strip().upper() == "PAPER":
            return row
    return {}


def _paper_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    by_stage = payload.get("readiness_by_stage") if isinstance(payload.get("readiness_by_stage"), dict) else {}
    paper = by_stage.get("paper") if isinstance(by_stage.get("paper"), dict) else {}
    return {
        "live_serio_ready": payload.get("live_serio_ready"),
        "paper": paper,
    }


def _latest_run_metrics(run: dict[str, Any]) -> dict[str, Any]:
    key_metrics = run.get("key_metrics_json") if isinstance(run.get("key_metrics_json"), dict) else {}
    blocking = run.get("blocking_reasons_json") if isinstance(run.get("blocking_reasons_json"), list) else []
    warnings = run.get("warnings_json") if isinstance(run.get("warnings_json"), list) else []
    return {
        "validation_run_id": run.get("validation_run_id"),
        "created_at": run.get("created_at"),
        "result": run.get("result"),
        "total_orders": run.get("total_orders"),
        "total_fills": run.get("total_fills"),
        "gross_pnl": run.get("gross_pnl"),
        "net_pnl": run.get("net_pnl"),
        "total_cost_realized": run.get("total_cost_realized"),
        "trading_days": key_metrics.get("trading_days"),
        "gross_net_inconsistency_rate_pct": key_metrics.get("gross_net_inconsistency_rate_pct"),
        "blocking_reasons_json": blocking,
        "warnings_json": warnings,
    }


def _load_previous_report(path: str) -> dict[str, Any]:
    value = str(path or "").strip()
    if not value:
        return {}
    target = Path(value)
    if not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _build_current_snapshot(*, status_summary: dict[str, Any], orders_payload: dict[str, Any], latest_run: dict[str, Any], readiness_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at_utc": _now_utc().isoformat(),
        "bot_status": status_summary.get("bot_status"),
        "mode": status_summary.get("mode"),
        "runtime_engine": status_summary.get("runtime_engine"),
        "orders_endpoint_count": _items_count(orders_payload),
        "latest_result": latest_run.get("result"),
        "validation_run_id": latest_run.get("validation_run_id"),
        "latest_total_orders": latest_run.get("total_orders"),
        "latest_total_fills": latest_run.get("total_fills"),
        "trading_days": latest_run.get("trading_days"),
        "blocking_reasons_json": latest_run.get("blocking_reasons_json"),
        "readiness_paper": readiness_summary.get("paper") if isinstance(readiness_summary.get("paper"), dict) else {},
    }


def _compute_diff(previous_report: dict[str, Any], current_snapshot: dict[str, Any]) -> dict[str, Any]:
    current_generated = _parse_iso(current_snapshot.get("generated_at_utc"))
    previous_snapshot = previous_report.get("snapshot") if isinstance(previous_report.get("snapshot"), dict) else {}
    previous_generated = _parse_iso(previous_snapshot.get("generated_at_utc") or previous_report.get("generated_at_utc"))
    previous_orders_endpoint = previous_snapshot.get("orders_endpoint_count")
    previous_latest_total_orders = previous_snapshot.get("latest_total_orders")
    previous_latest_total_fills = previous_snapshot.get("latest_total_fills")
    previous_result = previous_snapshot.get("latest_result")
    current_orders_endpoint = current_snapshot.get("orders_endpoint_count")
    current_latest_total_orders = current_snapshot.get("latest_total_orders")
    current_latest_total_fills = current_snapshot.get("latest_total_fills")
    diff = {
        "previous_observation_found": bool(previous_report),
        "previous_generated_at_utc": previous_snapshot.get("generated_at_utc") or previous_report.get("generated_at_utc"),
        "hours_since_previous": _hours_between(previous_generated, current_generated),
        "orders_endpoint_delta": None,
        "latest_total_orders_delta": None,
        "latest_total_fills_delta": None,
        "latest_result_changed": previous_result != current_snapshot.get("latest_result") if previous_report else None,
        "blocking_reasons_changed": None,
    }
    try:
        if previous_orders_endpoint is not None and current_orders_endpoint is not None:
            diff["orders_endpoint_delta"] = int(current_orders_endpoint) - int(previous_orders_endpoint)
    except Exception:
        pass
    try:
        if previous_latest_total_orders is not None and current_latest_total_orders is not None:
            diff["latest_total_orders_delta"] = int(current_latest_total_orders) - int(previous_latest_total_orders)
    except Exception:
        pass
    try:
        if previous_latest_total_fills is not None and current_latest_total_fills is not None:
            diff["latest_total_fills_delta"] = int(current_latest_total_fills) - int(previous_latest_total_fills)
    except Exception:
        pass
    if previous_report:
        diff["blocking_reasons_changed"] = (
            list(previous_snapshot.get("blocking_reasons_json") or []) != list(current_snapshot.get("blocking_reasons_json") or [])
        )
    return diff


def _should_reevaluate(*, orders_count: int | None, latest_run: dict[str, Any], max_age_hours: float) -> dict[str, Any]:
    latest_total_orders = latest_run.get("total_orders")
    latest_created_at = _parse_iso(latest_run.get("created_at"))
    run_age_hours = _hours_between(latest_created_at, _now_utc())
    reasons: list[str] = []
    if not latest_run:
        reasons.append("missing_latest_paper_run")
    else:
        try:
            if orders_count is not None and latest_total_orders is not None and int(orders_count) > int(latest_total_orders):
                reasons.append("new_orders_detected")
        except Exception:
            pass
        if run_age_hours is not None and float(run_age_hours) >= float(max_age_hours):
            reasons.append(f"latest_run_age_hours>={max_age_hours}")
    return {
        "should_reevaluate": bool(reasons),
        "reasons": reasons,
        "latest_run_age_hours": run_age_hours,
        "orders_endpoint_count": orders_count,
        "latest_run_total_orders": latest_total_orders,
    }


def _build_markdown(report: dict[str, Any]) -> str:
    config = report.get("config") if isinstance(report.get("config"), dict) else {}
    snapshot = report.get("snapshot") if isinstance(report.get("snapshot"), dict) else {}
    diff = report.get("diff") if isinstance(report.get("diff"), dict) else {}
    reevaluate = report.get("reevaluate") if isinstance(report.get("reevaluate"), dict) else {}
    overall = report.get("overall") if isinstance(report.get("overall"), dict) else {}
    failures = overall.get("failures") if isinstance(overall.get("failures"), list) else []
    warnings = overall.get("warnings") if isinstance(overall.get("warnings"), list) else []
    lines = [
        "# Paper Validation Monitor",
        "",
        "## Config",
        f"- cadence_minutes: `{config.get('cadence_minutes')}`",
        f"- reevaluate_max_age_hours: `{config.get('reevaluate_max_age_hours')}`",
        f"- stagnant_warn_after_hours: `{config.get('stagnant_warn_after_hours')}`",
        f"- stagnant_fail_after_hours: `{config.get('stagnant_fail_after_hours')}`",
        f"- orders_limit: `{config.get('orders_limit')}`",
        "",
        "## Current",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- auth_ok: `{(report.get('auth') or {}).get('ok')}`",
        f"- health_ok: `{((report.get('endpoints') or {}).get('health') or {}).get('ok')}`",
        f"- mode: `{snapshot.get('mode')}`",
        f"- bot_status: `{snapshot.get('bot_status')}`",
        f"- runtime_engine: `{snapshot.get('runtime_engine')}`",
        f"- orders_endpoint_count: `{snapshot.get('orders_endpoint_count')}`",
        f"- latest_result: `{snapshot.get('latest_result')}`",
        f"- validation_run_id: `{snapshot.get('validation_run_id')}`",
        f"- latest_total_orders: `{snapshot.get('latest_total_orders')}`",
        f"- latest_total_fills: `{snapshot.get('latest_total_fills')}`",
        f"- trading_days: `{snapshot.get('trading_days')}`",
        f"- blocking_reasons_json: `{json.dumps(snapshot.get('blocking_reasons_json') or [], ensure_ascii=False)}`",
        "",
        "## Reevaluation",
        f"- should_reevaluate: `{reevaluate.get('should_reevaluate')}`",
        f"- reasons: `{json.dumps(reevaluate.get('reasons') or [], ensure_ascii=False)}`",
        f"- evaluate_ok: `{((reevaluate.get('evaluate_result') or {}) if isinstance(reevaluate.get('evaluate_result'), dict) else {}).get('ok')}`",
        f"- evaluate_validation_run_id: `{((reevaluate.get('evaluate_result') or {}) if isinstance(reevaluate.get('evaluate_result'), dict) else {}).get('validation_run_id')}`",
        "",
        "## Diff",
        f"- previous_observation_found: `{diff.get('previous_observation_found')}`",
        f"- previous_generated_at_utc: `{diff.get('previous_generated_at_utc')}`",
        f"- hours_since_previous: `{diff.get('hours_since_previous')}`",
        f"- orders_endpoint_delta: `{diff.get('orders_endpoint_delta')}`",
        f"- latest_total_orders_delta: `{diff.get('latest_total_orders_delta')}`",
        f"- latest_total_fills_delta: `{diff.get('latest_total_fills_delta')}`",
        "",
        "## Overall",
        f"- ok: `{overall.get('ok')}`",
        f"- failures_count: `{len(failures)}`",
        f"- warnings_count: `{len(warnings)}`",
        "",
        "## Failures",
    ]
    if failures:
        for item in failures:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if warnings:
        for item in warnings:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor externo de PAPER en Railway staging.")
    parser.add_argument("--base-url", default="https://bot-trading-ia-staging.up.railway.app")
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
    parser.add_argument("--report-prefix", default="artifacts/paper_validation_monitor")
    parser.add_argument("--state-path", default="artifacts/paper_validation_monitor_state.json")
    parser.add_argument("--previous-report-json", default="")
    parser.add_argument("--orders-limit", type=int, default=200)
    parser.add_argument("--cadence-minutes", type=int, default=30)
    parser.add_argument("--auto-start-bot", action="store_true", default=False)
    parser.add_argument("--bot-start-wait-sec", type=float, default=20.0)
    parser.add_argument("--reevaluate-max-age-hours", type=float, default=6.0)
    parser.add_argument("--stagnant-warn-after-hours", type=float, default=3.0)
    parser.add_argument("--stagnant-fail-after-hours", type=float, default=6.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    timeout_sec = max(1.0, float(args.timeout_sec))
    base_url = _normalize_base_url(args.base_url)
    report_prefix = str(args.report_prefix or "artifacts/paper_validation_monitor").strip()
    state_path = str(args.state_path or "artifacts/paper_validation_monitor_state.json").strip()
    previous_report = _load_previous_report(str(args.previous_report_json or ""))
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
        "github": {
            "run_id": os.getenv("GITHUB_RUN_ID"),
            "workflow": os.getenv("GITHUB_WORKFLOW"),
            "ref_name": os.getenv("GITHUB_REF_NAME"),
            "repository": os.getenv("GITHUB_REPOSITORY"),
        },
        "config": {
            "cadence_minutes": int(args.cadence_minutes),
            "reevaluate_max_age_hours": float(args.reevaluate_max_age_hours),
            "stagnant_warn_after_hours": float(args.stagnant_warn_after_hours),
            "stagnant_fail_after_hours": float(args.stagnant_fail_after_hours),
            "orders_limit": int(args.orders_limit),
            "auto_start_bot": bool(args.auto_start_bot),
            "bot_start_wait_sec": float(args.bot_start_wait_sec),
        },
        "auth": {"ok": bool(token), "source": auth_source, "error": auth_error},
        "endpoints": {},
        "bot_start": {},
        "reevaluate": {},
    }

    failures: list[str] = []
    warnings: list[str] = []
    if not token:
        failures.append(f"auth_unavailable:{auth_source}")

    health, health_err, health_status = _request_json(method="GET", base_url=base_url, path="/api/v1/health", timeout_sec=timeout_sec)
    report["endpoints"]["health"] = {"ok": not bool(health_err), "status_code": health_status, "payload": health if not health_err else {}}
    if health_err:
        report["endpoints"]["health"]["error"] = health_err
        failures.append(f"health_failed:{health_err}")

    status_before, status_before_err, status_before_code = _request_json(
        method="GET", base_url=base_url, path="/api/v1/status", timeout_sec=timeout_sec, token=token
    )
    report["endpoints"]["status_before"] = {
        "ok": not bool(status_before_err),
        "status_code": status_before_code,
        "payload": status_before if not status_before_err else {},
    }
    if status_before_err:
        report["endpoints"]["status_before"]["error"] = status_before_err
        failures.append(f"status_failed:{status_before_err}")
    status_summary = _status_summary(status_before, status_code=status_before_code) if not status_before_err else {}
    if not status_before_err and str(status_summary.get("mode") or "").strip().lower() != "paper":
        failures.append(f"mode_not_paper:{status_summary.get('mode')}")

    if not status_before_err and bool(args.auto_start_bot) and str(status_summary.get("bot_status") or "").strip().upper() != "RUNNING":
        bot_start, bot_start_err, bot_start_code = _request_json(
            method="POST", base_url=base_url, path="/api/v1/bot/start", timeout_sec=timeout_sec, token=token
        )
        report["bot_start"] = {
            "requested": True,
            "ok": not bool(bot_start_err),
            "status_code": bot_start_code,
            "payload": bot_start if not bot_start_err else {},
        }
        if bot_start_err:
            report["bot_start"]["error"] = bot_start_err
            failures.append(f"bot_start_failed:{bot_start_err}")
        elif float(args.bot_start_wait_sec) > 0:
            time.sleep(max(0.0, float(args.bot_start_wait_sec)))
            status_after_start, status_after_start_err, status_after_start_code = _request_json(
                method="GET", base_url=base_url, path="/api/v1/status", timeout_sec=timeout_sec, token=token
            )
            report["endpoints"]["status_after_start"] = {
                "ok": not bool(status_after_start_err),
                "status_code": status_after_start_code,
                "payload": status_after_start if not status_after_start_err else {},
            }
            if status_after_start_err:
                report["endpoints"]["status_after_start"]["error"] = status_after_start_err
                failures.append(f"status_after_start_failed:{status_after_start_err}")
            else:
                status_summary = _status_summary(status_after_start, status_code=status_after_start_code)
    else:
        report["bot_start"] = {"requested": bool(args.auto_start_bot), "ok": True, "status_code": None, "payload": {}}

    orders_payload, orders_err, orders_code = _request_json(
        method="GET",
        base_url=base_url,
        path=f"/api/v1/execution/orders?environment=paper&limit={max(1, int(args.orders_limit))}",
        timeout_sec=timeout_sec,
        token=token,
    )
    report["endpoints"]["orders"] = {"ok": not bool(orders_err), "status_code": orders_code, "payload": orders_payload if not orders_err else {}}
    if orders_err:
        report["endpoints"]["orders"]["error"] = orders_err
        failures.append(f"orders_failed:{orders_err}")

    runs_payload, runs_err, runs_code = _request_json(
        method="GET", base_url=base_url, path="/api/v1/validation/runs?limit=20", timeout_sec=timeout_sec, token=token
    )
    report["endpoints"]["validation_runs"] = {
        "ok": not bool(runs_err),
        "status_code": runs_code,
        "payload": runs_payload if not runs_err else {},
    }
    if runs_err:
        report["endpoints"]["validation_runs"]["error"] = runs_err
        failures.append(f"validation_runs_failed:{runs_err}")

    readiness_payload, readiness_err, readiness_code = _request_json(
        method="GET", base_url=base_url, path="/api/v1/validation/readiness", timeout_sec=timeout_sec, token=token
    )
    report["endpoints"]["readiness"] = {
        "ok": not bool(readiness_err),
        "status_code": readiness_code,
        "payload": readiness_payload if not readiness_err else {},
    }
    if readiness_err:
        report["endpoints"]["readiness"]["error"] = readiness_err
        failures.append(f"readiness_failed:{readiness_err}")

    latest_paper_run = _latest_paper_run(runs_payload) if not runs_err else {}
    readiness_summary = _paper_readiness(readiness_payload) if not readiness_err else {}
    reevaluate_decision = _should_reevaluate(
        orders_count=_items_count(orders_payload), latest_run=latest_paper_run, max_age_hours=max(0.0, float(args.reevaluate_max_age_hours))
    )
    report["reevaluate"] = reevaluate_decision

    if reevaluate_decision.get("should_reevaluate"):
        eval_payload, eval_err, eval_code = _request_json(
            method="POST",
            base_url=base_url,
            path="/api/v1/validation/evaluate",
            timeout_sec=max(timeout_sec, 60.0),
            token=token,
            body={"stage": "PAPER"},
        )
        evaluate_result = {"ok": not bool(eval_err), "status_code": eval_code}
        if eval_err:
            evaluate_result["error"] = eval_err
            failures.append(f"paper_evaluate_failed:{eval_err}")
        else:
            validation_run = eval_payload.get("validation_run") if isinstance(eval_payload.get("validation_run"), dict) else {}
            evaluate_result["validation_run_id"] = validation_run.get("validation_run_id")
            evaluate_result["result"] = validation_run.get("result")
            evaluate_result["blocking_reasons_json"] = validation_run.get("blocking_reasons_json")
            evaluate_result["payload"] = eval_payload
            runs_payload, runs_err, runs_code = _request_json(
                method="GET", base_url=base_url, path="/api/v1/validation/runs?limit=20", timeout_sec=timeout_sec, token=token
            )
            report["endpoints"]["validation_runs_after_reevaluate"] = {
                "ok": not bool(runs_err),
                "status_code": runs_code,
                "payload": runs_payload if not runs_err else {},
            }
            readiness_payload, readiness_err, readiness_code = _request_json(
                method="GET", base_url=base_url, path="/api/v1/validation/readiness", timeout_sec=timeout_sec, token=token
            )
            report["endpoints"]["readiness_after_reevaluate"] = {
                "ok": not bool(readiness_err),
                "status_code": readiness_code,
                "payload": readiness_payload if not readiness_err else {},
            }
            if runs_err:
                report["endpoints"]["validation_runs_after_reevaluate"]["error"] = runs_err
                failures.append(f"validation_runs_after_reevaluate_failed:{runs_err}")
            if readiness_err:
                report["endpoints"]["readiness_after_reevaluate"]["error"] = readiness_err
                failures.append(f"readiness_after_reevaluate_failed:{readiness_err}")
        report["reevaluate"]["evaluate_result"] = evaluate_result
        latest_paper_run = _latest_paper_run(runs_payload) if not runs_err else latest_paper_run
        readiness_summary = _paper_readiness(readiness_payload) if not readiness_err else readiness_summary
    else:
        report["reevaluate"]["evaluate_result"] = {"ok": True, "skipped": True}

    snapshot = _build_current_snapshot(
        status_summary=status_summary,
        orders_payload=orders_payload,
        latest_run=_latest_run_metrics(latest_paper_run) if latest_paper_run else {},
        readiness_summary=readiness_summary,
    )
    report["snapshot"] = snapshot
    report["diff"] = _compute_diff(previous_report, snapshot)

    if str(snapshot.get("bot_status") or "").strip().upper() != "RUNNING":
        failures.append(f"bot_not_running:{snapshot.get('bot_status')}")
    if str(snapshot.get("latest_result") or "").strip().upper() == "BLOCK":
        failures.append("paper_result_block")
    blocking = snapshot.get("blocking_reasons_json") if isinstance(snapshot.get("blocking_reasons_json"), list) else []
    if blocking:
        failures.append(f"paper_blockers_present:{','.join(str(item) for item in blocking)}")

    hours_since_previous = report["diff"].get("hours_since_previous")
    orders_endpoint_delta = report["diff"].get("orders_endpoint_delta")
    if hours_since_previous is not None and orders_endpoint_delta is not None:
        if float(hours_since_previous) >= float(args.stagnant_fail_after_hours) and int(orders_endpoint_delta) <= 0:
            failures.append(f"paper_stagnant_no_order_growth_{float(args.stagnant_fail_after_hours):g}h")
        elif float(hours_since_previous) >= float(args.stagnant_warn_after_hours) and int(orders_endpoint_delta) <= 0:
            warnings.append(f"paper_stagnant_warning_no_order_growth_{float(args.stagnant_warn_after_hours):g}h")

    report["overall"] = {"ok": not bool(failures), "failures": failures, "warnings": warnings}

    stamp = _ts_compact()
    json_out = (REPO_ROOT / f"{report_prefix}_{stamp}.json").resolve()
    md_out = (REPO_ROOT / f"{report_prefix}_{stamp}.md").resolve()
    state_out = (REPO_ROOT / state_path).resolve()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    state_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_out.write_text(_build_markdown(report), encoding="utf-8")
    state_out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"REPORT_JSON={json_out}")
    print(f"REPORT_MD={md_out}")
    print(f"STATE_JSON={state_out}")
    return 2 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

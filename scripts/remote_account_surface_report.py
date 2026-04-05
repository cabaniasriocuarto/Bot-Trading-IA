#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
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
    value = str(url or "").strip()
    if value.endswith("/"):
        return value[:-1]
    return value


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
    method: str = "GET",
    base_url: str,
    path: str,
    timeout_sec: float,
    token: str,
    body: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, int]:
    headers = {"Authorization": f"Bearer {token}"}
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
    user = str(username or "").strip()
    pwd = str(password or "").strip()
    if not user or not pwd:
        return "", "missing_local_auth", "Falta RTLAB_AUTH_TOKEN o RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD."
    try:
        response = requests.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": user, "password": pwd},
            timeout=timeout_sec,
        )
    except Exception as exc:
        return "", "login_request_error", str(exc)
    if response.status_code != 200:
        body = str(response.text or "")[:300]
        return "", f"login_http_{response.status_code}", body
    if "json" not in str(response.headers.get("content-type", "")).lower():
        return "", "login_not_json", ""
    payload = response.json()
    token = str((payload or {}).get("token") or (payload or {}).get("access_token") or "").strip()
    if not token:
        return "", "login_no_token", ""
    return token, "login_password_env", ""


def _capability_row(family_payload: dict[str, Any], environment: str) -> dict[str, Any]:
    payload = family_payload.get(environment) if isinstance(family_payload.get(environment), dict) else {}
    notes = payload.get("notes") if isinstance(payload.get("notes"), dict) else {}
    return {
        "capability_source": payload.get("capability_source"),
        "can_trade": bool(payload.get("can_trade")),
        "can_margin": bool(payload.get("can_margin")),
        "can_user_data": bool(payload.get("can_user_data")),
        "fetched_at": payload.get("fetched_at"),
        "reason": notes.get("reason"),
        "credentials_present": notes.get("credentials_present"),
        "endpoint": notes.get("endpoint"),
        "credential_envs_tried": notes.get("credential_envs_tried"),
        "notes_error": notes.get("error"),
        "status_code": notes.get("status_code"),
        "exchange_code": notes.get("exchange_code"),
        "exchange_msg": notes.get("exchange_msg"),
        "raw_exchange_code": notes.get("raw_exchange_code"),
        "raw_exchange_msg": notes.get("raw_exchange_msg"),
        "error_category": notes.get("error_category"),
    }


def _readiness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    by_stage: dict[str, Any] = {}
    payload_by_stage = payload.get("readiness_by_stage")
    if isinstance(payload_by_stage, dict):
        for stage, row in payload_by_stage.items():
            if not isinstance(row, dict):
                continue
            stage_name = str(stage or "").strip().lower()
            if not stage_name:
                continue
            by_stage[stage_name] = {
                "ready": row.get("ready"),
                "latest_result": row.get("latest_result"),
                "reason": row.get("reason"),
                "blocking_reasons": row.get("blocking_reasons"),
                "warnings": row.get("warnings"),
                "validation_run_id": row.get("validation_run_id"),
            }
    else:
        items = payload.get("stages") if isinstance(payload.get("stages"), list) else []
        for row in items:
            if not isinstance(row, dict):
                continue
            stage = str(row.get("stage") or "").strip().lower()
            if not stage:
                continue
            by_stage[stage] = {
                "ready": row.get("ready"),
                "latest_result": row.get("latest_result"),
                "reason": row.get("reason"),
                "blocking_reasons": row.get("blocking_reasons"),
                "warnings": row.get("warnings"),
                "validation_run_id": row.get("validation_run_id"),
            }
    return {
        "live_serio_ready": payload.get("live_serio_ready"),
        "stages": by_stage,
    }


def _g9_status(gates_payload: dict[str, Any]) -> dict[str, Any]:
    rows = gates_payload.get("gates") if isinstance(gates_payload.get("gates"), list) else []
    for row in rows:
        if isinstance(row, dict) and str(row.get("id") or "") == "G9_RUNTIME_ENGINE_REAL":
            return {
                "status": row.get("status"),
                "reason": row.get("reason"),
                "details": row.get("details"),
            }
    return {"status": "UNKNOWN", "reason": "missing", "details": {}}


def _market_stream_session_keys(payload: dict[str, Any]) -> set[tuple[str, str]]:
    rows = payload.get("sessions") if isinstance(payload.get("sessions"), list) else []
    keys: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        connector = str(row.get("execution_connector") or "").strip()
        environment = str(row.get("environment") or "").strip()
        if connector and environment:
            keys.add((connector, environment))
    return keys


def _prewarm_runtime(
    *,
    base_url: str,
    timeout_sec: float,
    token: str,
    warm_symbol: str,
    warm_wait_sec: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "requested": True,
        "warm_symbol": warm_symbol,
        "warm_wait_sec": warm_wait_sec,
        "market_streams_summary_before": {},
        "market_stream_starts": [],
        "registry_sync": {},
        "gates_reevaluate": {},
        "market_streams_summary_after": {},
    }
    summary_before, err_before, status_before = _request_json(
        base_url=base_url,
        path="/api/v1/execution/market-streams/summary",
        timeout_sec=timeout_sec,
        token=token,
    )
    if err_before:
        result["market_streams_summary_before"] = {"ok": False, "error": err_before, "status_code": status_before}
        active_sessions: set[tuple[str, str]] = set()
    else:
        result["market_streams_summary_before"] = {
            "ok": True,
            "status_code": status_before,
            "running_sessions": summary_before.get("running_sessions"),
            "sessions": summary_before.get("sessions"),
        }
        active_sessions = _market_stream_session_keys(summary_before)

    start_payloads = [
        {
            "execution_connector": "binance_spot",
            "environment": "live",
            "symbols": [warm_symbol],
            "transport_mode": "combined",
        },
        {
            "execution_connector": "binance_um_futures",
            "environment": "live",
            "symbols": [warm_symbol],
            "transport_mode": "combined",
        },
    ]
    for payload in start_payloads:
        key = (str(payload["execution_connector"]), str(payload["environment"]))
        if key in active_sessions:
            result["market_stream_starts"].append(
                {
                    "execution_connector": payload["execution_connector"],
                    "environment": payload["environment"],
                    "ok": True,
                    "status_code": 200,
                    "action": "already_running",
                }
            )
            continue
        start_resp, start_err, start_status = _request_json(
            method="POST",
            base_url=base_url,
            path="/api/v1/execution/market-streams/start",
            timeout_sec=timeout_sec,
            token=token,
            body=payload,
        )
        row = {
            "execution_connector": payload["execution_connector"],
            "environment": payload["environment"],
            "status_code": start_status,
            "ok": not bool(start_err),
            "action": "started" if not start_err else "failed",
        }
        if start_err:
            row["error"] = start_err
        else:
            row["payload"] = {
                "execution_connector": start_resp.get("execution_connector"),
                "environment": start_resp.get("environment"),
                "symbols": start_resp.get("symbols"),
                "transport_mode": start_resp.get("transport_mode"),
            }
        result["market_stream_starts"].append(row)

    sync_resp, sync_err, sync_status = _request_json(
        method="POST",
        base_url=base_url,
        path="/api/v1/instruments/registry/sync",
        timeout_sec=timeout_sec,
        token=token,
        body={"environment": "live"},
    )
    result["registry_sync"] = {"ok": not bool(sync_err), "status_code": sync_status}
    if sync_err:
        result["registry_sync"]["error"] = sync_err
    else:
        result["registry_sync"]["payload"] = {
            "ok": sync_resp.get("ok"),
            "results": sync_resp.get("results"),
            "latest_snapshot_ids": sync_resp.get("latest_snapshot_ids"),
        }

    gates_resp, gates_err, gates_status = _request_json(
        method="POST",
        base_url=base_url,
        path="/api/v1/gates/reevaluate",
        timeout_sec=timeout_sec,
        token=token,
    )
    result["gates_reevaluate"] = {"ok": not bool(gates_err), "status_code": gates_status}
    if gates_err:
        result["gates_reevaluate"]["error"] = gates_err
    else:
        result["gates_reevaluate"]["payload"] = {
            "overall_status": gates_resp.get("overall_status"),
            "mode": gates_resp.get("mode"),
            "g9": _g9_status(gates_resp),
        }

    if warm_wait_sec > 0:
        time.sleep(warm_wait_sec)

    summary_after, err_after, status_after = _request_json(
        base_url=base_url,
        path="/api/v1/execution/market-streams/summary",
        timeout_sec=timeout_sec,
        token=token,
    )
    if err_after:
        result["market_streams_summary_after"] = {"ok": False, "error": err_after, "status_code": status_after}
    else:
        result["market_streams_summary_after"] = {
            "ok": True,
            "status_code": status_after,
            "running_sessions": summary_after.get("running_sessions"),
            "sessions": summary_after.get("sessions"),
        }

    return result


def _build_markdown(report: dict[str, Any]) -> str:
    auth = report.get("auth") if isinstance(report.get("auth"), dict) else {}
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    endpoint_errors = report.get("endpoint_errors") if isinstance(report.get("endpoint_errors"), dict) else {}
    capabilities = summary.get("capabilities_live") if isinstance(summary.get("capabilities_live"), dict) else {}
    readiness = summary.get("readiness") if isinstance(summary.get("readiness"), dict) else {}
    live_safety = summary.get("live_safety") if isinstance(summary.get("live_safety"), dict) else {}
    gates = summary.get("gates") if isinstance(summary.get("gates"), dict) else {}

    lines = [
        "# Remote Account Surface Report",
        "",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- base_url: `{report.get('base_url')}`",
        "",
        "## Auth",
        f"- auth_source: `{auth.get('auth_source')}`",
        f"- auth_ok: `{auth.get('ok')}`",
        f"- auth_error: `{auth.get('error') or ''}`",
        "",
        "## Endpoint status",
        f"- account_capabilities_summary_ok: `{summary.get('account_capabilities_summary_ok')}`",
        f"- validation_readiness_ok: `{summary.get('validation_readiness_ok')}`",
        f"- live_safety_ok: `{summary.get('live_safety_ok')}`",
        f"- gates_ok: `{summary.get('gates_ok')}`",
        "",
        "## Live capabilities",
    ]
    if capabilities:
        for family in ("spot", "margin", "usdm_futures", "coinm_futures"):
            row = capabilities.get(family) if isinstance(capabilities.get(family), dict) else {}
            lines.append(
                f"- {family}: source=`{row.get('capability_source')}`, "
                f"trade=`{row.get('can_trade')}`, margin=`{row.get('can_margin')}`, "
                f"user_data=`{row.get('can_user_data')}`, reason=`{row.get('reason') or ''}`, "
                f"credentials_present=`{row.get('credentials_present')}`, "
                f"status=`{row.get('status_code')}`, "
                f"exchange_code=`{row.get('exchange_code')}`, "
                f"exchange_msg=`{row.get('exchange_msg') or ''}`, "
                f"raw_exchange_code=`{row.get('raw_exchange_code')}`, "
                f"raw_exchange_msg=`{row.get('raw_exchange_msg') or ''}`, "
                f"error_category=`{row.get('error_category') or ''}`, "
                f"error=`{row.get('notes_error') or ''}`"
            )
    else:
        lines.append("- unavailable")

    prewarm = report.get("prewarm") if isinstance(report.get("prewarm"), dict) else {}
    lines.extend(
        [
            "",
            "## Prewarm",
            f"- requested: `{prewarm.get('requested')}`",
            f"- warm_symbol: `{prewarm.get('warm_symbol') or ''}`",
            f"- warm_wait_sec: `{prewarm.get('warm_wait_sec')}`",
        ]
    )
    starts = prewarm.get("market_stream_starts") if isinstance(prewarm.get("market_stream_starts"), list) else []
    if starts:
        for row in starts:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- stream `{row.get('execution_connector')}`/{row.get('environment')}: "
                f"action=`{row.get('action')}`, ok=`{row.get('ok')}`, status=`{row.get('status_code')}`, "
                f"error=`{row.get('error') or ''}`"
            )
    else:
        lines.append("- stream starts: none")
    registry_sync = prewarm.get("registry_sync") if isinstance(prewarm.get("registry_sync"), dict) else {}
    lines.append(
        f"- registry_sync: ok=`{registry_sync.get('ok')}`, status=`{registry_sync.get('status_code')}`, error=`{registry_sync.get('error') or ''}`"
    )
    gates_reevaluate = prewarm.get("gates_reevaluate") if isinstance(prewarm.get("gates_reevaluate"), dict) else {}
    lines.append(
        f"- gates_reevaluate: ok=`{gates_reevaluate.get('ok')}`, status=`{gates_reevaluate.get('status_code')}`, error=`{gates_reevaluate.get('error') or ''}`"
    )

    lines.extend(
        [
            "",
            "## Readiness",
            f"- live_serio_ready: `{readiness.get('live_serio_ready')}`",
        ]
    )
    stages = readiness.get("stages") if isinstance(readiness.get("stages"), dict) else {}
    for stage_name in ("paper", "testnet", "canary", "live_serio"):
        row = stages.get(stage_name) if isinstance(stages.get(stage_name), dict) else {}
        lines.append(
            f"- {stage_name}: ready=`{row.get('ready')}`, latest_result=`{row.get('latest_result')}`, reason=`{row.get('reason') or ''}`"
        )

    lines.extend(
        [
            "",
            "## Live safety",
            f"- overall_status: `{live_safety.get('overall_status')}`",
            f"- margin_guard_status: `{live_safety.get('margin_guard_status')}`",
            f"- margin_guard_level: `{((live_safety.get('margin_guard') or {}) if isinstance(live_safety.get('margin_guard'), dict) else {}).get('level')}`",
            f"- margin_guard_visible: `{((live_safety.get('margin_guard') or {}) if isinstance(live_safety.get('margin_guard'), dict) else {}).get('visible')}`",
            f"- safety_blockers: `{json.dumps(live_safety.get('safety_blockers') or [], ensure_ascii=False)}`",
            "",
            "## Gates",
            f"- overall_status: `{gates.get('overall_status')}`",
            f"- mode: `{gates.get('mode')}`",
            f"- g9_status: `{((gates.get('g9') or {}) if isinstance(gates.get('g9'), dict) else {}).get('status')}`",
            f"- g9_reason: `{((gates.get('g9') or {}) if isinstance(gates.get('g9'), dict) else {}).get('reason') or ''}`",
            "",
            "## Endpoint errors",
        ]
    )
    if endpoint_errors:
        for key, value in endpoint_errors.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recaptura endpoints de signed account surface / margin visibility.")
    parser.add_argument("--base-url", default="https://bot-trading-ia-staging.up.railway.app")
    parser.add_argument("--username", default=os.getenv("RTLAB_USERNAME", "Wadmin"))
    parser.add_argument("--timeout-sec", type=float, default=20.0)
    parser.add_argument("--auth-token", default=os.getenv("RTLAB_AUTH_TOKEN", ""))
    parser.add_argument(
        "--password",
        default="",
        help=(
            "DEPRECATED (inseguro): password por CLI. "
            "Usa RTLAB_ADMIN_PASSWORD/RTLAB_PASSWORD; para habilitar CLI setea ALLOW_INSECURE_PASSWORD_CLI=1."
        ),
    )
    parser.add_argument(
        "--report-prefix",
        default="artifacts/remote_account_surface",
        help="Output prefix without extension. Script writes <prefix>_<ts>.json/.md",
    )
    parser.add_argument(
        "--warm-runtime",
        action="store_true",
        help="Antes de recapturar, inicia streams live, hace registry sync live y reevaluate.",
    )
    parser.add_argument("--warm-symbol", default="BTCUSDT")
    parser.add_argument("--warm-wait-sec", type=float, default=6.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    base_url = _normalize_base_url(args.base_url)
    timeout_sec = max(1.0, float(args.timeout_sec))
    stamp = _ts_compact()
    prefix = Path(str(args.report_prefix or "artifacts/remote_account_surface")).as_posix()
    json_out = REPO_ROOT / f"{prefix}_{stamp}.json"
    md_out = REPO_ROOT / f"{prefix}_{stamp}.md"
    json_out.parent.mkdir(parents=True, exist_ok=True)

    password = _resolve_password(cli_password=str(args.password or ""))
    token, auth_source, auth_error = _resolve_token(
        base_url=base_url,
        timeout_sec=timeout_sec,
        username=str(args.username or ""),
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
        "endpoint_errors": {},
        "summary": {
            "account_capabilities_summary_ok": False,
            "validation_readiness_ok": False,
            "live_safety_ok": False,
            "gates_ok": False,
            "capabilities_live": {},
            "readiness": {},
            "live_safety": {},
            "gates": {},
        },
    }

    if token:
        report["prewarm"] = {"requested": bool(args.warm_runtime)}
        if args.warm_runtime:
            report["prewarm"] = _prewarm_runtime(
                base_url=base_url,
                timeout_sec=timeout_sec,
                token=token,
                warm_symbol=str(args.warm_symbol or "BTCUSDT").strip().upper() or "BTCUSDT",
                warm_wait_sec=max(0.0, float(args.warm_wait_sec)),
            )
        capabilities, err_cap, _ = _request_json(
            base_url=base_url,
            path="/api/v1/account/capabilities/summary",
            timeout_sec=timeout_sec,
            token=token,
        )
        readiness, err_readiness, _ = _request_json(
            base_url=base_url,
            path="/api/v1/validation/readiness",
            timeout_sec=timeout_sec,
            token=token,
        )
        live_safety, err_live_safety, _ = _request_json(
            base_url=base_url,
            path="/api/v1/execution/live-safety/summary",
            timeout_sec=timeout_sec,
            token=token,
        )
        gates, err_gates, _ = _request_json(
            base_url=base_url,
            path="/api/v1/gates",
            timeout_sec=timeout_sec,
            token=token,
        )

        if err_cap:
            report["endpoint_errors"]["account_capabilities_summary"] = err_cap
        else:
            families = capabilities.get("families") if isinstance(capabilities.get("families"), dict) else {}
            report["summary"]["account_capabilities_summary_ok"] = True
            report["summary"]["capabilities_live"] = {
                family: _capability_row(family_payload, "live")
                for family, family_payload in families.items()
                if isinstance(family_payload, dict)
            }
        if err_readiness:
            report["endpoint_errors"]["validation_readiness"] = err_readiness
        else:
            report["summary"]["validation_readiness_ok"] = True
            report["summary"]["readiness"] = _readiness_summary(readiness)
        if err_live_safety:
            report["endpoint_errors"]["execution_live_safety_summary"] = err_live_safety
        else:
            report["summary"]["live_safety_ok"] = True
            report["summary"]["live_safety"] = {
                "overall_status": live_safety.get("overall_status"),
                "margin_guard_status": live_safety.get("margin_guard_status"),
                "margin_guard": live_safety.get("margin_guard"),
                "safety_blockers": live_safety.get("safety_blockers"),
                "snapshot_fresh": live_safety.get("snapshot_fresh"),
                "exchange_filters_fresh": live_safety.get("exchange_filters_fresh"),
                "live_parity_base_ready": live_safety.get("live_parity_base_ready"),
                "market_data_guard": live_safety.get("market_data_guard"),
                "market_stream_runtime": live_safety.get("market_stream_runtime"),
                "exchange_filters_details": live_safety.get("exchange_filters_details"),
            }
        if err_gates:
            report["endpoint_errors"]["gates"] = err_gates
        else:
            report["summary"]["gates_ok"] = True
            report["summary"]["gates"] = {
                "overall_status": gates.get("overall_status"),
                "mode": gates.get("mode"),
                "g9": _g9_status(gates),
            }

    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_build_markdown(report), encoding="utf-8")

    print(json.dumps({"json": str(json_out), "md": str(md_out), "auth_ok": bool(token)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

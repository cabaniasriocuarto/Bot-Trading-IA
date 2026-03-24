from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


CANARY_PHASES = {
    "DRAFT",
    "READY",
    "ARMED",
    "RUNNING",
    "HOLD",
    "PASSED",
    "FAILED",
    "ROLLBACK_RECOMMENDED",
    "ROLLED_BACK",
    "ABORTED",
}

CANARY_TERMINAL_PHASES = {"PASSED", "FAILED", "ROLLED_BACK", "ABORTED"}

CANARY_SCOPE_TYPES = {"GLOBAL", "BOT", "SYMBOL", "BOT_SYMBOL"}

CANARY_EVENT_TYPES = {
    "CREATED",
    "STARTED",
    "EVALUATED",
    "PHASE_CHANGED",
    "HELD",
    "RESUMED",
    "ABORTED",
    "FAILED",
    "ROLLBACK_RECOMMENDED",
    "ROLLBACK_REQUESTED",
    "ROLLED_BACK",
}

CANARY_BLOCKING_SOURCES = {
    "PREFLIGHT",
    "RECONCILIATION",
    "SAFETY",
    "HEALTH",
    "ALERTS",
    "EVIDENCE",
}

DEFAULT_CANARY_SOURCE_PRECEDENCE = ("SAFETY", "HEALTH", "RECONCILIATION", "PREFLIGHT", "ALERTS", "EVIDENCE")


def _normalize_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def normalize_canary_phase(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in CANARY_PHASES else "DRAFT"


def normalize_canary_scope_type(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in CANARY_SCOPE_TYPES else "GLOBAL"


def normalize_canary_event_type(value: Any) -> str:
    normalized = _normalize_upper(value).replace("-", "_").replace(" ", "_")
    return normalized if normalized in CANARY_EVENT_TYPES else "EVALUATED"


def normalize_canary_blocking_source(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in CANARY_BLOCKING_SOURCES else "EVIDENCE"


def canary_scope_key(scope_type: Any, bot_id: Any = None, symbol: Any = None) -> str:
    scope_type_n = normalize_canary_scope_type(scope_type)
    bot_id_n = str(bot_id or "").strip()
    symbol_n = str(symbol or "").strip().upper()
    if scope_type_n == "GLOBAL":
        return "GLOBAL"
    if scope_type_n == "BOT":
        return f"BOT:{bot_id_n}"
    if scope_type_n == "SYMBOL":
        return f"SYMBOL:{symbol_n}"
    return f"BOT_SYMBOL:{bot_id_n}:{symbol_n}"


def canary_phase_is_terminal(value: Any) -> bool:
    return normalize_canary_phase(value) in CANARY_TERMINAL_PHASES


def build_canary_gate_reason(
    *,
    reason_code: str,
    source: str,
    blocking_bool: bool = True,
    advisory_bool: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "reason_code": str(reason_code or "").strip().upper() or "UNKNOWN",
        "source": normalize_canary_blocking_source(source),
        "blocking_bool": bool(blocking_bool),
        "advisory_bool": bool(advisory_bool),
        "details": details if isinstance(details, dict) else {},
    }


def sort_canary_gate_reasons(
    reasons: list[dict[str, Any]],
    *,
    source_precedence: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    precedence = list(source_precedence or DEFAULT_CANARY_SOURCE_PRECEDENCE)
    normalized_precedence = [normalize_canary_blocking_source(value) for value in precedence]

    def _source_rank(value: Any) -> int:
        source = normalize_canary_blocking_source(value)
        try:
            return normalized_precedence.index(source)
        except ValueError:
            return len(normalized_precedence)

    return sorted(
        [dict(row) for row in reasons if isinstance(row, dict)],
        key=lambda row: (
            0 if bool(row.get("blocking_bool", False)) else 1,
            _source_rank(row.get("source")),
            str(row.get("reason_code") or ""),
        ),
    )


def _normalize_alert_state(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in {"OPEN", "ACKED", "SUPPRESSED", "COOLDOWN", "RESOLVED", "EXPIRED"} else "OPEN"


def _normalize_alert_severity(value: Any) -> str:
    normalized = _normalize_upper(value)
    return normalized if normalized in {"INFO", "WARN", "CRITICAL"} else "WARN"


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _signal_item(raw_signals: dict[str, Any], snapshot_type: str) -> dict[str, Any]:
    for row in raw_signals.get("items") if isinstance(raw_signals.get("items"), list) else []:
        if isinstance(row, dict) and str(row.get("snapshot_type") or "").upper() == str(snapshot_type).upper():
            return row
    return {}


def _health_scope(summary: dict[str, Any], *, scope_type: str, bot_id: str | None = None, symbol: str | None = None) -> dict[str, Any]:
    if normalize_canary_scope_type(scope_type) == "GLOBAL":
        return dict(summary or {})
    for row in summary.get("scope_status") if isinstance(summary.get("scope_status"), list) else []:
        if not isinstance(row, dict):
            continue
        if str(row.get("scope_type") or "").upper() != normalize_canary_scope_type(scope_type):
            continue
        if str(row.get("bot_id") or "").strip() != str(bot_id or "").strip():
            continue
        if str(row.get("symbol") or "").strip().upper() != str(symbol or "").strip().upper():
            continue
        return dict(row)
    return dict(summary or {})


def build_canary_gate_evaluation(
    *,
    policy: dict[str, Any],
    scope: dict[str, Any],
    raw_signals: dict[str, Any],
    health_summary: dict[str, Any],
    safety_summary: dict[str, Any],
    open_alerts: list[dict[str, Any]],
    evaluated_at: str,
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_n = dict(run or {})
    scope_type = normalize_canary_scope_type(scope.get("scope_type"))
    bot_id = str(scope.get("bot_id") or "").strip() or None
    symbol = str(scope.get("symbol") or "").strip().upper() or None
    health_scope = _health_scope(health_summary, scope_type=scope_type, bot_id=bot_id, symbol=symbol)

    reasons: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def _add_reason(reason_code: str, source: str, *, blocking: bool, details: dict[str, Any] | None = None) -> None:
        target = reasons if blocking else warnings
        target.append(
            build_canary_gate_reason(
                reason_code=reason_code,
                source=source,
                blocking_bool=blocking,
                advisory_bool=not blocking,
                details=details,
            )
        )

    preflight_signal = _signal_item(raw_signals, "PREFLIGHT")
    preflight_payload = preflight_signal.get("payload") if isinstance(preflight_signal.get("payload"), dict) else {}
    preflight_metrics = preflight_payload.get("numeric_metrics") if isinstance(preflight_payload.get("numeric_metrics"), dict) else {}
    preflight_state_values = preflight_payload.get("state_values") if isinstance(preflight_payload.get("state_values"), dict) else {}
    preflight_status = str(preflight_state_values.get("preflight_last_status_observed") or "MISSING").strip().upper()
    preflight_age_ms = preflight_metrics.get("preflight_last_run_age_ms")
    if bool(policy.get("fail_closed_on_missing_surfaces", True)) and not preflight_signal:
        _add_reason("PREFLIGHT_SURFACE_MISSING", "EVIDENCE", blocking=True, details={"scope": scope})
    elif bool(policy.get("require_preflight_pass", True)) and preflight_status in {"FAIL", "EXPIRED", "STALE", "MISSING"}:
        _add_reason(
            f"PREFLIGHT_{preflight_status}",
            "PREFLIGHT",
            blocking=True,
            details={
                "status": preflight_status,
                "preflight_last_run_age_ms": preflight_age_ms,
                "signal_snapshot_id": preflight_signal.get("signal_snapshot_id"),
            },
        )

    reconciliation_signal = _signal_item(raw_signals, "RECONCILIATION")
    reconciliation_payload = reconciliation_signal.get("payload") if isinstance(reconciliation_signal.get("payload"), dict) else {}
    reconciliation_metrics = (
        reconciliation_payload.get("numeric_metrics") if isinstance(reconciliation_payload.get("numeric_metrics"), dict) else {}
    )
    reconciliation_state_values = (
        reconciliation_payload.get("state_values") if isinstance(reconciliation_payload.get("state_values"), dict) else {}
    )
    reconciliation_age_ms = reconciliation_metrics.get("reconciliation_last_run_age_ms")
    reconciliation_desync_count = int(reconciliation_metrics.get("reconciliation_desync_count") or 0)
    reconciliation_manual_review_count = int(reconciliation_metrics.get("reconciliation_manual_review_count") or 0)
    reconciliation_source_ok = bool(reconciliation_state_values.get("reconciliation_source_ok", False))
    if bool(policy.get("fail_closed_on_missing_surfaces", True)) and not reconciliation_signal:
        _add_reason("RECONCILIATION_SURFACE_MISSING", "EVIDENCE", blocking=True, details={"scope": scope})
    elif bool(policy.get("require_reconciliation_clean", True)):
        if reconciliation_desync_count > 0:
            _add_reason(
                "RECONCILIATION_DESYNC",
                "RECONCILIATION",
                blocking=True,
                details={"desync_count": reconciliation_desync_count, "signal_snapshot_id": reconciliation_signal.get("signal_snapshot_id")},
            )
        if reconciliation_manual_review_count > 0:
            _add_reason(
                "RECONCILIATION_MANUAL_REVIEW",
                "RECONCILIATION",
                blocking=True,
                details={
                    "manual_review_count": reconciliation_manual_review_count,
                    "signal_snapshot_id": reconciliation_signal.get("signal_snapshot_id"),
                },
            )
        if not reconciliation_source_ok or reconciliation_age_ms is None:
            _add_reason(
                "RECONCILIATION_FRESHNESS_UNKNOWN",
                "RECONCILIATION",
                blocking=True,
                details={
                    "reconciliation_source_ok": reconciliation_source_ok,
                    "reconciliation_last_run_age_ms": reconciliation_age_ms,
                    "signal_snapshot_id": reconciliation_signal.get("signal_snapshot_id"),
                },
            )

    safety_breakers = [
        row
        for row in (safety_summary.get("breakers") if isinstance(safety_summary.get("breakers"), list) else [])
        if isinstance(row, dict)
    ]
    active_safety_breakers = [
        row for row in safety_breakers if str(row.get("state") or "").strip().upper() != "CLOSED"
    ]
    live_blocking_breakers = [
        row
        for row in active_safety_breakers
        if bool(row.get("blocking_bool", False)) or str(row.get("state") or "").strip().upper() in {"OPEN", "MANUAL_LOCK"}
    ]
    if bool(policy.get("require_operational_safety_clear", True)) and (
        bool(safety_summary.get("blocking_bool", False)) or bool(live_blocking_breakers)
    ):
        _add_reason(
            "OPERATIONAL_SAFETY_BLOCKED",
            "SAFETY",
            blocking=True,
            details={
                "blocking_bool": bool(safety_summary.get("blocking_bool", False)),
                "breaker_codes": [str(row.get("breaker_code") or "") for row in live_blocking_breakers],
                "evaluated_at": str(safety_summary.get("evaluated_at") or ""),
            },
        )

    health_state = str(health_scope.get("state") or health_summary.get("state") or "BLOCKED").strip().upper()
    health_score = int(health_scope.get("score") if health_scope.get("score") is not None else (health_summary.get("score") or 0))
    health_blocking = bool(health_scope.get("blocking_bool", health_summary.get("blocking_bool", False)))
    if bool(policy.get("require_health_non_blocking", True)) and (
        health_blocking or health_state in {"BLOCKED", "MANUAL_REVIEW_REQUIRED"}
    ):
        _add_reason(
            f"HEALTH_{health_state}",
            "HEALTH",
            blocking=True,
            details={
                "state": health_state,
                "score": health_score,
                "top_priority_reason_code": str(health_scope.get("top_priority_reason_code") or health_summary.get("top_priority_reason_code") or ""),
                "snapshot_id": str(health_summary.get("snapshot_id") or ""),
            },
        )
    elif health_state not in set(policy.get("allow_health_states") or []):
        _add_reason(
            "HEALTH_STATE_NOT_ALLOWED",
            "HEALTH",
            blocking=True,
            details={"state": health_state, "allowed_states": policy.get("allow_health_states")},
        )
    elif health_score < int(policy.get("min_health_score_ready", 70)):
        _add_reason(
            "HEALTH_SCORE_BELOW_READY_THRESHOLD",
            "HEALTH",
            blocking=True,
            details={
                "score": health_score,
                "threshold": int(policy.get("min_health_score_ready", 70)),
                "snapshot_id": str(health_summary.get("snapshot_id") or ""),
            },
        )
    elif health_state == "DEGRADED":
        _add_reason(
            "HEALTH_DEGRADED_ALLOWED",
            "HEALTH",
            blocking=False,
            details={"state": health_state, "score": health_score},
        )

    critical_blocking_states = {
        _normalize_alert_state(value)
        for value in (
            policy.get("critical_alert_blocking_states")
            if isinstance(policy.get("critical_alert_blocking_states"), list)
            else []
        )
    }
    count_suppressed = bool(policy.get("count_suppressed_critical_alerts_as_blocking", False))
    critical_alerts: list[dict[str, Any]] = []
    warn_alerts: list[dict[str, Any]] = []
    for row in open_alerts if isinstance(open_alerts, list) else []:
        if not isinstance(row, dict):
            continue
        state_value = _normalize_alert_state(row.get("state"))
        severity = _normalize_alert_severity(row.get("severity"))
        if severity == "CRITICAL" and (state_value in critical_blocking_states or (count_suppressed and state_value == "SUPPRESSED")):
            critical_alerts.append(row)
        elif severity == "WARN":
            warn_alerts.append(row)
    if len(critical_alerts) > int(policy.get("max_blocking_critical_alerts", 0)):
        _add_reason(
            "CRITICAL_ALERTS_OPEN",
            "ALERTS",
            blocking=True,
            details={
                "count": len(critical_alerts),
                "allowed": int(policy.get("max_blocking_critical_alerts", 0)),
                "alert_ids": [str(row.get("alert_instance_id") or "") for row in critical_alerts],
                "trigger_codes": [str(row.get("trigger_code") or "") for row in critical_alerts],
            },
        )
    if warn_alerts:
        _add_reason(
            "WARN_ALERTS_OPEN",
            "ALERTS",
            blocking=False,
            details={"count": len(warn_alerts), "trigger_codes": [str(row.get("trigger_code") or "") for row in warn_alerts[:10]]},
        )

    ordered_reasons = sort_canary_gate_reasons(reasons)
    ordered_warnings = sort_canary_gate_reasons(warnings)
    blocking_sources: list[str] = []
    for row in ordered_reasons:
        if not bool(row.get("blocking_bool", False)):
            continue
        source = str(row.get("source") or "")
        if source and source not in blocking_sources:
            blocking_sources.append(source)

    phase = normalize_canary_phase(run_n.get("phase")) if run_n else ("READY" if not blocking_sources else "DRAFT")
    canary_allowed = not bool(blocking_sources)
    hold_required = not canary_allowed
    running_started_at_dt = _parse_iso(run_n.get("running_started_at"))
    stability_sec = max(0, int(((_parse_iso(evaluated_at) or datetime.now(timezone.utc)) - running_started_at_dt).total_seconds())) if isinstance(running_started_at_dt, datetime) else 0
    promotion_allowed = (
        canary_allowed
        and phase in {"RUNNING", "PASSED"}
        and health_state in set(policy.get("promotion_health_states") or [])
        and health_score >= int(policy.get("min_health_score_promotion", 90))
        and stability_sec >= int(policy.get("promotion_stability_sec", 300))
    )
    rollback_recommended = (
        bool(run_n)
        and not canary_phase_is_terminal(phase)
        and bool(policy.get("rollback_recommend_on_hard_block", True))
        and any(str(row.get("source") or "") in {"PREFLIGHT", "RECONCILIATION", "SAFETY", "HEALTH", "ALERTS"} for row in ordered_reasons)
    )

    return {
        "run_id": str(run_n.get("run_id") or "") or None,
        "scope_type": scope_type,
        "scope_key": canary_scope_key(scope_type, bot_id=bot_id, symbol=symbol),
        "bot_id": bot_id,
        "symbol": symbol,
        "phase": phase,
        "canary_allowed_bool": bool(canary_allowed),
        "hold_required_bool": bool(hold_required),
        "rollback_recommended_bool": bool(rollback_recommended),
        "promotion_allowed_bool": bool(promotion_allowed),
        "gating_reasons": ordered_reasons,
        "blocking_sources": blocking_sources,
        "advisory_warnings": ordered_warnings,
        "surface_status": {
            "preflight_status": preflight_status,
            "preflight_last_run_age_ms": preflight_age_ms,
            "reconciliation_last_run_age_ms": reconciliation_age_ms,
            "reconciliation_desync_count": reconciliation_desync_count,
            "reconciliation_manual_review_count": reconciliation_manual_review_count,
            "reconciliation_source_ok": reconciliation_source_ok,
            "safety_blocking_bool": bool(safety_summary.get("blocking_bool", False)),
            "health_state": health_state,
            "health_score": health_score,
            "health_blocking_bool": health_blocking,
            "open_critical_alerts_count": len(critical_alerts),
            "open_warn_alerts_count": len(warn_alerts),
            "stability_observed_sec": stability_sec,
            "promotion_stability_sec": int(policy.get("promotion_stability_sec", 300)),
        },
        "evaluated_at": str(evaluated_at or ""),
    }


def decide_canary_phase_transition(
    *,
    policy: dict[str, Any],
    run: dict[str, Any],
    evaluation: dict[str, Any],
    now_iso: str,
) -> tuple[str, dict[str, Any]]:
    current_phase = normalize_canary_phase(run.get("phase"))
    if canary_phase_is_terminal(current_phase):
        return current_phase, {"reason": "terminal_phase", "running_started_at": run.get("running_started_at"), "ended_at": run.get("ended_at")}

    if bool(evaluation.get("rollback_recommended_bool", False)):
        return "ROLLBACK_RECOMMENDED", {"reason": "rollback_recommended_by_policy", "running_started_at": run.get("running_started_at"), "ended_at": run.get("ended_at")}

    if bool(evaluation.get("hold_required_bool", False)) or not bool(evaluation.get("canary_allowed_bool", False)):
        return "HOLD", {"reason": "hold_required_by_gate", "running_started_at": run.get("running_started_at"), "ended_at": run.get("ended_at")}

    if current_phase == "ARMED":
        started_at = _parse_iso(run.get("started_at"))
        elapsed_sec = max(0, int(((_parse_iso(now_iso) or datetime.now(timezone.utc)) - started_at).total_seconds())) if isinstance(started_at, datetime) else 0
        if elapsed_sec >= int(policy.get("armed_to_running_min_sec", 0)):
            return "RUNNING", {"reason": "armed_promoted_to_running", "running_started_at": str(run.get("running_started_at") or now_iso), "ended_at": run.get("ended_at")}
        return "ARMED", {"reason": "awaiting_running_window", "running_started_at": run.get("running_started_at"), "ended_at": run.get("ended_at")}

    if current_phase == "HOLD":
        return "RUNNING", {"reason": "hold_resolved_resume_running", "running_started_at": str(run.get("running_started_at") or now_iso), "ended_at": run.get("ended_at")}

    if current_phase == "RUNNING" and bool(evaluation.get("promotion_allowed_bool", False)):
        return "PASSED", {"reason": "promotion_window_stable", "running_started_at": run.get("running_started_at"), "ended_at": now_iso}

    return current_phase, {"reason": "no_phase_change", "running_started_at": run.get("running_started_at"), "ended_at": run.get("ended_at")}

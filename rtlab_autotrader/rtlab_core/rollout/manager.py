from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ALLOWED_TRANSITIONS, PHASE_STATE_BY_NAME, ROLLOUT_STATES


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _json_save(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class RolloutManager:
    def __init__(self, *, user_data_dir: Path) -> None:
        self.root = (Path(user_data_dir).resolve() / "rollout").resolve()
        self.state_path = self.root / "state.json"
        self.artifacts_root = self.root / "artifacts"

    @staticmethod
    def default_rollout_config() -> dict[str, Any]:
        return {
            "enabled": True,
            "require_manual_approval_for_live": True,
            "paper_soak_days": 14,
            "testnet_soak_days": 7,
            "phases": [
                {"name": "shadow", "type": "shadow", "duration_hours": 24},
                {"name": "canary05", "type": "canary", "capital_pct": 5, "bake_hours": 24},
                {"name": "canary15", "type": "canary", "capital_pct": 15, "bake_hours": 24},
                {"name": "canary35", "type": "canary", "capital_pct": 35, "bake_hours": 24},
                {"name": "canary60", "type": "canary", "capital_pct": 60, "bake_hours": 24},
                {"name": "stable", "type": "stable", "capital_pct": 100},
            ],
            "abort_thresholds": {
                "max_dd_increment_phase_pct": 2.0,
                "slippage_p95_bps_max": 20.0,
                "api_error_rate_24h_max": 0.02,
                "breakers_24h_max": 3,
            },
            "improve_vs_baseline": {
                "min_expectancy_gain_pct": 5.0,
                "min_net_pnl_gain_pct": 3.0,
                "max_dd_worsen_pct": 2.0,
                "max_costs_increase_pct": 10.0,
            },
            "testnet_checks": {
                "fill_ratio_min": 0.30,
                "api_error_rate_24h_max": 0.02,
                "latency_p95_ms_max": 250.0,
            },
        }

    @staticmethod
    def default_blending_config() -> dict[str, Any]:
        return {"enabled": True, "mode": "consenso", "alpha": 0.5}

    def default_state(self) -> dict[str, Any]:
        return {
            "rollout_id": None,
            "state": "IDLE",
            "baseline_version": None,
            "candidate_version": None,
            "weights": {"baseline_pct": 100, "candidate_pct": 0},
            "routing": {"mode": "baseline_only", "shadow_only": False, "baseline_pct": 100, "candidate_pct": 0},
            "blending": self.default_blending_config(),
            "offline_gates": None,
            "compare_vs_baseline": None,
            "current_phase": None,
            "phase_kpis": {},
            "phase_runtime": {},
            "phase_evaluations": {},
            "live_signal_telemetry": {
                "recent": [],
                "phases": {},
                "last_decision": None,
                "updated_at": None,
            },
            "pending_live_approval": False,
            "pending_live_approval_target": None,
            "artifacts_dir": None,
            "abort_reason": None,
            "rollback_snapshot": None,
            "history": [],
            "updated_at": _utc_iso(),
        }

    def load_state(self) -> dict[str, Any]:
        state = _json_load(self.state_path, self.default_state())
        if not isinstance(state, dict):
            state = self.default_state()
        for key, value in self.default_state().items():
            state.setdefault(key, value)
        if state.get("state") not in ROLLOUT_STATES:
            state["state"] = "IDLE"
        return state

    def save_state(self, state: dict[str, Any]) -> dict[str, Any]:
        state["updated_at"] = _utc_iso()
        _json_save(self.state_path, state)
        return state

    def _append_history(self, state: dict[str, Any], event: str, payload: dict[str, Any] | None = None) -> None:
        history = state.get("history")
        if not isinstance(history, list):
            history = []
            state["history"] = history
        history.append({"ts": _utc_iso(), "event": event, "payload": payload or {}})
        state["history"] = history[-200:]

    def _transition(self, state: dict[str, Any], new_state: str, *, reason: str | None = None) -> None:
        old_state = str(state.get("state") or "IDLE")
        if new_state not in ROLLOUT_STATES:
            raise ValueError(f"Invalid rollout state: {new_state}")
        if new_state != old_state and new_state not in ALLOWED_TRANSITIONS.get(old_state, set()):
            raise ValueError(f"Invalid rollout transition {old_state} -> {new_state}")
        state["state"] = new_state
        if reason:
            state["last_transition_reason"] = reason
        self._append_history(state, "transition", {"from": old_state, "to": new_state, "reason": reason or ""})

    def _mark_phase_started(self, state: dict[str, Any], phase_key: str) -> None:
        runtime = state.get("phase_runtime")
        if not isinstance(runtime, dict):
            runtime = {}
        phase_row = runtime.get(phase_key) if isinstance(runtime.get(phase_key), dict) else {}
        phase_row.setdefault("started_at", _utc_iso())
        phase_row["last_seen_at"] = _utc_iso()
        runtime[phase_key] = phase_row
        state["phase_runtime"] = runtime

    def _mark_phase_finished(self, state: dict[str, Any], phase_key: str) -> None:
        runtime = state.get("phase_runtime")
        if not isinstance(runtime, dict):
            runtime = {}
        phase_row = runtime.get(phase_key) if isinstance(runtime.get(phase_key), dict) else {}
        phase_row["finished_at"] = _utc_iso()
        runtime[phase_key] = phase_row
        state["phase_runtime"] = runtime

    def _rollout_cfg(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        defaults = self.default_rollout_config()
        if not isinstance(settings, dict):
            return defaults
        rollout_cfg = settings.get("rollout") if isinstance(settings.get("rollout"), dict) else {}
        merged = {**defaults, **rollout_cfg}
        if isinstance(rollout_cfg.get("abort_thresholds"), dict):
            merged["abort_thresholds"] = {**defaults["abort_thresholds"], **rollout_cfg["abort_thresholds"]}
        if isinstance(rollout_cfg.get("improve_vs_baseline"), dict):
            merged["improve_vs_baseline"] = {**defaults["improve_vs_baseline"], **rollout_cfg["improve_vs_baseline"]}
        if isinstance(rollout_cfg.get("testnet_checks"), dict):
            merged["testnet_checks"] = {**defaults["testnet_checks"], **rollout_cfg["testnet_checks"]}
        if isinstance(rollout_cfg.get("phases"), list):
            merged["phases"] = rollout_cfg["phases"]
        return merged

    def _blending_cfg(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        defaults = self.default_blending_config()
        if not isinstance(settings, dict):
            return defaults
        blending_cfg = settings.get("blending") if isinstance(settings.get("blending"), dict) else {}
        return {**defaults, **blending_cfg}

    def _phase_cfg_by_name(self, settings: dict[str, Any] | None, phase_name: str) -> dict[str, Any]:
        rollout_cfg = self._rollout_cfg(settings)
        for row in rollout_cfg.get("phases", []):
            if isinstance(row, dict) and str(row.get("name")) == phase_name:
                return row
        return {}

    def _phase_name_from_state(self, state_name: str) -> str | None:
        for phase_name, phase_state in PHASE_STATE_BY_NAME.items():
            if phase_state == state_name:
                return phase_name
        return None

    def _phase_eval_key_for_state(self, state_name: str) -> str | None:
        if state_name in {"PAPER_SOAK", "TESTNET_SOAK"}:
            return state_name.lower()
        return self._phase_name_from_state(state_name)

    def _apply_live_phase_routing(self, state: dict[str, Any], *, phase_name: str, settings: dict[str, Any] | None = None) -> None:
        phase_cfg = self._phase_cfg_by_name(settings, phase_name)
        phase_type = str(phase_cfg.get("type") or ("shadow" if phase_name == "shadow" else "canary"))
        blending_cfg = self._blending_cfg(settings)
        state["blending"] = blending_cfg

        baseline_pct = 100
        candidate_pct = 0
        shadow_only = False
        real_execution_candidate_pct = 0

        if phase_type == "shadow" or phase_name == "shadow":
            shadow_only = True
        elif phase_type == "stable" or phase_name == "stable":
            baseline_pct = 0
            candidate_pct = 100
            real_execution_candidate_pct = 100
        else:
            candidate_pct = max(0, min(100, int(round(float(phase_cfg.get("capital_pct", 0) or 0)))))
            baseline_pct = max(0, 100 - candidate_pct)
            real_execution_candidate_pct = candidate_pct

        state["weights"] = {"baseline_pct": baseline_pct, "candidate_pct": candidate_pct}
        state["routing"] = {
            "phase": phase_name,
            "phase_type": phase_type,
            "mode": "shadow" if shadow_only else ("blended" if candidate_pct and baseline_pct else "candidate_only" if candidate_pct == 100 else "baseline_only"),
            "shadow_only": shadow_only,
            "baseline_pct": baseline_pct,
            "candidate_pct": candidate_pct,
            "real_execution_candidate_pct": real_execution_candidate_pct,
            "blending": blending_cfg if phase_name in {"shadow", "canary05", "canary15", "canary35", "canary60"} else None,
        }

    def _artifact_dir(self, rollout_id: str) -> Path:
        return (self.artifacts_root / rollout_id).resolve()

    def _write_artifacts(self, *, rollout_id: str, candidate_report: dict[str, Any], baseline_report: dict[str, Any]) -> dict[str, str]:
        base = self._artifact_dir(rollout_id)
        base.mkdir(parents=True, exist_ok=True)
        candidate_path = base / "candidate_report.json"
        baseline_path = base / "baseline_report.json"
        _json_save(candidate_path, candidate_report)
        _json_save(baseline_path, baseline_report)
        return {"candidate_report": str(candidate_path), "baseline_report": str(baseline_path)}

    def _version_snapshot(self, run: dict[str, Any], strategy: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "strategy_id": run.get("strategy_id"),
            "run_id": run.get("id"),
            "strategy_name": (strategy or {}).get("name"),
            "strategy_version": (strategy or {}).get("version"),
            "dataset_hash": run.get("dataset_hash"),
            "period": run.get("period"),
            "timeframe": run.get("timeframe"),
            "market": run.get("market"),
            "symbol": run.get("symbol"),
            "report_ref": {
                "metrics": run.get("metrics"),
                "costs_breakdown": run.get("costs_breakdown"),
            },
        }

    def _normalize_signal_action(self, value: Any) -> str:
        raw = str(value or "flat").strip().lower()
        mapping = {
            "buy": "long",
            "long": "long",
            "bull": "long",
            "sell": "short",
            "short": "short",
            "bear": "short",
            "flat": "flat",
            "hold": "flat",
            "none": "flat",
            "neutral": "flat",
        }
        return mapping.get(raw, "flat")

    def _signal_score_from_payload(self, payload: dict[str, Any] | None) -> float:
        row = payload if isinstance(payload, dict) else {}
        for key in ("score", "signal_score", "alpha", "value"):
            if isinstance(row.get(key), (int, float)):
                return float(row.get(key))
        action = self._normalize_signal_action(row.get("action"))
        confidence = float(row.get("confidence") or row.get("probability") or 1.0)
        confidence = max(0.0, min(1.0, confidence))
        if action == "long":
            return confidence
        if action == "short":
            return -confidence
        return 0.0

    def _action_from_score(self, score: float, deadband: float = 0.05) -> str:
        if score > deadband:
            return "long"
        if score < -deadband:
            return "short"
        return "flat"

    def _empty_live_signal_telemetry(self) -> dict[str, Any]:
        return {
            "recent": [],
            "phases": {},
            "last_decision": None,
            "updated_at": None,
        }

    def _record_live_signal_telemetry(self, state: dict[str, Any], event: dict[str, Any]) -> None:
        telemetry = state.get("live_signal_telemetry")
        if not isinstance(telemetry, dict):
            telemetry = self._empty_live_signal_telemetry()
        recent = telemetry.get("recent")
        if not isinstance(recent, list):
            recent = []
        recent.append(event)
        telemetry["recent"] = recent[-100:]

        phases = telemetry.get("phases")
        if not isinstance(phases, dict):
            phases = {}
        phase_key = str(event.get("phase") or "unknown")
        row = phases.get(phase_key) if isinstance(phases.get(phase_key), dict) else {
            "events": 0,
            "agreement_count": 0,
            "action_counts": {"baseline": {}, "candidate": {}, "blended": {}, "executed": {}},
            "last": None,
        }
        row["events"] = int(row.get("events") or 0) + 1
        if bool(event.get("agreement")):
            row["agreement_count"] = int(row.get("agreement_count") or 0) + 1
        action_counts = row.get("action_counts") if isinstance(row.get("action_counts"), dict) else {"baseline": {}, "candidate": {}, "blended": {}, "executed": {}}
        decisions = event.get("decisions") if isinstance(event.get("decisions"), dict) else {}
        for source_key in ("baseline", "candidate", "blended", "executed"):
            bucket = action_counts.get(source_key) if isinstance(action_counts.get(source_key), dict) else {}
            action = str(((decisions.get(source_key) if isinstance(decisions.get(source_key), dict) else {}) or {}).get("action") or "flat")
            bucket[action] = int(bucket.get(action) or 0) + 1
            action_counts[source_key] = bucket
        row["action_counts"] = action_counts
        row["agreement_rate"] = round((float(row.get("agreement_count") or 0) / max(1, int(row.get("events") or 1))), 4)
        row["last"] = event
        phases[phase_key] = row
        telemetry["phases"] = phases
        telemetry["last_decision"] = event
        telemetry["updated_at"] = _utc_iso()
        state["live_signal_telemetry"] = telemetry

    def route_live_signal(
        self,
        *,
        settings: dict[str, Any] | None,
        baseline_signal: dict[str, Any],
        candidate_signal: dict[str, Any],
        symbol: str | None = None,
        timeframe: str | None = None,
        record_telemetry: bool = True,
    ) -> dict[str, Any]:
        state = self.load_state()
        current_state = str(state.get("state") or "IDLE")
        if current_state not in {"LIVE_SHADOW", "LIVE_CANARY_05", "LIVE_CANARY_15", "LIVE_CANARY_35", "LIVE_CANARY_60"}:
            raise ValueError("Blending solo soportado en SHADOW/CANARY")

        phase_name = str(state.get("current_phase") or self._phase_name_from_state(current_state) or "")
        if not phase_name:
            raise ValueError("No se pudo resolver fase actual para blending")
        self._apply_live_phase_routing(state, phase_name=phase_name, settings=settings)
        routing = state.get("routing") if isinstance(state.get("routing"), dict) else {}
        blending_cfg = self._blending_cfg(settings)

        base_action = self._normalize_signal_action(baseline_signal.get("action"))
        cand_action = self._normalize_signal_action(candidate_signal.get("action"))
        base_score = self._signal_score_from_payload(baseline_signal)
        cand_score = self._signal_score_from_payload(candidate_signal)
        agreement = base_action == cand_action

        enabled = bool(blending_cfg.get("enabled", True))
        mode = str(blending_cfg.get("mode") or "consenso").strip().lower()
        if mode not in {"consenso", "ponderado"}:
            mode = "consenso"
        alpha = float(blending_cfg.get("alpha", 0.5))
        alpha = max(0.0, min(1.0, alpha))

        if not enabled:
            blended_score = cand_score
            blended_action = cand_action
            blending_reason = "Blending deshabilitado; se usa candidate."
        elif mode == "consenso":
            if agreement:
                blended_action = cand_action
                blended_score = (base_score + cand_score) / 2.0
                blending_reason = "Consenso: baseline y candidate coinciden."
            else:
                blended_action = "flat"
                blended_score = 0.0
                blending_reason = "Consenso: mismatch, no ejecutar."
        else:
            blended_score = (alpha * cand_score) + ((1.0 - alpha) * base_score)
            blended_action = self._action_from_score(blended_score)
            blending_reason = f"Ponderado alpha={round(alpha, 4)}"

        shadow_only = bool(routing.get("shadow_only"))
        executed_action = base_action if shadow_only else blended_action
        executed_score = base_score if shadow_only else blended_score
        execution_mode = "shadow_baseline_only" if shadow_only else "live_split_canary"

        event = {
            "ts": _utc_iso(),
            "phase": phase_name,
            "state": current_state,
            "symbol": symbol or "",
            "timeframe": timeframe or "",
            "agreement": agreement,
            "execution_mode": execution_mode,
            "routing": {
                "mode": routing.get("mode"),
                "shadow_only": shadow_only,
                "baseline_pct": routing.get("baseline_pct"),
                "candidate_pct": routing.get("candidate_pct"),
                "real_execution_candidate_pct": routing.get("real_execution_candidate_pct"),
            },
            "blending": {
                "enabled": enabled,
                "mode": mode,
                "alpha": alpha,
                "reason": blending_reason,
            },
            "decisions": {
                "baseline": {
                    "action": base_action,
                    "score": round(base_score, 6),
                    "raw": baseline_signal,
                },
                "candidate": {
                    "action": cand_action,
                    "score": round(cand_score, 6),
                    "raw": candidate_signal,
                },
                "blended": {
                    "action": blended_action,
                    "score": round(blended_score, 6),
                },
                "executed": {
                    "action": executed_action,
                    "score": round(executed_score, 6),
                    "shadow_only": shadow_only,
                },
            },
        }

        if record_telemetry:
            self._record_live_signal_telemetry(state, event)
            state = self.save_state(state)

        return {
            "event": event,
            "state": state,
            "telemetry": state.get("live_signal_telemetry"),
        }

    def start_offline(
        self,
        *,
        baseline_run: dict[str, Any],
        candidate_run: dict[str, Any],
        baseline_strategy: dict[str, Any] | None,
        candidate_strategy: dict[str, Any] | None,
        gates_result: dict[str, Any],
        compare_result: dict[str, Any],
        actor: str = "admin",
    ) -> dict[str, Any]:
        state = self.default_state()
        rollout_id = f"rlt_{secrets.token_hex(6)}"
        state["rollout_id"] = rollout_id
        state["blending"] = self.default_blending_config()
        state["baseline_version"] = self._version_snapshot(baseline_run, baseline_strategy)
        state["candidate_version"] = self._version_snapshot(candidate_run, candidate_strategy)
        state["weights"] = {"baseline_pct": 100, "candidate_pct": 0}
        state["offline_gates"] = gates_result
        state["compare_vs_baseline"] = compare_result
        state["artifacts"] = self._write_artifacts(rollout_id=rollout_id, candidate_report=candidate_run, baseline_report=baseline_run)
        state["artifacts_dir"] = str(self._artifact_dir(rollout_id))
        state["current_phase"] = None
        state["pending_live_approval"] = False
        self._append_history(state, "rollout_started", {"actor": actor, "rollout_id": rollout_id})
        self._transition(state, "CANDIDATE_READY", reason="Candidate selected for safe update")
        if not gates_result.get("passed"):
            state["abort_reason"] = f"Offline gates failed: {', '.join(gates_result.get('failed_ids', []))}"
            self._transition(state, "ABORTED", reason=state["abort_reason"])
            return self.save_state(state)
        if not compare_result.get("passed"):
            state["abort_reason"] = f"Compare vs baseline failed: {', '.join(compare_result.get('failed_ids', []))}"
            self._transition(state, "ABORTED", reason=state["abort_reason"])
            return self.save_state(state)
        self._transition(state, "OFFLINE_GATES_PASSED", reason="Offline gates + compare passed")
        return self.save_state(state)

    def rollback(self, *, reason: str, actor: str = "admin", auto: bool = False) -> dict[str, Any]:
        state = self.load_state()
        prev_state = str(state.get("state") or "IDLE")
        if prev_state == "IDLE":
            raise ValueError("No active rollout to rollback")
        state["weights"] = {"baseline_pct": 100, "candidate_pct": 0}
        state["rollback_snapshot"] = {
            "at": _utc_iso(),
            "reason": reason,
            "actor": actor,
            "auto": bool(auto),
            "prev_state": prev_state,
            "phase_kpis": state.get("phase_kpis", {}),
        }
        state["abort_reason"] = reason
        target = "ROLLED_BACK" if prev_state != "ABORTED" else "ROLLED_BACK"
        if target not in ALLOWED_TRANSITIONS.get(prev_state, set()):
            if prev_state == "IDLE":
                raise ValueError("No rollback from IDLE")
            state["state"] = prev_state
            self._append_history(state, "rollback_forced", state["rollback_snapshot"])
            state["state"] = "ROLLED_BACK"
        else:
            self._transition(state, "ROLLED_BACK", reason=reason)
        self._append_history(state, "rollback", state["rollback_snapshot"])
        return self.save_state(state)

    def reject(self, *, reason: str, actor: str = "admin") -> dict[str, Any]:
        state = self.load_state()
        state["abort_reason"] = reason
        current = str(state.get("state") or "IDLE")
        if "ABORTED" not in ALLOWED_TRANSITIONS.get(current, set()):
            raise ValueError(f"Cannot reject rollout from state {current}")
        self._transition(state, "ABORTED", reason=reason)
        self._append_history(state, "reject", {"actor": actor, "reason": reason})
        return self.save_state(state)

    def approve(self, *, actor: str = "admin", settings: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.load_state()
        if str(state.get("state")) != "PENDING_LIVE_APPROVAL":
            raise ValueError("Rollout is not pending live approval")
        target = str(state.get("pending_live_approval_target") or "LIVE_SHADOW")
        if target not in {"LIVE_SHADOW", "LIVE_STABLE_100"}:
            target = "LIVE_SHADOW"
        if target == "LIVE_STABLE_100":
            state["current_phase"] = "stable"
            self._mark_phase_started(state, "stable")
            self._apply_live_phase_routing(state, phase_name="stable", settings=settings)
        elif target == "LIVE_SHADOW":
            state["current_phase"] = "shadow"
            self._mark_phase_started(state, "shadow")
            self._apply_live_phase_routing(state, phase_name="shadow", settings=settings)
        self._transition(state, target, reason="Manual approval granted")
        state["pending_live_approval"] = False
        state["pending_live_approval_target"] = None
        self._append_history(state, "approve", {"actor": actor})
        return self.save_state(state)

    def advance(self, *, actor: str = "admin", note: str | None = None, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.load_state()
        current = str(state.get("state") or "IDLE")
        phase_evals = state.get("phase_evaluations") if isinstance(state.get("phase_evaluations"), dict) else {}
        if current == "PAPER_SOAK":
            paper_eval = phase_evals.get("paper_soak") if isinstance(phase_evals.get("paper_soak"), dict) else {}
            if not bool(paper_eval.get("passed")):
                raise ValueError("PAPER_SOAK no aprobado. Ejecuta evaluacion de fase y corrige condiciones antes de avanzar.")
        if current == "TESTNET_SOAK":
            testnet_eval = phase_evals.get("testnet_soak") if isinstance(phase_evals.get("testnet_soak"), dict) else {}
            if not bool(testnet_eval.get("passed")):
                raise ValueError("TESTNET_SOAK no aprobado. Ejecuta evaluacion de fase y corrige condiciones antes de avanzar.")
        if current in {"LIVE_SHADOW", "LIVE_CANARY_05", "LIVE_CANARY_15", "LIVE_CANARY_35", "LIVE_CANARY_60"}:
            phase_key = self._phase_eval_key_for_state(current) or ""
            live_eval = phase_evals.get(phase_key) if isinstance(phase_evals.get(phase_key), dict) else {}
            if not bool(live_eval.get("passed")):
                raise ValueError(f"{current} no aprobado. Ejecuta evaluacion de fase live y corrige condiciones antes de avanzar.")
        next_map = {
            "OFFLINE_GATES_PASSED": "PAPER_SOAK",
            "PAPER_SOAK": "TESTNET_SOAK",
            "TESTNET_SOAK": "PENDING_LIVE_APPROVAL",
            "LIVE_SHADOW": "LIVE_CANARY_05",
            "LIVE_CANARY_05": "LIVE_CANARY_15",
            "LIVE_CANARY_15": "LIVE_CANARY_35",
            "LIVE_CANARY_35": "LIVE_CANARY_60",
            "LIVE_CANARY_60": "PENDING_LIVE_APPROVAL",
            "LIVE_STABLE_100": "COMPLETED",
        }
        if current not in next_map:
            raise ValueError(f"No automatic advance defined for {current}")
        next_state = next_map[current]
        if next_state == "PENDING_LIVE_APPROVAL":
            state["pending_live_approval"] = True
            state["pending_live_approval_target"] = "LIVE_STABLE_100" if current == "LIVE_CANARY_60" else "LIVE_SHADOW"
        if next_state.startswith("LIVE_"):
            for phase_name, phase_state in PHASE_STATE_BY_NAME.items():
                if phase_state == next_state:
                    state["current_phase"] = phase_name
                    self._mark_phase_started(state, phase_name)
                    self._apply_live_phase_routing(state, phase_name=phase_name, settings=settings)
        if current == "PAPER_SOAK":
            self._mark_phase_finished(state, "paper_soak")
        if current == "TESTNET_SOAK":
            self._mark_phase_finished(state, "testnet_soak")
        current_live_phase = self._phase_name_from_state(current)
        if current_live_phase:
            self._mark_phase_finished(state, current_live_phase)
        if next_state == "PAPER_SOAK":
            state["current_phase"] = "paper_soak"
            self._mark_phase_started(state, "paper_soak")
        if next_state == "TESTNET_SOAK":
            state["current_phase"] = "testnet_soak"
            self._mark_phase_started(state, "testnet_soak")
        self._transition(state, next_state, reason=note or f"Advance by {actor}")
        self._append_history(state, "advance", {"actor": actor, "from": current, "to": next_state, "note": note or ""})
        return self.save_state(state)

    def evaluate_paper_soak(
        self,
        *,
        settings: dict[str, Any],
        status_payload: dict[str, Any],
        execution_payload: dict[str, Any],
        logs: list[dict[str, Any]],
        auto_abort: bool = True,
    ) -> dict[str, Any]:
        state = self.load_state()
        if str(state.get("state")) != "PAPER_SOAK":
            raise ValueError("Rollout no esta en PAPER_SOAK")

        rollout_cfg = settings.get("rollout") if isinstance(settings.get("rollout"), dict) else {}
        learning_cfg = settings.get("learning") if isinstance(settings.get("learning"), dict) else {}
        paper_days_required = float(rollout_cfg.get("paper_soak_days", 14))
        risk_profile = learning_cfg.get("risk_profile") if isinstance(learning_cfg.get("risk_profile"), dict) else {}
        paper_risk = risk_profile.get("paper") if isinstance(risk_profile.get("paper"), dict) else {}
        max_daily_loss_allowed_pct = abs(float(paper_risk.get("max_daily_loss_pct", 3.0)))
        max_dd_allowed_pct = abs(float(paper_risk.get("max_drawdown_pct", 15.0)))
        slippage_limit_bps = float((settings.get("execution") or {}).get("slippage_max_bps", 12))

        runtime = state.get("phase_runtime") if isinstance(state.get("phase_runtime"), dict) else {}
        paper_runtime = runtime.get("paper_soak") if isinstance(runtime.get("paper_soak"), dict) else {}
        started_at_raw = paper_runtime.get("started_at")
        started_at = datetime.fromisoformat(str(started_at_raw)) if started_at_raw else datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        elapsed_days = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds() / 86400.0)

        daily_loss_pct = abs(float((status_payload.get("daily_loss") or {}).get("value", 0.0)) * 100.0)
        max_dd_pct = abs(float((status_payload.get("max_dd") or {}).get("value", 0.0)) * 100.0)
        slippage_p95 = float(execution_payload.get("p95_slippage") or 0.0)
        critical_error_logs = [
            row for row in logs
            if str(row.get("severity", "")).lower() == "error" and str(row.get("module", "")).lower() in {"execution", "data", "exchange"}
        ]
        data_gap_logs = [
            row for row in logs
            if "data gap" in str(row.get("message", "")).lower() or str(row.get("type", "")).lower() in {"data_gap"}
        ]

        checks = [
            {
                "id": "paper_duration_min_days",
                "ok": elapsed_days >= paper_days_required,
                "reason": "Duracion minima de paper soak",
                "details": {"elapsed_days": round(elapsed_days, 4), "required_days": paper_days_required},
            },
            {
                "id": "paper_max_daily_loss",
                "ok": daily_loss_pct <= max_daily_loss_allowed_pct,
                "reason": "No rompe max_daily_loss del perfil medio",
                "details": {"daily_loss_pct": round(daily_loss_pct, 4), "allowed_pct": max_daily_loss_allowed_pct},
            },
            {
                "id": "paper_max_drawdown",
                "ok": max_dd_pct <= max_dd_allowed_pct,
                "reason": "No rompe max_dd del perfil medio",
                "details": {"max_dd_pct": round(max_dd_pct, 4), "allowed_pct": max_dd_allowed_pct},
            },
            {
                "id": "paper_no_critical_execution_errors",
                "ok": len(critical_error_logs) == 0,
                "reason": "Sin errores criticos de ejecucion/data",
                "details": {"critical_errors": len(critical_error_logs), "data_gap_logs": len(data_gap_logs)},
            },
            {
                "id": "paper_slippage_limit",
                "ok": slippage_p95 <= slippage_limit_bps,
                "reason": "Slippage estimado dentro de limites",
                "details": {"slippage_p95_bps": round(slippage_p95, 4), "allowed_bps": slippage_limit_bps},
            },
        ]

        hard_fail_ids = [
            row["id"] for row in checks
            if (not row["ok"]) and row["id"] != "paper_duration_min_days"
        ]
        passed = all(row["ok"] for row in checks)
        ready_to_promote = passed
        status = "PASS" if passed else ("FAIL" if hard_fail_ids else "PENDING_MIN_DURATION")

        evaluation = {
            "phase": "paper_soak",
            "status": status,
            "passed": passed,
            "ready_to_promote": ready_to_promote,
            "hard_fail": bool(hard_fail_ids),
            "failed_ids": [row["id"] for row in checks if not row["ok"]],
            "hard_fail_ids": hard_fail_ids,
            "checks": checks,
            "kpis": {
                "daily_loss_pct": round(daily_loss_pct, 4),
                "max_dd_pct": round(max_dd_pct, 4),
                "slippage_p95_bps": round(slippage_p95, 4),
                "critical_errors": len(critical_error_logs),
                "data_gap_logs": len(data_gap_logs),
                "elapsed_days": round(elapsed_days, 4),
            },
            "evaluated_at": _utc_iso(),
        }
        phase_evals = state.get("phase_evaluations") if isinstance(state.get("phase_evaluations"), dict) else {}
        phase_evals["paper_soak"] = evaluation
        state["phase_evaluations"] = phase_evals
        phase_kpis = state.get("phase_kpis") if isinstance(state.get("phase_kpis"), dict) else {}
        phase_kpis["paper_soak"] = evaluation["kpis"]
        state["phase_kpis"] = phase_kpis
        self._mark_phase_started(state, "paper_soak")
        self._append_history(state, "paper_soak_evaluated", {"status": status, "failed_ids": evaluation["failed_ids"]})

        if auto_abort and hard_fail_ids:
            state["abort_reason"] = f"PAPER_SOAK failed: {', '.join(hard_fail_ids)}"
            self._transition(state, "ABORTED", reason=state["abort_reason"])
        return self.save_state(state)

    def evaluate_testnet_soak(
        self,
        *,
        settings: dict[str, Any],
        execution_payload: dict[str, Any],
        diagnose_payload: dict[str, Any],
        logs: list[dict[str, Any]],
        auto_abort: bool = True,
    ) -> dict[str, Any]:
        state = self.load_state()
        if str(state.get("state")) != "TESTNET_SOAK":
            raise ValueError("Rollout no esta en TESTNET_SOAK")

        rollout_cfg = settings.get("rollout") if isinstance(settings.get("rollout"), dict) else {}
        testnet_days_required = float(rollout_cfg.get("testnet_soak_days", 7))
        testnet_checks_cfg = rollout_cfg.get("testnet_checks") if isinstance(rollout_cfg.get("testnet_checks"), dict) else {}
        fill_ratio_min = float(testnet_checks_cfg.get("fill_ratio_min", 0.30))
        api_error_rate_max = float(testnet_checks_cfg.get("api_error_rate_24h_max", 0.02))
        latency_p95_ms_max = float(testnet_checks_cfg.get("latency_p95_ms_max", 250.0))

        runtime = state.get("phase_runtime") if isinstance(state.get("phase_runtime"), dict) else {}
        phase_runtime = runtime.get("testnet_soak") if isinstance(runtime.get("testnet_soak"), dict) else {}
        started_at_raw = phase_runtime.get("started_at")
        started_at = datetime.fromisoformat(str(started_at_raw)) if started_at_raw else datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        elapsed_days = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds() / 86400.0)

        fill_ratio = float(execution_payload.get("fill_ratio") or 0.0)
        latency_p95 = float(execution_payload.get("latency_ms_p95") or 0.0)
        api_errors_metric = int(execution_payload.get("api_errors") or 0)
        req_estimate = int(execution_payload.get("requests_24h_estimate") or max(100, len(execution_payload.get("series") or []) * 25))
        log_api_errors_24h = sum(
            1
            for row in logs
            if str(row.get("severity", "")).lower() == "error"
            and str(row.get("module", "")).lower() in {"execution", "exchange"}
        )
        api_error_rate_24h = max(api_errors_metric, log_api_errors_24h) / max(1, req_estimate)
        breaker_events_24h = sum(1 for row in logs if str(row.get("type", "")).lower() in {"breaker_triggered", "kill_switch", "killswitch"})

        connector_ok = bool(diagnose_payload.get("connector_ok"))
        order_ok = bool(diagnose_payload.get("order_ok"))
        checks = [
            {
                "id": "testnet_duration_min_days",
                "ok": elapsed_days >= testnet_days_required,
                "reason": "Duracion minima de testnet soak",
                "details": {"elapsed_days": round(elapsed_days, 4), "required_days": testnet_days_required},
            },
            {
                "id": "testnet_place_cancel_ok",
                "ok": connector_ok and order_ok,
                "reason": "Place/cancel OK en testnet",
                "details": {
                    "connector_ok": connector_ok,
                    "order_ok": order_ok,
                    "connector_reason": diagnose_payload.get("connector_reason"),
                    "order_reason": diagnose_payload.get("order_reason"),
                },
            },
            {
                "id": "testnet_fill_ratio_min",
                "ok": fill_ratio >= fill_ratio_min,
                "reason": "Fill ratio minimo",
                "details": {"fill_ratio": round(fill_ratio, 4), "min": fill_ratio_min},
            },
            {
                "id": "testnet_api_error_rate_24h",
                "ok": api_error_rate_24h <= api_error_rate_max,
                "reason": "API error rate rolling 24h",
                "details": {"api_error_rate_24h": round(api_error_rate_24h, 6), "max": api_error_rate_max, "requests_est": req_estimate},
            },
            {
                "id": "testnet_latency_p95",
                "ok": latency_p95 <= latency_p95_ms_max,
                "reason": "Latency p95 dentro de limite",
                "details": {"latency_p95_ms": round(latency_p95, 4), "max_ms": latency_p95_ms_max},
            },
        ]

        hard_fail_ids = [row["id"] for row in checks if (not row["ok"]) and row["id"] != "testnet_duration_min_days"]
        passed = all(row["ok"] for row in checks)
        status = "PASS" if passed else ("FAIL" if hard_fail_ids else "PENDING_MIN_DURATION")

        evaluation = {
            "phase": "testnet_soak",
            "status": status,
            "passed": passed,
            "ready_to_promote": passed,
            "hard_fail": bool(hard_fail_ids),
            "failed_ids": [row["id"] for row in checks if not row["ok"]],
            "hard_fail_ids": hard_fail_ids,
            "checks": checks,
            "kpis": {
                "elapsed_days": round(elapsed_days, 4),
                "fill_ratio": round(fill_ratio, 4),
                "api_error_rate_24h": round(api_error_rate_24h, 6),
                "latency_p95_ms": round(latency_p95, 4),
                "api_errors_metric": api_errors_metric,
                "log_api_errors_24h": log_api_errors_24h,
                "breaker_events_24h": breaker_events_24h,
            },
            "diagnose": {
                "connector_ok": connector_ok,
                "order_ok": order_ok,
                "mode": diagnose_payload.get("mode"),
                "exchange": diagnose_payload.get("exchange"),
            },
            "evaluated_at": _utc_iso(),
        }

        phase_evals = state.get("phase_evaluations") if isinstance(state.get("phase_evaluations"), dict) else {}
        phase_evals["testnet_soak"] = evaluation
        state["phase_evaluations"] = phase_evals
        phase_kpis = state.get("phase_kpis") if isinstance(state.get("phase_kpis"), dict) else {}
        phase_kpis["testnet_soak"] = evaluation["kpis"]
        state["phase_kpis"] = phase_kpis
        self._mark_phase_started(state, "testnet_soak")
        self._append_history(state, "testnet_soak_evaluated", {"status": status, "failed_ids": evaluation["failed_ids"]})

        if auto_abort and hard_fail_ids:
            state["abort_reason"] = f"TESTNET_SOAK failed: {', '.join(hard_fail_ids)}"
            self._transition(state, "ABORTED", reason=state["abort_reason"])
        return self.save_state(state)

    def evaluate_live_phase(
        self,
        *,
        settings: dict[str, Any],
        status_payload: dict[str, Any],
        execution_payload: dict[str, Any],
        logs: list[dict[str, Any]],
        baseline_live_kpis: dict[str, Any] | None = None,
        auto_rollback: bool = True,
    ) -> dict[str, Any]:
        state = self.load_state()
        current_state = str(state.get("state") or "IDLE")
        if current_state not in {"LIVE_SHADOW", "LIVE_CANARY_05", "LIVE_CANARY_15", "LIVE_CANARY_35", "LIVE_CANARY_60"}:
            raise ValueError("Rollout no esta en una fase LIVE evaluable")

        phase_name = str(state.get("current_phase") or self._phase_name_from_state(current_state) or "").strip()
        if not phase_name:
            raise ValueError("No se pudo resolver la fase live actual")

        self._apply_live_phase_routing(state, phase_name=phase_name, settings=settings)

        rollout_cfg = self._rollout_cfg(settings)
        abort_cfg = rollout_cfg.get("abort_thresholds") if isinstance(rollout_cfg.get("abort_thresholds"), dict) else {}
        dd_increment_max = float(abort_cfg.get("max_dd_increment_phase_pct", 2.0))
        slippage_p95_max = float(abort_cfg.get("slippage_p95_bps_max", 20.0))
        api_error_rate_max = float(abort_cfg.get("api_error_rate_24h_max", 0.02))
        breakers_24h_max = int(abort_cfg.get("breakers_24h_max", 3))

        runtime = state.get("phase_runtime") if isinstance(state.get("phase_runtime"), dict) else {}
        live_runtime = runtime.get(phase_name) if isinstance(runtime.get(phase_name), dict) else {}
        started_at_raw = live_runtime.get("started_at")
        started_at = datetime.fromisoformat(str(started_at_raw)) if started_at_raw else datetime.now(timezone.utc)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        elapsed_hours = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds() / 3600.0)

        phase_cfg = self._phase_cfg_by_name(settings, phase_name)
        required_hours = 0.0
        if "duration_hours" in phase_cfg:
            required_hours = float(phase_cfg.get("duration_hours") or 0.0)
        elif "bake_hours" in phase_cfg:
            required_hours = float(phase_cfg.get("bake_hours") or 0.0)

        candidate_metrics_ref = {}
        if isinstance(state.get("candidate_version"), dict):
            report_ref = state["candidate_version"].get("report_ref")
            if isinstance(report_ref, dict) and isinstance(report_ref.get("metrics"), dict):
                candidate_metrics_ref = report_ref["metrics"]
        baseline_metrics_ref = {}
        if isinstance(state.get("baseline_version"), dict):
            report_ref = state["baseline_version"].get("report_ref")
            if isinstance(report_ref, dict) and isinstance(report_ref.get("metrics"), dict):
                baseline_metrics_ref = report_ref["metrics"]

        daily_pnl = float(status_payload.get("daily_pnl") or ((status_payload.get("pnl") or {}).get("daily") or 0.0))
        expectancy_24h_usd = float(
            status_payload.get("expectancy_24h_usd")
            or status_payload.get("expectancy_usd")
            or candidate_metrics_ref.get("expectancy_usd_per_trade")
            or candidate_metrics_ref.get("expectancy")
            or daily_pnl
        )
        max_dd_total_pct = abs(float(((status_payload.get("max_dd") or {}).get("value") or 0.0)) * 100.0)
        phase_dd_increment_pct = float(status_payload.get("phase_dd_increment_pct") or status_payload.get("max_dd_increment_phase_pct") or 0.0)
        profit_factor = float(status_payload.get("profit_factor") or candidate_metrics_ref.get("profit_factor") or 0.0)
        winrate = float(status_payload.get("winrate") or candidate_metrics_ref.get("winrate") or 0.0)
        net_pnl = float(status_payload.get("net_pnl_24h") or status_payload.get("net_pnl") or daily_pnl)

        slippage_p95_bps = float(execution_payload.get("p95_slippage") or 0.0)
        spread_p95_bps = float(execution_payload.get("p95_spread") or 0.0)
        latency_p95_ms = float(execution_payload.get("latency_ms_p95") or 0.0)

        api_errors_metric = int(execution_payload.get("api_errors") or 0)
        req_estimate = int(execution_payload.get("requests_24h_estimate") or max(100, len(execution_payload.get("series") or []) * 25))
        log_api_errors_24h = sum(
            1
            for row in logs
            if str(row.get("severity", "")).lower() == "error" and str(row.get("module", "")).lower() in {"execution", "exchange"}
        )
        api_error_rate_24h = max(api_errors_metric, log_api_errors_24h) / max(1, req_estimate)
        reconnects_24h = sum(1 for row in logs if str(row.get("type", "")).lower() in {"reconnect", "ws_reconnect", "socket_reconnect"})
        breaker_events_24h = sum(1 for row in logs if str(row.get("type", "")).lower() in {"breaker_triggered", "kill_switch", "killswitch"})

        baseline_live_kpis = baseline_live_kpis if isinstance(baseline_live_kpis, dict) else {}
        baseline_expectancy_24h_usd = float(
            baseline_live_kpis.get("expectancy_24h_usd")
            or baseline_live_kpis.get("expectancy_usd")
            or baseline_metrics_ref.get("expectancy_usd_per_trade")
            or baseline_metrics_ref.get("expectancy")
            or 0.0
        )
        baseline_dd_increment_phase_pct = float(
            baseline_live_kpis.get("max_dd_increment_phase_pct")
            or baseline_live_kpis.get("max_dd_phase_pct")
            or (abs(float(baseline_metrics_ref.get("max_dd") or 0.0)) * 100.0)
        )
        baseline_slippage_p95_bps = float(
            baseline_live_kpis.get("slippage_p95_bps")
            or baseline_live_kpis.get("p95_slippage_bps")
            or slippage_p95_bps
        )

        checks = [
            {
                "id": "live_phase_duration_hours",
                "ok": elapsed_hours >= required_hours if required_hours > 0 else True,
                "reason": "Duracion minima/bake de la fase live",
                "details": {"elapsed_hours": round(elapsed_hours, 4), "required_hours": required_hours, "phase": phase_name},
            },
            {
                "id": "abort_max_dd_increment_phase_pct",
                "ok": phase_dd_increment_pct <= dd_increment_max,
                "reason": "Drawdown incremental de fase dentro de umbral",
                "details": {"value_pct": round(phase_dd_increment_pct, 4), "max_pct": dd_increment_max},
            },
            {
                "id": "abort_expectancy_vs_baseline_24h",
                "ok": not (expectancy_24h_usd < 0 and baseline_expectancy_24h_usd > 0),
                "reason": "Expectancy 24h no negativa si baseline es positiva",
                "details": {"candidate_expectancy_24h_usd": round(expectancy_24h_usd, 4), "baseline_expectancy_24h_usd": round(baseline_expectancy_24h_usd, 4)},
            },
            {
                "id": "abort_slippage_p95_bps",
                "ok": slippage_p95_bps <= slippage_p95_max,
                "reason": "Slippage p95 dentro de umbral",
                "details": {"value_bps": round(slippage_p95_bps, 4), "max_bps": slippage_p95_max},
            },
            {
                "id": "abort_api_error_rate_24h",
                "ok": api_error_rate_24h <= api_error_rate_max,
                "reason": "API error rate 24h dentro de umbral",
                "details": {"value": round(api_error_rate_24h, 6), "max": api_error_rate_max, "requests_est": req_estimate},
            },
            {
                "id": "abort_breakers_24h",
                "ok": breaker_events_24h <= breakers_24h_max,
                "reason": "Eventos breaker 24h dentro de umbral",
                "details": {"value": breaker_events_24h, "max": breakers_24h_max},
            },
            {
                "id": "promote_expectancy_not_worse_vs_baseline",
                "ok": expectancy_24h_usd >= baseline_expectancy_24h_usd,
                "reason": "Candidate no peor que baseline en expectancy",
                "details": {"candidate": round(expectancy_24h_usd, 4), "baseline": round(baseline_expectancy_24h_usd, 4)},
            },
            {
                "id": "promote_dd_not_worse_vs_baseline",
                "ok": phase_dd_increment_pct <= baseline_dd_increment_phase_pct,
                "reason": "Candidate no peor que baseline en DD incremental de fase",
                "details": {"candidate_pct": round(phase_dd_increment_pct, 4), "baseline_pct": round(baseline_dd_increment_phase_pct, 4)},
            },
            {
                "id": "promote_slippage_not_worse_vs_baseline",
                "ok": slippage_p95_bps <= baseline_slippage_p95_bps,
                "reason": "Candidate no peor que baseline en slippage p95",
                "details": {"candidate_bps": round(slippage_p95_bps, 4), "baseline_bps": round(baseline_slippage_p95_bps, 4)},
            },
        ]

        failed_ids = [row["id"] for row in checks if not row["ok"]]
        hard_fail_ids = [row["id"] for row in checks if (not row["ok"]) and row["id"].startswith("abort_")]
        passed = not failed_ids
        if passed:
            status = "PASS"
        elif failed_ids == ["live_phase_duration_hours"] or (len(failed_ids) == 1 and "live_phase_duration_hours" in failed_ids):
            status = "PENDING_MIN_DURATION"
        elif "live_phase_duration_hours" in failed_ids and len(failed_ids) > 1 and not hard_fail_ids:
            status = "NOT_READY_COMPARE"
        elif hard_fail_ids:
            status = "FAIL"
        else:
            status = "NOT_READY_COMPARE"

        evaluation = {
            "phase": phase_name,
            "state": current_state,
            "status": status,
            "passed": passed,
            "ready_to_promote": passed,
            "hard_fail": bool(hard_fail_ids),
            "failed_ids": failed_ids,
            "hard_fail_ids": hard_fail_ids,
            "checks": checks,
            "kpis": {
                "elapsed_hours": round(elapsed_hours, 4),
                "required_hours": required_hours,
                "net_pnl_24h_usd": round(net_pnl, 4),
                "expectancy_24h_usd": round(expectancy_24h_usd, 4),
                "max_dd_pct": round(max_dd_total_pct, 4),
                "max_dd_increment_phase_pct": round(phase_dd_increment_pct, 4),
                "profit_factor": round(profit_factor, 4),
                "winrate": round(winrate, 4),
                "slippage_p95_bps": round(slippage_p95_bps, 4),
                "spread_p95_bps": round(spread_p95_bps, 4),
                "api_error_rate_24h": round(api_error_rate_24h, 6),
                "reconnects_24h": reconnects_24h,
                "latency_p95_ms": round(latency_p95_ms, 4),
                "breaker_events_24h": breaker_events_24h,
                "baseline_expectancy_24h_usd": round(baseline_expectancy_24h_usd, 4),
                "baseline_max_dd_increment_phase_pct": round(baseline_dd_increment_phase_pct, 4),
                "baseline_slippage_p95_bps": round(baseline_slippage_p95_bps, 4),
            },
            "routing": state.get("routing"),
            "evaluated_at": _utc_iso(),
        }

        phase_evals = state.get("phase_evaluations") if isinstance(state.get("phase_evaluations"), dict) else {}
        phase_evals[phase_name] = evaluation
        state["phase_evaluations"] = phase_evals
        phase_kpis = state.get("phase_kpis") if isinstance(state.get("phase_kpis"), dict) else {}
        phase_kpis[phase_name] = evaluation["kpis"]
        state["phase_kpis"] = phase_kpis
        self._mark_phase_started(state, phase_name)
        self._append_history(state, "live_phase_evaluated", {"phase": phase_name, "status": status, "failed_ids": evaluation["failed_ids"]})
        saved_state = self.save_state(state)

        if auto_rollback and hard_fail_ids:
            reason = f"{current_state} abort thresholds: {', '.join(hard_fail_ids)}"
            return self.rollback(reason=reason, actor="system", auto=True)
        return saved_state

    def set_phase_started_at(self, phase_key: str, started_at_iso: str) -> dict[str, Any]:
        state = self.load_state()
        runtime = state.get("phase_runtime") if isinstance(state.get("phase_runtime"), dict) else {}
        phase_row = runtime.get(phase_key) if isinstance(runtime.get(phase_key), dict) else {}
        phase_row["started_at"] = started_at_iso
        runtime[phase_key] = phase_row
        state["phase_runtime"] = runtime
        self._append_history(state, "phase_started_at_set", {"phase": phase_key, "started_at": started_at_iso})
        return self.save_state(state)

    def status(self) -> dict[str, Any]:
        return self.load_state()

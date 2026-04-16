from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from rtlab_core.policy_paths import describe_policy_root_resolution
from rtlab_core.src.data.runtime_path import runtime_path


VALIDATION_GATES_FILENAME = "validation_gates.yaml"
POLICY_EXPECTED_FILES: tuple[str, ...] = (
    "runtime_controls.yaml",
    "instrument_registry.yaml",
    "universes.yaml",
    "cost_stack.yaml",
    "reporting_exports.yaml",
    "execution_safety.yaml",
    "execution_router.yaml",
    VALIDATION_GATES_FILENAME,
)
PARSER_VERSION = "validation_gates_v1"
VALIDATION_RESULTS = {"PASS", "BLOCK", "HOLD"}
VALIDATION_STAGES = ("PAPER", "TESTNET", "CANARY", "LIVE_SERIO")

FAIL_CLOSED_MINIMAL_VALIDATION_GATES_POLICY: dict[str, Any] = {
    "validation_gates": {
        "stages": {
            "paper": {
                "min_orders": 1000000,
                "min_trading_days": 1000000,
                "max_unresolved_reconcile_rate_pct": 0.0,
                "max_reject_rate_pct": 0.0,
                "max_cost_mismatch_rate_pct": 0.0,
                "min_fill_coverage_pct": 100.0,
                "min_cost_materialization_coverage_pct": 100.0,
                "min_cancel_success_rate_pct": 100.0,
                "max_gross_net_inconsistency_rate_pct": 0.0,
            },
            "testnet": {
                "min_orders": 1000000,
                "min_trading_days": 1000000,
                "max_unresolved_reconcile_rate_pct": 0.0,
                "max_reject_rate_pct": 0.0,
                "max_cost_mismatch_rate_pct": 0.0,
                "min_fill_coverage_pct": 100.0,
                "min_cost_materialization_coverage_pct": 100.0,
                "min_cancel_success_rate_pct": 100.0,
                "max_gross_net_inconsistency_rate_pct": 0.0,
                "require_real_user_data_stream_or_explicit_degraded_mode": True,
            },
            "canary": {
                "min_orders": 1000000,
                "min_runtime_hours": 1000000,
                "max_unresolved_reconcile_rate_pct": 0.0,
                "max_reject_rate_pct": 0.0,
                "max_cost_mismatch_rate_pct": 0.0,
                "min_fill_coverage_pct": 100.0,
                "min_cost_materialization_coverage_pct": 100.0,
                "min_cancel_success_rate_pct": 100.0,
                "max_gross_net_inconsistency_rate_pct": 0.0,
                "max_kill_switch_trips": 0,
                "max_margin_guard_blocks": 0,
            },
        },
        "blocks": {
            "block_if_kill_switch_active": True,
            "block_if_fee_source_missing_in_live_like_modes": True,
            "block_if_snapshot_stale": True,
            "block_if_policy_missing": True,
            "allow_manual_override": False,
        },
        "promotion": {
            "order": list(VALIDATION_STAGES),
            "auto_activate_live_serio": False,
            "live_like_stages": ["TESTNET", "CANARY", "LIVE_SERIO"],
        },
        "environments": {
            "paper": {
                "mode": "paper",
                "environment": "paper",
                "preconditions": [],
                "control_metrics": [],
                "exit_criteria": [],
                "blocking_causes": ["validation_policy_missing"],
                "warnings": ["PAPER validates wiring and accounting, not live market behavior"],
            },
            "testnet": {
                "mode": "testnet",
                "environment": "testnet",
                "preconditions": [],
                "control_metrics": [],
                "exit_criteria": [],
                "blocking_causes": ["unsupported family/environment"],
                "warnings": [
                    "Spot Testnet is not equivalent to live",
                    "Futures Testnet uses separate base URLs/endpoints",
                ],
            },
            "canary": {
                "mode": "live",
                "environment": "live",
                "preconditions": [],
                "control_metrics": [],
                "exit_criteria": [],
                "blocking_causes": ["live safety blocker"],
                "warnings": ["Canary uses a controlled live slice, not full live serio"],
            },
            "live_serio": {
                "mode": "live",
                "environment": "live",
                "preconditions": [],
                "control_metrics": [],
                "exit_criteria": [],
                "blocking_causes": ["not evaluated in RTLOPS-36"],
                "warnings": ["LIVE_SERIO is destination only in this block"],
            },
        },
    }
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return _utc_now().isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _json_loads(value: Any, default: Any) -> Any:
    if value in {None, ""}:
        return copy.deepcopy(default)
    try:
        return json.loads(str(value))
    except Exception:
        return copy.deepcopy(default)


def _stable_payload_hash(value: Any) -> str:
    return hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _parse_ts(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _canonical_symbol(value: Any) -> str:
    return str(value or "").replace("/", "").replace("-", "").strip().upper()


def _execution_runtime_trade_row(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    provenance = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
    source_kind = str(provenance.get("source_kind") or row.get("source_kind") or "").strip()
    return source_kind in {"execution_reality_fill", "execution_reality_runtime"}


def _normalize_family(value: Any) -> str:
    family = str(value or "").strip().lower()
    return family if family in {"spot", "margin", "usdm_futures", "coinm_futures"} else ""


def _normalize_stage(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in VALIDATION_STAGES else "PAPER"


def _normalize_result(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if text in VALIDATION_RESULTS else "HOLD"


def _percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 6)


def _validation_source_label(repo_root: Path, policy_path: Path) -> str:
    try:
        return str(policy_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(policy_path.resolve())


def _resolve_repo_root_for_policy() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "policies").exists():
            return parent
        if (parent / "rtlab_autotrader" / "config" / "policies").exists():
            return parent
    return None


def _require_dict(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        errors.append(f"{path}.{key} debe ser dict")
        return {}
    return value


def _require_bool(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> bool:
    value = parent.get(key)
    if not isinstance(value, bool):
        errors.append(f"{path}.{key} debe ser bool")
        return False
    return value


def _require_number(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> float:
    value = parent.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{path}.{key} debe ser numero")
        return 0.0
    return float(value)


def _require_string(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key} debe ser string no vacio")
        return ""
    return value.strip()


def _require_str_list(parent: dict[str, Any], key: str, *, errors: list[str], path: str) -> list[str]:
    value = parent.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{path}.{key} debe ser lista de strings no vacios")
        return []
    return [str(item).strip() for item in value]


def _validate_validation_gates_policy(candidate: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(candidate, dict):
        return ["validation_gates policy debe ser dict"]

    root = _require_dict(candidate, "validation_gates", errors=errors, path="validation")
    stages = _require_dict(root, "stages", errors=errors, path="validation.validation_gates")
    for stage in ("paper", "testnet", "canary"):
        stage_cfg = _require_dict(stages, stage, errors=errors, path="validation.validation_gates.stages")
        _require_number(stage_cfg, "min_orders", errors=errors, path=f"validation.validation_gates.stages.{stage}")
        if stage == "canary":
            _require_number(stage_cfg, "min_runtime_hours", errors=errors, path="validation.validation_gates.stages.canary")
            _require_number(stage_cfg, "max_kill_switch_trips", errors=errors, path="validation.validation_gates.stages.canary")
            _require_number(stage_cfg, "max_margin_guard_blocks", errors=errors, path="validation.validation_gates.stages.canary")
        else:
            _require_number(stage_cfg, "min_trading_days", errors=errors, path=f"validation.validation_gates.stages.{stage}")
        for metric_name in (
            "max_unresolved_reconcile_rate_pct",
            "max_reject_rate_pct",
            "max_cost_mismatch_rate_pct",
            "min_fill_coverage_pct",
            "min_cost_materialization_coverage_pct",
            "min_cancel_success_rate_pct",
            "max_gross_net_inconsistency_rate_pct",
        ):
            _require_number(stage_cfg, metric_name, errors=errors, path=f"validation.validation_gates.stages.{stage}")
        if stage == "testnet":
            _require_bool(
                stage_cfg,
                "require_real_user_data_stream_or_explicit_degraded_mode",
                errors=errors,
                path="validation.validation_gates.stages.testnet",
            )

    blocks = _require_dict(root, "blocks", errors=errors, path="validation.validation_gates")
    for key in (
        "block_if_kill_switch_active",
        "block_if_fee_source_missing_in_live_like_modes",
        "block_if_snapshot_stale",
        "block_if_policy_missing",
        "allow_manual_override",
    ):
        _require_bool(blocks, key, errors=errors, path="validation.validation_gates.blocks")

    promotion = _require_dict(root, "promotion", errors=errors, path="validation.validation_gates")
    _require_str_list(promotion, "order", errors=errors, path="validation.validation_gates.promotion")
    _require_bool(promotion, "auto_activate_live_serio", errors=errors, path="validation.validation_gates.promotion")
    _require_str_list(promotion, "live_like_stages", errors=errors, path="validation.validation_gates.promotion")

    environments = _require_dict(root, "environments", errors=errors, path="validation.validation_gates")
    for stage in ("paper", "testnet", "canary", "live_serio"):
        env_cfg = _require_dict(environments, stage, errors=errors, path="validation.validation_gates.environments")
        _require_string(env_cfg, "mode", errors=errors, path=f"validation.validation_gates.environments.{stage}")
        _require_string(env_cfg, "environment", errors=errors, path=f"validation.validation_gates.environments.{stage}")
        for key in ("preconditions", "control_metrics", "exit_criteria", "blocking_causes", "warnings"):
            _require_str_list(env_cfg, key, errors=errors, path=f"validation.validation_gates.environments.{stage}")

    return errors


def clear_validation_gates_policy_cache() -> None:
    _load_validation_gates_bundle_cached.cache_clear()


@lru_cache(maxsize=8)
def _load_validation_gates_bundle_cached(repo_root_str: str, explicit_root_str: str) -> dict[str, Any]:
    repo_root = Path(repo_root_str).resolve()
    explicit_root = Path(explicit_root_str).resolve() if explicit_root_str else None
    resolution = describe_policy_root_resolution(
        repo_root,
        explicit=explicit_root,
        expected_files=POLICY_EXPECTED_FILES,
    )
    selected_root = Path(resolution["selected_root"]).resolve()
    policy_path = (selected_root / VALIDATION_GATES_FILENAME).resolve()

    payload: dict[str, Any] = {}
    valid = False
    source_hash = ""
    errors: list[str] = []
    warnings = list(resolution.get("warnings") or [])
    if policy_path.exists():
        try:
            raw_bytes = policy_path.read_bytes()
            raw = yaml.safe_load(raw_bytes.decode("utf-8")) or {}
            source_hash = hashlib.sha256(raw_bytes).hexdigest()
            validation_errors = _validate_validation_gates_policy(raw) if isinstance(raw, dict) and raw else ["validation_gates.yaml vacio o ausente"]
            if isinstance(raw, dict) and raw and not validation_errors:
                payload = raw
                valid = True
            else:
                errors.extend(validation_errors)
        except Exception:
            errors.append("validation_gates.yaml no pudo parsearse como YAML valido")
    else:
        errors.append("validation_gates.yaml no existe en la raiz seleccionada")

    active_policy = copy.deepcopy(payload if valid else FAIL_CLOSED_MINIMAL_VALIDATION_GATES_POLICY)
    policy_hash = _stable_payload_hash(active_policy)
    return {
        "source_root": str(selected_root),
        "path": str(policy_path),
        "exists": policy_path.exists(),
        "valid": valid,
        "fallback_used": bool(resolution.get("fallback_used")),
        "selected_role": resolution.get("selected_role"),
        "canonical_root": resolution.get("canonical_root"),
        "canonical_role": resolution.get("canonical_role"),
        "divergent_candidates": copy.deepcopy(resolution.get("divergent_candidates") or []),
        "source_hash": source_hash,
        "policy_hash": policy_hash,
        "source": _validation_source_label(repo_root, policy_path) if valid else "default_fail_closed_minimal",
        "errors": errors,
        "warnings": warnings,
        "validation_gates_bundle": active_policy,
    }


def load_validation_gates_bundle(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_root = (repo_root or _resolve_repo_root_for_policy() or Path.cwd()).resolve()
    explicit_root_str = str(explicit_root.resolve()) if explicit_root is not None else ""
    return copy.deepcopy(_load_validation_gates_bundle_cached(str(resolved_repo_root), explicit_root_str))


def validation_gates_policy(
    repo_root: Path | None = None,
    *,
    explicit_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_validation_gates_bundle(repo_root, explicit_root=explicit_root)
    payload = bundle.get("validation_gates_bundle")
    return payload if isinstance(payload, dict) else copy.deepcopy(FAIL_CLOSED_MINIMAL_VALIDATION_GATES_POLICY)


def _hydrate_run_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["source_snapshot_ids_json"] = _json_loads(out.get("source_snapshot_ids_json"), [])
    out["blocking_reasons_json"] = _json_loads(out.get("blocking_reasons_json"), [])
    out["warnings_json"] = _json_loads(out.get("warnings_json"), [])
    out["key_metrics_json"] = _json_loads(out.get("key_metrics_json"), {})
    out["degraded_mode_seen"] = _bool(out.get("degraded_mode_seen"))
    return out


def _hydrate_gate_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["passed"] = _bool(out.get("passed"))
    out["blocking"] = _bool(out.get("blocking"))
    out["details_json"] = _json_loads(out.get("details_json"), {})
    return out


def _hydrate_evidence_row(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    out = copy.deepcopy(payload)
    out["payload_json"] = _json_loads(out.get("payload_json"), {})
    return out


class ValidationDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = runtime_path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS validation_runs (
                  validation_run_id TEXT PRIMARY KEY,
                  created_at TEXT NOT NULL,
                  stage TEXT NOT NULL,
                  venue TEXT NOT NULL,
                  family TEXT,
                  symbol TEXT,
                  mode TEXT NOT NULL,
                  period_start TEXT,
                  period_end TEXT,
                  total_orders INTEGER NOT NULL DEFAULT 0,
                  total_fills INTEGER NOT NULL DEFAULT 0,
                  total_rejects INTEGER NOT NULL DEFAULT 0,
                  unresolved_reconcile_count INTEGER NOT NULL DEFAULT 0,
                  cost_mismatch_count INTEGER NOT NULL DEFAULT 0,
                  degraded_mode_seen INTEGER NOT NULL DEFAULT 0,
                  kill_switch_trip_count INTEGER NOT NULL DEFAULT 0,
                  margin_guard_block_count INTEGER NOT NULL DEFAULT 0,
                  gross_pnl REAL,
                  net_pnl REAL,
                  total_cost_realized REAL,
                  source_snapshot_ids_json TEXT NOT NULL DEFAULT '[]',
                  policy_hash TEXT NOT NULL DEFAULT '',
                  blocking_reasons_json TEXT NOT NULL DEFAULT '[]',
                  warnings_json TEXT NOT NULL DEFAULT '[]',
                  key_metrics_json TEXT NOT NULL DEFAULT '{}',
                  result TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS validation_gate_results (
                  validation_gate_result_id TEXT PRIMARY KEY,
                  validation_run_id TEXT NOT NULL,
                  gate_name TEXT NOT NULL,
                  metric_name TEXT NOT NULL,
                  observed_value REAL,
                  threshold_value REAL,
                  comparator TEXT NOT NULL,
                  passed INTEGER NOT NULL,
                  blocking INTEGER NOT NULL,
                  details_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_validation_gate_results_run
                  ON validation_gate_results(validation_run_id, gate_name);

                CREATE TABLE IF NOT EXISTS validation_stage_evidence (
                  evidence_id TEXT PRIMARY KEY,
                  validation_run_id TEXT NOT NULL,
                  evidence_type TEXT NOT NULL,
                  source TEXT NOT NULL,
                  source_hash TEXT,
                  payload_json TEXT NOT NULL DEFAULT '{}',
                  created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_validation_stage_evidence_run
                  ON validation_stage_evidence(validation_run_id, created_at DESC);
                """
            )

    def insert_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "validation_run_id": str(payload.get("validation_run_id") or uuid4()),
            "created_at": str(payload.get("created_at") or utc_now_iso()),
            "stage": _normalize_stage(payload.get("stage")),
            "venue": str(payload.get("venue") or "binance"),
            "family": str(payload.get("family") or "") or None,
            "symbol": _canonical_symbol(payload.get("symbol")) or None,
            "mode": str(payload.get("mode") or "paper"),
            "period_start": payload.get("period_start"),
            "period_end": payload.get("period_end"),
            "total_orders": _safe_int(payload.get("total_orders"), 0),
            "total_fills": _safe_int(payload.get("total_fills"), 0),
            "total_rejects": _safe_int(payload.get("total_rejects"), 0),
            "unresolved_reconcile_count": _safe_int(payload.get("unresolved_reconcile_count"), 0),
            "cost_mismatch_count": _safe_int(payload.get("cost_mismatch_count"), 0),
            "degraded_mode_seen": 1 if _bool(payload.get("degraded_mode_seen")) else 0,
            "kill_switch_trip_count": _safe_int(payload.get("kill_switch_trip_count"), 0),
            "margin_guard_block_count": _safe_int(payload.get("margin_guard_block_count"), 0),
            "gross_pnl": None if payload.get("gross_pnl") is None else _safe_float(payload.get("gross_pnl")),
            "net_pnl": None if payload.get("net_pnl") is None else _safe_float(payload.get("net_pnl")),
            "total_cost_realized": None if payload.get("total_cost_realized") is None else _safe_float(payload.get("total_cost_realized")),
            "source_snapshot_ids_json": _json_dumps(payload.get("source_snapshot_ids_json") or []),
            "policy_hash": str(payload.get("policy_hash") or ""),
            "blocking_reasons_json": _json_dumps(payload.get("blocking_reasons_json") or []),
            "warnings_json": _json_dumps(payload.get("warnings_json") or []),
            "key_metrics_json": _json_dumps(payload.get("key_metrics_json") or {}),
            "result": _normalize_result(payload.get("result")),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO validation_runs (
                  validation_run_id, created_at, stage, venue, family, symbol, mode,
                  period_start, period_end, total_orders, total_fills, total_rejects,
                  unresolved_reconcile_count, cost_mismatch_count, degraded_mode_seen,
                  kill_switch_trip_count, margin_guard_block_count, gross_pnl, net_pnl,
                  total_cost_realized, source_snapshot_ids_json, policy_hash,
                  blocking_reasons_json, warnings_json, key_metrics_json, result
                ) VALUES (
                  :validation_run_id, :created_at, :stage, :venue, :family, :symbol, :mode,
                  :period_start, :period_end, :total_orders, :total_fills, :total_rejects,
                  :unresolved_reconcile_count, :cost_mismatch_count, :degraded_mode_seen,
                  :kill_switch_trip_count, :margin_guard_block_count, :gross_pnl, :net_pnl,
                  :total_cost_realized, :source_snapshot_ids_json, :policy_hash,
                  :blocking_reasons_json, :warnings_json, :key_metrics_json, :result
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM validation_runs WHERE validation_run_id = ?",
                (row["validation_run_id"],),
            ).fetchone()
        return _hydrate_run_row(dict(stored) if stored is not None else row) or row

    def insert_gate_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "validation_gate_result_id": str(payload.get("validation_gate_result_id") or uuid4()),
            "validation_run_id": str(payload.get("validation_run_id") or ""),
            "gate_name": str(payload.get("gate_name") or ""),
            "metric_name": str(payload.get("metric_name") or ""),
            "observed_value": None if payload.get("observed_value") is None else _safe_float(payload.get("observed_value")),
            "threshold_value": None if payload.get("threshold_value") is None else _safe_float(payload.get("threshold_value")),
            "comparator": str(payload.get("comparator") or ""),
            "passed": 1 if _bool(payload.get("passed")) else 0,
            "blocking": 1 if _bool(payload.get("blocking")) else 0,
            "details_json": _json_dumps(payload.get("details_json") or {}),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO validation_gate_results (
                  validation_gate_result_id, validation_run_id, gate_name, metric_name,
                  observed_value, threshold_value, comparator, passed, blocking, details_json
                ) VALUES (
                  :validation_gate_result_id, :validation_run_id, :gate_name, :metric_name,
                  :observed_value, :threshold_value, :comparator, :passed, :blocking, :details_json
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM validation_gate_results WHERE validation_gate_result_id = ?",
                (row["validation_gate_result_id"],),
            ).fetchone()
        return _hydrate_gate_row(dict(stored) if stored is not None else row) or row

    def insert_stage_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {
            "evidence_id": str(payload.get("evidence_id") or uuid4()),
            "validation_run_id": str(payload.get("validation_run_id") or ""),
            "evidence_type": str(payload.get("evidence_type") or ""),
            "source": str(payload.get("source") or ""),
            "source_hash": str(payload.get("source_hash") or "") or None,
            "payload_json": _json_dumps(payload.get("payload_json") or {}),
            "created_at": str(payload.get("created_at") or utc_now_iso()),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO validation_stage_evidence (
                  evidence_id, validation_run_id, evidence_type, source, source_hash, payload_json, created_at
                ) VALUES (
                  :evidence_id, :validation_run_id, :evidence_type, :source, :source_hash, :payload_json, :created_at
                )
                """,
                row,
            )
            stored = conn.execute(
                "SELECT * FROM validation_stage_evidence WHERE evidence_id = ?",
                (row["evidence_id"],),
            ).fetchone()
        return _hydrate_evidence_row(dict(stored) if stored is not None else row) or row

    def list_runs(
        self,
        *,
        stage: str | None = None,
        result: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        params: list[Any] = []
        if stage:
            clauses.append("stage = ?")
            params.append(_normalize_stage(stage))
        if result:
            clauses.append("result = ?")
            params.append(_normalize_result(result))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM validation_runs
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC, validation_run_id DESC
                LIMIT ? OFFSET ?
                """,
                tuple([*params, max(1, int(limit)), max(0, int(offset))]),
            ).fetchall()
        return [_hydrate_run_row(dict(row)) or {} for row in rows]

    def latest_run(self, *, stage: str | None = None) -> dict[str, Any] | None:
        rows = self.list_runs(stage=stage, limit=1, offset=0)
        return rows[0] if rows else None

    def run_by_id(self, validation_run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM validation_runs WHERE validation_run_id = ?",
                (str(validation_run_id),),
            ).fetchone()
        return _hydrate_run_row(dict(row)) if row is not None else None

    def gate_results_for_run(self, validation_run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM validation_gate_results
                WHERE validation_run_id = ?
                ORDER BY blocking DESC, gate_name ASC, validation_gate_result_id ASC
                """,
                (str(validation_run_id),),
            ).fetchall()
        return [_hydrate_gate_row(dict(row)) or {} for row in rows]

    def stage_evidence_for_run(self, validation_run_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM validation_stage_evidence
                WHERE validation_run_id = ?
                ORDER BY created_at ASC, evidence_id ASC
                """,
                (str(validation_run_id),),
            ).fetchall()
        return [_hydrate_evidence_row(dict(row)) or {} for row in rows]


class ValidationService:
    def __init__(
        self,
        *,
        user_data_dir: Path,
        repo_root: Path,
        execution_service: Any,
        reporting_bridge_service: Any,
        instrument_registry_service: Any,
        universe_service: Any | None = None,
        explicit_policy_root: Path | None = None,
    ) -> None:
        self.user_data_dir = runtime_path(user_data_dir)
        self.repo_root = Path(repo_root).resolve()
        self.execution_service = execution_service
        self.reporting_bridge_service = reporting_bridge_service
        self.instrument_registry_service = instrument_registry_service
        self.universe_service = universe_service
        self.explicit_policy_root = explicit_policy_root.resolve() if explicit_policy_root is not None else None
        self.db = ValidationDB(self.user_data_dir / "validation" / "validation.sqlite3")

    def policy_bundle(self) -> dict[str, Any]:
        return load_validation_gates_bundle(self.repo_root, explicit_root=self.explicit_policy_root)

    def policy(self) -> dict[str, Any]:
        bundle = self.policy_bundle()
        payload = bundle.get("validation_gates_bundle")
        return copy.deepcopy(payload) if isinstance(payload, dict) else copy.deepcopy(FAIL_CLOSED_MINIMAL_VALIDATION_GATES_POLICY)

    def policy_source(self) -> dict[str, Any]:
        bundle = self.policy_bundle()
        return {
            "path": bundle.get("path"),
            "source_root": bundle.get("source_root"),
            "source_hash": bundle.get("source_hash"),
            "policy_hash": bundle.get("policy_hash"),
            "source": bundle.get("source"),
            "valid": bool(bundle.get("valid")),
            "errors": list(bundle.get("errors") or []),
            "warnings": list(bundle.get("warnings") or []),
            "fallback_used": bool(bundle.get("fallback_used")),
            "selected_role": bundle.get("selected_role"),
            "canonical_root": bundle.get("canonical_root"),
            "canonical_role": bundle.get("canonical_role"),
            "divergent_candidates": copy.deepcopy(bundle.get("divergent_candidates") or []),
        }

    def policy_hash(self) -> str:
        return str(self.policy_source().get("policy_hash") or "")

    def _root_policy(self) -> dict[str, Any]:
        payload = self.policy().get("validation_gates")
        return payload if isinstance(payload, dict) else {}

    def _stage_definition(self, stage: str) -> dict[str, Any]:
        key = _normalize_stage(stage).lower()
        payload = self._root_policy().get("environments")
        if not isinstance(payload, dict):
            return {}
        stage_cfg = payload.get(key)
        return stage_cfg if isinstance(stage_cfg, dict) else {}

    def _stage_thresholds(self, stage: str) -> dict[str, Any]:
        key = _normalize_stage(stage).lower()
        payload = self._root_policy().get("stages")
        if not isinstance(payload, dict):
            return {}
        stage_cfg = payload.get(key)
        return stage_cfg if isinstance(stage_cfg, dict) else {}

    def _blocks_policy(self) -> dict[str, Any]:
        payload = self._root_policy().get("blocks")
        return payload if isinstance(payload, dict) else {}

    def _promotion_policy(self) -> dict[str, Any]:
        payload = self._root_policy().get("promotion")
        return payload if isinstance(payload, dict) else {}

    def _stage_mode(self, stage: str) -> str:
        return str(self._stage_definition(stage).get("mode") or "paper").strip().lower()

    def _stage_environment(self, stage: str) -> str:
        return str(self._stage_definition(stage).get("environment") or "paper").strip().lower()

    def _stage_warnings(self, stage: str) -> list[str]:
        warnings = self._stage_definition(stage).get("warnings")
        return [str(item).strip() for item in warnings] if isinstance(warnings, list) else []

    def _supported_router_families(self) -> list[str]:
        router = self.execution_service.router_policy() if hasattr(self.execution_service, "router_policy") else {}
        families = router.get("families_enabled") if isinstance(router.get("families_enabled"), dict) else {}
        return [name for name, enabled in sorted(families.items()) if _bool(enabled)]

    def _stage_supported_families(self, stage: str) -> list[str]:
        stage_name = _normalize_stage(stage)
        router_families = self._supported_router_families()
        if stage_name == "PAPER":
            return router_families
        parity = self.instrument_registry_service.live_parity_matrix() if self.instrument_registry_service is not None else {}
        environment = "testnet" if stage_name == "TESTNET" else "live"
        supported: list[str] = []
        for family in router_families:
            env_payload = ((parity.get(family) or {}).get(environment) or {}) if isinstance(parity, dict) else {}
            if _bool(env_payload.get("supported")):
                supported.append(family)
        return supported

    def _select_families(self, stage: str, family: str | None) -> tuple[list[str], list[str], list[str]]:
        requested = _normalize_family(family)
        supported = self._stage_supported_families(stage)
        warnings: list[str] = []
        blockers: list[str] = []
        if requested:
            if requested not in supported:
                blockers.append(f"family_not_supported_for_stage:{requested}:{_normalize_stage(stage)}")
                return [], warnings, blockers
            return [requested], warnings, blockers
        if _normalize_stage(stage) == "TESTNET":
            excluded = sorted(set(self._supported_router_families()) - set(supported))
            if excluded:
                warnings.append(f"testnet_families_excluded:{','.join(excluded)}")
        return supported, warnings, blockers

    def _filter_orders(self, *, environment: str, families: list[str], symbol: str | None) -> list[dict[str, Any]]:
        symbol_n = _canonical_symbol(symbol)
        rows = self.execution_service.db.list_orders(limit=5000, offset=0)
        out: list[dict[str, Any]] = []
        for row in rows:
            if str(row.get("environment") or "").strip().lower() != environment:
                continue
            if families and _normalize_family(row.get("family")) not in families:
                continue
            if symbol_n and _canonical_symbol(row.get("symbol")) != symbol_n:
                continue
            out.append(copy.deepcopy(row))
        return out

    def _filter_intents(self, *, environment: str, families: list[str], symbol: str | None) -> list[dict[str, Any]]:
        symbol_n = _canonical_symbol(symbol)
        rows = self.execution_service.db.list_intents(limit=5000, offset=0)
        out: list[dict[str, Any]] = []
        for row in rows:
            if str(row.get("environment") or "").strip().lower() != environment:
                continue
            if families and _normalize_family(row.get("family")) not in families:
                continue
            if symbol_n and _canonical_symbol(row.get("symbol")) != symbol_n:
                continue
            out.append(copy.deepcopy(row))
        return out

    def _filter_reconcile_events(self, *, environment: str, families: list[str], symbol: str | None) -> list[dict[str, Any]]:
        symbol_n = _canonical_symbol(symbol)
        order_symbol_by_id: dict[str, str] = {}
        for order in self._filter_orders(environment=environment, families=families, symbol=symbol):
            order_symbol_by_id[str(order.get("execution_order_id") or "")] = _canonical_symbol(order.get("symbol"))
        rows = self.execution_service.db.list_reconcile_events()
        out: list[dict[str, Any]] = []
        for row in rows:
            if str(row.get("environment") or "").strip().lower() != environment:
                continue
            if families and _normalize_family(row.get("family")) not in families:
                continue
            if symbol_n:
                order_id = str(row.get("execution_order_id") or "")
                if order_symbol_by_id.get(order_id) != symbol_n:
                    continue
            out.append(copy.deepcopy(row))
        return out

    def _filter_trade_rows(self, *, environment: str, families: list[str], symbol: str | None) -> list[dict[str, Any]]:
        if self.reporting_bridge_service is None or not hasattr(self.reporting_bridge_service, "db"):
            return []
        symbol_n = _canonical_symbol(symbol)
        rows = self.reporting_bridge_service.db.trade_rows()
        out: list[dict[str, Any]] = []
        for row in rows:
            if not _execution_runtime_trade_row(row):
                continue
            if str(row.get("environment") or "").strip().lower() != environment:
                continue
            if families and _normalize_family(row.get("family")) not in families:
                continue
            if symbol_n and _canonical_symbol(row.get("symbol")) != symbol_n:
                continue
            out.append(copy.deepcopy(row))
        return out

    def _timestamp_window(
        self,
        *,
        orders: list[dict[str, Any]],
        fills: list[dict[str, Any]],
        trade_rows: list[dict[str, Any]],
        intents: list[dict[str, Any]],
    ) -> tuple[str | None, str | None, list[datetime]]:
        timestamps: list[datetime] = []
        for row in orders:
            for key in ("submitted_at", "acknowledged_at", "canceled_at", "expired_at"):
                parsed = _parse_ts(row.get(key))
                if parsed is not None:
                    timestamps.append(parsed)
        for row in fills:
            parsed = _parse_ts(row.get("fill_time"))
            if parsed is not None:
                timestamps.append(parsed)
        for row in trade_rows:
            parsed = _parse_ts(row.get("executed_at"))
            if parsed is not None:
                timestamps.append(parsed)
        for row in intents:
            parsed = _parse_ts(row.get("created_at")) or _parse_ts(row.get("submitted_at"))
            if parsed is not None:
                timestamps.append(parsed)
        if not timestamps:
            return None, None, []
        timestamps.sort()
        return timestamps[0].isoformat(), timestamps[-1].isoformat(), timestamps

    def _stream_requirements(
        self,
        *,
        stage: str,
        environment: str,
        families: list[str],
        reconcile_summary: dict[str, Any],
    ) -> dict[str, Any]:
        pair_map: dict[tuple[str, str], dict[str, Any]] = {}
        for row in reconcile_summary.get("pairs_checked") or []:
            family = _normalize_family(row.get("family"))
            pair_environment = str(row.get("environment") or "").strip().lower()
            pair_map[(family, pair_environment)] = copy.deepcopy(row.get("stream_state") or {})

        states: list[dict[str, Any]] = []
        for family in families:
            if environment not in {"testnet", "live"}:
                states.append(
                    {
                        "family": family,
                        "available": True,
                        "degraded_mode": False,
                        "reason": "not_required",
                    }
                )
                continue
            stream_state = pair_map.get((family, environment), {})
            states.append(
                {
                    "family": family,
                    "available": _bool(stream_state.get("available")),
                    "degraded_mode": _bool(stream_state.get("degraded_mode")) if stream_state else True,
                    "reason": str(stream_state.get("reason") or ("stream_status_unknown" if not stream_state else "ok")),
                }
            )
        return {
            "stage": _normalize_stage(stage),
            "states": states,
            "available_all": all(_bool(row.get("available")) for row in states) if states else False,
            "explicit_degraded_mode": any(_bool(row.get("degraded_mode")) for row in states),
        }

    def _snapshot_ids(self, *, stage: str, families: list[str]) -> list[str]:
        environment = "testnet" if _normalize_stage(stage) == "TESTNET" else "live"
        snapshot_ids: list[str] = []
        if self.instrument_registry_service is None or not hasattr(self.instrument_registry_service, "db"):
            return snapshot_ids
        for family in families:
            latest = self.instrument_registry_service.db.latest_snapshot(family, environment, success_only=False)
            if latest and latest.get("snapshot_id"):
                snapshot_ids.append(str(latest.get("snapshot_id")))
        return sorted({item for item in snapshot_ids if item})

    def _stage_snapshot_fresh(self, *, stage: str, families: list[str]) -> bool:
        if not families:
            return False
        environment = "testnet" if _normalize_stage(stage) == "TESTNET" else "live"
        parity = self.instrument_registry_service.live_parity_matrix() if self.instrument_registry_service is not None else {}
        return all(_bool((((parity.get(family) or {}).get(environment)) or {}).get("snapshot_fresh")) for family in families)

    def _stage_fee_source_fresh(self, *, stage: str, families: list[str]) -> bool:
        if not families or self.reporting_bridge_service is None or not hasattr(self.reporting_bridge_service, "db"):
            return False
        environment = "testnet" if _normalize_stage(stage) == "TESTNET" else "live"
        policy = self.reporting_bridge_service.cost_stack() if hasattr(self.reporting_bridge_service, "cost_stack") else {}
        alerts_cfg = policy.get("alerts") if isinstance(policy.get("alerts"), dict) else {}
        stale_hours = max(1, _safe_int(alerts_cfg.get("warn_if_fee_source_stale_hours_gt"), 24))
        rows = self.reporting_bridge_service.db.cost_source_snapshots()
        now = _utc_now()
        for family in families:
            family_rows = [
                row
                for row in rows
                if _normalize_family(row.get("family")) == family
                and str(row.get("environment") or "").strip().lower() == environment
                and _bool(row.get("success"))
            ]
            if not family_rows:
                return False
            latest = max((_parse_ts(row.get("fetched_at")) or datetime(1970, 1, 1, tzinfo=timezone.utc)) for row in family_rows)
            if (now - latest).total_seconds() > float(stale_hours * 3600):
                return False
        return True

    def _gross_net_inconsistency_rate(self, trade_rows: list[dict[str, Any]]) -> float:
        if not trade_rows:
            return 0.0
        inconsistent = 0
        for row in trade_rows:
            gross = _safe_float(row.get("gross_pnl"), 0.0)
            net = _safe_float(row.get("net_pnl"), 0.0)
            effective_cost = _safe_float(
                row.get("total_cost_realized")
                if row.get("total_cost_realized") is not None
                else row.get("total_cost_estimated"),
                0.0,
            )
            if abs(net - (gross - effective_cost)) > 0.000001:
                inconsistent += 1
        return _percent(inconsistent, len(trade_rows))

    def _cost_materialization_coverage(self, fills: list[dict[str, Any]], trade_rows: list[dict[str, Any]]) -> float:
        if not fills:
            return 100.0
        realized_trade_refs = {
            str((row.get("provenance") if isinstance(row.get("provenance"), dict) else {}).get("trade_ref") or row.get("trade_ref") or "")
            for row in trade_rows
        }
        if not realized_trade_refs:
            return 0.0
        covered = 0
        for fill in fills:
            trade_ref = str(fill.get("execution_fill_id") or fill.get("venue_trade_id") or "")
            if trade_ref in realized_trade_refs:
                covered += 1
        return _percent(covered, len(fills))

    def _fills_expected_count(self, orders: list[dict[str, Any]]) -> int:
        expected = 0
        for order in orders:
            status = str(order.get("order_status") or "").upper()
            executed_qty = _safe_float(order.get("executed_qty"), 0.0)
            if status == "FILLED" or executed_qty > 0.0:
                expected += 1
        return expected

    def _collect_metrics(
        self,
        *,
        stage: str,
        venue: str,
        family: str | None,
        symbol: str | None,
    ) -> dict[str, Any]:
        stage_name = _normalize_stage(stage)
        environment = self._stage_environment(stage_name)
        mode = self._stage_mode(stage_name)
        families, selection_warnings, selection_blockers = self._select_families(stage_name, family)
        if not families and not selection_blockers and stage_name == "PAPER":
            selection_blockers.append("no_router_family_enabled")
        orders = self._filter_orders(environment=environment, families=families, symbol=symbol)
        intents = self._filter_intents(environment=environment, families=families, symbol=symbol)
        fills = [
            fill
            for order in orders
            for fill in self.execution_service.db.fills_for_order(str(order.get("execution_order_id") or ""))
        ]
        reconcile_events = self._filter_reconcile_events(environment=environment, families=families, symbol=symbol)
        trade_rows = self._filter_trade_rows(environment=environment, families=families, symbol=symbol)
        period_start, period_end, timestamps = self._timestamp_window(
            orders=orders,
            fills=fills,
            trade_rows=trade_rows,
            intents=intents,
        )
        trading_days = len({ts.date().isoformat() for ts in timestamps})
        runtime_hours = round((timestamps[-1] - timestamps[0]).total_seconds() / 3600.0, 6) if len(timestamps) >= 2 else 0.0
        rejected_orders = sum(
            1
            for row in orders
            if str(row.get("order_status") or "").upper() == "REJECTED"
            or str(row.get("reject_code") or "").strip()
            or str(row.get("reject_reason") or "").strip()
        )
        submit_failed = sum(
            1
            for row in intents
            if str(row.get("preflight_status") or "").strip().lower() == "submit_failed"
        )
        total_rejects = rejected_orders + submit_failed
        total_attempts = len(orders) + submit_failed
        unresolved_reconcile_events = [row for row in reconcile_events if not _bool(row.get("resolved"))]
        cost_mismatch_events = [
            row for row in unresolved_reconcile_events if str(row.get("reconcile_type") or "") == "cost_mismatch"
        ]
        kill_switch_events = self.execution_service.db.kill_switch_events(limit=1000)
        if families:
            kill_switch_events = [
                row for row in kill_switch_events if not row.get("family") or _normalize_family(row.get("family")) in families
            ]
        symbol_n = _canonical_symbol(symbol)
        if symbol_n:
            kill_switch_events = [
                row for row in kill_switch_events if not row.get("symbol") or _canonical_symbol(row.get("symbol")) == symbol_n
            ]
        margin_guard_block_count = sum(
            1
            for row in intents
            if any(
                str(item).strip().lower() in {"margin_level_blocked", "margin_capability_missing", "margin_level_missing"}
                for item in (row.get("preflight_errors_json") or [])
            )
        )
        expected_fill_orders = self._fills_expected_count(orders)
        orders_with_fills = len({str(row.get("execution_order_id") or "") for row in fills if str(row.get("execution_order_id") or "")})
        fill_coverage_pct = 100.0 if expected_fill_orders == 0 else _percent(orders_with_fills, expected_fill_orders)
        cost_materialization_coverage_pct = self._cost_materialization_coverage(fills, trade_rows)
        gross_pnl = round(sum(_safe_float(row.get("gross_pnl"), 0.0) for row in trade_rows), 8)
        net_pnl = round(sum(_safe_float(row.get("net_pnl"), 0.0) for row in trade_rows), 8)
        total_cost_realized = round(sum(_safe_float(row.get("total_cost_realized"), 0.0) for row in trade_rows), 8)
        reconcile_summary = self.execution_service.reconcile_orders()
        live_safety = self.execution_service.live_safety_summary(reconcile_summary=reconcile_summary)
        stream_requirements = self._stream_requirements(
            stage=stage_name,
            environment=environment,
            families=families,
            reconcile_summary=reconcile_summary,
        )
        stage_snapshot_fresh = self._stage_snapshot_fresh(stage=stage_name, families=families) if stage_name in {"TESTNET", "CANARY"} else _bool(live_safety.get("snapshot_fresh"))
        stage_fee_source_fresh = self._stage_fee_source_fresh(stage=stage_name, families=families) if stage_name in {"TESTNET", "CANARY"} else _bool(live_safety.get("fee_source_fresh"))
        return {
            "stage": stage_name,
            "venue": str(venue or "binance"),
            "family": _normalize_family(family) or None,
            "symbol": symbol_n or None,
            "mode": mode,
            "environment": environment,
            "families_evaluated": families,
            "selection_warnings": selection_warnings,
            "selection_blockers": selection_blockers,
            "period_start": period_start,
            "period_end": period_end,
            "total_orders": len(orders),
            "total_fills": len(fills),
            "total_rejects": total_rejects,
            "total_attempts": total_attempts,
            "unresolved_reconcile_count": len(unresolved_reconcile_events),
            "cost_mismatch_count": len(cost_mismatch_events),
            "degraded_mode_seen": _bool(live_safety.get("degraded_mode")) or stream_requirements["explicit_degraded_mode"],
            "kill_switch_trip_count": len(kill_switch_events),
            "margin_guard_block_count": margin_guard_block_count,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "total_cost_realized": total_cost_realized,
            "trading_days": trading_days,
            "runtime_hours": runtime_hours,
            "unresolved_reconcile_rate_pct": _percent(len(unresolved_reconcile_events), max(len(orders), 1)),
            "reject_rate_pct": _percent(total_rejects, max(total_attempts, 1)),
            "cost_mismatch_rate_pct": _percent(len(cost_mismatch_events), max(len(orders), 1)),
            "fill_coverage_pct": fill_coverage_pct,
            "cost_materialization_coverage_pct": cost_materialization_coverage_pct,
            "cancel_success_rate_pct": 100.0,
            "gross_net_inconsistency_rate_pct": self._gross_net_inconsistency_rate(trade_rows),
            "execution_policy_loaded": _bool(live_safety.get("execution_policy_loaded")) and self.execution_service.policies_loaded(),
            "kill_switch_active": _bool((live_safety.get("kill_switch_status") or {}).get("blocking_submit")),
            "snapshot_fresh": stage_snapshot_fresh,
            "fee_source_fresh": stage_fee_source_fresh,
            "margin_guard_status": str(live_safety.get("margin_guard_status") or "UNKNOWN"),
            "overall_safety_status": str(live_safety.get("overall_status") or "BLOCK"),
            "stream_requirements": stream_requirements,
            "source_snapshot_ids": self._snapshot_ids(stage=stage_name, families=families),
            "live_safety": live_safety,
            "reconcile_summary": reconcile_summary,
        }

    def _gate(
        self,
        *,
        gate_name: str,
        metric_name: str,
        observed_value: Any,
        threshold_value: Any,
        comparator: str,
        passed: bool,
        blocking: bool,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "gate_name": gate_name,
            "metric_name": metric_name,
            "observed_value": None if observed_value is None else _safe_float(observed_value),
            "threshold_value": None if threshold_value is None else _safe_float(threshold_value),
            "comparator": comparator,
            "passed": bool(passed),
            "blocking": bool(blocking),
            "details_json": details or {},
        }

    def _previous_stage(self, stage: str) -> str | None:
        order = [item for item in self._promotion_policy().get("order", list(VALIDATION_STAGES)) if str(item).strip()]
        normalized_order = [_normalize_stage(item) for item in order]
        stage_name = _normalize_stage(stage)
        try:
            idx = normalized_order.index(stage_name)
        except ValueError:
            return None
        if idx <= 0:
            return None
        return normalized_order[idx - 1]

    def _latest_stage_result(self, stage: str | None) -> str | None:
        if not stage:
            return None
        row = self.db.latest_run(stage=stage)
        return str(row.get("result") or "") if isinstance(row, dict) else None

    def _evaluate_gates(self, *, stage: str, metrics: dict[str, Any]) -> tuple[list[dict[str, Any]], str, list[str], list[str]]:
        stage_name = _normalize_stage(stage)
        thresholds = self._stage_thresholds(stage_name)
        blocks_cfg = self._blocks_policy()
        gates: list[dict[str, Any]] = []
        blocking_reasons: list[str] = []
        warnings: list[str] = [*self._stage_warnings(stage_name), *list(metrics.get("selection_warnings") or [])]

        previous_stage = self._previous_stage(stage_name)
        previous_result = self._latest_stage_result(previous_stage) if previous_stage else "PASS"
        gates.append(
            self._gate(
                gate_name="previous_stage_pass",
                metric_name="previous_stage_result",
                observed_value=None,
                threshold_value=None,
                comparator="== PASS",
                passed=(previous_result == "PASS"),
                blocking=previous_stage is not None,
                details={"previous_stage": previous_stage, "previous_result": previous_result},
            )
        )
        gates.append(
            self._gate(
                gate_name="validation_policy_loaded",
                metric_name="policy_valid",
                observed_value=1 if self.policy_source().get("valid") else 0,
                threshold_value=1,
                comparator="==",
                passed=bool(self.policy_source().get("valid")),
                blocking=_bool(blocks_cfg.get("block_if_policy_missing")),
                details={"policy_source": self.policy_source()},
            )
        )
        gates.append(
            self._gate(
                gate_name="execution_policy_loaded",
                metric_name="execution_policy_loaded",
                observed_value=1 if metrics.get("execution_policy_loaded") else 0,
                threshold_value=1,
                comparator="==",
                passed=bool(metrics.get("execution_policy_loaded")),
                blocking=True,
                details={"execution_policy_source": self.execution_service.policy_source()},
            )
        )
        gates.append(
            self._gate(
                gate_name="family_selection_supported",
                metric_name="selected_families",
                observed_value=float(len(metrics.get("families_evaluated") or [])),
                threshold_value=1.0,
                comparator=">=",
                passed=bool(metrics.get("families_evaluated")) and not bool(metrics.get("selection_blockers")),
                blocking=True,
                details={
                    "families_evaluated": metrics.get("families_evaluated") or [],
                    "selection_blockers": metrics.get("selection_blockers") or [],
                },
            )
        )
        kill_switch_active = bool(metrics.get("kill_switch_active"))
        gates.append(
            self._gate(
                gate_name="kill_switch_inactive",
                metric_name="kill_switch_active",
                observed_value=1 if kill_switch_active else 0,
                threshold_value=0,
                comparator="==",
                passed=not kill_switch_active,
                blocking=_bool(blocks_cfg.get("block_if_kill_switch_active")),
                details={"kill_switch_status": (metrics.get("live_safety") or {}).get("kill_switch_status")},
            )
        )

        live_like = stage_name in {_normalize_stage(item) for item in self._promotion_policy().get("live_like_stages", [])}
        if live_like:
            gates.append(
                self._gate(
                    gate_name="snapshot_fresh",
                    metric_name="snapshot_fresh",
                    observed_value=1 if metrics.get("snapshot_fresh") else 0,
                    threshold_value=1,
                    comparator="==",
                    passed=bool(metrics.get("snapshot_fresh")),
                    blocking=_bool(blocks_cfg.get("block_if_snapshot_stale")),
                    details={"live_safety": metrics.get("live_safety") or {}},
                )
            )
            gates.append(
                self._gate(
                    gate_name="fee_source_fresh",
                    metric_name="fee_source_fresh",
                    observed_value=1 if metrics.get("fee_source_fresh") else 0,
                    threshold_value=1,
                    comparator="==",
                    passed=bool(metrics.get("fee_source_fresh")),
                    blocking=_bool(blocks_cfg.get("block_if_fee_source_missing_in_live_like_modes")),
                    details={"live_safety": metrics.get("live_safety") or {}},
                )
            )
            gates.append(
                self._gate(
                    gate_name="margin_guard",
                    metric_name="margin_guard_status",
                    observed_value=None,
                    threshold_value=None,
                    comparator="!= BLOCK",
                    passed=str(metrics.get("margin_guard_status") or "").upper() != "BLOCK",
                    blocking=True,
                    details={"margin_guard_status": metrics.get("margin_guard_status")},
                )
            )
            if stage_name == "CANARY":
                gates.append(
                    self._gate(
                        gate_name="live_safety_blockers_clear",
                        metric_name="safety_blockers_count",
                        observed_value=float(len((metrics.get("live_safety") or {}).get("safety_blockers") or [])),
                        threshold_value=0.0,
                        comparator="==",
                        passed=not bool((metrics.get("live_safety") or {}).get("safety_blockers")),
                        blocking=True,
                        details={
                            "overall_status": (metrics.get("live_safety") or {}).get("overall_status"),
                            "safety_blockers": (metrics.get("live_safety") or {}).get("safety_blockers") or [],
                            "safety_warnings": (metrics.get("live_safety") or {}).get("safety_warnings") or [],
                        },
                    )
                )

        if stage_name == "TESTNET":
            stream_requirements = metrics.get("stream_requirements") or {}
            require_stream = _bool(thresholds.get("require_real_user_data_stream_or_explicit_degraded_mode"))
            stream_ok = bool(stream_requirements.get("available_all")) or bool(stream_requirements.get("explicit_degraded_mode"))
            gates.append(
                self._gate(
                    gate_name="testnet_stream_or_explicit_degraded_mode",
                    metric_name="stream_requirements",
                    observed_value=1 if stream_ok else 0,
                    threshold_value=1 if require_stream else 0,
                    comparator="==",
                    passed=(stream_ok if require_stream else True),
                    blocking=require_stream,
                    details=stream_requirements if isinstance(stream_requirements, dict) else {},
                )
            )

        hold_gates = [
            self._gate(
                gate_name="min_orders",
                metric_name="total_orders",
                observed_value=metrics.get("total_orders"),
                threshold_value=thresholds.get("min_orders"),
                comparator=">=",
                passed=_safe_float(metrics.get("total_orders"), 0.0) >= _safe_float(thresholds.get("min_orders"), 0.0),
                blocking=False,
            )
        ]
        if stage_name == "CANARY":
            hold_gates.append(
                self._gate(
                    gate_name="min_runtime_hours",
                    metric_name="runtime_hours",
                    observed_value=metrics.get("runtime_hours"),
                    threshold_value=thresholds.get("min_runtime_hours"),
                    comparator=">=",
                    passed=_safe_float(metrics.get("runtime_hours"), 0.0) >= _safe_float(thresholds.get("min_runtime_hours"), 0.0),
                    blocking=False,
                )
            )
        else:
            hold_gates.append(
                self._gate(
                    gate_name="min_trading_days",
                    metric_name="trading_days",
                    observed_value=metrics.get("trading_days"),
                    threshold_value=thresholds.get("min_trading_days"),
                    comparator=">=",
                    passed=_safe_float(metrics.get("trading_days"), 0.0) >= _safe_float(thresholds.get("min_trading_days"), 0.0),
                    blocking=False,
                )
            )

        metric_gates = [
            self._gate(
                gate_name="max_unresolved_reconcile_rate",
                metric_name="unresolved_reconcile_rate_pct",
                observed_value=metrics.get("unresolved_reconcile_rate_pct"),
                threshold_value=thresholds.get("max_unresolved_reconcile_rate_pct"),
                comparator="<=",
                passed=_safe_float(metrics.get("unresolved_reconcile_rate_pct"), 0.0)
                <= _safe_float(thresholds.get("max_unresolved_reconcile_rate_pct"), 0.0),
                blocking=True,
            ),
            self._gate(
                gate_name="max_reject_rate",
                metric_name="reject_rate_pct",
                observed_value=metrics.get("reject_rate_pct"),
                threshold_value=thresholds.get("max_reject_rate_pct"),
                comparator="<=",
                passed=_safe_float(metrics.get("reject_rate_pct"), 0.0)
                <= _safe_float(thresholds.get("max_reject_rate_pct"), 0.0),
                blocking=True,
            ),
            self._gate(
                gate_name="max_cost_mismatch_rate",
                metric_name="cost_mismatch_rate_pct",
                observed_value=metrics.get("cost_mismatch_rate_pct"),
                threshold_value=thresholds.get("max_cost_mismatch_rate_pct"),
                comparator="<=",
                passed=_safe_float(metrics.get("cost_mismatch_rate_pct"), 0.0)
                <= _safe_float(thresholds.get("max_cost_mismatch_rate_pct"), 0.0),
                blocking=True,
            ),
            self._gate(
                gate_name="min_fill_coverage",
                metric_name="fill_coverage_pct",
                observed_value=metrics.get("fill_coverage_pct"),
                threshold_value=thresholds.get("min_fill_coverage_pct"),
                comparator=">=",
                passed=_safe_float(metrics.get("fill_coverage_pct"), 0.0)
                >= _safe_float(thresholds.get("min_fill_coverage_pct"), 0.0),
                blocking=True,
            ),
            self._gate(
                gate_name="min_cost_materialization_coverage",
                metric_name="cost_materialization_coverage_pct",
                observed_value=metrics.get("cost_materialization_coverage_pct"),
                threshold_value=thresholds.get("min_cost_materialization_coverage_pct"),
                comparator=">=",
                passed=_safe_float(metrics.get("cost_materialization_coverage_pct"), 0.0)
                >= _safe_float(thresholds.get("min_cost_materialization_coverage_pct"), 0.0),
                blocking=True,
            ),
            self._gate(
                gate_name="min_cancel_success_rate",
                metric_name="cancel_success_rate_pct",
                observed_value=metrics.get("cancel_success_rate_pct"),
                threshold_value=thresholds.get("min_cancel_success_rate_pct"),
                comparator=">=",
                passed=_safe_float(metrics.get("cancel_success_rate_pct"), 0.0)
                >= _safe_float(thresholds.get("min_cancel_success_rate_pct"), 0.0),
                blocking=True,
            ),
            self._gate(
                gate_name="max_gross_net_inconsistency_rate",
                metric_name="gross_net_inconsistency_rate_pct",
                observed_value=metrics.get("gross_net_inconsistency_rate_pct"),
                threshold_value=thresholds.get("max_gross_net_inconsistency_rate_pct"),
                comparator="<=",
                passed=_safe_float(metrics.get("gross_net_inconsistency_rate_pct"), 0.0)
                <= _safe_float(thresholds.get("max_gross_net_inconsistency_rate_pct"), 0.0),
                blocking=True,
            ),
        ]
        if stage_name == "CANARY":
            metric_gates.extend(
                [
                    self._gate(
                        gate_name="max_kill_switch_trips",
                        metric_name="kill_switch_trip_count",
                        observed_value=metrics.get("kill_switch_trip_count"),
                        threshold_value=thresholds.get("max_kill_switch_trips"),
                        comparator="<=",
                        passed=_safe_float(metrics.get("kill_switch_trip_count"), 0.0)
                        <= _safe_float(thresholds.get("max_kill_switch_trips"), 0.0),
                        blocking=True,
                    ),
                    self._gate(
                        gate_name="max_margin_guard_blocks",
                        metric_name="margin_guard_block_count",
                        observed_value=metrics.get("margin_guard_block_count"),
                        threshold_value=thresholds.get("max_margin_guard_blocks"),
                        comparator="<=",
                        passed=_safe_float(metrics.get("margin_guard_block_count"), 0.0)
                        <= _safe_float(thresholds.get("max_margin_guard_blocks"), 0.0),
                        blocking=True,
                    ),
                ]
            )

        gates.extend(hold_gates)
        gates.extend(metric_gates)
        if not bool(gates[0]["passed"]):
            blocking_reasons.append(f"previous_stage_not_passed:{previous_stage}:{previous_result}")
        for row in gates:
            if not row["passed"] and row["blocking"]:
                blocking_reasons.append(str(row["gate_name"]))
        blocking_reasons.extend(str(item) for item in (metrics.get("selection_blockers") or []))

        result = "PASS"
        if any(not row["passed"] and row["blocking"] for row in gates) or metrics.get("selection_blockers"):
            result = "BLOCK"
        elif any(not row["passed"] for row in hold_gates):
            result = "HOLD"
        return gates, result, blocking_reasons, warnings

    def _persist_evidence(self, *, validation_run_id: str, stage: str, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        evidences = [
            {
                "evidence_type": "validation_policy",
                "source": str(self.policy_source().get("source") or "validation_gates"),
                "source_hash": str(self.policy_source().get("source_hash") or ""),
                "payload_json": {
                    "policy_source": self.policy_source(),
                    "stage_definition": self._stage_definition(stage),
                    "stage_thresholds": self._stage_thresholds(stage),
                    "promotion": self._promotion_policy(),
                },
            },
            {
                "evidence_type": "execution_live_safety_summary",
                "source": "execution.live_safety_summary",
                "source_hash": str(self.execution_service.policy_hash() or ""),
                "payload_json": metrics.get("live_safety") or {},
            },
            {
                "evidence_type": "execution_reconcile_summary",
                "source": "execution.reconcile_orders",
                "source_hash": str(self.execution_service.policy_hash() or ""),
                "payload_json": metrics.get("reconcile_summary") or {},
            },
            {
                "evidence_type": "instrument_registry_policy",
                "source": str((self.instrument_registry_service.policy_source() or {}).get("source") or "instrument_registry"),
                "source_hash": str((self.instrument_registry_service.policy_source() or {}).get("source_hash") or ""),
                "payload_json": {
                    "policy_source": self.instrument_registry_service.policy_source(),
                    "live_parity_matrix": self.instrument_registry_service.live_parity_matrix(),
                    "capabilities_summary": self.instrument_registry_service.capabilities_summary(),
                },
            },
            {
                "evidence_type": "reporting_bridge_policy",
                "source": str((((self.reporting_bridge_service.policy_source() or {}).get("cost_stack")) or {}).get("source") or "cost_stack"),
                "source_hash": str((((self.reporting_bridge_service.policy_source() or {}).get("cost_stack")) or {}).get("policy_hash") or ""),
                "payload_json": {"policy_source": self.reporting_bridge_service.policy_source()},
            },
            {
                "evidence_type": "environment_warnings",
                "source": f"validation.stage.{_normalize_stage(stage).lower()}",
                "source_hash": str(self.policy_hash() or ""),
                "payload_json": {
                    "warnings": self._stage_warnings(stage),
                    "stream_requirements": metrics.get("stream_requirements") or {},
                    "families_evaluated": metrics.get("families_evaluated") or [],
                },
            },
        ]
        stored: list[dict[str, Any]] = []
        for row in evidences:
            stored.append(self.db.insert_stage_evidence({"validation_run_id": validation_run_id, **row}))
        return stored

    def evaluate(
        self,
        *,
        stage: str | None = None,
        venue: str = "binance",
        family: str | None = None,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        stage_name = _normalize_stage(stage or self.current_stage())
        if stage_name == "LIVE_SERIO":
            return {
                "ok": False,
                "stage": stage_name,
                "result": "BLOCK",
                "blocking_reasons": ["live_serio_not_evaluated_in_rtlops_36"],
                "readiness": self.readiness(),
                "policy_source": self.policy_source(),
                "policy_hash": self.policy_hash(),
            }

        metrics = self._collect_metrics(stage=stage_name, venue=venue, family=family, symbol=symbol)
        gate_results, result, blocking_reasons, warnings = self._evaluate_gates(stage=stage_name, metrics=metrics)
        run_row = self.db.insert_run(
            {
                "validation_run_id": str(uuid4()),
                "stage": stage_name,
                "venue": venue,
                "family": family,
                "symbol": symbol,
                "mode": metrics.get("mode"),
                "period_start": metrics.get("period_start"),
                "period_end": metrics.get("period_end"),
                "total_orders": metrics.get("total_orders"),
                "total_fills": metrics.get("total_fills"),
                "total_rejects": metrics.get("total_rejects"),
                "unresolved_reconcile_count": metrics.get("unresolved_reconcile_count"),
                "cost_mismatch_count": metrics.get("cost_mismatch_count"),
                "degraded_mode_seen": metrics.get("degraded_mode_seen"),
                "kill_switch_trip_count": metrics.get("kill_switch_trip_count"),
                "margin_guard_block_count": metrics.get("margin_guard_block_count"),
                "gross_pnl": metrics.get("gross_pnl"),
                "net_pnl": metrics.get("net_pnl"),
                "total_cost_realized": metrics.get("total_cost_realized"),
                "source_snapshot_ids_json": metrics.get("source_snapshot_ids") or [],
                "policy_hash": self.policy_hash(),
                "blocking_reasons_json": blocking_reasons,
                "warnings_json": warnings,
                "key_metrics_json": {
                    key: metrics.get(key)
                    for key in (
                        "trading_days",
                        "runtime_hours",
                        "unresolved_reconcile_rate_pct",
                        "reject_rate_pct",
                        "cost_mismatch_rate_pct",
                        "fill_coverage_pct",
                        "cost_materialization_coverage_pct",
                        "cancel_success_rate_pct",
                        "gross_net_inconsistency_rate_pct",
                        "kill_switch_active",
                        "snapshot_fresh",
                        "fee_source_fresh",
                        "margin_guard_status",
                        "overall_safety_status",
                        "degraded_mode_seen",
                    )
                },
                "result": result,
            }
        )
        for gate in gate_results:
            self.db.insert_gate_result({"validation_run_id": run_row["validation_run_id"], **gate})
        self._persist_evidence(validation_run_id=str(run_row["validation_run_id"]), stage=stage_name, metrics=metrics)
        return self.run_detail(str(run_row["validation_run_id"])) or {
            "validation_run": run_row,
            "gate_results": gate_results,
            "stage_evidence": [],
            "policy_source": self.policy_source(),
            "policy_hash": self.policy_hash(),
        }

    def run_detail(self, validation_run_id: str) -> dict[str, Any] | None:
        run = self.db.run_by_id(validation_run_id)
        if run is None:
            return None
        return {
            "validation_run": run,
            "gate_results": self.db.gate_results_for_run(validation_run_id),
            "stage_evidence": self.db.stage_evidence_for_run(validation_run_id),
            "policy_source": self.policy_source(),
            "policy_hash": self.policy_hash(),
        }

    def runs(self, *, limit: int = 100, offset: int = 0, stage: str | None = None, result: str | None = None) -> dict[str, Any]:
        rows = self.db.list_runs(stage=stage, result=result, limit=limit, offset=offset)
        return {
            "items": rows,
            "count": len(self.db.list_runs(stage=stage, result=result, limit=100000, offset=0)),
            "limit": max(1, int(limit)),
            "offset": max(0, int(offset)),
            "policy_source": self.policy_source(),
            "policy_hash": self.policy_hash(),
        }

    def readiness(self) -> dict[str, Any]:
        readiness_by_stage: dict[str, Any] = {}
        order = [_normalize_stage(item) for item in self._promotion_policy().get("order", list(VALIDATION_STAGES))]
        pass_chain = True
        for stage in order:
            latest = self.db.latest_run(stage=stage)
            latest_result = str((latest or {}).get("result") or "") or None
            latest_reasons = list((latest or {}).get("blocking_reasons_json") or []) if isinstance(latest, dict) else []
            ready = bool(pass_chain and latest_result == "PASS")
            if stage == "LIVE_SERIO":
                ready = bool(pass_chain)
            readiness_by_stage[stage.lower()] = {
                "latest_result": latest_result,
                "ready": ready,
                "validation_run_id": (latest or {}).get("validation_run_id") if isinstance(latest, dict) else None,
                "blocking_reasons": latest_reasons,
                "warnings": list((latest or {}).get("warnings_json") or []) if isinstance(latest, dict) else [],
            }
            if stage != "LIVE_SERIO":
                pass_chain = pass_chain and latest_result == "PASS"
        return {
            "readiness_by_stage": readiness_by_stage,
            "live_serio_ready": bool(readiness_by_stage.get("live_serio", {}).get("ready")),
            "policy_source": self.policy_source(),
            "policy_hash": self.policy_hash(),
        }

    def current_stage(self) -> str:
        readiness = self.readiness().get("readiness_by_stage") or {}
        for stage in ("paper", "testnet", "canary"):
            if not _bool((readiness.get(stage) or {}).get("ready")):
                return stage.upper()
        return "LIVE_SERIO"

    def summary(self) -> dict[str, Any]:
        latest_runs = self.db.list_runs(limit=1, offset=0)
        latest = latest_runs[0] if latest_runs else None
        readiness = self.readiness()
        current_stage = self.current_stage()
        current_payload = (readiness.get("readiness_by_stage") or {}).get(current_stage.lower(), {})
        return {
            "stage_actual": current_stage,
            "latest_result": (latest or {}).get("result") if isinstance(latest, dict) else None,
            "readiness_by_stage": readiness.get("readiness_by_stage"),
            "live_serio_ready": readiness.get("live_serio_ready"),
            "blocking_reasons": current_payload.get("blocking_reasons") or [],
            "key_metrics": (latest or {}).get("key_metrics_json") if isinstance(latest, dict) else {},
            "policy_source": self.policy_source(),
            "policy_hash": self.policy_hash(),
            "warnings": current_payload.get("warnings") or [],
        }

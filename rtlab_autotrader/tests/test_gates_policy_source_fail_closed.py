from __future__ import annotations

from pathlib import Path

from rtlab_core.learning.service import LearningService
from rtlab_core.rollout.gates import GateEvaluator


def _candidate_report() -> dict:
  return {
    "id": "run_candidate",
    "strategy_id": "s1",
    "timeframe": "5m",
    "data_source": "binance_public",
    "dataset_hash": "abc123",
    "validation_mode": "walk-forward",
    "validation_summary": {"mode": "walk-forward", "implemented": True},
    "metrics": {
      "trade_count": 220,
      "winrate": 0.54,
      "profit_factor": 1.4,
      "sharpe": 1.5,
      "sortino": 2.0,
      "calmar": 1.2,
      "max_dd": 0.12,
      "max_dd_duration_bars": 5000,
      "pbo": 0.03,
      "dsr": 1.02,
    },
    "costs_breakdown": {
      "gross_pnl_total": 2000.0,
      "fees_total": 180.0,
      "spread_total": 120.0,
      "slippage_total": 90.0,
      "funding_total": 30.0,
      "total_cost": 420.0,
      "gross_pnl": 2000.0,
    },
  }


def test_learning_service_gates_thresholds_fail_closed_without_config(tmp_path: Path) -> None:
  service = LearningService(user_data_dir=tmp_path / "user_data", repo_root=tmp_path)
  thresholds = service._canonical_gates_thresholds()
  assert thresholds["source"] == "config/policies/gates.yaml:default_fail_closed"
  assert float(thresholds["pbo_max"]) == 0.05
  assert float(thresholds["dsr_min"]) == 0.95


def test_gate_evaluator_requires_pbo_dsr_when_config_missing(tmp_path: Path) -> None:
  evaluator = GateEvaluator(repo_root=tmp_path)
  run = _candidate_report()
  run["metrics"]["pbo"] = None
  run["metrics"]["dsr"] = None

  result = evaluator.evaluate(run)

  assert result["thresholds"]["source_mode"] == "default_fail_closed"
  source_path = str(result["thresholds"]["source_path"]).replace("\\", "/")
  assert source_path.endswith("config/policies/gates.yaml")
  failed_ids = set(result["failed_ids"])
  assert "pbo_max" in failed_ids
  assert "dsr_min" in failed_ids

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rtlab_core.rollout import CompareEngine, GateEvaluator, RolloutManager

from test_web_live_ready import _auth_headers, _build_app, _login


def _sample_run(*, run_id: str, strategy_id: str, dataset_hash: str = "abc123", net_pnl: float = 1200.0) -> dict:
  gross = 2000.0
  total_cost = gross - net_pnl
  return {
    "id": run_id,
    "strategy_id": strategy_id,
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "data_source": "binance_public",
    "dataset_hash": dataset_hash,
    "period": {"start": "2024-01-01", "end": "2024-12-31"},
    "validation_mode": "walk-forward",
    "validation_summary": {"mode": "walk-forward", "implemented": True},
    "metrics": {
      "trade_count": 200,
      "winrate": 0.53,
      "profit_factor": 1.35,
      "sharpe": 1.55,
      "sortino": 2.1,
      "calmar": 1.2,
      "max_dd": 0.12,
      "max_dd_duration_bars": 5000,
      "expectancy": 12.0,
      "expectancy_usd_per_trade": 12.0,
      "pbo": None,
      "dsr": None,
    },
    "costs_breakdown": {
      "gross_pnl_total": gross,
      "gross_pnl": gross,
      "fees_total": 180.0,
      "spread_total": 140.0,
      "slippage_total": 120.0,
      "funding_total": 40.0,
      "rollover_total": 0.0,
      "total_cost": total_cost,
      "net_pnl_total": net_pnl,
      "net_pnl": net_pnl,
    },
  }


def test_gate_evaluator_with_knowledge_gates_defaults_pass_and_fail() -> None:
  repo_root = Path(__file__).resolve().parents[2]
  evaluator = GateEvaluator(repo_root=repo_root)
  good = _sample_run(run_id="run_good", strategy_id="s1")
  res_good = evaluator.evaluate(good)
  assert res_good["passed"] is True, res_good

  bad = copy.deepcopy(good)
  bad["data_source"] = "synthetic"
  bad["metrics"]["trade_count"] = 20
  bad["metrics"]["sharpe"] = 0.4
  res_bad = evaluator.evaluate(bad)
  assert res_bad["passed"] is False
  failed_ids = set(res_bad["failed_ids"])
  assert "real_data" in failed_ids
  assert "min_trades_oos" in failed_ids
  assert "min_sharpe_oos" in failed_ids


def test_compare_engine_improvement_rules() -> None:
  baseline = _sample_run(run_id="run_b", strategy_id="s_base", dataset_hash="samehash", net_pnl=1000.0)
  baseline["metrics"]["expectancy_usd_per_trade"] = 10.0
  baseline["metrics"]["max_dd"] = 0.11
  baseline["costs_breakdown"]["total_cost"] = 500.0

  candidate = _sample_run(run_id="run_c", strategy_id="s_cand", dataset_hash="samehash", net_pnl=1120.0)
  candidate["metrics"]["expectancy_usd_per_trade"] = 10.7
  candidate["metrics"]["max_dd"] = 0.12
  candidate["costs_breakdown"]["total_cost"] = 530.0

  compare = CompareEngine()
  ok = compare.compare(baseline, candidate)
  assert ok["passed"] is True, ok

  worse = copy.deepcopy(candidate)
  worse["dataset_hash"] = "other"
  worse["metrics"]["expectancy_usd_per_trade"] = 9.0
  worse["costs_breakdown"]["total_cost"] = 900.0
  fail = compare.compare(baseline, worse)
  assert fail["passed"] is False
  assert {"same_dataset_hash", "improve_expectancy_or_net_pnl", "cost_increase_limit"} & set(fail["failed_ids"])


def test_rollout_manager_transitions_and_rollback(tmp_path: Path) -> None:
  manager = RolloutManager(user_data_dir=tmp_path)
  baseline = _sample_run(run_id="run_b", strategy_id="s_base")
  candidate = _sample_run(run_id="run_c", strategy_id="s_cand", net_pnl=1300.0)
  state = manager.start_offline(
    baseline_run=baseline,
    candidate_run=candidate,
    baseline_strategy={"name": "Base", "version": "1.0.0"},
    candidate_strategy={"name": "Cand", "version": "1.1.0"},
    gates_result={"passed": True, "failed_ids": [], "checks": []},
    compare_result={"passed": True, "failed_ids": [], "checks": []},
    actor="tester",
  )
  assert state["state"] == "OFFLINE_GATES_PASSED"
  assert state["weights"]["baseline_pct"] == 100
  assert Path(state["artifacts"]["candidate_report"]).exists()

  state = manager.advance(actor="tester")
  assert state["state"] == "PAPER_SOAK"
  # No permite avanzar sin aprobar PAPER_SOAK.
  try:
    manager.advance(actor="tester")
    assert False, "advance debía fallar sin evaluacion de paper"
  except ValueError:
    pass
  manager.set_phase_started_at("paper_soak", (datetime.now(timezone.utc) - timedelta(days=15)).isoformat())
  state = manager.evaluate_paper_soak(
    settings={
      "rollout": {"paper_soak_days": 14},
      "learning": {"risk_profile": {"paper": {"max_daily_loss_pct": 3, "max_drawdown_pct": 15}}},
      "execution": {"slippage_max_bps": 12},
    },
    status_payload={"daily_loss": {"value": -0.01}, "max_dd": {"value": -0.05}},
    execution_payload={"p95_slippage": 7.0},
    logs=[],
    auto_abort=True,
  )
  assert state["phase_evaluations"]["paper_soak"]["passed"] is True
  state = manager.advance(actor="tester")
  assert state["state"] == "TESTNET_SOAK"
  state = manager.rollback(reason="abort threshold", actor="tester", auto=True)
  assert state["state"] == "ROLLED_BACK"
  assert state["weights"]["baseline_pct"] == 100
  assert state["weights"]["candidate_pct"] == 0


def test_rollout_manager_paper_soak_fail_auto_aborts(tmp_path: Path) -> None:
  manager = RolloutManager(user_data_dir=tmp_path)
  baseline = _sample_run(run_id="run_b", strategy_id="s_base")
  candidate = _sample_run(run_id="run_c", strategy_id="s_cand", net_pnl=1300.0)
  state = manager.start_offline(
    baseline_run=baseline,
    candidate_run=candidate,
    baseline_strategy={"name": "Base", "version": "1.0.0"},
    candidate_strategy={"name": "Cand", "version": "1.1.0"},
    gates_result={"passed": True, "failed_ids": [], "checks": []},
    compare_result={"passed": True, "failed_ids": [], "checks": []},
    actor="tester",
  )
  assert state["state"] == "OFFLINE_GATES_PASSED"
  state = manager.advance(actor="tester")
  assert state["state"] == "PAPER_SOAK"
  manager.set_phase_started_at("paper_soak", (datetime.now(timezone.utc) - timedelta(days=15)).isoformat())
  state = manager.evaluate_paper_soak(
    settings={
      "rollout": {"paper_soak_days": 14},
      "learning": {"risk_profile": {"paper": {"max_daily_loss_pct": 3, "max_drawdown_pct": 15}}},
      "execution": {"slippage_max_bps": 12},
    },
    status_payload={"daily_loss": {"value": -0.06}, "max_dd": {"value": -0.20}},
    execution_payload={"p95_slippage": 25.0},
    logs=[{"severity": "error", "module": "execution", "message": "critical", "type": "api_error"}],
    auto_abort=True,
  )
  assert state["state"] == "ABORTED"
  assert "PAPER_SOAK failed" in str(state.get("abort_reason"))


def test_rollout_manager_testnet_soak_pass_and_fail(tmp_path: Path) -> None:
  manager = RolloutManager(user_data_dir=tmp_path)
  baseline = _sample_run(run_id="run_b", strategy_id="s_base")
  candidate = _sample_run(run_id="run_c", strategy_id="s_cand", net_pnl=1300.0)
  state = manager.start_offline(
    baseline_run=baseline,
    candidate_run=candidate,
    baseline_strategy={"name": "Base", "version": "1.0.0"},
    candidate_strategy={"name": "Cand", "version": "1.1.0"},
    gates_result={"passed": True, "failed_ids": [], "checks": []},
    compare_result={"passed": True, "failed_ids": [], "checks": []},
    actor="tester",
  )
  assert state["state"] == "OFFLINE_GATES_PASSED"
  state = manager.advance(actor="tester")
  assert state["state"] == "PAPER_SOAK"
  manager.set_phase_started_at("paper_soak", (datetime.now(timezone.utc) - timedelta(days=15)).isoformat())
  state = manager.evaluate_paper_soak(
    settings={
      "rollout": {"paper_soak_days": 14},
      "learning": {"risk_profile": {"paper": {"max_daily_loss_pct": 3, "max_drawdown_pct": 15}}},
      "execution": {"slippage_max_bps": 12},
    },
    status_payload={"daily_loss": {"value": -0.01}, "max_dd": {"value": -0.05}},
    execution_payload={"p95_slippage": 7.0},
    logs=[],
    auto_abort=True,
  )
  assert state["phase_evaluations"]["paper_soak"]["passed"] is True
  state = manager.advance(actor="tester")
  assert state["state"] == "TESTNET_SOAK"

  manager.set_phase_started_at("testnet_soak", (datetime.now(timezone.utc) - timedelta(days=8)).isoformat())
  state = manager.evaluate_testnet_soak(
    settings={"rollout": {"testnet_soak_days": 7, "testnet_checks": {"fill_ratio_min": 0.3, "api_error_rate_24h_max": 0.02, "latency_p95_ms_max": 250}}},
    execution_payload={"fill_ratio": 0.81, "latency_ms_p95": 140.0, "api_errors": 1, "requests_24h_estimate": 400},
    diagnose_payload={"connector_ok": True, "order_ok": True, "mode": "testnet", "exchange": "binance"},
    logs=[],
    auto_abort=True,
  )
  assert state["state"] == "TESTNET_SOAK"
  assert state["phase_evaluations"]["testnet_soak"]["passed"] is True
  state = manager.advance(actor="tester")
  assert state["state"] == "PENDING_LIVE_APPROVAL"

  # Caso fail duro: place/cancel no OK + error rate alto => ABORTED.
  manager_fail = RolloutManager(user_data_dir=tmp_path / "fail_case")
  state = manager_fail.start_offline(
    baseline_run=baseline,
    candidate_run=candidate,
    baseline_strategy={"name": "Base", "version": "1.0.0"},
    candidate_strategy={"name": "Cand", "version": "1.1.0"},
    gates_result={"passed": True, "failed_ids": [], "checks": []},
    compare_result={"passed": True, "failed_ids": [], "checks": []},
    actor="tester",
  )
  state = manager_fail.advance(actor="tester")
  manager_fail.set_phase_started_at("paper_soak", (datetime.now(timezone.utc) - timedelta(days=15)).isoformat())
  state = manager_fail.evaluate_paper_soak(
    settings={
      "rollout": {"paper_soak_days": 14},
      "learning": {"risk_profile": {"paper": {"max_daily_loss_pct": 3, "max_drawdown_pct": 15}}},
      "execution": {"slippage_max_bps": 12},
    },
    status_payload={"daily_loss": {"value": -0.01}, "max_dd": {"value": -0.05}},
    execution_payload={"p95_slippage": 7.0},
    logs=[],
    auto_abort=True,
  )
  assert state["phase_evaluations"]["paper_soak"]["passed"] is True
  state = manager_fail.advance(actor="tester")
  assert state["state"] == "TESTNET_SOAK"
  manager_fail.set_phase_started_at("testnet_soak", (datetime.now(timezone.utc) - timedelta(days=8)).isoformat())
  state = manager_fail.evaluate_testnet_soak(
    settings={"rollout": {"testnet_soak_days": 7}},
    execution_payload={"fill_ratio": 0.1, "latency_ms_p95": 500.0, "api_errors": 25, "requests_24h_estimate": 100},
    diagnose_payload={"connector_ok": False, "order_ok": False, "mode": "testnet", "exchange": "binance"},
    logs=[{"severity": "error", "module": "exchange", "type": "api_error"}],
    auto_abort=True,
  )
  assert state["state"] == "ABORTED"
  assert "TESTNET_SOAK failed" in str(state.get("abort_reason"))


def test_rollout_manager_live_canary_auto_rollback(tmp_path: Path) -> None:
  manager = RolloutManager(user_data_dir=tmp_path)
  settings = {"rollout": RolloutManager.default_rollout_config(), "blending": RolloutManager.default_blending_config()}
  baseline = _sample_run(run_id="run_b", strategy_id="s_base")
  candidate = _sample_run(run_id="run_c", strategy_id="s_cand", net_pnl=1300.0)
  baseline["metrics"]["expectancy_usd_per_trade"] = 10.0
  candidate["metrics"]["expectancy_usd_per_trade"] = 12.0
  state = manager.start_offline(
    baseline_run=baseline,
    candidate_run=candidate,
    baseline_strategy={"name": "Base", "version": "1.0.0"},
    candidate_strategy={"name": "Cand", "version": "1.1.0"},
    gates_result={"passed": True, "failed_ids": [], "checks": []},
    compare_result={"passed": True, "failed_ids": [], "checks": []},
    actor="tester",
  )
  assert state["state"] == "OFFLINE_GATES_PASSED"
  state = manager.advance(actor="tester", settings=settings)
  assert state["state"] == "PAPER_SOAK"
  manager.set_phase_started_at("paper_soak", (datetime.now(timezone.utc) - timedelta(days=15)).isoformat())
  state = manager.evaluate_paper_soak(
    settings={
      "rollout": {"paper_soak_days": 14},
      "learning": {"risk_profile": {"paper": {"max_daily_loss_pct": 3, "max_drawdown_pct": 15}}},
      "execution": {"slippage_max_bps": 12},
    },
    status_payload={"daily_loss": {"value": -0.01}, "max_dd": {"value": -0.05}},
    execution_payload={"p95_slippage": 7.0},
    logs=[],
    auto_abort=True,
  )
  assert state["phase_evaluations"]["paper_soak"]["passed"] is True
  state = manager.advance(actor="tester", settings=settings)
  assert state["state"] == "TESTNET_SOAK"
  manager.set_phase_started_at("testnet_soak", (datetime.now(timezone.utc) - timedelta(days=8)).isoformat())
  state = manager.evaluate_testnet_soak(
    settings={"rollout": {"testnet_soak_days": 7}},
    execution_payload={"fill_ratio": 0.9, "latency_ms_p95": 140.0, "api_errors": 0, "requests_24h_estimate": 400},
    diagnose_payload={"connector_ok": True, "order_ok": True, "mode": "testnet", "exchange": "binance"},
    logs=[],
    auto_abort=True,
  )
  assert state["phase_evaluations"]["testnet_soak"]["passed"] is True
  state = manager.advance(actor="tester", settings=settings)
  assert state["state"] == "PENDING_LIVE_APPROVAL"
  state = manager.approve(actor="tester", settings=settings)
  assert state["state"] == "LIVE_SHADOW"
  assert state["routing"]["shadow_only"] is True

  manager.set_phase_started_at("shadow", (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat())
  state = manager.evaluate_live_phase(
    settings=settings,
    status_payload={"daily_pnl": 4.0, "phase_dd_increment_pct": 0.2, "max_dd": {"value": -0.01}},
    execution_payload={"p95_slippage": 6.0, "p95_spread": 10.0, "latency_ms_p95": 110.0, "api_errors": 0, "requests_24h_estimate": 300, "series": [1]},
    logs=[],
    auto_rollback=True,
  )
  assert state["phase_evaluations"]["shadow"]["passed"] is True
  state = manager.advance(actor="tester", settings=settings)
  assert state["state"] == "LIVE_CANARY_05"
  assert state["weights"]["candidate_pct"] == 5

  manager.set_phase_started_at("canary05", (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat())
  state = manager.evaluate_live_phase(
    settings=settings,
    status_payload={"daily_pnl": 5.0, "phase_dd_increment_pct": 0.4, "max_dd": {"value": -0.02}},
    execution_payload={"p95_slippage": 7.0, "p95_spread": 11.0, "latency_ms_p95": 120.0, "api_errors": 0, "requests_24h_estimate": 300, "series": [1]},
    logs=[],
    auto_rollback=True,
  )
  assert state["phase_evaluations"]["canary05"]["passed"] is True
  state = manager.advance(actor="tester", settings=settings)
  assert state["state"] == "LIVE_CANARY_15"
  assert state["weights"]["candidate_pct"] == 15

  manager.set_phase_started_at("canary15", (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat())
  state = manager.evaluate_live_phase(
    settings=settings,
    status_payload={"daily_pnl": -25.0, "expectancy_24h_usd": -8.0, "phase_dd_increment_pct": 2.6, "max_dd": {"value": -0.05}},
    execution_payload={"p95_slippage": 26.0, "p95_spread": 18.0, "latency_ms_p95": 170.0, "api_errors": 5, "requests_24h_estimate": 100, "series": [1]},
    logs=[{"type": "breaker_triggered", "severity": "error", "module": "execution"} for _ in range(3)],
    auto_rollback=True,
  )
  assert state["state"] == "ROLLED_BACK"
  assert state["weights"]["baseline_pct"] == 100
  assert state["weights"]["candidate_pct"] == 0
  assert state["rollback_snapshot"]["auto"] is True


def test_rollout_manager_blending_hook_and_telemetry(tmp_path: Path) -> None:
  manager = RolloutManager(user_data_dir=tmp_path)
  settings = {"rollout": RolloutManager.default_rollout_config(), "blending": RolloutManager.default_blending_config()}
  baseline = _sample_run(run_id="run_b", strategy_id="s_base")
  candidate = _sample_run(run_id="run_c", strategy_id="s_cand", net_pnl=1300.0)
  baseline["metrics"]["expectancy_usd_per_trade"] = 10.0
  candidate["metrics"]["expectancy_usd_per_trade"] = 12.0
  state = manager.start_offline(
    baseline_run=baseline,
    candidate_run=candidate,
    baseline_strategy={"name": "Base", "version": "1.0.0"},
    candidate_strategy={"name": "Cand", "version": "1.1.0"},
    gates_result={"passed": True, "failed_ids": [], "checks": []},
    compare_result={"passed": True, "failed_ids": [], "checks": []},
    actor="tester",
  )
  assert state["state"] == "OFFLINE_GATES_PASSED"
  state = manager.advance(actor="tester", settings=settings)
  manager.set_phase_started_at("paper_soak", (datetime.now(timezone.utc) - timedelta(days=15)).isoformat())
  state = manager.evaluate_paper_soak(
    settings={"rollout": {"paper_soak_days": 14}, "learning": {"risk_profile": {"paper": {"max_daily_loss_pct": 3, "max_drawdown_pct": 15}}}, "execution": {"slippage_max_bps": 12}},
    status_payload={"daily_loss": {"value": -0.01}, "max_dd": {"value": -0.05}},
    execution_payload={"p95_slippage": 7.0},
    logs=[],
    auto_abort=True,
  )
  assert state["phase_evaluations"]["paper_soak"]["passed"] is True
  state = manager.advance(actor="tester", settings=settings)
  manager.set_phase_started_at("testnet_soak", (datetime.now(timezone.utc) - timedelta(days=8)).isoformat())
  state = manager.evaluate_testnet_soak(
    settings={"rollout": {"testnet_soak_days": 7}},
    execution_payload={"fill_ratio": 0.9, "latency_ms_p95": 120.0, "api_errors": 0, "requests_24h_estimate": 400},
    diagnose_payload={"connector_ok": True, "order_ok": True, "mode": "testnet", "exchange": "binance"},
    logs=[],
    auto_abort=True,
  )
  assert state["phase_evaluations"]["testnet_soak"]["passed"] is True
  state = manager.advance(actor="tester", settings=settings)
  state = manager.approve(actor="tester", settings=settings)
  assert state["state"] == "LIVE_SHADOW"

  # Consenso en shadow: mismatch => blended flat, pero ejecutado sigue baseline por shadow.
  routed_shadow = manager.route_live_signal(
    settings=settings,
    baseline_signal={"action": "long", "confidence": 0.8},
    candidate_signal={"action": "short", "confidence": 0.9},
    symbol="BTCUSDT",
    timeframe="5m",
    record_telemetry=True,
  )
  event_shadow = routed_shadow["event"]
  assert event_shadow["phase"] == "shadow"
  assert event_shadow["decisions"]["blended"]["action"] == "flat"
  assert event_shadow["decisions"]["executed"]["action"] == "long"
  assert event_shadow["decisions"]["executed"]["shadow_only"] is True
  telemetry_shadow = routed_shadow["telemetry"]
  assert telemetry_shadow["phases"]["shadow"]["events"] >= 1
  assert telemetry_shadow["phases"]["shadow"]["action_counts"]["baseline"]["long"] >= 1
  assert telemetry_shadow["phases"]["shadow"]["action_counts"]["candidate"]["short"] >= 1
  assert telemetry_shadow["phases"]["shadow"]["action_counts"]["blended"]["flat"] >= 1

  # Pasar a canary05 y usar blending ponderado.
  manager.set_phase_started_at("shadow", (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat())
  state = manager.evaluate_live_phase(
    settings=settings,
    status_payload={"daily_pnl": 6.0, "phase_dd_increment_pct": 0.3, "max_dd": {"value": -0.02}},
    execution_payload={"p95_slippage": 6.0, "p95_spread": 10.0, "latency_ms_p95": 120.0, "api_errors": 0, "requests_24h_estimate": 300, "series": [1]},
    logs=[],
    auto_rollback=True,
  )
  assert state["phase_evaluations"]["shadow"]["passed"] is True
  state = manager.advance(actor="tester", settings=settings)
  assert state["state"] == "LIVE_CANARY_05"

  weighted_settings = {
    **settings,
    "blending": {"enabled": True, "mode": "ponderado", "alpha": 0.7},
  }
  routed_canary = manager.route_live_signal(
    settings=weighted_settings,
    baseline_signal={"action": "short", "score": -0.4},
    candidate_signal={"action": "long", "score": 0.9},
    symbol="BTCUSDT",
    timeframe="5m",
    record_telemetry=True,
  )
  event_canary = routed_canary["event"]
  assert event_canary["phase"] == "canary05"
  assert event_canary["blending"]["mode"] == "ponderado"
  assert event_canary["decisions"]["blended"]["action"] == "long"
  assert event_canary["decisions"]["executed"]["action"] == "long"
  assert event_canary["decisions"]["executed"]["shadow_only"] is False
  telemetry_canary = routed_canary["telemetry"]
  assert telemetry_canary["phases"]["canary05"]["events"] >= 1
  assert telemetry_canary["last_decision"]["phase"] == "canary05"


def test_rollout_api_canary15_manual_rollback_e2e(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  # Crear estrategia candidata (YAML) para tener strategy_id distinto al baseline.
  yaml_payload = """
id: rollout_candidate_strategy
name: Rollout Candidate
version: 1.0.0
defaults:
  risk_per_trade_pct: 0.5
""".strip()
  upload = client.post(
    "/api/v1/strategies/upload",
    headers=headers,
    files={"file": ("rollout_candidate_strategy.yaml", yaml_payload.encode("utf-8"), "application/x-yaml")},
  )
  assert upload.status_code == 200, upload.text

  runs = module.store.load_runs()
  assert runs, "seed run esperado"
  baseline_run = copy.deepcopy(runs[0])
  baseline_run["id"] = "run_baseline_rollout"
  baseline_run["strategy_id"] = "trend_pullback_orderflow_confirm_v1"
  baseline_run["market"] = "crypto"
  baseline_run["symbol"] = "BTCUSDT"
  baseline_run["timeframe"] = "5m"
  baseline_run["data_source"] = "binance_public"
  baseline_run["validation_mode"] = "walk-forward"
  baseline_run["validation_summary"] = {"mode": "walk-forward", "implemented": True}
  baseline_run["dataset_hash"] = "same_dataset_rollout"
  baseline_run["period"] = {"start": "2024-01-01", "end": "2024-12-31"}
  baseline_run["metrics"].update(
    {
      "trade_count": 200,
      "winrate": 0.50,
      "profit_factor": 1.25,
      "sharpe": 1.30,
      "sortino": 1.80,
      "calmar": 1.05,
      "max_dd": 0.12,
      "max_dd_duration_bars": 5000,
      "expectancy": 10.0,
      "expectancy_usd_per_trade": 10.0,
    }
  )
  baseline_run["costs_breakdown"].update({"gross_pnl_total": 2000.0, "total_cost": 600.0, "net_pnl_total": 1400.0, "net_pnl": 1400.0})

  candidate_run = copy.deepcopy(baseline_run)
  candidate_run["id"] = "run_candidate_rollout"
  candidate_run["strategy_id"] = "rollout_candidate_strategy"
  candidate_run["metrics"].update(
    {
      "winrate": 0.54,
      "profit_factor": 1.35,
      "sharpe": 1.55,
      "sortino": 2.10,
      "calmar": 1.25,
      "max_dd": 0.13,
      "expectancy": 11.2,
      "expectancy_usd_per_trade": 11.2,
    }
  )
  candidate_run["costs_breakdown"].update({"gross_pnl_total": 2150.0, "total_cost": 630.0, "net_pnl_total": 1520.0, "net_pnl": 1520.0})

  module.store.save_runs([candidate_run, baseline_run, *runs])

  start = client.post(
    "/api/v1/rollout/start",
    headers=headers,
    json={"candidate_run_id": "run_candidate_rollout", "baseline_run_id": "run_baseline_rollout"},
  )
  assert start.status_code == 200, start.text
  assert start.json()["state"]["state"] == "OFFLINE_GATES_PASSED"

  adv = client.post("/api/v1/rollout/advance", headers=headers, json={})
  assert adv.status_code == 200, adv.text
  assert adv.json()["state"]["state"] == "PAPER_SOAK"
  old_start = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
  eval_res = client.post(
    "/api/v1/rollout/evaluate-phase",
    headers=headers,
    json={"phase": "paper_soak", "override_started_at": old_start, "auto_advance": True},
  )
  assert eval_res.status_code == 200, eval_res.text
  assert eval_res.json()["state"]["state"] == "TESTNET_SOAK"
  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "ok": True,
      "mode": mode,
      "exchange": "binance",
      "connector_ok": True,
      "connector_reason": "ok",
      "order_ok": True,
      "order_reason": "ok",
    },
  )
  old_testnet_start = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
  eval_testnet = client.post(
    "/api/v1/rollout/evaluate-phase",
    headers=headers,
    json={"phase": "testnet_soak", "override_started_at": old_testnet_start, "auto_advance": True},
  )
  assert eval_testnet.status_code == 200, eval_testnet.text
  assert eval_testnet.json()["evaluation"]["passed"] is True
  assert eval_testnet.json()["state"]["state"] == "PENDING_LIVE_APPROVAL"

  approve = client.post("/api/v1/rollout/approve", headers=headers, json={"reason": "ok"})
  assert approve.status_code == 200, approve.text
  assert approve.json()["state"]["state"] == "LIVE_SHADOW"
  assert approve.json()["state"]["routing"]["shadow_only"] is True

  old_shadow_start = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
  eval_shadow = client.post(
    "/api/v1/rollout/evaluate-phase",
    headers=headers,
    json={"phase": "shadow", "override_started_at": old_shadow_start, "auto_advance": True},
  )
  assert eval_shadow.status_code == 200, eval_shadow.text
  assert eval_shadow.json()["evaluation"]["passed"] is True
  assert eval_shadow.json()["state"]["state"] == "LIVE_CANARY_05"

  old_canary05_start = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
  eval_canary05 = client.post(
    "/api/v1/rollout/evaluate-phase",
    headers=headers,
    json={"phase": "canary05", "override_started_at": old_canary05_start, "auto_advance": True},
  )
  assert eval_canary05.status_code == 200, eval_canary05.text
  assert eval_canary05.json()["evaluation"]["passed"] is True
  assert eval_canary05.json()["state"]["state"] == "LIVE_CANARY_15"

  rollback = client.post("/api/v1/rollout/rollback", headers=headers, json={"reason": "falla simulada canary15"})
  assert rollback.status_code == 200, rollback.text
  payload = rollback.json()["state"]
  assert payload["state"] == "ROLLED_BACK"
  assert payload["weights"]["baseline_pct"] == 100
  assert payload["weights"]["candidate_pct"] == 0


def test_rollout_api_paper_soak_evaluate_and_auto_advance(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  yaml_payload = """
id: rollout_candidate_strategy_2
name: Rollout Candidate 2
version: 1.0.0
defaults:
  risk_per_trade_pct: 0.5
""".strip()
  upload = client.post(
    "/api/v1/strategies/upload",
    headers=headers,
    files={"file": ("rollout_candidate_strategy_2.yaml", yaml_payload.encode("utf-8"), "application/x-yaml")},
  )
  assert upload.status_code == 200, upload.text

  runs = module.store.load_runs()
  baseline_run = copy.deepcopy(runs[0])
  baseline_run["id"] = "run_baseline_rollout_2"
  baseline_run["strategy_id"] = "trend_pullback_orderflow_confirm_v1"
  baseline_run["market"] = "crypto"
  baseline_run["symbol"] = "BTCUSDT"
  baseline_run["timeframe"] = "5m"
  baseline_run["data_source"] = "binance_public"
  baseline_run["validation_mode"] = "walk-forward"
  baseline_run["validation_summary"] = {"mode": "walk-forward", "implemented": True}
  baseline_run["dataset_hash"] = "same_dataset_rollout_2"
  baseline_run["period"] = {"start": "2024-01-01", "end": "2024-12-31"}
  baseline_run["metrics"].update({"trade_count": 200, "winrate": 0.50, "profit_factor": 1.25, "sharpe": 1.30, "sortino": 1.80, "calmar": 1.05, "max_dd": 0.12, "max_dd_duration_bars": 5000, "expectancy_usd_per_trade": 10.0})
  baseline_run["costs_breakdown"].update({"gross_pnl_total": 2000.0, "total_cost": 600.0, "net_pnl_total": 1400.0, "net_pnl": 1400.0})
  candidate_run = copy.deepcopy(baseline_run)
  candidate_run["id"] = "run_candidate_rollout_2"
  candidate_run["strategy_id"] = "rollout_candidate_strategy_2"
  candidate_run["metrics"].update({"winrate": 0.54, "profit_factor": 1.35, "sharpe": 1.55, "sortino": 2.10, "calmar": 1.25, "max_dd": 0.13, "expectancy_usd_per_trade": 11.0})
  candidate_run["costs_breakdown"].update({"gross_pnl_total": 2150.0, "total_cost": 630.0, "net_pnl_total": 1520.0, "net_pnl": 1520.0})
  module.store.save_runs([candidate_run, baseline_run, *runs])

  start = client.post("/api/v1/rollout/start", headers=headers, json={"candidate_run_id": candidate_run["id"], "baseline_run_id": baseline_run["id"]})
  assert start.status_code == 200, start.text
  adv = client.post("/api/v1/rollout/advance", headers=headers, json={})
  assert adv.status_code == 200, adv.text
  assert adv.json()["state"]["state"] == "PAPER_SOAK"

  old_start = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
  eval_res = client.post(
    "/api/v1/rollout/evaluate-phase",
    headers=headers,
    json={"phase": "paper_soak", "override_started_at": old_start, "auto_advance": True},
  )
  assert eval_res.status_code == 200, eval_res.text
  body = eval_res.json()
  assert body["evaluation"]["passed"] is True
  assert body["advanced"] is True
  assert body["state"]["state"] == "TESTNET_SOAK"


def test_rollout_api_testnet_soak_evaluate_and_auto_advance(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  yaml_payload = """
id: rollout_candidate_strategy_3
name: Rollout Candidate 3
version: 1.0.0
defaults:
  risk_per_trade_pct: 0.5
""".strip()
  upload = client.post(
    "/api/v1/strategies/upload",
    headers=headers,
    files={"file": ("rollout_candidate_strategy_3.yaml", yaml_payload.encode("utf-8"), "application/x-yaml")},
  )
  assert upload.status_code == 200, upload.text

  runs = module.store.load_runs()
  baseline_run = copy.deepcopy(runs[0])
  baseline_run["id"] = "run_baseline_rollout_3"
  baseline_run["strategy_id"] = "trend_pullback_orderflow_confirm_v1"
  baseline_run["data_source"] = "binance_public"
  baseline_run["validation_mode"] = "walk-forward"
  baseline_run["validation_summary"] = {"mode": "walk-forward", "implemented": True}
  baseline_run["dataset_hash"] = "same_dataset_rollout_3"
  baseline_run["period"] = {"start": "2024-01-01", "end": "2024-12-31"}
  baseline_run["metrics"].update({"trade_count": 200, "winrate": 0.50, "profit_factor": 1.25, "sharpe": 1.30, "sortino": 1.80, "calmar": 1.05, "max_dd": 0.12, "max_dd_duration_bars": 5000, "expectancy_usd_per_trade": 10.0})
  baseline_run["costs_breakdown"].update({"gross_pnl_total": 2000.0, "total_cost": 600.0, "net_pnl_total": 1400.0, "net_pnl": 1400.0})
  candidate_run = copy.deepcopy(baseline_run)
  candidate_run["id"] = "run_candidate_rollout_3"
  candidate_run["strategy_id"] = "rollout_candidate_strategy_3"
  candidate_run["metrics"].update({"winrate": 0.54, "profit_factor": 1.35, "sharpe": 1.55, "sortino": 2.10, "calmar": 1.25, "max_dd": 0.13, "expectancy_usd_per_trade": 11.1})
  candidate_run["costs_breakdown"].update({"gross_pnl_total": 2150.0, "total_cost": 630.0, "net_pnl_total": 1520.0, "net_pnl": 1520.0})
  module.store.save_runs([candidate_run, baseline_run, *runs])

  start = client.post("/api/v1/rollout/start", headers=headers, json={"candidate_run_id": candidate_run["id"], "baseline_run_id": baseline_run["id"]})
  assert start.status_code == 200, start.text
  adv = client.post("/api/v1/rollout/advance", headers=headers, json={})
  assert adv.status_code == 200, adv.text
  assert adv.json()["state"]["state"] == "PAPER_SOAK"

  old_paper_start = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
  eval_paper = client.post(
    "/api/v1/rollout/evaluate-phase",
    headers=headers,
    json={"phase": "paper_soak", "override_started_at": old_paper_start, "auto_advance": True},
  )
  assert eval_paper.status_code == 200, eval_paper.text
  assert eval_paper.json()["state"]["state"] == "TESTNET_SOAK"

  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "ok": True,
      "mode": mode,
      "exchange": "binance",
      "connector_ok": True,
      "connector_reason": "ok",
      "order_ok": True,
      "order_reason": "ok",
    },
  )
  old_testnet_start = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
  eval_testnet = client.post(
    "/api/v1/rollout/evaluate-phase",
    headers=headers,
    json={"phase": "testnet_soak", "override_started_at": old_testnet_start, "auto_advance": True},
  )
  assert eval_testnet.status_code == 200, eval_testnet.text
  payload = eval_testnet.json()
  assert payload["phase"] == "testnet_soak"
  assert payload["evaluation"]["passed"] is True
  assert payload["advanced"] is True
  assert payload["state"]["state"] == "PENDING_LIVE_APPROVAL"


def test_rollout_api_canary15_auto_rollback_e2e(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  yaml_payload = """
id: rollout_candidate_strategy_4
name: Rollout Candidate 4
version: 1.0.0
defaults:
  risk_per_trade_pct: 0.5
""".strip()
  upload = client.post(
    "/api/v1/strategies/upload",
    headers=headers,
    files={"file": ("rollout_candidate_strategy_4.yaml", yaml_payload.encode("utf-8"), "application/x-yaml")},
  )
  assert upload.status_code == 200, upload.text

  runs = module.store.load_runs()
  baseline_run = copy.deepcopy(runs[0])
  baseline_run["id"] = "run_baseline_rollout_4"
  baseline_run["strategy_id"] = "trend_pullback_orderflow_confirm_v1"
  baseline_run["data_source"] = "binance_public"
  baseline_run["validation_mode"] = "walk-forward"
  baseline_run["validation_summary"] = {"mode": "walk-forward", "implemented": True}
  baseline_run["dataset_hash"] = "same_dataset_rollout_4"
  baseline_run["period"] = {"start": "2024-01-01", "end": "2024-12-31"}
  baseline_run["metrics"].update({"trade_count": 200, "winrate": 0.50, "profit_factor": 1.25, "sharpe": 1.30, "sortino": 1.80, "calmar": 1.05, "max_dd": 0.12, "max_dd_duration_bars": 5000, "expectancy_usd_per_trade": 10.0})
  baseline_run["costs_breakdown"].update({"gross_pnl_total": 2000.0, "total_cost": 600.0, "net_pnl_total": 1400.0, "net_pnl": 1400.0})
  candidate_run = copy.deepcopy(baseline_run)
  candidate_run["id"] = "run_candidate_rollout_4"
  candidate_run["strategy_id"] = "rollout_candidate_strategy_4"
  candidate_run["metrics"].update({"winrate": 0.54, "profit_factor": 1.35, "sharpe": 1.55, "sortino": 2.10, "calmar": 1.25, "max_dd": 0.13, "expectancy_usd_per_trade": 12.0})
  candidate_run["costs_breakdown"].update({"gross_pnl_total": 2150.0, "total_cost": 630.0, "net_pnl_total": 1520.0, "net_pnl": 1520.0})
  module.store.save_runs([candidate_run, baseline_run, *runs])

  start = client.post("/api/v1/rollout/start", headers=headers, json={"candidate_run_id": candidate_run["id"], "baseline_run_id": baseline_run["id"]})
  assert start.status_code == 200, start.text
  assert start.json()["state"]["state"] == "OFFLINE_GATES_PASSED"

  adv = client.post("/api/v1/rollout/advance", headers=headers, json={})
  assert adv.status_code == 200, adv.text
  assert adv.json()["state"]["state"] == "PAPER_SOAK"
  old_paper = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
  eval_paper = client.post("/api/v1/rollout/evaluate-phase", headers=headers, json={"phase": "paper_soak", "override_started_at": old_paper, "auto_advance": True})
  assert eval_paper.status_code == 200, eval_paper.text
  assert eval_paper.json()["state"]["state"] == "TESTNET_SOAK"

  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "ok": True,
      "mode": mode,
      "exchange": "binance",
      "connector_ok": True,
      "connector_reason": "ok",
      "order_ok": True,
      "order_reason": "ok",
    },
  )
  old_testnet = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
  eval_testnet = client.post("/api/v1/rollout/evaluate-phase", headers=headers, json={"phase": "testnet_soak", "override_started_at": old_testnet, "auto_advance": True})
  assert eval_testnet.status_code == 200, eval_testnet.text
  assert eval_testnet.json()["state"]["state"] == "PENDING_LIVE_APPROVAL"

  approve = client.post("/api/v1/rollout/approve", headers=headers, json={"reason": "ok"})
  assert approve.status_code == 200, approve.text
  assert approve.json()["state"]["state"] == "LIVE_SHADOW"
  assert approve.json()["state"]["routing"]["shadow_only"] is True

  old_shadow = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
  eval_shadow = client.post("/api/v1/rollout/evaluate-phase", headers=headers, json={"phase": "shadow", "override_started_at": old_shadow, "auto_advance": True})
  assert eval_shadow.status_code == 200, eval_shadow.text
  assert eval_shadow.json()["state"]["state"] == "LIVE_CANARY_05"

  old_canary05 = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
  eval_canary05 = client.post("/api/v1/rollout/evaluate-phase", headers=headers, json={"phase": "canary05", "override_started_at": old_canary05, "auto_advance": True})
  assert eval_canary05.status_code == 200, eval_canary05.text
  assert eval_canary05.json()["state"]["state"] == "LIVE_CANARY_15"
  assert eval_canary05.json()["state"]["weights"]["candidate_pct"] == 15

  monkeypatch.setattr(
    module,
    "build_status_payload",
    lambda: {
      "daily_pnl": -25.0,
      "expectancy_24h_usd": -8.0,
      "phase_dd_increment_pct": 2.6,
      "max_dd": {"value": -0.05},
    },
  )
  monkeypatch.setattr(
    module,
    "build_execution_metrics_payload",
    lambda: {
      "p95_slippage": 26.0,
      "p95_spread": 18.0,
      "latency_ms_p95": 170.0,
      "api_errors": 5,
      "requests_24h_estimate": 100,
      "series": [{"ts": "x"}],
    },
  )
  failing_logs = [
    {"severity": "error", "module": "execution", "type": "breaker_triggered", "message": "b1"},
    {"severity": "error", "module": "execution", "type": "breaker_triggered", "message": "b2"},
    {"severity": "error", "module": "execution", "type": "breaker_triggered", "message": "b3"},
    {"severity": "error", "module": "exchange", "type": "api_error", "message": "api fail"},
  ]
  monkeypatch.setattr(module.store, "list_logs", lambda **kwargs: {"items": failing_logs})

  old_canary15 = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
  eval_canary15 = client.post("/api/v1/rollout/evaluate-phase", headers=headers, json={"phase": "canary15", "override_started_at": old_canary15, "auto_abort": True})
  assert eval_canary15.status_code == 200, eval_canary15.text
  payload = eval_canary15.json()
  assert payload["phase"] == "canary15"
  assert payload["evaluation"]["hard_fail"] is True
  assert payload["state"]["state"] == "ROLLED_BACK"
  assert payload["state"]["weights"]["baseline_pct"] == 100
  assert payload["state"]["weights"]["candidate_pct"] == 0


def test_rollout_api_blending_preview_records_telemetry(tmp_path: Path, monkeypatch) -> None:
  module, client = _build_app(tmp_path, monkeypatch)
  admin_token = _login(client, "Wadmin", "moroco123")
  headers = _auth_headers(admin_token)

  yaml_payload = """
id: rollout_candidate_strategy_5
name: Rollout Candidate 5
version: 1.0.0
defaults:
  risk_per_trade_pct: 0.5
""".strip()
  upload = client.post(
    "/api/v1/strategies/upload",
    headers=headers,
    files={"file": ("rollout_candidate_strategy_5.yaml", yaml_payload.encode("utf-8"), "application/x-yaml")},
  )
  assert upload.status_code == 200, upload.text

  runs = module.store.load_runs()
  baseline_run = copy.deepcopy(runs[0])
  baseline_run["id"] = "run_baseline_rollout_5"
  baseline_run["strategy_id"] = "trend_pullback_orderflow_confirm_v1"
  baseline_run["data_source"] = "binance_public"
  baseline_run["validation_mode"] = "walk-forward"
  baseline_run["validation_summary"] = {"mode": "walk-forward", "implemented": True}
  baseline_run["dataset_hash"] = "same_dataset_rollout_5"
  baseline_run["period"] = {"start": "2024-01-01", "end": "2024-12-31"}
  baseline_run["metrics"].update({"trade_count": 200, "winrate": 0.50, "profit_factor": 1.25, "sharpe": 1.30, "sortino": 1.80, "calmar": 1.05, "max_dd": 0.12, "max_dd_duration_bars": 5000, "expectancy_usd_per_trade": 10.0})
  baseline_run["costs_breakdown"].update({"gross_pnl_total": 2000.0, "total_cost": 600.0, "net_pnl_total": 1400.0, "net_pnl": 1400.0})
  candidate_run = copy.deepcopy(baseline_run)
  candidate_run["id"] = "run_candidate_rollout_5"
  candidate_run["strategy_id"] = "rollout_candidate_strategy_5"
  candidate_run["metrics"].update({"winrate": 0.54, "profit_factor": 1.35, "sharpe": 1.55, "sortino": 2.10, "calmar": 1.25, "max_dd": 0.13, "expectancy_usd_per_trade": 12.0})
  candidate_run["costs_breakdown"].update({"gross_pnl_total": 2150.0, "total_cost": 630.0, "net_pnl_total": 1520.0, "net_pnl": 1520.0})
  module.store.save_runs([candidate_run, baseline_run, *runs])

  start = client.post("/api/v1/rollout/start", headers=headers, json={"candidate_run_id": candidate_run["id"], "baseline_run_id": baseline_run["id"]})
  assert start.status_code == 200, start.text
  adv = client.post("/api/v1/rollout/advance", headers=headers, json={})
  assert adv.status_code == 200, adv.text
  old_paper = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
  eval_paper = client.post("/api/v1/rollout/evaluate-phase", headers=headers, json={"phase": "paper_soak", "override_started_at": old_paper, "auto_advance": True})
  assert eval_paper.status_code == 200, eval_paper.text

  monkeypatch.setattr(
    module,
    "diagnose_exchange",
    lambda mode, force_refresh=False: {
      "ok": True,
      "mode": mode,
      "exchange": "binance",
      "connector_ok": True,
      "connector_reason": "ok",
      "order_ok": True,
      "order_reason": "ok",
    },
  )
  old_testnet = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
  eval_testnet = client.post("/api/v1/rollout/evaluate-phase", headers=headers, json={"phase": "testnet_soak", "override_started_at": old_testnet, "auto_advance": True})
  assert eval_testnet.status_code == 200, eval_testnet.text
  approve = client.post("/api/v1/rollout/approve", headers=headers, json={"reason": "ok"})
  assert approve.status_code == 200, approve.text
  assert approve.json()["state"]["state"] == "LIVE_SHADOW"

  preview = client.post(
    "/api/v1/rollout/blending/preview",
    headers=headers,
    json={
      "baseline_signal": {"action": "long", "confidence": 0.7},
      "candidate_signal": {"action": "short", "confidence": 0.9},
      "symbol": "BTCUSDT",
      "timeframe": "5m",
      "record_telemetry": True,
    },
  )
  assert preview.status_code == 200, preview.text
  body = preview.json()
  assert body["event"]["phase"] == "shadow"
  assert body["event"]["decisions"]["baseline"]["action"] == "long"
  assert body["event"]["decisions"]["candidate"]["action"] == "short"
  assert body["event"]["decisions"]["blended"]["action"] == "flat"
  assert body["telemetry"]["phases"]["shadow"]["events"] >= 1

  status = client.get("/api/v1/rollout/status", headers=headers)
  assert status.status_code == 200, status.text
  status_payload = status.json()
  assert status_payload["live_signal_telemetry"]["phases"]["shadow"]["events"] >= 1

from __future__ import annotations

from pathlib import Path
import json

from rtlab_core.learning.knowledge import KnowledgeLoader
from rtlab_core.src.data.catalog import DataCatalog
from rtlab_core.src.research.data_provider import build_data_provider
from rtlab_core.src.research.mass_backtest_engine import FoldWindow, MassBacktestEngine


def _dummy_run_factory(strategy_id: str, fold: FoldWindow) -> dict:
  return {
    "id": f"run_{strategy_id}_{fold.fold_index}",
    "strategy_id": strategy_id,
    "dataset_hash": f"ds_{fold.fold_index}",
    "provenance": {"dataset_hash": f"ds_{fold.fold_index}", "from": fold.test_start, "to": fold.test_end},
    "metrics": {
      "sharpe": 0.9,
      "sortino": 1.2,
      "calmar": 0.8,
      "max_dd": 0.12,
      "winrate": 0.52,
      "expectancy": 4.5,
      "expectancy_usd_per_trade": 4.5,
      "trade_count": 80,
      "roundtrips": 80,
      "robustness_score": 64.0,
    },
    "costs_breakdown": {
      "gross_pnl_total": 500.0,
      "net_pnl_total": 420.0,
      "total_cost": 80.0,
      "total_cost_pct_of_gross_pnl": 0.16,
    },
  }


def _engine(tmp_path: Path) -> MassBacktestEngine:
  repo_root = Path(__file__).resolve().parents[2]
  return MassBacktestEngine(user_data_dir=tmp_path, repo_root=repo_root, knowledge_loader=KnowledgeLoader(repo_root=repo_root))


def _seed_dataset_manifest(tmp_path: Path, *, market: str = "crypto", symbol: str = "BTCUSDT", timeframe: str = "5m") -> None:
  provider = "binance_public" if market == "crypto" else "manual"
  dataset_dir = tmp_path / "datasets" / provider / market / symbol / timeframe
  dataset_dir.mkdir(parents=True, exist_ok=True)
  chunk = dataset_dir / "chunk.parquet"
  chunk.write_bytes(b"stub")
  manifest = {
    "provider": provider,
    "market": market,
    "symbol": symbol,
    "timeframe": timeframe,
    "dataset_source": provider,
    "dataset_hash": "ds_unit_mass_001",
    "start": "2024-01-01",
    "end": "2024-12-31",
    "files": [str(chunk.resolve())],
  }
  (dataset_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_load_knowledge_pack_and_generate_variants_reproducible(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  kp = engine.load_knowledge_pack()
  assert isinstance(kp["templates"], list) and kp["templates"]
  strategies = [
    {"id": "trend_pullback_orderflow_v2", "name": "Trend", "status": "active", "tags": ["trend"]},
    {"id": "breakout_volatility_v2", "name": "Break", "status": "active", "tags": ["breakout"]},
  ]
  v1 = engine.generate_variants(strategies=strategies, knowledge_pack=kp, seed=123, max_variants_per_strategy=3)
  v2 = engine.generate_variants(strategies=strategies, knowledge_pack=kp, seed=123, max_variants_per_strategy=3)
  assert len(v1) == 6
  assert [r["variant_id"] for r in v1] == [r["variant_id"] for r in v2]
  assert [r["params"] for r in v1] == [r["params"] for r in v2]


def test_walk_forward_runner_and_cost_model(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  folds = engine.walk_forward_runner(start="2024-01-01", end="2025-12-31", train_days=180, test_days=60, max_folds=10)
  assert folds and len(folds) >= 4
  assert folds[0].test_start >= folds[0].train_end
  base = engine.realistic_cost_model({"fees_bps": 5, "spread_bps": 3, "slippage_bps": 2, "funding_bps": 1})
  stress = engine.realistic_cost_model({"fees_bps": 5, "spread_bps": 3, "slippage_bps": 2, "funding_bps": 1}, stress_level="stress_plus")
  assert stress["spread_bps"] > base["spread_bps"]
  assert stress["slippage_bps"] > base["slippage_bps"]


def test_scoring_and_ranking_applies_hard_filters(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  summary_ok = {"trade_count_oos": 300, "max_dd_oos_pct": 12, "costs_ratio": 0.25, "sharpe_oos": 1.5, "calmar_oos": 1.2, "expectancy_net_usd": 6.0, "stability": 0.7}
  summary_bad = {"trade_count_oos": 50, "max_dd_oos_pct": 40, "costs_ratio": 0.9, "sharpe_oos": 3.0, "calmar_oos": 2.0, "expectancy_net_usd": 20.0, "stability": 0.9}
  anti_ok = {"pbo": 0.2, "dsr": 0.5}
  anti_bad = {"pbo": 0.8, "dsr": -0.5}
  score_ok, pass_ok, reasons_ok = engine._score(summary_ok, anti_ok)  # test internal formula
  score_bad, pass_bad, reasons_bad = engine._score(summary_bad, anti_bad)
  assert score_ok > 0
  assert pass_ok is True and not reasons_ok
  assert pass_bad is False
  assert any("trades_oos" in r for r in reasons_bad)


def test_run_job_persists_results_and_duckdb_smoke_fallback(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  _seed_dataset_manifest(tmp_path, market="crypto", symbol="BTCUSDT", timeframe="5m")
  run_id = "mass_test_001"
  cfg = {
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "start": "2024-01-01",
    "end": "2024-12-31",
    "dataset_source": "auto",
    "validation_mode": "walk-forward",
    "max_variants_per_strategy": 2,
    "max_folds": 2,
    "train_days": 90,
    "test_days": 30,
    "top_n": 3,
    "seed": 7,
    "costs": {"fees_bps": 5.5, "spread_bps": 4.0, "slippage_bps": 3.0, "funding_bps": 1.0},
  }
  strategies = [
    {"id": "trend_pullback_orderflow_v2", "name": "Trend", "status": "active", "tags": ["trend"]},
    {"id": "breakout_volatility_v2", "name": "Breakout", "status": "active", "tags": ["breakout"]},
  ]

  def cb(variant: dict, fold: FoldWindow, costs: dict) -> dict:
    return _dummy_run_factory(str(variant["strategy_id"]), fold)

  out = engine.run_job(run_id=run_id, config=cfg, strategies=strategies, historical_runs=[], backtest_callback=cb)
  assert out["run_id"] == run_id
  st = engine.status(run_id)
  assert st["state"] == "COMPLETED"
  results = engine.results(run_id, limit=50)
  assert isinstance(results.get("results"), list) and results["results"]
  assert results["query_backend"]["engine"] in {"duckdb", "python"}
  first_row = results["results"][0]
  assert "microstructure" in first_row
  assert isinstance(first_row.get("microstructure"), dict)
  assert "gates_eval" in first_row
  assert isinstance(first_row.get("gates_eval"), dict)
  assert "checks" in (first_row.get("gates_eval") or {})
  artifacts = engine.artifacts(run_id)
  assert any(item["name"] == "index.html" for item in artifacts["items"])
  batch_row = engine.backtest_catalog.get_batch(run_id)
  assert batch_row is not None
  child_rows = engine.backtest_catalog.batch_children_runs(run_id)
  assert child_rows
  assert all(str(row["run_id"]).startswith("BT-") for row in child_rows)
  assert all(str(row["run_type"]) == "batch_child" for row in child_rows)
  assert any(str((row.get("kpis") or {}).get("expectancy_unit") or "") == "usd_per_trade" for row in child_rows)
  assert "MICRO_SOFT_KILL" in (child_rows[0].get("flags") or {})


def test_dataset_mode_provider_no_api_keys_required_and_returns_hints_when_missing(tmp_path: Path) -> None:
  provider = build_data_provider(mode="dataset", user_data_dir=tmp_path, catalog=DataCatalog(tmp_path))
  resolved = provider.resolve(market="crypto", symbol="BTCUSDT", timeframe="5m", start="2024-01-01", end="2024-03-31")
  payload = resolved.to_dict()
  assert payload["mode"] == "dataset"
  assert payload["api_keys_required"] is False
  assert payload["public_downloadable"] is True
  assert payload["ready"] is False
  assert payload["hints"]


def test_orderflow_toggle_can_disable_microstructure_in_mass_backtest(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  policy = engine._micro_policy({"use_orderflow_data": False})
  assert bool(policy.get("enabled")) is False
  assert bool((policy.get("vpin") or {}).get("enabled")) is False
  debug = engine._compute_microstructure_dataset_debug(df=None, cfg={"use_orderflow_data": False})
  assert debug["available"] is False
  assert debug["reason"] == "microstructure_disabled_by_request"


def test_run_job_uses_raw_engine_metrics_by_default(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  _seed_dataset_manifest(tmp_path, market="crypto", symbol="BTCUSDT", timeframe="5m")
  cfg = {
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "start": "2024-01-01",
    "end": "2024-02-01",
    "dataset_source": "auto",
    "validation_mode": "walk-forward",
    "max_variants_per_strategy": 1,
    "max_folds": 1,
    "train_days": 30,
    "test_days": 10,
    "top_n": 1,
    "seed": 11,
    "costs": {"fees_bps": 5.5, "spread_bps": 4.0, "slippage_bps": 3.0, "funding_bps": 1.0},
  }
  strategies = [{"id": "trend_pullback_orderflow_v2", "name": "Trend", "status": "active", "tags": ["trend"]}]

  def cb(variant: dict, fold: FoldWindow, costs: dict) -> dict:
    return _dummy_run_factory(str(variant["strategy_id"]), fold)

  engine.run_job(run_id="mass_raw_engine", config=cfg, strategies=strategies, historical_runs=[], backtest_callback=cb)
  rows = engine.results("mass_raw_engine", limit=5).get("results") or []
  assert rows
  first = rows[0]
  assert float((first.get("summary") or {}).get("sharpe_oos") or 0.0) == 0.9
  assert str((first.get("summary") or {}).get("evaluation_mode") or "") == "engine_raw"
  assert str((((first.get("folds") or [{}])[0]).get("evaluation_mode") or "")) == "engine_raw"


def test_run_job_applies_surrogate_only_in_demo_mode_and_blocks_promotion(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  _seed_dataset_manifest(tmp_path, market="crypto", symbol="BTCUSDT", timeframe="5m")
  cfg = {
    "market": "crypto",
    "symbol": "BTCUSDT",
    "timeframe": "5m",
    "start": "2024-01-01",
    "end": "2024-02-01",
    "dataset_source": "auto",
    "validation_mode": "walk-forward",
    "max_variants_per_strategy": 1,
    "max_folds": 1,
    "train_days": 30,
    "test_days": 10,
    "top_n": 1,
    "seed": 11,
    "execution_mode": "demo",
    "costs": {"fees_bps": 5.5, "spread_bps": 4.0, "slippage_bps": 3.0, "funding_bps": 1.0},
    "policy_snapshot": {
      "gates": {
        "gates": {
          "pbo": {"enabled": False},
          "dsr": {"enabled": False},
          "walk_forward": {"enabled": False},
          "cost_stress": {"enabled": False},
          "min_trade_quality": {"enabled": False},
          "surrogate_adjustments": {
            "enabled": True,
            "allow_request_override": False,
            "allowed_execution_modes": ["demo"],
            "promotion_blocked": True,
          },
        }
      }
    },
  }
  strategies = [{"id": "trend_pullback_orderflow_v2", "name": "Trend", "status": "active", "tags": ["trend"]}]

  def cb(variant: dict, fold: FoldWindow, costs: dict) -> dict:
    return _dummy_run_factory(str(variant["strategy_id"]), fold)

  engine.run_job(run_id="mass_demo_surrogate", config=cfg, strategies=strategies, historical_runs=[], backtest_callback=cb)
  rows = engine.results("mass_demo_surrogate", limit=5).get("results") or []
  assert rows
  first = rows[0]
  assert str((first.get("summary") or {}).get("evaluation_mode") or "") == "engine_surrogate_adjusted"
  assert str((((first.get("folds") or [{}])[0]).get("evaluation_mode") or "")) == "engine_surrogate_adjusted"
  assert bool((first.get("gates_eval") or {}).get("passed")) is False
  assert "surrogate_adjustments" in ((first.get("gates_eval") or {}).get("fail_reasons") or [])
  assert bool(first.get("promotable")) is False
  assert bool(first.get("recommendable_option_b")) is False


def _min_trade_quality_policy(*, min_trades_per_run: int = 150, min_trades_per_symbol: int = 30) -> dict:
  return {
    "policy_snapshot": {
      "gates": {
        "gates": {
          "pbo": {"enabled": False},
          "dsr": {"enabled": False},
          "walk_forward": {"enabled": False},
          "cost_stress": {"enabled": False},
          "min_trade_quality": {
            "enabled": True,
            "min_trades_per_run": min_trades_per_run,
            "min_trades_per_symbol": min_trades_per_symbol,
          },
        }
      }
    }
  }


def _with_surrogate_policy(
  cfg: dict,
  *,
  enabled: bool,
  allow_request_override: bool = False,
  allowed_execution_modes: list[str] | None = None,
  promotion_blocked: bool = True,
) -> dict:
  out = dict(cfg)
  snap = out.get("policy_snapshot") if isinstance(out.get("policy_snapshot"), dict) else {}
  gates_file = snap.get("gates") if isinstance(snap.get("gates"), dict) else {}
  gates_root = gates_file.get("gates") if isinstance(gates_file.get("gates"), dict) else {}
  merged = dict(gates_root)
  merged["surrogate_adjustments"] = {
    "enabled": bool(enabled),
    "allow_request_override": bool(allow_request_override),
    "allowed_execution_modes": [str(x) for x in (allowed_execution_modes or ["demo"])],
    "promotion_blocked": bool(promotion_blocked),
  }
  out["policy_snapshot"] = {"gates": {"gates": merged}}
  return out


def _gate_row_with_symbol_counts(symbol_counts: dict[str, int]) -> dict:
  trade_count_oos = sum(int(v) for v in symbol_counts.values())
  return {
    "variant_id": "v_min_trade_quality",
    "hard_filters_pass": True,
    "summary": {
      "trade_count_oos": trade_count_oos,
      "trade_count_by_symbol_oos": symbol_counts,
      "min_trades_per_symbol_oos": min(symbol_counts.values()) if symbol_counts else 0,
      "sharpe_oos": 1.0,
      "gross_pnl_oos": 1200.0,
      "net_pnl_oos": 900.0,
      "costs_total": 300.0,
    },
    "folds": [{"sharpe_oos": 1.0, "net_pnl": 450.0}, {"sharpe_oos": 1.0, "net_pnl": 450.0}],
    "anti_overfitting": {"promotion_blocked": False},
  }


def test_advanced_gates_fail_when_min_trades_per_symbol_is_below_threshold(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  row = _gate_row_with_symbol_counts({"BTCUSDT": 280, "ETHUSDT": 20})
  cfg = _min_trade_quality_policy(min_trades_per_run=150, min_trades_per_symbol=30)

  engine._apply_advanced_gates(rows=[row], cfg=cfg)

  gates_eval = row.get("gates_eval") or {}
  checks = (gates_eval.get("checks") or {})
  tq = checks.get("min_trade_quality") or {}
  assert gates_eval.get("passed") is False
  assert "min_trade_quality" in (gates_eval.get("fail_reasons") or [])
  assert tq.get("symbol_trade_pass") is False
  assert tq.get("run_trade_pass") is True
  assert tq.get("min_trades_per_symbol_oos") == 20
  assert "ETHUSDT" in (tq.get("symbols_below_min_trades") or [])


def test_advanced_gates_pass_when_min_trades_per_symbol_meets_threshold(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  row = _gate_row_with_symbol_counts({"BTCUSDT": 170, "ETHUSDT": 160})
  cfg = _min_trade_quality_policy(min_trades_per_run=150, min_trades_per_symbol=30)

  engine._apply_advanced_gates(rows=[row], cfg=cfg)

  gates_eval = row.get("gates_eval") or {}
  checks = (gates_eval.get("checks") or {})
  tq = checks.get("min_trade_quality") or {}
  assert gates_eval.get("passed") is True
  assert tq.get("symbol_trade_pass") is True
  assert tq.get("run_trade_pass") is True
  assert tq.get("min_trades_per_symbol_oos") == 160


def test_surrogate_adjustments_policy_requires_allowed_execution_mode(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  cfg = _with_surrogate_policy(
    _min_trade_quality_policy(),
    enabled=True,
    allow_request_override=False,
    allowed_execution_modes=["demo"],
    promotion_blocked=True,
  )
  cfg["execution_mode"] = "research"
  meta = engine._resolve_surrogate_adjustments(cfg)
  assert meta["enabled_effective"] is False
  assert meta["reason"] == "execution_mode_not_allowed"

  cfg["execution_mode"] = "demo"
  meta_demo = engine._resolve_surrogate_adjustments(cfg)
  assert meta_demo["enabled_effective"] is True
  assert meta_demo["promotion_blocked_effective"] is True
  assert meta_demo["evaluation_mode"] == "engine_surrogate_adjusted"


def test_surrogate_adjustments_request_override_rejected_by_default(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  cfg = _with_surrogate_policy(
    _min_trade_quality_policy(),
    enabled=False,
    allow_request_override=False,
    allowed_execution_modes=["research"],
    promotion_blocked=True,
  )
  cfg["execution_mode"] = "research"
  cfg["enable_surrogate_adjustments"] = True
  meta = engine._resolve_surrogate_adjustments(cfg)
  assert meta["enabled_effective"] is False
  assert meta["reason"] == "request_override_not_allowed"


def test_advanced_gates_block_promotion_when_surrogate_adjustments_enabled(tmp_path: Path) -> None:
  engine = _engine(tmp_path)
  row = _gate_row_with_symbol_counts({"BTCUSDT": 200, "ETHUSDT": 180})
  cfg = _with_surrogate_policy(
    _min_trade_quality_policy(min_trades_per_run=150, min_trades_per_symbol=30),
    enabled=True,
    allow_request_override=False,
    allowed_execution_modes=["research"],
    promotion_blocked=True,
  )
  cfg["execution_mode"] = "research"

  engine._apply_advanced_gates(rows=[row], cfg=cfg)

  gates_eval = row.get("gates_eval") or {}
  checks = (gates_eval.get("checks") or {})
  surrogate = checks.get("surrogate_adjustments") or {}
  assert gates_eval.get("passed") is False
  assert "surrogate_adjustments" in (gates_eval.get("fail_reasons") or [])
  assert surrogate.get("enabled_effective") is True
  assert surrogate.get("pass") is False
  assert row.get("promotable") is False
  assert row.get("recommendable_option_b") is False
  assert ((row.get("anti_overfitting") or {}).get("promotion_block_reason")) == "surrogate_adjustments_enabled"

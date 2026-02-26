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

from __future__ import annotations

import json
from pathlib import Path

from rtlab_core.backtest import BacktestCatalogDB


def test_backtest_catalog_ids_and_run_record(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")

    bt1 = db.next_formatted_id("BT")
    bx1 = db.next_formatted_id("BX")
    assert bt1.startswith("BT-")
    assert bx1.startswith("BX-")

    run = {
        "id": "BT-000999",
        "strategy_id": "trend_pullback_orderflow_confirm_v1",
        "strategy_name": "Trend Pullback",
        "strategy_version": "1.0.0",
        "mode": "backtest",
        "period": {"start": "2024-01-01", "end": "2024-12-31"},
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "universe": ["BTCUSDT"],
        "data_source": "binance_ohlcv_local",
        "dataset_version": "ohlcv_v3",
        "dataset_hash": "abc123",
        "costs_model": {"fees_bps": 5.5, "spread_bps": 4.0, "slippage_bps": 3.0, "funding_bps": 1.0},
        "metrics": {"sharpe": 1.2, "max_dd": 0.12, "trade_count": 240, "expectancy": 2.5, "expectancy_unit": "usd_per_trade"},
        "created_at": "2026-02-23T00:00:00+00:00",
        "git_commit": "deadbeef",
    }
    strategy_meta = {"db_strategy_id": 12, "name": "Trend Pullback OF", "version": "2.3.0"}
    catalog_run_id = db.record_run_from_payload(run=run, strategy_meta=strategy_meta, created_by="admin")
    assert catalog_run_id == "BT-000999"
    assert run["catalog_run_id"] == "BT-000999"
    assert str(run.get("title_structured") or "").startswith("BT-000999")
    stored = db.get_run("BT-000999")
    assert stored is not None
    assert stored["dataset_hash"] == "abc123"
    assert stored["code_commit_hash"] == "deadbeef"
    assert stored["fee_model"].startswith("maker_taker_bps:")
    assert stored["kpis"]["expectancy_unit"] == "usd_per_trade"

    batch = db.upsert_backtest_batch(
        {
            "batch_id": "BX-000038",
            "objective": "Research Batch prueba",
            "universe_json": json.dumps({"symbols": ["BTCUSDT", "ETHUSDT"], "timeframes": ["5m"]}),
            "variables_explored_json": json.dumps({"max_variants_per_strategy": 8}),
            "status": "running",
            "run_count_total": 10,
            "run_count_done": 4,
            "run_count_failed": 1,
        }
    )
    assert batch["batch_id"] == "BX-000038"

    db.add_artifact(run_id="BT-000999", batch_id="BX-000038", kind="report_json", path="/api/v1/backtests/runs/BT-000999?format=report_json")
    artifacts = db.get_artifacts_for_run("BT-000999")
    assert any(a["artifact_kind"] == "report_json" for a in artifacts)


def test_backtest_catalog_query_patch_and_rankings(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    for i in range(3):
        run = {
            "id": f"BT-00010{i}",
            "strategy_id": "trend_pullback_orderflow_confirm_v1",
            "strategy_name": "Trend Pullback",
            "strategy_version": "1.0.0",
            "mode": "backtest",
            "period": {"start": "2024-01-01", "end": "2024-12-31"},
            "symbol": "BTCUSDT",
            "timeframe": "5m",
            "universe": ["BTCUSDT"],
            "data_source": "binance_ohlcv_local",
            "dataset_version": "ohlcv_v3",
            "dataset_hash": f"hash{i}",
            "costs_model": {"fees_bps": 5.5, "spread_bps": 4.0, "slippage_bps": 3.0, "funding_bps": 1.0},
            "metrics": {
                "cagr": 0.1 + i * 0.05,
                "sharpe": 0.8 + i * 0.4,
                "sortino": 1.0 + i * 0.5,
                "calmar": 0.6 + i * 0.3,
                "max_dd": 0.22 - i * 0.03,
                "profit_factor": 1.1 + i * 0.2,
                "trade_count": 100 + i * 100,
                "expectancy": 1.0 + i,
                "expectancy_unit": "usd_per_trade",
            },
            "created_at": f"2026-02-23T0{i}:00:00+00:00",
            "git_commit": "deadbeef",
        }
        db.record_run_from_payload(run=run, strategy_meta={"db_strategy_id": 12, "name": "Trend Pullback OF", "version": "2.3.0"})

    rows = db.query_runs(min_trades=200, sort_by="sharpe", sort_dir="desc")
    assert rows
    assert all(int((r.get("kpis") or {}).get("trade_count") or 0) >= 200 for r in rows)
    assert float((rows[0].get("kpis") or {}).get("sharpe") or 0.0) >= float((rows[-1].get("kpis") or {}).get("sharpe") or 0.0)

    patched = db.patch_run("BT-000101", alias="Mi run", tags=["favorito", "wfa"], pinned=True, archived=True)
    assert patched is not None
    assert patched["alias"] == "Mi run"
    assert "favorito" in patched["tags"]
    assert patched["pinned"] is True
    assert patched["status"] == "archived"

    patched_flags = db.patch_run_flags("BT-000101", {"PASO_GATES": True, "BASELINE": True})
    assert patched_flags is not None
    assert bool((patched_flags.get("flags") or {}).get("PASO_GATES")) is True
    assert bool((patched_flags.get("flags") or {}).get("BASELINE")) is True

    rankings = db.rankings(preset="balanceado", constraints={"min_trades": 100}, limit=10)
    assert rankings["items"]
    assert "composite_score" in rankings["items"][0]

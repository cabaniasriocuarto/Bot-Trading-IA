from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from rtlab_core.learning.experience_store import ExperienceStore
from rtlab_core.learning.service import LearningService
from rtlab_core.strategy_packs.registry_db import RegistryDB


def _strategy_row(strategy_id: str, *, tags: list[str] | None = None) -> dict[str, object]:
    return {
        "id": strategy_id,
        "name": strategy_id,
        "status": "active",
        "enabled_for_trading": True,
        "allow_learning": True,
        "tags": tags or ["range"],
    }


def _record_run(
    store: ExperienceStore,
    *,
    strategy_id: str,
    run_id: str,
    source: str,
    start_dt: datetime,
    bot_id: str | None = None,
    expectancy: float = 8.0,
    sharpe: float = 1.2,
    max_dd: float = 0.04,
    trade_count: int = 12,
) -> None:
    end_dt = start_dt + timedelta(minutes=5)
    run = {
        "id": run_id,
        "strategy_id": strategy_id,
        "mode": source,
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "data_source": "dataset_real",
        "dataset_hash": f"{strategy_id}-{source}-hash",
        "git_commit": "deadbeef",
        "feature_set": "orderflow_on",
        "period": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
        "created_at": (start_dt + timedelta(days=2)).isoformat(),
        "metrics": {
            "trade_count": trade_count,
            "roundtrips": trade_count,
            "expectancy_usd_per_trade": expectancy,
            "sharpe": sharpe,
            "sortino": sharpe + 0.15,
            "profit_factor": 1.8 if expectancy > 0 else 0.9,
            "win_rate": 0.62 if expectancy > 0 else 0.44,
            "max_dd": max_dd,
        },
        "costs_model": {
            "fees_bps": 4.0,
            "spread_bps": 2.0,
            "slippage_bps": 1.0,
            "funding_bps": 0.0,
        },
        "costs_breakdown": {
            "gross_pnl_total": expectancy * trade_count,
            "net_pnl_total": (expectancy - 1.0) * trade_count,
            "total_cost": 1.0 * trade_count,
            "fees_total": 0.4 * trade_count,
            "spread_total": 0.4 * trade_count,
            "slippage_total": 0.2 * trade_count,
            "funding_total": 0.0,
        },
        "trades": [],
    }
    store.record_run(run, source_override=source, bot_id=bot_id)


def test_learning_service_builds_bot_brain_from_live_and_ledgers(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    repo_root = Path(__file__).resolve().parents[2]
    service = LearningService(user_data_dir=tmp_path, repo_root=repo_root, registry=registry)

    strategy_live = "trend_pullback_orderflow_confirm_v1"
    strategy_pool = "meanreversion_range_v2"
    base_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)

    for idx in range(15):
        _record_run(
            store,
            strategy_id=strategy_live,
            run_id=f"live-bot-{idx}",
            source="live",
            start_dt=base_dt + timedelta(days=idx * 3),
            bot_id="BOT-ALPHA",
            expectancy=9.0,
            sharpe=1.4,
            max_dd=0.03,
            trade_count=12,
        )
    for idx in range(12):
        _record_run(
            store,
            strategy_id=strategy_pool,
            run_id=f"shadow-pool-{idx}",
            source="shadow",
            start_dt=base_dt + timedelta(days=idx * 4),
            bot_id="BOT-BETA",
            expectancy=5.5,
            sharpe=0.9,
            max_dd=0.05,
            trade_count=10,
        )
    for idx in range(10):
        _record_run(
            store,
            strategy_id=strategy_pool,
            run_id=f"backtest-global-{idx}",
            source="backtest",
            start_dt=base_dt + timedelta(days=idx * 5),
            expectancy=3.0,
            sharpe=0.6,
            max_dd=0.07,
            trade_count=8,
        )

    strategies = [
        _strategy_row(strategy_live, tags=["trend"]),
        _strategy_row(strategy_pool, tags=["range"]),
    ]
    runs = [
        {
            "id": "runtime-latest",
            "strategy_id": strategy_live,
            "mode": "live",
            "timeframe": "5m",
            "symbol": "BTCUSDT",
            "feature_set": "orderflow_on",
            "orderflow_feature_set": "orderflow_on",
            "use_orderflow_data": True,
            "metrics": {"sharpe": 1.2, "max_dd": 0.03},
        }
    ]
    bots = [
        {
            "id": "BOT-ALPHA",
            "engine_id": "bandit_thompson",
            "pool_strategy_ids": [strategy_live, strategy_pool],
        }
    ]

    payload = service.build_bot_brain(bot_id="BOT-ALPHA", bots=bots, strategies=strategies, runs=runs, persist=True)

    assert payload["selected_strategy_id"] == strategy_live
    assert "live" in payload["source_summary"]["sources"]
    assert payload["items"][0]["strategy_id"] == strategy_live

    policy_rows = registry.list_bot_policy_state(bot_id="BOT-ALPHA")
    assert len(policy_rows) == 2
    assert any(row["strategy_id"] == strategy_live for row in policy_rows)

    decision_rows = registry.list_bot_decision_log(bot_id="BOT-ALPHA")
    assert len(decision_rows) >= 1
    assert decision_rows[0]["selected_strategy_id"] == strategy_live

    truth_payload = service.get_strategy_truth_payload(strategy_live, strategies=strategies, runs=runs)
    assert truth_payload["truth"]["strategy_id"] == strategy_live

    evidence_payload = service.get_strategy_evidence_payload(strategy_live)
    assert evidence_payload["summary"]["live"]["count"] >= 1


def test_learning_service_reads_execution_reality_ledger(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    repo_root = Path(__file__).resolve().parents[2]
    service = LearningService(user_data_dir=tmp_path, repo_root=repo_root, registry=registry)

    registry.upsert_execution_reality(
        execution_id="exec-1",
        order_id="order-1",
        bot_id="BOT-ALPHA",
        strategy_id="trend_pullback_orderflow_confirm_v1",
        symbol="BTCUSDT",
        timestamp=datetime(2025, 2, 1, tzinfo=timezone.utc).isoformat(),
        side="buy",
        qty=0.2,
        realized_slippage_bps=1.5,
        maker_taker="taker",
        partial_fill_ratio=0.9,
        latency_ms=18.0,
        spread_bps=2.2,
        impact_bps_est=1.1,
        impact_budget_bps=3.0,
        reconciliation_status="ok",
    )

    payload = service.get_execution_reality_payload(bot_id="BOT-ALPHA", limit=20)

    assert payload["summary"]["count"] == 1
    assert payload["summary"]["avg_realized_slippage_bps"] == 1.5
    assert payload["items"][0]["reconciliation_status"] == "ok"

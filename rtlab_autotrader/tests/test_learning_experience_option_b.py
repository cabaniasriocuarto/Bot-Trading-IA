from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from rtlab_core.learning.experience_store import ExperienceStore
from rtlab_core.learning.option_b_engine import OptionBLearningEngine
from rtlab_core.learning.shadow_runner import ShadowRunConfig
from rtlab_core.strategy_packs.registry_db import RegistryDB


def _strategy_row(strategy_id: str, *, allow_learning: bool, is_primary: bool = False) -> dict[str, object]:
    return {
        "id": strategy_id,
        "name": strategy_id,
        "status": "active",
        "enabled_for_trading": True,
        "allow_learning": allow_learning,
        "is_primary": is_primary,
    }


def _seed_run(
    store: ExperienceStore,
    *,
    strategy_id: str,
    run_id: str,
    source: str,
    start_dt: datetime,
    gross: float,
    fee: float,
    spread_cost: float,
    slippage_cost: float,
    funding_cost: float = 0.0,
    feature_set: str = "orderflow_on",
    pbo: float = 0.12,
) -> None:
    end_dt = start_dt + timedelta(minutes=5)
    created_at = start_dt + timedelta(days=2)
    total_cost = fee + spread_cost + slippage_cost + funding_cost
    net = gross - total_cost
    run = {
        "id": run_id,
        "strategy_id": strategy_id,
        "mode": source,
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "data_source": "dataset",
        "dataset_hash": f"dataset-{strategy_id}-{feature_set}",
        "git_commit": "deadbeef",
        "validation_mode": "walk-forward",
        "feature_set": feature_set,
        "orderflow_feature_set": feature_set,
        "use_orderflow_data": feature_set == "orderflow_on",
        "period": {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
        },
        "created_at": created_at.isoformat(),
        "costs_model": {
            "fees_bps": 5.5,
            "spread_bps": 4.0,
            "slippage_bps": 3.0,
            "funding_bps": 1.0,
        },
        "costs_breakdown": {
            "gross_pnl_total": gross,
            "net_pnl_total": net,
            "total_cost": total_cost,
            "fees_total": fee,
            "spread_total": spread_cost,
            "slippage_total": slippage_cost,
            "funding_total": funding_cost,
        },
        "metrics": {
            "trade_count": 3,
            "roundtrips": 3,
            "expectancy": net,
            "expectancy_usd_per_trade": net,
            "sharpe": 1.4 if net > 0 else -0.3,
            "sortino": 1.7 if net > 0 else -0.4,
            "max_dd": 0.05 if net > 0 else 0.18,
            "pbo": pbo,
        },
        "trades": [
            {
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "side": "long",
                "entry_time": start_dt.isoformat(),
                "exit_time": end_dt.isoformat(),
                "pnl": gross,
                "pnl_net": net,
                "fees": fee,
                "spread_cost": spread_cost,
                "slippage_cost": slippage_cost,
                "funding_cost": funding_cost,
                "latency_ms": 18.0,
                "spread_bps": 4.0,
                "features": {"vpin": 0.22, "imbalance": 0.08},
                "events": [{"type": "skip", "ts": start_dt.isoformat(), "detail": "senal_rechazada_control"}],
            }
        ],
    }
    store.record_run(run, source_override=source)


def _seed_strategy_history(
    store: ExperienceStore,
    *,
    strategy_id: str,
    source: str,
    gross: float,
    fee: float,
    spread_cost: float,
    slippage_cost: float,
    runs: int = 45,
) -> None:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    for idx in range(runs):
        start_dt = base + timedelta(days=idx * 3)
        gross_i = gross + ((idx % 5) * 0.4)
        _seed_run(
            store,
            strategy_id=strategy_id,
            run_id=f"{strategy_id}-{source}-{idx}",
            source=source,
            start_dt=start_dt,
            gross=gross_i,
            fee=fee,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
        )


def test_experience_store_record_run_is_idempotent(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    strategy_id = "trend_pullback_orderflow_confirm_v1"
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)

    _seed_run(
        store,
        strategy_id=strategy_id,
        run_id="same-run",
        source="backtest",
        start_dt=start_dt,
        gross=14.0,
        fee=1.0,
        spread_cost=1.0,
        slippage_cost=1.0,
    )
    _seed_run(
        store,
        strategy_id=strategy_id,
        run_id="same-run",
        source="backtest",
        start_dt=start_dt,
        gross=14.0,
        fee=1.0,
        spread_cost=1.0,
        slippage_cost=1.0,
    )

    episodes = registry.list_experience_episodes(strategy_ids=[strategy_id], sources=["backtest"])
    events = registry.list_experience_events(episode_ids=[episodes[0]["id"]])
    assert len(episodes) == 1
    assert len(events) == 3


def test_experience_store_persists_and_filters_bot_id(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    strategy_id = "trend_pullback_orderflow_confirm_v1"
    start_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)

    run = {
        "id": "run-bot-linked",
        "strategy_id": strategy_id,
        "mode": "backtest",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "data_source": "dataset",
        "dataset_hash": "dataset-bot-linked",
        "git_commit": "deadbeef",
        "feature_set": "orderflow_on",
        "period": {
            "start": start_dt.isoformat(),
            "end": (start_dt + timedelta(minutes=5)).isoformat(),
        },
        "metrics": {"trade_count": 1, "roundtrips": 1},
        "trades": [],
    }
    store.record_run(run, source_override="backtest", bot_id="BOT-ALPHA")

    all_episodes = registry.list_experience_episodes(strategy_ids=[strategy_id], sources=["backtest"])
    assert len(all_episodes) == 1
    assert all_episodes[0]["bot_id"] == "BOT-ALPHA"

    filtered = registry.list_experience_episodes(bot_ids=["BOT-ALPHA"], sources=["backtest"])
    assert len(filtered) == 1
    assert filtered[0]["run_id"] == "run-bot-linked"

    empty = registry.list_experience_episodes(bot_ids=["BOT-BETA"], sources=["backtest"])
    assert empty == []


def test_experience_store_persists_live_source_and_run_bot_link(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    strategy_id = "trend_pullback_orderflow_confirm_v1"
    start_dt = datetime(2025, 2, 1, tzinfo=timezone.utc)

    run = {
        "id": "live-run-linked",
        "strategy_id": strategy_id,
        "mode": "live",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "data_source": "exchange_live",
        "dataset_hash": "live-dataset-hash",
        "git_commit": "cafebabe",
        "feature_set": "orderflow_on",
        "as_of": start_dt.isoformat(),
        "period": {
            "start": start_dt.isoformat(),
            "end": (start_dt + timedelta(minutes=5)).isoformat(),
        },
        "metrics": {
            "trade_count": 2,
            "roundtrips": 2,
            "expectancy_usd_per_trade": 5.5,
            "sharpe": 1.1,
            "sortino": 1.3,
            "profit_factor": 1.6,
            "win_rate": 0.5,
            "max_dd": 0.02,
        },
        "costs_model": {
            "fees_bps": 4.5,
            "spread_bps": 2.5,
            "slippage_bps": 1.0,
            "funding_bps": 0.0,
        },
        "costs_breakdown": {
            "gross_pnl_total": 14.0,
            "net_pnl_total": 11.0,
            "fees_total": 1.0,
            "spread_total": 1.0,
            "slippage_total": 1.0,
            "funding_total": 0.0,
        },
        "trades": [],
    }
    payload = store.record_run(run, source_override="live", bot_id="BOT-LIVE")

    assert payload is not None
    episodes = registry.list_experience_episodes(bot_ids=["BOT-LIVE"], sources=["live"])
    assert len(episodes) == 1
    assert episodes[0]["source"] == "live"
    assert episodes[0]["attribution_type"] == "exact"
    assert episodes[0]["attribution_confidence"] == 1.0
    assert episodes[0]["effective_weight"] == 1.0

    links = registry.list_run_bot_links(run_id="live-run-linked")
    assert len(links) == 1
    assert links[0]["bot_id"] == "BOT-LIVE"
    assert links[0]["attribution_type"] == "exact"

    evidence = registry.list_strategy_evidence(strategy_id=strategy_id, source_type="live")
    assert len(evidence) == 1
    assert evidence[0]["run_id"] == "live-run-linked"
    assert evidence[0]["source_type"] == "live"


def test_option_b_engine_filters_pool_true(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    engine = OptionBLearningEngine(registry)
    allowed = "trend_pullback_orderflow_confirm_v1"
    blocked = "breakout_volatility_v2"

    _seed_strategy_history(store, strategy_id=allowed, source="shadow", gross=12.0, fee=1.0, spread_cost=1.0, slippage_cost=1.0)
    _seed_strategy_history(store, strategy_id=blocked, source="shadow", gross=20.0, fee=0.5, spread_cost=0.5, slippage_cost=0.5)

    result = engine.recalculate(
        strategies=[
            _strategy_row(allowed, allow_learning=True, is_primary=True),
            _strategy_row(blocked, allow_learning=False),
        ],
        pbo_max=0.25,
        dsr_min=0.0,
    )

    proposals = result["proposals"]
    assert proposals
    assert all(row["proposed_strategy_id"] == allowed for row in proposals)
    assert any(row["status"] == "pending" for row in proposals)


def test_option_b_engine_blocks_negative_cost_stress(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    engine = OptionBLearningEngine(registry)
    strategy_id = "meanreversion_range_v2"

    _seed_strategy_history(store, strategy_id=strategy_id, source="backtest", gross=10.0, fee=2.0, spread_cost=3.0, slippage_cost=3.0)

    result = engine.recalculate(
        strategies=[_strategy_row(strategy_id, allow_learning=True, is_primary=True)],
        pbo_max=0.25,
        dsr_min=0.0,
    )

    proposals = [row for row in result["proposals"] if row["proposed_strategy_id"] == strategy_id]
    assert proposals
    proposal = proposals[0]
    assert proposal["needs_validation"] is True
    assert proposal["status"] == "needs_validation"
    assert "cost_stress_1_5x<0" in proposal["metrics"]["reasons"]


def test_shadow_run_config_uses_safe_defaults() -> None:
    left = ShadowRunConfig(strategy_id="trend_pullback_orderflow_v2", symbol="BTCUSDT")
    right = ShadowRunConfig(strategy_id="trend_pullback_orderflow_v2", symbol="ETHUSDT")

    assert left.lookback_bars == 300
    assert right.lookback_bars == 300
    assert left.costs is not right.costs

    left.costs.fees_bps = 9.0
    assert right.costs.fees_bps == 5.5


def test_registry_ledgers_support_truth_and_execution_reality(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")

    registry.upsert_strategy_truth(
        strategy_id="trend_pullback_orderflow_confirm_v1",
        strategy_version="1.2.0",
        family="trend_pullback",
        market="crypto",
        asset_class="spot",
        timeframe="5m",
        thesis_summary="La estrategia busca pullbacks a favor de tendencia con confirmación de order flow.",
        intended_regimes=["trend"],
        forbidden_regimes=["toxic"],
        current_status="candidate",
        current_confidence=0.72,
    )
    truth = registry.get_strategy_truth("trend_pullback_orderflow_confirm_v1")
    assert truth is not None
    assert truth["family"] == "trend_pullback"
    assert truth["current_confidence"] == 0.72

    registry.upsert_execution_reality(
        execution_id="exec-1",
        order_id="order-1",
        bot_id="BOT-LIVE",
        strategy_id="trend_pullback_orderflow_confirm_v1",
        symbol="BTCUSDT",
        timestamp=datetime(2025, 2, 1, tzinfo=timezone.utc).isoformat(),
        order_type="market",
        side="buy",
        qty=0.1,
        participation_rate=0.01,
        expected_fill_price=100.0,
        realized_fill_price=100.2,
        realized_slippage_bps=20.0,
        maker_taker="taker",
        partial_fill_ratio=1.0,
        queue_proxy=0.0,
        cancel_replace_count=0,
        latency_ms=42.0,
        spread_bps=4.0,
        impact_bps_est=8.0,
        impact_budget_bps=15.0,
        reconciliation_status="ok",
    )
    rows = registry.list_execution_reality(bot_id="BOT-LIVE")
    assert len(rows) == 1
    assert rows[0]["execution_id"] == "exec-1"
    assert rows[0]["impact_bps_est"] == 8.0

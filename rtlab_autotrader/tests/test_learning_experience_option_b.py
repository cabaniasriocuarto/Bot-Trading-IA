from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from rtlab_core.learning.experience_store import (
    EVIDENCE_STATUS_LEGACY,
    EVIDENCE_STATUS_QUARANTINE,
    ExperienceStore,
)
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
    include_costs_breakdown: bool = True,
    include_commit_hash: bool = True,
    include_validation_mode: bool = True,
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
    if include_commit_hash:
        run["git_commit"] = "deadbeef"
    if include_validation_mode:
        run["validation_mode"] = "walk-forward"
    if include_costs_breakdown:
        run["costs_breakdown"] = {
            "gross_pnl_total": gross,
            "net_pnl_total": net,
            "total_cost": total_cost,
            "fees_total": fee,
            "spread_total": spread_cost,
            "slippage_total": slippage_cost,
            "funding_total": funding_cost,
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
    include_costs_breakdown: bool = True,
    include_commit_hash: bool = True,
    include_validation_mode: bool = True,
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
            include_costs_breakdown=include_costs_breakdown,
            include_commit_hash=include_commit_hash,
            include_validation_mode=include_validation_mode,
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


def test_experience_store_quarantines_runs_with_missing_cost_totals(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    strategy_id = "quarantine_missing_costs_v1"
    start_dt = datetime(2025, 2, 1, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(minutes=5)

    run = {
        "id": "run-missing-cost-totals",
        "strategy_id": strategy_id,
        "mode": "backtest",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "data_source": "dataset",
        "dataset_hash": "dataset-quarantine-costs",
        "git_commit": "deadbeef",
        "validation_mode": "walk-forward",
        "feature_set": "orderflow_on",
        "period": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
        "created_at": (start_dt + timedelta(days=1)).isoformat(),
        "metrics": {"trade_count": 1, "roundtrips": 1, "expectancy": 12.0, "pbo": 0.12, "max_dd": 0.04},
        "trades": [
            {
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "side": "long",
                "entry_time": start_dt.isoformat(),
                "exit_time": end_dt.isoformat(),
                "pnl": 12.0,
                "latency_ms": 18.0,
                "spread_bps": 4.0,
                "features": {"vpin": 0.22, "imbalance": 0.08},
            }
        ],
    }

    store.record_run(run, source_override="backtest")

    episodes = registry.list_experience_episodes(strategy_ids=[strategy_id], sources=["backtest"])
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["evidence_status"] == EVIDENCE_STATUS_QUARANTINE
    assert episode["learning_excluded"] is True
    assert "missing_cost_totals" in episode["evidence_flags"]
    assert registry.list_regime_kpis(strategy_id=strategy_id) == []

    guidance_rows = [row for row in registry.list_strategy_policy_guidance() if str(row.get("strategy_id") or "") == strategy_id]
    assert len(guidance_rows) == 1
    assert "quarantine" in str(guidance_rows[0].get("notes") or "").lower()


def test_experience_store_marks_reconstructed_costs_as_legacy(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    strategy_id = "legacy_reconstructed_costs_v1"

    _seed_run(
        store,
        strategy_id=strategy_id,
        run_id="legacy-costs-run",
        source="backtest",
        start_dt=datetime(2025, 3, 1, tzinfo=timezone.utc),
        gross=14.0,
        fee=1.0,
        spread_cost=1.0,
        slippage_cost=1.0,
        include_costs_breakdown=False,
    )

    episodes = registry.list_experience_episodes(strategy_ids=[strategy_id], sources=["backtest"])
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["evidence_status"] == EVIDENCE_STATUS_LEGACY
    assert episode["learning_excluded"] is False
    assert "costs_breakdown_missing" in episode["evidence_flags"]
    assert "costs_reconstructed_from_trades" in episode["evidence_flags"]
    assert registry.list_regime_kpis(strategy_id=strategy_id)


def test_option_b_engine_marks_legacy_evidence_for_validation(tmp_path: Path) -> None:
    registry = RegistryDB(tmp_path / "registry.sqlite")
    store = ExperienceStore(registry)
    engine = OptionBLearningEngine(registry)
    strategy_id = "trend_pullback_legacy_commit_v1"

    _seed_strategy_history(
        store,
        strategy_id=strategy_id,
        source="shadow",
        gross=12.0,
        fee=1.0,
        spread_cost=1.0,
        slippage_cost=1.0,
        include_commit_hash=False,
    )

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
    assert "legacy_evidence_present" in proposal["metrics"]["reasons"]
    assert proposal["metrics"]["legacy_episode_count"] > 0
    assert result["summary"]["experience_episodes_legacy"] > 0
    assert result["summary"]["experience_episodes_quarantine"] == 0


def test_shadow_run_config_uses_safe_defaults() -> None:
    left = ShadowRunConfig(strategy_id="trend_pullback_orderflow_v2", symbol="BTCUSDT")
    right = ShadowRunConfig(strategy_id="trend_pullback_orderflow_v2", symbol="ETHUSDT")

    assert left.lookback_bars == 300
    assert right.lookback_bars == 300
    assert left.costs is not right.costs

    left.costs.fees_bps = 9.0
    assert right.costs.fees_bps == 5.5

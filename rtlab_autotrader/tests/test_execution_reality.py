from __future__ import annotations

from pathlib import Path

from rtlab_core.execution.reality import (
    ExecutionRealityService,
    load_execution_router_bundle,
    load_execution_safety_bundle,
)


def test_execution_reality_policies_load_from_canonical_yaml() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    explicit_root = repo_root / "config" / "policies"

    safety = load_execution_safety_bundle(repo_root, explicit_root=explicit_root)
    router = load_execution_router_bundle(repo_root, explicit_root=explicit_root)

    assert safety["valid"] is True
    assert router["valid"] is True
    assert safety["source"] == "config/policies/execution_safety.yaml"
    assert router["source"] == "config/policies/execution_router.yaml"
    assert safety["payload"]["execution_safety"]["preflight"]["quote_stale_block_ms"] == 3000
    assert router["payload"]["execution_router"]["conditional_orders_phase1"] is False


def test_execution_reality_db_creates_tables_and_persists_core_rows(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    service = ExecutionRealityService(
        user_data_dir=tmp_path / "user_data",
        repo_root=repo_root,
        explicit_policy_root=repo_root / "config" / "policies",
    )

    intent = service.db.insert_intent(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "limit_price": 50000.0,
            "preflight_status": "pending",
            "policy_hash": service.policy_hash(),
        }
    )
    order = service.db.upsert_order(
        {
            "execution_intent_id": intent["execution_intent_id"],
            "client_order_id": intent["client_order_id"],
            "symbol": "BTCUSDT",
            "family": "spot",
            "environment": "paper",
            "order_status": "CREATED",
        }
    )
    fill = service.db.insert_fill(
        {
            "execution_order_id": order["execution_order_id"],
            "symbol": "BTCUSDT",
            "family": "spot",
            "price": 50000.0,
            "qty": 0.01,
            "commission": 0.25,
        }
    )
    reconcile = service.db.insert_reconcile_event(
        {
            "family": "spot",
            "environment": "paper",
            "reconcile_type": "ack_missing",
            "severity": "WARN",
            "execution_order_id": order["execution_order_id"],
            "client_order_id": order["client_order_id"],
            "details_json": {"reason": "base_test"},
        }
    )
    service.db.trip_kill_switch(
        trigger_type="manual_test",
        severity="BLOCK",
        family="spot",
        symbol="BTCUSDT",
        reason="base_trip",
        auto_actions=[{"action": "cancel_all"}],
    )

    counts = service.db.counts()
    assert "execution_intents" in service.db.table_names()
    assert counts["execution_intents"] == 1
    assert counts["execution_orders"] == 1
    assert counts["execution_fills"] == 1
    assert counts["execution_reconcile_events"] == 1
    assert counts["kill_switch_events"] == 1
    assert fill["commission"] == 0.25
    assert reconcile["details_json"]["reason"] == "base_test"
    assert service.db.kill_switch_status()["armed"] is True
    assert service.db.reset_kill_switch()["armed"] is False


def test_execution_reality_bootstrap_summary_reports_wiring_and_future_split(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    service = ExecutionRealityService(
        user_data_dir=tmp_path / "user_data",
        repo_root=repo_root,
        explicit_policy_root=repo_root / "config" / "policies",
        instrument_registry_service=object(),
        universe_service=object(),
        reporting_bridge_service=object(),
        runs_loader=lambda: [],
    )

    service.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50010.0)
    service.mark_user_stream_status(family="spot", environment="live", available=False, degraded_reason="bootstrap")
    service.set_margin_level(environment="live", level=1.8)

    summary = service.bootstrap_summary()

    assert summary["policy_loaded"] is True
    assert summary["dependencies"]["instrument_registry_service"] is True
    assert summary["cache_sizes"]["market_snapshots"] == 1
    assert "spot" in summary["families_enabled"]
    assert summary["supported_order_types"]["spot"] == ["MARKET", "LIMIT"]

    try:
        service.preflight({})
    except NotImplementedError as exc:
        assert "parte 3.2" in str(exc).lower()
    else:
        raise AssertionError("preflight base debe quedar pendiente para la parte 3.2")

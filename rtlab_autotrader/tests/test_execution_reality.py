from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from rtlab_core.execution.reality import (
    ExecutionRealityService,
    load_execution_router_bundle,
    load_execution_safety_bundle,
)


def _iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _default_filters() -> dict[str, Any]:
    return {
        "price_filter": {"min_price": "0.01", "max_price": "1000000", "tick_size": "0.01"},
        "lot_size": {"min_qty": "0.0001", "max_qty": "1000", "step_size": "0.0001"},
        "market_lot_size": {"min_qty": "0.0001", "max_qty": "1000", "step_size": "0.0001"},
        "min_notional": {"min_notional": "10.0"},
        "notional": {"min_notional": "10.0"},
    }


class _FakeRegistryDB:
    def __init__(
        self,
        *,
        instrument_row: dict[str, Any],
        snapshot_fetched_at: str | None,
        capability_snapshot: dict[str, Any] | None,
    ) -> None:
        self._instrument_row = instrument_row
        self._live_snapshot = (
            {
                "snapshot_id": "SNAP-LIVE",
                "fetched_at": snapshot_fetched_at,
                "success": True,
                "symbol_count": 1,
                "diff_severity": "OK",
            }
            if snapshot_fetched_at is not None
            else None
        )
        self._testnet_snapshot = (
            {
                "snapshot_id": "SNAP-TESTNET",
                "fetched_at": snapshot_fetched_at,
                "success": True,
                "symbol_count": 1,
                "diff_severity": "OK",
            }
            if snapshot_fetched_at is not None
            else None
        )
        self._capability_snapshot = capability_snapshot

    def registry_rows(self, *, family: str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
        row = self._instrument_row
        if family and str(row.get("family") or "") != str(family):
            return []
        return [dict(row)]

    def latest_snapshot(self, family: str, environment: str, success_only: bool = True) -> dict[str, Any] | None:
        if str(self._instrument_row.get("family") or "") != str(family):
            return None
        if environment == "testnet":
            return dict(self._testnet_snapshot) if self._testnet_snapshot else None
        return dict(self._live_snapshot) if self._live_snapshot else None

    def latest_capability_snapshot(self, family: str, environment: str) -> dict[str, Any] | None:
        if str(self._instrument_row.get("family") or "") != str(family):
            return None
        if self._capability_snapshot is None:
            return None
        payload = dict(self._capability_snapshot)
        payload["environment"] = environment
        return payload

    def snapshot_items(self, snapshot_id: str) -> list[dict[str, Any]]:
        valid_ids = {"SNAP-LIVE", "SNAP-TESTNET"}
        if snapshot_id not in valid_ids:
            return []
        return [
            {
                "instrument_id": self._instrument_row["instrument_id"],
                "symbol": self._instrument_row["symbol"],
                "family": self._instrument_row["family"],
                "status": self._instrument_row["status"],
                "filter_summary": self._instrument_row["filter_summary"],
                "permission_summary": self._instrument_row.get("permission_summary") or {},
                "live_eligible": self._instrument_row["live_eligible"],
                "testnet_eligible": self._instrument_row["testnet_eligible"],
                "paper_eligible": self._instrument_row["paper_eligible"],
            }
        ]


class _FakeRegistryService:
    def __init__(
        self,
        *,
        family: str,
        instrument_row: dict[str, Any],
        snapshot_fetched_at: str | None,
        capability_snapshot: dict[str, Any] | None,
    ) -> None:
        self.family = family
        self.db = _FakeRegistryDB(
            instrument_row=instrument_row,
            snapshot_fetched_at=snapshot_fetched_at,
            capability_snapshot=capability_snapshot,
        )

    def policy(self) -> dict[str, Any]:
        return {
            "freshness": {
                "warn_if_snapshot_older_than_hours": 24,
                "block_if_snapshot_older_than_hours": 72,
            }
        }

    def live_parity_matrix(self) -> dict[str, dict[str, Any]]:
        supported = {"spot", "margin", "usdm_futures", "coinm_futures"}
        matrix: dict[str, dict[str, Any]] = {}
        for family_name in supported:
            enabled = family_name == self.family
            matrix[family_name] = {
                "live": {
                    "supported": enabled,
                    "catalog_ready": enabled,
                    "snapshot_fresh": enabled,
                    "policy_loaded": True,
                    "capabilities_known": enabled and self.db.latest_capability_snapshot(family_name, "live") is not None,
                    "live_parity_base_ready": enabled and self.db.latest_capability_snapshot(family_name, "live") is not None,
                }
            }
        return matrix


class _FakeUniverseService:
    def __init__(self, *, matched: bool) -> None:
        self._matched = matched

    def membership(self, *, family: str, symbol: str, venue: str = "binance") -> dict[str, Any]:
        return {
            "matched": self._matched,
            "universes": ["core_test"] if self._matched else [],
            "snapshot_source": {"snapshot_id": "SNAP-LIVE", "environment": "live"},
            "policy_source": {"source": "config/policies/universes.yaml"},
        }


class _FakeReportingDB:
    def __init__(self, *, family: str, available: bool, fetched_at: str | None) -> None:
        self._family = family
        self._available = available
        self._fetched_at = fetched_at

    def cost_source_snapshots(self) -> list[dict[str, Any]]:
        if not self._available:
            return []
        return [
            {
                "family": self._family,
                "environment": "live",
                "source_kind": "binance_account_commission",
                "fetched_at": self._fetched_at,
                "success": True,
            }
        ]


class _FakeReportingBridge:
    def __init__(self, *, family: str, available: bool, fresh: bool, fetched_at: str | None = None) -> None:
        self.db = _FakeReportingDB(family=family, available=available, fetched_at=fetched_at or _iso_hours_ago(1))
        self._fresh = fresh

    def cost_stack(self) -> dict[str, Any]:
        return {
            "estimation": {
                "spread_bps_default": 4.0,
                "slippage_bps_default": 6.0,
                "block_if_missing_real_cost_source_in_live": True,
                "allow_fallback_estimation_in_paper": True,
            },
            "alerts": {"warn_if_fee_source_stale_hours_gt": 24},
        }

    def _latest_cost_source_status(self, *, family: str) -> str:
        return "fresh" if self._fresh else "stale"


def _instrument_row(
    *,
    family: str = "spot",
    status: str = "TRADING",
    live_eligible: bool = True,
    testnet_eligible: bool = True,
    paper_eligible: bool = True,
    filter_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = "BTCUSDT" if family != "coinm_futures" else "BTCUSD_PERP"
    quote_asset = "USDT" if family != "coinm_futures" else "USD"
    return {
        "instrument_id": f"binance:{family}:{symbol}",
        "venue": "binance",
        "family": family,
        "symbol": symbol,
        "base_asset": "BTC",
        "quote_asset": quote_asset,
        "contract_type": "PERPETUAL" if "futures" in family else None,
        "margin_asset": "USDT" if family == "usdm_futures" else ("BTC" if family == "coinm_futures" else None),
        "status": status,
        "is_active": True,
        "live_eligible": live_eligible,
        "paper_eligible": paper_eligible,
        "testnet_eligible": testnet_eligible,
        "catalog_source": "binance_exchange_info",
        "first_seen_at": _iso_hours_ago(48),
        "last_seen_at": _iso_hours_ago(1),
        "last_snapshot_id": "SNAP-LIVE",
        "raw_hash": "hash",
        "archived_at": None,
        "filter_summary": filter_summary or _default_filters(),
        "permission_summary": {"permissions": ["SPOT", "MARGIN"]},
    }


def _capability_snapshot(*, can_trade: bool = True, can_margin: bool = True) -> dict[str, Any]:
    return {
        "capability_snapshot_id": "CAP-LIVE",
        "capability_source": "binance_account",
        "can_read_market_data": True,
        "can_trade": can_trade,
        "can_margin": can_margin,
        "can_user_data": True,
        "can_testnet": True,
        "fetched_at": _iso_hours_ago(1),
    }


def _build_service(
    tmp_path: Path,
    *,
    family: str = "spot",
    snapshot_fetched_at: str | None = None,
    capability_snapshot: dict[str, Any] | None = None,
    universe_matched: bool = True,
    fee_source_available: bool = True,
    fee_source_fresh: bool = True,
    instrument_row: dict[str, Any] | None = None,
) -> ExecutionRealityService:
    repo_root = Path(__file__).resolve().parents[2]
    row = instrument_row or _instrument_row(family=family)
    return ExecutionRealityService(
        user_data_dir=tmp_path / "user_data",
        repo_root=repo_root,
        explicit_policy_root=repo_root / "config" / "policies",
        instrument_registry_service=_FakeRegistryService(
            family=family,
            instrument_row=row,
            snapshot_fetched_at=snapshot_fetched_at or _iso_hours_ago(1),
            capability_snapshot=capability_snapshot or _capability_snapshot(),
        ),
        universe_service=_FakeUniverseService(matched=universe_matched),
        reporting_bridge_service=_FakeReportingBridge(
            family=family,
            available=fee_source_available,
            fresh=fee_source_fresh,
        ),
        runs_loader=lambda: [],
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


def test_execution_reality_bootstrap_summary_and_live_safety_wiring(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    service.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50010.0)
    service.mark_user_stream_status(family="spot", environment="live", available=False, degraded_reason="rest_fallback")
    service.set_margin_level(environment="live", level=1.8)

    bootstrap = service.bootstrap_summary()
    summary = service.live_safety_summary()

    assert bootstrap["policy_loaded"] is True
    assert bootstrap["dependencies"]["instrument_registry_service"] is True
    assert bootstrap["cache_sizes"]["market_snapshots"] == 1
    assert summary["execution_policy_loaded"] is True
    assert summary["capabilities_known"] is True
    assert summary["degraded_mode"] is True
    assert summary["overall_status"] == "WARN"


def test_preflight_accepts_live_order_and_normalizes_price_qty(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    result = service.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.001234,
            "price": 50000.129,
            "market_snapshot": {
                "bid": 50000.0,
                "ask": 50000.2,
                "quote_ts_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
                "orderbook_ts_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            },
        }
    )

    assert result["allowed"] is True
    assert result["fail_closed"] is False
    assert result["blocking_reasons"] == []
    assert result["normalized_order_preview"]["quantity"] == 0.0012
    assert result["normalized_order_preview"]["limit_price"] == 50000.12
    assert result["snapshot_source"]["universe_membership"]["matched"] is True
    assert result["estimated_costs"]["total_cost_estimated"] > 0


def test_preflight_blocks_stale_market_data_in_live(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    old_ms = int((datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp() * 1000)

    result = service.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": {
                "bid": 50000.0,
                "ask": 50001.0,
                "quote_ts_ms": old_ms,
                "orderbook_ts_ms": old_ms,
            },
        }
    )

    assert result["allowed"] is False
    assert result["fail_closed"] is True
    assert "quote_stale" in result["blocking_reasons"]
    assert "orderbook_stale" in result["blocking_reasons"]


def test_preflight_blocks_missing_fee_source_in_live(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot", fee_source_available=False, fee_source_fresh=False)

    result = service.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": {
                "bid": 50000.0,
                "ask": 50001.0,
            },
        }
    )

    assert result["allowed"] is False
    assert result["fail_closed"] is True
    assert "fee_source_missing_in_live" in result["blocking_reasons"]


def test_preflight_blocks_max_notional_and_open_order_limit(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    for idx in range(6):
        service.db.upsert_order(
            {
                "execution_intent_id": f"intent-{idx}",
                "client_order_id": f"client-{idx}",
                "symbol": "BTCUSDT",
                "family": "spot",
                "environment": "live",
                "order_status": "NEW",
            }
        )

    result = service.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.2,
            "price": 50000.0,
            "market_snapshot": {
                "bid": 50000.0,
                "ask": 50001.0,
            },
        }
    )

    assert result["allowed"] is False
    assert "max_notional_per_order_exceeded" in result["blocking_reasons"]
    assert "max_open_orders_per_symbol_reached" in result["blocking_reasons"]


def test_preflight_blocks_margin_capability_and_margin_level(tmp_path: Path) -> None:
    service = _build_service(
        tmp_path,
        family="margin",
        capability_snapshot=_capability_snapshot(can_trade=True, can_margin=False),
        instrument_row=_instrument_row(family="margin"),
    )
    service.set_margin_level(environment="live", level=1.2)

    result = service.preflight(
        {
            "family": "margin",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": {
                "bid": 50000.0,
                "ask": 50001.0,
            },
        }
    )

    assert result["allowed"] is False
    assert result["fail_closed"] is True
    assert "margin_capability_missing" in result["blocking_reasons"]
    assert "margin_level_blocked" in result["blocking_reasons"]

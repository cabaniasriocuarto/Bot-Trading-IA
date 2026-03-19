from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from rtlab_core.execution.reality import ExecutionRealityService
from rtlab_core.validation import ValidationService, load_validation_gates_bundle


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_ROOT = REPO_ROOT / "config" / "policies"


def _iso_hours_ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _fresh_market_snapshot(*, bid: float = 50000.0, ask: float = 50001.0) -> dict[str, Any]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "bid": bid,
        "ask": ask,
        "quote_ts_ms": now_ms,
        "orderbook_ts_ms": now_ms,
    }


def _instrument_row(
    *,
    family: str = "spot",
    live_eligible: bool = True,
    testnet_eligible: bool = True,
    paper_eligible: bool = True,
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
        "status": "TRADING",
        "price_tick": 0.01,
        "qty_step": 0.0001 if family != "coinm_futures" else 1.0,
        "min_qty": 0.0001 if family != "coinm_futures" else 1.0,
        "max_qty": 1000.0,
        "min_notional": 10.0,
        "notional": 10.0,
        "filter_summary": {
            "price_filter": {"min_price": "0.01", "max_price": "1000000", "tick_size": "0.01"},
            "lot_size": {"min_qty": "0.0001", "max_qty": "1000", "step_size": "0.0001"},
            "market_lot_size": {"min_qty": "0.0001", "max_qty": "1000", "step_size": "0.0001"},
            "min_notional": {"min_notional": "10.0"},
            "notional": {"min_notional": "10.0"},
        },
        "permission_summary": {"permissions": ["SPOT", "MARGIN"] if family in {"spot", "margin"} else []},
        "live_eligible": live_eligible,
        "testnet_eligible": testnet_eligible,
        "paper_eligible": paper_eligible,
    }


class _FakeRegistryDB:
    def __init__(
        self,
        *,
        instrument_row: dict[str, Any],
        snapshot_fetched_at: str,
        capability_snapshot: dict[str, Any],
    ) -> None:
        self._instrument_row = instrument_row
        self._snapshot_fetched_at = snapshot_fetched_at
        self._capability_snapshot = capability_snapshot

    def registry_rows(self, *, family: str | None = None, active_only: bool = False) -> list[dict[str, Any]]:
        row = self._instrument_row
        if family and str(row.get("family") or "") != str(family):
            return []
        return [dict(row)]

    def latest_snapshot(self, family: str, environment: str, success_only: bool = True) -> dict[str, Any] | None:
        if str(self._instrument_row.get("family") or "") != str(family):
            return None
        return {
            "snapshot_id": f"SNAP-{family.upper()}-{environment.upper()}",
            "fetched_at": self._snapshot_fetched_at,
            "success": True,
            "symbol_count": 1,
            "diff_severity": "OK",
        }

    def latest_capability_snapshot(self, family: str, environment: str) -> dict[str, Any] | None:
        if str(self._instrument_row.get("family") or "") != str(family):
            return None
        payload = dict(self._capability_snapshot)
        payload["environment"] = environment
        return payload


class _FakeRegistryService:
    def __init__(
        self,
        *,
        repo_root: Path,
        explicit_policy_root: Path,
        family: str,
        testnet_supported: bool = True,
        live_supported: bool = True,
        snapshot_fetched_at: str | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.explicit_policy_root = explicit_policy_root
        self.family = family
        self.testnet_supported = testnet_supported
        self.live_supported = live_supported
        self.db = _FakeRegistryDB(
            instrument_row=_instrument_row(
                family=family,
                live_eligible=live_supported,
                testnet_eligible=testnet_supported,
                paper_eligible=True,
            ),
            snapshot_fetched_at=snapshot_fetched_at or _iso_hours_ago(1),
            capability_snapshot={
                "family": family,
                "can_read_market_data": True,
                "can_trade": True,
                "can_margin": family in {"margin", "usdm_futures", "coinm_futures"},
                "can_user_data": True,
                "can_testnet": testnet_supported,
                "capability_source": "fake_capabilities",
                "notes": {},
                "fetched_at": snapshot_fetched_at or _iso_hours_ago(1),
            },
        )

    def policy(self) -> dict[str, Any]:
        return {
            "freshness": {
                "warn_if_snapshot_older_than_hours": 24,
                "block_if_snapshot_older_than_hours": 72,
            }
        }

    def policy_source(self) -> dict[str, Any]:
        return {
            "path": "config/policies/instrument_registry.yaml",
            "source_root": str(self.explicit_policy_root),
            "source_hash": "registry-source-hash",
            "policy_hash": "registry-policy-hash",
            "source": "config/policies/instrument_registry.yaml",
            "valid": True,
            "errors": [],
            "warnings": [],
            "fallback_used": False,
            "selected_role": "monorepo_root",
            "canonical_root": str(self.explicit_policy_root),
            "canonical_role": "monorepo_root",
            "divergent_candidates": [],
        }

    def live_parity_matrix(self) -> dict[str, dict[str, Any]]:
        matrix: dict[str, dict[str, Any]] = {}
        for family_name in ("spot", "margin", "usdm_futures", "coinm_futures"):
            live_supported = self.live_supported if family_name == self.family else False
            testnet_supported = self.testnet_supported if family_name == self.family else False
            matrix[family_name] = {
                "live": {
                    "supported": live_supported,
                    "catalog_ready": live_supported,
                    "snapshot_fresh": live_supported,
                    "policy_loaded": True,
                    "capabilities_known": live_supported,
                    "live_parity_base_ready": live_supported,
                },
                "testnet": {
                    "supported": testnet_supported,
                    "catalog_ready": testnet_supported,
                    "snapshot_fresh": testnet_supported,
                    "policy_loaded": True,
                    "capabilities_known": testnet_supported,
                    "live_parity_base_ready": testnet_supported,
                },
            }
        return matrix

    def capabilities_summary(self) -> dict[str, Any]:
        families: dict[str, Any] = {}
        for family_name in ("spot", "margin", "usdm_futures", "coinm_futures"):
            live_supported = self.live_supported if family_name == self.family else False
            testnet_supported = self.testnet_supported if family_name == self.family else False
            live_payload = {
                "family": family_name,
                "environment": "live",
                "can_trade": live_supported,
                "can_margin": family_name in {"margin", "usdm_futures", "coinm_futures"} and live_supported,
                "can_user_data": live_supported,
                "can_testnet": testnet_supported,
            }
            testnet_payload = {
                "family": family_name,
                "environment": "testnet",
                "can_trade": testnet_supported,
                "can_margin": False,
                "can_user_data": testnet_supported,
                "can_testnet": testnet_supported,
            }
            families[family_name] = {
                "live": live_payload,
                "testnet": testnet_payload,
                "can_trade": live_supported or testnet_supported,
                "can_testnet": testnet_supported,
                "can_user_data": live_supported or testnet_supported,
                "capability_freshness": {
                    "live": {"status": "fresh"},
                    "testnet": {"status": "fresh"},
                },
                "source": ["fake_capabilities"],
            }
        return {"families": families, "policy_source": self.policy_source()}


class _FakeReportingDB:
    def __init__(self, *, family: str) -> None:
        self._family = family
        self._trade_rows: list[dict[str, Any]] = []

    def trade_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._trade_rows]

    def cost_source_snapshots(self) -> list[dict[str, Any]]:
        now = _iso_hours_ago(1)
        return [
            {
                "family": self._family,
                "environment": "live",
                "source_kind": "cost_source_binding",
                "fetched_at": now,
                "success": True,
            },
            {
                "family": self._family,
                "environment": "testnet",
                "source_kind": "cost_source_binding",
                "fetched_at": now,
                "success": True,
            },
        ]


class _FakeReportingBridge:
    def __init__(self, *, family: str) -> None:
        self.db = _FakeReportingDB(family=family)

    def cost_stack(self) -> dict[str, Any]:
        return {
            "alerts": {"warn_if_fee_source_stale_hours_gt": 24},
        }

    def cost_stack_bundle(self) -> dict[str, Any]:
        return {
            "policy_hash": "cost-stack-policy-hash",
            "source_hash": "cost-stack-source-hash",
            "valid": True,
            "source": "config/policies/cost_stack.yaml",
        }

    def policy_source(self) -> dict[str, Any]:
        return {
            "cost_stack": {
                "hash": "cost-stack-source-hash",
                "policy_hash": "cost-stack-policy-hash",
                "source": "config/policies/cost_stack.yaml",
                "valid": True,
            }
        }

    def _latest_cost_source_status(self, *, family: str) -> str:
        return "fresh"

    def upsert_execution_trade_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        merged = {
            str(row.get("trade_cost_id") or ""): dict(row)
            for row in self.db._trade_rows
            if str(row.get("trade_cost_id") or "")
        }
        for row in rows:
            merged[str(row.get("trade_cost_id") or "")] = dict(row)
        self.db._trade_rows = list(merged.values())
        return {"ok": True, "trade_rows_upserted": len(rows), "trade_rows_total": len(self.db._trade_rows)}


def _build_services(
    tmp_path: Path,
    *,
    family: str = "spot",
    testnet_supported: bool = True,
    live_supported: bool = True,
) -> tuple[ExecutionRealityService, ValidationService]:
    registry = _FakeRegistryService(
        repo_root=REPO_ROOT,
        explicit_policy_root=POLICY_ROOT,
        family=family,
        testnet_supported=testnet_supported,
        live_supported=live_supported,
    )
    reporting = _FakeReportingBridge(family=family)
    execution = ExecutionRealityService(
        user_data_dir=tmp_path,
        repo_root=REPO_ROOT,
        explicit_policy_root=POLICY_ROOT,
        instrument_registry_service=registry,
        universe_service=None,
        reporting_bridge_service=reporting,
        runs_loader=lambda: [],
    )
    validation = ValidationService(
        user_data_dir=tmp_path,
        repo_root=REPO_ROOT,
        explicit_policy_root=POLICY_ROOT,
        execution_service=execution,
        reporting_bridge_service=reporting,
        instrument_registry_service=registry,
        universe_service=None,
    )
    return execution, validation


def _seed_order(
    execution: ExecutionRealityService,
    *,
    environment: str,
    family: str,
    when: datetime,
    status: str = "FILLED",
    with_fill: bool = True,
    reject_reason: str | None = None,
    cost_mismatch: bool = False,
    gross_pnl: float = 100.0,
    net_pnl: float = 95.0,
) -> dict[str, Any]:
    symbol = "BTCUSDT" if family != "coinm_futures" else "BTCUSD_PERP"
    created_at = when.astimezone(timezone.utc).isoformat()
    intent = execution.db.insert_intent(
        {
            "created_at": created_at,
            "submitted_at": created_at,
            "venue": "binance",
            "family": family,
            "environment": environment,
            "mode": environment if environment != "paper" else "paper",
            "symbol": symbol,
            "side": "BUY",
            "order_type": "LIMIT",
            "client_order_id": f"CID-{uuid4().hex[:12]}",
            "preflight_status": "submitted",
            "estimated_total_cost": 5.0,
            "estimated_fee": 1.0,
            "estimated_slippage_bps": 2.0,
            "policy_hash": execution.policy_hash(),
            "raw_request_json": {"seeded": True},
        }
    )
    order = execution.db.upsert_order(
        {
            "execution_intent_id": intent["execution_intent_id"],
            "client_order_id": intent["client_order_id"],
            "venue_order_id": f"OID-{uuid4().hex[:12]}",
            "symbol": symbol,
            "family": family,
            "environment": environment,
            "order_status": status,
            "submitted_at": created_at,
            "acknowledged_at": created_at,
            "price": 50000.0,
            "orig_qty": 0.01,
            "executed_qty": 0.01 if with_fill else 0.0,
            "cum_quote_qty": 500.0 if with_fill else 0.0,
            "avg_fill_price": 50000.0 if with_fill else None,
            "reject_reason": reject_reason,
            "raw_ack_json": {"seeded": True},
            "raw_last_status_json": {"status": status},
        }
    )
    fills: list[dict[str, Any]] = []
    if with_fill:
        fill = execution.db.insert_fill(
            {
                "execution_order_id": order["execution_order_id"],
                "venue_trade_id": f"TID-{uuid4().hex[:10]}",
                "fill_time": created_at,
                "symbol": symbol,
                "family": family,
                "price": 50000.0,
                "qty": 0.01,
                "quote_qty": 500.0,
                "commission": 1.0,
                "commission_asset": "USDT",
                "spread_realized": 2.0,
                "slippage_realized": 2.0,
                "gross_pnl": gross_pnl,
                "net_pnl": net_pnl,
                "cost_source_json": {"source_kind": "execution_reality_fill"},
                "provenance_json": {"trade_ref": "", "source_kind": "execution_reality_fill"},
                "raw_fill_json": {"seeded": True},
            }
        )
        fills.append(fill)
        execution._sync_fills_to_reporting_bridge(order=order, intent=intent, fills=fills)
    if cost_mismatch:
        execution.db.insert_reconcile_event(
            {
                "created_at": created_at,
                "family": family,
                "environment": environment,
                "reconcile_type": "cost_mismatch",
                "severity": "BLOCK",
                "execution_order_id": order["execution_order_id"],
                "details_json": {"seeded": True},
            }
        )
    return {"intent": intent, "order": order, "fills": fills}


def _seed_stage_pass(execution: ExecutionRealityService, *, stage: str, family: str, count: int) -> None:
    now = datetime.now(timezone.utc)
    environment = {"PAPER": "paper", "TESTNET": "testnet", "CANARY": "live"}[stage]
    hours_step = 12 if stage != "CANARY" else 1
    base = now - timedelta(hours=max(count // 2, 1) * hours_step)
    for index in range(count):
        when = base + timedelta(hours=index * hours_step)
        _seed_order(execution, environment=environment, family=family, when=when)
    execution.set_market_snapshot(family=family, environment="live", symbol="BTCUSDT" if family != "coinm_futures" else "BTCUSD_PERP", **_fresh_market_snapshot())
    execution.set_market_snapshot(family=family, environment="testnet", symbol="BTCUSDT" if family != "coinm_futures" else "BTCUSD_PERP", **_fresh_market_snapshot())
    execution.mark_user_stream_status(family=family, environment="testnet", available=True)
    execution.mark_user_stream_status(family=family, environment="live", available=True)


def test_validation_gates_bundle_loads_from_canonical_yaml() -> None:
    bundle = load_validation_gates_bundle(REPO_ROOT, explicit_root=POLICY_ROOT)
    assert bundle["valid"] is True
    assert bundle["source"] == "config/policies/validation_gates.yaml"
    assert bundle["source_hash"]
    assert bundle["policy_hash"]
    assert bundle["source_hash"] != bundle["policy_hash"]


def test_validation_gates_bundle_falls_back_fail_closed_when_yaml_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies = repo_root / "config" / "policies"
    root_policies.mkdir(parents=True, exist_ok=True)
    bundle = load_validation_gates_bundle(repo_root, explicit_root=root_policies)
    assert bundle["valid"] is False
    assert bundle["source"] == "default_fail_closed_minimal"
    assert bundle["policy_hash"]
    assert bundle["errors"]


def test_validation_service_paper_gate_pass_and_persists_evidence(tmp_path: Path) -> None:
    execution, validation = _build_services(tmp_path, family="spot")
    _seed_stage_pass(execution, stage="PAPER", family="spot", count=30)

    payload = validation.evaluate(stage="PAPER", family="spot")
    run = payload["validation_run"]
    gate_results = payload["gate_results"]

    assert run["result"] == "PASS"
    assert run["total_orders"] == 30
    assert any(row["gate_name"] == "min_orders" and row["threshold_value"] == 30.0 for row in gate_results)
    assert any(row["evidence_type"] == "validation_policy" for row in payload["stage_evidence"])
    assert validation.readiness()["readiness_by_stage"]["paper"]["ready"] is True
    assert validation.readiness()["live_serio_ready"] is False


def test_validation_service_paper_gate_block_on_rejects_and_cost_mismatch(tmp_path: Path) -> None:
    execution, validation = _build_services(tmp_path, family="spot")
    now = datetime.now(timezone.utc) - timedelta(days=3)
    for index in range(30):
        when = now + timedelta(hours=index * 2)
        if index < 3:
            _seed_order(
                execution,
                environment="paper",
                family="spot",
                when=when,
                status="REJECTED",
                with_fill=False,
                reject_reason="seeded_reject",
                cost_mismatch=True,
            )
        else:
            _seed_order(execution, environment="paper", family="spot", when=when)

    payload = validation.evaluate(stage="PAPER", family="spot")
    assert payload["validation_run"]["result"] == "BLOCK"
    assert "max_reject_rate" in payload["validation_run"]["blocking_reasons_json"]


def test_validation_service_testnet_gate_block_on_metrics(tmp_path: Path) -> None:
    execution, validation = _build_services(tmp_path, family="spot")
    _seed_stage_pass(execution, stage="PAPER", family="spot", count=30)
    validation.evaluate(stage="PAPER", family="spot")

    now = datetime.now(timezone.utc) - timedelta(days=2)
    for index in range(20):
        when = now + timedelta(hours=index * 2)
        if index < 2:
            _seed_order(
                execution,
                environment="testnet",
                family="spot",
                when=when,
                status="REJECTED",
                with_fill=False,
                reject_reason="seeded_testnet_reject",
                cost_mismatch=True,
            )
        else:
            _seed_order(execution, environment="testnet", family="spot", when=when)
    execution.mark_user_stream_status(family="spot", environment="testnet", available=False, degraded_reason="stream_down")

    payload = validation.evaluate(stage="TESTNET", family="spot")
    assert payload["validation_run"]["result"] == "BLOCK"
    assert "max_reject_rate" in payload["validation_run"]["blocking_reasons_json"]
    assert payload["validation_run"]["degraded_mode_seen"] is True


def test_validation_service_testnet_gate_pass_and_preserves_live_serio_block(tmp_path: Path) -> None:
    execution, validation = _build_services(tmp_path, family="spot")
    _seed_stage_pass(execution, stage="PAPER", family="spot", count=30)
    validation.evaluate(stage="PAPER", family="spot")
    _seed_stage_pass(execution, stage="TESTNET", family="spot", count=20)

    payload = validation.evaluate(stage="TESTNET", family="spot")
    readiness = validation.readiness()

    assert payload["validation_run"]["result"] == "PASS"
    assert payload["validation_run"]["degraded_mode_seen"] is False
    assert readiness["readiness_by_stage"]["paper"]["ready"] is True
    assert readiness["readiness_by_stage"]["testnet"]["ready"] is True
    assert readiness["live_serio_ready"] is False


def test_validation_service_canary_gate_block_on_kill_switch_and_margin(tmp_path: Path) -> None:
    execution, validation = _build_services(tmp_path, family="usdm_futures")
    _seed_stage_pass(execution, stage="PAPER", family="usdm_futures", count=30)
    validation.evaluate(stage="PAPER", family="usdm_futures")
    _seed_stage_pass(execution, stage="TESTNET", family="usdm_futures", count=20)
    validation.evaluate(stage="TESTNET", family="usdm_futures")
    _seed_stage_pass(execution, stage="CANARY", family="usdm_futures", count=10)
    execution.trip_kill_switch(trigger_type="manual", severity="BLOCK", family="usdm_futures", reason="seeded_trip")
    execution.set_margin_level(environment="live", level=0.1)
    execution.db.insert_reconcile_event(
        {
            "family": "usdm_futures",
            "environment": "live",
            "reconcile_type": "status_mismatch",
            "severity": "BLOCK",
            "details_json": {"seeded": True},
        }
    )

    payload = validation.evaluate(stage="CANARY", family="usdm_futures")
    assert payload["validation_run"]["result"] == "BLOCK"
    assert "kill_switch_inactive" in payload["validation_run"]["blocking_reasons_json"]
    assert "margin_guard" in payload["validation_run"]["blocking_reasons_json"]


def test_validation_service_canary_pass_sets_live_serio_ready_without_auto_promotion(tmp_path: Path) -> None:
    execution, validation = _build_services(tmp_path, family="spot")
    _seed_stage_pass(execution, stage="PAPER", family="spot", count=30)
    validation.evaluate(stage="PAPER", family="spot")
    _seed_stage_pass(execution, stage="TESTNET", family="spot", count=20)
    validation.evaluate(stage="TESTNET", family="spot")
    _seed_stage_pass(execution, stage="CANARY", family="spot", count=10)

    payload = validation.evaluate(stage="CANARY", family="spot")
    readiness = validation.readiness()
    live_serio_attempt = validation.evaluate(stage="LIVE_SERIO", family="spot")

    assert payload["validation_run"]["result"] == "PASS"
    assert readiness["readiness_by_stage"]["canary"]["ready"] is True
    assert readiness["live_serio_ready"] is True
    assert validation.current_stage() == "LIVE_SERIO"
    assert live_serio_attempt["result"] == "BLOCK"
    assert "live_serio_not_evaluated_in_rtlops_36" in live_serio_attempt["blocking_reasons"]

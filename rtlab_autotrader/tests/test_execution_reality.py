from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from rtlab_core.execution.binance_adapter import map_exchange_error
from rtlab_core.execution.reality import (
    ExecutionRealityService,
    clear_execution_policy_cache,
    load_execution_router_bundle,
    load_execution_safety_bundle,
    utc_now_iso,
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
        "max_num_orders": {"limit": 25, "max_num_orders": 25},
        "filter_types_present": ["LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL", "NOTIONAL", "PRICE_FILTER"],
    }


def _fresh_market_snapshot(*, bid: float = 50000.0, ask: float = 50001.0) -> dict[str, Any]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return {
        "bid": bid,
        "ask": ask,
        "quote_ts_ms": now_ms,
        "orderbook_ts_ms": now_ms,
    }


def _spot_create_ack(
    *,
    client_order_id: str,
    status: str = "NEW",
    executed_qty: str = "0.00000000",
    cum_quote_qty: str = "0.00000000",
    order_id: int = 123456,
    price: str = "50000.00",
    orig_qty: str = "0.01000000",
    fills: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "symbol": "BTCUSDT",
        "orderId": order_id,
        "clientOrderId": client_order_id,
        "transactTime": now_ms,
        "price": price,
        "origQty": orig_qty,
        "executedQty": executed_qty,
        "cummulativeQuoteQty": cum_quote_qty,
        "status": status,
        "timeInForce": "GTC",
        "type": "LIMIT",
        "side": "BUY",
    }
    if fills is not None:
        payload["fills"] = fills
    return payload


def _spot_execution_report(
    *,
    client_order_id: str,
    execution_type: str,
    order_status: str,
    last_fill_qty: str = "0.00000000",
    cumulative_filled_qty: str = "0.00000000",
    last_fill_price: str = "0.00000000",
    execution_id: int = 7001,
    order_id: int = 123456,
    trade_id: int = 7701,
    commission: str = "0.00000000",
    commission_asset: str | None = None,
    maker: bool | None = None,
) -> dict[str, Any]:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "e": "executionReport",
        "E": now_ms,
        "s": "BTCUSDT",
        "c": client_order_id,
        "S": "BUY",
        "o": "LIMIT",
        "f": "GTC",
        "q": "0.01000000",
        "p": "50000.00",
        "x": execution_type,
        "X": order_status,
        "i": order_id,
        "I": execution_id,
        "t": trade_id,
        "l": last_fill_qty,
        "z": cumulative_filled_qty,
        "L": last_fill_price,
        "Z": str(float(cumulative_filled_qty or "0") * float(last_fill_price or "0")),
        "Y": str(float(last_fill_qty or "0") * float(last_fill_price or "0")),
        "n": commission,
        "T": now_ms,
    }
    if commission_asset is not None:
        payload["N"] = commission_asset
    if maker is not None:
        payload["m"] = maker
    return payload


class _HTTPResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload) if not isinstance(payload, str) else payload

    @property
    def content(self) -> bytes:
        if self._payload is None:
            return b""
        if isinstance(self._payload, bytes):
            return self._payload
        if isinstance(self._payload, str):
            return self._payload.encode("utf-8")
        return json.dumps(self._payload).encode("utf-8")

    def json(self) -> Any:
        return self._payload


class _FakeWebSocket:
    def __init__(self, messages: list[Any]) -> None:
        self._messages = list(messages)
        self.sent: list[str] = []
        self.closed = False

    async def __aenter__(self) -> "_FakeWebSocket":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        self.closed = True
        return False

    async def recv(self) -> Any:
        if self._messages:
            item = self._messages.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        await asyncio.sleep(3600)
        return ""

    async def send(self, payload: str) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True


class _FailingAsyncContextManager:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def __aenter__(self) -> Any:
        raise self._exc

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False


class _FakeConnectFactory:
    def __init__(self, sessions: list[Any]) -> None:
        self._sessions = list(sessions)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url: str, **kwargs) -> Any:  # noqa: ANN003
        self.calls.append({"url": url, "kwargs": kwargs})
        if not self._sessions:
            return _FailingAsyncContextManager(RuntimeError("no_fake_session"))
        next_item = self._sessions.pop(0)
        if isinstance(next_item, Exception):
            return _FailingAsyncContextManager(next_item)
        return next_item


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
        self._trade_rows: list[dict[str, Any]] = []

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

    def trade_rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._trade_rows]


class _FakeReportingBridge:
    def __init__(self, *, family: str, available: bool, fresh: bool, fetched_at: str | None = None) -> None:
        self.db = _FakeReportingDB(family=family, available=available, fetched_at=fetched_at or _iso_hours_ago(1))
        self._fresh = fresh
        self._policy_hash = "cost-stack-policy-hash"
        self._source_hash = "cost-stack-source-hash"

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

    def cost_stack_bundle(self) -> dict[str, Any]:
        return {
            "policy_hash": self._policy_hash,
            "source_hash": self._source_hash,
            "valid": True,
            "source": "config/policies/cost_stack.yaml",
        }

    def policy_source(self) -> dict[str, Any]:
        return {
            "cost_stack": {
                "hash": self._source_hash,
                "policy_hash": self._policy_hash,
                "source": "config/policies/cost_stack.yaml",
                "valid": True,
            }
        }

    def upsert_execution_trade_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        merged = {str(row.get("trade_cost_id") or ""): dict(row) for row in self.db._trade_rows if str(row.get("trade_cost_id") or "")}
        for row in rows:
            merged[str(row.get("trade_cost_id") or "")] = dict(row)
        self.db._trade_rows = list(merged.values())
        self.db._trade_rows.sort(key=lambda row: (str(row.get("executed_at") or ""), str(row.get("trade_cost_id") or "")))
        return {"ok": True, "trade_rows_upserted": len(rows), "trade_rows_total": len(self.db._trade_rows)}

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
    catalog_source = {
        "spot": "binance_spot_exchangeInfo",
        "margin": "derived:spot_exchangeInfo_for_margin",
        "usdm_futures": "binance_usdm_exchangeInfo",
        "coinm_futures": "binance_coinm_exchangeInfo",
    }.get(family, "binance_exchange_info")
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
        "catalog_source": catalog_source,
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
            snapshot_fetched_at=snapshot_fetched_at or utc_now_iso(),
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


def _seed_order(
    service: ExecutionRealityService,
    *,
    family: str = "spot",
    environment: str = "live",
    mode: str | None = None,
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    order_type: str = "LIMIT",
    quantity: float = 0.01,
    price: float = 50000.0,
    order_status: str = "NEW",
    submitted_at: str | None = None,
    acknowledged_at: str | None = None,
    executed_qty: float | None = None,
    cum_quote_qty: float | None = None,
    estimated_fee: float = 0.25,
    estimated_slippage_bps: float = 6.0,
    estimated_total_cost: float = 0.75,
) -> tuple[dict[str, Any], dict[str, Any]]:
    intent = service.db.insert_intent(
        {
            "family": family,
            "environment": environment,
            "mode": mode or environment,
            "strategy_id": "strat-1",
            "bot_id": "bot-1",
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "limit_price": price if order_type == "LIMIT" else None,
            "requested_notional": quantity * price,
            "estimated_fee": estimated_fee,
            "estimated_slippage_bps": estimated_slippage_bps,
            "estimated_total_cost": estimated_total_cost,
            "preflight_status": "submitted",
            "policy_hash": service.policy_hash(),
            "submitted_at": submitted_at or _iso_hours_ago(1),
            "raw_request_json": {
                "market_snapshot": {"bid": price - 1.0, "ask": price + 1.0},
                "price": price,
            },
        }
    )
    order = service.db.upsert_order(
        {
            "execution_intent_id": intent["execution_intent_id"],
            "client_order_id": intent["client_order_id"],
            "venue_order_id": "123456",
            "symbol": symbol,
            "family": family,
            "environment": environment,
            "order_status": order_status,
            "submitted_at": submitted_at or _iso_hours_ago(1),
            "acknowledged_at": acknowledged_at,
            "price": price,
            "orig_qty": quantity,
            "executed_qty": executed_qty,
            "cum_quote_qty": cum_quote_qty,
            "raw_ack_json": {"side": side, "type": order_type, "symbol": symbol, "price": price, "origQty": quantity},
            "raw_last_status_json": {"status": order_status, "symbol": symbol, "side": side},
        }
    )
    return intent, order


def _canonical_execution_policy_text(filename: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / "config" / "policies" / filename).read_text(encoding="utf-8")


def _prepare_execution_policy_repo(
    repo_root: Path,
    *,
    root_safety: str | None,
    root_router: str | None,
    nested_safety: str | None = None,
    nested_router: str | None = None,
) -> tuple[Path, Path]:
    root_policies = repo_root / "config" / "policies"
    nested_policies = repo_root / "rtlab_autotrader" / "config" / "policies"
    root_policies.mkdir(parents=True, exist_ok=True)
    nested_policies.mkdir(parents=True, exist_ok=True)

    for name in ("instrument_registry.yaml", "universes.yaml", "cost_stack.yaml", "reporting_exports.yaml"):
        root_policies.joinpath(name).write_text("placeholder: true\n", encoding="utf-8")
        nested_policies.joinpath(name).write_text("placeholder: true\n", encoding="utf-8")

    if root_safety is not None:
        root_policies.joinpath("execution_safety.yaml").write_text(root_safety, encoding="utf-8")
    if root_router is not None:
        root_policies.joinpath("execution_router.yaml").write_text(root_router, encoding="utf-8")
    if nested_safety is not None:
        nested_policies.joinpath("execution_safety.yaml").write_text(nested_safety, encoding="utf-8")
    if nested_router is not None:
        nested_policies.joinpath("execution_router.yaml").write_text(nested_router, encoding="utf-8")
    return root_policies, nested_policies


def test_execution_reality_policies_load_from_canonical_yaml() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    explicit_root = repo_root / "config" / "policies"
    clear_execution_policy_cache()

    safety = load_execution_safety_bundle(repo_root, explicit_root=explicit_root)
    router = load_execution_router_bundle(repo_root, explicit_root=explicit_root)

    assert safety["valid"] is True
    assert router["valid"] is True
    assert safety["source"] == "config/policies/execution_safety.yaml"
    assert router["source"] == "config/policies/execution_router.yaml"
    assert safety["source_hash"]
    assert router["source_hash"]
    assert safety["policy_hash"]
    assert router["policy_hash"]
    assert safety["source_hash"] != safety["policy_hash"]
    assert router["source_hash"] != router["policy_hash"]
    assert safety["payload"]["execution_safety"]["preflight"]["quote_stale_block_ms"] == 3000
    assert router["payload"]["execution_router"]["conditional_orders_phase1"] is False


def test_execution_policy_bundle_missing_yaml_uses_minimal_fail_closed_payload(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies, _ = _prepare_execution_policy_repo(
        repo_root,
        root_safety=None,
        root_router=_canonical_execution_policy_text("execution_router.yaml"),
    )
    clear_execution_policy_cache()

    safety = load_execution_safety_bundle(repo_root, explicit_root=root_policies)

    assert safety["valid"] is False
    assert safety["exists"] is False
    assert safety["source"] == "default_fail_closed_minimal"
    assert safety["source_hash"] == ""
    assert safety["policy_hash"]
    assert safety["errors"]
    assert safety["payload"]["execution_safety"]["modes"]["allow_live"] is False
    assert safety["payload"]["execution_safety"]["sizing"]["max_notional_per_order_usd"] == 0.0


def test_execution_router_bundle_missing_yaml_uses_minimal_fail_closed_payload(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies, _ = _prepare_execution_policy_repo(
        repo_root,
        root_safety=_canonical_execution_policy_text("execution_safety.yaml"),
        root_router=None,
    )
    clear_execution_policy_cache()

    router = load_execution_router_bundle(repo_root, explicit_root=root_policies)

    assert router["valid"] is False
    assert router["exists"] is False
    assert router["source"] == "default_fail_closed_minimal"
    assert router["source_hash"] == ""
    assert router["policy_hash"]
    assert router["errors"]
    assert router["payload"]["execution_router"]["families_enabled"]["spot"] is False
    assert router["payload"]["execution_router"]["first_iteration_supported_order_types"]["spot"] == []


def test_execution_policy_bundle_tracks_root_nested_divergence(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_safety = _canonical_execution_policy_text("execution_safety.yaml")
    nested_safety = root_safety.replace("quote_stale_block_ms: 3000", "quote_stale_block_ms: 9999")
    root_router = _canonical_execution_policy_text("execution_router.yaml")
    nested_router = root_router.replace('spot: ["MARKET", "LIMIT"]', 'spot: ["MARKET"]')
    root_policies, _ = _prepare_execution_policy_repo(
        repo_root,
        root_safety=root_safety,
        root_router=root_router,
        nested_safety=nested_safety,
        nested_router=nested_router,
    )
    clear_execution_policy_cache()

    safety = load_execution_safety_bundle(repo_root, explicit_root=root_policies)
    router = load_execution_router_bundle(repo_root, explicit_root=root_policies)

    assert safety["valid"] is True
    assert router["valid"] is True
    assert safety["selected_role"] == "monorepo_root"
    assert router["selected_role"] == "monorepo_root"
    assert safety["fallback_used"] is False
    assert router["fallback_used"] is False
    assert any(
        "execution_safety.yaml" in (row.get("differing_files_vs_selected") or [])
        for row in (safety.get("divergent_candidates") or [])
    )
    assert any(
        "execution_router.yaml" in (row.get("differing_files_vs_selected") or [])
        for row in (router.get("divergent_candidates") or [])
    )


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
    assert bootstrap["policy_hash"]
    assert bootstrap["policy_hash"] == service.policy_hash()
    assert bootstrap["policy_source"]["execution_safety"]["source_hash"]
    assert bootstrap["policy_source"]["execution_safety"]["policy_hash"]
    assert bootstrap["policy_source"]["execution_router"]["source_hash"]
    assert bootstrap["policy_source"]["execution_router"]["policy_hash"]
    assert bootstrap["dependencies"]["instrument_registry_service"] is True
    assert bootstrap["cache_sizes"]["market_snapshots"] == 1
    assert summary["execution_policy_loaded"] is True
    assert summary["policy_hash"] == bootstrap["policy_hash"]
    assert summary["policy_source"]["execution_safety"]["source_hash"] == bootstrap["policy_source"]["execution_safety"]["source_hash"]
    assert summary["capabilities_known"] is True
    assert summary["degraded_mode"] is True
    assert summary["overall_status"] == "WARN"
    assert bootstrap["binance_live_runtime"]["policy_loaded"] is True
    assert bootstrap["binance_live_runtime"]["policy_hash"]
    assert bootstrap["binance_live_runtime"]["family_split"]["binance_spot"]["repo_family"] == "spot"
    assert "market_streams" in bootstrap


def test_market_ws_runtime_spot_combined_updates_quotes_and_summary(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    fake_ws = _FakeWebSocket(
        [
            json.dumps(
                {
                    "stream": "btcusdt@bookTicker",
                    "data": {
                        "e": "bookTicker",
                        "E": int(datetime.now(timezone.utc).timestamp() * 1000),
                        "s": "BTCUSDT",
                        "b": "50000.10",
                        "a": "50000.20",
                    },
                }
            ),
            json.dumps(
                {
                    "stream": "btcusdt@aggTrade",
                    "data": {
                        "e": "aggTrade",
                        "E": int(datetime.now(timezone.utc).timestamp() * 1000),
                        "s": "BTCUSDT",
                        "p": "50000.15",
                        "q": "0.0500",
                    },
                }
            ),
        ]
    )
    factory = _FakeConnectFactory([fake_ws])
    service._market_ws_runtime._connect_factory = factory  # type: ignore[attr-defined]

    started = service.start_market_stream(
        execution_connector="binance_spot",
        environment="live",
        symbols=["BTCUSDT"],
    )
    deadline = time.time() + 3.0
    while time.time() < deadline:
        snapshot = service._quote_snapshot("spot", "live", "BTCUSDT")
        sessions = service.market_streams_summary()["sessions"]
        if sessions and snapshot.get("bid") is not None:
            break
        time.sleep(0.05)
    stopped = service.stop_market_stream(execution_connector="binance_spot", environment="live")
    summary = service.market_streams_summary()
    live_safety = service.live_safety_summary(reconcile_summary={"unresolved_count": 0})

    assert started["execution_connector"] == "binance_spot"
    assert any("btcusdt@bookTicker" in row["url"] for row in factory.calls)
    assert service._quote_snapshot("spot", "live", "BTCUSDT")["bid"] == pytest.approx(50000.10)
    assert summary["family_split"]["binance_spot"]["market_family"] == "spot"
    assert live_safety["market_stream_runtime"]["policy_source"]["source_hash"]
    assert live_safety["market_stream_runtime_blocked"] is False
    assert stopped["reason"] == "stopped_by_operator"


def test_market_ws_runtime_raw_transport_subscribes_for_um_futures(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="usdm_futures")
    fake_ws = _FakeWebSocket(
        [
            json.dumps({"result": None, "id": 1}),
            json.dumps(
                {
                    "e": "markPriceUpdate",
                    "E": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "s": "BTCUSDT",
                    "p": "50010.5",
                    "i": "50009.8",
                    "r": "0.000100",
                }
            ),
        ]
    )
    factory = _FakeConnectFactory([fake_ws])
    service._market_ws_runtime._connect_factory = factory  # type: ignore[attr-defined]

    service.start_market_stream(
        execution_connector="binance_um_futures",
        environment="testnet",
        symbols=["BTCUSDT"],
        transport_mode="raw",
    )
    deadline = time.time() + 3.0
    while time.time() < deadline and not fake_ws.sent:
        time.sleep(0.05)
    stopped = service.stop_market_stream(execution_connector="binance_um_futures", environment="testnet")
    summary = service.market_streams_summary()

    assert fake_ws.sent
    sent_payload = json.loads(fake_ws.sent[0])
    assert sent_payload["method"] == "SUBSCRIBE"
    assert "btcusdt@bookTicker" in sent_payload["params"]
    assert summary["family_split"]["binance_um_futures"]["repo_family"] == "usdm_futures"
    assert stopped["transport_mode"] == "raw"


def test_market_ws_runtime_blocks_live_after_repeated_failures(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    service._market_ws_runtime._connect_factory = _FakeConnectFactory([RuntimeError("connect_failed")])  # type: ignore[attr-defined]
    service._market_ws_runtime._backoff_schedule = lambda _cfg: [0.05]  # type: ignore[attr-defined]

    service.start_market_stream(
        execution_connector="binance_spot",
        environment="live",
        symbols=["BTCUSDT"],
    )
    with service._market_ws_runtime._lock:  # type: ignore[attr-defined]
        session = service._market_ws_runtime._sessions[("binance_spot", "live")]  # type: ignore[attr-defined]
        session["summary"]["failure_threshold"] = 1

    deadline = time.time() + 3.0
    blocked = False
    while time.time() < deadline:
        payload = service.market_streams_summary()
        blocked = bool(payload.get("live_blocked"))
        if blocked:
            break
        time.sleep(0.05)
    safety = service.live_safety_summary(reconcile_summary={"unresolved_count": 0})
    service.stop_market_stream(execution_connector="binance_spot", environment="live")

    assert blocked is True
    assert safety["market_stream_runtime_blocked"] is True
    assert "market_ws_runtime_blocker" in safety["safety_blockers"]


def test_user_stream_runtime_spot_websocket_api_subscribes_and_persists_execution_report(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="NEW",
        acknowledged_at=None,
        submitted_at=_iso_hours_ago(0.1),
    )
    service._binance_adapter.signed_websocket_params = lambda **kwargs: (  # type: ignore[method-assign]
        {
            "apiKey": "spot-key",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "recvWindow": 5000,
            "signature": "deadbeef",
        },
        {"ok": True, "reason": "ok"},
    )
    fake_ws = _FakeWebSocket(
        [
            json.dumps({"id": "sub-1", "status": 200, "result": {"subscriptionId": 7}}),
            json.dumps(
                {
                    "subscriptionId": 7,
                    "event": {
                        "e": "executionReport",
                        "E": int(datetime.now(timezone.utc).timestamp() * 1000),
                        "s": "BTCUSDT",
                        "c": order["client_order_id"],
                        "S": "BUY",
                        "o": "LIMIT",
                        "f": "GTC",
                        "q": "0.01000000",
                        "p": "50000.00",
                        "x": "NEW",
                        "X": "NEW",
                        "i": 123456,
                        "l": "0.00000000",
                        "z": "0.00000000",
                        "L": "0.00000000",
                        "Z": "0.00000000",
                        "T": int(datetime.now(timezone.utc).timestamp() * 1000),
                    },
                }
            ),
        ]
    )
    service._user_stream_runtime._connect_factory = _FakeConnectFactory([fake_ws])  # type: ignore[attr-defined]

    started = service.start_user_stream(execution_connector="binance_spot", environment="live")
    deadline = time.time() + 3.0
    summary = None
    while time.time() < deadline:
        summary = service.user_streams_summary()
        sessions = summary.get("sessions") or []
        events = service.db.list_user_stream_events(family="spot", environment="live")
        if sessions and events:
            break
        time.sleep(0.05)
    stopped = service.stop_user_stream(execution_connector="binance_spot", environment="live")

    assert started["user_stream_mode"] == "websocket_api_spot"
    assert fake_ws.sent
    sent = json.loads(fake_ws.sent[0])
    assert sent["method"] == "userDataStream.subscribe.signature"
    assert sent["params"]["apiKey"] == "spot-key"
    assert summary is not None
    assert summary["sessions"][0]["subscription_id"] == 7
    events = service.db.list_user_stream_events(family="spot", environment="live")
    assert events
    assert events[0]["event_name"] == "executionReport"
    assert events[0]["execution_connector"] == "binance_spot"
    assert stopped["reason"] == "stopped_by_operator"


def test_user_stream_runtime_futures_listenkey_keeps_alive_and_persists_trade_update(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="usdm_futures")
    _, order = _seed_order(
        service,
        family="usdm_futures",
        environment="live",
        order_status="NEW",
        acknowledged_at=_iso_hours_ago(0.1),
        submitted_at=_iso_hours_ago(0.1),
    )
    calls: list[tuple[str, str]] = []
    base_cfg = service._user_stream_runtime.connector_config("binance_um_futures")  # type: ignore[attr-defined]
    patched_cfg = copy.deepcopy(base_cfg)
    patched_cfg["user_stream"]["keepalive_interval_sec"] = 0.05
    service._user_stream_runtime.connector_config = lambda connector: copy.deepcopy(patched_cfg if connector == "binance_um_futures" else base_cfg)  # type: ignore[method-assign]

    def _fake_api_key_request(method: str, endpoint_url: str, **kwargs):  # noqa: ANN001
        calls.append((str(method).upper(), endpoint_url))
        if method == "POST":
            return {"listenKey": "listen-key-1"}, {"ok": True, "reason": "ok"}
        return {}, {"ok": True, "reason": "ok"}

    service._binance_adapter.api_key_request = _fake_api_key_request  # type: ignore[method-assign]
    fake_ws = _FakeWebSocket(
        [
            json.dumps(
                {
                    "e": "ORDER_TRADE_UPDATE",
                    "E": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "o": {
                        "s": "BTCUSDT",
                        "c": order["client_order_id"],
                        "i": 999001,
                        "X": "NEW",
                        "x": "NEW",
                        "q": "0.01000000",
                        "z": "0.00000000",
                        "ap": "0",
                        "l": "0.00000000",
                        "L": "0.00000000",
                        "T": int(datetime.now(timezone.utc).timestamp() * 1000),
                    },
                }
            )
        ]
    )
    service._user_stream_runtime._connect_factory = _FakeConnectFactory([fake_ws])  # type: ignore[attr-defined]

    service.start_user_stream(execution_connector="binance_um_futures", environment="live")
    deadline = time.time() + 3.0
    while time.time() < deadline:
        events = service.db.list_user_stream_events(family="usdm_futures", environment="live")
        if events and any(method == "PUT" for method, _url in calls):
            break
        time.sleep(0.05)
    stopped = service.stop_user_stream(execution_connector="binance_um_futures", environment="live")

    assert any(method == "POST" for method, _url in calls)
    assert any(method == "PUT" for method, _url in calls)
    assert any(method == "DELETE" for method, _url in calls)
    events = service.db.list_user_stream_events(family="usdm_futures", environment="live")
    assert events
    assert events[0]["event_name"] == "ORDER_TRADE_UPDATE"
    assert events[0]["listen_key"] == "listen-key-1"
    assert stopped["reason"] == "stopped_by_operator"


def test_ingest_user_stream_account_event_persists_without_orphan(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    result = service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={
            "subscriptionId": 9,
            "event": {
                "e": "outboundAccountPosition",
                "E": int(datetime.now(timezone.utc).timestamp() * 1000),
                "u": int(datetime.now(timezone.utc).timestamp() * 1000),
                "B": [{"a": "USDT", "f": "100.0", "l": "0.0"}],
            },
            "_rtlab_user_stream": {
                "execution_connector": "binance_spot",
                "user_stream_mode": "websocket_api_spot",
                "subscription_id": 9,
                "received_at": utc_now_iso(),
            },
        },
    )

    events = service.db.list_user_stream_events(family="spot", environment="live")
    orphans = service.db.list_reconcile_events(reconcile_type="orphan_order")

    assert result["ok"] is True
    assert result["account_event"] is True
    assert events
    assert events[0]["event_name"] == "outboundAccountPosition"
    assert not orphans


def test_live_safety_summary_flags_user_stream_runtime_blocker(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    service.mark_user_stream_runtime_status(
        family="spot",
        environment="live",
        payload={
            "available": False,
            "running": True,
            "connected": False,
            "degraded_mode": True,
            "block_live": True,
            "reason": "failure_threshold_reached",
        },
    )

    summary = service.live_safety_summary(reconcile_summary={"unresolved_count": 0})

    assert summary["user_stream_runtime_blocked"] is True
    assert summary["user_stream_runtime_degraded"] is True
    assert "user_stream_runtime_blocker" in summary["safety_blockers"]


def test_user_stream_runtime_spot_legacy_listenkey_is_explicit_transitional_blocker(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    started = service.start_user_stream(
        execution_connector="binance_spot",
        environment="live",
        user_stream_mode="legacy_listenkey",
    )

    deadline = time.time() + 3.0
    session = None
    while time.time() < deadline:
        summary = service.user_streams_summary()
        sessions = summary.get("sessions") or []
        if sessions:
            session = sessions[0]
            if session.get("reason") == "legacy_listenkey_not_implemented":
                break
        time.sleep(0.05)
    stopped = service.stop_user_stream(execution_connector="binance_spot", environment="live")

    assert started["user_stream_mode"] == "legacy_listenkey"
    assert session is not None
    assert session["unsupported_mode"] is True
    assert session["degraded_mode"] is True
    assert session["block_live"] is True
    assert session["reason"] == "legacy_listenkey_not_implemented"
    assert stopped["reason"] == "stopped_by_operator"


def test_exchange_adapter_spot_test_order_uses_server_time_sync_and_recv_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(tmp_path, family="spot")
    monkeypatch.setenv("BINANCE_API_KEY", "live-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live-secret")
    calls: list[tuple[str, str, dict[str, str] | None]] = []
    expected_server_time = 1730000005000

    def _fake_request(method: str, url: str, headers=None, timeout=None, params=None):  # noqa: ANN001
        calls.append((str(method).upper(), url, headers))
        if url.endswith("/api/v3/time"):
            return _HTTPResponse({"serverTime": expected_server_time})
        if "/api/v3/order/test?" in url:
            query = parse_qs(urlsplit(url).query)
            assert query["recvWindow"] == ["5000"]
            assert headers == {"X-MBX-APIKEY": "live-key"}
            timestamp_ms = int(query["timestamp"][0])
            assert abs(timestamp_ms - expected_server_time) < 2500
            return _HTTPResponse({}, status_code=200)
        raise AssertionError(f"Unexpected adapter URL: {url}")

    monkeypatch.setattr("rtlab_core.execution.binance_adapter.requests.request", _fake_request)

    result = service.test_order_contract(
        family="spot",
        environment="live",
        preview={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "limit_price": 50000.0,
            "time_in_force": "GTC",
        },
        client_order_id="cli-test-spot",
    )
    bootstrap = service.bootstrap_summary()

    assert result["ok"] is True
    assert result["supported"] is True
    assert result["remote_source"]["ok"] is True
    assert calls[0][1].endswith("/api/v3/time")
    assert any("/api/v3/order/test?" in url for _method, url, _headers in calls)
    assert bootstrap["exchange_adapter"]["recv_window_ms"] == 5000
    assert bootstrap["exchange_adapter"]["server_time_sync_enabled"] is True
    assert bootstrap["exchange_adapter"]["supported_contracts"]["spot"]["test_order"] is True
    assert bootstrap["exchange_adapter"]["server_time_cache"]


def test_exchange_adapter_signed_websocket_params_follow_sorted_hmac_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(tmp_path, family="spot")
    monkeypatch.setenv("BINANCE_API_KEY", "ws-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "ws-secret")
    fixed_now_ms = 1730000000000

    monkeypatch.setattr("rtlab_core.execution.binance_adapter._now_ms", lambda: fixed_now_ms)
    service._binance_adapter.sync_server_time = lambda family, environment, force=False: {  # type: ignore[method-assign]
        "ok": True,
        "reason": "ok",
        "cached": False,
        "offset_ms": 0,
    }

    params, meta = service._user_stream_signed_ws_params(
        family="spot",
        environment="live",
        params={"symbol": "BTCUSDT"},
    )

    expected_payload = "apiKey=ws-key&recvWindow=5000&symbol=BTCUSDT&timestamp=1730000000000"
    expected_signature = hmac.new(
        b"ws-secret",
        expected_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert params is not None
    assert meta["ok"] is True
    assert params["apiKey"] == "ws-key"
    assert params["recvWindow"] == 5000
    assert params["timestamp"] == fixed_now_ms
    assert params["signature"] == expected_signature


def test_exchange_adapter_api_key_request_allows_api_key_only_listenkey_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(tmp_path, family="usdm_futures")
    monkeypatch.setenv("BINANCE_USDM_API_KEY", "futures-key")
    monkeypatch.delenv("BINANCE_USDM_API_SECRET", raising=False)
    calls: list[tuple[str, str, dict[str, str] | None]] = []

    def _fake_request(method: str, url: str, headers=None, timeout=None, params=None):  # noqa: ANN001
        calls.append((str(method).upper(), url, headers))
        return _HTTPResponse({"listenKey": "listen-key-42"}, status_code=200)

    monkeypatch.setattr("rtlab_core.execution.binance_adapter.requests.request", _fake_request)

    payload, meta = service._user_stream_api_key_request(
        "POST",
        service._user_stream_endpoint("usdm_futures", "live"),
        family="usdm_futures",
        environment="live",
        params=None,
    )

    assert payload == {"listenKey": "listen-key-42"}
    assert meta["ok"] is True
    assert meta["credentials_present"] is True
    assert meta["api_key_present"] is True
    assert meta["api_secret_present"] is False
    assert calls == [
        (
            "POST",
            service._user_stream_endpoint("usdm_futures", "live"),
            {"X-MBX-APIKEY": "futures-key"},
        )
    ]


def test_exchange_adapter_invalid_timestamp_resyncs_and_retries_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(tmp_path, family="spot")
    monkeypatch.setenv("BINANCE_API_KEY", "live-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live-secret")
    current_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    service._binance_adapter._server_time_cache[("spot", "live")] = {  # type: ignore[attr-defined]
        "server_time_ms": current_ms - 5000,
        "offset_ms": -5000,
        "synced_at_ms": current_ms,
        "within_threshold": False,
        "threshold_ms": 1000,
    }
    calls: list[str] = []

    def _fake_request(method: str, url: str, headers=None, timeout=None, params=None):  # noqa: ANN001
        calls.append(url)
        if "/api/v3/order?" in url and len([item for item in calls if "/api/v3/order?" in item]) == 1:
            return _HTTPResponse(
                {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."},
                status_code=400,
            )
        if url.endswith("/api/v3/time"):
            return _HTTPResponse({"serverTime": current_ms + 100})
        if "/api/v3/order?" in url:
            return _HTTPResponse(
                {
                    "symbol": "BTCUSDT",
                    "orderId": 123456,
                    "clientOrderId": "cli-retry-1",
                    "status": "NEW",
                    "executedQty": "0",
                    "cummulativeQuoteQty": "0",
                },
                status_code=200,
            )
        raise AssertionError(f"Unexpected adapter URL: {url}")

    monkeypatch.setattr("rtlab_core.execution.binance_adapter.requests.request", _fake_request)

    payload, meta = service._signed_request(
        "POST",
        service._exchange_contract_endpoint("spot", "live", "submit"),
        family="spot",
        environment="live",
        params={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": 0.01,
            "price": 50000.0,
            "newClientOrderId": "cli-retry-1",
            "newOrderRespType": "ACK",
        },
    )

    assert isinstance(payload, dict)
    assert payload["orderId"] == 123456
    assert meta["ok"] is True
    assert meta["attempt"] == 2
    assert any(url.endswith("/api/v3/time") for url in calls)
    assert len([url for url in calls if "/api/v3/order?" in url]) == 2


def test_exchange_adapter_error_mapping_covers_auth_rate_limit_and_missing_order() -> None:
    auth = map_exchange_error(400, {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."})
    rate_limit = map_exchange_error(429, {"code": -1003, "msg": "Too many requests."})
    missing = map_exchange_error(400, {"code": -2013, "msg": "Order does not exist."})

    assert auth["reason"] == "auth_rejected"
    assert auth["error_category"] == "auth"
    assert rate_limit["reason"] == "rate_limit"
    assert rate_limit["retryable"] is True
    assert missing["reason"] == "no_such_order"
    assert missing["retryable"] is False


def test_exchange_adapter_fetches_exchange_info_and_balances_for_margin_and_futures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(tmp_path, family="usdm_futures")
    monkeypatch.setenv("BINANCE_API_KEY", "spot-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "spot-secret")
    monkeypatch.setenv("BINANCE_USDM_API_KEY", "usdm-key")
    monkeypatch.setenv("BINANCE_USDM_API_SECRET", "usdm-secret")

    def _fake_request(method: str, url: str, headers=None, timeout=None, params=None):  # noqa: ANN001
        if url.endswith("/api/v3/exchangeInfo"):
            return _HTTPResponse({"symbols": [{"symbol": "BTCUSDT"}]})
        if url.endswith("/api/v3/time"):
            return _HTTPResponse({"serverTime": int(datetime.now(timezone.utc).timestamp() * 1000)})
        if "/sapi/v1/margin/account?" in url:
            return _HTTPResponse(
                {
                    "borrowEnabled": True,
                    "tradeEnabled": True,
                    "marginLevel": "1.8",
                    "userAssets": [{"asset": "USDT"}],
                }
            )
        if "/fapi/v2/account?" in url:
            return _HTTPResponse({"canTrade": True, "assets": [{"asset": "USDT", "walletBalance": "100.0"}]})
        if url.endswith("/fapi/v1/time"):
            return _HTTPResponse({"serverTime": int(datetime.now(timezone.utc).timestamp() * 1000)})
        raise AssertionError(f"Unexpected adapter URL: {url}")

    monkeypatch.setattr("rtlab_core.execution.binance_adapter.requests.request", _fake_request)

    margin_info = service.fetch_exchange_info(family="margin", environment="live")
    margin_balances = service.fetch_account_balances(family="margin", environment="live")
    usdm_balances = service.fetch_account_balances(family="usdm_futures", environment="live")

    assert margin_info["ok"] is True
    assert margin_info["remote_source"]["contract_source"] == "spot_exchange_info_for_margin"
    assert margin_info["symbol_count"] == 1
    assert margin_balances["ok"] is True
    assert margin_balances["balances_count"] == 1
    assert service._margin_levels["live"]["level"] == pytest.approx(1.8)
    assert service._margin_levels["live"]["source"] == "binance_margin_account"
    assert usdm_balances["ok"] is True
    assert usdm_balances["balances_count"] == 1


def test_live_safety_summary_refreshes_margin_level_from_margin_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = _build_service(
        tmp_path,
        family="margin",
        capability_snapshot=_capability_snapshot(can_trade=True, can_margin=True),
        instrument_row=_instrument_row(family="margin"),
    )
    monkeypatch.setenv("BINANCE_API_KEY", "spot-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "spot-secret")

    def _fake_request(method: str, url: str, headers=None, timeout=None, params=None):  # noqa: ANN001
        if url.endswith("/api/v3/time"):
            return _HTTPResponse({"serverTime": int(datetime.now(timezone.utc).timestamp() * 1000)})
        if "/sapi/v1/margin/account?" in url:
            return _HTTPResponse(
                {
                    "borrowEnabled": True,
                    "tradeEnabled": True,
                    "marginLevel": "2.5",
                    "userAssets": [{"asset": "USDT"}],
                }
            )
        raise AssertionError(f"Unexpected adapter URL: {url}")

    monkeypatch.setattr("rtlab_core.execution.binance_adapter.requests.request", _fake_request)
    service._fee_source_state = lambda family, environment: {  # type: ignore[method-assign]
        "available": True,
        "fresh": True,
        "latest": {"family": family, "environment": environment},
    }

    summary = service.live_safety_summary()

    assert summary["margin_guard"]["level"] == pytest.approx(2.5)
    assert summary["margin_guard"]["source"] == "binance_margin_account"
    assert "margin_level_blocker" not in summary["safety_blockers"]


def test_preflight_blocks_when_execution_policy_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    root_policies, _ = _prepare_execution_policy_repo(
        repo_root,
        root_safety=None,
        root_router=_canonical_execution_policy_text("execution_router.yaml"),
    )
    clear_execution_policy_cache()

    service = ExecutionRealityService(
        user_data_dir=tmp_path / "user_data",
        repo_root=repo_root,
        explicit_policy_root=root_policies,
        instrument_registry_service=_FakeRegistryService(
            family="spot",
            instrument_row=_instrument_row(family="spot"),
            snapshot_fetched_at=_iso_hours_ago(1),
            capability_snapshot=_capability_snapshot(),
        ),
        universe_service=_FakeUniverseService(matched=True),
        reporting_bridge_service=_FakeReportingBridge(
            family="spot",
            available=True,
            fresh=True,
        ),
        runs_loader=lambda: [],
    )
    service.set_market_snapshot(family="spot", environment="paper", symbol="BTCUSDT", bid=50000.0, ask=50001.0)

    result = service.preflight(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
        }
    )

    assert result["allowed"] is False
    assert "execution_policy_not_loaded" in result["blocking_reasons"]


def test_preflight_accepts_live_order_with_aligned_exchange_filters(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    result = service.preflight(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.0012,
            "price": 50000.12,
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
    assert result["filter_validation"]["status"] == "PASS"
    assert result["filter_validation"]["filter_source"] == "spot_exchange_info"
    assert result["snapshot_source"]["universe_membership"]["matched"] is True
    assert result["estimated_costs"]["total_cost_estimated"] > 0


def test_preflight_blocks_invalid_tick_and_step_alignment_but_exposes_normalized_preview(tmp_path: Path) -> None:
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

    assert result["allowed"] is False
    assert result["fail_closed"] is True
    assert "invalid_step_alignment" in result["blocking_reasons"]
    assert "invalid_tick_alignment" in result["blocking_reasons"]
    assert result["normalized_order_preview"]["quantity"] == 0.0012
    assert result["normalized_order_preview"]["limit_price"] == 50000.12
    assert result["filter_validation"]["status"] == "BLOCK"
    assert result["filter_validation"]["changed_fields"] == ["limit_price", "quantity"]


def test_preflight_accepts_usdm_filters_with_family_specific_source(tmp_path: Path) -> None:
    instrument_row = _instrument_row(
        family="usdm_futures",
        filter_summary={
            "price_filter": {"min_price": "0.1", "max_price": "1000000", "tick_size": "0.1"},
            "lot_size": {"min_qty": "0.001", "max_qty": "1000", "step_size": "0.001"},
            "market_lot_size": {"min_qty": "0.001", "max_qty": "1500", "step_size": "0.001"},
            "min_notional": {"min_notional": "5.0"},
            "max_num_orders": {"limit": 200, "max_num_orders": 200},
            "filter_types_present": ["LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL", "PRICE_FILTER"],
        },
    )
    service = _build_service(tmp_path, family="usdm_futures", instrument_row=instrument_row)

    result = service.preflight(
        {
            "family": "usdm_futures",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.005,
            "price": 50000.1,
            "market_snapshot": {
                "bid": 50000.0,
                "ask": 50000.2,
                "mark_price": 50000.05,
                "quote_ts_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
                "orderbook_ts_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            },
        }
    )

    assert result["allowed"] is True
    assert result["filter_validation"]["status"] == "PASS"
    assert result["filter_validation"]["market_family"] == "um_futures"
    assert result["filter_validation"]["execution_connector"] == "binance_um_futures"
    assert result["filter_validation"]["filter_source"] == "um_futures_exchange_info"


def test_preflight_blocks_stale_exchange_filters_in_live(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot", snapshot_fetched_at=_iso_hours_ago(1))

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
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert result["allowed"] is False
    assert result["fail_closed"] is True
    assert "exchange_filters_stale" in result["blocking_reasons"]
    assert result["snapshot_source"]["exchange_filters"]["status"] == "block"


def test_preflight_blocks_filter_source_mismatch(tmp_path: Path) -> None:
    instrument_row = _instrument_row(family="spot")
    instrument_row["catalog_source"] = "binance_usdm_exchangeInfo"
    service = _build_service(tmp_path, family="spot", instrument_row=instrument_row)

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
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert result["allowed"] is False
    assert "filter_source_mismatch" in result["blocking_reasons"]
    assert result["filter_validation"]["status"] == "BLOCK"


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


def test_create_market_order_paper_persists_intent_before_submit_and_estimated_costs(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    result = service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert result["order_status"] == "NEW"
    assert result["execution_intent_id"] is not None
    assert result["execution_order_id"] is not None
    assert result["estimated_costs"]["requested_notional"] > 0
    assert result["estimated_costs"]["total_cost_estimated"] > 0
    counts = service.db.counts()
    assert counts["execution_intents"] == 1
    assert counts["execution_orders"] == 1

    intent = service.db.intent_by_id(str(result["execution_intent_id"]))
    assert intent is not None
    assert intent["submitted_at"] is not None
    assert intent["preflight_status"] == "submitted"


def test_create_market_order_paper_reuses_live_quote_snapshot_when_paper_cache_is_empty(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    service.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50001.0)

    result = service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
        }
    )

    assert result["order_status"] == "NEW"
    assert result["execution_order_id"] is not None
    assert result["blocking_reasons"] == []


def test_create_market_order_paper_prefers_fresher_live_quote_snapshot_when_paper_cache_is_stale(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    old_ms = int((datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp() * 1000)
    fresh_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    service.set_market_snapshot(
        family="spot",
        environment="paper",
        symbol="BTCUSDT",
        bid=49900.0,
        ask=49901.0,
        quote_ts_ms=old_ms,
        orderbook_ts_ms=old_ms,
    )
    service.set_market_snapshot(
        family="spot",
        environment="live",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
        quote_ts_ms=fresh_ms,
        orderbook_ts_ms=fresh_ms,
    )

    result = service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
        }
    )

    assert result["order_status"] == "NEW"
    assert result["execution_order_id"] is not None
    assert result["blocking_reasons"] == []


def test_create_limit_order_paper_requires_explicit_price(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    result = service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert result["order_status"] == "BLOCKED"
    assert result["execution_order_id"] is None
    assert "limit_price_required" in result["blocking_reasons"]
    assert service.db.counts()["execution_intents"] == 1
    assert service.db.counts()["execution_orders"] == 0


def test_create_limit_order_paper_and_query_single_order_detail(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    result = service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.0012,
            "price": 50000.12,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    detail = service.order_detail(str(result["execution_order_id"]))

    assert detail is not None
    assert detail["order"]["order_status"] == "NEW"
    assert detail["order"]["price"] == 50000.12
    assert detail["intent"]["execution_intent_id"] == result["execution_intent_id"]
    assert detail["fills"] == []
    assert detail["reconcile_events"] == []
    assert detail["filter_validation"]["status"] == "PASS"


def test_list_open_orders_and_cancel_single_paper(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    first = service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )
    service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "SELL",
            "order_type": "LIMIT",
            "quantity": 0.02,
            "price": 51000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    listed = service.list_orders(family="spot", environment="paper", symbol="BTCUSDT", status="OPEN")
    canceled = service.cancel_order(str(first["execution_order_id"]))
    open_after = service.list_orders(family="spot", environment="paper", symbol="BTCUSDT", status="OPEN")

    assert listed["count"] == 2
    assert canceled["order_status"] == "CANCELED"
    assert open_after["count"] == 1


def test_cancel_all_paper_orders_for_symbol(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    for side in ("BUY", "SELL"):
        service.create_order(
            {
                "family": "spot",
                "environment": "paper",
                "mode": "paper",
                "symbol": "BTCUSDT",
                "side": side,
                "order_type": "LIMIT",
                "quantity": 0.01,
                "price": 50000.0 if side == "BUY" else 51000.0,
                "market_snapshot": _fresh_market_snapshot(),
            }
        )

    result = service.cancel_all(family="spot", environment="paper", symbol="BTCUSDT")

    assert result["canceled_count"] == 2
    assert len(service.db.open_orders(family="spot", symbol="BTCUSDT")) == 0


def test_live_order_state_machine_rest_ack_then_execution_report_new_enters_working(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    def _signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        params = kwargs.get("params") or {}
        if str(method).upper() == "POST":
            return _spot_create_ack(client_order_id=str(params["newClientOrderId"])), {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unexpected_call"}

    service._signed_request = _signed_request  # type: ignore[method-assign]

    created = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "bot_id": "bot-live-1",
            "strategy_id": "strat-live-1",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    order = service.db.order_by_id(str(created["execution_order_id"]))
    assert order is not None
    assert order["current_local_state"] == "ACKED"
    assert order["requested_new_order_resp_type"] == "FULL"

    ingested = service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={
            "event": _spot_execution_report(
                client_order_id=str(order["client_order_id"]),
                execution_type="NEW",
                order_status="NEW",
            ),
            "_rtlab_user_stream": {
                "execution_connector": "binance_spot",
                "user_stream_mode": "websocket_api_spot",
                "received_at": utc_now_iso(),
            },
        },
    )

    updated = service.db.order_by_id(str(created["execution_order_id"]))
    timeline = service.db.live_order_events_for_order(str(created["execution_order_id"]))

    assert ingested["ok"] is True
    assert updated is not None
    assert updated["current_local_state"] == "WORKING"
    assert [row["local_state_after"] for row in timeline[:4]] == [
        "INTENT_CREATED",
        "PRECHECK_PASSED",
        "SUBMITTING",
        "ACKED",
    ]
    assert timeline[-1]["local_state_after"] == "WORKING"


def test_live_order_state_machine_trade_partial_and_final_fill(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    service._signed_request = lambda method, endpoint, **kwargs: (  # type: ignore[method-assign]
        _spot_create_ack(client_order_id=str((kwargs.get("params") or {})["newClientOrderId"])),
        {"ok": True, "reason": "ok"},
    )
    created = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "bot_id": "bot-live-2",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )
    order = service.db.order_by_id(str(created["execution_order_id"]))
    assert order is not None

    service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={
            "event": _spot_execution_report(
                client_order_id=str(order["client_order_id"]),
                execution_type="TRADE",
                order_status="PARTIALLY_FILLED",
                last_fill_qty="0.00400000",
                cumulative_filled_qty="0.00400000",
                last_fill_price="50000.00",
                execution_id=7002,
                trade_id=7702,
            ),
            "_rtlab_user_stream": {"received_at": utc_now_iso()},
        },
    )
    partial = service.db.order_by_id(str(created["execution_order_id"]))
    assert partial is not None
    assert partial["current_local_state"] == "PARTIALLY_FILLED"

    service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={
            "event": _spot_execution_report(
                client_order_id=str(order["client_order_id"]),
                execution_type="TRADE",
                order_status="FILLED",
                last_fill_qty="0.00600000",
                cumulative_filled_qty="0.01000000",
                last_fill_price="50000.00",
                execution_id=7003,
                trade_id=7703,
            ),
            "_rtlab_user_stream": {"received_at": utc_now_iso()},
        },
    )
    filled = service.db.order_by_id(str(created["execution_order_id"]))
    fills = service.db.fills_for_order(str(created["execution_order_id"]))

    assert filled is not None
    assert filled["current_local_state"] == "FILLED"
    assert filled["order_status"] == "FILLED"
    assert len(fills) == 2
    assert filled["commission_total"] >= 0.0


def test_live_order_state_machine_cancel_flow_records_cancel_requested_then_canceled(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    def _signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        params = kwargs.get("params") or {}
        if str(method).upper() == "POST":
            return _spot_create_ack(client_order_id=str(params["newClientOrderId"])), {"ok": True, "reason": "ok"}
        if str(method).upper() == "DELETE":
            return {
                "symbol": "BTCUSDT",
                "origClientOrderId": params.get("origClientOrderId"),
                "clientOrderId": params.get("origClientOrderId"),
                "orderId": 123456,
                "status": "CANCELED",
                "transactTime": int(datetime.now(timezone.utc).timestamp() * 1000),
            }, {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unexpected_call"}

    service._signed_request = _signed_request  # type: ignore[method-assign]
    created = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "bot_id": "bot-live-3",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    canceled = service.cancel_order(str(created["execution_order_id"]))
    timeline = service.db.live_order_events_for_order(str(created["execution_order_id"]))

    assert canceled["current_local_state"] == "CANCELED"
    assert any(row["local_state_after"] == "CANCEL_REQUESTED" for row in timeline)
    assert timeline[-1]["local_state_after"] == "CANCELED"


def test_live_order_state_machine_reject_expire_and_stp_paths(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, reject_order = _seed_order(service, family="spot", environment="live", order_status="NEW", acknowledged_at=_iso_hours_ago(0.1))
    _, expire_order = _seed_order(service, family="spot", environment="live", order_status="NEW", acknowledged_at=_iso_hours_ago(0.1))
    _, stp_order = _seed_order(service, family="spot", environment="live", order_status="NEW", acknowledged_at=_iso_hours_ago(0.1))

    service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={"event": _spot_execution_report(client_order_id=str(reject_order["client_order_id"]), execution_type="REJECTED", order_status="REJECTED", execution_id=7101)},
    )
    service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={"event": _spot_execution_report(client_order_id=str(expire_order["client_order_id"]), execution_type="EXPIRED", order_status="EXPIRED", execution_id=7102)},
    )
    service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={"event": _spot_execution_report(client_order_id=str(stp_order["client_order_id"]), execution_type="TRADE_PREVENTION", order_status="EXPIRED_IN_MATCH", execution_id=7103)},
    )

    assert service.db.order_by_id(str(reject_order["execution_order_id"]))["current_local_state"] == "REJECTED"  # type: ignore[index]
    assert service.db.order_by_id(str(expire_order["execution_order_id"]))["current_local_state"] == "EXPIRED"  # type: ignore[index]
    assert service.db.order_by_id(str(stp_order["execution_order_id"]))["current_local_state"] == "EXPIRED_STP"  # type: ignore[index]


def test_live_order_state_machine_unknown_submit_reconciles_to_recovered_open(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    def _signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        params = kwargs.get("params") or {}
        if str(method).upper() == "POST":
            return None, {
                "ok": False,
                "reason": "exchange_unavailable",
                "exchange_code": -1007,
                "exchange_msg": "Timeout waiting for response from backend server. Send status unknown; execution status unknown.",
            }
        if str(method).upper() == "GET":
            return _spot_create_ack(
                client_order_id=str(params.get("origClientOrderId") or ""),
                status="NEW",
                order_id=888001,
            ), {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unexpected_call"}

    service._signed_request = _signed_request  # type: ignore[method-assign]
    created = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "bot_id": "bot-live-4",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    order = service.db.order_by_id(str(created["execution_order_id"]))
    assert order is not None
    assert order["current_local_state"] in {"RECOVERED_OPEN", "WORKING"}


def test_live_order_state_machine_dedups_identical_execution_reports(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(service, family="spot", environment="live", order_status="NEW", acknowledged_at=_iso_hours_ago(0.1))

    payload = {
        "event": _spot_execution_report(
            client_order_id=str(order["client_order_id"]),
            execution_type="TRADE",
            order_status="PARTIALLY_FILLED",
            last_fill_qty="0.00400000",
            cumulative_filled_qty="0.00400000",
            last_fill_price="50000.00",
            execution_id=7201,
        ),
        "_rtlab_user_stream": {"received_at": utc_now_iso()},
    }
    first = service.ingest_user_stream_event(family="spot", environment="live", payload=copy.deepcopy(payload))
    second = service.ingest_user_stream_event(family="spot", environment="live", payload=copy.deepcopy(payload))
    timeline = service.db.live_order_events_for_order(str(order["execution_order_id"]))
    fills = service.db.fills_for_order(str(order["execution_order_id"]))

    assert first["duplicated_event"] is False
    assert second["duplicated_event"] is True
    assert len([row for row in timeline if row["source_type"] == "WS_EXECUTION_REPORT"]) == 1
    assert len(fills) == 1


def test_live_order_state_machine_startup_recovery_rehydrates_unknown_order(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    intent, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="NEW",
        submitted_at=_iso_hours_ago(1),
        acknowledged_at=None,
    )
    service.db.update_order_fields(
        str(order["execution_order_id"]),
        {
            "bot_id": intent["bot_id"],
            "current_local_state": "UNKNOWN_PENDING_RECONCILIATION",
            "unresolved_reason": "timeout_unknown",
            "last_event_at": _iso_hours_ago(1),
        },
    )

    service._signed_request = lambda method, endpoint, **kwargs: (  # type: ignore[method-assign]
        _spot_create_ack(
            client_order_id=str((kwargs.get("params") or {}).get("origClientOrderId") or order["client_order_id"]),
            status="NEW",
            order_id=999111,
        ),
        {"ok": True, "reason": "ok"},
    )

    recovery = service.recover_live_orders_on_startup()
    updated = service.db.order_by_id(str(order["execution_order_id"]))

    assert recovery["processed_orders"] >= 1
    assert updated is not None
    assert updated["current_local_state"] in {"RECOVERED_OPEN", "WORKING"}


def test_live_order_state_machine_blocks_new_submit_when_same_bot_symbol_is_unknown(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    intent, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="NEW",
        submitted_at=_iso_hours_ago(1),
        acknowledged_at=None,
    )
    service.db.update_order_fields(
        str(order["execution_order_id"]),
        {
            "bot_id": intent["bot_id"],
            "current_local_state": "UNKNOWN_PENDING_RECONCILIATION",
            "unresolved_reason": "timeout_unknown",
            "last_event_at": _iso_hours_ago(1),
        },
    )

    blocked = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "bot_id": intent["bot_id"],
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert blocked["order_status"] == "BLOCKED"
    assert "unresolved_live_order_same_bot_symbol" in blocked["blocking_reasons"]


def test_create_order_live_fail_closed_when_fee_source_missing(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot", fee_source_available=False, fee_source_fresh=False)

    result = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert result["order_status"] == "BLOCKED"
    assert result["execution_order_id"] is None
    assert result["fail_closed"] is True
    assert "fee_source_missing_in_live" in result["blocking_reasons"]


def test_reconcile_ack_missing_generates_event(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="NEW",
        acknowledged_at=None,
        submitted_at=_iso_hours_ago(1),
    )

    service._signed_request = lambda *args, **kwargs: (None, {"ok": False, "reason": "missing_credentials"})  # type: ignore[method-assign]

    summary = service.reconcile_orders()
    events = service.db.list_reconcile_events(reconcile_type="ack_missing")

    assert summary["ack_missing"] == 1
    assert events
    assert events[0]["execution_order_id"] == order["execution_order_id"]
    assert events[0]["severity"] == "BLOCK"
    assert events[0]["resolved"] is False


def test_reconcile_fill_missing_generates_event(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="FILLED",
        acknowledged_at=_iso_hours_ago(1),
        executed_qty=0.01,
        cum_quote_qty=500.0,
    )

    def _fake_signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        if endpoint.endswith("/api/v3/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "FILLED",
                "executedQty": "0.01",
                "cummulativeQuoteQty": "500.0",
                "updateTime": int(datetime.now(timezone.utc).timestamp() * 1000),
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/myTrades"):
            return [], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/openOrders"):
            return [], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _fake_signed_request  # type: ignore[method-assign]

    summary = service.reconcile_orders()
    events = service.db.list_reconcile_events(reconcile_type="fill_missing")

    assert summary["fill_missing"] == 1
    assert events
    assert events[0]["execution_order_id"] == order["execution_order_id"]
    assert events[0]["resolved"] is False


def test_reconcile_status_mismatch_generates_resolved_event(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="NEW",
        acknowledged_at=_iso_hours_ago(1),
    )

    def _fake_signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        if endpoint.endswith("/api/v3/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "CANCELED",
                "executedQty": "0",
                "cummulativeQuoteQty": "0",
                "updateTime": int(datetime.now(timezone.utc).timestamp() * 1000),
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/myTrades"):
            return [], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/openOrders"):
            return [], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _fake_signed_request  # type: ignore[method-assign]

    summary = service.reconcile_orders()
    events = service.db.list_reconcile_events(reconcile_type="status_mismatch")
    updated = service.db.order_by_id(str(order["execution_order_id"]))

    assert summary["status_mismatches"] == 0
    assert updated is not None
    assert updated["order_status"] == "CANCELED"
    assert events
    assert events[0]["resolved"] is True
    assert events[0]["details_json"]["local_status_before"] == "NEW"
    assert events[0]["details_json"]["remote_status"] == "CANCELED"


def test_reconcile_spot_rest_fallback_materializes_fill_and_reporting_row(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="FILLED",
        acknowledged_at=_iso_hours_ago(1),
        executed_qty=0.01,
        cum_quote_qty=500.0,
        estimated_total_cost=1.0,
    )
    service.mark_user_stream_status(family="spot", environment="live", available=False, degraded_reason="rest_fallback")

    def _fake_signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        if endpoint.endswith("/api/v3/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "FILLED",
                "executedQty": "0.01",
                "cummulativeQuoteQty": "500.01",
                "updateTime": int(datetime.now(timezone.utc).timestamp() * 1000),
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/myTrades"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "id": 77,
                    "orderId": 123456,
                    "price": "50001.0",
                    "qty": "0.01",
                    "quoteQty": "500.01",
                    "commission": "0.25",
                    "commissionAsset": "USDT",
                    "time": int(datetime.now(timezone.utc).timestamp() * 1000),
                    "isMaker": False,
                }
            ], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/openOrders"):
            return [], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _fake_signed_request  # type: ignore[method-assign]

    summary = service.reconcile_orders()
    detail = service.order_detail(str(order["execution_order_id"]))
    ledger_rows = service.reporting_bridge_service.db.trade_rows()  # type: ignore[union-attr]

    assert summary["degraded_mode"] is True
    assert detail is not None
    assert detail["degraded_mode"] is True
    assert len(detail["fills"]) == 1
    assert detail["realized_costs"]["exchange_fee_realized"] == pytest.approx(0.25)
    assert detail["estimated_costs"]["total_cost_estimated"] == pytest.approx(1.0)
    assert detail["realized_costs"]["cost_classification"] == "mixed"
    assert ledger_rows
    assert ledger_rows[0]["trade_ref"] == detail["fills"][0]["execution_fill_id"]


def test_reconcile_futures_rest_fallback_materializes_funding_and_net_pnl(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="usdm_futures")
    _, order = _seed_order(
        service,
        family="usdm_futures",
        environment="live",
        order_status="FILLED",
        acknowledged_at=_iso_hours_ago(1),
        executed_qty=0.01,
        cum_quote_qty=500.0,
        estimated_total_cost=1.2,
    )
    service.mark_user_stream_status(family="usdm_futures", environment="live", available=False, degraded_reason="rest_fallback")

    def _fake_signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if endpoint.endswith("/fapi/v1/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "FILLED",
                "executedQty": "0.01",
                "cumQuote": "500.10",
                "avgPrice": "50010.0",
                "updateTime": now_ms,
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/fapi/v1/userTrades"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "id": 88,
                    "orderId": 123456,
                    "price": "50010.0",
                    "qty": "0.01",
                    "quoteQty": "500.10",
                    "commission": "0.12",
                    "commissionAsset": "USDT",
                    "realizedPnl": "5.0",
                    "time": now_ms,
                    "maker": False,
                }
            ], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/fapi/v1/income"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "incomeType": "FUNDING_FEE",
                    "income": "-0.50",
                    "time": now_ms,
                }
            ], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/fapi/v1/openOrders"):
            return [], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _fake_signed_request  # type: ignore[method-assign]

    service.reconcile_orders()
    detail = service.order_detail(str(order["execution_order_id"]))

    assert detail is not None
    assert len(detail["fills"]) == 1
    assert detail["realized_costs"]["funding_realized"] == pytest.approx(0.5)
    assert detail["gross_pnl"] == pytest.approx(5.0)
    assert detail["net_pnl"] == pytest.approx(5.0 - detail["realized_costs"]["total_cost_realized"])
    assert detail["fills"][0]["net_pnl"] == pytest.approx(detail["net_pnl"])


def test_live_fill_from_execution_report_persists_commission_trade_and_execution_ids(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(service, family="spot", environment="live", order_status="NEW", acknowledged_at=_iso_hours_ago(0.1))

    service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={
            "event": _spot_execution_report(
                client_order_id=str(order["client_order_id"]),
                execution_type="TRADE",
                order_status="PARTIALLY_FILLED",
                last_fill_qty="0.00400000",
                cumulative_filled_qty="0.00400000",
                last_fill_price="50000.00",
                execution_id=8101,
                trade_id=9101,
                commission="0.12",
                commission_asset="BNB",
                maker=True,
            )
        },
    )

    fills = service.db.fills_for_order(str(order["execution_order_id"]))

    assert len(fills) == 1
    assert fills[0]["trade_id"] == "9101"
    assert fills[0]["execution_id"] == "8101"
    assert fills[0]["commission"] == pytest.approx(0.12)
    assert fills[0]["commission_asset"] == "BNB"
    assert fills[0]["maker"] is True
    assert fills[0]["raw_source_type"] == "WS_EXECUTION_REPORT"
    assert fills[0]["reconciliation_status"] == "WS_ONLY"
    assert fills[0]["last_executed_qty"] == pytest.approx(0.004)


def test_live_fill_rest_create_full_materializes_fill_without_stream(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    service._signed_request = lambda method, endpoint, **kwargs: (  # type: ignore[method-assign]
        _spot_create_ack(
            client_order_id=str((kwargs.get("params") or {})["newClientOrderId"]),
            status="FILLED",
            executed_qty="0.01000000",
            cum_quote_qty="500.00",
            fills=[
                {
                    "price": "50000.00",
                    "qty": "0.01000000",
                    "commission": "0.25",
                    "commissionAsset": "USDT",
                    "tradeId": 9201,
                }
            ],
        ),
        {"ok": True, "reason": "ok"},
    )

    created = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "bot_id": "bot-live-fill-create",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    fills = service.db.fills_for_order(str(created["execution_order_id"]))
    assert len(fills) == 1
    assert fills[0]["raw_source_type"] == "REST_CREATE_FULL"
    assert fills[0]["trade_id"] == "9201"
    assert fills[0]["commission_asset"] == "USDT"


def test_live_fill_reconcile_marks_discrepancy_without_destroying_ws_evidence(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="FILLED",
        acknowledged_at=_iso_hours_ago(1),
        executed_qty=0.01,
        cum_quote_qty=500.0,
    )
    service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={
            "event": _spot_execution_report(
                client_order_id=str(order["client_order_id"]),
                execution_type="TRADE",
                order_status="FILLED",
                last_fill_qty="0.01000000",
                cumulative_filled_qty="0.01000000",
                last_fill_price="50000.00",
                execution_id=8201,
                trade_id=9301,
                commission="0.25",
                commission_asset="BNB",
                maker=True,
            )
        },
    )

    def _fake_signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if endpoint.endswith("/api/v3/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "FILLED",
                "executedQty": "0.01",
                "cummulativeQuoteQty": "500.0",
                "updateTime": now_ms,
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/myTrades"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "id": 9301,
                    "orderId": 123456,
                    "price": "50000.0",
                    "qty": "0.01",
                    "quoteQty": "500.0",
                    "commission": "0.30",
                    "commissionAsset": "USDT",
                    "time": now_ms,
                    "isMaker": False,
                }
            ], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/openOrders"):
            return [], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _fake_signed_request  # type: ignore[method-assign]

    payload = service.reconcile_live_fills(execution_order_id=str(order["execution_order_id"]), family="spot", environment="live", trigger="MANUAL")
    fills = service.db.fills_for_order(str(order["execution_order_id"]))
    discrepancy_events = service.db.list_reconcile_events(reconcile_type="fill_discrepancy", resolved=False)

    assert payload["discrepancies"]["count"] == 1
    assert fills[0]["reconciliation_status"] == "DISCREPANCY"
    assert fills[0]["trade_id"] == "9301"
    assert fills[0]["commission_asset"] == "USDT"
    assert fills[0]["discrepancy_json"]["ws_vs_mytrades_value_mismatch"]["commission"]["local"] == pytest.approx(0.25)
    assert discrepancy_events
    assert discrepancy_events[0]["details_json"]["discrepancy_type"] == "ws_vs_mytrades_value_mismatch"


def test_live_fill_startup_recovery_backfills_recent_missing_fills(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="FILLED",
        acknowledged_at=_iso_hours_ago(1),
        executed_qty=0.01,
        cum_quote_qty=500.0,
    )

    def _fake_signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if endpoint.endswith("/api/v3/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "FILLED",
                "executedQty": "0.01",
                "cummulativeQuoteQty": "500.0",
                "updateTime": now_ms,
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/myTrades"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "id": 9401,
                    "orderId": 123456,
                    "price": "50000.0",
                    "qty": "0.01",
                    "quoteQty": "500.0",
                    "commission": "0.20",
                    "commissionAsset": "USDT",
                    "time": now_ms,
                    "isMaker": False,
                }
            ], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/openOrders"):
            return [], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _fake_signed_request  # type: ignore[method-assign]

    recovery = service.recover_live_orders_on_startup()
    fills = service.db.fills_for_order(str(order["execution_order_id"]))

    assert recovery["processed_orders"] >= 1
    assert len(fills) == 1
    assert fills[0]["trade_id"] == "9401"
    assert fills[0]["reconciliation_status"] == "REST_BACKFILL"


def test_live_fill_symbol_reconcile_records_unlinked_mytrades(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")

    def _fake_signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if endpoint.endswith("/api/v3/myTrades"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "id": 9501,
                    "orderId": 777777,
                    "price": "50010.0",
                    "qty": "0.01",
                    "quoteQty": "500.10",
                    "commission": "0.10",
                    "commissionAsset": "USDT",
                    "time": now_ms,
                    "isMaker": True,
                }
            ], {"ok": True, "reason": "ok"}
        return [], {"ok": True, "reason": "ok"}

    service._signed_request = _fake_signed_request  # type: ignore[method-assign]

    payload = service.reconcile_live_fills(family="spot", environment="live", symbol="BTCUSDT", trigger="MANUAL")
    discrepancy_events = service.db.list_reconcile_events(reconcile_type="fill_discrepancy", resolved=False)

    assert payload["unlinked_mytrades"]
    assert discrepancy_events
    assert discrepancy_events[0]["details_json"]["discrepancy_type"] == "mytrades_unlinked_local_order"


def test_live_fill_reporting_rows_preserve_trade_linkage_and_fee_asset(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(service, family="spot", environment="live", order_status="NEW", acknowledged_at=_iso_hours_ago(0.1))

    service.ingest_user_stream_event(
        family="spot",
        environment="live",
        payload={
            "event": _spot_execution_report(
                client_order_id=str(order["client_order_id"]),
                execution_type="TRADE",
                order_status="FILLED",
                last_fill_qty="0.01000000",
                cumulative_filled_qty="0.01000000",
                last_fill_price="50000.00",
                execution_id=8301,
                trade_id=9601,
                commission="0.15",
                commission_asset="USDT",
                maker=False,
            )
        },
    )

    ledger_rows = service.reporting_bridge_service.db.trade_rows()  # type: ignore[union-attr]

    assert ledger_rows
    assert ledger_rows[0]["fee_asset"] == "USDT"
    assert ledger_rows[0]["provenance"]["trade_id"] == "9601"
    assert ledger_rows[0]["provenance"]["execution_id"] == "8301"
    assert ledger_rows[0]["provenance"]["raw_source_type"] == "WS_EXECUTION_REPORT"


def test_reconciliation_engine_resolves_local_open_against_remote_terminal(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(service, family="spot", environment="live", order_status="NEW", acknowledged_at=_iso_hours_ago(0.1))
    service.db.update_order_fields(
        str(order["execution_order_id"]),
        {
            "current_local_state": "WORKING",
            "last_event_at": _iso_hours_ago(0.1),
        },
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def _signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        if endpoint.endswith("/api/v3/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "FILLED",
                "executedQty": "0.01",
                "cummulativeQuoteQty": "500.0",
                "updateTime": now_ms,
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/openOrders"):
            return [], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/myTrades"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "id": 99101,
                    "orderId": 123456,
                    "price": "50000.0",
                    "qty": "0.01",
                    "quoteQty": "500.0",
                    "commission": "0.25",
                    "commissionAsset": "USDT",
                    "time": now_ms,
                    "isMaker": False,
                }
            ], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _signed_request  # type: ignore[method-assign]

    payload = service.run_reconciliation_engine(
        execution_order_id=str(order["execution_order_id"]),
        family="spot",
        environment="live",
        trigger="MANUAL",
    )
    updated = service.db.order_by_id(str(order["execution_order_id"]))
    fills = service.db.fills_for_order(str(order["execution_order_id"]))

    assert payload["generated_cases"] == 1
    assert payload["items"][0]["final_status"] == "RESOLVED"
    assert updated is not None
    assert updated["current_local_state"] in {"FILLED", "RECOVERED_TERMINAL"}
    assert len(fills) == 1


def test_reconciliation_engine_marks_manual_review_when_query_and_open_orders_conflict(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(service, family="spot", environment="live", order_status="NEW", acknowledged_at=_iso_hours_ago(0.1))
    service.db.update_order_fields(
        str(order["execution_order_id"]),
        {
            "current_local_state": "WORKING",
            "last_event_at": _iso_hours_ago(0.1),
        },
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def _signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        if endpoint.endswith("/api/v3/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "FILLED",
                "executedQty": "0.01",
                "cummulativeQuoteQty": "500.0",
                "updateTime": now_ms,
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/openOrders"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "orderId": 123456,
                    "clientOrderId": order["client_order_id"],
                    "status": "NEW",
                    "origQty": "0.01",
                    "executedQty": "0.00",
                    "price": "50000.0",
                    "updateTime": now_ms,
                }
            ], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/myTrades"):
            return [], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _signed_request  # type: ignore[method-assign]

    payload = service.run_reconciliation_engine(
        execution_order_id=str(order["execution_order_id"]),
        family="spot",
        environment="live",
        trigger="MANUAL",
    )
    summary = service.reconciliation_summary(environment="live", family="spot", execution_order_id=str(order["execution_order_id"]))

    assert payload["items"][0]["final_status"] == "MANUAL_REVIEW_REQUIRED"
    assert payload["blocking_cases"][0]["final_status"] == "MANUAL_REVIEW_REQUIRED"
    assert summary["blocking_cases_count"] == 1


def test_reconciliation_engine_marks_unknown_timeout_as_desync_blocking(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="NEW",
        submitted_at=_iso_hours_ago(1),
        acknowledged_at=None,
    )
    service.db.update_order_fields(
        str(order["execution_order_id"]),
        {
            "current_local_state": "UNKNOWN_PENDING_RECONCILIATION",
            "unresolved_reason": "timeout_unknown",
            "last_event_at": _iso_hours_ago(1),
        },
    )

    service._signed_request = lambda method, endpoint, **kwargs: (  # type: ignore[method-assign]
        [] if endpoint.endswith("/api/v3/openOrders") else None,
        {"ok": True, "reason": "ok"} if endpoint.endswith("/api/v3/openOrders") else {"ok": False, "reason": "unknown"},
    )

    payload = service.run_reconciliation_engine(
        execution_order_id=str(order["execution_order_id"]),
        family="spot",
        environment="live",
        trigger="UNKNOWN_TIMEOUT",
    )
    gate = service.live_reconciliation_gate(family="spot", environment="live", run_required=False)

    assert payload["items"][0]["final_status"] == "DESYNC"
    assert payload["blocking_cases"][0]["blocking_bool"] is True
    assert gate["ok"] is False
    assert gate["reason"] == "reconciliation_blocking_cases_open"


def test_reconciliation_engine_startup_detects_remote_open_without_local_order(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def _signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        if endpoint.endswith("/api/v3/openOrders"):
            return [
                {
                    "symbol": "BTCUSDT",
                    "orderId": 777001,
                    "clientOrderId": "remote-open-only",
                    "status": "NEW",
                    "origQty": "0.01",
                    "executedQty": "0.00",
                    "price": "50000.0",
                    "updateTime": now_ms,
                }
            ], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/api/v3/myTrades"):
            return [], {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "not_found"}

    service._signed_request = _signed_request  # type: ignore[method-assign]

    recovery = service.recover_live_orders_on_startup()
    open_cases = service.open_reconciliation_cases(environment="live", family="spot")

    assert recovery["generated_cases"] >= 1
    assert any(case["final_status"] == "DESYNC" for case in recovery["items"])
    assert any(
        any(str(discrepancy.get("code") or "") == "ORDER_MISSING_LOCALLY_BUT_REMOTE_OPEN" for discrepancy in (case.get("discrepancies") or []))
        for case in open_cases["items"]
    )


def test_reconciliation_engine_manual_run_is_append_only_for_traceability(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    _, order = _seed_order(
        service,
        family="spot",
        environment="live",
        order_status="NEW",
        submitted_at=_iso_hours_ago(1),
        acknowledged_at=None,
    )
    service.db.update_order_fields(
        str(order["execution_order_id"]),
        {
            "current_local_state": "UNKNOWN_PENDING_RECONCILIATION",
            "unresolved_reason": "timeout_unknown",
            "last_event_at": _iso_hours_ago(1),
        },
    )
    service._signed_request = lambda method, endpoint, **kwargs: (  # type: ignore[method-assign]
        [] if endpoint.endswith("/api/v3/openOrders") else None,
        {"ok": True, "reason": "ok"} if endpoint.endswith("/api/v3/openOrders") else {"ok": False, "reason": "unknown"},
    )

    first = service.run_reconciliation_engine(execution_order_id=str(order["execution_order_id"]), family="spot", environment="live", trigger="MANUAL")
    second = service.run_reconciliation_engine(execution_order_id=str(order["execution_order_id"]), family="spot", environment="live", trigger="MANUAL")
    rows = service.db.list_reconciliation_cases(
        execution_order_id=str(order["execution_order_id"]),
        environment="live",
        family="spot",
        limit=10,
        offset=0,
    )

    assert first["generated_cases"] == 1
    assert second["generated_cases"] == 1
    assert len(rows) >= 2


def test_paper_submit_reconcile_materializes_fill(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    result = service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    service.reconcile_orders()
    detail = service.order_detail(str(result["execution_order_id"]))
    ledger_rows = service.reporting_bridge_service.db.trade_rows()  # type: ignore[union-attr]

    assert detail is not None
    assert detail["order"]["order_status"] == "FILLED"
    assert len(detail["fills"]) == 1
    assert detail["realized_costs"]["cost_classification"] == "mixed"
    assert ledger_rows


def test_kill_switch_trip_reset_blocks_submit_and_auto_cancels_open_orders(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    for side in ("BUY", "SELL"):
        service.create_order(
            {
                "family": "spot",
                "environment": "paper",
                "mode": "paper",
                "symbol": "BTCUSDT",
                "side": side,
                "order_type": "LIMIT",
                "quantity": 0.01,
                "price": 50000.0 if side == "BUY" else 50010.0,
                "market_snapshot": _fresh_market_snapshot(),
            }
        )

    trip = service.trip_kill_switch(
        trigger_type="manual",
        severity="BLOCK",
        family="spot",
        symbol="BTCUSDT",
        reason="manual_operator_trip",
    )

    assert trip["active"] is True
    assert trip["trip_recorded"] is True
    assert trip["auto_actions"]
    assert trip["auto_actions"][0]["canceled_count"] == 2
    assert len(service.db.open_orders(family="spot", symbol="BTCUSDT")) == 0

    blocked = service.create_order(
        {
            "family": "spot",
            "environment": "paper",
            "mode": "paper",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "MARKET",
            "quantity": 0.01,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert blocked["order_status"] == "BLOCKED"
    assert "kill_switch_active" in blocked["blocking_reasons"]

    reset = service.reset_kill_switch(reason="operator_reset")

    assert reset["active"] is False
    assert reset["reset_applied"] is True
    assert reset["cooldown_active"] is True
    assert reset["last_event"]["cleared_reason"] == "operator_reset"


def test_reject_storm_blocker_trips_kill_switch(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    service.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50001.0)
    recent = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    for idx in range(8):
        _seed_order(
            service,
            family="spot",
            environment="live",
            symbol="BTCUSDT",
            order_status="REJECTED",
            submitted_at=recent,
            acknowledged_at=recent,
            price=50000.0 + idx,
        )

    result = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert result["order_status"] == "BLOCKED"
    assert "reject_storm_block" in result["blocking_reasons"]
    assert service.kill_switch_status()["active"] is True


def test_consecutive_failed_submit_blocker_trips_kill_switch(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    service.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50001.0)
    for _ in range(5):
        service.db.insert_intent(
            {
                "family": "spot",
                "environment": "live",
                "mode": "live",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "order_type": "LIMIT",
                "quantity": 0.01,
                "limit_price": 50000.0,
                "requested_notional": 500.0,
                "estimated_fee": 0.25,
                "estimated_slippage_bps": 6.0,
                "estimated_total_cost": 0.75,
                "preflight_status": "submit_failed",
                "policy_hash": service.policy_hash(),
                "raw_request_json": {"market_snapshot": _fresh_market_snapshot()},
            }
        )

    result = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert result["order_status"] == "BLOCKED"
    assert "consecutive_failed_submit_block" in result["blocking_reasons"]
    assert service.kill_switch_status()["active"] is True


def test_repeated_reconcile_mismatch_blocker_trips_kill_switch(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="spot")
    service.set_market_snapshot(family="spot", environment="live", symbol="BTCUSDT", bid=50000.0, ask=50001.0)
    for idx in range(5):
        service.db.insert_reconcile_event(
            {
                "family": "spot",
                "environment": "live",
                "reconcile_type": "status_mismatch",
                "severity": "WARN",
                "execution_order_id": None,
                "client_order_id": f"cli-{idx}",
                "details_json": {"reason": "synthetic_mismatch"},
                "resolved": False,
            }
        )

    result = service.create_order(
        {
            "family": "spot",
            "environment": "live",
            "mode": "live",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "order_type": "LIMIT",
            "quantity": 0.01,
            "price": 50000.0,
            "market_snapshot": _fresh_market_snapshot(),
        }
    )

    assert result["order_status"] == "BLOCKED"
    assert "repeated_reconcile_mismatch_block" in result["blocking_reasons"]
    assert service.kill_switch_status()["active"] is True


def test_futures_auto_cancel_heartbeat_refreshes_during_reconcile(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="usdm_futures")
    _, order = _seed_order(
        service,
        family="usdm_futures",
        environment="live",
        symbol="BTCUSDT",
        order_status="NEW",
        submitted_at=_iso_hours_ago(1),
        acknowledged_at=_iso_hours_ago(1),
    )

    def _fake_signed_request(method: str, endpoint: str, **kwargs):  # noqa: ANN001
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if endpoint.endswith("/fapi/v1/order"):
            return {
                "symbol": "BTCUSDT",
                "orderId": 123456,
                "clientOrderId": order["client_order_id"],
                "status": "NEW",
                "executedQty": "0.0",
                "cumQuote": "0.0",
                "updateTime": now_ms,
            }, {"ok": True, "reason": "ok"}
        if endpoint.endswith("/fapi/v1/userTrades"):
            return [], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/fapi/v1/income"):
            return [], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/fapi/v1/openOrders"):
            return [], {"ok": True, "reason": "ok"}
        if endpoint.endswith("/fapi/v1/countdownCancelAll"):
            return {"symbol": "BTCUSDT", "countdownTime": "120000"}, {"ok": True, "reason": "ok"}
        return None, {"ok": False, "reason": "unsupported"}

    service._signed_request = _fake_signed_request  # type: ignore[method-assign]

    summary = service.reconcile_orders()
    safety = service.live_safety_summary()

    assert summary["futures_auto_cancel"]
    assert summary["futures_auto_cancel"][0]["ok"] is True
    assert safety["futures_auto_cancel"]
    assert safety["futures_auto_cancel"][0]["effective_countdown_ms"] == 120000


def test_live_safety_summary_reports_final_blockers_and_overall_status(tmp_path: Path) -> None:
    service = _build_service(tmp_path, family="usdm_futures", fee_source_available=False, fee_source_fresh=False)
    old_ms = int((datetime.now(timezone.utc) - timedelta(seconds=10)).timestamp() * 1000)
    service.set_market_snapshot(
        family="usdm_futures",
        environment="live",
        symbol="BTCUSDT",
        bid=50000.0,
        ask=50001.0,
        quote_ts_ms=old_ms,
        orderbook_ts_ms=old_ms,
    )
    service.mark_user_stream_status(
        family="usdm_futures",
        environment="live",
        available=False,
        degraded_reason="rest_fallback",
    )
    service.set_margin_level(environment="live", level=1.0)
    service.db.insert_reconcile_event(
        {
            "family": "usdm_futures",
            "environment": "live",
            "reconcile_type": "status_mismatch",
            "severity": "WARN",
            "client_order_id": "late-1",
            "details_json": {"reason": "pending"},
            "resolved": False,
        }
    )

    summary = service.live_safety_summary()

    assert summary["stale_market_data"] is True
    assert summary["fee_source_fresh"] is False
    assert summary["margin_guard_status"] == "BLOCK"
    assert summary["degraded_mode"] is True
    assert summary["overall_status"] == "BLOCK"
    assert "cost_source_missing_blocker" in summary["safety_blockers"]
    assert "stale_quote_blocker" in summary["safety_blockers"]
    assert "stale_orderbook_blocker" in summary["safety_blockers"]

from pathlib import Path

from rtlab_core.backtest import BacktestCatalogDB
from rtlab_core.reporting.service import ReportingBridgeService


def test_reporting_cost_breakdown_exposes_binance_commission_component_contract(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    service = ReportingBridgeService(user_data_dir=tmp_path / "user_data", repo_root=repo_root)

    service.refresh_materialized_views([])
    breakdown = service.costs_breakdown()

    evidence = breakdown.get("commission_components") if isinstance(breakdown.get("commission_components"), dict) else {}
    items = evidence.get("items") if isinstance(evidence.get("items"), list) else []

    spot_tax = next(
        item
        for item in items
        if item.get("family") == "spot" and item.get("key") == "tax_commission"
    )
    spot_special = next(
        item
        for item in items
        if item.get("family") == "spot" and item.get("key") == "special_commission"
    )
    usdm_tax = next(
        item
        for item in items
        if item.get("family") == "usdm_futures" and item.get("key") == "tax_commission"
    )

    assert evidence["contract_version"] == "binance_commission_components_v1"
    assert spot_tax["label"] == "taxCommission"
    assert spot_tax["status"] == "supported"
    assert spot_tax["value"] is None
    assert spot_tax["estimated_vs_realized"] == "rate_metadata"
    assert spot_special["label"] == "specialCommission"
    assert spot_special["status"] == "supported"
    assert usdm_tax["status"] == "not_applicable"
    assert "no expone taxCommission" in usdm_tax["detail"]


def test_reporting_cost_breakdown_surfaces_real_fee_snapshot_commission_components(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    user_data = tmp_path / "user_data"
    catalog = BacktestCatalogDB(user_data / "backtests" / "catalog.sqlite3")
    catalog.insert_fee_snapshot(
        exchange="binance",
        market="crypto",
        symbol="BTCUSDT",
        maker_fee=0.00000040,
        taker_fee=0.00000050,
        commission_rate=None,
        source="exchange_api",
        payload={
            "exchange_fetch": {
                "endpoint": "/api/v3/account/commission",
                "commission_components": {
                    "tax_commission": {
                        "key": "tax_commission",
                        "label": "taxCommission",
                        "value": 0.00000130,
                        "asset": None,
                        "rates": {"maker": 0.00000128, "taker": 0.00000130},
                        "source": "binance_account_commission",
                        "source_endpoint": "GET /api/v3/account/commission",
                        "family": "spot",
                        "symbol": "BTCUSDT",
                        "status": "supported",
                        "estimated_vs_realized": "rate_metadata",
                    },
                    "special_commission": {
                        "key": "special_commission",
                        "label": "specialCommission",
                        "value": 0.05000000,
                        "asset": None,
                        "rates": {"maker": 0.04000000, "taker": 0.05000000},
                        "source": "binance_account_commission",
                        "source_endpoint": "GET /api/v3/account/commission",
                        "family": "spot",
                        "symbol": "BTCUSDT",
                        "status": "supported",
                        "estimated_vs_realized": "rate_metadata",
                    },
                },
            }
        },
        fetched_at="2026-05-06T00:00:00+00:00",
        expires_at="2099-01-01T00:00:00+00:00",
    )
    service = ReportingBridgeService(user_data_dir=user_data, repo_root=repo_root)

    service.refresh_materialized_views([])
    breakdown = service.costs_breakdown(family="spot", symbol="BTCUSDT")
    evidence = breakdown.get("commission_components") if isinstance(breakdown.get("commission_components"), dict) else {}
    items = evidence.get("items") if isinstance(evidence.get("items"), list) else []

    tax = next(
        item
        for item in items
        if item.get("key") == "tax_commission" and item.get("symbol") == "BTCUSDT"
    )
    special = next(
        item
        for item in items
        if item.get("key") == "special_commission" and item.get("symbol") == "BTCUSDT"
    )

    assert tax["value"] == 0.00000130
    assert tax["rates"]["maker"] == 0.00000128
    assert tax["fee_snapshot_id"]
    assert special["value"] == 0.05000000
    assert special["rates"]["taker"] == 0.05000000

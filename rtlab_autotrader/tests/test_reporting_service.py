from pathlib import Path

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

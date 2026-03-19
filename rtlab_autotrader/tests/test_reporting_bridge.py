from __future__ import annotations

import zipfile
from pathlib import Path

from rtlab_core.reporting import ReportingBridgeService


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_runs(tmp_path: Path, runs: list[dict]) -> Path:
    runs_path = tmp_path / "user_data" / "backtests" / "runs.json"
    runs_path.parent.mkdir(parents=True, exist_ok=True)
    runs_path.write_text(__import__("json").dumps(runs, ensure_ascii=True), encoding="utf-8")
    return runs_path


def _trade(
    *,
    trade_id: str,
    symbol: str = "BTC/USDT",
    executed_at: str = "2026-03-10T12:00:00+00:00",
    gross_pnl: float = 100.0,
    net_pnl: float | None = None,
    fees: float = 5.0,
    spread_cost: float = 4.0,
    slippage_cost: float = 6.0,
    funding_cost: float = 2.0,
    borrow_interest: float = 0.0,
    commission_asset: str | None = None,
    exchange_fee_realized: float | None = None,
    funding_realized: float | None = None,
    borrow_interest_realized: float | None = None,
    family: str | None = None,
) -> dict:
    estimated_total = fees + spread_cost + slippage_cost + funding_cost + borrow_interest
    return {
        "id": trade_id,
        "symbol": symbol,
        "family": family,
        "entry_time": executed_at,
        "exit_time": executed_at,
        "entry_px": 100.0,
        "exit_px": 110.0,
        "qty": 1.0,
        "pnl": gross_pnl,
        "pnl_net": gross_pnl - estimated_total if net_pnl is None else net_pnl,
        "fees": fees,
        "spread_cost": spread_cost,
        "slippage_cost": slippage_cost,
        "funding_cost": funding_cost,
        "borrow_interest": borrow_interest,
        "commissionAsset": commission_asset,
        "exchange_fee_realized": exchange_fee_realized,
        "funding_realized": funding_realized,
        "borrow_interest_realized": borrow_interest_realized,
    }


def _run(
    *,
    run_id: str,
    mode: str = "backtest",
    family: str | None = None,
    trades: list[dict] | None = None,
    costs_model: dict | None = None,
) -> dict:
    return {
        "id": run_id,
        "strategy_id": "STRAT-1",
        "mode": mode,
        "created_at": "2026-03-10T12:00:00+00:00",
        "finished_at": "2026-03-10T12:30:00+00:00",
        "costs_model": costs_model or {"fees_bps": 5.0, "spread_bps": 4.0, "slippage_bps": 6.0, "funding_bps": 2.0},
        "trades": trades or [],
        "provenance": {"venue": "binance", "family": family, "dataset_hash": "abc123"},
    }


def _service(tmp_path: Path, runs: list[dict]) -> ReportingBridgeService:
    user_data_dir = tmp_path / "user_data"
    runs_path = _write_runs(tmp_path, runs)
    return ReportingBridgeService(
        user_data_dir=user_data_dir,
        repo_root=_repo_root(),
        instrument_registry_service=None,
        runs_path=runs_path,
    )


def test_reporting_bridge_spot_backtest_marks_estimated_only(tmp_path: Path) -> None:
    service = _service(tmp_path, [_run(run_id="BT-1", trades=[_trade(trade_id="tr-1")])])

    result = service.refresh_materialized_views()

    assert result["ok"] is True
    rows = service.db.trade_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["exchange_fee_estimated"] == 5.0
    assert row["exchange_fee_realized"] is None
    assert row["cost_source"]["cost_classification"] == "estimated_only"


def test_reporting_bridge_margin_live_uses_realized_borrow_and_fee(tmp_path: Path) -> None:
    trade = _trade(
        trade_id="tr-m-1",
        symbol="BTCUSDT",
        gross_pnl=60.0,
        commission_asset="USDT",
        exchange_fee_realized=3.5,
        borrow_interest_realized=1.25,
        family="margin",
    )
    service = _service(tmp_path, [_run(run_id="LV-1", mode="live", family="margin", trades=[trade])])

    service.refresh_materialized_views()
    row = service.db.trade_rows()[0]

    assert row["exchange_fee_realized"] == 3.5
    assert row["borrow_interest_realized"] == 1.25
    assert row["cost_source"]["cost_classification"] == "mixed"


def test_reporting_bridge_futures_live_uses_realized_funding_and_fee(tmp_path: Path) -> None:
    trade = _trade(
        trade_id="tr-f-1",
        symbol="BTCUSDT",
        gross_pnl=80.0,
        commission_asset="USDT",
        exchange_fee_realized=4.0,
        funding_realized=1.5,
        family="usdm_futures",
    )
    service = _service(tmp_path, [_run(run_id="LV-2", mode="live", family="usdm_futures", trades=[trade])])

    service.refresh_materialized_views()
    row = service.db.trade_rows()[0]

    assert row["exchange_fee_realized"] == 4.0
    assert row["funding_realized"] == 1.5
    assert row["family"] == "usdm_futures"


def test_reporting_bridge_live_fail_closed_when_real_fee_source_missing(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        [_run(run_id="LV-3", mode="live", family="spot", trades=[_trade(trade_id="tr-live-missing", symbol="BTCUSDT")])],
    )

    try:
        service.refresh_materialized_views()
    except RuntimeError as exc:
        assert "fail-closed" in str(exc)
    else:
        raise AssertionError("Expected fail-closed RuntimeError for live trade without realized fee source")


def test_reporting_bridge_daily_monthly_breakdown_and_gross_vs_net_consistency(tmp_path: Path) -> None:
    runs = [
        _run(
            run_id="BT-2",
            trades=[
                _trade(trade_id="tr-a", executed_at="2026-03-01T12:00:00+00:00", gross_pnl=100.0, fees=5.0, spread_cost=4.0, slippage_cost=6.0, funding_cost=2.0),
                _trade(trade_id="tr-b", executed_at="2026-03-15T12:00:00+00:00", gross_pnl=50.0, fees=2.0, spread_cost=1.0, slippage_cost=1.0, funding_cost=0.0),
                _trade(trade_id="tr-c", executed_at="2026-04-02T12:00:00+00:00", gross_pnl=-20.0, fees=1.0, spread_cost=1.0, slippage_cost=1.0, funding_cost=0.0),
            ],
        )
    ]
    service = _service(tmp_path, runs)

    service.refresh_materialized_views()
    summary = service.performance_summary()
    daily = service.daily_series()
    monthly = service.monthly_series()
    breakdown = service.costs_breakdown()

    assert summary["all_time"]["trade_count"] == 3
    assert len(daily["items"]) == 3
    assert len(monthly["items"]) == 2
    assert breakdown["gross_pnl"] == 130.0
    assert breakdown["net_pnl"] == 106.0
    assert breakdown["total_cost_estimated"] == 24.0


def test_reporting_bridge_exports_write_manifest_xlsx_and_pdf(tmp_path: Path) -> None:
    service = _service(tmp_path, [_run(run_id="BT-4", trades=[_trade(trade_id="tr-exp")])])
    service.refresh_materialized_views()

    xlsx_manifest = service.create_export(export_type="xlsx", generated_by="tester")
    pdf_manifest = service.create_export(export_type="pdf", generated_by="tester")

    xlsx_path = Path(xlsx_manifest["artifact_path"])
    pdf_path = Path(pdf_manifest["artifact_path"])
    assert xlsx_path.exists()
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
    with zipfile.ZipFile(xlsx_path, "r") as archive:
        assert "xl/workbook.xml" in archive.namelist()
        assert "xl/worksheets/sheet1.xml" in archive.namelist()

    manifests = service.db.list_exports(limit=10)
    assert len(manifests) == 2

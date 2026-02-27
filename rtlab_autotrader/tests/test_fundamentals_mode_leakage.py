from __future__ import annotations

from pathlib import Path

from rtlab_core.backtest import BacktestCatalogDB
from rtlab_core.fundamentals import FundamentalsCreditFilter


def test_same_snapshot_yields_different_decision_by_mode(tmp_path: Path) -> None:
    db = BacktestCatalogDB(tmp_path / "catalog.sqlite3")
    filt = FundamentalsCreditFilter(catalog=db, policies_root=Path("config/policies"))
    snapshot = {
        "enforced": True,
        "fund_status": "BASIC",
        "allow_trade": True,
        "explain": [],
    }

    backtest = filt.evaluate_credit_policy(snapshot=snapshot, mode="backtest")
    live = filt.evaluate_credit_policy(snapshot=snapshot, mode="live")

    assert backtest["allow_trade"] is True
    assert backtest["fund_status"] == "BASIC"
    assert backtest["promotion_blocked"] is False

    assert live["allow_trade"] is False
    assert live["fund_status"] == "BASIC"
    assert live["promotion_blocked"] is True

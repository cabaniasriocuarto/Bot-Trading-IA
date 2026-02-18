from rtlab_core.risk.risk_engine import RiskEngine, RiskLimits


def test_risk_position_size_and_limits() -> None:
    engine = RiskEngine(
        limits=RiskLimits(
            daily_loss_limit_pct=0.05,
            max_drawdown_pct=0.22,
            max_positions=20,
            max_total_exposure_pct=1.0,
            max_asset_exposure_pct=0.2,
            risk_per_trade=0.005,
        ),
        starting_equity=10000,
    )

    qty = engine.position_size(equity=10000, entry=100, stop=98, confidence=1.0)
    assert qty > 0

    ok = engine.can_trade(
        equity=10000,
        daily_pnl=10,
        open_positions=2,
        total_exposure_pct=0.3,
        asset_exposure_pct=0.1,
    )
    assert ok.allow_new_positions

    blocked = engine.can_trade(
        equity=10000,
        daily_pnl=-600,
        open_positions=2,
        total_exposure_pct=0.3,
        asset_exposure_pct=0.1,
    )
    assert not blocked.allow_new_positions
    assert blocked.reason == "daily_loss_limit"

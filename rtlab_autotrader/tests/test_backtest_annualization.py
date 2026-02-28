from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sqrt

import pytest

from rtlab_core.src.backtest.engine import ReportEngine


def _equity_curve_points() -> list[dict[str, float | str]]:
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    equity = 10_000.0
    curve: list[dict[str, float | str]] = []
    max_equity = equity
    for idx in range(240):
        ret = 0.0007 + (0.0004 if idx % 2 == 0 else -0.0002)
        equity *= 1.0 + ret
        max_equity = max(max_equity, equity)
        drawdown = 0.0 if max_equity == 0 else (equity - max_equity) / max_equity
        curve.append(
            {
                "time": (ts + timedelta(minutes=idx)).isoformat(),
                "equity": round(equity, 6),
                "drawdown": round(drawdown, 6),
            }
        )
    return curve


def test_periods_per_year_by_timeframe() -> None:
    report = ReportEngine()
    assert report._periods_per_year("1m") == 365 * 24 * 60
    assert report._periods_per_year("5m") == 365 * 24 * 12
    assert report._periods_per_year("10m") == 365 * 24 * 6
    assert report._periods_per_year("15m") == 365 * 24 * 4
    assert report._periods_per_year("1h") == 365 * 24
    assert report._periods_per_year("1d") == 365
    assert report._periods_per_year("30m") == pytest.approx(365 * 24 * 2)


def test_sharpe_annualization_changes_with_timeframe() -> None:
    report = ReportEngine()
    curve = _equity_curve_points()

    one_minute = report.build_metrics(trades=[], equity_curve=curve, avg_exposure=0.0, timeframe="1m")
    one_hour = report.build_metrics(trades=[], equity_curve=curve, avg_exposure=0.0, timeframe="1h")

    assert one_minute["sharpe"] > one_hour["sharpe"]
    assert one_hour["sharpe"] > 0
    ratio = float(one_minute["sharpe"]) / float(one_hour["sharpe"])
    assert ratio == pytest.approx(sqrt(60), rel=0.03)

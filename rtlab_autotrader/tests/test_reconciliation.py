from rtlab_core.execution.reconciliation import reconcile_orders


def test_reconciliation_detects_mismatches() -> None:
    exchange = {
        "1": {"filled_qty": 1.0},
        "2": {"filled_qty": 2.0},
    }
    local = {
        "2": {"filled_qty": 1.5},
        "3": {"filled_qty": 1.0},
    }
    report = reconcile_orders(exchange, local)
    assert report.missing_local == ["1"]
    assert report.missing_exchange == ["3"]
    assert report.qty_mismatches == ["2"]
    assert report.desync_count == 3

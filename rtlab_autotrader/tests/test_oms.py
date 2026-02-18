from datetime import timedelta

from rtlab_core.execution.oms import OMS, Order
from rtlab_core.types import OrderStatus, Side


def test_oms_partial_and_stale() -> None:
    oms = OMS()
    order = Order(order_id="A1", symbol="BTC/USDT", side=Side.LONG, qty=10)
    oms.submit(order)
    assert oms.orders["A1"].status == OrderStatus.SUBMITTED

    oms.apply_fill("A1", 4)
    assert oms.orders["A1"].status == OrderStatus.PARTIALLY_FILLED
    assert oms.orders["A1"].filled_qty == 4

    oms.orders["A1"].updated_at = oms.orders["A1"].updated_at - timedelta(seconds=100)
    stale = oms.cancel_stale(max_age_seconds=45)
    assert "A1" in stale
    assert oms.orders["A1"].status == OrderStatus.STALE

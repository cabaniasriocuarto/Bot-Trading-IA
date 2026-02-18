from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from rtlab_core.types import OrderStatus, Side


@dataclass(slots=True)
class Order:
    order_id: str
    symbol: str
    side: Side
    qty: float
    filled_qty: float = 0.0
    status: OrderStatus = OrderStatus.NEW
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class OMS:
    def __init__(self) -> None:
        self.orders: dict[str, Order] = {}

    def submit(self, order: Order) -> Order:
        order.status = OrderStatus.SUBMITTED
        now = datetime.now(timezone.utc)
        order.created_at = now
        order.updated_at = now
        self.orders[order.order_id] = order
        return order

    def apply_fill(self, order_id: str, fill_qty: float) -> Order:
        order = self.orders[order_id]
        order.filled_qty = min(order.qty, order.filled_qty + max(0.0, fill_qty))
        order.status = OrderStatus.FILLED if order.filled_qty >= order.qty else OrderStatus.PARTIALLY_FILLED
        order.updated_at = datetime.now(timezone.utc)
        return order

    def cancel(self, order_id: str) -> Order:
        order = self.orders[order_id]
        if order.status not in {OrderStatus.FILLED, OrderStatus.CANCELED}:
            order.status = OrderStatus.CANCELED
            order.updated_at = datetime.now(timezone.utc)
        return order

    def cancel_stale(self, max_age_seconds: int) -> list[str]:
        now = datetime.now(timezone.utc)
        canceled: list[str] = []
        for oid, order in self.orders.items():
            if order.status in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}:
                age = (now - order.updated_at).total_seconds()
                if age > max_age_seconds:
                    order.status = OrderStatus.STALE
                    order.updated_at = now
                    canceled.append(oid)
        return canceled

    def open_orders(self) -> list[Order]:
        return [
            order
            for order in self.orders.values()
            if order.status in {OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED}
        ]

    def snapshot(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for order in self.orders.values():
            rows.append(
                {
                    "order_id": order.order_id,
                    "symbol": order.symbol,
                    "side": order.side.value,
                    "qty": order.qty,
                    "filled_qty": order.filled_qty,
                    "status": order.status.value,
                    "created_at": order.created_at.isoformat(),
                    "updated_at": order.updated_at.isoformat(),
                }
            )
        return rows

    def hydrate(self, rows: list[dict[str, object]]) -> None:
        self.orders.clear()
        for row in rows:
            order = Order(
                order_id=str(row["order_id"]),
                symbol=str(row["symbol"]),
                side=Side(str(row["side"])),
                qty=float(row["qty"]),
                filled_qty=float(row["filled_qty"]),
                status=OrderStatus(str(row["status"])),
                created_at=datetime.fromisoformat(str(row["created_at"])),
                updated_at=datetime.fromisoformat(str(row["updated_at"])),
            )
            self.orders[order.order_id] = order

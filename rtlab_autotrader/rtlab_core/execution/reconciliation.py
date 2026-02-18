from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ReconciliationReport:
    missing_local: list[str]
    missing_exchange: list[str]
    qty_mismatches: list[str]

    @property
    def desync_count(self) -> int:
        return len(self.missing_local) + len(self.missing_exchange) + len(self.qty_mismatches)


def reconcile_orders(
    exchange_orders: dict[str, dict[str, float]],
    local_orders: dict[str, dict[str, float]],
) -> ReconciliationReport:
    exchange_ids = set(exchange_orders)
    local_ids = set(local_orders)

    missing_local = sorted(list(exchange_ids - local_ids))
    missing_exchange = sorted(list(local_ids - exchange_ids))
    qty_mismatches: list[str] = []

    for oid in sorted(exchange_ids.intersection(local_ids)):
        ex_qty = float(exchange_orders[oid].get("filled_qty", 0.0))
        lc_qty = float(local_orders[oid].get("filled_qty", 0.0))
        if abs(ex_qty - lc_qty) > 1e-9:
            qty_mismatches.append(oid)

    return ReconciliationReport(
        missing_local=missing_local,
        missing_exchange=missing_exchange,
        qty_mismatches=qty_mismatches,
    )

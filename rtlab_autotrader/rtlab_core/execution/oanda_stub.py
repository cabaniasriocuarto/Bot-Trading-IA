from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class OandaOrderRequest:
    instrument: str
    units: int
    side: str
    type: str = "MARKET"


@dataclass(slots=True)
class OandaOrderResponse:
    order_id: str
    status: str


class OandaPracticeStub:
    """FASE 2 stub: contrato minimo para runner OANDA practice."""

    def __init__(self) -> None:
        self._seq = 0

    def place_order(self, request: OandaOrderRequest) -> OandaOrderResponse:
        self._seq += 1
        return OandaOrderResponse(order_id=f"oanda-{self._seq}", status="FILLED")


class OandaRunner:
    def __init__(self, client: OandaPracticeStub) -> None:
        self.client = client

    def run_once(self, instrument: str, units: int, side: str) -> OandaOrderResponse:
        return self.client.place_order(OandaOrderRequest(instrument=instrument, units=units, side=side))

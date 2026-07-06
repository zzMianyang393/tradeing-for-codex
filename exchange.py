from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    symbol: str
    direction: str
    qty: float
    status: str
    fill_price: float | None = None
    fill_qty: float | None = None
    fee: float = 0.0
    reason: str = ""


class DryRunExchange:
    """Local exchange stub that fills orders immediately at the requested price."""

    def __init__(self) -> None:
        self._next_order_id = 1
        self.orders: list[OrderResult] = []
        self.positions: list[dict] = []

    def place_order(
        self,
        symbol: str,
        direction: str,
        qty: float,
        order_type: str = "market",
        price: float | None = None,
        fee: float = 0.0,
    ) -> OrderResult:
        fill_price = price if price is not None else 0.0
        result = OrderResult(
            order_id=f"dry-{self._next_order_id}",
            symbol=symbol,
            direction=direction,
            qty=qty,
            status="filled",
            fill_price=fill_price,
            fill_qty=qty,
            fee=fee,
        )
        self._next_order_id += 1
        self.orders.append(result)
        self.positions.append({"symbol": symbol, "direction": direction})
        return result

    def get_positions(self) -> list[dict]:
        return [dict(position) for position in self.positions]

    def close_position(
        self,
        symbol: str,
        direction: str,
        qty: float,
        price: float,
        fee: float = 0.0,
    ) -> OrderResult:
        opposite = "short" if direction == "long" else "long"
        result = self.place_order(
            symbol,
            opposite,
            qty,
            order_type="market",
            price=price,
            fee=fee,
        )
        for idx, position in enumerate(self.positions):
            if position["symbol"] == symbol and position["direction"] == direction:
                del self.positions[idx]
                break
        for idx, position in enumerate(self.positions):
            if position["symbol"] == symbol and position["direction"] == opposite:
                del self.positions[idx]
                break
        return result

"""OKX futures calendar-spread data-pipeline primitives.

This module is research infrastructure, not a strategy.  It contains only
deterministic helpers for parsing OKX delivery futures, applying the
pre-registered 72h rollover rule, and building spread-first aligned rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


FIFTEEN_MINUTES_MS = 15 * 60 * 1000
ROLLOVER_BEFORE_EXPIRY_MS = 72 * 60 * 60 * 1000
FOUR_LEG_ROUND_TRIP_COST = 0.0032
ROLLOVER_TWO_LEG_COST = 0.0016


@dataclass(frozen=True)
class DeliveryContract:
    inst_id: str
    family: str
    expiry_ts: int
    listed_ts: int | None = None

    @property
    def rollover_ts(self) -> int:
        return self.expiry_ts - ROLLOVER_BEFORE_EXPIRY_MS


@dataclass(frozen=True)
class SpreadRow:
    ts: int
    future_inst_id: str
    future_close: float
    swap_close: float
    spread_abs: float
    spread_pct: float


def parse_utc_ms(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_okx_delivery_contract(inst_id: str, listed_ts: int | None = None) -> DeliveryContract:
    parts = inst_id.split("-")
    if len(parts) != 3 or len(parts[2]) != 6 or not parts[2].isdigit():
        raise ValueError(f"not an OKX delivery futures instrument id: {inst_id}")
    family = f"{parts[0]}-{parts[1]}"
    yy = int(parts[2][:2])
    month = int(parts[2][2:4])
    day = int(parts[2][4:6])
    year = 2000 + yy
    expiry = datetime(year, month, day, 8, 0, 0, tzinfo=timezone.utc)
    return DeliveryContract(inst_id=inst_id, family=family, expiry_ts=int(expiry.timestamp() * 1000), listed_ts=listed_ts)


def selectable_contracts(contracts: list[DeliveryContract], ts: int, family: str) -> list[DeliveryContract]:
    eligible = [
        contract
        for contract in contracts
        if contract.family == family
        and (contract.listed_ts is None or contract.listed_ts <= ts)
        and ts < contract.rollover_ts
    ]
    return sorted(eligible, key=lambda contract: contract.expiry_ts)


def select_current_and_next_quarter(
    contracts: list[DeliveryContract],
    ts: int,
    family: str,
) -> tuple[DeliveryContract | None, DeliveryContract | None]:
    eligible = selectable_contracts(contracts, ts, family)
    current = eligible[0] if eligible else None
    next_contract = eligible[1] if len(eligible) > 1 else None
    return current, next_contract


def selected_current_contract_id(contracts: list[DeliveryContract], ts: int, family: str) -> str | None:
    current, _next_contract = select_current_and_next_quarter(contracts, ts, family)
    return current.inst_id if current is not None else None


def build_spread_rows(
    futures_close_by_inst: Mapping[str, Mapping[int, float]],
    swap_close: Mapping[int, float],
    contracts: list[DeliveryContract],
    family: str,
) -> list[SpreadRow]:
    """Build a spread-first aligned series from selected futures and swap closes.

    The output does not stitch futures prices into a pseudo-price.  Each row
    records which future was selected at that timestamp, then computes spread
    metrics directly against the aligned swap close.
    """
    timestamps = sorted(swap_close)
    rows: list[SpreadRow] = []
    for ts in timestamps:
        inst_id = selected_current_contract_id(contracts, ts, family)
        if inst_id is None:
            continue
        future_close = futures_close_by_inst.get(inst_id, {}).get(ts)
        swap_price = swap_close.get(ts)
        if future_close is None or swap_price is None or swap_price <= 0:
            continue
        spread_abs = future_close - swap_price
        rows.append(
            SpreadRow(
                ts=ts,
                future_inst_id=inst_id,
                future_close=future_close,
                swap_close=swap_price,
                spread_abs=spread_abs,
                spread_pct=spread_abs / swap_price,
            )
        )
    return rows


def assert_four_leg_cost(cost: float = FOUR_LEG_ROUND_TRIP_COST) -> None:
    if cost < FOUR_LEG_ROUND_TRIP_COST:
        raise ValueError("calendar-spread round-trip cost must be at least 0.0032")

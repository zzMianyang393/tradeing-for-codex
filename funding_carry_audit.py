"""Pre-registered OKX spot/perpetual funding-carry event study.

The study is long spot / short perpetual only, so it does not invent an
unobserved spot-borrow cost.  It uses an already-settled funding rate as the
decision input, enters on the following 15m open, and captures only later
funding settlements.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from config import BacktestConfig
from funding_rate import FundingRate, load_funding_rates


BAR_MS = 15 * 60 * 1000


@dataclass(frozen=True)
class CarrySpec:
    funding_periods_held: int = 3
    cooldown_periods: int = 3


def load_15m_opens(path: Path, start_ts: int, end_ts: int) -> dict[int, float]:
    """Stream a 1m file and retain only first opens in the requested 15m range."""
    opens: dict[int, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                ts = int(row["timestamp_ms"])
                if ts < start_ts or ts > end_ts:
                    continue
                bucket = ts // BAR_MS * BAR_MS
                opens.setdefault(bucket, float(row["open"]))
            except (KeyError, TypeError, ValueError):
                continue
    return opens


def _summary(events: list[dict[str, Any]]) -> dict[str, float | int | None]:
    values = [float(event["net_return"]) for event in events]
    return {
        "events": len(events),
        "avg_funding_income": mean([float(event["funding_income"]) for event in events]) if events else None,
        "avg_hedge_return": mean([float(event["hedge_return"]) for event in events]) if events else None,
        "avg_net_return": mean(values) if values else None,
        "net_win_rate": (sum(value > 0 for value in values) / len(values)) if values else None,
        "net_profit_factor": (
            sum(value for value in values if value > 0) / abs(sum(value for value in values if value < 0))
            if any(value < 0 for value in values)
            else None
        ),
    }


def audit_positive_funding_carry(
    symbol: str,
    funding: list[FundingRate],
    spot_opens: dict[int, float],
    swap_opens: dict[int, float],
    spec: CarrySpec = CarrySpec(),
    four_leg_cost: float | None = None,
) -> dict[str, Any]:
    """Audit positive-funding cash-and-carry with conservative timing.

    At settlement i the realized funding rate is known.  If it alone is at
    least one third of four-leg costs, enter after the event and receive only
    settlements i+1 through i+3.  This avoids using future funding rates for
    entry selection.
    """
    if four_leg_cost is None:
        config = BacktestConfig()
        four_leg_cost = 4.0 * (config.taker_fee + config.slippage)
    threshold = four_leg_cost / spec.funding_periods_held
    events: list[dict[str, Any]] = []
    next_allowed = 0
    for index in range(len(funding) - spec.funding_periods_held):
        if index < next_allowed:
            continue
        trigger = funding[index]
        if trigger.realized_rate < threshold:
            continue
        exit_funding = funding[index + spec.funding_periods_held]
        entry_ts = (trigger.ts // BAR_MS + 1) * BAR_MS
        exit_ts = (exit_funding.ts // BAR_MS + 1) * BAR_MS
        spot_entry = spot_opens.get(entry_ts)
        spot_exit = spot_opens.get(exit_ts)
        swap_entry = swap_opens.get(entry_ts)
        swap_exit = swap_opens.get(exit_ts)
        if not all(value and value > 0 for value in (spot_entry, spot_exit, swap_entry, swap_exit)):
            continue
        funding_income = sum(item.realized_rate for item in funding[index + 1 : index + spec.funding_periods_held + 1])
        hedge_return = (spot_exit / spot_entry - 1.0) - (swap_exit / swap_entry - 1.0)
        events.append(
            {
                "symbol": symbol,
                "trigger_ts": trigger.ts,
                "trigger_rate": trigger.realized_rate,
                "funding_income": funding_income,
                "hedge_return": hedge_return,
                "net_return": funding_income + hedge_return - four_leg_cost,
            }
        )
        next_allowed = index + spec.cooldown_periods
    return {
        "methodology": {
            "position": "long spot, short perpetual",
            "entry": "next 15m open after a known funding settlement",
            "exit": f"next 15m open after {spec.funding_periods_held} later funding settlements",
            "four_leg_cost": four_leg_cost,
            "entry_threshold": threshold,
            "note": "negative-funding carry is excluded because spot borrowing costs are unavailable",
        },
        "spec": asdict(spec),
        "summary": _summary(events),
    }


def _as_of(value: str | None) -> int:
    if value:
        return int(datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit pre-registered positive funding carry.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--basis-data", type=Path, default=Path("data/basis"))
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--as-of", help="UTC date YYYY-MM-DD")
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--out", type=Path, default=Path("reports/funding_carry_formation.json"))
    args = parser.parse_args(argv)
    end_ts = _as_of(args.as_of)
    start_ts = end_ts - args.days * 24 * 60 * 60 * 1000
    reports: dict[str, Any] = {}
    for base in args.symbols:
        funding = [
            item for item in load_funding_rates(args.data / f"{base}-USDT-SWAP_funding.csv")
            if start_ts <= item.ts <= end_ts
        ]
        reports[base] = audit_positive_funding_carry(
            base,
            funding,
            load_15m_opens(args.basis_data / f"{base}-USDT_spot_1m.csv", start_ts, end_ts),
            load_15m_opens(args.basis_data / f"{base}-USDT_swap_1m.csv", start_ts, end_ts),
        )
    payload = {"window_days": args.days, "as_of": args.as_of, "reports": reports}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

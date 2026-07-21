"""Funding term carry audit.

This is research infrastructure, not a runnable strategy.  It audits a
medium-horizon cash-and-carry rule:

  - signal uses only already-settled funding rates
  - compute 7-day average realized funding
  - enter long spot / short perpetual when that average is above the prior
    180-day 80th percentile for the same symbol
  - enter on the next 15m open after the known settlement
  - hold 14 days and collect only future funding settlements
  - charge 0.32% four-leg cost

No parameter scan is performed.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from funding_rate import FundingRate, load_funding_rates


BAR_MS = 15 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
FUNDING_PER_DAY = 3
LOOKBACK_DAYS = 7
HOLD_DAYS = 14
PERCENTILE_LOOKBACK_DAYS = 180
PERCENTILE_THRESHOLD = 0.80
FOUR_LEG_ROUND_TRIP_COST = 0.0032


@dataclass(frozen=True)
class CarryEvent:
    symbol: str
    split: str
    signal_ts: int
    signal_timestamp_utc: str
    entry_ts: int
    entry_timestamp_utc: str
    exit_ts: int
    exit_timestamp_utc: str
    rolling_7d_funding: float
    prior_percentile_threshold: float
    funding_income: float
    hedge_return: float
    gross_return: float
    net_return: float
    net_return_pct: float
    hold_days: int


def parse_date_ms(value: str, end_of_day: bool = False) -> int:
    suffix = " 23:59:59" if end_of_day else " 00:00:00"
    return int(datetime.strptime(value + suffix, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("values must not be empty")
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * q))
    return ordered[index]


def rolling_average(values: list[float], end_index: int, periods: int) -> float | None:
    start = end_index + 1 - periods
    if start < 0:
        return None
    window = values[start : end_index + 1]
    return sum(window) / periods


def load_15m_opens(path: Path, start_ts: int, end_ts: int) -> dict[int, float]:
    opens: dict[int, float] = {}
    if not path.exists():
        return opens
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                raw_ts = row.get("timestamp_ms") or row.get("timestamp")
                if raw_ts is None:
                    continue
                ts = int(raw_ts) if raw_ts.isdigit() else int(
                    datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000
                )
                if ts < start_ts or ts > end_ts:
                    continue
                bucket = ts // BAR_MS * BAR_MS
                opens.setdefault(bucket, float(row["open"]))
            except (KeyError, TypeError, ValueError):
                continue
    return opens


def first_open_at_or_after(opens: dict[int, float], ts: int) -> tuple[int, float] | None:
    bucket = ((ts + BAR_MS - 1) // BAR_MS) * BAR_MS
    for _ in range(96):
        price = opens.get(bucket)
        if price and price > 0:
            return bucket, price
        bucket += BAR_MS
    return None


def split_for_entry(entry_ts: int, formation_start_ts: int, formation_end_ts: int, oos_start_ts: int, oos_end_ts: int) -> str | None:
    if formation_start_ts <= entry_ts <= formation_end_ts:
        return "formation"
    if oos_start_ts <= entry_ts <= oos_end_ts:
        return "oos"
    return None


def audit_symbol(
    symbol: str,
    funding: list[FundingRate],
    spot_opens: dict[int, float],
    swap_opens: dict[int, float],
    formation_start_ts: int,
    formation_end_ts: int,
    oos_start_ts: int,
    oos_end_ts: int,
) -> list[CarryEvent]:
    funding = sorted(funding, key=lambda item: item.ts)
    rates = [item.realized_rate for item in funding]
    rolling_periods = LOOKBACK_DAYS * FUNDING_PER_DAY
    percentile_periods = PERCENTILE_LOOKBACK_DAYS * FUNDING_PER_DAY
    hold_periods = HOLD_DAYS * FUNDING_PER_DAY
    events: list[CarryEvent] = []
    next_allowed_ts = 0

    for index in range(percentile_periods + rolling_periods, len(funding) - hold_periods):
        trigger = funding[index]
        signal_avg = rolling_average(rates, index, rolling_periods)
        if signal_avg is None or signal_avg <= 0:
            continue
        prior_avgs = [
            value
            for prior_index in range(index - percentile_periods, index)
            if (value := rolling_average(rates, prior_index, rolling_periods)) is not None
        ]
        if len(prior_avgs) < percentile_periods - rolling_periods:
            continue
        threshold = percentile(prior_avgs, PERCENTILE_THRESHOLD)
        if signal_avg < threshold:
            continue

        entry_ts = ((trigger.ts // BAR_MS) + 1) * BAR_MS
        if entry_ts < next_allowed_ts:
            continue
        exit_funding = funding[index + hold_periods]
        exit_ts = ((exit_funding.ts // BAR_MS) + 1) * BAR_MS
        if exit_ts > oos_end_ts:
            continue
        split = split_for_entry(entry_ts, formation_start_ts, formation_end_ts, oos_start_ts, oos_end_ts)
        if split is None:
            continue

        spot_entry = first_open_at_or_after(spot_opens, entry_ts)
        swap_entry = first_open_at_or_after(swap_opens, entry_ts)
        spot_exit = first_open_at_or_after(spot_opens, exit_ts)
        swap_exit = first_open_at_or_after(swap_opens, exit_ts)
        if not all((spot_entry, swap_entry, spot_exit, swap_exit)):
            continue
        assert spot_entry is not None and swap_entry is not None and spot_exit is not None and swap_exit is not None

        funding_income = sum(item.realized_rate for item in funding[index + 1 : index + hold_periods + 1])
        spot_return = spot_exit[1] / spot_entry[1] - 1.0
        short_swap_return = 1.0 - swap_exit[1] / swap_entry[1]
        hedge_return = spot_return + short_swap_return
        gross = funding_income + hedge_return
        net = gross - FOUR_LEG_ROUND_TRIP_COST
        events.append(
            CarryEvent(
                symbol=symbol,
                split=split,
                signal_ts=trigger.ts,
                signal_timestamp_utc=format_utc(trigger.ts),
                entry_ts=entry_ts,
                entry_timestamp_utc=format_utc(entry_ts),
                exit_ts=exit_ts,
                exit_timestamp_utc=format_utc(exit_ts),
                rolling_7d_funding=round(signal_avg, 10),
                prior_percentile_threshold=round(threshold, 10),
                funding_income=round(funding_income, 10),
                hedge_return=round(hedge_return, 10),
                gross_return=round(gross, 10),
                net_return=round(net, 10),
                net_return_pct=round(net * 100.0, 6),
                hold_days=HOLD_DAYS,
            )
        )
        next_allowed_ts = exit_ts + BAR_MS
    return events


def summarize(values: list[float]) -> dict[str, float | int]:
    positives = [value for value in values if value > 0]
    negatives = [value for value in values if value <= 0]
    gross_profit = sum(positives)
    gross_loss = abs(sum(negatives))
    return {
        "observations": len(values),
        "sum_pct": round(sum(values), 6) if values else 0.0,
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "median_pct": round(median(values), 6) if values else 0.0,
        "win_rate": round(len(positives) / len(values), 6) if values else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0),
    }


def summarize_events(events: list[CarryEvent]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split in ("formation", "oos"):
        split_events = [event for event in events if event.split == split]
        result[split] = {
            "net": summarize([event.net_return_pct for event in split_events]),
            "funding_income": summarize([event.funding_income * 100.0 for event in split_events]),
            "hedge_return": summarize([event.hedge_return * 100.0 for event in split_events]),
        }
    return result


def concentration(events: list[CarryEvent], split: str) -> dict[str, Any]:
    split_events = [event for event in events if event.split == split]
    month_counts = Counter(event.entry_timestamp_utc[:7] for event in split_events)
    symbol_counts = Counter(event.symbol for event in split_events)
    positive_by_month: Counter[str] = Counter()
    for event in split_events:
        if event.net_return_pct > 0:
            positive_by_month[event.entry_timestamp_utc[:7]] += event.net_return_pct
    total_positive = sum(positive_by_month.values())
    return {
        "events": len(split_events),
        "top_month_event_share": round(max(month_counts.values()) / len(split_events), 6) if split_events else 0.0,
        "top_symbol_event_share": round(max(symbol_counts.values()) / len(split_events), 6) if split_events else 0.0,
        "top_month_positive_contribution_share": round(max(positive_by_month.values()) / total_positive, 6) if total_positive > 0 else 0.0,
        "events_by_month": dict(sorted(month_counts.items())),
        "events_by_symbol": dict(sorted(symbol_counts.items())),
    }


def without_month(events: list[CarryEvent], split: str, month: str) -> dict[str, float | int]:
    return summarize([event.net_return_pct for event in events if event.split == split and not event.entry_timestamp_utc.startswith(month)])


def build_verdict(summary: dict[str, Any], formation_concentration: dict[str, Any], oos_concentration: dict[str, Any]) -> dict[str, Any]:
    formation = summary["formation"]["net"]
    oos = summary["oos"]["net"]
    reasons: list[str] = []
    if int(formation["observations"]) < 10:
        reasons.append(f"formation events {formation['observations']} < 10")
    if float(formation["mean_pct"]) <= 0:
        reasons.append(f"formation net mean {formation['mean_pct']:+.6f}% <= 0")
    if float(formation["win_rate"]) < 0.52:
        reasons.append(f"formation win rate {formation['win_rate']:.2%} < 52%")
    if float(oos["mean_pct"]) <= 0:
        reasons.append(f"oos net mean {oos['mean_pct']:+.6f}% <= 0")
    if float(oos["win_rate"]) < 0.50:
        reasons.append(f"oos win rate {oos['win_rate']:.2%} < 50%")
    if float(formation_concentration["top_month_positive_contribution_share"]) > 0.25:
        reasons.append(
            "formation top month positive contribution "
            f"{formation_concentration['top_month_positive_contribution_share']:.2%} > 25%"
        )
    if float(oos_concentration["top_month_positive_contribution_share"]) > 0.25:
        reasons.append(
            "oos top month positive contribution "
            f"{oos_concentration['top_month_positive_contribution_share']:.2%} > 25%"
        )
    return {
        "status": "rejected" if reasons else "passed_research_screen",
        "eligible_for_strategy": False,
        "reasons": reasons,
    }


def run_audit(
    data_dir: Path,
    basis_dir: Path,
    bases: list[str],
    formation_start: str,
    formation_end: str,
    oos_start: str,
    oos_end: str,
) -> dict[str, Any]:
    formation_start_ts = parse_date_ms(formation_start)
    formation_end_ts = parse_date_ms(formation_end, end_of_day=True)
    oos_start_ts = parse_date_ms(oos_start)
    oos_end_ts = parse_date_ms(oos_end, end_of_day=True)
    load_start_ts = formation_start_ts - (PERCENTILE_LOOKBACK_DAYS + LOOKBACK_DAYS + 3) * DAY_MS
    load_end_ts = oos_end_ts + HOLD_DAYS * DAY_MS

    events: list[CarryEvent] = []
    skipped: dict[str, str] = {}
    for base in bases:
        funding = load_funding_rates(data_dir / f"{base}-USDT-SWAP_funding.csv")
        funding = [item for item in funding if load_start_ts <= item.ts <= load_end_ts]
        spot_opens = load_15m_opens(basis_dir / f"{base}-USDT_spot_1m.csv", load_start_ts, load_end_ts)
        swap_opens = load_15m_opens(basis_dir / f"{base}-USDT_swap_1m.csv", load_start_ts, load_end_ts)
        if len(funding) < (PERCENTILE_LOOKBACK_DAYS + LOOKBACK_DAYS + HOLD_DAYS) * FUNDING_PER_DAY:
            skipped[base] = "insufficient_funding_history"
            continue
        if not spot_opens or not swap_opens:
            skipped[base] = "missing_spot_or_swap_basis_1m"
            continue
        events.extend(
            audit_symbol(
                f"{base}-USDT-SWAP",
                funding,
                spot_opens,
                swap_opens,
                formation_start_ts,
                formation_end_ts,
                oos_start_ts,
                oos_end_ts,
            )
        )

    summary = summarize_events(events)
    formation_concentration = concentration(events, "formation")
    oos_concentration = concentration(events, "oos")
    return {
        "research_id": "funding_term_carry",
        "scope": "event_audit_not_strategy",
        "parameters": {
            "position": "long spot / short perpetual",
            "lookback_days": LOOKBACK_DAYS,
            "hold_days": HOLD_DAYS,
            "percentile_lookback_days": PERCENTILE_LOOKBACK_DAYS,
            "percentile_threshold": PERCENTILE_THRESHOLD,
            "four_leg_round_trip_cost": FOUR_LEG_ROUND_TRIP_COST,
            "entry": "next 15m open after an already-settled funding timestamp",
            "exit": "next 15m open after 14 days; only future funding settlements are collected",
            "overlap_rule": "one open event per symbol; signals during an open event are skipped",
        },
        "formation_period": f"{formation_start} to {formation_end}",
        "oos_period": f"{oos_start} to {oos_end}",
        "bases": bases,
        "skipped_symbols": skipped,
        "summary": summary,
        "formation_concentration": formation_concentration,
        "oos_concentration": oos_concentration,
        "formation_without_2024_11": without_month(events, "formation", "2024-11"),
        "verdict": build_verdict(summary, formation_concentration, oos_concentration),
        "events": [asdict(event) for event in events],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit medium-horizon funding term carry.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--basis-data", type=Path, default=Path("data/basis"))
    parser.add_argument("--bases", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--formation-start", default="2025-01-01")
    parser.add_argument("--formation-end", default="2025-07-10")
    parser.add_argument("--oos-start", default="2025-07-11")
    parser.add_argument("--oos-end", default="2026-06-10")
    parser.add_argument("--out", type=Path, default=Path("reports/funding_term_carry_audit.json"))
    args = parser.parse_args(argv)
    report = run_audit(
        args.data,
        args.basis_data,
        args.bases,
        args.formation_start,
        args.formation_end,
        args.oos_start,
        args.oos_end,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

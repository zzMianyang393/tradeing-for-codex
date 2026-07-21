"""Audit funding-OI joint sentiment signal.

This is a research audit, NOT a strategy. It measures:
1. Cross-coin funding+OI joint extreme events
2. Post-event price paths
3. Event distribution and concentration

Data: OKX perpetual funding rates (24 coins) + daily OI (24 coins) + 15m OHLCV.
Formation period: 365 days up to --as-of date.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev, median


DATA_DIR = Path("data")
COST_ROUND_TRIP = 0.0016  # 0.05% taker + 0.03% slippap * 2


def load_funding_daily(symbol: str, start_ts: int, end_ts: int) -> dict[str, float]:
    """Load daily aggregated funding rates (mean of 3 daily settlements)."""
    path = DATA_DIR / f"{symbol}_funding.csv"
    if not path.exists():
        return {}
    daily: dict[str, list[float]] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["timestamp_ms"])
                if start_ts <= ts <= end_ts:
                    day = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    daily.setdefault(day, []).append(float(row["funding_rate"]))
            except (KeyError, TypeError, ValueError):
                continue
    return {day: mean(rates) for day, rates in daily.items() if rates}


def load_oi_daily(symbol: str, start_ts: int, end_ts: int) -> dict[str, float]:
    """Load daily OI data."""
    path = DATA_DIR / f"{symbol}_open_interest_1d.csv"
    if not path.exists():
        return {}
    oi: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["ts"])
                if start_ts <= ts <= end_ts:
                    day = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
                    oi[day] = float(row["open_interest_usd"])
            except (KeyError, TypeError, ValueError):
                continue
    return oi


def load_ohlcv_15m(symbol: str, start_ts: int, end_ts: int) -> list[dict]:
    """Load 15m OHLCV data."""
    path = DATA_DIR / f"{symbol}_15m.csv"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                if "timestamp_ms" in row:
                    ts = int(row["timestamp_ms"])
                else:
                    ts = int(datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
                if start_ts <= ts <= end_ts:
                    rows.append({"ts": ts, "open": float(row["open"]), "close": float(row["close"])})
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def compute_daily_joint_signals(
    all_funding: dict[str, dict[str, float]],
    all_oi: dict[str, dict[str, float]],
    reference_days: list[str],
) -> list[dict]:
    """Compute daily cross-coin funding+OI joint signals."""
    results = []
    for i in range(1, len(reference_days)):
        today = reference_days[i]
        yesterday = reference_days[i - 1]

        funding_up = 0
        oi_up = 0
        both_up = 0
        total = 0

        for symbol in all_funding:
            if symbol not in all_oi:
                continue
            if yesterday not in all_funding[symbol] or today not in all_funding[symbol]:
                continue
            if yesterday not in all_oi[symbol] or today not in all_oi[symbol]:
                continue

            funding_change = all_funding[symbol][today] - all_funding[symbol][yesterday]
            oi_change = all_oi[symbol][today] - all_oi[symbol][yesterday]

            total += 1
            if funding_change > 0:
                funding_up += 1
            if oi_change > 0:
                oi_up += 1
            if funding_change > 0 and oi_change > 0:
                both_up += 1

        if total < 5:
            continue

        results.append({
            "day": today,
            "total_coins": total,
            "funding_up_pct": funding_up / total,
            "oi_up_pct": oi_up / total,
            "both_up_pct": both_up / total,
        })

    return results


def find_joint_events(
    signals: list[dict],
    both_up_threshold: float = 0.6,
) -> list[dict]:
    """Find days where both funding and OI are rising across coins."""
    events = []
    for s in signals:
        if s["both_up_pct"] >= both_up_threshold:
            events.append({
                "day": s["day"],
                "both_up_pct": s["both_up_pct"],
                "funding_up_pct": s["funding_up_pct"],
                "oi_up_pct": s["oi_up_pct"],
                "total_coins": s["total_coins"],
            })
    return events


def compute_forward_returns(
    events: list[dict],
    ohlcv_data: dict[str, list[dict]],
    horizons_bars: list[int] = [1, 4, 16, 96],
) -> list[dict]:
    """Compute forward returns for each event across all coins."""
    # Build OHLCV lookups
    ohlcv_lookups: dict[str, dict[int, dict]] = {}
    for symbol, rows in ohlcv_data.items():
        ohlcv_lookups[symbol] = {r["ts"]: r for r in rows}

    # Get all OHLCV timestamps (sorted)
    all_ts = set()
    for rows in ohlcv_data.values():
        for r in rows:
            all_ts.add(r["ts"])
    sorted_ts = sorted(all_ts)

    results = []
    for event in events:
        # Find the first OHLCV timestamp on or after the event day
        event_day = event["day"]
        event_dt = datetime.strptime(event_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        event_ts = int(event_dt.timestamp() * 1000)

        entry_idx = None
        for idx, ts in enumerate(sorted_ts):
            if ts >= event_ts:
                entry_idx = idx
                break

        if entry_idx is None:
            continue

        entry_ts = sorted_ts[entry_idx]

        # Compute forward returns for each coin
        coin_returns: dict[str, dict] = {}
        for symbol, lookup in ohlcv_lookups.items():
            if entry_ts not in lookup:
                continue
            entry_price = lookup[entry_ts]["open"]

            for horizon in horizons_bars:
                exit_idx = entry_idx + horizon
                if exit_idx >= len(sorted_ts):
                    continue
                exit_ts = sorted_ts[exit_idx]
                if exit_ts not in lookup:
                    continue
                exit_price = lookup[exit_ts]["close"]

                ret_pct = (exit_price / entry_price - 1.0) * 100
                key = f"fwd_{horizon}bar"
                if key not in coin_returns:
                    coin_returns[key] = []
                coin_returns[key].append(ret_pct)

        # Aggregate across coins
        fwd_returns = {}
        for horizon in horizons_bars:
            key = f"fwd_{horizon}bar"
            if key in coin_returns and coin_returns[key]:
                rets = coin_returns[key]
                fwd_returns[key] = {
                    "n_coins": len(rets),
                    "mean_pct": round(mean(rets), 4),
                    "median_pct": round(median(rets), 4),
                    "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 3),
                    "net_mean_pct": round(mean(rets) - COST_ROUND_TRIP * 100, 4),
                }

        results.append({
            "event_day": event["day"],
            "both_up_pct": event["both_up_pct"],
            "entry_ts": entry_ts,
            **fwd_returns,
        })

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit funding-OI joint sentiment signal.")
    parser.add_argument("--symbols", nargs="+", default=[
        "BTC-USDT-SWAP", "ETH-USDT-SWAP",
        "AAVE-USDT-SWAP", "ADA-USDT-SWAP", "APT-USDT-SWAP", "ARB-USDT-SWAP",
        "ATOM-USDT-SWAP", "AVAX-USDT-SWAP", "BNB-USDT-SWAP", "CRV-USDT-SWAP",
        "DOGE-USDT-SWAP", "DOT-USDT-SWAP", "DYDX-USDT-SWAP", "FIL-USDT-SWAP",
        "IMX-USDT-SWAP", "INJ-USDT-SWAP", "LINK-USDT-SWAP", "LTC-USDT-SWAP",
        "NEAR-USDT-SWAP", "OP-USDT-SWAP", "RENDER-USDT-SWAP",
        "STX-USDT-SWAP", "SUI-USDT-SWAP", "TIA-USDT-SWAP",
        "TRX-USDT-SWAP", "UNI-USDT-SWAP", "XRP-USDT-SWAP",
    ])
    parser.add_argument("--as-of", type=str, default="2025-07-10")
    parser.add_argument("--days", type=int, default=365, help="Formation period length")
    parser.add_argument("--both-up-threshold", type=float, default=0.6, help="Min % of coins with both funding+OI up")
    parser.add_argument("--out", type=Path, default=Path("reports/funding_oi_joint_audit.json"))
    args = parser.parse_args(argv)

    as_of_ts = int(datetime.strptime(args.as_of, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    start_ts = as_of_ts - args.days * 86400 * 1000

    # Load funding and OI data
    print("Loading funding and OI data...")
    all_funding: dict[str, dict[str, float]] = {}
    all_oi: dict[str, dict[str, float]] = {}
    reference_days: set[str] = set()

    for symbol in args.symbols:
        funding = load_funding_daily(symbol, start_ts, as_of_ts)
        oi = load_oi_daily(symbol, start_ts, as_of_ts)
        if funding and oi:
            all_funding[symbol] = funding
            all_oi[symbol] = oi
            reference_days.update(funding.keys())
            print(f"  {symbol}: funding={len(funding)} days, oi={len(oi)} days")

    print(f"\nLoaded data for {len(all_funding)} symbols")
    sorted_days = sorted(reference_days)
    print(f"Reference days: {len(sorted_days)}")

    # Compute joint signals
    print("\nComputing daily joint signals...")
    signals = compute_daily_joint_signals(all_funding, all_oi, sorted_days)
    print(f"Computed {len(signals)} daily signals")

    # Find events
    print(f"\nFinding events (both_up_threshold={args.both_up_threshold})...")
    events = find_joint_events(signals, args.both_up_threshold)
    print(f"Found {len(events)} events")

    # Load OHLCV data
    print("\nLoading OHLCV data...")
    ohlcv_data: dict[str, list[dict]] = {}
    for symbol in args.symbols:
        base_sym = symbol.split("-")[0]
        rows = load_ohlcv_15m(base_sym, start_ts, as_of_ts + 7 * 86400 * 1000)
        if rows:
            ohlcv_data[base_sym] = rows
    print(f"Loaded OHLCV for {len(ohlcv_data)} symbols")

    # Compute forward returns
    if events:
        print("\nComputing forward returns...")
        event_returns = compute_forward_returns(events, ohlcv_data)

        # Aggregate statistics
        fwd_stats = {}
        for horizon in [1, 4, 16, 96]:
            key = f"fwd_{horizon}bar"
            horizon_events = [e for e in event_returns if key in e]
            if horizon_events:
                all_means = [e[key]["mean_pct"] for e in horizon_events]
                all_net_means = [e[key]["net_mean_pct"] for e in horizon_events]
                all_win_rates = [e[key]["win_rate"] for e in horizon_events]
                fwd_stats[key] = {
                    "n_events": len(horizon_events),
                    "avg_mean_pct": round(mean(all_means), 4),
                    "avg_net_mean_pct": round(mean(all_net_means), 4),
                    "avg_win_rate": round(mean(all_win_rates), 3),
                    "positive_events": sum(1 for m in all_means if m > 0),
                    "negative_events": sum(1 for m in all_means if m <= 0),
                }

        # Check month concentration
        from collections import Counter
        month_counts = Counter(e["event_day"][:7] for e in event_returns)
        max_month_pct = max(month_counts.values()) / len(events) if events else 0

        report = {
            "formation_days": args.days,
            "as_of": args.as_of,
            "both_up_threshold": args.both_up_threshold,
            "n_symbols": len(all_funding),
            "n_signals": len(signals),
            "n_events": len(events),
            "events_per_month": round(len(events) / (args.days / 30), 1),
            "month_concentration": {k: v for k, v in sorted(month_counts.items())},
            "max_month_pct": round(max_month_pct, 3),
            "forward_returns": fwd_stats,
            "event_details": event_returns[:10],
        }
    else:
        report = {
            "formation_days": args.days,
            "as_of": args.as_of,
            "both_up_threshold": args.both_up_threshold,
            "n_symbols": len(all_funding),
            "n_signals": len(signals),
            "n_events": 0,
            "note": "No events found at current thresholds",
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

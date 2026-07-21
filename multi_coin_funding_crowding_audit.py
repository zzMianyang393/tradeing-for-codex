"""Audit multi-coin funding crowding reversal hypothesis.

This is a research audit, NOT a strategy. It measures:
1. Cross-coin funding rate extreme events
2. Post-event price paths (do extreme funding readings predict reversals?)
3. Event distribution and concentration

Data: OKX perpetual funding rates (25 coins) + 15m OHLCV.
Formation period: 365 days up to --as-of date.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, stdev, median


FUNDING_DIR = Path("data")
OHLCV_DIR = Path("data")
COST_ROUND_TRIP = 0.0016  # 0.05% taker + 0.03% slippap * 2


def load_funding(symbol: str, start_ts: int, end_ts: int) -> list[dict]:
    """Load funding rates for a symbol within time range."""
    path = FUNDING_DIR / f"{symbol}_funding.csv"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = int(row["timestamp_ms"])
                if start_ts <= ts <= end_ts:
                    rows.append({
                        "ts": ts,
                        "funding_rate": float(row["funding_rate"]),
                    })
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def load_ohlcv_15m(symbol: str, start_ts: int, end_ts: int) -> list[dict]:
    """Load 15m OHLCV data for a symbol."""
    path = OHLCV_DIR / f"{symbol}_15m.csv"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                # Handle both timestamp_ms and timestamp formats
                if "timestamp_ms" in row:
                    ts = int(row["timestamp_ms"])
                else:
                    ts = int(datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)
                if start_ts <= ts <= end_ts:
                    rows.append({
                        "ts": ts,
                        "open": float(row["open"]),
                        "close": float(row["close"]),
                    })
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def compute_cross_coin_funding_stats(
    all_funding: dict[str, list[dict]],
    reference_ts: list[int],
) -> list[dict]:
    """Compute cross-coin funding statistics at each settlement timestamp."""
    # Build per-coin funding lookup
    coin_lookups: dict[str, dict[int, float]] = {}
    for symbol, rows in all_funding.items():
        coin_lookups[symbol] = {r["ts"]: r["funding_rate"] for r in rows}

    results = []
    for ts in reference_ts:
        rates = {}
        for symbol, lookup in coin_lookups.items():
            if ts in lookup:
                rates[symbol] = lookup[ts]

        if len(rates) < 5:  # need at least 5 coins
            continue

        rate_values = list(rates.values())
        mean_rate = mean(rate_values)
        extreme_threshold = 0.0003  # 0.03% funding rate (~P95)
        extreme_count = sum(1 for r in rate_values if r >= extreme_threshold)
        extreme_pct = extreme_count / len(rates)

        results.append({
            "ts": ts,
            "mean_funding": mean_rate,
            "n_coins": len(rates),
            "extreme_count": extreme_count,
            "extreme_pct": extreme_pct,
            "max_funding": max(rate_values),
            "min_funding": min(rate_values),
            "rates": rates,
        })

    return results


def find_crowding_events(
    stats: list[dict],
    percentile_threshold: float = 90.0,
    extreme_pct_threshold: float = 0.5,
) -> list[dict]:
    """Find cross-coin funding crowding events."""
    if len(stats) < 10:
        return []

    # Compute historical percentile
    mean_rates = [s["mean_funding"] for s in stats]
    sorted_rates = sorted(mean_rates)
    idx = min(len(sorted_rates) - 1, int(len(sorted_rates) * percentile_threshold / 100))
    threshold = sorted_rates[idx]

    events = []
    for i, s in enumerate(stats):
        if s["mean_funding"] >= threshold and s["extreme_pct"] >= extreme_pct_threshold:
            events.append({
                "ts": s["ts"],
                "mean_funding": s["mean_funding"],
                "extreme_pct": s["extreme_pct"],
                "n_coins": s["n_coins"],
                "max_funding": s["max_funding"],
                "threshold": threshold,
                "event_idx": i,
            })

    return events


def compute_forward_returns(
    events: list[dict],
    ohlcv_data: dict[str, list[dict]],
    horizons_bars: list[int] = [1, 4, 16],
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
        # Find the next OHLCV timestamp after the event
        event_ts = event["ts"]
        entry_idx = None
        for idx, ts in enumerate(sorted_ts):
            if ts > event_ts:
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
            "event_ts": event["ts"],
            "mean_funding": event["mean_funding"],
            "extreme_pct": event["extreme_pct"],
            "entry_ts": entry_ts,
            **fwd_returns,
        })

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit multi-coin funding crowding reversal.")
    parser.add_argument("--symbols", nargs="+", default=[
        "BTC-USDT-SWAP", "ETH-USDT-SWAP",
        "AAVE-USDT-SWAP", "ADA-USDT-SWAP", "APT-USDT-SWAP", "ARB-USDT-SWAP",
        "ATOM-USDT-SWAP", "AVAX-USDT-SWAP", "BNB-USDT-SWAP", "CRV-USDT-SWAP",
        "DOGE-USDT-SWAP", "DOT-USDT-SWAP", "DYDX-USDT-SWAP", "FIL-USDT-SWAP",
        "IMX-USDT-SWAP", "INJ-USDT-SWAP", "LINK-USDT-SWAP", "LTC-USDT-SWAP",
        "NEAR-USDT-SWAP", "OP-USDT-SWAP", "RENDER-USDT-SWAP", "SEI-USDT-SWAP",
        "SOL-USDT-SWAP", "STX-USDT-SWAP", "SUI-USDT-SWAP", "TIA-USDT-SWAP",
        "TRX-USDT-SWAP", "UNI-USDT-SWAP", "XRP-USDT-SWAP",
    ])
    parser.add_argument("--as-of", type=str, default="2025-07-10")
    parser.add_argument("--days", type=int, default=365, help="Formation period length")
    parser.add_argument("--percentile", type=float, default=90.0, help="Funding percentile threshold")
    parser.add_argument("--extreme-pct", type=float, default=0.5, help="Minimum extreme coin %")
    parser.add_argument("--out", type=Path, default=Path("reports/multi_coin_funding_crowding_audit.json"))
    args = parser.parse_args(argv)

    as_of_ts = int(datetime.strptime(args.as_of, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    start_ts = as_of_ts - args.days * 86400 * 1000

    # Load funding data for all symbols
    print("Loading funding data...")
    all_funding: dict[str, list[dict]] = {}
    for symbol in args.symbols:
        rows = load_funding(symbol, start_ts, as_of_ts)
        if rows:
            all_funding[symbol] = rows
            print(f"  {symbol}: {len(rows)} rows")

    print(f"\nLoaded funding for {len(all_funding)} symbols")

    # Get reference timestamps (use BTC as reference)
    reference_symbol = "BTC-USDT-SWAP"
    if reference_symbol not in all_funding:
        print(f"ERROR: reference symbol {reference_symbol} not found")
        return 1
    reference_ts = [r["ts"] for r in all_funding[reference_symbol]]

    # Compute cross-coin stats
    print("\nComputing cross-coin funding statistics...")
    stats = compute_cross_coin_funding_stats(all_funding, reference_ts)
    print(f"Computed stats for {len(stats)} settlement timestamps")

    # Find crowding events
    print(f"\nFinding crowding events (percentile={args.percentile}, extreme_pct={args.extreme_pct})...")
    events = find_crowding_events(stats, args.percentile, args.extreme_pct)
    print(f"Found {len(events)} crowding events")

    # Load OHLCV data for forward returns
    print("\nLoading OHLCV data...")
    ohlcv_data: dict[str, list[dict]] = {}
    for symbol in args.symbols:
        # Map SWAP symbol to OHLCV symbol format: BTC-USDT-SWAP -> BTC, AAVE-USDT-SWAP -> AAVE
        base_sym = symbol.split("-")[0]
        rows = load_ohlcv_15m(base_sym, start_ts, as_of_ts + 7 * 86400 * 1000)  # extend for forward returns
        if rows:
            ohlcv_data[base_sym] = rows

    print(f"Loaded OHLCV for {len(ohlcv_data)} symbols")

    # Compute forward returns
    if events:
        print("\nComputing forward returns...")
        event_returns = compute_forward_returns(events, ohlcv_data)

        # Aggregate statistics
        fwd_stats = {}
        for horizon in [1, 4, 16]:
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

        report = {
            "formation_days": args.days,
            "as_of": args.as_of,
            "percentile_threshold": args.percentile,
            "extreme_pct_threshold": args.extreme_pct,
            "n_symbols_with_funding": len(all_funding),
            "n_settlement_timestamps": len(stats),
            "n_crowding_events": len(events),
            "events_per_month": round(len(events) / (args.days / 30), 1),
            "cross_coin_stats": {
                "mean_funding_overall": round(mean([s["mean_funding"] for s in stats]), 6),
                "mean_extreme_pct": round(mean([s["extreme_pct"] for s in stats]), 3),
            },
            "event_threshold": events[0]["threshold"] if events else None,
            "forward_returns": fwd_stats,
            "event_details": event_returns[:10],  # first 10 for inspection
        }
    else:
        report = {
            "formation_days": args.days,
            "as_of": args.as_of,
            "percentile_threshold": args.percentile,
            "extreme_pct_threshold": args.extreme_pct,
            "n_symbols_with_funding": len(all_funding),
            "n_settlement_timestamps": len(stats),
            "n_crowding_events": 0,
            "note": "No events found at current thresholds",
            "cross_coin_stats": {
                "mean_funding_overall": round(mean([s["mean_funding"] for s in stats]), 6) if stats else 0,
                "mean_extreme_pct": round(mean([s["extreme_pct"] for s in stats]), 3) if stats else 0,
            },
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

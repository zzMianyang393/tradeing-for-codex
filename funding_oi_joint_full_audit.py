"""Full audit of all funding+OI direction combinations.

Tests 4 scenarios:
1. Both up (funding↑, OI↑) → trend continuation?
2. Both down (funding↓, OI↓) → trend continuation?
3. Funding up, OI down (funding↑, OI↓) → shorts closing?
4. Funding down, OI up (funding↓, OI↑) → new shorts entering?

Data: OKX perpetual funding rates (24 coins) + daily OI (24 coins) + 15m OHLCV.
Formation period: 365 days up to --as-of date.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median


DATA_DIR = Path("data")
COST_ROUND_TRIP = 0.0016


def load_funding_daily(symbol: str, start_ts: int, end_ts: int) -> dict[str, float]:
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


def compute_daily_signals(
    all_funding: dict[str, dict[str, float]],
    all_oi: dict[str, dict[str, float]],
    reference_days: list[str],
) -> list[dict]:
    """Compute daily cross-coin signals for all 4 combinations."""
    results = []
    for i in range(1, len(reference_days)):
        today = reference_days[i]
        yesterday = reference_days[i - 1]

        counts = {"both_up": 0, "both_down": 0, "fund_up_oi_down": 0, "fund_down_oi_up": 0}
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
            if funding_change > 0 and oi_change > 0:
                counts["both_up"] += 1
            elif funding_change < 0 and oi_change < 0:
                counts["both_down"] += 1
            elif funding_change > 0 and oi_change < 0:
                counts["fund_up_oi_down"] += 1
            elif funding_change < 0 and oi_change > 0:
                counts["fund_down_oi_up"] += 1

        if total < 5:
            continue

        results.append({
            "day": today,
            "total_coins": total,
            "both_up_pct": counts["both_up"] / total,
            "both_down_pct": counts["both_down"] / total,
            "fund_up_oi_down_pct": counts["fund_up_oi_down"] / total,
            "fund_down_oi_up_pct": counts["fund_down_oi_up"] / total,
        })

    return results


def find_events(signals: list[dict], scenario: str, threshold: float) -> list[dict]:
    """Find events for a given scenario."""
    key = f"{scenario}_pct"
    return [{"day": s["day"], "pct": s[key], "total_coins": s["total_coins"]}
            for s in signals if s[key] >= threshold]


def compute_forward_returns(events, ohlcv_data, horizons_bars=[1, 4, 16, 96]):
    ohlcv_lookups = {sym: {r["ts"]: r for r in rows} for sym, rows in ohlcv_data.items()}
    all_ts = sorted(set(r["ts"] for rows in ohlcv_data.values() for r in rows))

    results = []
    for event in events:
        event_dt = datetime.strptime(event["day"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        event_ts = int(event_dt.timestamp() * 1000)
        entry_idx = next((idx for idx, ts in enumerate(all_ts) if ts >= event_ts), None)
        if entry_idx is None:
            continue
        entry_ts = all_ts[entry_idx]

        coin_returns = {}
        for symbol, lookup in ohlcv_lookups.items():
            if entry_ts not in lookup:
                continue
            entry_price = lookup[entry_ts]["open"]
            for horizon in horizons_bars:
                exit_idx = entry_idx + horizon
                if exit_idx >= len(all_ts) or all_ts[exit_idx] not in lookup:
                    continue
                ret_pct = (lookup[all_ts[exit_idx]]["close"] / entry_price - 1.0) * 100
                coin_returns.setdefault(f"fwd_{horizon}bar", []).append(ret_pct)

        fwd = {}
        for horizon in horizons_bars:
            key = f"fwd_{horizon}bar"
            if key in coin_returns and coin_returns[key]:
                rets = coin_returns[key]
                fwd[key] = {
                    "n_coins": len(rets),
                    "mean_pct": round(mean(rets), 4),
                    "median_pct": round(median(rets), 4),
                    "win_rate": round(sum(1 for r in rets if r > 0) / len(rets), 3),
                    "net_mean_pct": round(mean(rets) - COST_ROUND_TRIP * 100, 4),
                }

        results.append({"event_day": event["day"], "pct": event["pct"], **fwd})

    return results


def aggregate(event_returns, horizons=[1, 4, 16, 96]):
    stats = {}
    for h in horizons:
        key = f"fwd_{h}bar"
        events = [e for e in event_returns if key in e]
        if events:
            means = [e[key]["mean_pct"] for e in events]
            stats[key] = {
                "n_events": len(events),
                "avg_mean_pct": round(mean(means), 4),
                "avg_net_mean_pct": round(mean(means) - COST_ROUND_TRIP * 100, 4),
                "avg_win_rate": round(mean([e[key]["win_rate"] for e in events]), 3),
                "positive_events": sum(1 for m in means if m > 0),
                "negative_events": sum(1 for m in means if m <= 0),
            }
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=[
        "BTC-USDT-SWAP", "ETH-USDT-SWAP", "AAVE-USDT-SWAP", "ADA-USDT-SWAP",
        "APT-USDT-SWAP", "ARB-USDT-SWAP", "ATOM-USDT-SWAP", "AVAX-USDT-SWAP",
        "BNB-USDT-SWAP", "CRV-USDT-SWAP", "DOGE-USDT-SWAP", "DOT-USDT-SWAP",
        "DYDX-USDT-SWAP", "FIL-USDT-SWAP", "IMX-USDT-SWAP", "INJ-USDT-SWAP",
        "LINK-USDT-SWAP", "LTC-USDT-SWAP", "NEAR-USDT-SWAP", "OP-USDT-SWAP",
        "RENDER-USDT-SWAP", "STX-USDT-SWAP", "SUI-USDT-SWAP", "TIA-USDT-SWAP",
        "TRX-USDT-SWAP", "UNI-USDT-SWAP", "XRP-USDT-SWAP",
    ])
    parser.add_argument("--as-of", default="2025-07-10")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--threshold", type=float, default=0.6)
    parser.add_argument("--out", type=Path, default=Path("reports/funding_oi_joint_full_audit.json"))
    args = parser.parse_args(argv)

    as_of_ts = int(datetime.strptime(args.as_of, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)
    start_ts = as_of_ts - args.days * 86400 * 1000

    # Load data
    all_funding, all_oi = {}, {}
    for sym in args.symbols:
        f = load_funding_daily(sym, start_ts, as_of_ts)
        o = load_oi_daily(sym, start_ts, as_of_ts)
        if f and o:
            all_funding[sym] = f
            all_oi[sym] = o

    sorted_days = sorted(set().union(*[set(d.keys()) for d in all_funding.values()]))
    signals = compute_daily_signals(all_funding, all_oi, sorted_days)

    # Load OHLCV
    ohlcv_data = {}
    for sym in args.symbols:
        base = sym.split("-")[0]
        rows = load_ohlcv_15m(base, start_ts, as_of_ts + 7 * 86400 * 1000)
        if rows:
            ohlcv_data[base] = rows

    # Test all 4 scenarios
    scenarios = ["both_up", "both_down", "fund_up_oi_down", "fund_down_oi_up"]
    report = {"threshold": args.threshold, "n_signals": len(signals), "n_symbols": len(all_funding), "scenarios": {}}

    for scenario in scenarios:
        events = find_events(signals, scenario, args.threshold)
        if events:
            event_returns = compute_forward_returns(events, ohlcv_data)
            from collections import Counter
            months = Counter(e["event_day"][:7] for e in event_returns)
            report["scenarios"][scenario] = {
                "n_events": len(events),
                "month_dist": dict(sorted(months.items())),
                "max_month_pct": round(max(months.values()) / len(events), 3) if events else 0,
                "forward_returns": aggregate(event_returns),
            }
        else:
            report["scenarios"][scenario] = {"n_events": 0}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

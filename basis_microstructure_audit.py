"""Audit basis microstructure dynamics using 1m spot/perp data.

This is a research audit, NOT a strategy. It measures:
1. Basis突变 events: large basis changes in short windows
2. Basis volatility clustering: does high basis vol predict future price vol?
3. Basis-price divergence: when basis and price move in opposite directions
4. Post-event price paths: do basis突变 events predict subsequent returns?

Data: OKX 1m spot + perpetual candles for BTC/ETH.
Formation period: 180 days up to --as-of date.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, stdev, median


def load_1m(path: Path) -> list[dict]:
    """Load 1m candle data."""
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                rows.append({
                    "ts": int(row["timestamp_ms"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                })
            except (KeyError, TypeError, ValueError):
                continue
    return rows


def align_series(spot: list[dict], swap: list[dict]) -> list[dict]:
    """Align spot and swap by timestamp, compute basis."""
    spot_map = {r["ts"]: r for r in spot}
    swap_map = {r["ts"]: r for r in swap}
    common_ts = sorted(set(spot_map) & set(swap_map))

    aligned = []
    for ts in common_ts:
        s = spot_map[ts]
        w = swap_map[ts]
        if s["close"] > 0:
            basis = (w["close"] / s["close"] - 1.0) * 10000  # in bps
            aligned.append({
                "ts": ts,
                "spot_close": s["close"],
                "swap_close": w["close"],
                "basis_bps": basis,
                "spot_volume": s["volume"],
                "swap_volume": w["volume"],
            })
    return aligned


def resample_to_15m(aligned: list[dict]) -> list[dict]:
    """Resample 1m aligned data to 15m bars."""
    bar_ms = 15 * 60 * 1000
    bars: dict[int, list[dict]] = {}
    for row in aligned:
        bucket = (row["ts"] // bar_ms) * bar_ms
        bars.setdefault(bucket, []).append(row)

    result = []
    for bucket_ts in sorted(bars):
        bucket = bars[bucket_ts]
        if len(bucket) < 5:  # need at least 5 minutes for a valid bar
            continue
        result.append({
            "ts": bucket_ts,
            "basis_open": bucket[0]["basis_bps"],
            "basis_close": bucket[-1]["basis_bps"],
            "basis_high": max(r["basis_bps"] for r in bucket),
            "basis_low": min(r["basis_bps"] for r in bucket),
            "spot_open": bucket[0]["spot_close"],
            "spot_close": bucket[-1]["spot_close"],
            "swap_open": bucket[0]["swap_close"],
            "swap_close": bucket[-1]["swap_close"],
            "spot_volume": sum(r["spot_volume"] for r in bucket),
            "swap_volume": sum(r["swap_volume"] for r in bucket),
            "basis_change_bps": bucket[-1]["basis_bps"] - bucket[0]["basis_bps"],
            "basis_range_bps": max(r["basis_bps"] for r in bucket) - min(r["basis_bps"] for r in bucket),
        })
    return result


def compute_basis_stats(bars_15m: list[dict]) -> dict:
    """Compute basic basis statistics."""
    basis_values = [b["basis_close"] for b in bars_15m]
    basis_changes = [b["basis_change_bps"] for b in bars_15m]
    basis_ranges = [b["basis_range_bps"] for b in bars_15m]

    def quantile(data: list[float], q: float) -> float:
        if not data:
            return 0.0
        idx = min(len(data) - 1, int(len(data) * q))
        return sorted(data)[idx]

    return {
        "n_bars": len(bars_15m),
        "basis_bps": {
            "mean": mean(basis_values) if basis_values else 0,
            "median": median(basis_values) if basis_values else 0,
            "stdev": stdev(basis_values) if len(basis_values) > 1 else 0,
            "p05": quantile(basis_values, 0.05),
            "p25": quantile(basis_values, 0.25),
            "p75": quantile(basis_values, 0.75),
            "p95": quantile(basis_values, 0.95),
        },
        "basis_change_bps": {
            "mean": mean(basis_changes) if basis_changes else 0,
            "stdev": stdev(basis_changes) if len(basis_changes) > 1 else 0,
            "p05": quantile(basis_changes, 0.05),
            "p95": quantile(basis_changes, 0.95),
        },
        "basis_range_bps": {
            "mean": mean(basis_ranges) if basis_ranges else 0,
            "p95": quantile(basis_ranges, 0.95),
        },
    }


def find_basis突变_events(
    bars_15m: list[dict],
    threshold_sigma: float = 2.5,
    lookback_bars: int = 16,  # 4 hours
) -> list[dict]:
    """Find basis突变 events: large basis changes exceeding threshold * rolling stdev."""
    events = []

    for i in range(lookback_bars, len(bars_15m)):
        # Compute rolling stdev of basis changes
        window = bars_15m[i - lookback_bars:i]
        changes = [b["basis_change_bps"] for b in window]
        if len(changes) < 5:
            continue
        mu = mean(changes)
        sigma = stdev(changes)
        if sigma < 0.1:  # skip near-zero volatility
            continue

        current_change = bars_15m[i]["basis_change_bps"]
        z_score = (current_change - mu) / sigma

        if abs(z_score) >= threshold_sigma:
            # Compute forward returns (next 1, 4, 16 bars = 15m, 1h, 4h)
            fwd_returns = {}
            for horizon in [1, 4, 16]:
                if i + horizon < len(bars_15m):
                    spot_ret = (bars_15m[i + horizon]["spot_close"] / bars_15m[i]["spot_close"] - 1.0) * 100
                    swap_ret = (bars_15m[i + horizon]["swap_close"] / bars_15m[i]["swap_close"] - 1.0) * 100
                    fwd_returns[f"fwd_{horizon}bar_spot_pct"] = round(spot_ret, 4)
                    fwd_returns[f"fwd_{horizon}bar_swap_pct"] = round(swap_ret, 4)

            events.append({
                "ts": bars_15m[i]["ts"],
                "basis_change_bps": round(current_change, 2),
                "z_score": round(z_score, 2),
                "rolling_sigma_bps": round(sigma, 2),
                "direction": "basis_widening" if z_score > 0 else "basis_narrowing",
                "spot_volume": bars_15m[i]["spot_volume"],
                "swap_volume": bars_15m[i]["swap_volume"],
                **fwd_returns,
            })

    return events


def compute_vol_clustering(bars_15m: list[dict], lookback_bars: int = 96) -> dict:
    """Test whether basis volatility clusters and predicts price volatility."""
    if len(bars_15m) < lookback_bars * 2:
        return {"error": "insufficient data"}

    basis_changes = [b["basis_change_bps"] for b in bars_15m]
    spot_returns = []
    for i in range(1, len(bars_15m)):
        if bars_15m[i - 1]["spot_close"] > 0:
            spot_returns.append((bars_15m[i]["spot_close"] / bars_15m[i - 1]["spot_close"] - 1.0) * 10000)
        else:
            spot_returns.append(0)

    # Compute rolling basis vol and future price vol
    pairs = []
    for i in range(lookback_bars, len(bars_15m) - lookback_bars):
        basis_vol = stdev(basis_changes[i - lookback_bars:i])
        future_price_vol = stdev(spot_returns[i:i + lookback_bars])
        pairs.append((basis_vol, future_price_vol))

    if len(pairs) < 10:
        return {"error": "insufficient pairs"}

    # Simple correlation
    bv = [p[0] for p in pairs]
    fpv = [p[1] for p in pairs]
    n = len(bv)
    mean_bv = mean(bv)
    mean_fpv = mean(fpv)
    cov = sum((bv[i] - mean_bv) * (fpv[i] - mean_fpv) for i in range(n)) / n
    std_bv = stdev(bv)
    std_fpv = stdev(fpv)
    correlation = cov / (std_bv * std_fpv) if std_bv > 0 and std_fpv > 0 else 0

    return {
        "n_pairs": n,
        "basis_vol_mean_bps": round(mean(bv), 2),
        "price_vol_mean_bps": round(mean(fpv), 2),
        "correlation": round(correlation, 4),
        "interpretation": "positive = basis vol clusters with future price vol" if correlation > 0.1 else "weak/no relationship",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit basis microstructure dynamics.")
    parser.add_argument("--data", type=Path, default=Path("data/basis"))
    parser.add_argument("--pairs", nargs="+", default=["BTC-USDT", "ETH-USDT"])
    parser.add_argument("--as-of", type=str, default="2025-07-10", help="Formation period end date")
    parser.add_argument("--days", type=int, default=180, help="Formation period length in days")
    parser.add_argument("--out", type=Path, default=Path("reports/basis_microstructure_audit.json"))
    parser.add_argument("--threshold-sigma", type=float, default=2.5, help="Z-score threshold for basis突变 events")
    args = parser.parse_args(argv)

    as_of_ts = int(
        __import__("datetime").datetime.strptime(args.as_of, "%Y-%m-%d").timestamp() * 1000
    )
    start_ts = as_of_ts - args.days * 86400 * 1000

    report = {}
    for pair in args.pairs:
        print(f"Processing {pair}...")
        spot_path = args.data / f"{pair}_spot_1m.csv"
        swap_path = args.data / f"{pair}_swap_1m.csv"

        if not spot_path.exists() or not swap_path.exists():
            report[pair] = {"error": "data files not found"}
            continue

        spot = load_1m(spot_path)
        swap = load_1m(swap_path)
        print(f"  Loaded {len(spot)} spot rows, {len(swap)} swap rows")

        # Filter to formation period
        spot = [r for r in spot if start_ts <= r["ts"] <= as_of_ts]
        swap = [r for r in swap if start_ts <= r["ts"] <= as_of_ts]
        print(f"  Formation period: {len(spot)} spot rows, {len(swap)} swap rows")

        aligned = align_series(spot, swap)
        print(f"  Aligned: {len(aligned)} rows")

        bars_15m = resample_to_15m(aligned)
        print(f"  15m bars: {len(bars_15m)}")

        stats = compute_basis_stats(bars_15m)
        events = find_basis突变_events(bars_15m, threshold_sigma=args.threshold_sigma)
        vol_clustering = compute_vol_clustering(bars_15m)

        # Analyze events
        if events:
            # Event statistics
            n_events = len(events)
            widening_events = [e for e in events if e["direction"] == "basis_widening"]
            narrowing_events = [e for e in events if e["direction"] == "basis_narrowing"]

            # Forward return analysis
            fwd_stats = {}
            for horizon in [1, 4, 16]:
                key_spot = f"fwd_{horizon}bar_spot_pct"
                key_swap = f"fwd_{horizon}bar_swap_pct"
                spot_rets = [e[key_spot] for e in events if key_spot in e]
                swap_rets = [e[key_swap] for e in events if key_swap in e]
                if spot_rets:
                    fwd_stats[f"fwd_{horizon}bar"] = {
                        "n": len(spot_rets),
                        "spot_mean_pct": round(mean(spot_rets), 4),
                        "swap_mean_pct": round(mean(swap_rets), 4),
                        "spot_win_rate": round(sum(1 for r in spot_rets if r > 0) / len(spot_rets), 3),
                        "direction_consistency": "positive" if mean(spot_rets) > 0 and mean(swap_rets) > 0 else "mixed",
                    }

            event_report = {
                "total_events": n_events,
                "widening_events": len(widening_events),
                "narrowing_events": len(narrowing_events),
                "avg_z_score": round(mean([abs(e["z_score"]) for e in events]), 2),
                "forward_returns": fwd_stats,
            }
        else:
            event_report = {"total_events": 0, "note": "no events found at threshold_sigma=" + str(args.threshold_sigma)}

        report[pair] = {
            "formation_days": args.days,
            "as_of": args.as_of,
            "threshold_sigma": args.threshold_sigma,
            "basis_stats": stats,
            "basis突变_events": event_report,
            "volatility_clustering": vol_clustering,
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

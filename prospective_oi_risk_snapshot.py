"""Prospective OI risk snapshot generator.

Reads raw daily OI data from OKX and produces risk state snapshots.
Each snapshot is available at 16:15 UTC (after 16:00 OI formation).

This is a CONTEXT/RISK snapshot only.  It does NOT:
  - Generate trading signals
  - Block or veto any signal
  - Calculate returns or PnL
  - Import runner.py

risk_state_candidate is descriptive only: normal / elevated_deleveraging_risk.
It NEVER means long / short / trade / veto.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median, stdev


DATA_DIR = Path("data")
OI_AVAILABILITY_HOUR = 16
OI_AVAILABILITY_MINUTE = 15


def load_oi_series(symbol: str, start_ts: int, end_ts: int) -> list[dict]:
    """Load daily OI records within [start_ts, end_ts]."""
    path = DATA_DIR / f"{symbol}_open_interest_1d.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                ts = int(r["ts"])
                if start_ts <= ts <= end_ts:
                    rows.append({
                        "ts": ts,
                        "timestamp_utc": r.get("timestamp_utc", ""),
                        "oi_usd": float(r["open_interest_usd"]),
                    })
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(rows, key=lambda x: x["ts"])


def compute_daily_changes(oi_series: list[dict]) -> list[dict]:
    """Compute daily OI changes (percentage)."""
    changes = []
    for i in range(1, len(oi_series)):
        prev = oi_series[i - 1]["oi_usd"]
        curr = oi_series[i]["oi_usd"]
        if prev > 0:
            pct = (curr / prev - 1.0) * 100
            changes.append({
                "ts": oi_series[i]["ts"],
                "timestamp_utc": oi_series[i]["timestamp_utc"],
                "oi_usd": curr,
                "change_pct": round(pct, 4),
            })
    return changes


def generate_snapshots(
    all_changes: dict[str, list[dict]],
    cutoff_ts: int,
) -> list[dict]:
    """Generate cross-coin OI risk snapshots for each day.

    available_ts = OI ts + 16:15 UTC offset (same day).
    """
    # Group by timestamp
    by_ts: dict[int, list[dict]] = {}
    for sym, changes in all_changes.items():
        for c in changes:
            by_ts.setdefault(c["ts"], []).append({"symbol": sym, **c})

    snapshots = []
    for ts in sorted(by_ts):
        entries = by_ts[ts]
        if len(entries) < 5:
            continue

        # available_ts = this day's 16:15 UTC
        day_str = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        avail_dt = datetime.strptime(
            f"{day_str} {OI_AVAILABILITY_HOUR}:{OI_AVAILABILITY_MINUTE}:00",
            "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
        avail_ts = int(avail_dt.timestamp() * 1000)

        # Only include if available before cutoff
        if avail_ts > cutoff_ts:
            continue

        changes_pct = [e["change_pct"] for e in entries]
        abs_changes = [abs(c) for c in changes_pct]

        # Qualified: |change| >= 5%
        qualified_count = sum(1 for c in abs_changes if c >= 5.0)
        qualified_fraction = qualified_count / len(entries)

        median_abs = median(abs_changes) if abs_changes else 0

        # Risk state: elevated if significant deleveraging
        negative_count = sum(1 for c in changes_pct if c <= -5.0)
        negative_fraction = negative_count / len(entries)

        if negative_fraction >= 0.3:
            risk_state = "elevated_deleveraging_risk"
        else:
            risk_state = "normal"

        snapshots.append({
            "snapshot_ts": ts,
            "available_ts": avail_ts,
            "available_timestamp_utc": avail_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "qualified_coin_count": qualified_count,
            "qualified_fraction": round(qualified_fraction, 4),
            "median_abs_change_pct": round(median_abs, 4),
            "risk_state_candidate": risk_state,
            "observation_only": True,
        })

    return snapshots


def main(argv=None):
    p = argparse.ArgumentParser(description="Prospective OI risk snapshot generator.")
    p.add_argument("--symbols", nargs="+", default=[
        "BTC-USDT-SWAP", "ETH-USDT-SWAP", "AAVE-USDT-SWAP", "ADA-USDT-SWAP",
        "APT-USDT-SWAP", "ARB-USDT-SWAP", "ATOM-USDT-SWAP", "AVAX-USDT-SWAP",
        "CRV-USDT-SWAP", "DOGE-USDT-SWAP", "DOT-USDT-SWAP", "DYDX-USDT-SWAP",
        "FIL-USDT-SWAP", "IMX-USDT-SWAP", "INJ-USDT-SWAP", "LINK-USDT-SWAP",
        "LTC-USDT-SWAP", "NEAR-USDT-SWAP", "OP-USDT-SWAP", "RENDER-USDT-SWAP",
        "STX-USDT-SWAP", "SUI-USDT-SWAP", "TIA-USDT-SWAP", "TRX-USDT-SWAP",
        "UNI-USDT-SWAP",
    ])
    p.add_argument("--cutoff", type=str, default=None, help="Override cutoff (default: ledger)")
    p.add_argument("--out", type=Path, default=Path("reports/prospective_oi_risk_snapshot.json"))
    args = p.parse_args(argv)

    # Determine cutoff
    if args.cutoff:
        cutoff_ts = int(
            datetime.strptime(args.cutoff, "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=timezone.utc).timestamp() * 1000
        )
    else:
        ledger_path = Path("reports/prospective_shadow_signal_ledger.json")
        if ledger_path.exists():
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            cutoff_str = ledger.get("common_data_cutoff", "2026-07-13 08:15:00")
        else:
            cutoff_str = "2026-07-13 08:15:00"
        cutoff_ts = int(
            datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=timezone.utc).timestamp() * 1000
        )

    # Load OI data (18 months before cutoff)
    start_ts = cutoff_ts - 18 * 30 * 86400 * 1000

    print("Loading OI data...")
    all_changes: dict[str, list[dict]] = {}
    for sym in args.symbols:
        oi = load_oi_series(sym, start_ts, cutoff_ts)
        if len(oi) < 10:
            print(f"  {sym}: insufficient data ({len(oi)} rows)")
            continue
        changes = compute_daily_changes(oi)
        all_changes[sym] = changes
        print(f"  {sym}: {len(changes)} daily changes")

    print(f"\n{len(all_changes)} symbols loaded")

    # Generate snapshots
    snapshots = generate_snapshots(all_changes, cutoff_ts)
    print(f"Generated {len(snapshots)} snapshots")

    # Risk state distribution
    from collections import Counter
    state_counts = Counter(s["risk_state_candidate"] for s in snapshots)

    output = {
        "snapshot_type": "prospective_oi_risk_snapshot",
        "generation_date": "2026-07-14",
        "observation_only": True,
        "cutoff_ts": cutoff_ts,
        "cutoff_utc": datetime.fromtimestamp(cutoff_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "n_symbols": len(all_changes),
        "n_snapshots": len(snapshots),
        "risk_state_distribution": dict(state_counts),
        "snapshots": snapshots,
        "methodology_notes": [
            "OI daily values formed at 16:00 UTC.",
            "available_ts = 16:15 UTC on the same day.",
            "risk_state_candidate is descriptive only: normal / elevated_deleveraging_risk.",
            "This is a context/risk snapshot, NOT a trading signal or veto.",
            "No returns, PnL, or price data.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")

    for state, count in sorted(state_counts.items()):
        print(f"  {state}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

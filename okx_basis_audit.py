"""Descriptive audit for aligned OKX spot/perpetual basis data."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any


BAR_MS = 15 * 60 * 1000
ROUND_TRIP_TWO_LEG_COST = 0.0028


def load_15m_close(path: Path) -> dict[int, float]:
    closes: dict[int, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                bucket = int(row["timestamp_ms"]) // BAR_MS * BAR_MS
                closes[bucket] = float(row["close"])
            except (KeyError, TypeError, ValueError):
                continue
    return closes


def _runs(flags: list[bool]) -> list[int]:
    lengths: list[int] = []
    current = 0
    for flag in flags:
        if flag:
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return lengths


def audit_pair(spot: dict[int, float], swap: dict[int, float]) -> dict[str, Any]:
    timestamps = sorted(set(spot) & set(swap))
    basis = [(swap[ts] / spot[ts] - 1.0) for ts in timestamps if spot[ts] > 0]
    ordered = sorted(basis)
    profitable = [value >= ROUND_TRIP_TWO_LEG_COST for value in basis]
    inverse_profitable = [value <= -ROUND_TRIP_TWO_LEG_COST for value in basis]
    positive_runs = _runs(profitable)
    negative_runs = _runs(inverse_profitable)
    def quantile(fraction: float) -> float:
        return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))] if ordered else 0.0
    return {
        "aligned_15m_bars": len(basis),
        "coverage_days": len(basis) / 96.0,
        "basis_bps": {"p05": quantile(0.05) * 10_000, "median": median(basis) * 10_000 if basis else 0.0, "p95": quantile(0.95) * 10_000},
        "cost_threshold_pct": ROUND_TRIP_TWO_LEG_COST * 100.0,
        "swap_premium": {
            "bars_at_or_above_cost": sum(profitable),
            "share": sum(profitable) / len(basis) if basis else 0.0,
            "median_run_15m_bars": median(positive_runs) if positive_runs else 0.0,
            "max_run_15m_bars": max(positive_runs, default=0),
        },
        "swap_discount": {
            "bars_at_or_below_cost": sum(inverse_profitable),
            "share": sum(inverse_profitable) / len(basis) if basis else 0.0,
            "median_run_15m_bars": median(negative_runs) if negative_runs else 0.0,
            "max_run_15m_bars": max(negative_runs, default=0),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit aligned OKX spot/swap basis without generating trades.")
    parser.add_argument("--data", type=Path, default=Path("data/basis"))
    parser.add_argument("--pairs", nargs="+", default=["BTC-USDT", "ETH-USDT"])
    parser.add_argument("--out", type=Path, default=Path("reports/okx_basis_audit.json"))
    args = parser.parse_args(argv)
    report = {
        pair: audit_pair(load_15m_close(args.data / f"{pair}_spot_1m.csv"), load_15m_close(args.data / f"{pair}_swap_1m.csv"))
        for pair in args.pairs
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

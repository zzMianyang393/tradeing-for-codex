"""Precompute candidate events for fast, auditable CP backtests.

Usage:
    python cp_precompute.py --days 365 --symbols 5 --output reports/candidates_365d.jsonl
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from candidate_pipeline import _build_index, _common_timeline
from candidate_pool import save_candidates_indexed, scan_all_symbols
from market import discover_symbols, load_market


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute candidate-pool events.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--symbols", type=int, default=0, help="Limit symbols; 0 means all")
    parser.add_argument("--min-proximity", type=float, default=0.25)
    parser.add_argument("--output", type=Path, default=Path("reports/candidate_pool/candidates_precomputed.jsonl"))
    args = parser.parse_args()

    selected_symbols = None
    if args.symbols > 0:
        selected_symbols = set(discover_symbols(args.data)[:args.symbols])
    print(f"Loading 15m market data from {args.data}...", flush=True)
    market = load_market(args.data, 15, symbols=selected_symbols)
    if not market:
        raise SystemExit("No market data found")

    timeline = _common_timeline(market)
    if args.days is not None:
        start_ts = timeline[-1] - args.days * 24 * 60 * 60 * 1000
        timeline = [ts for ts in timeline if ts >= start_ts]
    index = _build_index(market)
    print(f"Scanning {len(market)} symbols across {len(timeline)} bars...", flush=True)
    candidates = scan_all_symbols(market, timeline, index, args.min_proximity)
    save_candidates_indexed(candidates, args.output)
    metadata = {
        "kind": "candidate_pool_events",
        "timeframe_minutes": 15,
        "days": args.days,
        "symbols": sorted(market),
        "min_proximity": args.min_proximity,
        "candidates": len(candidates),
        "output": str(args.output),
    }
    metadata_path = args.output.with_suffix(args.output.suffix + ".meta.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(candidates)} candidates to {args.output}", flush=True)


if __name__ == "__main__":
    main()

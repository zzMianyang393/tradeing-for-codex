"""Precompute MFE/MAE labels for a candidate JSONL file."""
from __future__ import annotations

import argparse
from pathlib import Path

from candidate_pool import CandidateEventStore, save_candidates_indexed
from candidate_pipeline import _build_index
from market import discover_symbols, load_market
from mfe_labeler import label_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute candidate MFE/MAE labels")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--symbols", type=int, default=0)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--min-mfe", type=float, default=0.003)
    parser.add_argument("--stop-atr", type=float, default=2.0)
    parser.add_argument("--take-profit-atr", type=float, default=1.2)
    parser.add_argument("--trailing-atr", type=float, default=1.8)
    parser.add_argument("--max-hold-bars", type=int, default=8)
    parser.add_argument("--taker-fee", type=float, default=0.0005)
    parser.add_argument("--slippage", type=float, default=0.0002)
    args = parser.parse_args()

    selected = None
    if args.symbols > 0:
        selected = set(discover_symbols(args.data)[:args.symbols])
    print(f"Loading market data from {args.data}...", flush=True)
    market = load_market(args.data, 15, symbols=selected)
    index = _build_index(market)
    store = CandidateEventStore(args.candidates)

    def labeled_events():
        total = 0
        labeled_count = 0
        for candidate in store.iter_candidates():
            total += 1
            labeled = label_candidates(
                [candidate],
                market,
                index,
                horizon_bars=args.horizon,
                min_mfe_pct=args.min_mfe,
                stop_atr=args.stop_atr,
                take_profit_atr=args.take_profit_atr,
                trailing_atr=args.trailing_atr,
                max_hold_bars=args.max_hold_bars,
                taker_fee=args.taker_fee,
                slippage=args.slippage,
            )
            if labeled:
                labeled_count += 1
                yield labeled[0]
            if total % 50_000 == 0:
                print(f"Labeled {total} candidates...", flush=True)
        print(f"Finished: {labeled_count}/{total} labeled", flush=True)

    save_candidates_indexed(labeled_events(), args.output)
    store.close()
    print(f"Saved labeled candidates to {args.output}", flush=True)


if __name__ == "__main__":
    main()

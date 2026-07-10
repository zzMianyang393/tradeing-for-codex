"""Pre-train candidate pool ML model and save to file.

Usage:
    python cp_pretrain.py [--data-dir data] [--symbols 3] [--days 30] [--output reports/cp_model.json]
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from candidate_pool import scan_all_symbols
from candidate_filter import CandidateFilter, RuleFilterConfig, MLFilterConfig
from market import load_market
from mfe_labeler import label_candidates, print_label_report


def _build_index(market):
    return {s: {b.ts: i for i, b in enumerate(bars)} for s, bars in market.items()}


def _common_timeline(market, min_frac=0.50):
    counts = {}
    for bars in market.values():
        for bar in bars:
            counts[bar.ts] = counts.get(bar.ts, 0) + 1
    min_count = max(1, int(len(market) * min_frac))
    return sorted(ts for ts, c in counts.items() if c >= min_count)


def pretrain(
    data_dir: Path,
    n_symbols: int = 5,
    train_days: int = 30,
    timeframe: int = 15,
    min_proximity: float = 0.25,
    horizon_bars: int = 8,
    min_mfe_pct: float = 0.003,
    output: Path | None = None,
) -> dict:
    if output is None:
        output = Path("reports/cp_model.json")

    # Load market
    print(f"Loading market data...")
    market_full = load_market(data_dir, timeframe)
    symbols = list(market_full.keys())[:n_symbols]
    market = {s: market_full[s] for s in symbols}
    print(f"  Using {len(market)} symbols: {symbols}")

    # Build timeline
    timeline = _common_timeline(market)
    index = _build_index(market)
    if train_days:
        start_ts = timeline[-1] - train_days * 24 * 3600 * 1000
        timeline = [ts for ts in timeline if ts >= start_ts]
    print(f"  Timeline: {len(timeline)} bars ({train_days} days)")

    # L1: Scan candidates
    print(f"\nL1: Scanning candidates (min_proximity={min_proximity})...")
    t0 = time.time()
    candidates = scan_all_symbols(market, timeline, index, min_proximity)
    print(f"  {len(candidates)} candidates ({time.time()-t0:.1f}s)")

    # L2: Label
    print(f"\nL2: Labeling (horizon={horizon_bars}, min_mfe={min_mfe_pct})...")
    t0 = time.time()
    labeled = label_candidates(candidates, market, index, horizon_bars, min_mfe_pct)
    profitable = sum(1 for c in labeled if c.label == 1)
    print(f"  {len(labeled)} labeled, {profitable} profitable ({profitable/max(len(labeled),1):.1%}) ({time.time()-t0:.1f}s)")

    # L3: Train ML
    print(f"\nL3: Training ML filter...")
    filt = CandidateFilter(
        rule_config=RuleFilterConfig(min_proximity=min_proximity),
        ml_config=MLFilterConfig(n_estimators=80, learning_rate=0.08),
    )
    ml_stats = filt.train_ml(labeled)
    print(f"  {ml_stats}")

    # Save
    filt.save_ml(str(output))
    print(f"\nModel saved to {output}")

    # Quick eval
    filtered = filt.filter_candidates(labeled)
    print(f"Filter: {len(labeled)} → {len(filtered)} ({len(filtered)/max(len(labeled),1):.1%} retention)")

    return {
        "symbols": symbols,
        "train_days": train_days,
        "candidates": len(candidates),
        "labeled": len(labeled),
        "profitable": profitable,
        "ml_stats": ml_stats,
        "output": str(output),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--symbols", type=int, default=5)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--min-proximity", type=float, default=0.25)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("reports/cp_model.json"))
    args = parser.parse_args()
    pretrain(args.data_dir, args.symbols, args.days, args.timeframe,
             args.min_proximity, args.horizon, output=args.output)


if __name__ == "__main__":
    main()

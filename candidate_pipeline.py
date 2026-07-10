"""Full pipeline runner: L1 Candidate Pool → L2 MFE/MAE Labels → L3 Filter.

Usage:
    python candidate_pipeline.py [--days 90] [--data-dir data] [--min-proximity 0.15]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from candidate_filter import CandidateFilter, RuleFilterConfig, MLFilterConfig
from candidate_pool import scan_all_symbols, save_candidates
from market import load_market
from mfe_labeler import label_candidates, print_label_report


def _build_index(market):
    return {symbol: {bar.ts: idx for idx, bar in enumerate(bars)} for symbol, bars in market.items()}


def _common_timeline(market, min_frac=0.50):
    counts = {}
    for bars in market.values():
        for bar in bars:
            counts[bar.ts] = counts.get(bar.ts, 0) + 1
    min_count = max(1, int(len(market) * min_frac))
    return sorted(ts for ts, c in counts.items() if c >= min_count)


def run_pipeline(
    data_dir: Path,
    days: int | None = 90,
    timeframe: int = 15,
    min_proximity: float = 0.15,
    horizon_bars: int = 8,
    min_mfe_pct: float = 0.003,
    output_dir: Path | None = None,
) -> dict:
    """Run the full 3-layer pipeline."""
    if output_dir is None:
        output_dir = data_dir.parent / "reports" / "candidate_pool"
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Load market ---
    print(f"Loading market data from {data_dir}...")
    t0 = time.time()
    market = load_market(data_dir, timeframe)
    print(f"  Loaded {len(market)} symbols in {time.time()-t0:.1f}s")

    if not market:
        print("ERROR: No market data found.")
        return {"error": "no_data"}

    timeline = _common_timeline(market)
    index = _build_index(market)
    print(f"  Timeline: {len(timeline)} bars ({timeline[0]} → {timeline[-1]})")

    # Trim to requested window
    if days is not None:
        start_ts = timeline[-1] - days * 24 * 60 * 60 * 1000
        timeline = [ts for ts in timeline if ts >= start_ts]
        print(f"  Trimmed to {days} days: {len(timeline)} bars")

    # --- L1: Scan candidates ---
    print(f"\nL1: Scanning candidates (min_proximity={min_proximity})...")
    t0 = time.time()
    candidates = scan_all_symbols(market, timeline, index, min_proximity)
    print(f"  Found {len(candidates)} candidates in {time.time()-t0:.1f}s")

    if not candidates:
        print("  No candidates found. Try lowering min_proximity.")
        return {"error": "no_candidates"}

    # Save raw candidates
    raw_path = output_dir / "candidates_raw.jsonl"
    save_candidates(candidates, raw_path)
    print(f"  Saved to {raw_path}")

    # Quick breakdown
    by_pattern: dict[str, int] = {}
    by_direction: dict[str, int] = {"long": 0, "short": 0}
    by_regime: dict[str, int] = {}
    by_symbol: dict[str, int] = {}
    for c in candidates:
        by_pattern[c.pattern_type] = by_pattern.get(c.pattern_type, 0) + 1
        by_direction["long" if c.direction == 1 else "short"] += 1
        by_regime[c.regime] = by_regime.get(c.regime, 0) + 1
        by_symbol[c.symbol] = by_symbol.get(c.symbol, 0) + 1

    print(f"  By pattern: {by_pattern}")
    print(f"  By direction: {by_direction}")
    print(f"  By regime: {by_regime}")
    print(f"  Top 10 symbols: {sorted(by_symbol.items(), key=lambda x: -x[1])[:10]}")

    # --- L2: MFE/MAE Labels ---
    print(f"\nL2: Labeling with MFE/MAE (horizon={horizon_bars}, min_mfe={min_mfe_pct})...")
    t0 = time.time()
    labeled = label_candidates(candidates, market, index, horizon_bars, min_mfe_pct)
    print(f"  Labeled {len(labeled)} candidates in {time.time()-t0:.1f}s")

    # Save labeled candidates
    labeled_path = output_dir / "candidates_labeled.jsonl"
    save_candidates(labeled, labeled_path)
    print(f"  Saved to {labeled_path}")

    # Build summary
    total = len(labeled)
    profitable = sum(1 for c in labeled if c.label == 1)
    by_pattern_stats: dict[str, dict] = {}
    for c in labeled:
        key = f"{c.pattern_type}_{('long' if c.direction == 1 else 'short')}"
        if key not in by_pattern_stats:
            by_pattern_stats[key] = {"total": 0, "profitable": 0, "avg_mfe": 0.0, "avg_mae": 0.0}
        by_pattern_stats[key]["total"] += 1
        if c.label == 1:
            by_pattern_stats[key]["profitable"] += 1
        by_pattern_stats[key]["avg_mfe"] += c.mfe_pct
        by_pattern_stats[key]["avg_mae"] += c.mae_pct

    for key, stats in by_pattern_stats.items():
        n = stats["total"]
        if n > 0:
            stats["avg_mfe"] = round(stats["avg_mfe"] / n, 6)
            stats["avg_mae"] = round(stats["avg_mae"] / n, 6)
            stats["win_rate"] = round(stats["profitable"] / n, 4)

    summary = {
        "total_candidates": total,
        "profitable": profitable,
        "win_rate": round(profitable / total, 4) if total > 0 else 0.0,
        "horizon_bars": horizon_bars,
        "min_mfe_pct": min_mfe_pct,
        "by_pattern": by_pattern_stats,
    }
    print_label_report(summary)

    # --- L3: Train filter ---
    print("L3: Training candidate filter...")
    filt = CandidateFilter(
        rule_config=RuleFilterConfig(),
        ml_config=MLFilterConfig(n_estimators=80, learning_rate=0.08),
        use_rules=True,
        use_ml=True,
    )

    # Split: first 70% train, last 30% test
    split_idx = int(len(labeled) * 0.7)
    test_set = labeled[split_idx:]
    test_start_ts = test_set[0].ts if test_set else None

    # Do not let a training candidate borrow labels from the test period.
    # The forward horizon must finish before the first test timestamp.
    train_set = []
    for candidate in labeled[:split_idx]:
        bar_idx = index.get(candidate.symbol, {}).get(candidate.ts)
        bars = market.get(candidate.symbol, [])
        if bar_idx is None or test_start_ts is None:
            continue
        end_idx = bar_idx + horizon_bars
        if end_idx < len(bars) and bars[end_idx].ts < test_start_ts:
            train_set.append(candidate)

    print(f"  Train: {len(train_set)}, Test: {len(test_set)}")

    # Train ML
    ml_stats = filt.train_ml(train_set)
    print(f"  ML training: {ml_stats}")

    # Evaluate on test set
    if test_set:
        tp = fp = tn = fn = 0
        for c in test_set:
            passed, reason, prob = filt.should_trade(c)
            if passed and c.label == 1:
                tp += 1
            elif passed and c.label == 0:
                fp += 1
            elif not passed and c.label == 0:
                tn += 1
            elif not passed and c.label == 1:
                fn += 1

        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = 2 * precision * recall / max(precision + recall, 1e-10)
        accuracy = (tp + tn) / max(tp + tn + fp + fn, 1)

        eval_stats = {
            "test_samples": len(test_set),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(accuracy, 4),
        }
        print(f"\n  Test set evaluation:")
        print(f"    TP={tp} FP={fp} TN={tn} FN={fn}")
        print(f"    Precision={precision:.2%} Recall={recall:.2%} F1={f1:.2%}")
        print(f"    Accuracy={accuracy:.2%}")
    else:
        eval_stats = {"error": "no_test_data"}

    # Compare: filtered vs unfiltered candidate counts
    filtered_candidates = filt.filter_candidates(labeled)
    print(f"\n  Filter results:")
    print(f"    Before filter: {len(labeled)} candidates")
    print(f"    After filter:  {len(filtered_candidates)} candidates")
    print(f"    Retention rate: {len(filtered_candidates)/max(len(labeled),1):.1%}")

    # --- Save full report ---
    report = {
        "pipeline": "candidate_pool_v1",
        "data_dir": str(data_dir),
        "days": days,
        "timeframe": timeframe,
        "min_proximity": min_proximity,
        "horizon_bars": horizon_bars,
        "min_mfe_pct": min_mfe_pct,
        "l1": {
            "total_candidates": len(candidates),
            "by_pattern": by_pattern,
            "by_direction": by_direction,
            "by_regime": by_regime,
        },
        "l2": summary,
        "l3": {
            "ml_training": ml_stats,
            "evaluation": eval_stats,
            "filter_retention": round(len(filtered_candidates) / max(len(labeled), 1), 4),
        },
    }

    report_path = output_dir / "pipeline_report.json"
    with report_path.open("w") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"\nFull report saved to {report_path}")

    return report


def main():
    parser = argparse.ArgumentParser(description="Candidate Pool Pipeline")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--timeframe", type=int, default=15)
    parser.add_argument("--min-proximity", type=float, default=0.15)
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--min-mfe", type=float, default=0.003)
    args = parser.parse_args()

    run_pipeline(
        data_dir=args.data_dir,
        days=args.days,
        timeframe=args.timeframe,
        min_proximity=args.min_proximity,
        horizon_bars=args.horizon,
        min_mfe_pct=args.min_mfe,
    )


if __name__ == "__main__":
    main()

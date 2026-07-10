"""L2 — MFE/MAE Labeler.

For each candidate from the pool, simulate "what if we entered here" and compute:
  - MFE (Max Favorable Excursion): best price move in our direction
  - MAE (Max Adverse Excursion): worst price move against us
  - forward_pnl_pct: PnL at a fixed horizon (e.g., 8 bars = 2 hours on 15m)
  - label: 1 = profitable (MFE > threshold), 0 = not

Key insight:
  - MFE不够 → 形态本身没价值，淘汰
  - MFE够但最终亏 → 不是信号问题，是退出/止损问题
"""
from __future__ import annotations

import json
from pathlib import Path

from candidate_pool import Candidate, save_candidates
from market import FeatureBar


def label_candidates(
    candidates: list[Candidate],
    market: dict[str, list[FeatureBar]],
    index: dict[str, dict[int, int]],
    horizon_bars: int = 8,
    min_mfe_pct: float = 0.003,
) -> list[Candidate]:
    """Label candidates with forward MFE/MAE.

    Args:
        candidates: unlabeled candidates from candidate_pool
        market: symbol → FeatureBar list
        index: symbol → {ts: idx} mapping
        horizon_bars: how many bars to look forward (default 8 = 2h on 15m)
        min_mfe_pct: minimum MFE to label as "profitable" (default 0.3%)
    """
    labeled: list[Candidate] = []
    for c in candidates:
        bars = market.get(c.symbol)
        if bars is None:
            continue
        sym_index = index.get(c.symbol)
        if sym_index is None:
            continue
        bar_idx = sym_index.get(c.ts)
        if bar_idx is None:
            continue

        entry_price = c.close
        if entry_price <= 0:
            continue

        mfe = 0.0  # max favorable
        mae = 0.0  # max adverse
        forward_pnl = 0.0

        end_idx = min(bar_idx + horizon_bars, len(bars) - 1)
        for fwd_idx in range(bar_idx + 1, end_idx + 1):
            fwd_bar = bars[fwd_idx]
            if c.direction == 1:  # long
                favorable = (fwd_bar.high - entry_price) / entry_price
                adverse = (entry_price - fwd_bar.low) / entry_price
                if fwd_idx == end_idx:
                    forward_pnl = (fwd_bar.close - entry_price) / entry_price
            else:  # short
                favorable = (entry_price - fwd_bar.low) / entry_price
                adverse = (fwd_bar.high - entry_price) / entry_price
                if fwd_idx == end_idx:
                    forward_pnl = (entry_price - fwd_bar.close) / entry_price

            mfe = max(mfe, favorable)
            mae = max(mae, adverse)

        # Label: profitable if MFE exceeds threshold
        label = 1 if mfe >= min_mfe_pct else 0

        # Create labeled copy
        labeled_c = Candidate(
            symbol=c.symbol,
            ts=c.ts,
            time=c.time,
            direction=c.direction,
            regime=c.regime,
            pattern_type=c.pattern_type,
            proximity_score=c.proximity_score,
            close=c.close,
            open_=c.open_,
            high=c.high,
            low=c.low,
            ema20=c.ema20,
            ema50=c.ema50,
            ema200=c.ema200,
            atr=c.atr,
            atr_pct=c.atr_pct,
            rsi=c.rsi,
            bb_upper=c.bb_upper,
            bb_lower=c.bb_lower,
            bb_mid=c.bb_mid,
            donchian_high=c.donchian_high,
            donchian_low=c.donchian_low,
            trend_strength=c.trend_strength,
            vol_ratio=c.vol_ratio,
            candle_body_pct=c.candle_body_pct,
            candle_range_pct=c.candle_range_pct,
            move_1d=c.move_1d,
            funding_rate=c.funding_rate,
            open_interest_change_pct=c.open_interest_change_pct,
            trade_flow_imbalance=c.trade_flow_imbalance,
            depth_imbalance=c.depth_imbalance,
            mfe_pct=round(mfe, 6),
            mae_pct=round(mae, 6),
            forward_pnl_pct=round(forward_pnl, 6),
            label=label,
            label_horizon_bars=horizon_bars,
        )
        labeled.append(labeled_c)

    return labeled


def label_and_save(
    candidates: list[Candidate],
    market: dict[str, list[FeatureBar]],
    index: dict[str, dict[int, int]],
    output_path: Path,
    horizon_bars: int = 8,
    min_mfe_pct: float = 0.003,
) -> dict:
    """Label candidates, save to file, and return summary stats."""
    labeled = label_candidates(candidates, market, index, horizon_bars, min_mfe_pct)
    save_candidates(labeled, output_path)

    total = len(labeled)
    profitable = sum(1 for c in labeled if c.label == 1)
    by_pattern: dict[str, dict] = {}
    for c in labeled:
        key = f"{c.pattern_type}_{('long' if c.direction == 1 else 'short')}"
        if key not in by_pattern:
            by_pattern[key] = {"total": 0, "profitable": 0, "avg_mfe": 0.0, "avg_mae": 0.0}
        by_pattern[key]["total"] += 1
        if c.label == 1:
            by_pattern[key]["profitable"] += 1
        by_pattern[key]["avg_mfe"] += c.mfe_pct
        by_pattern[key]["avg_mae"] += c.mae_pct

    # Compute averages
    for key, stats in by_pattern.items():
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
        "by_pattern": by_pattern,
    }
    return summary


def print_label_report(summary: dict) -> None:
    """Print a human-readable label report."""
    print(f"\n{'='*70}")
    print(f"MFE/MAE Label Report (horizon={summary['horizon_bars']} bars, min_mfe={summary['min_mfe_pct']})")
    print(f"{'='*70}")
    print(f"Total candidates: {summary['total_candidates']}")
    print(f"Profitable (MFE >= {summary['min_mfe_pct']}): {summary['profitable']} ({summary['win_rate']:.1%})")
    print(f"\n{'Pattern':<30} {'Total':>6} {'Profit':>7} {'Win%':>6} {'Avg MFE':>9} {'Avg MAE':>9}")
    print("-" * 70)
    for key in sorted(summary["by_pattern"]):
        s = summary["by_pattern"][key]
        print(f"{key:<30} {s['total']:>6} {s['profitable']:>7} {s.get('win_rate', 0):>6.1%} {s['avg_mfe']:>9.4%} {s['avg_mae']:>9.4%}")
    print()

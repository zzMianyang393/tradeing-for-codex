from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from config import BacktestConfig
from market import FeatureBar, load_market


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * q)))
    return ordered[idx]


def move(bars: list[FeatureBar], idx: int, lookback: int) -> float:
    start = bars[max(0, idx - lookback)]
    return bars[idx].close / start.close - 1.0 if start.close else 0.0


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    days = sys.argv[2] if len(sys.argv) > 2 else "365"
    cfg = BacktestConfig()
    market = load_market(Path("../Quantify/data"), cfg.timeframe_minutes)
    rows: dict[str, list[dict[str, float]]] = defaultdict(list)
    for trade in report["windows"][days]["trades_detail"]:
        if trade["reason"] != "range_revert_long":
            continue
        bars = market[trade["symbol"]]
        time_index = {bar.time: idx for idx, bar in enumerate(bars)}
        idx = time_index.get(trade["entry_time"])
        if idx is None:
            continue
        bar = bars[idx]
        rows["win" if trade["win"] else "loss"].append(
            {
                "pnl": trade["pnl"],
                "move_3d": move(bars, idx, 96 * 3),
                "move_7d": move(bars, idx, 96 * 7),
                "move_14d": move(bars, idx, 96 * 14),
                "move_21d": move(bars, idx, 96 * 21),
                "move_45d": move(bars, idx, 96 * 45),
                "trend_strength": bar.trend_strength,
                "ema20_ema200": bar.ema20 / bar.ema200 - 1.0 if bar.ema200 else 0.0,
                "close_ema200": bar.close / bar.ema200 - 1.0 if bar.ema200 else 0.0,
                "atr_pct": bar.atr_pct,
                "rsi": bar.rsi,
            }
        )
    for name, values in sorted(rows.items()):
        print(f"\n{name} count={len(values)} pnl={sum(row['pnl'] for row in values):.4f}")
        for key in (
            "move_3d",
            "move_7d",
            "move_14d",
            "move_21d",
            "move_45d",
            "trend_strength",
            "ema20_ema200",
            "close_ema200",
            "atr_pct",
            "rsi",
        ):
            sample = [row[key] for row in values]
            print(f"  {key:14s} p25={pct(sample, 0.25): .5f} p50={pct(sample, 0.50): .5f} p75={pct(sample, 0.75): .5f}")


if __name__ == "__main__":
    main()

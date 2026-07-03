from __future__ import annotations

import json
import sys
from pathlib import Path

from config import BacktestConfig
from market import load_market


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    days = sys.argv[2]
    cfg = BacktestConfig()
    market = load_market(Path("../Quantify/data"), cfg.timeframe_minutes)
    rows = []
    for trade in report["windows"][days]["trades_detail"]:
        bars = market[trade["symbol"]]
        idx_by_time = {bar.time: idx for idx, bar in enumerate(bars)}
        entry_idx = idx_by_time.get(trade["entry_time"])
        exit_idx = idx_by_time.get(trade["exit_time"])
        if entry_idx is None or exit_idx is None or exit_idx <= entry_idx:
            continue
        entry = trade["entry"]
        direction = 1 if trade["direction"] == "long" else -1
        path = bars[entry_idx + 1 : exit_idx + 1]
        first4 = bars[entry_idx + 1 : min(exit_idx + 1, entry_idx + 5)]
        if direction > 0:
            mfe = max((bar.high / entry - 1.0) for bar in path)
            mae = min((bar.low / entry - 1.0) for bar in path)
            first4_best = max((bar.high / entry - 1.0) for bar in first4) if first4 else 0.0
            first4_worst = min((bar.low / entry - 1.0) for bar in first4) if first4 else 0.0
        else:
            mfe = max((entry / bar.low - 1.0) for bar in path)
            mae = min((entry / bar.high - 1.0) for bar in path)
            first4_best = max((entry / bar.low - 1.0) for bar in first4) if first4 else 0.0
            first4_worst = min((entry / bar.high - 1.0) for bar in first4) if first4 else 0.0
        rows.append(
            {
                "trade": trade,
                "mfe": mfe,
                "mae": mae,
                "first4_best": first4_best,
                "first4_worst": first4_worst,
                "bars_held": exit_idx - entry_idx,
            }
        )

    losses = [row for row in rows if not row["trade"]["win"]]
    wins = [row for row in rows if row["trade"]["win"]]
    immediate_bad = [row for row in losses if row["first4_best"] < 0.002 and row["first4_worst"] < -0.004]
    never_worked = [row for row in losses if row["mfe"] < 0.003]
    gave_chance = [row for row in losses if row["mfe"] >= 0.006]
    print(f"{days}d trades={len(rows)} wins={len(wins)} losses={len(losses)}")
    print(f"loss pnl={sum(row['trade']['pnl'] for row in losses):.4f}")
    print(
        f"immediate_bad={len(immediate_bad)} pnl={sum(row['trade']['pnl'] for row in immediate_bad):.4f} "
        f"never_worked={len(never_worked)} pnl={sum(row['trade']['pnl'] for row in never_worked):.4f} "
        f"gave_chance={len(gave_chance)} pnl={sum(row['trade']['pnl'] for row in gave_chance):.4f}"
    )
    print("worst loss paths")
    for row in sorted(losses, key=lambda item: item["trade"]["pnl"])[:12]:
        trade = row["trade"]
        print(
            f"  {trade['entry_time']} {trade['symbol']:15s} {trade['direction']:5s} "
            f"{trade['reason']:24s} {trade['exit_reason']:14s} pnl={trade['pnl']:8.4f} "
            f"mfe={row['mfe']*100:6.2f}% mae={row['mae']*100:7.2f}% "
            f"first4_best={row['first4_best']*100:6.2f}% first4_worst={row['first4_worst']*100:7.2f}% "
            f"bars={row['bars_held']}"
        )


if __name__ == "__main__":
    main()

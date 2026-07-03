from __future__ import annotations

import json
import sys
from pathlib import Path


def summarize(result: dict) -> None:
    trades = result["trades_detail"]
    wins = [trade for trade in trades if trade["win"]]
    losses = [trade for trade in trades if not trade["win"]]
    win_pnl = sum(trade["pnl"] for trade in wins)
    loss_pnl = sum(trade["pnl"] for trade in losses)
    avg_win = win_pnl / len(wins) if wins else 0.0
    avg_loss = loss_pnl / len(losses) if losses else 0.0
    print(
        f"{result['days']}d return={result['return_pct']:.4f}% "
        f"pnl={result['pnl']:.4f} trades={len(trades)} win={result['win_rate']:.2%}"
    )
    print(f"  wins={len(wins)} win_pnl={win_pnl:.4f} avg_win={avg_win:.4f}")
    print(f"  losses={len(losses)} loss_pnl={loss_pnl:.4f} avg_loss={avg_loss:.4f}")
    print(f"  payoff_ratio={abs(avg_win / avg_loss):.4f}" if avg_loss else "  payoff_ratio=inf")
    print("  worst losses")
    for trade in sorted(losses, key=lambda item: item["pnl"])[:8]:
        print(
            f"    {trade['exit_time']} {trade['symbol']:15s} {trade['direction']:5s} "
            f"{trade['reason']:24s} {trade['exit_reason']:14s} "
            f"pnl={trade['pnl']:8.4f} pct={trade['pnl_pct_equity']:7.2f}"
        )
    print("  best wins")
    for trade in sorted(wins, key=lambda item: item["pnl"], reverse=True)[:8]:
        print(
            f"    {trade['exit_time']} {trade['symbol']:15s} {trade['direction']:5s} "
            f"{trade['reason']:24s} {trade['exit_reason']:14s} "
            f"pnl={trade['pnl']:8.4f} pct={trade['pnl_pct_equity']:7.2f}"
        )


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for days in sys.argv[2:]:
        summarize(report["windows"][days])


if __name__ == "__main__":
    main()

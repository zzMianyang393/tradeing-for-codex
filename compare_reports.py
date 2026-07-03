from __future__ import annotations

import json
import sys
from pathlib import Path


def trade_key(trade: dict) -> tuple:
    return (
        trade["symbol"],
        trade["direction"],
        trade["entry_time"],
        trade["exit_time"],
        trade["reason"],
    )


def main() -> None:
    old = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    new = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    days = sys.argv[3]
    old_trades = {trade_key(trade): trade for trade in old["windows"][days]["trades_detail"]}
    new_trades = {trade_key(trade): trade for trade in new["windows"][days]["trades_detail"]}
    added = [trade for key, trade in new_trades.items() if key not in old_trades]
    removed = [trade for key, trade in old_trades.items() if key not in new_trades]
    print(f"{days}d old={old['windows'][days]['return_pct']} new={new['windows'][days]['return_pct']}")
    print(f"added count={len(added)} pnl={sum(trade['pnl'] for trade in added):.4f}")
    print(f"removed count={len(removed)} pnl={sum(trade['pnl'] for trade in removed):.4f}")
    print("added worst")
    for trade in sorted(added, key=lambda item: item["pnl"])[:20]:
        print(
            f"  {trade['entry_time']} -> {trade['exit_time']} {trade['symbol']:15s} "
            f"{trade['direction']:5s} {trade['reason']:24s} {trade['exit_reason']:14s} "
            f"pnl={trade['pnl']:8.4f} pct={trade['pnl_pct_equity']:7.2f}"
        )
    print("added best")
    for trade in sorted(added, key=lambda item: item["pnl"], reverse=True)[:12]:
        print(
            f"  {trade['entry_time']} -> {trade['exit_time']} {trade['symbol']:15s} "
            f"{trade['direction']:5s} {trade['reason']:24s} {trade['exit_reason']:14s} "
            f"pnl={trade['pnl']:8.4f} pct={trade['pnl_pct_equity']:7.2f}"
        )


if __name__ == "__main__":
    main()

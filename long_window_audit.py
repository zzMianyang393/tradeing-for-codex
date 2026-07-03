from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    days = sys.argv[2] if len(sys.argv) > 2 else "365"
    trades = report["windows"][days]["trades_detail"]
    by_entry_month: dict[str, dict[str, float]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    by_reason_month: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"pnl": 0.0, "trades": 0, "wins": 0}
    )
    by_direction_month: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"pnl": 0.0, "trades": 0, "wins": 0}
    )
    for trade in trades:
        month = trade["entry_time"][:7]
        for bucket, key in (
            (by_entry_month, month),
            (by_reason_month, (month, trade["reason"])),
            (by_direction_month, (month, trade["direction"])),
        ):
            item = bucket[key]
            item["pnl"] += trade["pnl"]
            item["trades"] += 1
            item["wins"] += 1 if trade["win"] else 0

    print(f"{days}d monthly")
    for month, item in sorted(by_entry_month.items()):
        win_rate = item["wins"] / item["trades"] if item["trades"] else 0.0
        print(f"  {month} pnl={item['pnl']:8.4f} win={win_rate:.2%} trades={int(item['trades'])}")

    print("\nworst reason-month")
    for (month, reason), item in sorted(by_reason_month.items(), key=lambda kv: kv[1]["pnl"])[:20]:
        win_rate = item["wins"] / item["trades"] if item["trades"] else 0.0
        print(f"  {month} {reason:24s} pnl={item['pnl']:8.4f} win={win_rate:.2%} trades={int(item['trades'])}")

    print("\ndirection-month")
    for (month, direction), item in sorted(by_direction_month.items(), key=lambda kv: kv[1]["pnl"])[:20]:
        win_rate = item["wins"] / item["trades"] if item["trades"] else 0.0
        print(f"  {month} {direction:5s} pnl={item['pnl']:8.4f} win={win_rate:.2%} trades={int(item['trades'])}")

    print("\nworst trades")
    for trade in sorted(trades, key=lambda item: item["pnl"])[:25]:
        print(
            f"  {trade['entry_time']} -> {trade['exit_time']} {trade['symbol']:15s} "
            f"{trade['direction']:5s} {trade['reason']:24s} {trade['exit_reason']:14s} "
            f"pnl={trade['pnl']:8.4f} pct={trade['pnl_pct_equity']:7.2f}"
        )


if __name__ == "__main__":
    main()

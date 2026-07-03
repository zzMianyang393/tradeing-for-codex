from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def summarize_trades(trades: list[dict], label: str) -> None:
    by_month: dict[str, float] = defaultdict(float)
    by_exit: dict[str, dict[str, float]] = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    by_reason_exit: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"pnl": 0.0, "trades": 0, "wins": 0}
    )
    for trade in trades:
        by_month[trade["exit_time"][:7]] += trade["pnl"]
        exit_bucket = by_exit[trade["exit_reason"]]
        exit_bucket["pnl"] += trade["pnl"]
        exit_bucket["trades"] += 1
        exit_bucket["wins"] += 1 if trade["win"] else 0
        reason_exit = by_reason_exit[(trade["reason"], trade["exit_reason"])]
        reason_exit["pnl"] += trade["pnl"]
        reason_exit["trades"] += 1
        reason_exit["wins"] += 1 if trade["win"] else 0

    print(f"\n{label}")
    print("monthly pnl")
    for key, pnl in sorted(by_month.items()):
        print(f"  {key}: {pnl:.4f}")

    print("exit reasons")
    for key, item in sorted(by_exit.items(), key=lambda kv: kv[1]["pnl"]):
        win_rate = item["wins"] / item["trades"] if item["trades"] else 0.0
        print(f"  {key:14s} pnl={item['pnl']:8.4f} win={win_rate:.2%} trades={int(item['trades'])}")

    print("reason x exit")
    for (reason, exit_reason), item in sorted(by_reason_exit.items(), key=lambda kv: kv[1]["pnl"])[:12]:
        win_rate = item["wins"] / item["trades"] if item["trades"] else 0.0
        print(
            f"  {reason:24s} {exit_reason:14s} pnl={item['pnl']:8.4f} "
            f"win={win_rate:.2%} trades={int(item['trades'])}"
        )

    print("worst trades")
    for trade in sorted(trades, key=lambda item: item["pnl"])[:12]:
        print(
            f"  {trade['exit_time']} {trade['symbol']:15s} {trade['direction']:5s} "
            f"{trade['reason']:24s} {trade['exit_reason']:14s} pnl={trade['pnl']:8.4f} "
            f"pct={trade['pnl_pct_equity']:7.2f}"
        )


def main() -> None:
    report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for days in ("60", "90"):
        result = report["windows"][days]
        summarize_trades(result["trades_detail"], f"{days}d")


if __name__ == "__main__":
    main()

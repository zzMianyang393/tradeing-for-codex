from __future__ import annotations

import json
import sys
from pathlib import Path


def summarize(path: Path) -> None:
    report = json.loads(path.read_text(encoding="utf-8"))
    for days, result in report.get("windows", {}).items():
        if not result.get("available"):
            continue
        print(f"\n{days}d pnl={result['pnl']} win={result['win_rate']:.2%} trades={result['trades']}")
        print("  by_regime:")
        for name, item in sorted(result.get("by_regime", {}).items(), key=lambda kv: kv[1]["pnl"]):
            print(
                f"    {name:10s} pnl={item['pnl']:8.4f} win={item['win_rate']:.2%} trades={int(item['trades'])}"
            )
        print("  by_reason:")
        for name, item in sorted(result.get("by_reason", {}).items(), key=lambda kv: kv[1]["pnl"]):
            print(
                f"    {name:24s} pnl={item['pnl']:8.4f} win={item['win_rate']:.2%} trades={int(item['trades'])}"
            )
        print("  worst symbols:")
        for name, item in sorted(result.get("by_symbol", {}).items(), key=lambda kv: kv[1]["pnl"])[:8]:
            print(
                f"    {name:15s} pnl={item['pnl']:8.4f} win={item['win_rate']:.2%} trades={int(item['trades'])}"
            )


if __name__ == "__main__":
    summarize(Path(sys.argv[1]))

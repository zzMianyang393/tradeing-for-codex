"""Audit a single candidate-pool backtest report by month and subtype."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def _bucket() -> dict:
    return {"trades": 0, "wins": 0, "pnl": 0.0}


def _add(bucket: dict, trade: dict) -> None:
    bucket["trades"] += 1
    bucket["wins"] += int(bool(trade.get("win")))
    bucket["pnl"] += float(trade.get("pnl", 0.0) or 0.0)


def _finalize(groups: dict[str, dict]) -> dict[str, dict]:
    result = {}
    for key, value in sorted(groups.items()):
        trades = value["trades"]
        result[key] = {
            "trades": trades,
            "wins": value["wins"],
            "win_rate": round(value["wins"] / trades, 4) if trades else 0.0,
            "pnl": round(value["pnl"], 4),
        }
    return result


def audit(path: Path, output: Path | None = None) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    groups = {name: defaultdict(_bucket) for name in ("month", "reason", "symbol", "regime", "exit_reason")}
    for trade in report.get("trades_detail", []):
        entry_time = str(trade.get("entry_time", ""))
        keys = {
            "month": entry_time[:7] or "unknown",
            "reason": trade.get("reason", "unknown"),
            "symbol": trade.get("symbol", "unknown"),
            "regime": trade.get("regime", "unknown"),
            "exit_reason": trade.get("exit_reason", "unknown"),
        }
        for name, key in keys.items():
            _add(groups[name][key], trade)

    result = {
        "source": str(path),
        "summary": {
            "start_equity": report.get("start_equity"),
            "end_equity": report.get("end_equity"),
            "return_pct": report.get("return_pct"),
            "max_drawdown_pct": report.get("max_drawdown_pct"),
            "trades": report.get("trades"),
        },
        "by_month": _finalize(groups["month"]),
        "by_reason": _finalize(groups["reason"]),
        "by_symbol": _finalize(groups["symbol"]),
        "by_regime": _finalize(groups["regime"]),
        "by_exit_reason": _finalize(groups["exit_reason"]),
        "risk_status": report.get("risk_status", {}),
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    for name in ("by_month", "by_reason", "by_symbol", "by_regime", "by_exit_reason"):
        print(f"\n{name}")
        for key, value in result[name].items():
            print(
                f"  {key:28s} trades={value['trades']:>3} "
                f"win={value['win_rate']:.1%} pnl={value['pnl']:>8.4f}"
            )
    if output:
        print(f"\nAudit: {output}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a CP backtest report")
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    audit(args.report, args.output)


if __name__ == "__main__":
    main()

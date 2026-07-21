"""Read-only concentration and leave-one-symbol-out audit for the frozen candidate."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any


def month_of(event: dict[str, Any]) -> str:
    return datetime.fromtimestamp(event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")


def attribution(events: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[float]] = defaultdict(list)
    for event in events:
        value = month_of(event) if key == "month" else str(event[key])
        groups[value].append(float(event["net_return_pct"]))
    return {name: {"events": len(values), "net_sum_pct": round(sum(values), 6), "mean_pct": round(mean(values), 6)} for name, values in sorted(groups.items())}


def positive_contribution(groups: dict[str, dict[str, Any]]) -> dict[str, Any]:
    positives = {name: row["net_sum_pct"] for name, row in groups.items() if row["net_sum_pct"] > 0}
    total = sum(positives.values())
    leader = max(positives, key=positives.get) if positives else None
    return {"positive_net_sum_pct": round(total, 6), "leader": leader,
            "leader_positive_contribution": round(positives[leader] / total, 6) if leader and total else 0.0}


def leave_one_symbol_out(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    symbols = sorted({event["symbol"] for event in events})
    result: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        values = [float(event["net_return_pct"]) for event in events if event["symbol"] != symbol]
        result[symbol] = {"remaining_events": len(values), "remaining_net_sum_pct": round(sum(values), 6),
                          "remaining_mean_pct": round(mean(values), 6) if values else 0.0}
    return result


def split_audit(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_symbol, by_direction, by_month = attribution(events, "symbol"), attribution(events, "direction"), attribution(events, "month")
    return {"events": len(events), "net_sum_pct": round(sum(float(event["net_return_pct"]) for event in events), 6),
            "mean_pct": round(mean(float(event["net_return_pct"]) for event in events), 6) if events else 0.0,
            "by_symbol": by_symbol, "by_direction": by_direction, "by_month": by_month,
            "symbol_positive_concentration": positive_contribution(by_symbol),
            "direction_positive_concentration": positive_contribution(by_direction),
            "month_positive_concentration": positive_contribution(by_month),
            "leave_one_symbol_out": leave_one_symbol_out(events)}


def build(source: Path) -> dict[str, Any]:
    report = json.loads(source.read_text(encoding="utf-8"))
    compatible = [event for event in report["events"] if event.get("regime_compatible") is True]
    return {"report_type": "daily_volatility_expansion_stability_audit", "source_rule_id": report["rule_id"],
            "source_status": report["status"], "observation_only": True,
            "formation": split_audit([event for event in compatible if event["split"] == "formation"]),
            "oos": split_audit([event for event in compatible if event["split"] == "oos"]),
            "interpretation": "descriptive_only_not_a_new_gate_or_parameter_selection",
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("reports/daily_volatility_expansion_continuation_audit.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/daily_volatility_expansion_stability_audit.json"))
    args = parser.parse_args()
    report = build(args.source)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['events']}; oos={report['oos']['events']}; source_status={report['source_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

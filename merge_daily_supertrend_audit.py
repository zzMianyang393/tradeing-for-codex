"""Merge deterministic SuperTrend audit batches without changing their events."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


def summary(events: list[dict]) -> dict:
    returns = [event["net_return_pct"] for event in events]
    positive_by_month: dict[str, float] = defaultdict(float)
    for event in events:
        if event["net_return_pct"] > 0:
            month = datetime.fromtimestamp(event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")
            positive_by_month[month] += event["net_return_pct"]
    positive_total = sum(positive_by_month.values())
    concentration = max(positive_by_month.values()) / positive_total if positive_total else 0.0
    return {
        "events": len(returns),
        "net_sum_pct": round(sum(returns), 6),
        "mean_pct": round(mean(returns), 6) if returns else 0,
        "win_rate": round(sum(value > 0 for value in returns) / len(returns), 6) if returns else 0,
        "positive_return_month_concentration": round(concentration, 6),
    }


def verdict(formation: dict, oos: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    insufficient = False
    for split, stats in (("formation", formation), ("oos", oos)):
        if stats["events"] < 15:
            reasons.append(f"{split} events {stats['events']} < 15")
            insufficient = True
        if stats["mean_pct"] <= 0:
            reasons.append(f"{split} mean <= 0")
        if stats["positive_return_month_concentration"] > 0.25:
            reasons.append(f"{split} month concentration {stats['positive_return_month_concentration']:.1%} > 25%")
    if insufficient:
        return "insufficient_evidence", reasons
    return ("historical_rejected" if reasons else "historical_research_candidate"), reasons


def main() -> None:
    batches = [Path("reports") / f"supertrend_batch_{index}.json" for index in range(1, 5)]
    events = [event for path in batches for event in json.loads(path.read_text(encoding="utf-8"))["events"]]
    formation = summary([event for event in events if event["split"] == "formation"])
    oos = summary([event for event in events if event["split"] == "oos"])
    status, reasons = verdict(formation, oos)
    report = {
        "report_type": "daily_supertrend_audit",
        "source_batches": [str(path) for path in batches],
        "formation": formation,
        "oos": oos,
        "events": events,
        "status": status,
        "reasons": reasons,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False},
    }
    Path("reports/daily_supertrend_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={formation['events']}; oos={oos['events']}; status={status}")


if __name__ == "__main__":
    main()

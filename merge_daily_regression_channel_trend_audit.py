"""Publish the full-universe regression-channel result from its saved audit batches."""
from __future__ import annotations

import json
from pathlib import Path

from merge_daily_supertrend_audit import summary, verdict


def main() -> None:
    batches = [Path("reports") / f"regression_batch_{index}.json" for index in range(1, 5)]
    events = [event for path in batches for event in json.loads(path.read_text(encoding="utf-8"))["events"]]
    formation = summary([event for event in events if event["split"] == "formation"])
    oos = summary([event for event in events if event["split"] == "oos"])
    status, reasons = verdict(formation, oos)
    report = {
        "report_type": "daily_regression_channel_trend_audit",
        "source_batches": [str(path) for path in batches],
        "formation": formation,
        "oos": oos,
        "events": events,
        "status": status,
        "reasons": reasons,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False},
    }
    Path("reports/daily_regression_channel_trend_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={formation['events']}; oos={oos['events']}; status={status}")


if __name__ == "__main__":
    main()

"""Merge immutable volatility-expansion audit batches into the full-universe report."""
from __future__ import annotations

import json
from pathlib import Path

from daily_volatility_expansion_continuation_audit import RULE_ID, summarize, verdict


def main() -> None:
    batches = [Path("reports") / f"volatility_expansion_batch_{index}.json" for index in range(1, 5)]
    events = [event for path in batches for event in json.loads(path.read_text(encoding="utf-8"))["events"]]
    events.sort(key=lambda event: (event["signal_ts"], event["symbol"], event["direction"]))
    compatible = [event for event in events if event["regime_compatible"]]
    all_stats = {name: summarize([event for event in events if event["split"] == name]) for name in ("formation", "oos")}
    compatible_stats = {name: summarize([event for event in compatible if event["split"] == name]) for name in ("formation", "oos")}
    status, reasons = verdict(compatible_stats["formation"], compatible_stats["oos"])
    report = {
        "report_type": "daily_volatility_expansion_continuation_audit", "rule_id": RULE_ID,
        "source_batches": [str(path) for path in batches],
        "formation": {"all_signals": all_stats["formation"], "regime_compatible": compatible_stats["formation"]},
        "oos": {"all_signals": all_stats["oos"], "regime_compatible": compatible_stats["oos"]},
        "events": events, "status": status, "reasons": reasons,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }
    Path("reports/daily_volatility_expansion_continuation_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={compatible_stats['formation']['events']}; oos={compatible_stats['oos']['events']}; status={status}")


if __name__ == "__main__":
    main()

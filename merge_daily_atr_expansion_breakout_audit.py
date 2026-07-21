"""Merge bounded ATR expansion breakout audit batches without altering signals."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from daily_atr_expansion_breakout_audit import RULE_ID, summary, verdict


def merge(batch_paths: list[Path]) -> dict[str, Any]:
    batches = [json.loads(path.read_text(encoding="utf-8")) for path in batch_paths]
    if not batches:
        raise ValueError("at least one batch is required")
    parameters = batches[0]["parameters"]
    if any(batch.get("rule_id") != RULE_ID or batch.get("parameters") != parameters for batch in batches):
        raise ValueError("batch rule or parameter mismatch")
    events = [event for batch in batches for event in batch["events"]]
    events.sort(key=lambda event: (event["signal_ts"], event["symbol"], event["direction"]))
    formation = summary([event for event in events if event["split"] == "formation"])
    oos = summary([event for event in events if event["split"] == "oos"])
    status, reasons = verdict(formation, oos)
    return {"report_type": "daily_atr_expansion_breakout_audit", "rule_id": RULE_ID, "parameters": parameters,
            "formation": formation, "oos": oos, "events": events, "status": status, "reasons": reasons,
            "batch_sources": [str(path) for path in batch_paths],
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batches", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_atr_expansion_breakout_audit.json"))
    args = parser.parse_args()
    report: dict[str, Any] = merge(args.batches)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['events']}; oos={report['oos']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

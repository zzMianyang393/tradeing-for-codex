"""Resolve structural prototype priorities into the current research queue."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PREFLIGHT_PATH = Path("reports/strategy_prototype_batch_preflight.json")
OUTPUT_PATH = Path("reports/priority_research_queue_audit.json")
DOC_PATH = Path("docs/priority_research_queue_audit_2026-07-15.md")

# Each entry is anchored to the frozen closeout, rather than inferring a new status.
CLOSED_PRIORITIES = {
    "TF_06": ("historical_rejected", "daily_kama_trend_audit.json"),
    "TF_08": ("historical_rejected", "daily_supertrend_audit.json"),
    "TF_09": ("historical_rejected", "daily_regression_channel_trend_audit.json"),
    "MR_02": ("legacy_limited_scope_evidence", "daily_bb_mean_revert_audit.json"),
    "MR_03": ("insufficient_evidence", "daily_rsi_percentile_range_reversion_audit.json"),
    "MR_06": ("insufficient_evidence", "daily_bias_range_reversion_audit.json"),
    "MR_07": ("insufficient_evidence", "daily_zscore_range_reversion_audit.json"),
    "MR_09": ("requires_specification", None),
    "MR_14": ("historical_rejected", "btc_trend_confirmed_alt_momentum_audit.json"),
    "VS_05": ("observation_only", "daily_volatility_expansion_continuation_audit.json"),
    "VS_06": ("insufficient_evidence", "parkinson_volatility_extreme_reversion_audit.json"),
    "TS_02": ("insufficient_evidence", "weekend_low_liquidity_reversion_audit.json"),
    "TS_07": ("insufficient_evidence", "month_boundary_flow_audit.json"),
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(preflight: dict[str, Any] | None = None) -> dict[str, Any]:
    preflight = preflight or load_json(PREFLIGHT_PATH)
    priorities = preflight.get("research_card_priority", [])
    priority_ids = [item["prototype_id"] for item in priorities]
    unknown = sorted(set(priority_ids) - set(CLOSED_PRIORITIES))
    missing = sorted(set(CLOSED_PRIORITIES) - set(priority_ids))
    if unknown or missing:
        raise ValueError(f"Priority closeout mapping drift: unknown={unknown}, missing={missing}")

    items = []
    for priority in priorities:
        prototype_id = priority["prototype_id"]
        status, source_report = CLOSED_PRIORITIES[prototype_id]
        items.append({
            "prototype_id": prototype_id,
            "name_cn": priority["name_cn"],
            "queue_status": status,
            "source_report": source_report,
            "requires_new_backtest": False,
            "observation_only": True,
        })
    counts: dict[str, int] = {}
    for item in items:
        counts[item["queue_status"]] = counts.get(item["queue_status"], 0) + 1
    return {
        "report_type": "priority_research_queue_audit",
        "source_priority_count": len(priorities),
        "closed_count": len(items),
        "open_research_count": 0,
        "queue_decision": "historical_priority_queue_closed_preserve_prospective_cohorts",
        "status_counts": counts,
        "items": items,
        "observation_only": True,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Priority Research Queue Audit",
        "",
        f"- Structural priorities: {report['source_priority_count']}",
        f"- Closed: {report['closed_count']}",
        f"- Open historical research: {report['open_research_count']}",
        f"- Decision: `{report['queue_decision']}`",
        "",
        "| Prototype | Queue status | Evidence |",
        "| --- | --- | --- |",
    ]
    for item in report["items"]:
        lines.append(f"| {item['prototype_id']} {item['name_cn']} | {item['queue_status']} | {item['source_report'] or 'frozen rule not sufficiently specified'} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    report = build_report()
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    DOC_PATH.write_text(markdown(report), encoding="utf-8")
    print(f"closed={report['closed_count']}; open={report['open_research_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

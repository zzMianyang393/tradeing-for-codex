"""Exposure and entry-cohort concentration audit for downtrend rebounds.

Raw event-return sums count each symbol independently. This read-only audit
normalizes events sharing an entry timestamp into equal-weight cohorts and
reports overlapping-position counts. It is not an equity-curve backtest.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from downtrend_rebound_event_time_filter_audit import HYPOTHESES, load_json, select_hypotheses


def max_concurrent_positions(events: list[dict[str, Any]]) -> int:
    points: list[tuple[int, int]] = []
    for event in events:
        entry_ts = int(event.get("entry_ts") or 0)
        exit_ts = int(event.get("exit_ts") or 0)
        if entry_ts and exit_ts > entry_ts:
            points.append((entry_ts, 1))
            points.append((exit_ts, -1))
    active = maximum = 0
    for _ts, delta in sorted(points, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def entry_cohorts(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        entry_ts = int(event.get("entry_ts") or 0)
        if entry_ts:
            grouped[entry_ts].append(event)
    cohorts: list[dict[str, Any]] = []
    for entry_ts, items in sorted(grouped.items()):
        returns = [float(item.get("net_return_pct", 0.0)) for item in items]
        cohorts.append(
            {
                "entry_ts": entry_ts,
                "entry_timestamp_utc": str(items[0].get("entry_timestamp_utc") or ""),
                "split": str(items[0].get("split") or ""),
                "symbols": sorted(str(item.get("symbol") or "") for item in items),
                "events": len(items),
                "equal_weight_net_return_pct": round(mean(returns), 6),
            }
        )
    return cohorts


def summarize_cohorts(cohorts: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(item["equal_weight_net_return_pct"]) for item in cohorts]
    positives = [value for value in values if value > 0]
    negatives = [value for value in values if value <= 0]
    gross_profit = sum(positives)
    gross_loss = abs(sum(negatives))
    positive_by_month: dict[str, float] = defaultdict(float)
    for item in cohorts:
        value = float(item["equal_weight_net_return_pct"])
        if value > 0:
            positive_by_month[str(item["entry_timestamp_utc"])[:7]] += value
    total_positive = sum(positive_by_month.values())
    top_month = max(positive_by_month.values()) if positive_by_month else 0.0
    return {
        "cohorts": len(cohorts),
        "cohort_net_sum_pct": round(sum(values), 6),
        "cohort_mean_pct": round(mean(values), 6) if values else 0.0,
        "cohort_median_pct": round(median(values), 6) if values else 0.0,
        "cohort_win_rate": round(len(positives) / len(values), 6) if values else 0.0,
        "cohort_profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else (999.0 if gross_profit else 0.0),
        "top_positive_month_share": round(top_month / total_positive, 6) if total_positive else 0.0,
        "max_events_same_entry": max((int(item["events"]) for item in cohorts), default=0),
    }


def split_review(events: list[dict[str, Any]]) -> dict[str, Any]:
    reviews: dict[str, Any] = {}
    for split in ("formation", "oos", "all"):
        split_events = events if split == "all" else [event for event in events if event.get("split") == split]
        cohorts = entry_cohorts(split_events)
        raw_sum = sum(float(event.get("net_return_pct", 0.0)) for event in split_events)
        summary = summarize_cohorts(cohorts)
        reviews[split] = {
            "events": len(split_events),
            "unique_symbols": len({str(event.get("symbol") or "") for event in split_events}),
            "raw_event_net_sum_pct": round(raw_sum, 6),
            "max_concurrent_positions": max_concurrent_positions(split_events),
            **summary,
            "raw_to_cohort_sum_ratio": round(raw_sum / summary["cohort_net_sum_pct"], 6)
            if summary["cohort_net_sum_pct"]
            else 0.0,
        }
    return reviews


def build_report(event_time_report: dict[str, Any]) -> dict[str, Any]:
    events = list(event_time_report.get("events", []))
    hypotheses = select_hypotheses(events)
    reviews = {name: split_review(items) for name, items in hypotheses.items()}
    return {
        "report_type": "downtrend_rebound_exposure_concentration_audit",
        "report_date": "2026-07-13",
        "research_id": "downtrend_rebound_exposure_concentration_v1",
        "scope": "read_only_cohort_normalization_not_equity_curve",
        "normalization_rule": "equal weight among symbols sharing the same entry timestamp",
        "hypothesis_reviews": reviews,
        "limitations": [
            "Cohort normalization removes same-entry duplication but does not mark positions to market daily.",
            "Overlapping cohorts still require a future capital-constrained portfolio simulator.",
            "Raw event sums and cohort sums are diagnostics, not account returns.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Downtrend Rebound Exposure Concentration Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Raw event-return sums count every symbol separately. This audit equal-weights all symbols entering at the same timestamp, then reports the remaining overlap.",
        "",
        "## OOS Cohort Results",
        "",
        "| Hypothesis | Events | Entry Cohorts | Raw Sum | Cohort Sum | Cohort Mean | Cohort Win | Max Same Entry | Max Concurrent |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name in HYPOTHESES:
        item = report["hypothesis_reviews"][name]["oos"]
        lines.append(
            f"| `{name}` | {item['events']} | {item['cohorts']} | {item['raw_event_net_sum_pct']:+.6f}% | "
            f"{item['cohort_net_sum_pct']:+.6f}% | {item['cohort_mean_pct']:+.6f}% | "
            f"{item['cohort_win_rate']:.2%} | {item['max_events_same_entry']} | {item['max_concurrent_positions']} |"
        )
    baseline = report["hypothesis_reviews"]["H0_downtrend_rsi_baseline"]
    lines.extend(
        [
            "",
            "## Baseline Interpretation",
            "",
            f"- formation: {baseline['formation']['events']} events become {baseline['formation']['cohorts']} entry cohorts; raw sum {baseline['formation']['raw_event_net_sum_pct']:+.6f}% becomes cohort sum {baseline['formation']['cohort_net_sum_pct']:+.6f}%.",
            f"- OOS: {baseline['oos']['events']} events become {baseline['oos']['cohorts']} entry cohorts; raw sum {baseline['oos']['raw_event_net_sum_pct']:+.6f}% becomes cohort sum {baseline['oos']['cohort_net_sum_pct']:+.6f}%.",
            f"- OOS maximum simultaneous positions: {baseline['oos']['max_concurrent_positions']}.",
            f"- OOS maximum symbols entering together: {baseline['oos']['max_events_same_entry']}.",
            f"- OOS cohort positive-month concentration: {baseline['oos']['top_positive_month_share']:.2%}.",
            "- The next valid engineering step is a capital-constrained daily portfolio simulator; no raw sum above should be read as account return.",
            "",
            "## Safety",
            "",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit exposure concentration in downtrend rebound events.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("reports/downtrend_rebound_event_time_filter_audit.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/downtrend_rebound_exposure_concentration_audit.json"),
    )
    parser.add_argument(
        "--doc",
        type=Path,
        default=Path("docs/downtrend_rebound_exposure_concentration_audit_2026-07-13.md"),
    )
    args = parser.parse_args(argv)
    source = load_json(args.source)
    if not source:
        print(f"ERROR: Cannot load source report {args.source}")
        return 1
    report = build_report(source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    baseline = report["hypothesis_reviews"]["H0_downtrend_rsi_baseline"]["oos"]
    print(
        f"H0 OOS: events={baseline['events']}, cohorts={baseline['cohorts']}, "
        f"raw={baseline['raw_event_net_sum_pct']:+.6f}%, "
        f"cohort={baseline['cohort_net_sum_pct']:+.6f}%, "
        f"max_concurrent={baseline['max_concurrent_positions']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


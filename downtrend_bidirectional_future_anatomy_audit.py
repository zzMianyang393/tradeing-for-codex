"""Read-only anatomy audit for the locked future validation result."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from downtrend_bidirectional_drawdown_anatomy_audit import (
    daily_equity_changes,
    episode_attribution,
    maximum_drawdown_episode,
)


def monthly_component_pnl(closed_positions: list[dict[str, Any]]) -> dict[str, Any]:
    by_month: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    positive_by_component: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for position in closed_positions:
        month = str(position.get("exit_timestamp_utc") or "")[:7]
        component = str(position.get("component_id") or "unknown")
        pnl = float(position.get("realized_pnl") or 0.0)
        by_month[month][component] += pnl
        if pnl > 0:
            positive_by_component[component][month] += pnl

    components = sorted({component for values in by_month.values() for component in values})
    rows: list[dict[str, Any]] = []
    cancellation_months: list[str] = []
    for month in sorted(by_month):
        component_values = {component: round(by_month[month].get(component, 0.0), 6) for component in components}
        nonzero = [value for value in component_values.values() if value != 0]
        if any(value > 0 for value in nonzero) and any(value < 0 for value in nonzero):
            cancellation_months.append(month)
        rows.append(
            {
                "month": month,
                "component_pnl": component_values,
                "total_pnl": round(sum(component_values.values()), 6),
            }
        )

    concentration: dict[str, float] = {}
    for component in components:
        values = positive_by_component.get(component, {})
        total = sum(values.values())
        concentration[component] = round(max(values.values()) / total, 6) if total else 0.0
    return {
        "rows": rows,
        "cancellation_months": cancellation_months,
        "positive_month_concentration_by_component": concentration,
    }


def build_report(source: dict[str, Any]) -> dict[str, Any]:
    result = source.get("result", {})
    initial = float(result.get("initial_equity") or 100_000.0)
    curve = list(result.get("equity_curve", []))
    episode = maximum_drawdown_episode(curve, initial)
    return {
        "report_type": "downtrend_bidirectional_future_anatomy_audit",
        "report_date": "2026-07-13",
        "research_id": "downtrend_bidirectional_future_anatomy_v1",
        "scope": "read_only_attribution_no_new_rule_tested",
        "source_research_id": source.get("research_id"),
        "source_validation_status": source.get("validation_status"),
        "future_total_return_pct": float(result.get("total_return_pct", 0.0)),
        "maximum_drawdown_episode": episode,
        "episode_attribution": episode_attribution(result, episode),
        "monthly_component_pnl": monthly_component_pnl(list(result.get("closed_positions", []))),
        "worst_daily_equity_changes": sorted(
            daily_equity_changes(curve, initial), key=lambda item: item["equity_change_pct"]
        )[:5],
        "rejection_reason_counts": dict(
            Counter(str(item.get("rejection_reason") or "unknown") for item in result.get("rejected_events", []))
        ),
        "methodology_notes": [
            "This audit explains the locked future result and does not test a replacement rule.",
            "Monthly attribution uses realized PnL grouped by exit month.",
            "Daily marks cannot observe intraday drawdown between completed daily closes.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    episode = report["maximum_drawdown_episode"]
    attribution = report["episode_attribution"]
    monthly = report["monthly_component_pnl"]
    components = sorted(monthly["positive_month_concentration_by_component"])
    lines = [
        "# Downtrend Bidirectional Future Anatomy",
        "",
        "Date: 2026-07-13",
        "",
        "## Maximum Drawdown",
        "",
        f"- peak: {episode['peak_date']}, equity {episode['peak_equity']:.6f}",
        f"- trough: {episode['trough_date']}, equity {episode['trough_equity']:.6f}",
        f"- drawdown: {episode['drawdown_pct']:.6f}% over {episode['duration_days']} days",
        f"- average long / short exposure: {attribution['average_long_exposure']:.2%} / {attribution['average_short_exposure']:.2%}",
        f"- net-long / neutral / net-short days: {attribution['net_long_days']} / {attribution['approximately_neutral_days']} / {attribution['net_short_days']}",
        "",
        "## Monthly Realized PnL",
        "",
        "| Month | " + " | ".join(components) + " | Total |",
        "| --- | " + " | ".join("---:" for _ in components) + " | ---: |",
    ]
    for row in monthly["rows"]:
        values = " | ".join(f"{row['component_pnl'][component]:+.6f}" for component in components)
        lines.append(f"| {row['month']} | {values} | {row['total_pnl']:+.6f} |")
    lines.extend(["", "## Concentration", ""])
    for component, share in monthly["positive_month_concentration_by_component"].items():
        lines.append(f"- `{component}` top positive month share: {share:.2%}")
    cancellation = ", ".join(monthly["cancellation_months"]) or "none"
    lines.extend(
        [
            f"- opposite-sign component months: {cancellation}",
            "",
            "## Safety",
            "",
            "- no replacement rule or parameter was tested",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explain the locked future validation result.")
    parser.add_argument("--source", type=Path, default=Path("reports/downtrend_bidirectional_future_validation.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/downtrend_bidirectional_future_anatomy_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/downtrend_bidirectional_future_anatomy_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    source = json.loads(args.source.read_text(encoding="utf-8"))
    report = build_report(source)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    episode = report["maximum_drawdown_episode"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(f"drawdown={episode['drawdown_pct']:.6f}% from {episode['peak_date']} to {episode['trough_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


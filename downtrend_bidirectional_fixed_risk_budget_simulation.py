"""Post-hoc fixed component risk budget for the downtrend bidirectional combo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from downtrend_bidirectional_combo_simulation import (
    EMA_COMPONENT,
    RSI_COMPONENT,
    diagnostic_reasons,
    formation_without_november,
    tag_components,
)
from downtrend_rebound_capital_constrained_simulator import load_price_maps, simulate_portfolio
from downtrend_rebound_event_time_filter_audit import load_json
from two_regime_shared_capital_combo_simulation import component_attribution


COMPONENT_CAPS = {RSI_COMPONENT: 2, EMA_COMPONENT: 3}


def run_split(events: list[dict[str, Any]], price_maps: dict[str, Any]) -> dict[str, Any]:
    result = simulate_portfolio(
        events,
        price_maps,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
        component_position_caps=COMPONENT_CAPS,
    )
    result["component_attribution"] = component_attribution(result, (RSI_COMPONENT, EMA_COMPONENT))
    return result


def baseline_delta(overlay: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float]:
    return {
        "return_delta_pct": round(float(overlay["total_return_pct"]) - float(baseline.get("total_return_pct", 0.0)), 6),
        "max_drawdown_delta_pct": round(float(overlay["max_drawdown_pct"]) - float(baseline.get("max_drawdown_pct", 0.0)), 6),
        "accepted_position_delta": int(overlay["accepted_positions"]) - int(baseline.get("accepted_positions", 0)),
        "average_exposure_delta": round(float(overlay["average_gross_exposure"]) - float(baseline.get("average_gross_exposure", 0.0)), 6),
    }


def build_report(
    rsi_source: dict[str, Any],
    ema_source: dict[str, Any],
    baseline_report: dict[str, Any],
    data_dir: Path,
) -> dict[str, Any]:
    events = tag_components(rsi_source, ema_source)
    price_maps = load_price_maps(data_dir, events)
    formation = run_split([event for event in events if event.get("split") == "formation"], price_maps)
    formation_ex_november = run_split(formation_without_november(events), price_maps)
    oos = run_split([event for event in events if event.get("split") == "oos"], price_maps)
    reasons = diagnostic_reasons(formation, formation_ex_november, oos)
    baseline_results = baseline_report.get("results", {})
    return {
        "report_type": "downtrend_bidirectional_fixed_risk_budget_simulation",
        "report_date": "2026-07-13",
        "research_id": "downtrend_bidirectional_fixed_risk_budget_v1",
        "scope": "posthoc_read_only_risk_overlay_diagnostic_requires_future_validation",
        "component_position_caps": COMPONENT_CAPS,
        "results": {
            "formation": formation,
            "formation_excluding_2024_11": formation_ex_november,
            "oos": oos,
        },
        "baseline_deltas": {
            key: baseline_delta(result, baseline_results.get(key, {}))
            for key, result in (
                ("formation", formation),
                ("formation_excluding_2024_11", formation_ex_november),
                ("oos", oos),
            )
        },
        "diagnostic_reasons": reasons,
        "passes_current_diagnostic_screen": not reasons,
        "validated": False,
        "validation_status": "posthoc_overlay_requires_future_unseen_window",
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Downtrend Bidirectional Fixed Risk Budget",
        "",
        "Date: 2026-07-13",
        "",
        "Post-hoc diagnostic overlay: maximum two RSI long positions and three EMA short positions. Unused slots remain cash.",
        "",
        "## Results",
        "",
        "| Window | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Month Concentration | Return Delta | DD Delta |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ("formation", "formation_excluding_2024_11", "oos"):
        item = report["results"][key]
        delta = report["baseline_deltas"][key]
        lines.append(
            f"| `{key}` | {item['accepted_positions']} | {item['capacity_rejected_events']} | "
            f"{item['total_return_pct']:+.6f}% | {item['max_drawdown_pct']:.6f}% | "
            f"{item['realized_win_rate']:.2%} | {item['average_gross_exposure']:.2%} | "
            f"{item['top_positive_month_share']:.2%} | "
            f"{delta['return_delta_pct']:+.6f}% | {delta['max_drawdown_delta_pct']:+.6f}% |"
        )
    lines.extend(["", "## OOS Component Attribution", "", "| Component | Accepted | Rejected | Return Contribution | Win |", "| --- | ---: | ---: | ---: | ---: |"])
    for component, item in report["results"]["oos"]["component_attribution"].items():
        lines.append(
            f"| `{component}` | {item['accepted_positions']} | {item['rejected_events']} | "
            f"{item['return_contribution_pct']:+.6f}% | {item['realized_win_rate']:.2%} |"
        )
    lines.extend(["", "## Decision", ""])
    if report["diagnostic_reasons"]:
        lines.extend(f"- {reason}" for reason in report["diagnostic_reasons"])
    else:
        lines.append("- Current diagnostic thresholds pass, but this overlay is not validated because it was designed after observing OOS drawdown.")
    lines.extend(
        [
            "",
            f"Validation status: `{report['validation_status']}`.",
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
    parser = argparse.ArgumentParser(description="Test the fixed 2-long / 3-short research risk budget.")
    parser.add_argument("--rsi-source", type=Path, default=Path("reports/downtrend_rebound_event_time_filter_audit.json"))
    parser.add_argument("--ema-source", type=Path, default=Path("reports/ema_crossover_4h_regime_conditioned_audit.json"))
    parser.add_argument("--baseline", type=Path, default=Path("reports/downtrend_bidirectional_combo_simulation.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/downtrend_bidirectional_fixed_risk_budget_simulation.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/downtrend_bidirectional_fixed_risk_budget_simulation_2026-07-13.md"))
    args = parser.parse_args(argv)
    rsi_source = load_json(args.rsi_source)
    ema_source = load_json(args.ema_source)
    baseline = load_json(args.baseline)
    if not rsi_source or not ema_source or not baseline:
        print("ERROR: Cannot load one or more source reports")
        return 1
    report = build_report(rsi_source, ema_source, baseline, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    for key in ("formation", "formation_excluding_2024_11", "oos"):
        item = report["results"][key]
        print(
            f"{key}: accepted={item['accepted_positions']}, return={item['total_return_pct']:+.6f}%, "
            f"max_dd={item['max_drawdown_pct']:.6f}%, win={item['realized_win_rate']:.2%}"
        )
    print(f"diagnostic_pass={report['passes_current_diagnostic_screen']}; validated={report['validated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

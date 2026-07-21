"""Capital-constrained simulation for Donchian long events in uptrends.

This module filters frozen regime-annotated events and reuses the validated
cash-constrained daily mark-to-market simulator. It is research-only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from downtrend_rebound_capital_constrained_simulator import (
    load_price_maps,
    simulate_portfolio,
    simulation_screen,
)
from downtrend_rebound_event_time_filter_audit import load_json


REGIME = "趋势上行"
HYPOTHESIS = "T0_donchian_long_uptrend"


def compatible_long_events(source: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event
        for event in source.get("events", [])
        if event.get("direction") == "long"
        and event.get("entry_regime") == REGIME
        and event.get("declared_compatible_regime") is True
    ]


def formation_without_november(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("split") == "formation"
        and str(event.get("signal_timestamp_utc") or "")[:7] != "2024-11"
    ]


def build_report(source: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    events = compatible_long_events(source)
    price_maps = load_price_maps(data_dir, events)
    formation = simulate_portfolio(
        [event for event in events if event.get("split") == "formation"],
        price_maps,
        priority_mode="symbol",
    )
    oos = simulate_portfolio(
        [event for event in events if event.get("split") == "oos"],
        price_maps,
        priority_mode="symbol",
    )
    formation_ex_november = simulate_portfolio(
        formation_without_november(events),
        price_maps,
        priority_mode="symbol",
    )
    oos_reasons = simulation_screen(oos)
    if float(formation_ex_november["total_return_pct"]) <= 0:
        oos_reasons.append("formation excluding 2024-11 return <= 0")
    return {
        "report_type": "donchian_uptrend_capital_constrained_simulation",
        "report_date": "2026-07-13",
        "research_id": "donchian_uptrend_capital_constrained_v1",
        "scope": "read_only_daily_mark_to_market_portfolio_diagnostic",
        "regime": REGIME,
        "hypothesis": HYPOTHESIS,
        "source_event_count": len(source.get("events", [])),
        "compatible_long_event_count": len(events),
        "results": {
            "formation": formation,
            "formation_excluding_2024_11": formation_ex_november,
            "oos": oos,
        },
        "oos_screen_reasons": oos_reasons,
        "passes_diagnostic_screen": not oos_reasons,
        "portfolio_rules": {
            "initial_capital": 100_000.0,
            "max_positions": 5,
            "position_fraction": 0.20,
            "entry_cost_rate": 0.0008,
            "exit_cost_rate": 0.0008,
            "leverage": 1.0,
            "same_entry_priority": "symbol ascending",
            "rebalance": False,
        },
        "limitations": [
            "Daily close marking cannot observe intraday drawdown between completed daily marks.",
            "Symbol ordering is deterministic capacity handling, not an alpha ranking rule.",
            "This component must share capital with other regime components before portfolio admission.",
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
        "# Donchian Uptrend Capital-Constrained Simulation",
        "",
        "Date: 2026-07-13",
        "",
        "Frozen Donchian long events are included only when the completed-4h entry label is `趋势上行`.",
        "",
        "## Results",
        "",
        "| Window | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Positive-Month Concentration |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ("formation", "formation_excluding_2024_11", "oos"):
        item = report["results"][key]
        lines.append(
            f"| `{key}` | {item['candidate_events']} | {item['accepted_positions']} | "
            f"{item['capacity_rejected_events']} | {item['total_return_pct']:+.6f}% | "
            f"{item['max_drawdown_pct']:.6f}% | {item['realized_win_rate']:.2%} | "
            f"{item['average_gross_exposure']:.2%} | {item['peak_gross_exposure']:.2%} | "
            f"{item['top_positive_month_share']:.2%} |"
        )
    lines.extend(["", "## Decision", ""])
    if report["oos_screen_reasons"]:
        lines.extend(f"- {reason}" for reason in report["oos_screen_reasons"])
    else:
        lines.append("- Current diagnostic gate passes; shared-capital multi-regime research is the only allowed next step.")
    lines.extend(
        [
            "",
            f"Diagnostic status: `{'pass' if report['passes_diagnostic_screen'] else 'blocked'}`.",
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
    parser = argparse.ArgumentParser(description="Simulate capital-constrained Donchian longs in uptrends.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("reports/donchian_atr_trend_baseline_regime_conditioned_audit.json"),
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports/donchian_uptrend_capital_constrained_simulation.json"),
    )
    parser.add_argument(
        "--doc",
        type=Path,
        default=Path("docs/donchian_uptrend_capital_constrained_simulation_2026-07-13.md"),
    )
    args = parser.parse_args(argv)
    source = load_json(args.source)
    if not source:
        print(f"ERROR: Cannot load source report {args.source}")
        return 1
    report = build_report(source, args.data)
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
    print(f"passes={report['passes_diagnostic_screen']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

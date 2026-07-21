"""Shared-capital combo of downtrend RSI longs and EMA continuation shorts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from downtrend_rebound_capital_constrained_simulator import load_price_maps, simulate_portfolio
from downtrend_rebound_event_time_filter_audit import load_json, select_hypotheses
from ema_short_downtrend_capital_constrained_simulation import compatible_short_events
from two_regime_shared_capital_combo_simulation import component_attribution


RSI_COMPONENT = "rsi_rebound_long"
EMA_COMPONENT = "ema_continuation_short"


def tag_components(rsi_source: dict[str, Any], ema_source: dict[str, Any]) -> list[dict[str, Any]]:
    rsi_events = select_hypotheses(list(rsi_source.get("events", [])))["H0_downtrend_rsi_baseline"]
    tagged_rsi = [
        {
            **event,
            "direction": "long",
            "component_id": RSI_COMPONENT,
            "portfolio_priority": float(event.get("signal_rsi") or 100.0),
        }
        for event in rsi_events
    ]
    tagged_ema = [
        {
            **event,
            "component_id": EMA_COMPONENT,
            "portfolio_priority": 100.0,
        }
        for event in compatible_short_events(ema_source)
    ]
    return tagged_rsi + tagged_ema


def formation_without_november(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("split") == "formation"
        and str(event.get("signal_timestamp_utc") or "")[:7] != "2024-11"
    ]


def run_split(events: list[dict[str, Any]], price_maps: dict[str, Any]) -> dict[str, Any]:
    result = simulate_portfolio(
        events,
        price_maps,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
    )
    result["component_attribution"] = component_attribution(result, (RSI_COMPONENT, EMA_COMPONENT))
    return result


def diagnostic_reasons(
    formation: dict[str, Any],
    formation_ex_november: dict[str, Any],
    oos: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if float(formation["total_return_pct"]) <= 0:
        reasons.append("formation total return <= 0")
    if float(formation_ex_november["total_return_pct"]) <= 0:
        reasons.append("formation excluding 2024-11 return <= 0")
    if float(oos["total_return_pct"]) <= 0:
        reasons.append("OOS total return <= 0")
    if float(oos["max_drawdown_pct"]) > 20.0:
        reasons.append(f"OOS maximum drawdown {oos['max_drawdown_pct']:.2f}% > 20%")
    if int(oos["accepted_positions"]) < 30:
        reasons.append(f"OOS accepted positions {oos['accepted_positions']} < 30")
    attribution = oos["component_attribution"]
    for component in (RSI_COMPONENT, EMA_COMPONENT):
        accepted = int(attribution.get(component, {}).get("accepted_positions", 0))
        if accepted < 10:
            reasons.append(f"{component} accepted positions {accepted} < 10")
    if float(oos["top_positive_month_share"]) > 0.25:
        reasons.append(f"OOS positive-month concentration {oos['top_positive_month_share']:.2%} > 25%")
    return reasons


def build_report(rsi_source: dict[str, Any], ema_source: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    events = tag_components(rsi_source, ema_source)
    price_maps = load_price_maps(data_dir, events)
    formation = run_split([event for event in events if event.get("split") == "formation"], price_maps)
    formation_ex_november = run_split(formation_without_november(events), price_maps)
    oos = run_split([event for event in events if event.get("split") == "oos"], price_maps)
    reasons = diagnostic_reasons(formation, formation_ex_november, oos)
    return {
        "report_type": "downtrend_bidirectional_combo_simulation",
        "report_date": "2026-07-13",
        "research_id": "downtrend_bidirectional_combo_v1",
        "scope": "read_only_shared_capital_long_short_daily_mark_to_market_diagnostic",
        "components": [RSI_COMPONENT, EMA_COMPONENT],
        "component_candidate_counts": dict(Counter(str(event["component_id"]) for event in events)),
        "results": {
            "formation": formation,
            "formation_excluding_2024_11": formation_ex_november,
            "oos": oos,
        },
        "diagnostic_reasons": reasons,
        "passes_diagnostic_screen": not reasons,
        "portfolio_rules": {
            "initial_capital": 100_000.0,
            "max_positions": 5,
            "position_fraction": 0.20,
            "one_position_per_symbol": True,
            "component_capital_reservation": False,
            "leverage": 1.0,
            "rebalance": False,
        },
        "limitations": [
            "Both component interpretations were identified after conditional inspection.",
            "Daily marks do not capture intraday drawdown between completed daily closes.",
            "A future unseen validation window is mandatory regardless of this diagnostic.",
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
        "# Downtrend Bidirectional Shared-Capital Combo",
        "",
        "Date: 2026-07-13",
        "",
        "RSI rebound longs and EMA continuation shorts share one account inside completed-4h downtrend regimes.",
        "",
        "## Portfolio Results",
        "",
        "| Window | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Month Concentration |",
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
    lines.extend(["", "## OOS Component Attribution", "", "| Component | Accepted | Rejected | PnL | Return Contribution | Win |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for component, item in report["results"]["oos"]["component_attribution"].items():
        lines.append(
            f"| `{component}` | {item['accepted_positions']} | {item['rejected_events']} | "
            f"{item['realized_pnl']:+.6f} | {item['return_contribution_pct']:+.6f}% | {item['realized_win_rate']:.2%} |"
        )
    lines.extend(["", "## Decision", ""])
    if report["diagnostic_reasons"]:
        lines.extend(f"- {reason}" for reason in report["diagnostic_reasons"])
    else:
        lines.append("- Current diagnostics pass, but future-window validation remains mandatory.")
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
    parser = argparse.ArgumentParser(description="Simulate bidirectional weak components inside downtrends.")
    parser.add_argument("--rsi-source", type=Path, default=Path("reports/downtrend_rebound_event_time_filter_audit.json"))
    parser.add_argument("--ema-source", type=Path, default=Path("reports/ema_crossover_4h_regime_conditioned_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/downtrend_bidirectional_combo_simulation.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/downtrend_bidirectional_combo_simulation_2026-07-13.md"))
    args = parser.parse_args(argv)
    rsi_source = load_json(args.rsi_source)
    ema_source = load_json(args.ema_source)
    if not rsi_source or not ema_source:
        print("ERROR: Cannot load one or more component reports")
        return 1
    report = build_report(rsi_source, ema_source, args.data)
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

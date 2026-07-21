"""Shared-capital diagnostic for uptrend Donchian and downtrend RSI events."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from donchian_uptrend_capital_constrained_simulation import compatible_long_events
from downtrend_rebound_capital_constrained_simulator import (
    load_price_maps,
    simulate_portfolio,
    simulation_screen,
)
from downtrend_rebound_event_time_filter_audit import load_json, select_hypotheses


DONCHIAN_COMPONENT = "donchian_long_uptrend"
RSI_COMPONENT = "rsi_rebound_downtrend"


def tag_components(rsi_source: dict[str, Any], donchian_source: dict[str, Any]) -> list[dict[str, Any]]:
    rsi_events = select_hypotheses(list(rsi_source.get("events", [])))["H0_downtrend_rsi_baseline"]
    tagged_rsi = [
        {
            **event,
            "component_id": RSI_COMPONENT,
            "portfolio_priority": float(event.get("signal_rsi") or 100.0),
        }
        for event in rsi_events
    ]
    tagged_donchian = [
        {
            **event,
            "component_id": DONCHIAN_COMPONENT,
            "portfolio_priority": 100.0,
        }
        for event in compatible_long_events(donchian_source)
    ]
    return tagged_rsi + tagged_donchian


def excluding_formation_november(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("split") == "formation"
        and str(event.get("signal_timestamp_utc") or "")[:7] != "2024-11"
    ]


def component_attribution(
    result: dict[str, Any],
    required_components: tuple[str, ...] = (DONCHIAN_COMPONENT, RSI_COMPONENT),
) -> dict[str, Any]:
    accepted: Counter[str] = Counter()
    rejected: Counter[str] = Counter()
    pnl: dict[str, float] = defaultdict(float)
    wins: Counter[str] = Counter()
    for position in result.get("closed_positions", []):
        component = str(position.get("component_id") or "unknown")
        realized = float(position.get("realized_pnl") or 0.0)
        accepted[component] += 1
        pnl[component] += realized
        if realized > 0:
            wins[component] += 1
    for event in result.get("rejected_events", []):
        rejected[str(event.get("component_id") or "unknown")] += 1
    components = sorted(set(accepted) | set(rejected) | set(required_components))
    initial = float(result.get("initial_equity") or 1.0)
    return {
        component: {
            "accepted_positions": accepted[component],
            "rejected_events": rejected[component],
            "realized_pnl": round(pnl[component], 6),
            "return_contribution_pct": round(pnl[component] / initial * 100.0, 6),
            "realized_win_rate": round(wins[component] / accepted[component], 6) if accepted[component] else 0.0,
        }
        for component in components
    }


def combo_screen(oos: dict[str, Any], formation_ex_november: dict[str, Any]) -> list[str]:
    reasons = simulation_screen(oos)
    attribution = component_attribution(oos)
    if int(oos["accepted_positions"]) < 30 and not any("accepted positions" in reason for reason in reasons):
        reasons.append(f"accepted positions {oos['accepted_positions']} < 30")
    for component in (DONCHIAN_COMPONENT, RSI_COMPONENT):
        accepted = int(attribution[component]["accepted_positions"])
        if accepted < 10:
            reasons.append(f"{component} accepted positions {accepted} < 10")
    if float(formation_ex_november["total_return_pct"]) <= 0:
        reasons.append("formation excluding 2024-11 return <= 0")
    return reasons


def run_split(events: list[dict[str, Any]], price_maps: dict[str, Any]) -> dict[str, Any]:
    result = simulate_portfolio(
        events,
        price_maps,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
    )
    result["component_attribution"] = component_attribution(result)
    return result


def build_report(rsi_source: dict[str, Any], donchian_source: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    events = tag_components(rsi_source, donchian_source)
    price_maps = load_price_maps(data_dir, events)
    formation = run_split([event for event in events if event.get("split") == "formation"], price_maps)
    oos = run_split([event for event in events if event.get("split") == "oos"], price_maps)
    formation_ex_november = run_split(excluding_formation_november(events), price_maps)
    reasons = combo_screen(oos, formation_ex_november)
    return {
        "report_type": "two_regime_shared_capital_combo_simulation",
        "report_date": "2026-07-13",
        "research_id": "two_regime_shared_capital_combo_v1",
        "scope": "read_only_shared_capital_daily_mark_to_market_diagnostic",
        "components": [DONCHIAN_COMPONENT, RSI_COMPONENT],
        "component_candidate_counts": dict(Counter(str(event["component_id"]) for event in events)),
        "results": {
            "formation": formation,
            "formation_excluding_2024_11": formation_ex_november,
            "oos": oos,
        },
        "oos_screen_reasons": reasons,
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
            "Both registered components are long-only and do not provide market-neutral protection.",
            "Daily close marking cannot observe intraday drawdown between marks.",
            "The RSI regime interpretation remains post-hoc and requires future-window validation.",
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
        "# Two-Regime Shared-Capital Combo Simulation",
        "",
        "Date: 2026-07-13",
        "",
        "Components share one 100,000 USDT account, five positions, and one-position-per-symbol exposure control.",
        "",
        "## Portfolio Results",
        "",
        "| Window | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Peak Exposure | Month Concentration |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for key in ("formation", "formation_excluding_2024_11", "oos"):
        item = report["results"][key]
        lines.append(
            f"| `{key}` | {item['candidate_events']} | {item['accepted_positions']} | {item['capacity_rejected_events']} | "
            f"{item['total_return_pct']:+.6f}% | {item['max_drawdown_pct']:.6f}% | "
            f"{item['realized_win_rate']:.2%} | {item['average_gross_exposure']:.2%} | "
            f"{item['peak_gross_exposure']:.2%} | {item['top_positive_month_share']:.2%} |"
        )
    lines.extend(["", "## OOS Component Attribution", "", "| Component | Accepted | Rejected | PnL | Return Contribution | Win |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for component, item in report["results"]["oos"]["component_attribution"].items():
        lines.append(
            f"| `{component}` | {item['accepted_positions']} | {item['rejected_events']} | "
            f"{item['realized_pnl']:+.6f} | {item['return_contribution_pct']:+.6f}% | {item['realized_win_rate']:.2%} |"
        )
    lines.extend(["", "## Decision", ""])
    if report["oos_screen_reasons"]:
        lines.extend(f"- {reason}" for reason in report["oos_screen_reasons"])
    else:
        lines.append("- Current diagnostic gate passes; only another pre-registered regime component study may follow.")
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
    parser = argparse.ArgumentParser(description="Simulate a two-regime shared-capital research portfolio.")
    parser.add_argument(
        "--rsi-source",
        type=Path,
        default=Path("reports/downtrend_rebound_event_time_filter_audit.json"),
    )
    parser.add_argument(
        "--donchian-source",
        type=Path,
        default=Path("reports/donchian_atr_trend_baseline_regime_conditioned_audit.json"),
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/two_regime_shared_capital_combo_simulation.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/two_regime_shared_capital_combo_simulation_2026-07-13.md"))
    args = parser.parse_args(argv)
    rsi_source = load_json(args.rsi_source)
    donchian_source = load_json(args.donchian_source)
    if not rsi_source or not donchian_source:
        print("ERROR: Cannot load one or more component reports")
        return 1
    report = build_report(rsi_source, donchian_source, args.data)
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

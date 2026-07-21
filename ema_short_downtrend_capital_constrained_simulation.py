"""Capital-constrained audit of 4h EMA shorts in completed downtrends."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from downtrend_rebound_capital_constrained_simulator import load_price_maps, simulate_portfolio
from downtrend_rebound_event_time_filter_audit import load_json


REGIME = "趋势下行"


def compatible_short_events(source: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event
        for event in source.get("events", [])
        if event.get("direction") == "short"
        and event.get("entry_regime") == REGIME
        and event.get("direction_compatible_regime") is True
    ]


def formation_without_november(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("split") == "formation"
        and str(event.get("signal_timestamp_utc") or "")[:7] != "2024-11"
    ]


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
    if int(oos["accepted_positions"]) < 15:
        reasons.append(f"OOS accepted positions {oos['accepted_positions']} < 15")
    if float(oos["max_drawdown_pct"]) > 20.0:
        reasons.append(f"OOS maximum drawdown {oos['max_drawdown_pct']:.2f}% > 20%")
    if float(oos["top_positive_month_share"]) > 0.25:
        reasons.append(f"OOS positive-month concentration {oos['top_positive_month_share']:.2%} > 25%")
    return reasons


def build_report(source: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    events = compatible_short_events(source)
    price_maps = load_price_maps(data_dir, events)
    formation = simulate_portfolio(
        [event for event in events if event.get("split") == "formation"],
        price_maps,
        priority_mode="symbol",
    )
    formation_ex_november = simulate_portfolio(
        formation_without_november(events),
        price_maps,
        priority_mode="symbol",
    )
    oos = simulate_portfolio(
        [event for event in events if event.get("split") == "oos"],
        price_maps,
        priority_mode="symbol",
    )
    reasons = diagnostic_reasons(formation, formation_ex_november, oos)
    return {
        "report_type": "ema_short_downtrend_capital_constrained_simulation",
        "report_date": "2026-07-13",
        "research_id": "ema_short_downtrend_capital_constrained_v1",
        "scope": "read_only_daily_mark_to_market_short_portfolio_diagnostic",
        "regime": REGIME,
        "source_event_count": len(source.get("events", [])),
        "compatible_short_event_count": len(events),
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
            "direction": "short",
            "leverage": 1.0,
            "one_position_per_symbol": True,
            "same_entry_priority": "symbol ascending",
            "rebalance": False,
        },
        "limitations": [
            "The promising OOS direction was identified post-hoc from the regime inventory.",
            "Daily marks do not observe intraday drawdown between completed daily closes.",
            "A future unseen window remains mandatory regardless of this result.",
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
        "# EMA Short Downtrend Capital-Constrained Simulation",
        "",
        "Date: 2026-07-13",
        "",
        "Only frozen EMA20/EMA50 short events with completed-4h `趋势下行` labels are included.",
        "",
        "## Results",
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
    lines.extend(["", "## Decision", ""])
    if report["diagnostic_reasons"]:
        lines.extend(f"- {reason}" for reason in report["diagnostic_reasons"])
    else:
        lines.append("- Current diagnostics pass, but future-window validation remains mandatory because this direction was discovered post-hoc.")
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
    parser = argparse.ArgumentParser(description="Simulate EMA shorts inside completed downtrend regimes.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("reports/ema_crossover_4h_regime_conditioned_audit.json"),
    )
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/ema_short_downtrend_capital_constrained_simulation.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/ema_short_downtrend_capital_constrained_simulation_2026-07-13.md"))
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


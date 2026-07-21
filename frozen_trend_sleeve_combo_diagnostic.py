"""Frozen shared-capital diagnostic for the trend weak-factor sleeve.

This is an historical, post-hoc diagnostic only. It cannot approve a strategy,
paper trading, or future signal generation.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from downtrend_rebound_capital_constrained_simulator import load_price_maps, simulate_portfolio
from two_regime_shared_capital_combo_simulation import component_attribution


COMPONENTS = (
    "daily_parabolic_sar_trend",
    "donchian_atr_trend_baseline",
    "4h_ema_crossover",
)
SOURCE_PATHS = {
    "daily_parabolic_sar_trend": Path("reports/daily_parabolic_sar_trend_audit.json"),
    "donchian_atr_trend_baseline": Path("reports/donchian_atr_trend_baseline_regime_conditioned_audit.json"),
    "4h_ema_crossover": Path("reports/ema_crossover_4h_regime_conditioned_audit.json"),
}
COMPONENT_PRIORITY = {
    "daily_parabolic_sar_trend": 300.0,
    "donchian_atr_trend_baseline": 200.0,
    "4h_ema_crossover": 100.0,
}
COMPONENT_CAPS = {
    "daily_parabolic_sar_trend": 3,
    "donchian_atr_trend_baseline": 1,
    "4h_ema_crossover": 1,
}


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_compatible(component: str, event: dict[str, Any]) -> bool:
    if component == "daily_parabolic_sar_trend":
        direction, regime = event.get("direction"), event.get("entry_regime")
        return (direction == "long" and regime == "趋势上行") or (direction == "short" and regime == "趋势下行")
    if component == "donchian_atr_trend_baseline":
        return bool(event.get("declared_compatible_regime", False))
    if component == "4h_ema_crossover":
        return bool(event.get("direction_compatible_regime", False))
    return False


def tag_events(sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for component in COMPONENTS:
        for event in sources.get(component, {}).get("events", []):
            if is_compatible(component, event):
                tagged.append({
                    **event,
                    "component_id": component,
                    "portfolio_priority": COMPONENT_PRIORITY[component],
                })
    return sorted(tagged, key=lambda item: (item["entry_ts"], -item["portfolio_priority"], item["symbol"]))


def summarize(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in (
            "candidate_events", "accepted_positions", "capacity_rejected_events",
            "total_return_pct", "max_drawdown_pct", "realized_win_rate",
            "average_gross_exposure", "peak_gross_exposure", "capital_turnover",
            "top_positive_month_share", "component_attribution",
        )
    }


def diagnostic_reasons(result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if result["accepted_positions"] < 20:
        reasons.append(f"accepted positions {result['accepted_positions']} < 20")
    if result["total_return_pct"] <= 0:
        reasons.append(f"OOS total return {result['total_return_pct']:+.6f}% <= 0%")
    if result["max_drawdown_pct"] > 20:
        reasons.append(f"OOS maximum drawdown {result['max_drawdown_pct']:.6f}% > 20%")
    if result["top_positive_month_share"] > 0.25:
        reasons.append(f"OOS top positive month share {result['top_positive_month_share']:.2%} > 25%")
    return reasons


def run(events: list[dict[str, Any]], prices: dict[str, Any]) -> dict[str, Any]:
    result = simulate_portfolio(
        events, prices, initial_capital=100_000.0, max_positions=5, position_fraction=0.10,
        priority_mode="event_score_then_symbol", one_position_per_symbol=True,
        component_position_caps=COMPONENT_CAPS,
    )
    result["component_attribution"] = component_attribution(result, COMPONENTS)
    return result


def build_report(sources: dict[str, dict[str, Any]], data_dir: Path) -> dict[str, Any]:
    events = tag_events(sources)
    # Daily price resampling is the expensive part. The same frozen map is
    # shared across formation and OOS so results do not depend on reload order.
    prices = load_price_maps(data_dir, events)
    formation = run([event for event in events if event.get("split") == "formation"], prices)
    oos = run([event for event in events if event.get("split") == "oos"], prices)
    reasons = diagnostic_reasons(oos)
    return {
        "report_type": "frozen_trend_sleeve_combo_diagnostic",
        "scope": "posthoc_shared_capital_diagnostic_not_a_trading_strategy",
        "components": list(COMPONENTS),
        "component_candidate_counts": dict(Counter(event["component_id"] for event in events)),
        "portfolio_rules": {
            "initial_capital": 100_000.0,
            "max_positions": 5,
            "position_fraction": 0.10,
            "one_position_per_symbol": True,
            "component_position_caps": COMPONENT_CAPS,
            "priority_order": list(COMPONENTS),
            "leverage": 1.0,
            "rebalance": False,
        },
        "results": {"formation": summarize(formation), "oos": summarize(oos)},
        "oos_diagnostic_reasons": reasons,
        "status": "historical_combo_diagnostic_pass" if not reasons else "historical_combo_diagnostic_rejected",
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "methodology_notes": [
            "Component definitions, costs, entry and exit events are reused unchanged from source audits.",
            "The two concentrated components are capped at one simultaneous position each.",
            "This trend sleeve does not claim range-regime coverage.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Frozen Trend Sleeve Combo Diagnostic", "",
        "Historical shared-capital diagnostic only. This is not an approval.", "",
        "| Split | Candidates | Accepted | Return | Max DD | Win | Month Concentration |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for split in ("formation", "oos"):
        item = report["results"][split]
        lines.append(
            f"| `{split}` | {item['candidate_events']} | {item['accepted_positions']} | "
            f"{item['total_return_pct']:+.6f}% | {item['max_drawdown_pct']:.6f}% | "
            f"{item['realized_win_rate']:.2%} | {item['top_positive_month_share']:.2%} |"
        )
    lines.extend(["", "## OOS Decision", ""])
    lines.extend(f"- {reason}" for reason in report["oos_diagnostic_reasons"] or ["All diagnostic gates pass; prospective confirmation would still be required."])
    lines.extend(["", "## Safety", "", "- `approved_for_paper = []`", "- `eligible_for_paper = false`", "- `safe_to_enable_trading = false`", "- `ready_for_combo_backtest = false`", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run frozen trend-sleeve combo diagnostic.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/frozen_trend_sleeve_combo_diagnostic.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/frozen_trend_sleeve_combo_diagnostic_2026-07-16.md"))
    args = parser.parse_args(argv)
    sources = {component: load_json(path) for component, path in SOURCE_PATHS.items()}
    if any(source is None for source in sources.values()):
        print("ERROR: Cannot load one or more frozen component reports")
        return 1
    report = build_report(sources, args.data)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"formation accepted={report['results']['formation']['accepted_positions']}")
    print(f"oos accepted={report['results']['oos']['accepted_positions']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

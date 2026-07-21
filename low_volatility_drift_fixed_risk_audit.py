"""Post-hoc 10%-per-position risk diagnostic for low-volatility drift breakout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import FOLDS, candidate_reasons, fold_events


POSITION_FRACTION = 0.10
MAX_POSITIONS = 5


def candidate_events_from_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(result.get("closed_positions", [])) + list(result.get("rejected_events", []))


def load_price_maps(data_dir: Path, symbols: list[str]) -> dict[str, dict[int, Bar]]:
    maps: dict[str, dict[int, Bar]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        maps[symbol] = {bar.ts: bar for bar in resample_minutes(bars, 1440)}
    return maps


def run_fixed_risk(events: list[dict[str, Any]], price_maps: dict[str, dict[int, Bar]]) -> dict[str, Any]:
    return simulate_portfolio(
        events,
        price_maps,
        initial_capital=100_000.0,
        max_positions=MAX_POSITIONS,
        position_fraction=POSITION_FRACTION,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
    )


def build_report(source: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    events = candidate_events_from_result(source.get("aggregate", {}))
    symbols = list(source.get("eligible_symbols", []))
    price_maps = load_price_maps(data_dir, symbols)
    aggregate = run_fixed_risk(events, price_maps)
    folds = {
        name: run_fixed_risk(fold_events(events, start, end), price_maps)
        for name, start, end in FOLDS
    }
    reasons = candidate_reasons(aggregate, folds)
    return {
        "report_type": "low_volatility_drift_fixed_risk_audit",
        "report_date": "2026-07-13",
        "scope": "posthoc_fixed_risk_diagnostic_requires_prospective_validation",
        "source_report_type": source.get("report_type"),
        "source_status": source.get("status"),
        "position_fraction": POSITION_FRACTION,
        "max_positions": MAX_POSITIONS,
        "nominal_gross_allocation_cap": POSITION_FRACTION * MAX_POSITIONS,
        "eligible_symbols": symbols,
        "reconstructed_candidate_events": len(events),
        "aggregate": aggregate,
        "folds": folds,
        "positive_fold_count": sum(float(item["total_return_pct"]) > 0 for item in folds.values()),
        "candidate_reasons": reasons,
        "status": "frozen_prospective_candidate" if not reasons else "posthoc_fixed_risk_rejected",
        "validated": False,
        "prospective_validation_required": True,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    result = report["aggregate"]
    lines = [
        "# Low-Volatility Drift Fixed-Risk Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Post-hoc 10%-per-position diagnostic; prospective validation remains mandatory.",
        "",
        "## Aggregate",
        "",
        f"- reconstructed candidate events: {report['reconstructed_candidate_events']}",
        f"- accepted positions: {result['accepted_positions']}",
        f"- return: {result['total_return_pct']:+.6f}%",
        f"- maximum drawdown: {result['max_drawdown_pct']:.6f}%",
        f"- win rate: {result['realized_win_rate']:.2%}",
        f"- average / peak gross exposure: {result['average_gross_exposure']:.2%} / {result['peak_gross_exposure']:.2%}",
        f"- positive half-year folds: {report['positive_fold_count']}/5",
        f"- top positive month share: {result['top_positive_month_share']:.2%}",
        "",
        "## Fold Returns",
        "",
        "| 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
        "| ---: | ---: | ---: | ---: | ---: |",
        "| " + " | ".join(f"{report['folds'][fold[0]]['total_return_pct']:+.6f}%" for fold in FOLDS) + " |",
        "",
        "## Decision",
        "",
    ]
    if report["candidate_reasons"]:
        lines.extend(f"- {reason}" for reason in report["candidate_reasons"])
    else:
        lines.append("- Historical risk screen passed; freeze unchanged for prospective observation.")
    lines.extend(["", f"Status: `{report['status']}`; validated: `false`.", "", "## Safety", "", "- `approved_for_paper = []`", "- `eligible_for_paper = false`", "- `safe_to_enable_trading = false`", "- `ready_for_combo_backtest = false`", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply the frozen 10% risk budget to drift breakout events.")
    parser.add_argument("--source", type=Path, default=Path("reports/low_volatility_drift_breakout_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/low_volatility_drift_fixed_risk_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/low_volatility_drift_fixed_risk_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    source = json.loads(args.source.read_text(encoding="utf-8"))
    report = build_report(source, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    result = report["aggregate"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
        f"max_dd={result['max_drawdown_pct']:.6f}%, folds={report['positive_fold_count']}/5, status={report['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

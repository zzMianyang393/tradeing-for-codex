"""Audit whether observed walk-forward folds use a stable symbol universe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from market import load_quantify_15m_csv
from regime_component_walk_forward_audit import FOLDS, eligible_symbols, load_json, parse_day


BAR_MS = 15 * 60 * 1000
MIN_FOLD_COVERAGE = 0.98


def expected_bar_count(start_ts: int, end_ts: int) -> int:
    return max(0, (end_ts - start_ts) // BAR_MS + 1)


def fold_coverage(timestamps: list[int], start_ts: int, end_ts: int) -> dict[str, float | int | bool]:
    expected = expected_bar_count(start_ts, end_ts)
    actual = len({ts for ts in timestamps if start_ts <= ts <= end_ts})
    ratio = actual / expected if expected else 0.0
    return {
        "expected_bars": expected,
        "actual_bars": actual,
        "coverage_ratio": round(ratio, 6),
        "eligible": ratio >= MIN_FOLD_COVERAGE,
    }


def constant_universe(eligibility_by_fold: dict[str, list[str]]) -> list[str]:
    sets = [set(symbols) for symbols in eligibility_by_fold.values()]
    return sorted(set.intersection(*sets)) if sets else []


def build_report(coverage: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    symbol_folds: dict[str, dict[str, Any]] = {}
    eligibility_by_fold: dict[str, list[str]] = {name: [] for name, _start, _end in FOLDS}

    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        timestamps = [int(bar.ts) for bar in bars]
        fold_results: dict[str, Any] = {}
        for name, start, end in FOLDS:
            result = fold_coverage(timestamps, parse_day(start), parse_day(end, end=True))
            fold_results[name] = result
            if result["eligible"]:
                eligibility_by_fold[name].append(symbol)
        symbol_folds[symbol] = {
            "first_timestamp": min(timestamps) if timestamps else None,
            "last_timestamp": max(timestamps) if timestamps else None,
            "folds": fold_results,
        }

    stable = constant_universe(eligibility_by_fold)
    return {
        "report_type": "historical_fold_universe_audit",
        "report_date": "2026-07-13",
        "scope": "observed_data_universe_stability_audit",
        "minimum_fold_coverage": MIN_FOLD_COVERAGE,
        "folds": [{"name": name, "start": start, "end": end} for name, start, end in FOLDS],
        "eligible_symbols_by_fold": {
            name: sorted(symbols_in_fold) for name, symbols_in_fold in eligibility_by_fold.items()
        },
        "eligible_symbol_count_by_fold": {
            name: len(symbols_in_fold) for name, symbols_in_fold in eligibility_by_fold.items()
        },
        "constant_full_window_symbols": stable,
        "constant_full_window_symbol_count": len(stable),
        "symbol_details": symbol_folds,
        "research_contract": {
            "primary_stability_panel": "constant_full_window_symbols",
            "secondary_breadth_panel": "fold_eligible_expanding_universe",
            "require_both_panels_in_new_strategy_reports": True,
            "do_not_compare_fold_returns_without_universe_disclosure": True,
        },
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Historical Fold Universe Audit",
        "",
        "Date: 2026-07-13",
        "",
        f"A symbol is fold-eligible only when at least {report['minimum_fold_coverage']:.0%} of expected 15m bars exist.",
        "",
        "## Fold Coverage",
        "",
        "| Fold | Eligible Symbols |",
        "| --- | ---: |",
    ]
    for fold in report["folds"]:
        name = fold["name"]
        lines.append(f"| {name} | {report['eligible_symbol_count_by_fold'][name]} |")
    lines.extend(
        [
            "",
            "## Constant Universe",
            "",
            f"- symbols: {report['constant_full_window_symbol_count']}",
            "- list: " + ", ".join(f"`{symbol}`" for symbol in report["constant_full_window_symbols"]),
            "",
            "## Research Contract",
            "",
            "- new stability reports must show the constant full-window universe as the primary panel",
            "- the fold-eligible expanding universe may be shown only as a secondary breadth panel",
            "- fold returns must disclose universe changes",
            "- this audit does not approve any strategy",
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
    parser = argparse.ArgumentParser(description="Audit symbol-universe stability across observed folds.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/historical_fold_universe_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(f"fold_counts={report['eligible_symbol_count_by_fold']}")
    print(f"constant_universe={report['constant_full_window_symbols']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

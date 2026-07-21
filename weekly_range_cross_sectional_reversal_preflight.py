"""Return-free capacity preflight for weekly range cross-sectional reversal."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from daily_volume_shock_reversal_audit import PRIMARY_START, late_constant_symbols
from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DATA_END, DAY_MS, load_json, parse_day
from regime_validation import regime_at_entry
from regime_validation_v2 import MEAN_REVERTING_RANGE, label_completed_4h_bars_v2


LOOKBACK_DAYS = 7
MIN_ELIGIBLE_SYMBOLS = 6
SELECTIONS_PER_SIDE = 3


def is_monday_utc(ts: int) -> bool:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).weekday() == 0


def select_reversal_cohorts(scores: dict[str, float]) -> tuple[list[str], list[str]]:
    ranked = sorted(scores, key=lambda symbol: (scores[symbol], symbol))
    longs = ranked[:SELECTIONS_PER_SIDE]
    shorts = list(reversed(ranked[-SELECTIONS_PER_SIDE:]))
    return longs, shorts


def build_inputs(
    data_dir: Path, symbols: list[str]
) -> tuple[dict[str, list[Bar]], dict[str, dict[int, int]], dict[str, list[tuple[int, str]]]]:
    daily: dict[str, list[Bar]] = {}
    daily_index: dict[str, dict[int, int]] = {}
    labels: dict[str, list[tuple[int, str]]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        daily_bars = resample_minutes(bars, 1440)
        daily[symbol] = daily_bars
        daily_index[symbol] = {bar.ts: index for index, bar in enumerate(daily_bars)}
        labels[symbol] = label_completed_4h_bars_v2(bars)
    return daily, daily_index, labels


def collect_preflight(
    data_dir: Path, symbols: list[str], start_ts: int, end_ts: int
) -> dict[str, Any]:
    daily, indices, labels = build_inputs(data_dir, symbols)
    reference = daily[symbols[0]] if symbols else []
    weeks: list[dict[str, Any]] = []
    selected_symbol_counts: Counter[str] = Counter()
    for reference_bar in reference:
        signal_ts = reference_bar.ts + DAY_MS
        if not start_ts <= signal_ts <= end_ts or not is_monday_utc(signal_ts):
            continue
        completed_day_ts = signal_ts - DAY_MS
        prior_day_ts = completed_day_ts - LOOKBACK_DAYS * DAY_MS
        scores: dict[str, float] = {}
        for symbol in symbols:
            if regime_at_entry(labels[symbol], signal_ts) != MEAN_REVERTING_RANGE:
                continue
            current_index = indices[symbol].get(completed_day_ts)
            prior_index = indices[symbol].get(prior_day_ts)
            if current_index is None or prior_index is None:
                continue
            current = daily[symbol][current_index]
            prior = daily[symbol][prior_index]
            if prior.close > 0:
                scores[symbol] = current.close / prior.close - 1.0
        accepted = len(scores) >= MIN_ELIGIBLE_SYMBOLS
        longs: list[str] = []
        shorts: list[str] = []
        if accepted:
            longs, shorts = select_reversal_cohorts(scores)
            selected_symbol_counts.update(longs + shorts)
        weeks.append(
            {
                "signal_ts": signal_ts,
                "signal_date_utc": datetime.fromtimestamp(signal_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                "eligible_range_symbols": len(scores),
                "capacity_pass": accepted,
                "selected_longs": longs,
                "selected_shorts": shorts,
            }
        )
    eligible_counts = [int(item["eligible_range_symbols"]) for item in weeks]
    passing = [item for item in weeks if item["capacity_pass"]]
    return {
        "weekly_observations": len(weeks),
        "capacity_passing_weeks": len(passing),
        "candidate_events": len(passing) * SELECTIONS_PER_SIDE * 2,
        "eligible_symbols_per_week": {
            "mean": round(mean(eligible_counts), 6) if eligible_counts else 0.0,
            "median": round(median(eligible_counts), 6) if eligible_counts else 0.0,
            "minimum": min(eligible_counts) if eligible_counts else 0,
            "maximum": max(eligible_counts) if eligible_counts else 0,
        },
        "selected_symbol_counts": dict(sorted(selected_symbol_counts.items())),
        "weeks": weeks,
    }


def validate_return_free(report: dict[str, Any]) -> list[str]:
    forbidden = ("return", "pnl", "profit", "drawdown", "win_rate", "exit_price")
    violations: list[str] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = f"{path}.{key}" if path else str(key)
                if any(token in str(key).lower() for token in forbidden):
                    violations.append(child)
                visit(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")

    visit(report, "")
    return violations


def build_report(universe: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = late_constant_symbols(universe)
    preflight = collect_preflight(data_dir, symbols, parse_day(PRIMARY_START), parse_day(DATA_END, end=True))
    report = {
        "report_type": "weekly_range_cross_sectional_reversal_preflight",
        "report_date": "2026-07-14",
        "scope": "return_free_event_capacity_only",
        "window": {"start": PRIMARY_START, "end": DATA_END},
        "constant_symbols": symbols,
        "constant_symbol_count": len(symbols),
        "frozen_preflight_inputs": {
            "required_regime": MEAN_REVERTING_RANGE,
            "ranking_lookback_days": LOOKBACK_DAYS,
            "minimum_eligible_symbols": MIN_ELIGIBLE_SYMBOLS,
            "selections_per_side": SELECTIONS_PER_SIDE,
            "schedule": "Monday 00:00 UTC",
        },
        "capacity": preflight,
        "preflight_pass": (
            int(preflight["capacity_passing_weeks"]) >= 20
            and int(preflight["candidate_events"]) >= 120
            and len(preflight["selected_symbol_counts"]) >= 12
        ),
        "outcome_fields_read": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }
    violations = validate_return_free(report)
    if violations:
        raise ValueError(f"return-free preflight contains forbidden fields: {violations}")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    capacity = report["capacity"]
    counts = capacity["eligible_symbols_per_week"]
    return "\n".join(
        [
            "# Weekly Range Cross-Sectional Reversal Preflight",
            "",
            "Date: 2026-07-14",
            "",
            "Return-free event-capacity preflight. No future trade outcome was read.",
            "",
            "## Capacity",
            "",
            f"- constant symbols: {report['constant_symbol_count']}",
            f"- observed Mondays: {capacity['weekly_observations']}",
            f"- Mondays with at least six range symbols: {capacity['capacity_passing_weeks']}",
            f"- candidate events: {capacity['candidate_events']}",
            f"- eligible range symbols per week: mean {counts['mean']:.2f}, median {counts['median']:.2f}, range {counts['minimum']}-{counts['maximum']}",
            f"- distinct selected symbols: {len(capacity['selected_symbol_counts'])}",
            f"- preflight pass: `{str(report['preflight_pass']).lower()}`",
            "",
            "## Safety",
            "",
            "- `outcome_fields_read = false`",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run return-free weekly range reversal preflight.")
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/weekly_range_cross_sectional_reversal_preflight.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/weekly_range_cross_sectional_reversal_preflight_2026-07-14.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.universe), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"passing_weeks={report['capacity']['capacity_passing_weeks']}, "
        f"candidate_events={report['capacity']['candidate_events']}, "
        f"preflight_pass={report['preflight_pass']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

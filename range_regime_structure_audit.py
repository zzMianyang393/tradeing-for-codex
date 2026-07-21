"""Describe whether the residual range label actually contains mean reversion."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from directional_regime_conditioned_audit import RANGE_COMPATIBLE_REGIMES
from market import add_features, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DATA_END, DATA_START, eligible_symbols, load_json, parse_day
from regime_validation import label_completed_4h_bars


HORIZONS = {"4h": 1, "12h": 3, "24h": 6, "72h": 18}
COST_PCT = 0.16


def signed_path_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "observations": len(values),
        "mean_expected_direction_return_pct": round(mean(values), 6) if values else 0.0,
        "median_expected_direction_return_pct": round(median(values), 6) if values else 0.0,
        "expected_direction_hit_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
        "gross_return_above_cost_rate": round(sum(value > COST_PCT for value in values) / len(values), 6) if values else 0.0,
    }


def summarize_observations(observations: list[dict[str, Any]], field: str) -> dict[str, Any]:
    return {
        horizon: signed_path_summary(
            [float(item[field][horizon]) for item in observations if field in item and horizon in item[field]]
        )
        for horizon in HORIZONS
    }


def range_runs(labels: list[str]) -> list[int]:
    runs: list[int] = []
    current = 0
    for label in labels:
        if label in RANGE_COMPATIBLE_REGIMES:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def collect_symbol(path: Path, start_ts: int, end_ts: int) -> dict[str, Any]:
    bars_15m = load_quantify_15m_csv(path)
    raw_4h = resample_minutes(bars_15m, 240)
    featured = add_features(raw_4h)
    label_pairs = label_completed_4h_bars(bars_15m)
    labels = [label for _ts, label in label_pairs]
    observations: list[dict[str, Any]] = []
    transitions: Counter[str] = Counter()
    persistence_counts: Counter[str] = Counter()
    persistence_denominators: Counter[str] = Counter()

    for index, ((available_ts, label), bar) in enumerate(zip(label_pairs, featured)):
        if available_ts < start_ts or available_ts > end_ts or label not in RANGE_COMPATIBLE_REGIMES or index < 6:
            continue
        item: dict[str, Any] = {"availability_ts": available_ts}
        prior_return = bar.close / featured[index - 6].close - 1.0
        continuation_direction = 1.0 if prior_return > 0 else (-1.0 if prior_return < 0 else 0.0)
        bb_direction = 1.0 if bar.close < bar.bb_lower else (-1.0 if bar.close > bar.bb_upper else 0.0)
        rsi_direction = 1.0 if bar.rsi < 30.0 else (-1.0 if bar.rsi > 70.0 else 0.0)
        item["prior_24h_return_pct"] = prior_return * 100.0
        item["continuation"] = {}
        if bb_direction:
            item["bb_reversion"] = {}
        if rsi_direction:
            item["rsi_reversion"] = {}
        for horizon, offset in HORIZONS.items():
            future_index = index + offset
            if future_index >= len(featured):
                continue
            future_return_pct = (featured[future_index].close / bar.close - 1.0) * 100.0
            item["continuation"][horizon] = continuation_direction * future_return_pct
            if bb_direction:
                item["bb_reversion"][horizon] = bb_direction * future_return_pct
            if rsi_direction:
                item["rsi_reversion"][horizon] = rsi_direction * future_return_pct
            persistence_denominators[horizon] += 1
            if labels[future_index] in RANGE_COMPATIBLE_REGIMES:
                persistence_counts[horizon] += 1
        if index + 1 < len(labels):
            transitions[labels[index + 1]] += 1
        observations.append(item)

    return {
        "observations": observations,
        "transitions": transitions,
        "persistence_counts": persistence_counts,
        "persistence_denominators": persistence_denominators,
        "runs": range_runs(labels),
        "total_labels": sum(start_ts <= ts <= end_ts for ts, _label in label_pairs),
        "range_labels": sum(start_ts <= ts <= end_ts and label in RANGE_COMPATIBLE_REGIMES for ts, label in label_pairs),
    }


def build_report(coverage: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
    observations: list[dict[str, Any]] = []
    transitions: Counter[str] = Counter()
    persistence_counts: Counter[str] = Counter()
    persistence_denominators: Counter[str] = Counter()
    runs: list[int] = []
    total_labels = 0
    range_labels = 0
    by_halfyear: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        result = collect_symbol(data_dir / f"{base}_15m.csv", start_ts, end_ts)
        observations.extend(result["observations"])
        transitions.update(result["transitions"])
        persistence_counts.update(result["persistence_counts"])
        persistence_denominators.update(result["persistence_denominators"])
        runs.extend(result["runs"])
        total_labels += int(result["total_labels"])
        range_labels += int(result["range_labels"])
        for item in result["observations"]:
            from datetime import datetime, timezone

            dt = datetime.fromtimestamp(int(item["availability_ts"]) / 1000, tz=timezone.utc)
            by_halfyear[f"{dt.year}-H{1 if dt.month <= 6 else 2}"].append(item)

    persistence = {
        horizon: round(persistence_counts[horizon] / persistence_denominators[horizon], 6)
        if persistence_denominators[horizon]
        else 0.0
        for horizon in HORIZONS
    }
    return {
        "report_type": "range_regime_structure_audit",
        "report_date": "2026-07-13",
        "scope": "descriptive_label_path_audit_not_strategy_test",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "symbols": symbols,
        "label_counts": {
            "total_completed_4h": total_labels,
            "range": range_labels,
            "range_share": round(range_labels / total_labels, 6) if total_labels else 0.0,
        },
        "range_run_length_4h_bars": {
            "runs": len(runs),
            "mean": round(mean(runs), 6) if runs else 0.0,
            "median": round(median(runs), 6) if runs else 0.0,
            "max": max(runs) if runs else 0,
        },
        "same_label_persistence": persistence,
        "next_label_transitions": dict(transitions),
        "prior_24h_direction_continuation": summarize_observations(observations, "continuation"),
        "bb_extreme_reversion": summarize_observations(observations, "bb_reversion"),
        "rsi_extreme_reversion": summarize_observations(observations, "rsi_reversion"),
        "halfyear_extreme_reversion": {
            bucket: {
                "bb": summarize_observations(items, "bb_reversion"),
                "rsi": summarize_observations(items, "rsi_reversion"),
            }
            for bucket, items in sorted(by_halfyear.items())
        },
        "interpretation_contract": {
            "positive_expected_direction_return": "supports the named continuation or reversion hypothesis",
            "negative_expected_direction_return": "contradicts the named hypothesis",
            "cost_reference_pct": COST_PCT,
        },
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["label_counts"]
    runs = report["range_run_length_4h_bars"]
    lines = [
        "# Range Regime Structure Audit",
        "",
        "Date: 2026-07-13",
        "",
        "This is a descriptive path audit, not a strategy backtest.",
        "",
        "## Label Structure",
        "",
        f"- completed 4h labels: {counts['total_completed_4h']}",
        f"- range labels: {counts['range']} ({counts['range_share']:.2%})",
        f"- range runs: {runs['runs']}; mean {runs['mean']:.2f} bars; median {runs['median']:.2f}; max {runs['max']}",
        "",
        "| Horizon | Same Label | Prior-24h Continuation | BB Reversion | RSI Reversion |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for horizon in HORIZONS:
        continuation = report["prior_24h_direction_continuation"][horizon]
        bb = report["bb_extreme_reversion"][horizon]
        rsi = report["rsi_extreme_reversion"][horizon]
        lines.append(
            f"| {horizon} | {report['same_label_persistence'][horizon]:.2%} | "
            f"{continuation['mean_expected_direction_return_pct']:+.6f}% ({continuation['expected_direction_hit_rate']:.2%}) | "
            f"{bb['mean_expected_direction_return_pct']:+.6f}% ({bb['expected_direction_hit_rate']:.2%}) | "
            f"{rsi['mean_expected_direction_return_pct']:+.6f}% ({rsi['expected_direction_hit_rate']:.2%}) |"
        )
    lines.extend(
        [
            "",
            "Positive values support the named path hypothesis; negative values contradict it. The gross cost reference is 0.16%.",
            "",
            "## Safety",
            "",
            "- no entry or exit rule was optimized",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Describe persistence and reversion inside the range label.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/range_regime_structure_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/range_regime_structure_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"range_share={report['label_counts']['range_share']:.2%}; "
        f"median_run={report['range_run_length_4h_bars']['median']:.2f} bars"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


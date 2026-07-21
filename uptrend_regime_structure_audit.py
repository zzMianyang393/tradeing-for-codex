"""Describe persistence and forward drift inside the completed-4h uptrend label."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME
from market import add_features, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DATA_END, DATA_START, FOLDS, eligible_symbols, load_json, parse_day
from regime_validation import label_completed_4h_bars


HORIZONS = {"4h": 1, "1d": 6, "3d": 18, "10d": 60}
AGE_BUCKETS = ("first_1d", "day_2_to_3", "day_4_to_10", "older_than_10d")


def forward_return_summary(values: list[float]) -> dict[str, float | int]:
    return {
        "observations": len(values),
        "mean_return_pct": round(mean(values), 6) if values else 0.0,
        "median_return_pct": round(median(values), 6) if values else 0.0,
        "positive_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
    }


def summarize_observations(observations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        horizon: forward_return_summary(
            [float(item["forward_returns_pct"][horizon]) for item in observations if horizon in item["forward_returns_pct"]]
        )
        for horizon in HORIZONS
    }


def consecutive_runs(labels: list[str], target: str = LONG_COMPATIBLE_REGIME) -> list[int]:
    runs: list[int] = []
    current = 0
    for label in labels:
        if label == target:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def run_age_bucket(age_4h_bars: int) -> str:
    if age_4h_bars <= 6:
        return "first_1d"
    if age_4h_bars <= 18:
        return "day_2_to_3"
    if age_4h_bars <= 60:
        return "day_4_to_10"
    return "older_than_10d"


def walk_forward_fold(ts: int) -> str:
    for name, start, end in FOLDS:
        if parse_day(start) <= ts <= parse_day(end, end=True):
            return name
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return f"outside-{dt.year}"


def collect_symbol(path: Path, start_ts: int, end_ts: int) -> dict[str, Any]:
    bars_15m = load_quantify_15m_csv(path)
    featured = add_features(resample_minutes(bars_15m, 240))
    label_pairs = label_completed_4h_bars(bars_15m)
    labels = [label for _available_ts, label in label_pairs]
    observations: list[dict[str, Any]] = []
    persistence_hits = defaultdict(int)
    persistence_total = defaultdict(int)
    label_counts = defaultdict(lambda: {"total": 0, "uptrend": 0})
    run_age = 0

    for index, ((available_ts, label), bar) in enumerate(zip(label_pairs, featured)):
        run_age = run_age + 1 if label == LONG_COMPATIBLE_REGIME else 0
        if not start_ts <= available_ts <= end_ts:
            continue
        bucket = walk_forward_fold(available_ts)
        label_counts[bucket]["total"] += 1
        if label != LONG_COMPATIBLE_REGIME:
            continue
        label_counts[bucket]["uptrend"] += 1
        item: dict[str, Any] = {
            "availability_ts": available_ts,
            "halfyear": bucket,
            "run_age_4h_bars": run_age,
            "run_age_bucket": run_age_bucket(run_age),
            "forward_returns_pct": {},
        }
        for horizon, offset in HORIZONS.items():
            future_index = index + offset
            if future_index >= len(featured):
                continue
            future_available_ts = label_pairs[future_index][0]
            if future_available_ts > end_ts:
                continue
            item["forward_returns_pct"][horizon] = (featured[future_index].close / bar.close - 1.0) * 100.0
            persistence_total[horizon] += 1
            if labels[future_index] == LONG_COMPATIBLE_REGIME:
                persistence_hits[horizon] += 1
        observations.append(item)

    in_window_labels = [
        label for available_ts, label in label_pairs if start_ts <= available_ts <= end_ts
    ]
    return {
        "observations": observations,
        "runs": consecutive_runs(in_window_labels),
        "persistence_hits": dict(persistence_hits),
        "persistence_total": dict(persistence_total),
        "label_counts": dict(label_counts),
    }


def drift_diagnosis(aggregate: dict[str, Any], by_halfyear: dict[str, Any]) -> dict[str, Any]:
    three_day_positive = sum(
        float(item["forward_returns"]["3d"]["mean_return_pct"]) > 0
        for item in by_halfyear.values()
        if int(item["forward_returns"]["3d"]["observations"]) > 0
    )
    ten_day_positive = sum(
        float(item["forward_returns"]["10d"]["mean_return_pct"]) > 0
        for item in by_halfyear.values()
        if int(item["forward_returns"]["10d"]["observations"]) > 0
    )
    evaluated_halfyears = len(by_halfyear)
    supports_long_context = (
        float(aggregate["3d"]["mean_return_pct"]) > 0
        and float(aggregate["10d"]["mean_return_pct"]) > 0
        and three_day_positive >= 3
        and ten_day_positive >= 3
    )
    return {
        "supports_long_context": supports_long_context,
        "positive_mean_halfyears_3d": three_day_positive,
        "positive_mean_halfyears_10d": ten_day_positive,
        "evaluated_halfyears": evaluated_halfyears,
        "next_action": (
            "pre_register_independent_uptrend_entry_batch"
            if supports_long_context
            else "refine_uptrend_context_before_testing_more_long_entries"
        ),
        "note": "This diagnoses the label as context; it does not approve a strategy or select an entry rule.",
    }


def build_report(coverage: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
    observations: list[dict[str, Any]] = []
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_halfyear: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_age: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_age_and_halfyear: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    runs: list[int] = []
    persistence_hits = defaultdict(int)
    persistence_total = defaultdict(int)
    label_counts = defaultdict(lambda: {"total": 0, "uptrend": 0})

    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        result = collect_symbol(data_dir / f"{base}_15m.csv", start_ts, end_ts)
        runs.extend(result["runs"])
        for horizon in HORIZONS:
            persistence_hits[horizon] += int(result["persistence_hits"].get(horizon, 0))
            persistence_total[horizon] += int(result["persistence_total"].get(horizon, 0))
        for bucket, counts in result["label_counts"].items():
            label_counts[bucket]["total"] += int(counts["total"])
            label_counts[bucket]["uptrend"] += int(counts["uptrend"])
        for item in result["observations"]:
            observations.append(item)
            by_symbol[symbol].append(item)
            by_halfyear[str(item["halfyear"])].append(item)
            by_age[str(item["run_age_bucket"])].append(item)
            by_age_and_halfyear[str(item["run_age_bucket"])][str(item["halfyear"])].append(item)

    total_labels = sum(item["total"] for item in label_counts.values())
    uptrend_labels = sum(item["uptrend"] for item in label_counts.values())
    aggregate = summarize_observations(observations)
    halfyear_summary = {
        bucket: {
            "total_labels": label_counts[bucket]["total"],
            "uptrend_labels": label_counts[bucket]["uptrend"],
            "uptrend_share": round(label_counts[bucket]["uptrend"] / label_counts[bucket]["total"], 6)
            if label_counts[bucket]["total"]
            else 0.0,
            "forward_returns": summarize_observations(items),
        }
        for bucket, items in sorted(by_halfyear.items())
    }
    return {
        "report_type": "uptrend_regime_structure_audit",
        "report_date": "2026-07-13",
        "scope": "descriptive_completed_4h_label_audit_not_strategy_test",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "symbols": symbols,
        "label_counts": {
            "total_completed_4h": total_labels,
            "uptrend": uptrend_labels,
            "uptrend_share": round(uptrend_labels / total_labels, 6) if total_labels else 0.0,
        },
        "uptrend_run_length_4h_bars": {
            "runs": len(runs),
            "mean": round(mean(runs), 6) if runs else 0.0,
            "median": round(median(runs), 6) if runs else 0.0,
            "max": max(runs) if runs else 0,
        },
        "same_label_persistence": {
            horizon: round(persistence_hits[horizon] / persistence_total[horizon], 6)
            if persistence_total[horizon]
            else 0.0
            for horizon in HORIZONS
        },
        "forward_returns": aggregate,
        "by_halfyear": halfyear_summary,
        "by_run_age": {
            bucket: summarize_observations(by_age.get(bucket, [])) for bucket in AGE_BUCKETS
        },
        "by_run_age_and_halfyear": {
            age_bucket: {
                fold_name: summarize_observations(by_age_and_halfyear[age_bucket].get(fold_name, []))
                for fold_name, _start, _end in FOLDS
            }
            for age_bucket in AGE_BUCKETS
        },
        "by_symbol": {
            symbol: summarize_observations(items) for symbol, items in sorted(by_symbol.items())
        },
        "diagnosis": drift_diagnosis(aggregate, halfyear_summary),
        "methodology_notes": [
            "Each label uses only a completed 4h candle and becomes available after that candle closes.",
            "Forward returns are descriptive overlapping observations, not independently executable trades.",
            "All observations stop at 2026-07-10; prospective candidate signals and returns are not read.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["label_counts"]
    runs = report["uptrend_run_length_4h_bars"]
    diagnosis = report["diagnosis"]
    lines = [
        "# Uptrend Regime Structure Audit",
        "",
        "Date: 2026-07-13",
        "",
        "This is a descriptive completed-label audit, not a strategy backtest.",
        "",
        "## Aggregate Structure",
        "",
        f"- completed 4h labels: {counts['total_completed_4h']}",
        f"- uptrend labels: {counts['uptrend']} ({counts['uptrend_share']:.2%})",
        f"- runs: {runs['runs']}; mean {runs['mean']:.2f} bars; median {runs['median']:.2f}; max {runs['max']}",
        "",
        "| Horizon | Same Label | Mean Forward Return | Median | Positive Rate |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for horizon in HORIZONS:
        item = report["forward_returns"][horizon]
        lines.append(
            f"| {horizon} | {report['same_label_persistence'][horizon]:.2%} | "
            f"{item['mean_return_pct']:+.6f}% | {item['median_return_pct']:+.6f}% | {item['positive_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Half-Year Drift",
            "",
            "| Half-Year | Uptrend Share | 3d Mean | 10d Mean |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for bucket, item in report["by_halfyear"].items():
        lines.append(
            f"| {bucket} | {item['uptrend_share']:.2%} | "
            f"{item['forward_returns']['3d']['mean_return_pct']:+.6f}% | "
            f"{item['forward_returns']['10d']['mean_return_pct']:+.6f}% |"
        )
    lines.extend(
        [
            "",
            "## Diagnosis",
            "",
            f"- supports long context: `{str(diagnosis['supports_long_context']).lower()}`",
            f"- positive 3d half-years: {diagnosis['positive_mean_halfyears_3d']}/{diagnosis['evaluated_halfyears']}",
            f"- positive 10d half-years: {diagnosis['positive_mean_halfyears_10d']}/{diagnosis['evaluated_halfyears']}",
            f"- next action: `{diagnosis['next_action']}`",
            "",
            "Overlapping forward returns describe the label. They are not trade PnL and must not be read as an approval.",
        ]
    )
    lines.extend(
        [
            "",
            "## Drift By Label Age",
            "",
            "| Label Age | Observations | 3d Mean | 10d Mean |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for bucket in AGE_BUCKETS:
        item = report["by_run_age"][bucket]
        lines.append(
            f"| `{bucket}` | {item['3d']['observations']} | "
            f"{item['3d']['mean_return_pct']:+.6f}% | {item['10d']['mean_return_pct']:+.6f}% |"
        )
    lines.extend(
        [
            "",
            "## Three-Day Drift By Age And Fold",
            "",
            "| Label Age | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for bucket in AGE_BUCKETS:
        fold_values = " | ".join(
            f"{report['by_run_age_and_halfyear'][bucket][fold_name]['3d']['mean_return_pct']:+.6f}%"
            for fold_name, _start, _end in FOLDS
        )
        lines.append(f"| `{bucket}` | {fold_values} |")
    lines.extend(
        [
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
    parser = argparse.ArgumentParser(description="Describe persistence and drift inside the uptrend label.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/uptrend_regime_structure_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/uptrend_regime_structure_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"uptrend_share={report['label_counts']['uptrend_share']:.2%}; "
        f"3d_mean={report['forward_returns']['3d']['mean_return_pct']:+.6f}%; "
        f"10d_mean={report['forward_returns']['10d']['mean_return_pct']:+.6f}%; "
        f"next={report['diagnosis']['next_action']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

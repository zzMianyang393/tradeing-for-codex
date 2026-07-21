"""Describe local uptrend drift by BTC alignment and cross-sectional breadth."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME
from market import add_features, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DATA_END, DATA_START, FOLDS, eligible_symbols, load_json, parse_day
from regime_validation import label_completed_4h_bars
from uptrend_regime_structure_audit import HORIZONS, summarize_observations, walk_forward_fold


def breadth_bucket(share: float) -> str:
    if share < 0.25:
        return "narrow_lt_25pct"
    if share < 0.50:
        return "mixed_25_to_50pct"
    return "broad_ge_50pct"


def context_key(btc_aligned: bool, bucket: str) -> str:
    return f"{'btc_uptrend' if btc_aligned else 'btc_not_uptrend'}__{bucket}"


def asset_group(symbol: str) -> str:
    base = symbol.split("-", 1)[0]
    return base if base in {"BTC", "ETH", "SOL"} else "other_alts"


def load_symbol_series(path: Path, start_ts: int, end_ts: int) -> list[dict[str, Any]]:
    bars_15m = load_quantify_15m_csv(path)
    featured = add_features(resample_minutes(bars_15m, 240))
    labels = label_completed_4h_bars(bars_15m)
    series: list[dict[str, Any]] = []
    run_age = 0
    for index, ((available_ts, label), bar) in enumerate(zip(labels, featured)):
        run_age = run_age + 1 if label == LONG_COMPATIBLE_REGIME else 0
        if start_ts <= available_ts <= end_ts:
            series.append(
                {
                    "source_index": index,
                    "available_ts": available_ts,
                    "label": label,
                    "close": float(bar.close),
                    "uptrend_run_age_4h_bars": run_age,
                }
            )
    return series


def summarize_groups(groups: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {name: summarize_observations(items) for name, items in sorted(groups.items())}


def build_report(coverage: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
    series_by_symbol: dict[str, list[dict[str, Any]]] = {}
    labels_by_ts: dict[int, dict[str, str]] = defaultdict(dict)

    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        series = load_symbol_series(data_dir / f"{base}_15m.csv", start_ts, end_ts)
        series_by_symbol[symbol] = series
        for row in series:
            labels_by_ts[int(row["available_ts"])][symbol] = str(row["label"])

    btc_symbol = next((symbol for symbol in symbols if symbol.startswith("BTC-")), "")
    btc_labels = {
        int(row["available_ts"]): str(row["label"])
        for row in series_by_symbol.get(btc_symbol, [])
    }
    breadth_by_ts: dict[int, dict[str, float | int]] = {}
    for ts, snapshot in labels_by_ts.items():
        total = len(snapshot)
        uptrend = sum(label == LONG_COMPATIBLE_REGIME for label in snapshot.values())
        breadth_by_ts[ts] = {
            "available_symbols": total,
            "uptrend_symbols": uptrend,
            "uptrend_share": uptrend / total if total else 0.0,
        }

    observations: list[dict[str, Any]] = []
    by_btc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_breadth: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_context: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_context_and_fold: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    persistent_by_context: dict[str, list[dict[str, Any]]] = defaultdict(list)
    persistent_by_context_and_fold: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_asset_and_fold: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for symbol, series in series_by_symbol.items():
        for index, row in enumerate(series):
            if row["label"] != LONG_COMPATIBLE_REGIME:
                continue
            ts = int(row["available_ts"])
            breadth = breadth_by_ts[ts]
            bucket = breadth_bucket(float(breadth["uptrend_share"]))
            btc_aligned = btc_labels.get(ts) == LONG_COMPATIBLE_REGIME
            key = context_key(btc_aligned, bucket)
            item: dict[str, Any] = {
                "symbol": symbol,
                "availability_ts": ts,
                "fold": walk_forward_fold(ts),
                "btc_uptrend": btc_aligned,
                "breadth_bucket": bucket,
                "breadth_share": float(breadth["uptrend_share"]),
                "uptrend_run_age_4h_bars": int(row["uptrend_run_age_4h_bars"]),
                "forward_returns_pct": {},
            }
            for horizon, offset in HORIZONS.items():
                future_index = index + offset
                if future_index >= len(series):
                    continue
                future = series[future_index]
                if int(future["available_ts"]) > end_ts:
                    continue
                item["forward_returns_pct"][horizon] = (float(future["close"]) / float(row["close"]) - 1.0) * 100.0
            observations.append(item)
            by_btc["btc_uptrend" if btc_aligned else "btc_not_uptrend"].append(item)
            by_breadth[bucket].append(item)
            by_context[key].append(item)
            by_context_and_fold[key][str(item["fold"])].append(item)
            group = asset_group(symbol)
            by_asset[group].append(item)
            by_asset_and_fold[group][str(item["fold"])].append(item)
            if int(item["uptrend_run_age_4h_bars"]) > 60:
                persistent_by_context[key].append(item)
                persistent_by_context_and_fold[key][str(item["fold"])].append(item)

    context_summary = summarize_groups(by_context)
    fold_summary = {
        key: {
            fold_name: summarize_observations(by_context_and_fold[key].get(fold_name, []))
            for fold_name, _start, _end in FOLDS
        }
        for key in sorted(by_context)
    }
    return {
        "report_type": "uptrend_breadth_context_audit",
        "report_date": "2026-07-13",
        "scope": "descriptive_completed_label_context_audit_not_strategy_test",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "symbols": symbols,
        "btc_symbol": btc_symbol,
        "observations": len(observations),
        "fixed_breadth_thresholds": {"narrow_lt": 0.25, "broad_ge": 0.50},
        "by_btc_alignment": summarize_groups(by_btc),
        "by_breadth": summarize_groups(by_breadth),
        "by_combined_context": context_summary,
        "by_combined_context_and_fold": fold_summary,
        "persistent_over_10d_by_combined_context": summarize_groups(persistent_by_context),
        "persistent_over_10d_by_combined_context_and_fold": {
            key: {
                fold_name: summarize_observations(persistent_by_context_and_fold[key].get(fold_name, []))
                for fold_name, _start, _end in FOLDS
            }
            for key in sorted(persistent_by_context)
        },
        "by_asset_group": summarize_groups(by_asset),
        "by_asset_group_and_fold": {
            group: {
                fold_name: summarize_observations(by_asset_and_fold[group].get(fold_name, []))
                for fold_name, _start, _end in FOLDS
            }
            for group in ("BTC", "ETH", "SOL", "other_alts")
        },
        "methodology_notes": [
            "BTC alignment and breadth use labels available at the same completed-4h timestamp.",
            "Breadth thresholds are fixed descriptive buckets, not an optimized parameter grid.",
            "Forward returns overlap and are not executable trade PnL.",
            "All observations stop at 2026-07-10; prospective signals and returns are not read.",
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
        "# Uptrend Breadth Context Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Descriptive completed-label context audit. This is not a strategy backtest.",
        "",
        "## BTC Alignment",
        "",
        "| Context | Observations | 3d Mean | 10d Mean |",
        "| --- | ---: | ---: | ---: |",
    ]
    for name, item in report["by_btc_alignment"].items():
        lines.append(
            f"| `{name}` | {item['3d']['observations']} | {item['3d']['mean_return_pct']:+.6f}% | "
            f"{item['10d']['mean_return_pct']:+.6f}% |"
        )
    lines.extend(
        [
            "",
            "## Market Breadth",
            "",
            "| Breadth | Observations | 3d Mean | 10d Mean |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for name, item in report["by_breadth"].items():
        lines.append(
            f"| `{name}` | {item['3d']['observations']} | {item['3d']['mean_return_pct']:+.6f}% | "
            f"{item['10d']['mean_return_pct']:+.6f}% |"
        )
    lines.extend(
        [
            "",
            "## Combined Context: Three-Day Mean By Fold",
            "",
            "| Context | Aggregate | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for key, item in report["by_combined_context"].items():
        fold_values = " | ".join(
            f"{report['by_combined_context_and_fold'][key][fold_name]['3d']['mean_return_pct']:+.6f}% "
            f"(n={report['by_combined_context_and_fold'][key][fold_name]['3d']['observations']})"
            for fold_name, _start, _end in FOLDS
        )
        lines.append(f"| `{key}` | {item['3d']['mean_return_pct']:+.6f}% | {fold_values} |")
    lines.extend(
        [
            "",
            "## Persistent Uptrend (>10d): Three-Day Mean By Fold",
            "",
            "This slice was motivated by the preceding label-age audit and is post-hoc discovery evidence.",
            "",
            "| Context | Aggregate | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for key, item in report["persistent_over_10d_by_combined_context"].items():
        fold_values = " | ".join(
            f"{report['persistent_over_10d_by_combined_context_and_fold'][key][fold_name]['3d']['mean_return_pct']:+.6f}% "
            f"(n={report['persistent_over_10d_by_combined_context_and_fold'][key][fold_name]['3d']['observations']})"
            for fold_name, _start, _end in FOLDS
        )
        lines.append(f"| `{key}` | {item['3d']['mean_return_pct']:+.6f}% | {fold_values} |")
    lines.extend(
        [
            "",
            "## Three-Day Drift By Asset Group And Fold",
            "",
            "| Asset Group | Aggregate | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for group in ("BTC", "ETH", "SOL", "other_alts"):
        item = report["by_asset_group"].get(group, {"3d": {"mean_return_pct": 0.0}})
        fold_values = " | ".join(
            f"{report['by_asset_group_and_fold'][group][fold_name]['3d']['mean_return_pct']:+.6f}% "
            f"(n={report['by_asset_group_and_fold'][group][fold_name]['3d']['observations']})"
            for fold_name, _start, _end in FOLDS
        )
        lines.append(f"| `{group}` | {item['3d']['mean_return_pct']:+.6f}% | {fold_values} |")
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
    parser = argparse.ArgumentParser(description="Describe uptrend drift by BTC alignment and market breadth.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/uptrend_breadth_context_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/uptrend_breadth_context_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    for name, item in report["by_breadth"].items():
        print(f"{name}: observations={item['3d']['observations']}, 3d={item['3d']['mean_return_pct']:+.6f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Return-free overlap preflight between OI leverage states and weak signals."""

from __future__ import annotations

import argparse
import bisect
import json
from collections import Counter
from pathlib import Path
from typing import Any

from daily_volume_shock_reversal_audit import LATE_FOLDS, PRIMARY_START
from low_volatility_drift_fixed_risk_audit import candidate_events_from_result
from oi_deleveraging_filter_audit import (
    DAY_MS,
    FIFTEEN_MINUTES_MS,
    LOOKBACK_DAYS,
    MIN_OI_7D_CHANGE,
    OIVR_PERCENTILE,
    OiRow,
    PriceBar,
    load_oi,
    load_price_bars,
    percentile,
)
from regime_component_walk_forward_audit import DATA_END, load_json, parse_day


DRIFT = "low_volatility_drift_bb_breakout_fixed_risk_v1"
UPTREND = "persistent_uptrend_ema20_reclaim_v1"
DOWNTREND = "ema_continuation_short_downtrend_v1"
COMPONENTS = (DRIFT, UPTREND, DOWNTREND)
STATE_WINDOW_DAYS = 3


def trailing_notionals_at_oi_times(oi_rows: list[OiRow], bars: list[PriceBar]) -> list[float]:
    timestamps = [bar.ts for bar in bars]
    prefix = [0.0]
    for bar in bars:
        prefix.append(prefix[-1] + max(bar.close, 0.0) * max(bar.volume, 0.0))
    values: list[float] = []
    for row in oi_rows:
        left = bisect.bisect_right(timestamps, row.ts - DAY_MS)
        right = bisect.bisect_right(timestamps, row.ts)
        values.append(prefix[right] - prefix[left])
    return values


def leverage_state_intervals(oi_rows: list[OiRow], bars: list[PriceBar]) -> list[tuple[int, int]]:
    notionals = trailing_notionals_at_oi_times(oi_rows, bars)
    oivr = [
        row.open_interest_usd / notional if notional > 0 else None
        for row, notional in zip(oi_rows, notionals)
    ]
    intervals: list[tuple[int, int]] = []
    for index in range(LOOKBACK_DAYS, len(oi_rows)):
        current = oivr[index]
        if current is None:
            continue
        prior = [value for value in oivr[index - LOOKBACK_DAYS:index] if value is not None]
        if len(prior) < LOOKBACK_DAYS // 2:
            continue
        threshold = percentile(prior, OIVR_PERCENTILE)
        previous_oi = oi_rows[index - 7].open_interest_usd
        if previous_oi <= 0:
            continue
        oi_change = oi_rows[index].open_interest_usd / previous_oi - 1.0
        if current >= threshold and oi_change >= MIN_OI_7D_CHANGE:
            start = oi_rows[index].ts + FIFTEEN_MINUTES_MS
            intervals.append((start, start + STATE_WINDOW_DAYS * DAY_MS))
    return intervals


def overlaps_state(entry_ts: int, intervals: list[tuple[int, int]]) -> bool:
    return any(start <= entry_ts <= end for start, end in intervals)


def rename_events(events: list[dict[str, Any]], component: str) -> list[dict[str, Any]]:
    return [
        {
            "symbol": str(event.get("symbol")),
            "entry_ts": int(event.get("entry_ts", 0)),
            "component_id": component,
        }
        for event in events
        if int(event.get("entry_ts", 0)) > 0
    ]


def source_events(
    drift: dict[str, Any], uptrend: dict[str, Any], downtrend: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    uptrend_result = (
        uptrend.get("components", {})
        .get("persistent_uptrend_ema20_reclaim", {})
        .get("primary_constant_universe", {})
        .get("aggregate", {})
    )
    downtrend_events = [
        event
        for event in candidate_events_from_result(downtrend.get("result", {}))
        if event.get("component_id") == "ema_continuation_short"
    ]
    return {
        DRIFT: rename_events(candidate_events_from_result(drift.get("aggregate", {})), DRIFT),
        UPTREND: rename_events(candidate_events_from_result(uptrend_result), UPTREND),
        DOWNTREND: rename_events(downtrend_events, DOWNTREND),
    }


def fold_name(ts: int) -> str | None:
    for name, start, end in LATE_FOLDS:
        if parse_day(start) <= ts <= parse_day(end, end=True):
            return name
    return None


def build_report(
    drift: dict[str, Any],
    uptrend: dict[str, Any],
    downtrend: dict[str, Any],
    data_dir: Path,
) -> dict[str, Any]:
    by_component = source_events(drift, uptrend, downtrend)
    symbols = sorted({event["symbol"] for events in by_component.values() for event in events})
    intervals_by_symbol: dict[str, list[tuple[int, int]]] = {}
    coverage: dict[str, Any] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        oi_path = data_dir / f"{symbol}_open_interest_1d.csv"
        price_path = data_dir / f"{base}_15m.csv"
        if not oi_path.exists() or not price_path.exists():
            coverage[symbol] = {"available": False}
            intervals_by_symbol[symbol] = []
            continue
        oi_rows = load_oi(oi_path)
        bars = load_price_bars(price_path)
        intervals = leverage_state_intervals(oi_rows, bars)
        intervals_by_symbol[symbol] = intervals
        coverage[symbol] = {
            "available": True,
            "first_oi_ts": oi_rows[0].ts if oi_rows else None,
            "last_oi_ts": oi_rows[-1].ts if oi_rows else None,
            "state_intervals": len(intervals),
        }

    component_rows: dict[str, Any] = {}
    all_overlaps: list[dict[str, Any]] = []
    start_ts = parse_day(PRIMARY_START)
    end_ts = parse_day(DATA_END, end=True)
    for component, events in by_component.items():
        window_events = [event for event in events if start_ts <= event["entry_ts"] <= end_ts]
        overlapping = [
            event
            for event in window_events
            if overlaps_state(event["entry_ts"], intervals_by_symbol.get(event["symbol"], []))
        ]
        all_overlaps.extend(overlapping)
        folds = Counter(fold_name(event["entry_ts"]) or "outside" for event in overlapping)
        component_rows[component] = {
            "events_in_window": len(window_events),
            "oi_state_overlaps": len(overlapping),
            "overlap_rate": round(len(overlapping) / len(window_events), 6) if window_events else 0.0,
            "overlaps_by_fold": dict(folds),
            "distinct_overlap_symbols": len({event["symbol"] for event in overlapping}),
        }
    aggregate_folds = Counter(fold_name(event["entry_ts"]) or "outside" for event in all_overlaps)
    qualified_components = sum(int(row["oi_state_overlaps"]) >= 15 for row in component_rows.values())
    qualified_folds = sum(int(aggregate_folds.get(name, 0)) >= 15 for name, _start, _end in LATE_FOLDS)
    report = {
        "report_type": "oi_state_weak_signal_overlap_preflight",
        "report_date": "2026-07-14",
        "scope": "return_free_temporal_overlap_capacity_only",
        "window": {"start": PRIMARY_START, "end": DATA_END},
        "state_definition": {
            "oivr_percentile": OIVR_PERCENTILE,
            "oivr_lookback_days": LOOKBACK_DAYS,
            "minimum_oi_7d_change": MIN_OI_7D_CHANGE,
            "available_at": "16:00 UTC",
            "state_start": "16:15 UTC",
            "state_window_days": STATE_WINDOW_DAYS,
        },
        "components": component_rows,
        "aggregate": {
            "oi_state_overlaps": len(all_overlaps),
            "distinct_overlap_symbols": len({event["symbol"] for event in all_overlaps}),
            "overlaps_by_fold": dict(aggregate_folds),
            "qualified_components": qualified_components,
            "qualified_folds": qualified_folds,
        },
        "oi_coverage": coverage,
        "preflight_pass": (
            len(all_overlaps) >= 60
            and len({event["symbol"] for event in all_overlaps}) >= 10
            and qualified_components >= 2
            and qualified_folds >= 2
        ),
        "outcome_fields_read": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    aggregate = report["aggregate"]
    lines = [
        "# OI-State Weak-Signal Overlap Preflight",
        "",
        "Date: 2026-07-14",
        "",
        "Return-free temporal overlap preflight. No weak-signal outcome was read.",
        "",
        "## Aggregate",
        "",
        f"- OI-state overlaps: {aggregate['oi_state_overlaps']}",
        f"- distinct symbols: {aggregate['distinct_overlap_symbols']}",
        f"- components with at least 15 overlaps: {aggregate['qualified_components']}",
        f"- folds with at least 15 overlaps: {aggregate['qualified_folds']}",
        f"- preflight pass: `{str(report['preflight_pass']).lower()}`",
        "",
        "## Components",
        "",
        "| Component | Events | OI Overlaps | Rate | Symbols | 2025-H1 | 2025-H2 | 2026-H1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for component, item in report["components"].items():
        folds = item["overlaps_by_fold"]
        lines.append(
            f"| `{component}` | {item['events_in_window']} | {item['oi_state_overlaps']} | "
            f"{item['overlap_rate']:.2%} | {item['distinct_overlap_symbols']} | "
            f"{folds.get('2025-H1', 0)} | {folds.get('2025-H2', 0)} | {folds.get('2026-H1', 0)} |"
        )
    lines.extend(
        [
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
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run return-free OI-state weak-signal overlap preflight.")
    parser.add_argument("--drift", type=Path, default=Path("reports/low_volatility_drift_fixed_risk_audit.json"))
    parser.add_argument("--uptrend", type=Path, default=Path("reports/persistent_uptrend_entry_batch_audit.json"))
    parser.add_argument("--downtrend", type=Path, default=Path("reports/downtrend_bidirectional_future_validation.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/oi_state_weak_signal_overlap_preflight.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/oi_state_weak_signal_overlap_preflight_2026-07-14.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.drift), load_json(args.uptrend), load_json(args.downtrend), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    aggregate = report["aggregate"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"overlaps={aggregate['oi_state_overlaps']}, symbols={aggregate['distinct_overlap_symbols']}, "
        f"components={aggregate['qualified_components']}, folds={aggregate['qualified_folds']}, "
        f"preflight_pass={report['preflight_pass']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

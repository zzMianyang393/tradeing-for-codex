"""Forward-return-free event inventory for a daily volume-shock reversal candidate."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DATA_END, DATA_START, DAY_MS, FOLDS, eligible_symbols, load_json, parse_day, wilder_atr
from uptrend_regime_structure_audit import walk_forward_fold


VOLUME_LOOKBACK = 20
VOLUME_MULTIPLE = 2.5
ATR_PERIOD = 14
RANGE_ATR_MULTIPLE = 1.5
EXTREME_CLOSE_FRACTION = 0.20


def true_range(current: Bar, previous_close: float) -> float:
    return max(current.high - current.low, abs(current.high - previous_close), abs(current.low - previous_close))


def event_direction(close_location: float) -> str | None:
    if close_location <= EXTREME_CLOSE_FRACTION:
        return "long"
    if close_location >= 1.0 - EXTREME_CLOSE_FRACTION:
        return "short"
    return None


def inventory_symbol(symbol: str, bars_15m: list[Bar], start_ts: int, end_ts: int) -> list[dict[str, Any]]:
    daily = resample_minutes(bars_15m, 1440)
    atr_values = wilder_atr(daily, ATR_PERIOD)
    events: list[dict[str, Any]] = []
    for index in range(max(VOLUME_LOOKBACK, ATR_PERIOD) + 1, len(daily)):
        signal_ts = daily[index].ts + DAY_MS
        if not start_ts <= signal_ts <= end_ts:
            continue
        prior_atr = atr_values[index - 1]
        prior_volume = mean(float(bar.volume_quote) for bar in daily[index - VOLUME_LOOKBACK:index])
        current = daily[index]
        daily_range = current.high - current.low
        if prior_atr is None or prior_atr <= 0 or prior_volume <= 0 or daily_range <= 0:
            continue
        volume_ratio = float(current.volume_quote) / prior_volume
        range_ratio = true_range(current, daily[index - 1].close) / float(prior_atr)
        close_location = (current.close - current.low) / daily_range
        direction = event_direction(close_location)
        if volume_ratio < VOLUME_MULTIPLE or range_ratio < RANGE_ATR_MULTIPLE or direction is None:
            continue
        events.append(
            {
                "symbol": symbol,
                "signal_ts": signal_ts,
                "signal_date": daily[index].time[:10],
                "fold": walk_forward_fold(signal_ts),
                "month": daily[index].time[:7],
                "direction": direction,
                "volume_ratio": round(volume_ratio, 6),
                "range_atr_ratio": round(range_ratio, 6),
                "close_location": round(close_location, 6),
            }
        )
    return events


def panel_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    fold_counts = Counter(str(event["fold"]) for event in events)
    direction_counts = Counter(str(event["direction"]) for event in events)
    month_counts = Counter(str(event["month"]) for event in events)
    total = len(events)
    return {
        "events": total,
        "fold_counts": {name: fold_counts[name] for name, _start, _end in FOLDS},
        "folds_with_events": sum(fold_counts[name] > 0 for name, _start, _end in FOLDS),
        "folds_with_at_least_10_events": sum(fold_counts[name] >= 10 for name, _start, _end in FOLDS),
        "direction_counts": dict(direction_counts),
        "direction_shares": {
            direction: round(direction_counts[direction] / total, 6) if total else 0.0
            for direction in ("long", "short")
        },
        "top_month_event_share": round(max(month_counts.values()) / total, 6) if total else 0.0,
        "top_month": month_counts.most_common(1)[0][0] if month_counts else None,
    }


def coverage_reasons(primary: dict[str, Any], secondary: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if int(primary["events"]) < 15:
        reasons.append(f"primary events {primary['events']} < 15")
    if int(primary["folds_with_events"]) < 4:
        reasons.append(f"primary folds with events {primary['folds_with_events']}/5 < 4/5")
    if int(secondary["events"]) < 60:
        reasons.append(f"secondary events {secondary['events']} < 60")
    if int(secondary["folds_with_at_least_10_events"]) < 3:
        reasons.append(
            f"secondary folds with at least 10 events {secondary['folds_with_at_least_10_events']}/5 < 3/5"
        )
    for direction in ("long", "short"):
        if float(secondary["direction_shares"][direction]) < 0.20:
            reasons.append(f"secondary {direction} share {secondary['direction_shares'][direction]:.2%} < 20%")
    if float(secondary["top_month_event_share"]) > 0.25:
        reasons.append(f"secondary top month event share {secondary['top_month_event_share']:.2%} > 25%")
    return reasons


def build_report(coverage: dict[str, Any], universe: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    start_ts = parse_day(DATA_START)
    end_ts = parse_day(DATA_END, end=True)
    events: list[dict[str, Any]] = []
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        events.extend(
            inventory_symbol(symbol, load_quantify_15m_csv(data_dir / f"{base}_15m.csv"), start_ts, end_ts)
        )
    primary_symbols = set(str(symbol) for symbol in universe["constant_full_window_symbols"])
    fold_eligible = {
        fold: set(str(symbol) for symbol in fold_symbols)
        for fold, fold_symbols in universe["eligible_symbols_by_fold"].items()
    }
    primary_events = [event for event in events if str(event["symbol"]) in primary_symbols]
    secondary_events = [
        event for event in events
        if str(event["symbol"]) in fold_eligible.get(str(event["fold"]), set())
    ]
    primary = panel_summary(primary_events)
    secondary = panel_summary(secondary_events)
    reasons = coverage_reasons(primary, secondary)
    return {
        "report_type": "daily_volume_shock_reversal_preflight",
        "report_date": "2026-07-13",
        "scope": "event_inventory_without_forward_returns",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "frozen_event_definition": {
            "volume_lookback_days": VOLUME_LOOKBACK,
            "volume_multiple": VOLUME_MULTIPLE,
            "atr_period": ATR_PERIOD,
            "range_atr_multiple": RANGE_ATR_MULTIPLE,
            "extreme_close_fraction": EXTREME_CLOSE_FRACTION,
            "direction": "reverse_the_extreme_close",
        },
        "primary_constant_universe_symbols": sorted(primary_symbols),
        "primary_panel": primary,
        "secondary_fold_eligible_panel": secondary,
        "coverage_reasons": reasons,
        "preflight_passed": not reasons,
        "status": "eligible_for_research_card" if not reasons else "event_coverage_blocked",
        "event_preview": secondary_events[:25],
        "forward_return_fields_present": False,
        "methodology_notes": [
            "No future price, exit, PnL, or return is read.",
            "ATR and volume baselines use only data completed before the shock candle.",
            "Signal timestamps become available only after the completed daily candle.",
        ],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    primary = report["primary_panel"]
    secondary = report["secondary_fold_eligible_panel"]
    lines = [
        "# Daily Volume-Shock Reversal Preflight",
        "",
        "Date: 2026-07-13",
        "",
        "Event inventory only. No forward returns or trade outcomes are computed.",
        "",
        "## Coverage",
        "",
        "| Panel | Events | Long | Short | Folds With Events | Folds >=10 | Top Month Share |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| constant BTC/ETH | {primary['events']} | {primary['direction_counts'].get('long', 0)} | "
        f"{primary['direction_counts'].get('short', 0)} | {primary['folds_with_events']}/5 | "
        f"{primary['folds_with_at_least_10_events']}/5 | {primary['top_month_event_share']:.2%} |",
        f"| fold-eligible expanding | {secondary['events']} | {secondary['direction_counts'].get('long', 0)} | "
        f"{secondary['direction_counts'].get('short', 0)} | {secondary['folds_with_events']}/5 | "
        f"{secondary['folds_with_at_least_10_events']}/5 | {secondary['top_month_event_share']:.2%} |",
        "",
        "## Fold Counts",
        "",
        "| Panel | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        "| constant BTC/ETH | " + " | ".join(str(primary["fold_counts"][name]) for name, _s, _e in FOLDS) + " |",
        "| fold-eligible expanding | " + " | ".join(str(secondary["fold_counts"][name]) for name, _s, _e in FOLDS) + " |",
        "",
        "## Decision",
        "",
    ]
    if report["coverage_reasons"]:
        lines.extend(f"- {reason}" for reason in report["coverage_reasons"])
    else:
        lines.append("- Event coverage passes; a frozen return-audit research card may be created.")
    lines.extend(
        [
            "",
            f"Status: `{report['status']}`.",
            "",
            "## Safety",
            "",
            "- forward-return fields present: `false`",
            "- `approved_for_paper = []`",
            "- `eligible_for_paper = false`",
            "- `safe_to_enable_trading = false`",
            "- `ready_for_combo_backtest = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory daily volume-shock reversal events without returns.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/daily_volume_shock_reversal_preflight.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/daily_volume_shock_reversal_preflight_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), load_json(args.universe), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"primary={report['primary_panel']['events']}; secondary={report['secondary_fold_eligible_panel']['events']}; "
        f"status={report['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Observed-data walk-forward audit for four frozen regime components."""

from __future__ import annotations

import argparse
import json
from bisect import bisect_left
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME, RANGE_COMPATIBLE_REGIMES
from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from market import Bar, FeatureBar, add_features, load_quantify_15m_csv, resample_minutes
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry


DAY_MS = 24 * 60 * 60 * 1000
ROUND_TRIP_COST = 0.0016
STOP_ATR_MULTIPLE = 2.0
INITIAL_EQUITY = 100_000.0
DATA_START = "2024-01-01"
DATA_END = "2026-07-10"

DONCHIAN_COMPONENT = "uptrend_donchian_55_20_long"
SUPERTREND_COMPONENT = "uptrend_supertrend_4h_long"
BB_COMPONENT = "range_bb_reversion_4h"
RSI_COMPONENT = "range_rsi_reversion_4h"
COMPONENTS = (DONCHIAN_COMPONENT, SUPERTREND_COMPONENT, BB_COMPONENT, RSI_COMPONENT)

FOLDS = (
    ("2024-H1", "2024-01-01", "2024-06-30"),
    ("2024-H2", "2024-07-01", "2024-12-31"),
    ("2025-H1", "2025-01-01", "2025-06-30"),
    ("2025-H2", "2025-07-01", "2025-12-31"),
    ("2026-H1", "2026-01-01", "2026-07-10"),
)


def parse_day(value: str, end: bool = False) -> int:
    from datetime import datetime, timezone

    suffix = "23:45:00" if end else "00:00:00"
    return int(datetime.strptime(f"{value} {suffix}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def eligible_symbols(coverage: dict[str, Any]) -> list[str]:
    return sorted(str(symbol) for symbol in coverage.get("eligible_symbols", []) if symbol)


def wilder_atr(bars: list[Bar], period: int) -> list[float | None]:
    if period <= 0:
        raise ValueError("period must be positive")
    true_ranges: list[float] = []
    for index, bar in enumerate(bars):
        previous_close = bars[index - 1].close if index else bar.close
        true_ranges.append(max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close)))
    values: list[float | None] = [None] * len(bars)
    if len(bars) < period:
        return values
    atr = sum(true_ranges[:period]) / period
    values[period - 1] = atr
    for index in range(period, len(bars)):
        atr = (atr * (period - 1) + true_ranges[index]) / period
        values[index] = atr
    return values


def supertrend_direction(bars: list[Bar], period: int = 10, multiplier: float = 3.0) -> tuple[list[int], list[float | None]]:
    atr_values = wilder_atr(bars, period)
    directions = [0] * len(bars)
    final_upper = 0.0
    final_lower = 0.0
    direction = 0
    for index, bar in enumerate(bars):
        atr = atr_values[index]
        if atr is None:
            continue
        midpoint = (bar.high + bar.low) / 2.0
        basic_upper = midpoint + multiplier * atr
        basic_lower = midpoint - multiplier * atr
        if direction == 0:
            final_upper = basic_upper
            final_lower = basic_lower
            direction = 1 if bar.close >= midpoint else -1
        else:
            previous_close = bars[index - 1].close
            final_upper = basic_upper if basic_upper < final_upper or previous_close > final_upper else final_upper
            final_lower = basic_lower if basic_lower > final_lower or previous_close < final_lower else final_lower
            if direction < 0 and bar.close > final_upper:
                direction = 1
            elif direction > 0 and bar.close < final_lower:
                direction = -1
        directions[index] = direction
    return directions, atr_values


def first_index_at_or_after(bars: list[Bar], ts: int) -> int | None:
    index = bisect_left([bar.ts for bar in bars], ts)
    return index if index < len(bars) else None


def trade_event(
    symbol: str,
    component: str,
    direction: str,
    signal_ts: int,
    bars_15m: list[Bar],
    atr: float,
    indicator_exit_ts: int | None,
    max_hold_ms: int,
    overall_end_ts: int,
    entry_regime: str,
) -> dict[str, Any] | None:
    entry_index = first_index_at_or_after(bars_15m, signal_ts)
    if entry_index is None:
        return None
    entry = bars_15m[entry_index]
    if entry.open <= 0 or atr <= 0:
        return None
    time_exit_ts = entry.ts + max_hold_ms
    planned_ts = min(indicator_exit_ts, time_exit_ts) if indicator_exit_ts is not None else time_exit_ts
    exit_index = first_index_at_or_after(bars_15m, planned_ts)
    if exit_index is None or bars_15m[exit_index].ts > overall_end_ts or exit_index <= entry_index:
        return None

    stop = entry.open - STOP_ATR_MULTIPLE * atr if direction == "long" else entry.open + STOP_ATR_MULTIPLE * atr
    exit_price = bars_15m[exit_index].open
    exit_reason = "indicator" if indicator_exit_ts is not None and indicator_exit_ts <= time_exit_ts else "time"
    actual_exit_index = exit_index
    for index in range(entry_index, exit_index + 1):
        bar = bars_15m[index]
        if direction == "long" and bar.low <= stop:
            actual_exit_index = index
            exit_price = stop
            exit_reason = "stop"
            break
        if direction == "short" and bar.high >= stop:
            actual_exit_index = index
            exit_price = stop
            exit_reason = "stop"
            break

    exit_bar = bars_15m[actual_exit_index]
    gross = exit_price / entry.open - 1.0 if direction == "long" else entry.open / exit_price - 1.0
    return {
        "symbol": symbol,
        "component_id": component,
        "direction": direction,
        "split": "observed_walk_forward",
        "signal_ts": signal_ts,
        "signal_timestamp_utc": _format_ts(signal_ts),
        "entry_ts": entry.ts,
        "entry_timestamp_utc": entry.time,
        "exit_ts": exit_bar.ts,
        "exit_timestamp_utc": exit_bar.time,
        "entry_price": round(entry.open, 10),
        "exit_price": round(exit_price, 10),
        "stop_price": round(stop, 10),
        "exit_reason": exit_reason,
        "gross_return_pct": round(gross * 100.0, 6),
        "net_return_pct": round((gross - ROUND_TRIP_COST) * 100.0, 6),
        "entry_regime": entry_regime,
        "portfolio_priority": 100.0,
    }


def _format_ts(ts: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def first_future_4h_exit(
    featured: list[FeatureBar],
    start_index: int,
    predicate: Callable[[FeatureBar, int], bool],
) -> int | None:
    for index in range(start_index + 1, len(featured)):
        if predicate(featured[index], index):
            return featured[index].ts + FOUR_HOURS_MS
    return None


def generate_4h_events(
    symbol: str,
    bars_15m: list[Bar],
    labels: list[tuple[int, str]],
    overall_start_ts: int,
    overall_end_ts: int,
    range_regimes: set[str] | None = None,
) -> list[dict[str, Any]]:
    raw_4h = resample_minutes(bars_15m, 240)
    featured = add_features(raw_4h)
    supertrend, supertrend_atr = supertrend_direction(raw_4h)
    events: list[dict[str, Any]] = []
    next_available = {SUPERTREND_COMPONENT: 0, BB_COMPONENT: 0, RSI_COMPONENT: 0}

    allowed_range_regimes = range_regimes if range_regimes is not None else RANGE_COMPATIBLE_REGIMES
    for index in range(1, len(featured)):
        signal_ts = featured[index].ts + FOUR_HOURS_MS
        if signal_ts < overall_start_ts or signal_ts > overall_end_ts:
            continue
        regime = regime_at_entry(labels, signal_ts)

        specifications: list[tuple[str, str, float, int | None, int]] = []
        atr = float(featured[index].atr)
        if (
            regime == LONG_COMPATIBLE_REGIME
            and supertrend[index - 1] < 0
            and supertrend[index] > 0
            and supertrend_atr[index] is not None
        ):
            exit_ts = first_future_4h_exit(featured, index, lambda _bar, j: supertrend[j] < 0)
            specifications.append((SUPERTREND_COMPONENT, "long", float(supertrend_atr[index]), exit_ts, 10 * DAY_MS))

        if regime in allowed_range_regimes:
            current = featured[index]
            previous = featured[index - 1]
            if previous.close >= previous.bb_lower and current.close < current.bb_lower:
                exit_ts = first_future_4h_exit(featured, index, lambda bar, _j: bar.close >= bar.bb_mid)
                specifications.append((BB_COMPONENT, "long", atr, exit_ts, 3 * DAY_MS))
            elif previous.close <= previous.bb_upper and current.close > current.bb_upper:
                exit_ts = first_future_4h_exit(featured, index, lambda bar, _j: bar.close <= bar.bb_mid)
                specifications.append((BB_COMPONENT, "short", atr, exit_ts, 3 * DAY_MS))

            if previous.rsi >= 30.0 and current.rsi < 30.0:
                exit_ts = first_future_4h_exit(featured, index, lambda bar, _j: bar.rsi >= 50.0)
                specifications.append((RSI_COMPONENT, "long", atr, exit_ts, 3 * DAY_MS))
            elif previous.rsi <= 70.0 and current.rsi > 70.0:
                exit_ts = first_future_4h_exit(featured, index, lambda bar, _j: bar.rsi <= 50.0)
                specifications.append((RSI_COMPONENT, "short", atr, exit_ts, 3 * DAY_MS))

        for component, direction, signal_atr, indicator_exit_ts, max_hold_ms in specifications:
            if signal_ts < next_available[component]:
                continue
            event = trade_event(
                symbol,
                component,
                direction,
                signal_ts,
                bars_15m,
                signal_atr,
                indicator_exit_ts,
                max_hold_ms,
                overall_end_ts,
                regime,
            )
            if event is not None:
                events.append(event)
                next_available[component] = int(event["exit_ts"]) + 15 * 60 * 1000
    return events


def generate_donchian_events(
    symbol: str,
    bars_15m: list[Bar],
    labels: list[tuple[int, str]],
    overall_start_ts: int,
    overall_end_ts: int,
) -> list[dict[str, Any]]:
    daily = resample_minutes(bars_15m, 1440)
    atr_values = wilder_atr(daily, 14)
    events: list[dict[str, Any]] = []
    next_available = 0
    for index in range(56, len(daily)):
        signal_ts = daily[index].ts + DAY_MS
        if signal_ts < overall_start_ts or signal_ts > overall_end_ts or signal_ts < next_available:
            continue
        prior_high = max(bar.high for bar in daily[index - 55:index])
        previous_prior_high = max(bar.high for bar in daily[index - 56:index - 1])
        if not (daily[index].close > prior_high and daily[index - 1].close <= previous_prior_high):
            continue
        regime = regime_at_entry(labels, signal_ts)
        if regime != LONG_COMPATIBLE_REGIME or atr_values[index] is None:
            continue
        indicator_exit_ts: int | None = None
        for future_index in range(index + 1, len(daily)):
            if future_index < 20:
                continue
            prior_low = min(bar.low for bar in daily[future_index - 20:future_index])
            if daily[future_index].close < prior_low:
                indicator_exit_ts = daily[future_index].ts + DAY_MS
                break
        event = trade_event(
            symbol,
            DONCHIAN_COMPONENT,
            "long",
            signal_ts,
            bars_15m,
            float(atr_values[index]),
            indicator_exit_ts,
            30 * DAY_MS,
            overall_end_ts,
            regime,
        )
        if event is not None:
            events.append(event)
            next_available = int(event["exit_ts"]) + 15 * 60 * 1000
    return events


def generate_events(data_dir: Path, symbols: list[str]) -> tuple[list[dict[str, Any]], dict[str, dict[int, Bar]]]:
    overall_start_ts = parse_day(DATA_START)
    overall_end_ts = parse_day(DATA_END, end=True)
    events: list[dict[str, Any]] = []
    price_maps: dict[str, dict[int, Bar]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        labels = label_completed_4h_bars(bars)
        events.extend(generate_donchian_events(symbol, bars, labels, overall_start_ts, overall_end_ts))
        events.extend(generate_4h_events(symbol, bars, labels, overall_start_ts, overall_end_ts))
        price_maps[symbol] = {bar.ts: bar for bar in resample_minutes(bars, 1440)}
    return events, price_maps


def fold_events(events: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    start_ts = parse_day(start)
    end_ts = parse_day(end, end=True)
    return [
        event
        for event in events
        if start_ts <= int(event["entry_ts"]) <= end_ts and int(event["exit_ts"]) <= end_ts
    ]


def run_portfolio(events: list[dict[str, Any]], price_maps: dict[str, dict[int, Bar]]) -> dict[str, Any]:
    return simulate_portfolio(
        events,
        price_maps,
        initial_capital=INITIAL_EQUITY,
        max_positions=5,
        position_fraction=0.20,
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
    )


def candidate_reasons(aggregate: dict[str, Any], folds: dict[str, dict[str, Any]]) -> list[str]:
    reasons: list[str] = []
    if int(aggregate.get("accepted_positions", 0)) < 30:
        reasons.append(f"aggregate accepted positions {aggregate.get('accepted_positions', 0)} < 30")
    if float(aggregate.get("total_return_pct", 0.0)) <= 0:
        reasons.append(f"aggregate return {aggregate.get('total_return_pct', 0.0):+.6f}% <= 0%")
    if float(aggregate.get("max_drawdown_pct", 0.0)) > 20.0:
        reasons.append(f"aggregate maximum drawdown {aggregate['max_drawdown_pct']:.6f}% > 20%")
    positive_folds = sum(float(item.get("total_return_pct", 0.0)) > 0 for item in folds.values())
    if positive_folds < 3:
        reasons.append(f"positive half-year folds {positive_folds}/5 < 3/5")
    concentration = float(aggregate.get("top_positive_month_share", 0.0))
    if concentration > 0.25:
        reasons.append(f"top positive month share {concentration:.2%} > 25%")
    return reasons


def summarize_shared_capital_combo(
    events: list[dict[str, Any]],
    price_maps: dict[str, dict[int, Bar]],
) -> dict[str, Any]:
    """Run all frozen sleeves through one unchanged shared-capital simulator."""
    aggregate = run_portfolio(events, price_maps)
    folds = {
        fold_name: run_portfolio(fold_events(events, start, end), price_maps)
        for fold_name, start, end in FOLDS
    }
    reasons = candidate_reasons(aggregate, folds)
    return {
        "generated_events": len(events),
        "event_counts_by_component": dict(Counter(str(event["component_id"]) for event in events)),
        "aggregate": aggregate,
        "folds": folds,
        "positive_fold_count": sum(float(item["total_return_pct"]) > 0 for item in folds.values()),
        "candidate_reasons": reasons,
        "status": "historical_walk_forward_candidate" if not reasons else "historical_walk_forward_rejected",
        "portfolio_rules": {
            "initial_capital": INITIAL_EQUITY,
            "max_positions": 5,
            "position_fraction": 0.20,
            "one_position_per_symbol": True,
            "same_timestamp_priority": "existing event_score_then_symbol; all frozen sleeves have equal score",
            "component_weights": "no sleeve weights; each accepted position uses the same fixed fraction",
        },
    }


def compact_portfolio_metrics(aggregate: dict[str, Any]) -> dict[str, Any]:
    """Keep ablation reports small and prevent equity-curve duplication."""
    keys = (
        "candidate_events", "accepted_positions", "capacity_rejected_events",
        "total_return_pct", "max_drawdown_pct", "realized_win_rate",
        "average_gross_exposure", "peak_gross_exposure", "capital_turnover",
        "top_positive_month_share",
    )
    return {key: aggregate.get(key) for key in keys}


def realized_pnl_by_component(aggregate: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for position in aggregate.get("closed_positions", []):
        component = str(position.get("component_id") or "unassigned")
        values[component] = values.get(component, 0.0) + float(position.get("realized_pnl", 0.0))
    return {component: round(value, 6) for component, value in sorted(values.items())}


def leave_one_sleeve_out_diagnostics(
    events: list[dict[str, Any]],
    price_maps: dict[str, dict[int, Bar]],
) -> dict[str, Any]:
    """Measure attribution only; ablations are never candidate-selection runs."""
    diagnostics: dict[str, Any] = {}
    for excluded in COMPONENTS:
        subset = [event for event in events if event["component_id"] != excluded]
        result = summarize_shared_capital_combo(subset, price_maps)
        diagnostics[excluded] = {
            "excluded_component": excluded,
            "remaining_components": [component for component in COMPONENTS if component != excluded],
            "aggregate": compact_portfolio_metrics(result["aggregate"]),
            "positive_fold_count": result["positive_fold_count"],
            "screen_reasons": result["candidate_reasons"],
            "diagnostic_only": True,
            "not_a_candidate": True,
        }
    return diagnostics


def build_report(coverage: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols(coverage)
    events, price_maps = generate_events(data_dir, symbols)
    components: dict[str, Any] = {}
    for component in COMPONENTS:
        component_events = [event for event in events if event["component_id"] == component]
        aggregate = run_portfolio(component_events, price_maps)
        folds: dict[str, Any] = {}
        for fold_name, start, end in FOLDS:
            folds[fold_name] = run_portfolio(fold_events(component_events, start, end), price_maps)
        reasons = candidate_reasons(aggregate, folds)
        components[component] = {
            "declared_regime": "uptrend" if component in {DONCHIAN_COMPONENT, SUPERTREND_COMPONENT} else "range",
            "generated_events": len(component_events),
            "event_direction_counts": dict(Counter(str(event["direction"]) for event in component_events)),
            "aggregate": aggregate,
            "folds": folds,
            "positive_fold_count": sum(float(item["total_return_pct"]) > 0 for item in folds.values()),
            "candidate_reasons": reasons,
            "status": "historical_walk_forward_candidate" if not reasons else "historical_walk_forward_rejected",
        }
    combined = summarize_shared_capital_combo(events, price_maps)
    combined["realized_pnl_by_component"] = realized_pnl_by_component(combined["aggregate"])
    combined["leave_one_sleeve_out"] = leave_one_sleeve_out_diagnostics(events, price_maps)
    return {
        "report_type": "regime_component_walk_forward_audit",
        "report_date": "2026-07-13",
        "scope": "observed_data_stability_research_not_unseen_validation",
        "observed_period": {"start": DATA_START, "end": DATA_END},
        "eligible_symbols": symbols,
        "excluded_symbols": coverage.get("blocked_symbols", []),
        "folds": [{"name": name, "start": start, "end": end} for name, start, end in FOLDS],
        "components": components,
        "shared_capital_combo": combined,
        "candidate_components": [name for name, item in components.items() if not item["candidate_reasons"]],
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regime Component Walk-Forward Audit",
        "",
        "Date: 2026-07-13",
        "",
        "Observed historical stability research. This is not a new unseen validation.",
        "",
        "## Aggregate Results",
        "",
        "| Component | Regime | Events | Accepted | Return | Max DD | Win | Positive Folds | Month Concentration | Status |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, item in report["components"].items():
        result = item["aggregate"]
        lines.append(
            f"| `{name}` | {item['declared_regime']} | {item['generated_events']} | {result['accepted_positions']} | "
            f"{result['total_return_pct']:+.6f}% | {result['max_drawdown_pct']:.6f}% | "
            f"{result['realized_win_rate']:.2%} | {item['positive_fold_count']}/5 | "
            f"{result['top_positive_month_share']:.2%} | `{item['status']}` |"
        )
    combo = report["shared_capital_combo"]
    combo_result = combo["aggregate"]
    lines.extend([
        "",
        "## Shared-Capital Four-Sleeve Baseline",
        "",
        "All four frozen sleeves compete for the same fixed five-position portfolio. This is a deterministic equal-position baseline, not a fitted allocation.",
        "",
        "| Events | Accepted | Return | Max DD | Win | Positive Folds | Month Concentration | Status |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        f"| {combo['generated_events']} | {combo_result['accepted_positions']} | {combo_result['total_return_pct']:+.6f}% | {combo_result['max_drawdown_pct']:.6f}% | {combo_result['realized_win_rate']:.2%} | {combo['positive_fold_count']}/5 | {combo_result['top_positive_month_share']:.2%} | `{combo['status']}` |",
        "",
    ])
    lines.extend([
        "## Failure Attribution Diagnostics",
        "",
        "These four leave-one-sleeve-out results explain the failed baseline. They are not a subset search and cannot create a candidate.",
        "",
        "| Excluded sleeve | Return | Max DD | Positive Folds | Diagnostic-only |",
        "| --- | ---: | ---: | ---: | --- |",
    ])
    for excluded, item in combo["leave_one_sleeve_out"].items():
        result = item["aggregate"]
        lines.append(
            f"| `{excluded}` | {result['total_return_pct']:+.6f}% | {result['max_drawdown_pct']:.6f}% | "
            f"{item['positive_fold_count']}/5 | true |"
        )
    lines.append("")
    lines.extend(["", "## Fold Returns", "", "| Component | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for name, item in report["components"].items():
        returns = " | ".join(f"{item['folds'][fold[0]]['total_return_pct']:+.6f}%" for fold in FOLDS)
        lines.append(f"| `{name}` | {returns} |")
    lines.extend(["", "## Decisions", ""])
    for name, item in report["components"].items():
        if item["candidate_reasons"]:
            lines.append(f"- `{name}`: " + "; ".join(item["candidate_reasons"]))
        else:
            lines.append(f"- `{name}`: passed the observed historical walk-forward screen.")
    lines.append(
        "- `shared_capital_combo`: " + "; ".join(combo["candidate_reasons"])
        if combo["candidate_reasons"] else "- `shared_capital_combo`: passed the observed historical walk-forward screen."
    )
    lines.append("- All leave-one-sleeve-out figures are diagnostic only and cannot become a candidate without a separately frozen prospective protocol.")
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
    parser = argparse.ArgumentParser(description="Audit four frozen regime components across observed half-year folds.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/regime_component_walk_forward_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/regime_component_walk_forward_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    for name, item in report["components"].items():
        result = item["aggregate"]
        print(
            f"{name}: accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
            f"max_dd={result['max_drawdown_pct']:.6f}%, folds={item['positive_fold_count']}/5, status={item['status']}"
        )
    combo = report["shared_capital_combo"]
    combo_result = combo["aggregate"]
    print(
        f"shared_capital_combo: accepted={combo_result['accepted_positions']}, "
        f"return={combo_result['total_return_pct']:+.6f}%, max_dd={combo_result['max_drawdown_pct']:.6f}%, "
        f"folds={combo['positive_fold_count']}/5, status={combo['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

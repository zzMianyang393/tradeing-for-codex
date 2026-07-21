"""Return-free preflight for weekly funding-term and price-regime alignment."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daily_volume_shock_reversal_audit import PRIMARY_START, late_constant_symbols
from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME, SHORT_COMPATIBLE_REGIME
from market import Bar, load_quantify_15m_csv, resample_minutes
from regime_component_walk_forward_audit import DATA_END, DAY_MS, load_json, parse_day
from regime_validation import regime_at_entry
from regime_validation_v2 import LOW_VOLATILITY_DRIFT, label_completed_4h_bars_v2


FUNDING_ROLLING_POINTS = 21
PERCENTILE_LOOKBACK_DAYS = 180
HIGH_QUANTILE = 0.80
LOW_QUANTILE = 0.20
PRICE_LOOKBACK_DAYS = 7
MIN_HISTORY_POINTS = 450
SIGNAL_MINUTES_AFTER_MIDNIGHT = 15


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be in [0, 1]")
    ordered = sorted(values)
    index = int((len(ordered) - 1) * quantile)
    return ordered[index]


def load_funding(path: Path) -> list[tuple[int, float]]:
    rows: list[tuple[int, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                rows.append((int(row["timestamp_ms"]), float(row["funding_rate"])))
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(rows)


def rolling_funding(points: list[tuple[int, float]]) -> list[tuple[int, float]]:
    if len(points) < FUNDING_ROLLING_POINTS:
        return []
    total = sum(value for _ts, value in points[:FUNDING_ROLLING_POINTS])
    result = [(points[FUNDING_ROLLING_POINTS - 1][0], total / FUNDING_ROLLING_POINTS)]
    for index in range(FUNDING_ROLLING_POINTS, len(points)):
        total += points[index][1] - points[index - FUNDING_ROLLING_POINTS][1]
        result.append((points[index][0], total / FUNDING_ROLLING_POINTS))
    return result


def funding_state(rolling: list[tuple[int, float]], signal_ts: int) -> dict[str, float | str] | None:
    available = [(ts, value) for ts, value in rolling if ts <= signal_ts]
    if not available:
        return None
    current_ts, current = available[-1]
    history_start = current_ts - PERCENTILE_LOOKBACK_DAYS * DAY_MS
    history = [value for ts, value in available[:-1] if history_start <= ts < current_ts]
    if len(history) < MIN_HISTORY_POINTS:
        return None
    low = percentile(history, LOW_QUANTILE)
    high = percentile(history, HIGH_QUANTILE)
    state = "neutral"
    if current > 0.0 and current >= high:
        state = "high_positive"
    elif current < 0.0 and current <= low:
        state = "low_negative"
    return {
        "state": state,
        "current": current,
        "low_threshold": low,
        "high_threshold": high,
        "latest_settlement_ts": current_ts,
        "history_points": len(history),
    }


def is_monday_signal(ts: int) -> bool:
    value = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return value.weekday() == 0 and value.hour == 0 and value.minute == SIGNAL_MINUTES_AFTER_MIDNIGHT


def build_symbol_inputs(
    data_dir: Path, symbol: str
) -> tuple[list[Bar], dict[int, int], list[tuple[int, str]], list[tuple[int, float]]]:
    base = symbol.split("-", 1)[0]
    bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
    daily = resample_minutes(bars, 1440)
    daily_index = {bar.ts: index for index, bar in enumerate(daily)}
    labels = label_completed_4h_bars_v2(bars)
    funding = rolling_funding(load_funding(data_dir / f"{symbol}_funding.csv"))
    return daily, daily_index, labels, funding


def collect_preflight(data_dir: Path, symbols: list[str], start_ts: int, end_ts: int) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    skipped: dict[str, str] = {}
    for symbol in symbols:
        funding_path = data_dir / f"{symbol}_funding.csv"
        if not funding_path.exists():
            skipped[symbol] = "missing_funding_file"
            continue
        daily, indices, labels, funding = build_symbol_inputs(data_dir, symbol)
        for bar in daily:
            signal_ts = bar.ts + DAY_MS + SIGNAL_MINUTES_AFTER_MIDNIGHT * 60 * 1000
            if not start_ts <= signal_ts <= end_ts or not is_monday_signal(signal_ts):
                continue
            completed_day_ts = signal_ts // DAY_MS * DAY_MS - DAY_MS
            prior_day_ts = completed_day_ts - PRICE_LOOKBACK_DAYS * DAY_MS
            current_index = indices.get(completed_day_ts)
            prior_index = indices.get(prior_day_ts)
            if current_index is None or prior_index is None:
                continue
            prior_close = daily[prior_index].close
            if prior_close <= 0:
                continue
            price_change = daily[current_index].close / prior_close - 1.0
            state = funding_state(funding, signal_ts)
            if state is None:
                continue
            regime = regime_at_entry(labels, signal_ts)
            direction: str | None = None
            if (
                state["state"] == "high_positive"
                and price_change > 0
                and regime in {LONG_COMPATIBLE_REGIME, LOW_VOLATILITY_DRIFT}
            ):
                direction = "long"
            elif (
                state["state"] == "low_negative"
                and price_change < 0
                and regime in {SHORT_COMPATIBLE_REGIME, LOW_VOLATILITY_DRIFT}
            ):
                direction = "short"
            if direction is None:
                continue
            events.append(
                {
                    "symbol": symbol,
                    "signal_ts": signal_ts,
                    "signal_date_utc": datetime.fromtimestamp(signal_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d"),
                    "direction": direction,
                    "funding_state": state["state"],
                    "latest_settlement_ts": state["latest_settlement_ts"],
                    "funding_history_points": state["history_points"],
                    "entry_regime": regime,
                    "prior_7d_price_change": round(price_change, 8),
                }
            )
    direction_counts = Counter(str(item["direction"]) for item in events)
    symbol_counts = Counter(str(item["symbol"]) for item in events)
    regime_counts = Counter(str(item["entry_regime"]) for item in events)
    active_weeks = {str(item["signal_date_utc"]) for item in events}
    return {
        "candidate_events": len(events),
        "direction_counts": dict(direction_counts),
        "distinct_symbols": len(symbol_counts),
        "symbol_counts": dict(sorted(symbol_counts.items())),
        "active_weeks": len(active_weeks),
        "regime_counts": dict(regime_counts),
        "skipped_symbols": skipped,
        "events": events,
    }


def validate_return_free(report: dict[str, Any]) -> list[str]:
    forbidden = ("future_return", "net_return", "pnl", "profit", "drawdown", "win_rate", "exit_price")
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
    capacity = collect_preflight(data_dir, symbols, parse_day(PRIMARY_START), parse_day(DATA_END, end=True))
    directions = capacity["direction_counts"]
    report = {
        "report_type": "funding_term_price_alignment_preflight",
        "report_date": "2026-07-14",
        "scope": "return_free_event_capacity_only",
        "window": {"start": PRIMARY_START, "end": DATA_END},
        "constant_symbols": symbols,
        "frozen_preflight_inputs": {
            "funding_rolling_settlements": FUNDING_ROLLING_POINTS,
            "percentile_lookback_days": PERCENTILE_LOOKBACK_DAYS,
            "high_quantile": HIGH_QUANTILE,
            "low_quantile": LOW_QUANTILE,
            "price_lookback_days": PRICE_LOOKBACK_DAYS,
            "schedule": "Monday 00:15 UTC",
            "long_regimes": [LONG_COMPATIBLE_REGIME, LOW_VOLATILITY_DRIFT],
            "short_regimes": [SHORT_COMPATIBLE_REGIME, LOW_VOLATILITY_DRIFT],
        },
        "capacity": capacity,
        "preflight_pass": (
            int(capacity["candidate_events"]) >= 100
            and int(directions.get("long", 0)) >= 30
            and int(directions.get("short", 0)) >= 30
            and int(capacity["distinct_symbols"]) >= 12
            and int(capacity["active_weeks"]) >= 30
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
    return "\n".join(
        [
            "# Funding-Term Price Alignment Preflight",
            "",
            "Date: 2026-07-14",
            "",
            "Return-free capacity preflight. This is not the rejected four-leg carry trade.",
            "",
            "## Capacity",
            "",
            f"- candidate events: {capacity['candidate_events']}",
            f"- long events: {capacity['direction_counts'].get('long', 0)}",
            f"- short events: {capacity['direction_counts'].get('short', 0)}",
            f"- distinct symbols: {capacity['distinct_symbols']}",
            f"- active weeks: {capacity['active_weeks']}",
            f"- preflight pass: `{str(report['preflight_pass']).lower()}`",
            "",
            "## Regime Counts",
            "",
            *[f"- `{name}`: {count}" for name, count in capacity["regime_counts"].items()],
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
    parser = argparse.ArgumentParser(description="Run funding-term price alignment capacity preflight.")
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/funding_term_price_alignment_preflight.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/funding_term_price_alignment_preflight_2026-07-14.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.universe), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    capacity = report["capacity"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"events={capacity['candidate_events']}, long={capacity['direction_counts'].get('long', 0)}, "
        f"short={capacity['direction_counts'].get('short', 0)}, weeks={capacity['active_weeks']}, "
        f"preflight_pass={report['preflight_pass']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Locked future-window validation for the fixed downtrend bidirectional combo."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from daily_rsi_mean_revert_audit import (
    DAY_MS,
    audit_symbol as audit_rsi_symbol,
    load_ohlcv,
    parse_timestamp_ms,
    resample_daily,
    rsi_values,
)
from directional_regime_conditioned_audit import annotate_events, build_regime_labels
from downtrend_bidirectional_combo_simulation import EMA_COMPONENT, RSI_COMPONENT, tag_components
from downtrend_bidirectional_fixed_risk_budget_simulation import COMPONENT_CAPS
from downtrend_rebound_capital_constrained_simulator import simulate_portfolio
from downtrend_rebound_event_time_filter_audit import strict_prior_regime_streak
from ema_crossover_4h_audit import audit_symbol as audit_ema_symbol, load_ohlcv_15m
from two_regime_shared_capital_combo_simulation import component_attribution


WINDOW_START = "2025-07-11"
WINDOW_END = "2026-07-10"
RSI_PROFILE = "daily_rsi_downtrend_rebound"
MIN_ACCEPTED = 30
MIN_COMPONENT_ACCEPTED = 10
MAX_DRAWDOWN_PCT = 20.0
MAX_POSITIVE_MONTH_SHARE = 0.25


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def eligible_symbols_from_coverage(coverage: dict[str, Any]) -> list[str]:
    return sorted(str(symbol) for symbol in coverage.get("eligible_symbols", []) if symbol)


def daily_inputs_from_15m(data_dir: Path, symbols: list[str]) -> dict[str, list[Any]]:
    daily_by_symbol: dict[str, list[Any]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        path = data_dir / f"{base}_15m.csv"
        daily_by_symbol[symbol] = resample_daily(load_ohlcv(path))
    return daily_by_symbol


def daily_price_maps(daily_by_symbol: dict[str, list[Any]]) -> dict[str, dict[int, Any]]:
    return {
        symbol: {bar.ts: bar for bar in bars}
        for symbol, bars in daily_by_symbol.items()
    }


def signal_rsi_map(daily: list[Any]) -> dict[int, float]:
    values = rsi_values([bar.close for bar in daily])
    return {
        bar.ts + DAY_MS: float(value)
        for bar, value in zip(daily, values)
        if value is not None
    }


def declared_downtrend_rsi_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in events if event.get("declared_compatible_regime") is True]


def generate_frozen_events(
    data_dir: Path,
    symbols: list[str],
    start_ts: int,
    end_ts: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    daily_by_symbol = daily_inputs_from_15m(data_dir, symbols)
    rsi_raw: list[dict[str, Any]] = []
    ema_raw: list[dict[str, Any]] = []
    rsi_maps: dict[str, dict[int, float]] = {}

    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        daily = daily_by_symbol[symbol]
        rsi_maps[symbol] = signal_rsi_map(daily)
        rsi_raw.extend(
            asdict(event)
            for event in audit_rsi_symbol(symbol, daily, start_ts, end_ts, end_ts)
        )

        bars_15m = load_ohlcv_15m(data_dir / f"{base}_15m.csv")
        ema_raw.extend(
            asdict(event)
            for event in audit_ema_symbol(symbol, bars_15m, start_ts, end_ts, end_ts)
            if event.exit_ts <= end_ts
        )

    rsi_directional = [{**event, "direction": "long"} for event in rsi_raw]
    labels = build_regime_labels(data_dir, rsi_directional + ema_raw)
    annotated_rsi = annotate_events(rsi_directional, labels, RSI_PROFILE)
    annotated_ema = annotate_events(ema_raw, labels, RSI_PROFILE)

    enriched_rsi: list[dict[str, Any]] = []
    for event in declared_downtrend_rsi_events(annotated_rsi):
        signal_rsi = rsi_maps.get(str(event["symbol"]), {}).get(int(event["entry_ts"]), 0.0)
        enriched_rsi.append(
            {
                **event,
                "prior_downtrend_4h_streak": strict_prior_regime_streak(
                    labels.get(str(event["symbol"]), []), int(event["entry_ts"])
                ),
                "signal_rsi": round(signal_rsi, 6),
                "event_time_inputs_complete": signal_rsi > 0.0,
            }
        )

    tagged = tag_components({"events": enriched_rsi}, {"events": annotated_ema})
    future_events = [
        {
            **event,
            "split": "future_unseen",
        }
        for event in tagged
        if start_ts <= int(event.get("entry_ts") or 0) <= end_ts
        and int(event.get("exit_ts") or 0) <= end_ts
    ]
    diagnostics = {
        "raw_rsi_events": len(rsi_raw),
        "raw_ema_events": len(ema_raw),
        "regime_eligible_rsi_events": sum(event["component_id"] == RSI_COMPONENT for event in future_events),
        "regime_eligible_ema_events": sum(event["component_id"] == EMA_COMPONENT for event in future_events),
        "regime_counts_at_entry": dict(Counter(str(event.get("entry_regime")) for event in future_events)),
    }
    return future_events, {"daily_by_symbol": daily_by_symbol, "diagnostics": diagnostics}


def validation_reasons(result: dict[str, Any], eligible_symbols: set[str]) -> list[str]:
    reasons: list[str] = []
    if float(result.get("total_return_pct", 0.0)) <= 0:
        reasons.append("future net return <= 0%")
    if float(result.get("max_drawdown_pct", 0.0)) > MAX_DRAWDOWN_PCT:
        reasons.append(f"future maximum drawdown {result['max_drawdown_pct']:.6f}% > {MAX_DRAWDOWN_PCT:.0f}%")
    if int(result.get("accepted_positions", 0)) < MIN_ACCEPTED:
        reasons.append(f"future accepted positions {result.get('accepted_positions', 0)} < {MIN_ACCEPTED}")

    attribution = result.get("component_attribution", {})
    for component in (RSI_COMPONENT, EMA_COMPONENT):
        item = attribution.get(component, {})
        accepted = int(item.get("accepted_positions", 0))
        contribution = float(item.get("return_contribution_pct", 0.0))
        if accepted < MIN_COMPONENT_ACCEPTED:
            reasons.append(f"{component} accepted positions {accepted} < {MIN_COMPONENT_ACCEPTED}")
        if contribution <= 0:
            reasons.append(f"{component} return contribution {contribution:+.6f}% <= 0%")

    concentration = float(result.get("top_positive_month_share", 0.0))
    if concentration > MAX_POSITIVE_MONTH_SHARE:
        reasons.append(f"positive-month concentration {concentration:.2%} > {MAX_POSITIVE_MONTH_SHARE:.0%}")

    traded = {str(position.get("symbol")) for position in result.get("closed_positions", [])}
    outside = sorted(traded - eligible_symbols)
    if outside:
        reasons.append(f"traded symbols failed frozen data gate: {', '.join(outside)}")
    return reasons


def build_report(coverage: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = eligible_symbols_from_coverage(coverage)
    start_ts = parse_timestamp_ms(f"{WINDOW_START} 00:00:00")
    end_ts = parse_timestamp_ms(f"{WINDOW_END} 23:45:00")
    events, inputs = generate_frozen_events(data_dir, symbols, start_ts, end_ts)
    result = simulate_portfolio(
        events,
        daily_price_maps(inputs["daily_by_symbol"]),
        priority_mode="event_score_then_symbol",
        one_position_per_symbol=True,
        component_position_caps=COMPONENT_CAPS,
    )
    result["component_attribution"] = component_attribution(result, (RSI_COMPONENT, EMA_COMPONENT))
    reasons = validation_reasons(result, set(symbols))
    return {
        "report_type": "downtrend_bidirectional_future_validation",
        "report_date": "2026-07-13",
        "research_id": "downtrend_bidirectional_fixed_risk_budget_future_v1",
        "scope": "locked_pre_registered_future_unseen_validation",
        "window": {"start": WINDOW_START, "end": WINDOW_END},
        "eligible_symbols": symbols,
        "excluded_symbols": coverage.get("blocked_symbols", []),
        "component_position_caps": COMPONENT_CAPS,
        "event_generation": inputs["diagnostics"],
        "result": result,
        "validation_reasons": reasons,
        "validation_passed": not reasons,
        "validation_status": "passed_locked_future_window" if not reasons else "failed_locked_future_window",
        "parameters_changed_after_result": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    result = report["result"]
    lines = [
        "# Downtrend Bidirectional Future Validation",
        "",
        "Date: 2026-07-13",
        "",
        f"Locked unseen window: `{report['window']['start']}` to `{report['window']['end']}`.",
        "",
        "## Result",
        "",
        "| Symbols | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Month Concentration |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| {len(report['eligible_symbols'])} | {result['candidate_events']} | {result['accepted_positions']} | "
            f"{result['capacity_rejected_events']} | {result['total_return_pct']:+.6f}% | "
            f"{result['max_drawdown_pct']:.6f}% | {result['realized_win_rate']:.2%} | "
            f"{result['average_gross_exposure']:.2%} | {result['top_positive_month_share']:.2%} |"
        ),
        "",
        "## Component Attribution",
        "",
        "| Component | Candidates | Accepted | Rejected | Return Contribution | Win |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    generated = report["event_generation"]
    candidate_key = {RSI_COMPONENT: "regime_eligible_rsi_events", EMA_COMPONENT: "regime_eligible_ema_events"}
    for component in (RSI_COMPONENT, EMA_COMPONENT):
        item = result["component_attribution"][component]
        lines.append(
            f"| `{component}` | {generated[candidate_key[component]]} | {item['accepted_positions']} | "
            f"{item['rejected_events']} | {item['return_contribution_pct']:+.6f}% | {item['realized_win_rate']:.2%} |"
        )
    lines.extend(["", "## Decision", ""])
    if report["validation_reasons"]:
        lines.extend(f"- {reason}" for reason in report["validation_reasons"])
    else:
        lines.append("- All pre-registered future-window criteria passed.")
    lines.extend(
        [
            "",
            f"Validation status: `{report['validation_status']}`.",
            "",
            "This result does not open trading gates. Portfolio approval requires a separate decision.",
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
    parser = argparse.ArgumentParser(description="Run the locked future validation.")
    parser.add_argument("--coverage", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/downtrend_bidirectional_future_validation.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/downtrend_bidirectional_future_validation_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(load_json(args.coverage), args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    result = report["result"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"future: accepted={result['accepted_positions']}, return={result['total_return_pct']:+.6f}%, "
        f"max_dd={result['max_drawdown_pct']:.6f}%, win={result['realized_win_rate']:.2%}"
    )
    print(f"validation_passed={report['validation_passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

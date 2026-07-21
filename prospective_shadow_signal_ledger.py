"""Prospective signal-only ledger with no outcome or execution evaluation."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from daily_volume_shock_reversal_audit import late_constant_symbols
from daily_volume_shock_reversal_preflight import (
    ATR_PERIOD,
    RANGE_ATR_MULTIPLE,
    VOLUME_LOOKBACK,
    VOLUME_MULTIPLE,
    true_range,
)
from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME, SHORT_COMPATIBLE_REGIME
from donchian_atr_trend_baseline_audit import generate_signals as generate_donchian_signals
from ema_crossover_4h_audit import ema_values
from low_volatility_drift_breakout_audit import breakout_direction
from market import Bar, add_features, load_quantify_15m_csv, resample_minutes
from persistent_uptrend_entry_batch_audit import persistent_context, run_ages
from prospective_candidate_registry import PROSPECTIVE_START
from regime_component_walk_forward_audit import DAY_MS, parse_day, wilder_atr
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry
from regime_validation_v2 import (
    LOW_VOLATILITY_DRIFT,
    MEAN_REVERTING_RANGE,
    label_completed_4h_bars_v2,
)
from weekly_cross_sectional_momentum_audit import LOOKBACK_DAYS, SHORT_COUNT, is_monday_utc


FIFTEEN_MINUTES_MS = 15 * 60 * 1000
INDEPENDENT_RULES = {
    "low_volatility_drift_bb_breakout_fixed_risk_v1",
    "ema_continuation_short_downtrend_v1",
    "persistent_uptrend_ema20_reclaim_v1",
    "daily_volume_shock_reversal_v1_short",
    "weekly_cross_sectional_momentum_v1_short",
    "weekly_range_microtrend_continuation_v1_long",
    "donchian_atr_trend_baseline",
}
ALLOWED_SIGNAL_FIELDS = {
    "candidate_id",
    "rule_version",
    "signal_ts",
    "signal_timestamp_utc",
    "symbol",
    "direction",
    "regime",
    "trigger_metrics",
    "observation_only",
}


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def common_cutoff(data_dir: Path, symbols: list[str], start_ts: int) -> int:
    latest: list[int] = []
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = load_quantify_15m_csv(data_dir / f"{base}_15m.csv")
        eligible = [bar.ts for bar in bars if bar.ts >= start_ts]
        if not eligible:
            return 0
        latest.append(max(eligible))
    return min(latest) if latest else 0


def load_completed_inputs(data_dir: Path, symbols: list[str], cutoff_ts: int) -> dict[str, list[Bar]]:
    loaded: dict[str, list[Bar]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        loaded[symbol] = [
            bar for bar in load_quantify_15m_csv(data_dir / f"{base}_15m.csv") if bar.ts <= cutoff_ts
        ]
    return loaded


def signal_record(
    candidate_id: str,
    signal_ts: int,
    symbol: str,
    direction: str,
    regime: str,
    metrics: dict[str, float | int],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "rule_version": "frozen_2026-07-14",
        "signal_ts": signal_ts,
        "signal_timestamp_utc": format_utc(signal_ts),
        "symbol": symbol,
        "direction": direction,
        "regime": regime,
        "trigger_metrics": metrics,
        "observation_only": True,
    }


def drift_breakout_signals(
    symbol: str, bars: list[Bar], start_ts: int, cutoff_ts: int
) -> list[dict[str, Any]]:
    featured = add_features(resample_minutes(bars, 240))
    labels = label_completed_4h_bars_v2(bars)
    signals: list[dict[str, Any]] = []
    for index in range(1, len(featured)):
        signal_ts = featured[index].ts + FOUR_HOURS_MS
        if not start_ts <= signal_ts <= cutoff_ts:
            continue
        if regime_at_entry(labels, signal_ts) != LOW_VOLATILITY_DRIFT:
            continue
        direction = breakout_direction(featured[index - 1], featured[index])
        if direction is None:
            continue
        current = featured[index]
        band = current.bb_upper if direction == "long" else current.bb_lower
        signals.append(
            signal_record(
                "low_volatility_drift_bb_breakout_fixed_risk_v1",
                signal_ts,
                symbol,
                direction,
                LOW_VOLATILITY_DRIFT,
                {"band_distance_atr": round((current.close - band) / current.atr, 6) if current.atr else 0.0},
            )
        )
    return signals


def ema_downtrend_short_signals(
    symbol: str, bars: list[Bar], start_ts: int, cutoff_ts: int
) -> list[dict[str, Any]]:
    bars_4h = resample_minutes(bars, 240)
    fast = ema_values(bars_4h, 20)
    slow = ema_values(bars_4h, 50)
    labels = label_completed_4h_bars(bars)
    signals: list[dict[str, Any]] = []
    for index in range(1, len(bars_4h)):
        signal_ts = bars_4h[index].ts + FOUR_HOURS_MS
        if not start_ts <= signal_ts <= cutoff_ts:
            continue
        if any(value is None for value in (fast[index - 1], slow[index - 1], fast[index], slow[index])):
            continue
        crossed_short = float(fast[index - 1]) >= float(slow[index - 1]) and float(fast[index]) < float(slow[index])
        if not crossed_short or regime_at_entry(labels, signal_ts) != SHORT_COMPATIBLE_REGIME:
            continue
        signals.append(
            signal_record(
                "ema_continuation_short_downtrend_v1",
                signal_ts,
                symbol,
                "short",
                SHORT_COMPATIBLE_REGIME,
                {"ema20_minus_ema50_pct": round((float(fast[index]) / float(slow[index]) - 1.0) * 100.0, 6)},
            )
        )
    return signals


def persistent_uptrend_signals(
    symbol: str,
    bars: list[Bar],
    btc_labels: list[tuple[int, str]],
    start_ts: int,
    cutoff_ts: int,
) -> list[dict[str, Any]]:
    featured = add_features(resample_minutes(bars, 240))
    labels = label_completed_4h_bars(bars)
    ages = run_ages(labels)
    signals: list[dict[str, Any]] = []
    for index in range(20, len(featured)):
        signal_ts = featured[index].ts + FOUR_HOURS_MS
        if not start_ts <= signal_ts <= cutoff_ts:
            continue
        local_label = labels[index][1]
        btc_label = regime_at_entry(btc_labels, signal_ts)
        if not persistent_context(local_label, ages[index], btc_label):
            continue
        previous, current = featured[index - 1], featured[index]
        if previous.close <= previous.ema20 and current.close > current.ema20:
            signals.append(
                signal_record(
                    "persistent_uptrend_ema20_reclaim_v1",
                    signal_ts,
                    symbol,
                    "long",
                    LONG_COMPATIBLE_REGIME,
                    {
                        "uptrend_run_age_4h_bars": ages[index],
                        "close_above_ema20_pct": round((current.close / current.ema20 - 1.0) * 100.0, 6),
                    },
                )
            )
    return signals


def volume_shock_short_signals(
    symbol: str, bars: list[Bar], start_ts: int, cutoff_ts: int
) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    atr_values = wilder_atr(daily, ATR_PERIOD)
    signals: list[dict[str, Any]] = []
    for index in range(max(VOLUME_LOOKBACK, ATR_PERIOD) + 1, len(daily)):
        signal_ts = daily[index].ts + DAY_MS
        if not start_ts <= signal_ts <= cutoff_ts:
            continue
        current = daily[index]
        prior_atr = atr_values[index - 1]
        prior_volume = mean(float(bar.volume_quote) for bar in daily[index - VOLUME_LOOKBACK:index])
        daily_range = current.high - current.low
        if prior_atr is None or prior_atr <= 0 or prior_volume <= 0 or daily_range <= 0:
            continue
        volume_ratio = float(current.volume_quote) / prior_volume
        range_ratio = true_range(current, daily[index - 1].close) / float(prior_atr)
        close_location = (current.close - current.low) / daily_range
        if volume_ratio < VOLUME_MULTIPLE or range_ratio < RANGE_ATR_MULTIPLE or close_location < 0.80:
            continue
        signals.append(
            signal_record(
                "daily_volume_shock_reversal_v1_short",
                signal_ts,
                symbol,
                "short",
                "daily_volume_shock_upside_exhaustion",
                {
                    "volume_ratio": round(volume_ratio, 6),
                    "range_atr_ratio": round(range_ratio, 6),
                    "close_location": round(close_location, 6),
                },
            )
        )
    return signals


def donchian_regime_gated_signals(
    symbol: str, bars: list[Bar], start_ts: int, cutoff_ts: int
) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels = label_completed_4h_bars(bars)
    signals: list[dict[str, Any]] = []
    for item in generate_donchian_signals(symbol, daily, start_ts, cutoff_ts, cutoff_ts):
        signal_ts = int(item.signal_ts)
        regime = regime_at_entry(labels, signal_ts)
        compatible = (
            item.direction == "long" and regime == LONG_COMPATIBLE_REGIME
        ) or (item.direction == "short" and regime == SHORT_COMPATIBLE_REGIME)
        if not compatible:
            continue
        boundary = item.donchian_high if item.direction == "long" else item.donchian_low
        distance = item.close - boundary if item.direction == "long" else boundary - item.close
        signals.append(
            signal_record(
                "donchian_atr_trend_baseline",
                signal_ts,
                symbol,
                str(item.direction),
                regime,
                {"breakout_distance_atr": round(distance / item.atr, 6) if item.atr else 0.0},
            )
        )
    return signals


def weekly_weakest_signals(
    daily_by_symbol: dict[str, list[Bar]], start_ts: int, cutoff_ts: int
) -> list[dict[str, Any]]:
    symbols = sorted(daily_by_symbol)
    indices = {symbol: {bar.ts: index for index, bar in enumerate(bars)} for symbol, bars in daily_by_symbol.items()}
    reference = daily_by_symbol[symbols[0]] if symbols else []
    signals: list[dict[str, Any]] = []
    for reference_bar in reference:
        signal_ts = reference_bar.ts + DAY_MS
        if not start_ts <= signal_ts <= cutoff_ts or not is_monday_utc(signal_ts):
            continue
        completed_day_ts = signal_ts - DAY_MS
        lookback_ts = completed_day_ts - LOOKBACK_DAYS * DAY_MS
        scores: dict[str, float] = {}
        for symbol in symbols:
            current_index = indices[symbol].get(completed_day_ts)
            prior_index = indices[symbol].get(lookback_ts)
            if current_index is not None and prior_index is not None:
                prior_close = daily_by_symbol[symbol][prior_index].close
                if prior_close > 0:
                    scores[symbol] = daily_by_symbol[symbol][current_index].close / prior_close - 1.0
        if len(scores) != len(symbols):
            continue
        ranked = sorted(scores, key=lambda item: (scores[item], item))[:SHORT_COUNT]
        for rank, symbol in enumerate(ranked, start=1):
            signals.append(
                signal_record(
                    "weekly_cross_sectional_momentum_v1_short",
                    signal_ts,
                    symbol,
                    "short",
                    "cross_sectional_weakness_continuation",
                    {"weakness_rank": rank, "trailing_change_28d_pct": round(scores[symbol] * 100.0, 6)},
                )
            )
    return signals


def weekly_range_long_signals(
    bars_by_symbol: dict[str, list[Bar]],
    daily_by_symbol: dict[str, list[Bar]],
    start_ts: int,
    cutoff_ts: int,
) -> list[dict[str, Any]]:
    symbols = sorted(daily_by_symbol)
    indices = {symbol: {bar.ts: index for index, bar in enumerate(bars)} for symbol, bars in daily_by_symbol.items()}
    labels = {symbol: label_completed_4h_bars_v2(bars_by_symbol[symbol]) for symbol in symbols}
    reference = daily_by_symbol[symbols[0]] if symbols else []
    signals: list[dict[str, Any]] = []
    for reference_bar in reference:
        signal_ts = reference_bar.ts + DAY_MS
        if not start_ts <= signal_ts <= cutoff_ts or not is_monday_utc(signal_ts):
            continue
        completed_day_ts = signal_ts - DAY_MS
        prior_day_ts = completed_day_ts - DAY_MS
        changes: dict[str, float] = {}
        for symbol in symbols:
            if regime_at_entry(labels[symbol], signal_ts) != MEAN_REVERTING_RANGE:
                continue
            current_index = indices[symbol].get(completed_day_ts)
            prior_index = indices[symbol].get(prior_day_ts)
            if current_index is None or prior_index is None:
                continue
            prior_close = daily_by_symbol[symbol][prior_index].close
            if prior_close > 0:
                change = daily_by_symbol[symbol][current_index].close / prior_close - 1.0
                if change > 0:
                    changes[symbol] = change
        ranked = sorted(changes, key=lambda item: (-abs(changes[item]), item))[:5]
        for rank, symbol in enumerate(ranked, start=1):
            signals.append(
                signal_record(
                    "weekly_range_microtrend_continuation_v1_long",
                    signal_ts,
                    symbol,
                    "long",
                    MEAN_REVERTING_RANGE,
                    {"priority_rank": rank, "trailing_change_24h_pct": round(changes[symbol] * 100.0, 6)},
                )
            )
    return signals


def validate_signal_schema(signals: list[dict[str, Any]]) -> None:
    forbidden_fragments = ("exit", "pnl", "profit", "drawdown", "win_rate", "entry_price", "equity")
    for signal in signals:
        if set(signal) != ALLOWED_SIGNAL_FIELDS:
            raise ValueError(f"unexpected signal fields for {signal.get('candidate_id')}: {sorted(set(signal) - ALLOWED_SIGNAL_FIELDS)}")
        serialized = json.dumps(signal, sort_keys=True).lower()
        if any(fragment in serialized for fragment in forbidden_fragments):
            raise ValueError(f"outcome or execution field found in signal {signal.get('candidate_id')}")


def build_ledger(
    registry: dict[str, Any], universe: dict[str, Any], data_dir: Path
) -> dict[str, Any]:
    frozen_symbols = sorted(
        {symbol for item in registry.get("frozen_candidates", []) for symbol in item.get("eligible_symbols", [])}
    )
    start_ts = parse_day(PROSPECTIVE_START)
    cutoff_ts = common_cutoff(data_dir, frozen_symbols, start_ts)
    loaded = load_completed_inputs(data_dir, frozen_symbols, cutoff_ts) if cutoff_ts else {}
    btc_symbol = next((symbol for symbol in frozen_symbols if symbol.startswith("BTC-")), "")
    btc_labels = label_completed_4h_bars(loaded[btc_symbol]) if btc_symbol else []
    weekly_symbols = [symbol for symbol in late_constant_symbols(universe) if symbol in loaded]
    weekly_daily = {symbol: resample_minutes(loaded[symbol], 1440) for symbol in weekly_symbols}

    signals: list[dict[str, Any]] = []
    for symbol in frozen_symbols:
        bars = loaded.get(symbol, [])
        signals.extend(drift_breakout_signals(symbol, bars, start_ts, cutoff_ts))
        signals.extend(ema_downtrend_short_signals(symbol, bars, start_ts, cutoff_ts))
        signals.extend(persistent_uptrend_signals(symbol, bars, btc_labels, start_ts, cutoff_ts))
        signals.extend(volume_shock_short_signals(symbol, bars, start_ts, cutoff_ts))
        signals.extend(donchian_regime_gated_signals(symbol, bars, start_ts, cutoff_ts))
    signals.extend(weekly_weakest_signals(weekly_daily, start_ts, cutoff_ts))
    signals.extend(weekly_range_long_signals(loaded, weekly_daily, start_ts, cutoff_ts))
    signals.sort(key=lambda item: (int(item["signal_ts"]), str(item["candidate_id"]), str(item["symbol"])))
    validate_signal_schema(signals)

    registered = list(registry.get("frozen_candidates", [])) + list(registry.get("watchlist", []))
    excluded = [
        {
            "candidate_id": str(item.get("candidate_id")),
            "reason": "derived_pair_or_combo_not_an_independent_signal_rule",
        }
        for item in registered
        if str(item.get("candidate_id", "")).startswith(("combo::", "pair_watchlist::"))
    ]
    counts = Counter(str(item["candidate_id"]) for item in signals)
    return {
        "report_type": "prospective_shadow_signal_ledger",
        "report_date": "2026-07-14",
        "scope": "signal_only_no_outcome_or_execution_evaluation",
        "prospective_start": PROSPECTIVE_START,
        "common_data_cutoff": format_utc(cutoff_ts) if cutoff_ts else None,
        "evaluated_rule_ids": sorted(INDEPENDENT_RULES),
        "excluded_registry_items": excluded,
        "signal_count": len(signals),
        "signal_counts_by_candidate": {candidate: counts.get(candidate, 0) for candidate in sorted(INDEPENDENT_RULES)},
        "signals": signals,
        "methodology_notes": [
            "Each row is a raw trigger known at signal time, not an accepted trade or position.",
            "Cooldown, portfolio capacity, exits, prices, and outcomes are intentionally not evaluated.",
            "Pair and combo registry rows reuse component signals and never emit duplicate signals.",
        ],
        "outcomes_evaluated": False,
        "exits_evaluated": False,
        "forward_returns_evaluated": False,
        "positions_opened": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Prospective Shadow Signal Ledger",
        "",
        "Date: 2026-07-14",
        "",
        "Signal-only observation. No exits, forward returns, PnL, or positions were evaluated.",
        "",
        f"- prospective start: `{report['prospective_start']}`",
        f"- common data cutoff: `{report['common_data_cutoff']}`",
        f"- raw signals recorded: {report['signal_count']}",
        "",
        "## Signal Counts",
        "",
        "| Candidate | Raw signals |",
        "| --- | ---: |",
    ]
    for candidate, count in report["signal_counts_by_candidate"].items():
        lines.append(f"| `{candidate}` | {count} |")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- These are raw triggers, not accepted trades.",
            "- `outcomes_evaluated = false`",
            "- `exits_evaluated = false`",
            "- `forward_returns_evaluated = false`",
            "- `positions_opened = false`",
            "- `safe_to_enable_trading = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record prospective signals without evaluating outcomes.")
    parser.add_argument("--registry", type=Path, default=Path("reports/prospective_candidate_registry.json"))
    parser.add_argument("--universe", type=Path, default=Path("reports/historical_fold_universe_audit.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/prospective_shadow_signal_ledger_2026-07-14.md"))
    args = parser.parse_args(argv)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    report = build_ledger(registry, universe, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(f"signals={report['signal_count']}; cutoff={report['common_data_cutoff']}; outcomes_evaluated=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

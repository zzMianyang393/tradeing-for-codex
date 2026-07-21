"""Signal-only prospective preflight for a second batch of low-turnover factors."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from daily_rsi_mean_revert_audit import rsi_values
from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME, SHORT_COMPATIBLE_REGIME
from market import Bar, load_quantify_15m_csv, resample_minutes
from prospective_shadow_signal_ledger import signal_record
from prospective_signal_conflict_arbitrator import SIGNAL_VALIDITY_DAYS, deduplicate_signals
from prospective_signal_interaction_audit import signal_pairs_within_window
from regime_component_walk_forward_audit import DAY_MS
from regime_validation import regime_at_entry
from regime_validation_v2 import MEAN_REVERTING_RANGE, label_completed_4h_bars_v2
from weekly_cross_sectional_momentum_audit import is_monday_utc


SECOND_BATCH_VALIDITY_DAYS = {
    "donchian55_trend_breakout_v1": 20,
    "daily_rsi_5pct_range_reversal_v1": 7,
    "daily_volume_breakout_v1": 7,
    "weekly_cross_sectional_momentum_90d_long_v1": 7,
}
RSI_PERCENTILE_LOOKBACK_DAYS = 252
MOMENTUM_LOOKBACK_DAYS = 90


def parse_utc(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires values")
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction)))
    return ordered[index]


def tagged_record(
    candidate_id: str,
    signal_ts: int,
    symbol: str,
    direction: str,
    regime: str,
    metrics: dict[str, float | int],
    compatible: bool,
) -> dict[str, Any]:
    item = signal_record(candidate_id, signal_ts, symbol, direction, regime, metrics)
    item["declared_regime_compatible"] = compatible
    return item


def donchian55_signals(
    symbol: str,
    daily: list[Bar],
    labels: list[tuple[int, str]],
    start_ts: int,
    cutoff_ts: int,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for index in range(55, len(daily)):
        signal_ts = daily[index].ts + DAY_MS
        if not start_ts <= signal_ts <= cutoff_ts:
            continue
        prior = daily[index - 55:index]
        high = max(item.high for item in prior)
        low = min(item.low for item in prior)
        if daily[index].close > high:
            direction, boundary = "long", high
        elif daily[index].close < low:
            direction, boundary = "short", low
        else:
            continue
        regime = regime_at_entry(labels, signal_ts)
        compatible = (direction == "long" and regime == LONG_COMPATIBLE_REGIME) or (
            direction == "short" and regime == SHORT_COMPATIBLE_REGIME
        )
        distance = daily[index].close - boundary if direction == "long" else boundary - daily[index].close
        signals.append(
            tagged_record(
                "donchian55_trend_breakout_v1",
                signal_ts,
                symbol,
                direction,
                regime,
                {"breakout_distance_pct": round(distance / boundary * 100.0, 6) if boundary else 0.0},
                compatible,
            )
        )
    return signals


def rsi_percentile_signals(
    symbol: str,
    daily: list[Bar],
    labels: list[tuple[int, str]],
    start_ts: int,
    cutoff_ts: int,
) -> list[dict[str, Any]]:
    rsi = rsi_values([bar.close for bar in daily])
    signals: list[dict[str, Any]] = []
    for index in range(RSI_PERCENTILE_LOOKBACK_DAYS, len(daily)):
        signal_ts = daily[index].ts + DAY_MS
        if not start_ts <= signal_ts <= cutoff_ts or rsi[index] is None:
            continue
        history = [float(item) for item in rsi[index - RSI_PERCENTILE_LOOKBACK_DAYS:index] if item is not None]
        if len(history) < 200:
            continue
        threshold = percentile(history, 0.05)
        if float(rsi[index]) >= threshold:
            continue
        regime = regime_at_entry(labels, signal_ts)
        signals.append(
            tagged_record(
                "daily_rsi_5pct_range_reversal_v1",
                signal_ts,
                symbol,
                "long",
                regime,
                {"rsi14": round(float(rsi[index]), 6), "prior_252d_5pct_rsi": round(threshold, 6)},
                regime == MEAN_REVERTING_RANGE,
            )
        )
    return signals


def volume_breakout_signals(
    symbol: str,
    daily: list[Bar],
    labels: list[tuple[int, str]],
    start_ts: int,
    cutoff_ts: int,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for index in range(5, len(daily)):
        signal_ts = daily[index].ts + DAY_MS
        if not start_ts <= signal_ts <= cutoff_ts:
            continue
        prior_volume = mean(float(item.volume_quote) for item in daily[index - 5:index])
        if prior_volume <= 0:
            continue
        volume_ratio = float(daily[index].volume_quote) / prior_volume
        if daily[index].close <= daily[index - 1].close or volume_ratio < 2.5:
            continue
        regime = regime_at_entry(labels, signal_ts)
        signals.append(
            tagged_record(
                "daily_volume_breakout_v1",
                signal_ts,
                symbol,
                "long",
                regime,
                {
                    "volume_to_prior_5d_mean": round(volume_ratio, 6),
                    "daily_close_change_pct": round((daily[index].close / daily[index - 1].close - 1.0) * 100.0, 6),
                },
                regime == LONG_COMPATIBLE_REGIME,
            )
        )
    return signals


def weekly_90d_momentum_signals(
    daily_by_symbol: dict[str, list[Bar]],
    labels_by_symbol: dict[str, list[tuple[int, str]]],
    btc_labels: list[tuple[int, str]],
    start_ts: int,
    cutoff_ts: int,
) -> list[dict[str, Any]]:
    symbols = sorted(daily_by_symbol)
    indices = {symbol: {bar.ts: index for index, bar in enumerate(bars)} for symbol, bars in daily_by_symbol.items()}
    reference = daily_by_symbol[symbols[0]] if symbols else []
    signals: list[dict[str, Any]] = []
    for reference_bar in reference:
        signal_ts = reference_bar.ts + DAY_MS
        if not start_ts <= signal_ts <= cutoff_ts or not is_monday_utc(signal_ts):
            continue
        completed_ts = signal_ts - DAY_MS
        prior_ts = completed_ts - MOMENTUM_LOOKBACK_DAYS * DAY_MS
        scores: dict[str, float] = {}
        for symbol in symbols:
            current_index = indices[symbol].get(completed_ts)
            prior_index = indices[symbol].get(prior_ts)
            if current_index is None or prior_index is None:
                continue
            prior_close = daily_by_symbol[symbol][prior_index].close
            if prior_close > 0:
                scores[symbol] = daily_by_symbol[symbol][current_index].close / prior_close - 1.0
        if len(scores) != len(symbols):
            continue
        leaders = sorted(scores, key=lambda item: (scores[item], item), reverse=True)[:3]
        btc_compatible = regime_at_entry(btc_labels, signal_ts) == LONG_COMPATIBLE_REGIME
        for rank, symbol in enumerate(leaders, start=1):
            regime = regime_at_entry(labels_by_symbol[symbol], signal_ts)
            signals.append(
                tagged_record(
                    "weekly_cross_sectional_momentum_90d_long_v1",
                    signal_ts,
                    symbol,
                    "long",
                    regime,
                    {"strength_rank": rank, "trailing_change_90d_pct": round(scores[symbol] * 100.0, 6)},
                    regime == LONG_COMPATIBLE_REGIME and btc_compatible,
                )
            )
    return signals


def exact_overlap_count(candidate: list[dict[str, Any]], existing: list[dict[str, Any]]) -> int:
    existing_keys = {
        (int(item["signal_ts"]), str(item["symbol"]), str(item["direction"]))
        for item in existing
    }
    return sum(
        (int(item["signal_ts"]), str(item["symbol"]), str(item["direction"])) in existing_keys
        for item in candidate
    )


def factor_decisions(
    raw: list[dict[str, Any]], compatible: list[dict[str, Any]], retained: list[dict[str, Any]], existing: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    raw_counts = Counter(str(item["candidate_id"]) for item in raw)
    compatible_counts = Counter(str(item["candidate_id"]) for item in compatible)
    retained_by_factor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in retained:
        retained_by_factor[str(item["candidate_id"])].append(item)
    decisions: list[dict[str, Any]] = []
    for factor in SECOND_BATCH_VALIDITY_DAYS:
        factor_retained = retained_by_factor[factor]
        overlaps = exact_overlap_count(factor_retained, existing)
        duplicate_share = overlaps / len(factor_retained) if factor_retained else 0.0
        if raw_counts[factor] == 0:
            status = "inactive_short_window_keep_observing"
        elif compatible_counts[factor] == 0:
            status = "signals_only_in_declared_incompatible_regimes"
        elif duplicate_share >= 0.80:
            status = "semantic_duplicate_observed_do_not_add"
        else:
            status = "eligible_for_shadow_observation_only"
        decisions.append(
            {
                "factor_id": factor,
                "raw_signal_count": raw_counts[factor],
                "declared_regime_compatible_signal_count": compatible_counts[factor],
                "fixed_window_signal_count": len(factor_retained),
                "exact_existing_overlap_count": overlaps,
                "exact_duplicate_share": round(duplicate_share, 6),
                "preflight_status": status,
                "allowed_as_standalone": False,
                "authorized_for_combo_backtest": False,
            }
        )
    return decisions


def build_report(ledger: dict[str, Any], registry: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    start_ts = parse_utc(f"{ledger['prospective_start']} 00:00:00")
    cutoff_ts = parse_utc(str(ledger["common_data_cutoff"]))
    symbols = sorted(
        {symbol for item in registry.get("frozen_candidates", []) for symbol in item.get("eligible_symbols", [])}
    )
    bars_by_symbol: dict[str, list[Bar]] = {}
    daily_by_symbol: dict[str, list[Bar]] = {}
    labels_by_symbol: dict[str, list[tuple[int, str]]] = {}
    raw: list[dict[str, Any]] = []
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        bars = [bar for bar in load_quantify_15m_csv(data_dir / f"{base}_15m.csv") if bar.ts <= cutoff_ts]
        daily = resample_minutes(bars, 1440)
        labels = label_completed_4h_bars_v2(bars)
        bars_by_symbol[symbol] = bars
        daily_by_symbol[symbol] = daily
        labels_by_symbol[symbol] = labels
        raw.extend(donchian55_signals(symbol, daily, labels, start_ts, cutoff_ts))
        raw.extend(rsi_percentile_signals(symbol, daily, labels, start_ts, cutoff_ts))
        raw.extend(volume_breakout_signals(symbol, daily, labels, start_ts, cutoff_ts))
    btc_symbol = next(symbol for symbol in symbols if symbol.startswith("BTC-"))
    raw.extend(
        weekly_90d_momentum_signals(
            daily_by_symbol,
            labels_by_symbol,
            labels_by_symbol[btc_symbol],
            start_ts,
            cutoff_ts,
        )
    )
    raw.sort(key=lambda item: (int(item["signal_ts"]), str(item["candidate_id"]), str(item["symbol"])))
    compatible = [item for item in raw if item["declared_regime_compatible"] is True]
    retained, suppressed = deduplicate_signals(compatible, SECOND_BATCH_VALIDITY_DAYS)
    existing = list(ledger.get("signals", []))
    decisions = factor_decisions(raw, compatible, retained, existing)
    combined_validity = {**SIGNAL_VALIDITY_DAYS, **SECOND_BATCH_VALIDITY_DAYS}
    combined, _ = deduplicate_signals(existing + retained, combined_validity)
    interactions = [
        item
        for item in signal_pairs_within_window(combined)
        if any(part in SECOND_BATCH_VALIDITY_DAYS for part in str(item["pair_key"]).split("__"))
        and any(part in SIGNAL_VALIDITY_DAYS for part in str(item["pair_key"]).split("__"))
    ]
    return {
        "report_type": "prospective_second_batch_factor_preflight",
        "report_date": "2026-07-14",
        "scope": "signal_only_low_turnover_factor_preflight_no_outcome_evaluation",
        "prospective_start": ledger.get("prospective_start"),
        "common_data_cutoff": ledger.get("common_data_cutoff"),
        "factor_count": len(SECOND_BATCH_VALIDITY_DAYS),
        "frozen_factor_rules": {
            "donchian55_trend_breakout_v1": "daily close outside prior 55-day channel; direction-compatible trend only",
            "daily_rsi_5pct_range_reversal_v1": "RSI14 below prior 252-day 5th percentile; range-v2 long only",
            "daily_volume_breakout_v1": "positive daily close and volume >= 2.5x prior 5-day mean; uptrend long only",
            "weekly_cross_sectional_momentum_90d_long_v1": "Monday top-3 prior 90-day strength; symbol and BTC uptrend only",
        },
        "fixed_validity_days": dict(SECOND_BATCH_VALIDITY_DAYS),
        "raw_signal_count": len(raw),
        "declared_regime_compatible_raw_signal_count": len(compatible),
        "declared_regime_incompatible_raw_signal_count": len(raw) - len(compatible),
        "fixed_window_signal_count": len(retained),
        "suppressed_repeat_count": len(suppressed),
        "factor_preflight_decisions": decisions,
        "existing_factor_interactions_within_24h": {
            "total": len(interactions),
            "same_direction": sum(item["relationship"] == "same_direction_consensus" for item in interactions),
            "opposite_direction": sum(item["relationship"] == "opposite_direction_conflict" for item in interactions),
            "observations": interactions,
        },
        "signals": retained,
        "signal_inputs_evaluated": True,
        "forward_prices_evaluated": False,
        "outcomes_evaluated": False,
        "exits_evaluated": False,
        "positions_opened": False,
        "orders_created": False,
        "registry_changed": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Prospective Second-Batch Factor Preflight",
        "",
        "Date: 2026-07-14",
        "",
        "Four low-turnover mechanisms were frozen before any prospective outcome evaluation.",
        "",
        f"- common data cutoff: `{report['common_data_cutoff']}`",
        f"- raw signals: {report['raw_signal_count']}",
        f"- declared-regime-compatible signals: {report['declared_regime_compatible_raw_signal_count']}",
        f"- fixed-window signals: {report['fixed_window_signal_count']}",
        "",
        "| Factor | Raw | Compatible | Fixed-window | Exact overlap | Status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["factor_preflight_decisions"]:
        lines.append(
            f"| `{item['factor_id']}` | {item['raw_signal_count']} | "
            f"{item['declared_regime_compatible_signal_count']} | {item['fixed_window_signal_count']} | "
            f"{item['exact_existing_overlap_count']} | `{item['preflight_status']}` |"
        )
    lines.extend(
        [
            "",
            "- `forward_prices_evaluated = false`",
            "- `outcomes_evaluated = false`",
            "- `registry_changed = false`",
            "- `safe_to_enable_trading = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight a second batch of low-turnover prospective weak factors.")
    parser.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    parser.add_argument("--registry", type=Path, default=Path("reports/prospective_candidate_registry.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_second_batch_factor_preflight.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/prospective_second_batch_factor_preflight_2026-07-14.md"))
    args = parser.parse_args(argv)
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    report = build_report(ledger, registry, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"raw={report['raw_signal_count']}; compatible={report['declared_regime_compatible_raw_signal_count']}; "
        f"fixed={report['fixed_window_signal_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

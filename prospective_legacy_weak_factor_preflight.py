"""Prospective signal-only preflight for rejected-but-reusable weak factors."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from daily_bb_mean_revert_audit import generate_signals as generate_bb_signals
from daily_rsi_mean_revert_audit import generate_signals as generate_rsi_signals
from daily_trend_pullback_audit import generate_signals as generate_pullback_signals
from donchian_atr_trend_baseline_audit import (
    generate_signals as generate_donchian_signals,
    load_ohlcv_15m,
    resample_daily,
)
from directional_regime_conditioned_audit import LONG_COMPATIBLE_REGIME, SHORT_COMPATIBLE_REGIME
from ema_crossover_4h_audit import generate_signals as generate_ema_signals, resample_4h
from market import load_quantify_15m_csv
from prospective_shadow_signal_ledger import signal_record
from prospective_signal_conflict_arbitrator import SIGNAL_VALIDITY_DAYS, deduplicate_signals
from prospective_signal_interaction_audit import signal_pairs_within_window
from regime_validation import regime_at_entry
from regime_validation_v2 import MEAN_REVERTING_RANGE, label_completed_4h_bars_v2


LEGACY_FACTOR_VALIDITY_DAYS = {
    "donchian_atr_trend_baseline": 10,
    "daily_bb_mean_revert": 10,
    "daily_rsi_mean_revert": 10,
    "daily_trend_pullback": 15,
    "4h_ema_crossover": 5,
}
LEGACY_FACTOR_ROLE = "rejected_standalone_reused_as_directional_weak_factor"


def parse_utc(value: str) -> int:
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def metric_donchian(signal: Any) -> dict[str, float]:
    boundary = signal.donchian_high if signal.direction == "long" else signal.donchian_low
    signed_distance = signal.close - boundary if signal.direction == "long" else boundary - signal.close
    return {"breakout_distance_atr": round(signed_distance / signal.atr, 6) if signal.atr else 0.0}


def metric_bb(signal: Any) -> dict[str, float]:
    return {"distance_below_lower_pct": round((signal.bb_lower / signal.close - 1.0) * 100.0, 6)}


def metric_rsi(signal: Any) -> dict[str, float]:
    return {"rsi14": round(float(signal.rsi), 6)}


def metric_pullback(signal: Any) -> dict[str, float]:
    return {
        "ema50_above_ema200_pct": round((signal.ema_context / signal.ema_slow - 1.0) * 100.0, 6),
        "close_below_ema20_pct": round((signal.ema_fast / signal.close - 1.0) * 100.0, 6),
    }


def metric_ema(signal: Any) -> dict[str, float]:
    return {"ema20_minus_ema50_pct": round((signal.fast_ema / signal.slow_ema - 1.0) * 100.0, 6)}


def convert_signals(
    candidate_id: str,
    source: list[Any],
    labels: list[tuple[int, str]],
    direction: str | Callable[[Any], str],
    metric_builder: Callable[[Any], dict[str, float]],
    compatibility: Callable[[str, str], bool],
) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for item in source:
        signal_ts = int(item.signal_ts)
        item_direction = direction(item) if callable(direction) else direction
        regime = regime_at_entry(labels, signal_ts)
        record = signal_record(
                candidate_id,
                signal_ts,
                str(item.symbol),
                item_direction,
                regime,
                metric_builder(item),
            )
        record["declared_regime_compatible"] = compatibility(item_direction, regime)
        converted.append(record)
    return converted


def generate_symbol_signals(
    symbol: str, data_dir: Path, start_ts: int, cutoff_ts: int
) -> list[dict[str, Any]]:
    base = symbol.split("-", 1)[0]
    audit_bars = [bar for bar in load_ohlcv_15m(data_dir / f"{base}_15m.csv") if bar.ts <= cutoff_ts]
    market_bars = [bar for bar in load_quantify_15m_csv(data_dir / f"{base}_15m.csv") if bar.ts <= cutoff_ts]
    labels = label_completed_4h_bars_v2(market_bars)
    daily = resample_daily(audit_bars)
    args = (symbol, daily, start_ts, cutoff_ts, cutoff_ts)
    signals: list[dict[str, Any]] = []
    signals.extend(
        convert_signals(
            "donchian_atr_trend_baseline",
            generate_donchian_signals(*args),
            labels,
            lambda item: str(item.direction),
            metric_donchian,
            lambda direction, regime: (
                direction == "long" and regime == LONG_COMPATIBLE_REGIME
            ) or (direction == "short" and regime == SHORT_COMPATIBLE_REGIME),
        )
    )
    signals.extend(
        convert_signals(
            "daily_bb_mean_revert",
            generate_bb_signals(*args),
            labels,
            "long",
            metric_bb,
            lambda _direction, regime: regime == MEAN_REVERTING_RANGE,
        )
    )
    signals.extend(
        convert_signals(
            "daily_rsi_mean_revert",
            generate_rsi_signals(*args),
            labels,
            "long",
            metric_rsi,
            lambda _direction, regime: regime == MEAN_REVERTING_RANGE,
        )
    )
    signals.extend(
        convert_signals(
            "daily_trend_pullback",
            generate_pullback_signals(*args),
            labels,
            "long",
            metric_pullback,
            lambda _direction, regime: regime == LONG_COMPATIBLE_REGIME,
        )
    )
    ema_source = generate_ema_signals(symbol, resample_4h(audit_bars), start_ts, cutoff_ts, cutoff_ts)
    signals.extend(
        convert_signals(
            "4h_ema_crossover",
            ema_source,
            labels,
            lambda item: str(item.direction),
            metric_ema,
            lambda direction, regime: (
                direction == "long" and regime == LONG_COMPATIBLE_REGIME
            ) or (direction == "short" and regime == SHORT_COMPATIBLE_REGIME),
        )
    )
    return signals


def exact_overlap_summary(
    legacy: list[dict[str, Any]], existing: list[dict[str, Any]]
) -> dict[str, Any]:
    exact_existing = {
        (int(item["signal_ts"]), str(item["symbol"]), str(item["direction"])): str(item["candidate_id"])
        for item in existing
    }
    opposite_existing = {
        (int(item["signal_ts"]), str(item["symbol"]), str(item["direction"])): str(item["candidate_id"])
        for item in existing
    }
    same: list[dict[str, Any]] = []
    opposite: list[dict[str, Any]] = []
    for item in legacy:
        key = (int(item["signal_ts"]), str(item["symbol"]), str(item["direction"]))
        other = exact_existing.get(key)
        if other and other != item["candidate_id"]:
            same.append({"legacy_factor": item["candidate_id"], "existing_factor": other, "signal_ts": key[0], "symbol": key[1]})
        reverse = "short" if key[2] == "long" else "long"
        other = opposite_existing.get((key[0], key[1], reverse))
        if other and other != item["candidate_id"]:
            opposite.append({"legacy_factor": item["candidate_id"], "existing_factor": other, "signal_ts": key[0], "symbol": key[1]})
    return {
        "same_direction_exact_overlap_count": len(same),
        "opposite_direction_exact_overlap_count": len(opposite),
        "same_direction_exact_overlaps": same,
        "opposite_direction_exact_overlaps": opposite,
    }


def factor_decisions(
    raw: list[dict[str, Any]], compatible: list[dict[str, Any]], retained: list[dict[str, Any]], exact: dict[str, Any]
) -> list[dict[str, Any]]:
    raw_counts = Counter(str(item["candidate_id"]) for item in raw)
    compatible_counts = Counter(str(item["candidate_id"]) for item in compatible)
    retained_counts = Counter(str(item["candidate_id"]) for item in retained)
    overlap_counts = Counter(str(item["legacy_factor"]) for item in exact["same_direction_exact_overlaps"])
    decisions: list[dict[str, Any]] = []
    for factor in LEGACY_FACTOR_VALIDITY_DAYS:
        retained_count = retained_counts[factor]
        duplicate_share = overlap_counts[factor] / retained_count if retained_count else 0.0
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
                "source_role": LEGACY_FACTOR_ROLE,
                "raw_signal_count": raw_counts[factor],
                "declared_regime_compatible_signal_count": compatible_counts[factor],
                "fixed_window_signal_count": retained_count,
                "same_direction_exact_overlap_count": overlap_counts[factor],
                "exact_duplicate_share": round(duplicate_share, 6),
                "preflight_status": status,
                "allowed_as_standalone": False,
                "authorized_for_combo_backtest": False,
            }
        )
    return decisions


def build_report(
    ledger: dict[str, Any], registry: dict[str, Any], data_dir: Path
) -> dict[str, Any]:
    start_ts = parse_utc(f"{ledger['prospective_start']} 00:00:00")
    cutoff_ts = parse_utc(str(ledger["common_data_cutoff"]))
    symbols = sorted(
        {symbol for item in registry.get("frozen_candidates", []) for symbol in item.get("eligible_symbols", [])}
    )
    raw: list[dict[str, Any]] = []
    for symbol in symbols:
        raw.extend(generate_symbol_signals(symbol, data_dir, start_ts, cutoff_ts))
    raw.sort(key=lambda item: (int(item["signal_ts"]), str(item["candidate_id"]), str(item["symbol"])))
    compatible = [item for item in raw if item["declared_regime_compatible"] is True]
    retained, suppressed = deduplicate_signals(compatible, LEGACY_FACTOR_VALIDITY_DAYS)
    existing = list(ledger.get("signals", []))
    exact = exact_overlap_summary(retained, existing)
    combined_validity = {**SIGNAL_VALIDITY_DAYS, **LEGACY_FACTOR_VALIDITY_DAYS}
    combined_retained, _ = deduplicate_signals(existing + retained, combined_validity)
    cross_interactions = [
        item
        for item in signal_pairs_within_window(combined_retained)
        if any(part in LEGACY_FACTOR_VALIDITY_DAYS for part in str(item["pair_key"]).split("__"))
        and any(part in SIGNAL_VALIDITY_DAYS for part in str(item["pair_key"]).split("__"))
    ]
    decisions = factor_decisions(raw, compatible, retained, exact)
    return {
        "report_type": "prospective_legacy_weak_factor_preflight",
        "report_date": "2026-07-14",
        "scope": "signal_only_rejected_strategy_reuse_preflight_no_outcome_evaluation",
        "prospective_start": ledger.get("prospective_start"),
        "common_data_cutoff": ledger.get("common_data_cutoff"),
        "source_factor_count": len(LEGACY_FACTOR_VALIDITY_DAYS),
        "source_role": LEGACY_FACTOR_ROLE,
        "fixed_signal_definitions": {
            "donchian_atr_trend_baseline": "completed daily close outside prior 20-day channel",
            "daily_bb_mean_revert": "completed daily close below BB(20, 2) lower band; long",
            "daily_rsi_mean_revert": "completed daily RSI(14) below 35; long",
            "daily_trend_pullback": "EMA50 above EMA200 and completed daily close below EMA20; long",
            "4h_ema_crossover": "completed 4h EMA20/EMA50 cross; bidirectional",
        },
        "fixed_validity_days": dict(LEGACY_FACTOR_VALIDITY_DAYS),
        "raw_signal_count": len(raw),
        "declared_regime_compatible_raw_signal_count": len(compatible),
        "declared_regime_incompatible_raw_signal_count": len(raw) - len(compatible),
        "fixed_window_signal_count": len(retained),
        "suppressed_repeat_count": len(suppressed),
        "compatible_signal_counts_by_factor": dict(Counter(str(item["candidate_id"]) for item in retained)),
        "factor_preflight_decisions": decisions,
        "exact_existing_overlap": exact,
        "existing_factor_interactions_within_24h": {
            "total": len(cross_interactions),
            "same_direction": sum(item["relationship"] == "same_direction_consensus" for item in cross_interactions),
            "opposite_direction": sum(item["relationship"] == "opposite_direction_conflict" for item in cross_interactions),
            "observations": cross_interactions,
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
    interactions = report["existing_factor_interactions_within_24h"]
    lines = [
        "# Prospective Legacy Weak-Factor Preflight",
        "",
        "Date: 2026-07-14",
        "",
        "Rejected standalone strategies are evaluated only as reusable weak-signal triggers.",
        "",
        f"- common data cutoff: `{report['common_data_cutoff']}`",
        f"- source weak factors: {report['source_factor_count']}",
        f"- raw signals: {report['raw_signal_count']}",
        f"- declared-regime-compatible raw signals: {report['declared_regime_compatible_raw_signal_count']}",
        f"- fixed-window signals: {report['fixed_window_signal_count']}",
        f"- suppressed repeats: {report['suppressed_repeat_count']}",
        f"- interactions with existing factors within 24h: {interactions['total']}",
        "",
        "## Factor Decisions",
        "",
        "| Factor | Raw | Regime-compatible | Fixed-window | Exact overlap | Status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["factor_preflight_decisions"]:
        lines.append(
            f"| `{item['factor_id']}` | {item['raw_signal_count']} | "
            f"{item['declared_regime_compatible_signal_count']} | {item['fixed_window_signal_count']} | "
            f"{item['same_direction_exact_overlap_count']} | `{item['preflight_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Standalone approval remains forbidden.",
            "- `forward_prices_evaluated = false`",
            "- `outcomes_evaluated = false`",
            "- `registry_changed = false`",
            "- `safe_to_enable_trading = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight reusable rejected strategies as prospective weak factors.")
    parser.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    parser.add_argument("--registry", type=Path, default=Path("reports/prospective_candidate_registry.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_legacy_weak_factor_preflight.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/prospective_legacy_weak_factor_preflight_2026-07-14.md"))
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
        f"raw={report['raw_signal_count']}; fixed={report['fixed_window_signal_count']}; "
        f"interactions={report['existing_factor_interactions_within_24h']['total']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

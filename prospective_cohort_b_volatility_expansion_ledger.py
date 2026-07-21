"""Signal-only staging ledger for the activated Cohort B volatility-expansion rule."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daily_volatility_expansion_continuation_audit import ATR_PERIOD, EXPANSION_MULTIPLE, HIGH_VOL_TRANSITION, true_range
from market import Bar, load_quantify_15m_csv, resample_minutes
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS, common_cutoff
from regime_component_walk_forward_audit import DAY_MS, wilder_atr
from regime_validation import label_completed_4h_bars, regime_at_entry

RULE_ID = "daily_volatility_expansion_continuation_v1"
RULE_VERSION = "frozen_2026-07-14"
ALLOWED_FIELDS = {"cohort_id", "candidate_id", "rule_version", "signal_ts", "signal_timestamp_utc", "symbol", "direction", "regime", "trigger_metrics", "observation_only"}


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def signals_for_symbol(symbol: str, bars: list[Bar], not_before_ts: int, cutoff_ts: int, cohort_id: str) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels = label_completed_4h_bars(bars)
    atr = wilder_atr(daily, ATR_PERIOD)
    signals: list[dict[str, Any]] = []
    for index in range(ATR_PERIOD + 1, len(daily)):
        bar, previous = daily[index], daily[index - 1]
        signal_ts = bar.ts + DAY_MS
        if not not_before_ts <= signal_ts <= cutoff_ts or atr[index - 1] is None:
            continue
        daily_range = bar.high - bar.low
        if daily_range <= 0:
            continue
        ratio = true_range(bar, previous.close) / float(atr[index - 1])
        close_location = (bar.close - bar.low) / daily_range
        direction = "long" if close_location >= 0.75 else "short" if close_location <= 0.25 else None
        if ratio < EXPANSION_MULTIPLE or direction is None:
            continue
        regime = regime_at_entry(labels, signal_ts)
        if regime != HIGH_VOL_TRANSITION:
            continue
        signals.append({"cohort_id": cohort_id, "candidate_id": RULE_ID, "rule_version": RULE_VERSION,
                        "signal_ts": signal_ts, "signal_timestamp_utc": format_utc(signal_ts), "symbol": symbol,
                        "direction": direction, "regime": regime,
                        "trigger_metrics": {"true_range_to_prior_atr": round(ratio, 6), "close_location": round(close_location, 6)},
                        "observation_only": True})
    return signals


def validate(signals: list[dict[str, Any]], not_before_ts: int) -> None:
    forbidden = {"entry_price", "exit_price", "pnl", "return", "position", "order"}
    for signal in signals:
        if set(signal) != ALLOWED_FIELDS or forbidden & set(signal):
            raise ValueError("signal schema violation")
        if signal["candidate_id"] != RULE_ID or int(signal["signal_ts"]) < not_before_ts:
            raise ValueError("candidate identity or activation-boundary violation")


def build(data_dir: Path, activation: dict, symbols: list[str]) -> dict[str, Any]:
    record = next(item for item in activation["activation_records"] if item["candidate_id"] == RULE_ID)
    not_before_ts = int(record["not_before_signal_ts"])
    cutoff = common_cutoff(data_dir, symbols)
    signals: list[dict[str, Any]] = []
    if cutoff >= not_before_ts:
        for symbol in symbols:
            signals.extend(signals_for_symbol(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"), not_before_ts, cutoff, activation["cohort_id"]))
    signals.sort(key=lambda signal: (signal["signal_ts"], signal["symbol"]))
    validate(signals, not_before_ts)
    return {"report_type": "prospective_cohort_b_volatility_expansion_staging_ledger", "cohort_id": activation["cohort_id"],
            "scope": "signal_only_not_merged_not_committed", "common_data_cutoff": format_utc(cutoff) if cutoff else None,
            "not_before_signal_utc": record["not_before_signal_utc"], "coverage_status": "active" if cutoff >= not_before_ts else "awaiting_data_coverage",
            "generator_available": True, "signal_count": len(signals), "signals": signals,
            "outcomes_evaluated": False, "positions_opened": False,
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_cohort_b_volatility_expansion_staging_ledger.json"))
    args = parser.parse_args()
    activation = json.loads(Path("reports/cohort_b_candidate_activation_registry.json").read_text(encoding="utf-8"))
    report = build(args.data, activation, DEFAULT_SYMBOLS)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"coverage={report['coverage_status']}; signals={report['signal_count']}; merged=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

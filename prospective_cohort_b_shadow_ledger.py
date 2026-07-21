"""Append-safe, signal-only ledger for the admitted Cohort B RSI rule."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daily_rsi_mean_revert_audit import ENTRY_RSI, RSI_PERIOD, rsi_values
from market import Bar, load_quantify_15m_csv, resample_minutes
from prospective_cohort_b_admission import COHORT_ID, COHORT_START_UTC
from regime_component_walk_forward_audit import DAY_MS, parse_day
from regime_validation import label_completed_4h_bars, regime_at_entry


RULE_ID = "daily_rsi_downtrend_rebound_v1"
DEFAULT_SYMBOLS = ["AAVE-USDT-SWAP", "ADA-USDT-SWAP", "APT-USDT-SWAP", "ARB-USDT-SWAP", "ATOM-USDT-SWAP", "AVAX-USDT-SWAP", "BNB-USDT-SWAP", "BTC-USDT-SWAP", "CRV-USDT-SWAP", "DOGE-USDT-SWAP", "DOT-USDT-SWAP", "DYDX-USDT-SWAP", "ETH-USDT-SWAP", "FIL-USDT-SWAP", "IMX-USDT-SWAP", "INJ-USDT-SWAP", "LINK-USDT-SWAP", "LTC-USDT-SWAP", "NEAR-USDT-SWAP", "OP-USDT-SWAP", "RENDER-USDT-SWAP", "SOL-USDT-SWAP", "STX-USDT-SWAP", "SUI-USDT-SWAP", "TIA-USDT-SWAP", "TRX-USDT-SWAP", "UNI-USDT-SWAP", "XRP-USDT-SWAP"]
ALLOWED_SIGNAL_FIELDS = {"cohort_id", "candidate_id", "rule_version", "signal_ts", "signal_timestamp_utc", "symbol", "direction", "regime", "trigger_metrics", "observation_only"}


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def common_cutoff(data_dir: Path, symbols: list[str]) -> int:
    latest: list[int] = []
    for symbol in symbols:
        bars = load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv")
        if not bars:
            return 0
        latest.append(max(bar.ts for bar in bars))
    return min(latest) if latest else 0


def rsi_downtrend_signals(symbol: str, bars: list[Bar], start_ts: int, cutoff_ts: int) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels = label_completed_4h_bars(bars)
    rsi = rsi_values([bar.close for bar in daily])
    signals: list[dict[str, Any]] = []
    for index in range(RSI_PERIOD, len(daily)):
        value = rsi[index]
        signal_ts = daily[index].ts + DAY_MS
        if value is None or value >= ENTRY_RSI or not start_ts <= signal_ts <= cutoff_ts:
            continue
        regime = regime_at_entry(labels, signal_ts)
        if regime != "趋势下行":
            continue
        signals.append({"cohort_id": COHORT_ID, "candidate_id": RULE_ID, "rule_version": "frozen_2026-07-14",
                        "signal_ts": signal_ts, "signal_timestamp_utc": format_utc(signal_ts), "symbol": symbol,
                        "direction": "long", "regime": regime, "trigger_metrics": {"rsi14": round(float(value), 6)},
                        "observation_only": True})
    return signals


def validate(signals: list[dict[str, Any]], start_ts: int) -> None:
    forbidden = {"entry_price", "exit_price", "pnl", "return", "position", "order"}
    for signal in signals:
        if set(signal) != ALLOWED_SIGNAL_FIELDS or forbidden & set(signal):
            raise ValueError("Cohort B signal schema violation")
        if signal["cohort_id"] != COHORT_ID or signal["candidate_id"] != RULE_ID or int(signal["signal_ts"]) < start_ts:
            raise ValueError("Cohort B identity or no-backfill violation")


def build_ledger(data_dir: Path, symbols: list[str]) -> dict[str, Any]:
    start_ts = parse_day(COHORT_START_UTC[:10])
    cutoff = common_cutoff(data_dir, symbols)
    signals: list[dict[str, Any]] = []
    if cutoff >= start_ts:
        for symbol in symbols:
            signals.extend(rsi_downtrend_signals(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"), start_ts, cutoff))
    signals.sort(key=lambda item: (int(item["signal_ts"]), str(item["symbol"])))
    validate(signals, start_ts)
    return {"report_type": "prospective_cohort_b_shadow_ledger", "cohort_id": COHORT_ID,
            "scope": "signal_only_no_outcome_or_execution_evaluation", "cohort_start_utc": COHORT_START_UTC,
            "common_data_cutoff": format_utc(cutoff) if cutoff else None,
            "coverage_status": "active" if cutoff >= start_ts else "awaiting_data_coverage",
            "evaluated_rule_ids": [RULE_ID], "signal_count": len(signals), "signals": signals,
            "outcomes_evaluated": False, "positions_opened": False,
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_cohort_b_shadow_ledger.json"))
    args = parser.parse_args()
    report = build_ledger(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"coverage={report['coverage_status']}; signals={report['signal_count']}; outcomes_evaluated=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

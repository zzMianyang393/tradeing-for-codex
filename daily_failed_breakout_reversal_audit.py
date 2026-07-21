"""Frozen historical audit for the Cohort B failed-breakout reversal card."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daily_volatility_expansion_continuation_audit import HIGH_VOL_TRANSITION, OOS_END, split, summarize, verdict
from market import Bar, load_quantify_15m_csv, resample_minutes
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from regime_component_walk_forward_audit import DAY_MS, ROUND_TRIP_COST, first_index_at_or_after, wilder_atr
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry

RULE_ID = "daily_failed_breakout_reversal_v1"
CHANNEL_DAYS = 20
BREAKOUT_ATR = 0.25
WICK_MINIMUM = 0.40
STOP_ATR = 1.5
MAX_HORIZON_MS = 5 * DAY_MS


def short_event(symbol: str, signal_ts: int, bars: list[Bar], atr: float, regime: str) -> dict[str, Any] | None:
    entry_index = first_index_at_or_after(bars, signal_ts)
    if entry_index is None or atr <= 0 or bars[entry_index].open <= 0:
        return None
    exit_index = first_index_at_or_after(bars, bars[entry_index].ts + MAX_HORIZON_MS)
    if exit_index is None or bars[exit_index].ts > OOS_END or exit_index <= entry_index:
        return None
    entry = bars[entry_index]
    stop = entry.open + STOP_ATR * atr
    actual_exit, exit_price, exit_reason = exit_index, bars[exit_index].open, "time"
    for index in range(entry_index, exit_index + 1):
        if bars[index].high >= stop:
            actual_exit, exit_price, exit_reason = index, stop, "stop"
            break
    exit_bar = bars[actual_exit]
    gross = entry.open / exit_price - 1.0
    return {
        "symbol": symbol, "component_id": RULE_ID, "direction": "short", "signal_ts": signal_ts,
        "signal_timestamp_utc": datetime.fromtimestamp(signal_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "entry_ts": entry.ts, "entry_timestamp_utc": entry.time, "exit_ts": exit_bar.ts, "exit_timestamp_utc": exit_bar.time,
        "entry_price": round(entry.open, 10), "exit_price": round(exit_price, 10), "stop_price": round(stop, 10),
        "exit_reason": exit_reason, "gross_return_pct": round(gross * 100.0, 6),
        "net_return_pct": round((gross - ROUND_TRIP_COST) * 100.0, 6), "entry_regime": regime,
    }


def signal_candidates(symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels = label_completed_4h_bars(bars)
    atr = wilder_atr(daily, 20)
    events: list[dict[str, Any]] = []
    next_allowed_ts = 0
    for index in range(CHANNEL_DAYS, len(daily) - 6):
        bar = daily[index]
        signal_ts = bar.ts + DAY_MS
        if signal_ts < next_allowed_ts or split(signal_ts) is None or atr[index - 1] is None:
            continue
        prior_channel_high = max(item.high for item in daily[index - CHANNEL_DAYS:index])
        daily_range = bar.high - bar.low
        upper_wick = (bar.high - max(bar.open, bar.close)) / daily_range if daily_range > 0 else 0.0
        if bar.high < prior_channel_high + BREAKOUT_ATR * float(atr[index - 1]) or bar.close >= prior_channel_high or upper_wick < WICK_MINIMUM:
            continue
        regime = regime_at_entry(labels, signal_ts)
        event = short_event(symbol, signal_ts + FOUR_HOURS_MS, bars, float(atr[index - 1]), regime)
        if event is None:
            continue
        event["split"] = split(signal_ts)
        event["regime_compatible"] = regime == HIGH_VOL_TRANSITION
        event["trigger_metrics"] = {"prior_channel_high": round(prior_channel_high, 8), "upper_wick_fraction": round(upper_wick, 6)}
        events.append(event)
        next_allowed_ts = event["exit_ts"] + 900_000
    return events


def build(data_dir: Path, symbols: list[str]) -> dict[str, Any]:
    events = [event for symbol in symbols for event in signal_candidates(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"))]
    events.sort(key=lambda event: (event["signal_ts"], event["symbol"]))
    compatible = [event for event in events if event["regime_compatible"]]
    all_stats = {name: summarize([event for event in events if event["split"] == name]) for name in ("formation", "oos")}
    compatible_stats = {name: summarize([event for event in compatible if event["split"] == name]) for name in ("formation", "oos")}
    status, reasons = verdict(compatible_stats["formation"], compatible_stats["oos"])
    return {
        "report_type": "daily_failed_breakout_reversal_audit", "rule_id": RULE_ID,
        "parameters": {"channel_days": CHANNEL_DAYS, "breakout_atr": BREAKOUT_ATR, "upper_wick_minimum": WICK_MINIMUM, "stop_atr": STOP_ATR, "entry_delay_hours": 4, "max_horizon_days": 5, "friction_pct": 0.16},
        "formation": {"all_signals": all_stats["formation"], "regime_compatible": compatible_stats["formation"]},
        "oos": {"all_signals": all_stats["oos"], "regime_compatible": compatible_stats["oos"]},
        "events": events, "status": status, "reasons": reasons,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_failed_breakout_reversal_audit.json"))
    args = parser.parse_args()
    report = build(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['regime_compatible']['events']}; oos={report['oos']['regime_compatible']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Non-backfilled signal-only observation for a post-hoc short-side hypothesis."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daily_volatility_expansion_continuation_audit import ATR_PERIOD, EXPANSION_MULTIPLE, HIGH_VOL_TRANSITION, true_range
from market import Bar, _format_utc, _parse_timestamp, load_quantify_15m_csv, resample_minutes
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from regime_component_walk_forward_audit import DAY_MS, wilder_atr
from regime_validation import label_completed_4h_bars, regime_at_entry

COHORT_ID = "prospective_cohort_c_2026-07-15"
HYPOTHESIS_ID = "daily_volatility_expansion_short_exploration_v1"
RULE_VERSION = "frozen_2026-07-15"
ACTIVATION_TS = 1784160000000  # 2026-07-16 00:00 UTC, strictly after the observed cutoff.
DEFAULT_REGISTRY_OUT = Path("reports/prospective_cohort_c_exploration_registry.json")
DEFAULT_STAGING_OUT = Path("reports/staging_cohort_c/prospective_cohort_c_short_exploration_ledger.json")
ALLOWED_FIELDS = {"cohort_id", "hypothesis_id", "rule_version", "signal_ts", "signal_timestamp_utc", "symbol", "direction", "regime", "trigger_metrics", "observation_only"}


class _Aggregate:
    def __init__(self, ts: int, time: str, open_value: float, high: float, low: float, close: float, bucket: str) -> None:
        self.bucket = bucket
        self.ts = ts
        self.time = time
        self.open = open_value
        self.high = high
        self.low = low
        self.close = close

    def append(self, high: float, low: float, close: float) -> None:
        self.high = max(self.high, high)
        self.low = min(self.low, low)
        self.close = close

    def bar(self) -> Bar:
        return Bar(self.ts, self.time, self.open, self.high, self.low, self.close, 0.0)


def _feature_label(state: dict[str, float], bar: Bar) -> str:
    previous_close = state.get("previous_close", bar.close)
    state["ema20"] = bar.close if state.get("ema20", 0.0) == 0.0 else state["ema20"] + 2.0 / 21.0 * (bar.close - state["ema20"])
    state["ema50"] = bar.close if state.get("ema50", 0.0) == 0.0 else state["ema50"] + 2.0 / 51.0 * (bar.close - state["ema50"])
    state["ema200"] = bar.close if state.get("ema200", 0.0) == 0.0 else state["ema200"] + 2.0 / 201.0 * (bar.close - state["ema200"])
    true_range_value = max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))
    state["atr"] = true_range_value if "atr" not in state else (state["atr"] * 13.0 + true_range_value) / 14.0
    state["previous_close"] = bar.close
    atr = state["atr"]
    trend_strength = (state["ema20"] - state["ema200"]) / (atr if atr else bar.close * 0.01)
    if state["ema20"] > state["ema50"] > state["ema200"] and trend_strength >= 1.0:
        return "趋势上行"
    if state["ema20"] < state["ema50"] < state["ema200"] and trend_strength <= -1.0:
        return "趋势下行"
    return HIGH_VOL_TRANSITION if atr / bar.close >= 0.03 else "震荡"


def signals_for_path(symbol: str, path: Path, cutoff_ts: int) -> list[dict[str, Any]]:
    """Stream long 15m archives while preserving the frozen daily/4h calculations."""
    signals: list[dict[str, Any]] = []
    four_hour: _Aggregate | None = None
    daily: _Aggregate | None = None
    four_hour_state: dict[str, float] = {}
    latest_label: tuple[int, str] | None = None
    daily_index = -1
    daily_atr: float | None = None
    daily_true_ranges: list[float] = []
    previous_daily_close: float | None = None

    def close_four_hour(aggregate: _Aggregate) -> None:
        nonlocal latest_label
        bar = aggregate.bar()
        latest_label = (bar.ts + 4 * 60 * 60 * 1000, _feature_label(four_hour_state, bar))

    def close_daily(aggregate: _Aggregate) -> None:
        nonlocal daily_index, daily_atr, previous_daily_close
        bar = aggregate.bar()
        daily_index += 1
        prior_atr = daily_atr
        prior_close = previous_daily_close if previous_daily_close is not None else bar.close
        true_range_value = max(bar.high - bar.low, abs(bar.high - prior_close), abs(bar.low - prior_close))
        if daily_index < ATR_PERIOD:
            daily_true_ranges.append(true_range_value)
            if daily_index == ATR_PERIOD - 1:
                daily_atr = sum(daily_true_ranges) / ATR_PERIOD
        else:
            daily_atr = (float(daily_atr) * (ATR_PERIOD - 1) + true_range_value) / ATR_PERIOD
        signal_ts = bar.ts + DAY_MS
        daily_range = bar.high - bar.low
        label = latest_label[1] if latest_label and latest_label[0] <= signal_ts else "样本不足"
        if (daily_index >= ATR_PERIOD + 1 and ACTIVATION_TS <= signal_ts <= cutoff_ts and prior_atr is not None
                and daily_range > 0 and label == HIGH_VOL_TRANSITION):
            ratio = true_range_value / prior_atr
            close_location = (bar.close - bar.low) / daily_range
            if ratio >= EXPANSION_MULTIPLE and close_location <= 0.25:
                signals.append({"cohort_id": COHORT_ID, "hypothesis_id": HYPOTHESIS_ID, "rule_version": RULE_VERSION,
                                "signal_ts": signal_ts, "signal_timestamp_utc": utc(signal_ts), "symbol": symbol, "direction": "short",
                                "regime": HIGH_VOL_TRANSITION, "trigger_metrics": {"true_range_to_prior_atr": round(ratio, 6), "close_location": round(close_location, 6)},
                                "observation_only": True})
        previous_daily_close = bar.close

    with path.open("r", encoding="utf-8") as handle:
        next(handle, None)
        for raw_line in handle:
            try:
                timestamp, open_text, high_text, low_text, close_text, *_ = raw_line.rstrip().split(",")
                open_value, high, low, close = float(open_text), float(high_text), float(low_text), float(close_text)
            except ValueError:
                continue
            day = timestamp[:10]
            four_hour_bucket, daily_bucket = f"{day}:{int(timestamp[11:13]) // 4}", day
            ts: int | None = None

            def timestamp_ms() -> int:
                nonlocal ts
                if ts is None:
                    ts = _parse_timestamp(timestamp)
                return ts

            if four_hour is None:
                four_hour = _Aggregate(timestamp_ms(), timestamp, open_value, high, low, close, four_hour_bucket)
            elif four_hour.bucket != four_hour_bucket:
                close_four_hour(four_hour)
                four_hour = _Aggregate(timestamp_ms(), timestamp, open_value, high, low, close, four_hour_bucket)
            else:
                four_hour.append(high, low, close)
            if daily is None:
                daily = _Aggregate(timestamp_ms(), timestamp, open_value, high, low, close, daily_bucket)
            elif daily.bucket != daily_bucket:
                close_daily(daily)
                daily = _Aggregate(timestamp_ms(), timestamp, open_value, high, low, close, daily_bucket)
            else:
                daily.append(high, low, close)
    return signals


def utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def latest_timestamp(path: Path) -> int:
    """Read only a CSV tail when finding the common cutoff for the full universe."""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - 4096))
        lines = [line for line in handle.read().decode("utf-8").splitlines() if line]
    if not lines:
        return 0
    timestamp = lines[-1].split(",", 1)[0]
    return int(datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def common_cutoff(data_dir: Path, symbols: list[str]) -> int:
    latest = []
    for symbol in symbols:
        path = data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"
        if not path.exists():
            return 0
        timestamp = latest_timestamp(path)
        if not timestamp:
            return 0
        latest.append(timestamp)
    return min(latest) if latest else 0


def registry() -> dict[str, Any]:
    return {"registry_type": "prospective_cohort_c_exploration_registry", "cohort_id": COHORT_ID,
            "hypothesis_id": HYPOTHESIS_ID, "rule_version": RULE_VERSION,
            "activation_not_before_ts": ACTIVATION_TS, "activation_not_before_utc": utc(ACTIVATION_TS),
            "origin": "post_hoc_direction_asymmetry_observation_not_historical_approval",
            "frozen_signal": {"daily_true_range_at_least_prior_atr_multiple": EXPANSION_MULTIPLE,
                              "atr_period": ATR_PERIOD, "daily_close_location_at_most": 0.25,
                              "completed_regime": HIGH_VOL_TRANSITION, "direction": "short"},
            "non_backfill": True, "outcomes_evaluated": False, "positions_opened": False,
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def signals_for_symbol(symbol: str, bars: list[Bar], cutoff_ts: int) -> list[dict[str, Any]]:
    daily, labels = resample_minutes(bars, 1440), label_completed_4h_bars(bars)
    atr = wilder_atr(daily, ATR_PERIOD)
    signals: list[dict[str, Any]] = []
    for index in range(ATR_PERIOD + 1, len(daily)):
        bar, previous = daily[index], daily[index - 1]
        signal_ts = bar.ts + DAY_MS
        if not ACTIVATION_TS <= signal_ts <= cutoff_ts or atr[index - 1] is None:
            continue
        daily_range = bar.high - bar.low
        if daily_range <= 0:
            continue
        ratio = true_range(bar, previous.close) / float(atr[index - 1])
        close_location = (bar.close - bar.low) / daily_range
        if ratio < EXPANSION_MULTIPLE or close_location > 0.25 or regime_at_entry(labels, signal_ts) != HIGH_VOL_TRANSITION:
            continue
        signals.append({"cohort_id": COHORT_ID, "hypothesis_id": HYPOTHESIS_ID, "rule_version": RULE_VERSION,
                        "signal_ts": signal_ts, "signal_timestamp_utc": utc(signal_ts), "symbol": symbol, "direction": "short",
                        "regime": HIGH_VOL_TRANSITION, "trigger_metrics": {"true_range_to_prior_atr": round(ratio, 6), "close_location": round(close_location, 6)},
                        "observation_only": True})
    return signals


def validate(signals: list[dict[str, Any]]) -> None:
    forbidden = {"entry_price", "exit_price", "pnl", "return", "position", "order", "outcome"}
    for signal in signals:
        if set(signal) != ALLOWED_FIELDS or set(signal) & forbidden:
            raise ValueError("signal schema violation")
        if signal["hypothesis_id"] != HYPOTHESIS_ID or signal["direction"] != "short" or signal["signal_ts"] < ACTIVATION_TS:
            raise ValueError("identity, direction, or activation violation")


def build(data_dir: Path, symbols: list[str]) -> dict[str, Any]:
    cutoff = common_cutoff(data_dir, symbols)
    signals = [] if cutoff < ACTIVATION_TS else [signal for symbol in symbols for signal in signals_for_path(symbol, data_dir / f"{symbol.split('-', 1)[0]}_15m.csv", cutoff)]
    signals.sort(key=lambda signal: (signal["signal_ts"], signal["symbol"]))
    validate(signals)
    return {"report_type": "prospective_cohort_c_short_exploration_staging_ledger", "cohort_id": COHORT_ID, "hypothesis_id": HYPOTHESIS_ID,
            "scope": "post_hoc_hypothesis_future_signal_only_not_merged_not_committed", "activation_not_before_utc": utc(ACTIVATION_TS),
            "common_data_cutoff": utc(cutoff) if cutoff else None, "coverage_status": "active" if cutoff >= ACTIVATION_TS else "awaiting_data_coverage",
            "signal_count": len(signals), "signals": signals, "outcomes_evaluated": False, "positions_opened": False,
            "safety_gates": registry()["safety_gates"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--registry-out", type=Path, default=DEFAULT_REGISTRY_OUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_STAGING_OUT)
    args = parser.parse_args()
    args.registry_out.parent.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.registry_out.write_text(json.dumps(registry(), ensure_ascii=False, indent=2), encoding="utf-8")
    report = build(args.data, DEFAULT_SYMBOLS)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"coverage={report['coverage_status']}; signals={report['signal_count']}; outcomes=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

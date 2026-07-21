"""Frozen, regime-conditioned audit for daily KDJ oversold reversions."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from market import Bar, load_quantify_15m_csv, resample_minutes
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from regime_component_walk_forward_audit import DAY_MS, parse_day, trade_event, wilder_atr
from regime_validation import FOUR_HOURS_MS, label_completed_4h_bars, regime_at_entry


RULE_ID = "daily_kdj_range_reversion_v1"
LOOKBACK = 9
SMOOTHING = 3
OVERSOLD_K = 20.0
OVERBOUGHT_K = 80.0
OOS_END = parse_day("2025-07-10", end=True)


def split(ts: int) -> str | None:
    if parse_day("2024-01-01") <= ts <= parse_day("2024-12-31", end=True):
        return "formation"
    if parse_day("2025-01-01") <= ts <= OOS_END:
        return "oos"
    return None


def kdj_values(bars: list[Bar]) -> tuple[list[float | None], list[float | None]]:
    """Return completed-bar K/D values using no prices after each bar."""
    k_values: list[float | None] = [None] * len(bars)
    d_values: list[float | None] = [None] * len(bars)
    k, d = 50.0, 50.0
    for index in range(LOOKBACK - 1, len(bars)):
        window = bars[index - LOOKBACK + 1:index + 1]
        highest, lowest = max(bar.high for bar in window), min(bar.low for bar in window)
        rsv = 50.0 if highest == lowest else 100.0 * (bars[index].close - lowest) / (highest - lowest)
        k = ((SMOOTHING - 1) * k + rsv) / SMOOTHING
        d = ((SMOOTHING - 1) * d + k) / SMOOTHING
        k_values[index], d_values[index] = k, d
    return k_values, d_values


def events_for_symbol(symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
    daily = resample_minutes(bars, 1440)
    labels, atr = label_completed_4h_bars(bars), wilder_atr(daily, 14)
    k_values, d_values = kdj_values(daily)
    events: list[dict[str, Any]] = []
    next_allowed = 0
    for index in range(max(14, LOOKBACK), len(daily) - 8):
        signal_ts = daily[index].ts + DAY_MS
        k_now, d_now = k_values[index], d_values[index]
        k_prior, d_prior = k_values[index - 1], d_values[index - 1]
        if (
            signal_ts < next_allowed
            or split(signal_ts) is None
            or atr[index - 1] is None
            or None in (k_now, d_now, k_prior, d_prior)
            or regime_at_entry(labels, signal_ts) != "震荡"
            or not (k_prior <= d_prior and k_now > d_now and k_now < OVERSOLD_K)
        ):
            continue
        exit_ts = next(
            (
                daily[j].ts + DAY_MS
                for j in range(index + 1, min(index + 8, len(daily)))
                if k_values[j] is not None and k_values[j] >= OVERBOUGHT_K
            ),
            None,
        )
        event = trade_event(
            symbol, RULE_ID, "long", signal_ts + FOUR_HOURS_MS, bars, float(atr[index - 1]),
            exit_ts, 7 * DAY_MS, OOS_END, "震荡",
        )
        if event is not None:
            event["split"] = split(signal_ts)
            event["k"] = round(float(k_now), 6)
            event["d"] = round(float(d_now), 6)
            events.append(event)
            next_allowed = event["exit_ts"] + 900_000
    return events


def summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(event["net_return_pct"]) for event in events]
    positive_by_month: dict[str, float] = defaultdict(float)
    for event in events:
        if event["net_return_pct"] > 0:
            month = datetime.fromtimestamp(event["signal_ts"] / 1000, tz=timezone.utc).strftime("%Y-%m")
            positive_by_month[month] += float(event["net_return_pct"])
    positive_total = sum(positive_by_month.values())
    return {
        "events": len(events),
        "net_sum_pct": round(sum(values), 6),
        "mean_pct": round(mean(values), 6) if values else 0.0,
        "win_rate": round(sum(value > 0 for value in values) / len(values), 6) if values else 0.0,
        "positive_return_month_concentration": round(max(positive_by_month.values()) / positive_total, 6) if positive_total else 0.0,
    }


def verdict(formation: dict[str, Any], oos: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    insufficient = False
    for name, stats in (("formation", formation), ("oos", oos)):
        if stats["events"] < 15:
            reasons.append(f"{name} events {stats['events']} < 15")
            insufficient = True
        if stats["mean_pct"] <= 0:
            reasons.append(f"{name} mean <= 0")
        if stats["positive_return_month_concentration"] > 0.25:
            reasons.append(f"{name} month concentration {stats['positive_return_month_concentration']:.1%} > 25%")
    if insufficient:
        return "insufficient_evidence", reasons
    return ("historical_rejected" if reasons else "historical_research_candidate"), reasons


def build(data_dir: Path, symbols: list[str]) -> dict[str, Any]:
    events = [
        event
        for symbol in symbols
        for event in events_for_symbol(symbol, load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"))
    ]
    events.sort(key=lambda event: (event["signal_ts"], event["symbol"]))
    formation = summary([event for event in events if event["split"] == "formation"])
    oos = summary([event for event in events if event["split"] == "oos"])
    status, reasons = verdict(formation, oos)
    return {
        "report_type": "daily_kdj_range_reversion_audit",
        "rule_id": RULE_ID,
        "parameters": {
            "lookback": LOOKBACK,
            "smoothing": SMOOTHING,
            "oversold_k": OVERSOLD_K,
            "overbought_k_exit": OVERBOUGHT_K,
            "entry_delay_hours": 4,
            "stop_atr_multiple": 2.0,
            "max_horizon_days": 7,
            "friction_pct": 0.16,
        },
        "formation": formation,
        "oos": oos,
        "events": events,
        "status": status,
        "reasons": reasons,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/daily_kdj_range_reversion_audit.json"))
    args = parser.parse_args()
    report = build(args.data, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"formation={report['formation']['events']}; oos={report['oos']['events']}; status={report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

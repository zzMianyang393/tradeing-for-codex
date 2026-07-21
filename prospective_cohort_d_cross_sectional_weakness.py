"""Future-only metadata observations for a post-hoc cross-sectional short hypothesis."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market import Bar, load_quantify_15m_csv, resample_minutes
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from regime_component_walk_forward_audit import DAY_MS


COHORT_ID = "prospective_cohort_d_2026-07-16"
HYPOTHESIS_ID = "weekly_cross_sectional_weakness_short_exploration_v1"
RULE_VERSION = "frozen_2026-07-16"
ACTIVATION_TS = 1784505600000  # 2026-07-20 00:00 UTC, after the observed cutoff.
LOOKBACK_DAYS = 28
SELECTION_COUNT = 3
DEFAULT_REGISTRY_OUT = Path("reports/prospective_cohort_d_exploration_registry.json")
DEFAULT_STAGING_OUT = Path("reports/staging_cohort_d/prospective_cohort_d_cross_sectional_weakness_ledger.json")
ALLOWED_FIELDS = {
    "cohort_id", "hypothesis_id", "rule_version", "signal_ts", "signal_timestamp_utc",
    "symbol", "direction", "regime", "trigger_metrics", "observation_only",
}


def utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def is_monday_utc(ts: int) -> bool:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).weekday() == 0


def latest_timestamp(path: Path) -> int:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        handle.seek(max(0, handle.tell() - 4096))
        lines = [line for line in handle.read().decode("utf-8").splitlines() if line]
    if not lines:
        return 0
    value = lines[-1].split(",", 1)[0]
    return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def common_cutoff(data_dir: Path, symbols: list[str]) -> int:
    timestamps = []
    for symbol in symbols:
        path = data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"
        if not path.exists():
            return 0
        timestamp = latest_timestamp(path)
        if not timestamp:
            return 0
        timestamps.append(timestamp)
    return min(timestamps) if timestamps else 0


def signals_from_daily(daily_by_symbol: dict[str, list[Bar]], cutoff_ts: int) -> list[dict[str, Any]]:
    """Rank completed 28-day returns only at future Monday UTC boundaries."""
    if not daily_by_symbol:
        return []
    by_symbol_ts = {symbol: {bar.ts: bar for bar in bars} for symbol, bars in daily_by_symbol.items()}
    reference = next(iter(daily_by_symbol.values()))
    signals: list[dict[str, Any]] = []
    for bar in reference:
        signal_ts = bar.ts + DAY_MS
        if not ACTIVATION_TS <= signal_ts <= cutoff_ts or not is_monday_utc(signal_ts):
            continue
        completed_ts, prior_ts = signal_ts - DAY_MS, signal_ts - DAY_MS - LOOKBACK_DAYS * DAY_MS
        scores: dict[str, float] = {}
        for symbol, index in by_symbol_ts.items():
            current, prior = index.get(completed_ts), index.get(prior_ts)
            if current is None or prior is None or prior.close <= 0:
                break
            scores[symbol] = current.close / prior.close - 1.0
        if len(scores) != len(daily_by_symbol):
            continue
        ranked = sorted(scores, key=lambda symbol: (scores[symbol], symbol))[:SELECTION_COUNT]
        for rank, symbol in enumerate(ranked, start=1):
            signals.append({
                "cohort_id": COHORT_ID, "hypothesis_id": HYPOTHESIS_ID, "rule_version": RULE_VERSION,
                "signal_ts": signal_ts, "signal_timestamp_utc": utc(signal_ts), "symbol": symbol,
                "direction": "short", "regime": "weekly_cross_sectional_rank",
                "trigger_metrics": {"lookback_days": LOOKBACK_DAYS, "selection_count": SELECTION_COUNT,
                                    "weakness_rank": rank, "ranking_return_28d": round(scores[symbol], 8)},
                "observation_only": True,
            })
    signals.sort(key=lambda row: (row["signal_ts"], row["symbol"]))
    return signals


def registry() -> dict[str, Any]:
    return {
        "registry_type": "prospective_cohort_d_exploration_registry", "cohort_id": COHORT_ID,
        "hypothesis_id": HYPOTHESIS_ID, "rule_version": RULE_VERSION,
        "activation_not_before_ts": ACTIVATION_TS, "activation_not_before_utc": utc(ACTIVATION_TS),
        "origin": "post_hoc_rejected_long_short_portfolio_short_sleeve_not_historical_approval",
        "frozen_signal": {"completed_return_lookback_days": LOOKBACK_DAYS, "rebalance": "Monday 00:00 UTC",
                           "select": "weakest three", "direction": "short", "metadata_only": True},
        "non_backfill": True, "outcomes_evaluated": False, "positions_opened": False,
        "safety_gates": safety_gates(),
    }


def safety_gates() -> dict[str, Any]:
    return {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False}


def validate(signals: list[dict[str, Any]]) -> None:
    forbidden = {"entry_price", "exit_price", "pnl", "return", "position", "order", "outcome"}
    for signal in signals:
        if set(signal) != ALLOWED_FIELDS or set(signal) & forbidden:
            raise ValueError("signal schema violation")
        if (signal["cohort_id"] != COHORT_ID or signal["hypothesis_id"] != HYPOTHESIS_ID
                or signal["direction"] != "short" or signal["signal_ts"] < ACTIVATION_TS):
            raise ValueError("identity, direction, or activation violation")


def build(data_dir: Path, symbols: list[str] = DEFAULT_SYMBOLS) -> dict[str, Any]:
    cutoff = common_cutoff(data_dir, symbols)
    daily_by_symbol = {} if cutoff < ACTIVATION_TS else {
        symbol: resample_minutes(load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv"), 1440)
        for symbol in symbols
    }
    signals = signals_from_daily(daily_by_symbol, cutoff)
    validate(signals)
    return {
        "report_type": "prospective_cohort_d_cross_sectional_weakness_staging_ledger", "cohort_id": COHORT_ID,
        "hypothesis_id": HYPOTHESIS_ID, "scope": "post_hoc_hypothesis_future_signal_only_not_merged_not_committed",
        "activation_not_before_utc": utc(ACTIVATION_TS), "common_data_cutoff": utc(cutoff) if cutoff else None,
        "coverage_status": "active" if cutoff >= ACTIVATION_TS else "awaiting_data_coverage", "signal_count": len(signals),
        "signals": signals, "outcomes_evaluated": False, "positions_opened": False, "safety_gates": safety_gates(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--registry-out", type=Path, default=DEFAULT_REGISTRY_OUT)
    parser.add_argument("--out", type=Path, default=DEFAULT_STAGING_OUT)
    args = parser.parse_args()
    args.registry_out.parent.mkdir(parents=True, exist_ok=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.registry_out.write_text(json.dumps(registry(), ensure_ascii=False, indent=2), encoding="utf-8")
    report = build(args.data)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"coverage={report['coverage_status']}; signals={report['signal_count']}; outcomes=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Return-free same-day overlap audit for two future Cohort B weak signals."""
from __future__ import annotations

import json
import argparse
from pathlib import Path

from daily_volume_shock_reversal_preflight import inventory_symbol
from daily_volatility_expansion_continuation_audit import OOS_END
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS
from regime_component_walk_forward_audit import DAY_MS, parse_day
from regime_validation import FOUR_HOURS_MS
from market import load_quantify_15m_csv

VOLUME_SHOCK_SHORT = "daily_volume_shock_reversal_v1_short"
VOLATILITY_EXPANSION = "daily_volatility_expansion_continuation_v1"


def decision_key(symbol: str, signal_ts: int) -> tuple[str, int]:
    return symbol, signal_ts


def build(data_dir: Path, volatility_report: dict, symbols: list[str]) -> dict:
    selected_symbols = set(symbols)
    expansion = [event for event in volatility_report["events"] if event["regime_compatible"] and event["symbol"] in selected_symbols]
    expansion_by_key = {
        decision_key(event["symbol"], int(event["signal_ts"]) - FOUR_HOURS_MS): event
        for event in expansion
    }
    volume_short = []
    for symbol in symbols:
        bars = load_quantify_15m_csv(data_dir / f"{symbol.split('-', 1)[0]}_15m.csv")
        volume_short.extend(event for event in inventory_symbol(symbol, bars, parse_day("2024-01-01"), OOS_END)
                            if event["direction"] == "short")
    volume_by_key = {decision_key(event["symbol"], int(event["signal_ts"])): event for event in volume_short}
    shared_keys = sorted(set(expansion_by_key) & set(volume_by_key))
    overlap = [
        {"symbol": symbol, "decision_ts": ts, "expansion_direction": expansion_by_key[(symbol, ts)]["direction"],
         "volume_shock_direction": volume_by_key[(symbol, ts)]["direction"],
         "same_direction": expansion_by_key[(symbol, ts)]["direction"] == "short"}
        for symbol, ts in shared_keys
    ]
    smaller = min(len(expansion_by_key), len(volume_by_key))
    overlap_rate = len(overlap) / smaller if smaller else 0.0
    return {
        "report_type": "volatility_expansion_volume_shock_overlap_audit", "observation_only": True,
        "scope": "same_symbol_same_completed_daily_signal_only_no_returns",
        "expansion_compatible_event_count": len(expansion_by_key), "volume_shock_short_event_count": len(volume_by_key),
        "same_day_same_symbol_overlap_count": len(overlap), "overlap_rate_of_smaller_set": round(overlap_rate, 6),
        "same_direction_overlap_count": sum(item["same_direction"] for item in overlap), "overlap_events": overlap,
        "conclusion": "no_same_day_overlap_observed" if not overlap else "overlap_penalty_required_before_any_combo_research",
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--out", type=Path, default=Path("reports/volatility_expansion_volume_shock_overlap_audit.json"))
    args = parser.parse_args()
    audit = json.loads(Path("reports/daily_volatility_expansion_continuation_audit.json").read_text(encoding="utf-8"))
    report = build(Path("data"), audit, args.symbols)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"expansion={report['expansion_compatible_event_count']}; volume_short={report['volume_shock_short_event_count']}; overlap={report['same_day_same_symbol_overlap_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

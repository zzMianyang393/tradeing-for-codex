"""Pre-registered signal-state arbitration without prices, exits, or outcomes."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DAY_MS = 24 * 60 * 60 * 1000
SIGNAL_VALIDITY_DAYS = {
    "low_volatility_drift_bb_breakout_fixed_risk_v1": 3,
    "ema_continuation_short_downtrend_v1": 5,
    "persistent_uptrend_ema20_reclaim_v1": 10,
    "daily_volume_shock_reversal_v1_short": 3,
    "weekly_cross_sectional_momentum_v1_short": 7,
    "weekly_range_microtrend_continuation_v1_long": 3,
    "donchian_atr_trend_baseline": 10,
}
UPTREND_TREND_SLEEVE = frozenset(
    {
        "donchian_atr_trend_baseline",
        "persistent_uptrend_ema20_reclaim_v1",
    }
)
ARBITRATION_STATES = {
    "independent_observation",
    "same_direction_consensus_no_leverage_addition",
    "opposite_direction_conflict_lockout",
}


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def deduplicate_signals(
    signals: list[dict[str, Any]], validity_days: dict[str, int] | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validity = validity_days or SIGNAL_VALIDITY_DAYS
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        grouped[(str(signal["candidate_id"]), str(signal["symbol"]))].append(signal)
    retained: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    for (candidate_id, symbol), items in sorted(grouped.items()):
        valid_until = -1
        source_ts = -1
        for signal in sorted(items, key=lambda item: int(item["signal_ts"])):
            signal_ts = int(signal["signal_ts"])
            if signal_ts < valid_until:
                suppressed.append(
                    {
                        "candidate_id": candidate_id,
                        "symbol": symbol,
                        "signal_ts": signal_ts,
                        "signal_timestamp_utc": format_utc(signal_ts),
                        "suppressed_by_signal_ts": source_ts,
                        "reason": "same_component_symbol_fixed_validity_window_active",
                    }
                )
                continue
            retained.append(dict(signal))
            source_ts = signal_ts
            valid_until = signal_ts + int(validity[candidate_id]) * DAY_MS
    retained.sort(key=lambda item: (int(item["signal_ts"]), str(item["symbol"]), str(item["candidate_id"])))
    suppressed.sort(key=lambda item: (int(item["signal_ts"]), str(item["symbol"]), str(item["candidate_id"])))
    return retained, suppressed


def arbitration_state(active: list[dict[str, Any]]) -> tuple[str, str | None]:
    directions = {str(item["direction"]) for item in active}
    components = {str(item["candidate_id"]) for item in active}
    if len(directions) > 1:
        return "opposite_direction_conflict_lockout", None
    direction = next(iter(directions)) if directions else None
    if len(components) > 1:
        return "same_direction_consensus_no_leverage_addition", direction
    return "independent_observation", direction


def uptrend_sleeve_validity(
    active: dict[str, dict[str, Any]], candidate_id: str, signal_ts: int, validity: dict[str, int]
) -> tuple[int, int, bool]:
    """Keep the two uptrend components inside one non-extending observation window."""
    default_until = signal_ts + int(validity[candidate_id]) * DAY_MS
    if candidate_id not in UPTREND_TREND_SLEEVE:
        return default_until, signal_ts, False
    paired = [item for component, item in active.items() if component in UPTREND_TREND_SLEEVE]
    if not paired:
        return default_until, signal_ts, False
    primary = min(paired, key=lambda item: (int(item["source_signal_ts"]), str(item["candidate_id"])))
    return int(primary["valid_until_ts"]), int(primary["source_signal_ts"]), True


def build_arbitration_snapshots(
    signals: list[dict[str, Any]], validity_days: dict[str, int] | None = None
) -> list[dict[str, Any]]:
    validity = validity_days or SIGNAL_VALIDITY_DAYS
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        grouped[(int(signal["signal_ts"]), str(signal["symbol"]))].append(signal)
    active_by_symbol: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    snapshots: list[dict[str, Any]] = []
    for (signal_ts, symbol), arrivals in sorted(grouped.items()):
        active = active_by_symbol[symbol]
        expired = [candidate for candidate, item in active.items() if int(item["valid_until_ts"]) <= signal_ts]
        for candidate in expired:
            del active[candidate]
        for signal in sorted(arrivals, key=lambda item: str(item["candidate_id"])):
            candidate_id = str(signal["candidate_id"])
            valid_until_ts, sleeve_start_ts, joined_existing_sleeve = uptrend_sleeve_validity(
                active, candidate_id, signal_ts, validity
            )
            active[candidate_id] = {
                "candidate_id": candidate_id,
                "direction": str(signal["direction"]),
                "source_signal_ts": signal_ts,
                "valid_until_ts": valid_until_ts,
                "uptrend_sleeve_start_ts": sleeve_start_ts if candidate_id in UPTREND_TREND_SLEEVE else None,
                "joined_existing_uptrend_sleeve": joined_existing_sleeve,
            }
        active_items = sorted(active.values(), key=lambda item: str(item["candidate_id"]))
        state, resolved_direction = arbitration_state(active_items)
        sleeve_items = [item for item in active_items if item["candidate_id"] in UPTREND_TREND_SLEEVE]
        sleeve_start_ts = min((int(item["uptrend_sleeve_start_ts"]) for item in sleeve_items), default=None)
        snapshots.append(
            {
                "snapshot_ts": signal_ts,
                "snapshot_timestamp_utc": format_utc(signal_ts),
                "symbol": symbol,
                "arriving_components": sorted(str(item["candidate_id"]) for item in arrivals),
                "active_components": [str(item["candidate_id"]) for item in active_items],
                "active_directions": sorted({str(item["direction"]) for item in active_items}),
                "arbitration_state": state,
                "resolved_direction": resolved_direction,
                "notional_vote_cap": 0 if state == "opposite_direction_conflict_lockout" else 1,
                "uptrend_trend_sleeve_active": bool(sleeve_items),
                "uptrend_trend_sleeve_components": [str(item["candidate_id"]) for item in sleeve_items],
                "uptrend_trend_sleeve_start_ts": sleeve_start_ts,
                "uptrend_trend_sleeve_start_timestamp_utc": format_utc(sleeve_start_ts) if sleeve_start_ts is not None else None,
                "observation_only": True,
            }
        )
    return snapshots


def build_report(ledger: dict[str, Any]) -> dict[str, Any]:
    raw_signals = list(ledger.get("signals", []))
    retained, suppressed = deduplicate_signals(raw_signals)
    snapshots = build_arbitration_snapshots(retained)
    state_counts = Counter(str(item["arbitration_state"]) for item in snapshots)
    conflict_symbols = sorted(
        {str(item["symbol"]) for item in snapshots if item["arbitration_state"] == "opposite_direction_conflict_lockout"}
    )
    consensus_symbols = sorted(
        {
            str(item["symbol"])
            for item in snapshots
            if item["arbitration_state"] == "same_direction_consensus_no_leverage_addition"
        }
    )
    return {
        "report_type": "prospective_signal_conflict_arbitration",
        "report_date": "2026-07-14",
        "scope": "pre_registered_signal_state_only_no_price_outcome_or_execution_evaluation",
        "prospective_start": ledger.get("prospective_start"),
        "common_data_cutoff": ledger.get("common_data_cutoff"),
        "frozen_signal_validity_days": dict(SIGNAL_VALIDITY_DAYS),
        "frozen_arbitration_rules": [
            "Suppress repeated same-component same-symbol triggers while its fixed validity window remains active.",
            "Opposite active directions on one symbol create a conflict lockout with zero notional votes.",
            "Two or more same-direction components create one capped consensus vote; leverage is never added.",
            "One active component creates one independent observation vote.",
            "On one symbol, Donchian trend baseline and EMA20 reclaim share one 10-day uptrend trend-sleeve window.",
            "A later signal from the other uptrend component records co-activation but never extends that sleeve window or adds a vote.",
        ],
        "raw_signal_count": len(raw_signals),
        "deduplicated_signal_count": len(retained),
        "suppressed_repeat_count": len(suppressed),
        "suppressed_repeat_signals": suppressed,
        "arbitration_snapshot_count": len(snapshots),
        "arbitration_state_counts": {state: state_counts.get(state, 0) for state in sorted(ARBITRATION_STATES)},
        "conflict_symbols": conflict_symbols,
        "consensus_symbols": consensus_symbols,
        "snapshots": snapshots,
        "interpretation_limits": [
            "Validity windows are frozen maximum-hold proxies and do not inspect actual exits.",
            "Arbitration states are observations, not orders, positions, or backtest events.",
            "No state can authorize paper or live trading.",
        ],
        "prices_evaluated": False,
        "outcomes_evaluated": False,
        "exits_evaluated": False,
        "forward_returns_evaluated": False,
        "positions_opened": False,
        "orders_created": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["arbitration_state_counts"]
    lines = [
        "# Prospective Signal Conflict Arbitration",
        "",
        "Date: 2026-07-14",
        "",
        "Pre-registered signal-state arbitration. No prices, exits, outcomes, positions, or orders were evaluated.",
        "",
        f"- common data cutoff: `{report['common_data_cutoff']}`",
        f"- raw signals: {report['raw_signal_count']}",
        f"- deduplicated signals: {report['deduplicated_signal_count']}",
        f"- suppressed repeats: {report['suppressed_repeat_count']}",
        f"- arbitration snapshots: {report['arbitration_snapshot_count']}",
        f"- independent observations: {counts['independent_observation']}",
        f"- capped same-direction consensus: {counts['same_direction_consensus_no_leverage_addition']}",
        f"- opposite-direction lockouts: {counts['opposite_direction_conflict_lockout']}",
        "",
        "## Frozen Rules",
        "",
    ]
    lines.extend(f"- {rule}" for rule in report["frozen_arbitration_rules"])
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- `prices_evaluated = false`",
            "- `outcomes_evaluated = false`",
            "- `exits_evaluated = false`",
            "- `positions_opened = false`",
            "- `orders_created = false`",
            "- `safe_to_enable_trading = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arbitrate prospective signal states without outcomes.")
    parser.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_signal_conflict_arbitration.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/prospective_signal_conflict_arbitration_2026-07-14.md"))
    args = parser.parse_args(argv)
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    report = build_report(ledger)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"raw={report['raw_signal_count']}; deduplicated={report['deduplicated_signal_count']}; "
        f"suppressed={report['suppressed_repeat_count']}; states={report['arbitration_state_counts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

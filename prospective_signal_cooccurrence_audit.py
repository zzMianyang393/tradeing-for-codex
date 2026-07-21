"""Audit co-occurrence among sealed prospective weak-factor signals.

This is a structural diagnostic for future combo research.  It never derives
outcomes or creates a combined signal: it only counts exact same-symbol,
same-timestamp factor co-occurrences in the sealed Cohort A ledger.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

from factor_regime_compatibility_matrix import (
    CANDIDATE_TO_FACTOR,
    REGIME_VOCABULARY_VERSION,
    normalize_regime,
)


SAFETY_GATES = {
    "approved_for_paper": [],
    "eligible_for_paper": False,
    "safe_to_enable_trading": False,
    "ready_for_combo_backtest": False,
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compact_signal(signal: dict[str, Any]) -> dict[str, Any] | None:
    """Keep only fields required to measure structural co-occurrence."""
    candidate_id = signal.get("candidate_id")
    factor_id = CANDIDATE_TO_FACTOR.get(candidate_id)
    if not factor_id:
        return None
    return {
        "candidate_id": candidate_id,
        "factor_id": factor_id,
        "signal_ts": signal.get("signal_ts"),
        "signal_timestamp_utc": signal.get("signal_timestamp_utc"),
        "symbol": signal.get("symbol"),
        "direction": signal.get("direction"),
        "normalized_regime": normalize_regime(str(signal.get("regime", ""))),
    }


def audit(ledger: dict[str, Any]) -> dict[str, Any]:
    signals = ledger.get("signals", [])
    known: list[dict[str, Any]] = []
    unknown_candidate_count = 0
    for signal in signals:
        compact = compact_signal(signal)
        if compact is None:
            unknown_candidate_count += 1
        else:
            known.append(compact)

    by_event: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for signal in known:
        by_event[(signal["signal_ts"], signal["symbol"])].append(signal)

    multi_factor_events = []
    pairs: list[dict[str, Any]] = []
    for (signal_ts, symbol), event_signals in sorted(by_event.items()):
        factors = sorted({signal["factor_id"] for signal in event_signals})
        if len(factors) < 2:
            continue
        multi_factor_events.append({
            "signal_ts": signal_ts,
            "signal_timestamp_utc": event_signals[0]["signal_timestamp_utc"],
            "symbol": symbol,
            "factor_ids": factors,
            "directions": sorted({str(signal["direction"]) for signal in event_signals}),
            "normalized_regimes": sorted({signal["normalized_regime"] for signal in event_signals}),
        })
        by_factor = {signal["factor_id"]: signal for signal in event_signals}
        for factor_a, factor_b in combinations(factors, 2):
            left, right = by_factor[factor_a], by_factor[factor_b]
            directions_match = left["direction"] == right["direction"]
            regimes_match = left["normalized_regime"] == right["normalized_regime"]
            pairs.append({
                "factor_a": factor_a,
                "factor_b": factor_b,
                "signal_ts": signal_ts,
                "signal_timestamp_utc": left["signal_timestamp_utc"],
                "symbol": symbol,
                "direction_relation": "same" if directions_match else "opposite",
                "regime_relation": "same" if regimes_match else "different_or_unknown",
            })

    pair_summary: dict[str, dict[str, Any]] = {}
    for pair in pairs:
        pair_id = f"{pair['factor_a']}|{pair['factor_b']}"
        summary = pair_summary.setdefault(pair_id, {
            "factor_a": pair["factor_a"],
            "factor_b": pair["factor_b"],
            "cooccurrence_count": 0,
            "same_direction_count": 0,
            "opposite_direction_count": 0,
            "same_regime_count": 0,
        })
        summary["cooccurrence_count"] += 1
        summary[f"{pair['direction_relation']}_direction_count"] += 1
        if pair["regime_relation"] == "same":
            summary["same_regime_count"] += 1

    factor_counts = Counter(signal["factor_id"] for signal in known)
    signals_in_multi_factor_events = sum(
        len(by_event[(event["signal_ts"], event["symbol"])]) for event in multi_factor_events
    )
    signal_count = len(signals)
    return {
        "audit_type": "prospective_signal_cooccurrence",
        "observation_only": True,
        "common_data_cutoff": ledger.get("common_data_cutoff"),
        "regime_vocabulary_version": REGIME_VOCABULARY_VERSION,
        "ledger_signal_count": ledger.get("signal_count"),
        "observed_signal_count": signal_count,
        "signal_count_match": signal_count == ledger.get("signal_count"),
        "known_factor_signal_count": len(known),
        "unknown_candidate_count": unknown_candidate_count,
        "per_factor_signal_count": dict(sorted(factor_counts.items())),
        "multi_factor_event_count": len(multi_factor_events),
        "signals_in_multi_factor_events": signals_in_multi_factor_events,
        "signal_cooccurrence_rate": round(signals_in_multi_factor_events / signal_count, 6) if signal_count else 0.0,
        "pair_observation_count": len(pairs),
        "pair_summary": list(pair_summary.values()),
        "multi_factor_events": multi_factor_events,
        "pair_observations": pairs,
        "safety_gates": SAFETY_GATES,
        "methodology_notes": [
            "Exact co-occurrence means same symbol and same signal timestamp.",
            "This report is structural only; it does not create a combined signal or calculate outcomes.",
            "Unknown candidate ids are counted and excluded from pair calculations.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit sealed factor signal co-occurrence.")
    parser.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_signal_cooccurrence_audit.json"))
    args = parser.parse_args(argv)
    report = audit(load_json(args.ledger))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"signals={report['observed_signal_count']}; multi_factor_events={report['multi_factor_event_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

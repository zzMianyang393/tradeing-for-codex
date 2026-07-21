"""Signal-metadata-only interaction audit for prospective weak components."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any


DAY_MS = 24 * 60 * 60 * 1000
DERIVED_PREFIXES = ("combo::", "pair_watchlist::")


def utc_day(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def component_pair(candidate_id: str) -> tuple[str, str] | None:
    prefix = next((item for item in DERIVED_PREFIXES if candidate_id.startswith(item)), None)
    if prefix is None:
        return None
    parts = candidate_id.removeprefix(prefix).split("__")
    return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else None


def pair_key(left: str, right: str) -> str:
    return "__".join(sorted((left, right)))


def signal_pairs_within_window(
    signals: list[dict[str, Any]], window_ms: int = DAY_MS
) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        by_symbol[str(signal["symbol"])].append(signal)
    overlaps: list[dict[str, Any]] = []
    for symbol, items in by_symbol.items():
        ordered = sorted(items, key=lambda item: (int(item["signal_ts"]), str(item["candidate_id"])))
        for left, right in combinations(ordered, 2):
            if left["candidate_id"] == right["candidate_id"]:
                continue
            distance = abs(int(right["signal_ts"]) - int(left["signal_ts"]))
            if distance > window_ms:
                continue
            same_direction = str(left["direction"]) == str(right["direction"])
            overlaps.append(
                {
                    "pair_key": pair_key(str(left["candidate_id"]), str(right["candidate_id"])),
                    "symbol": symbol,
                    "left_signal_ts": int(left["signal_ts"]),
                    "right_signal_ts": int(right["signal_ts"]),
                    "distance_hours": round(distance / (60 * 60 * 1000), 4),
                    "relationship": "same_direction_consensus" if same_direction else "opposite_direction_conflict",
                }
            )
    return sorted(overlaps, key=lambda item: (item["left_signal_ts"], item["right_signal_ts"], item["symbol"]))


def candidate_active_days(signals: list[dict[str, Any]]) -> dict[str, set[str]]:
    active: dict[str, set[str]] = defaultdict(set)
    for signal in signals:
        active[str(signal["candidate_id"])].add(utc_day(int(signal["signal_ts"])))
    return active


def build_pair_observations(
    registry: dict[str, Any], signals: list[dict[str, Any]], overlaps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    active_days = candidate_active_days(signals)
    overlap_counts = Counter(str(item["pair_key"]) for item in overlaps)
    consensus_counts = Counter(
        str(item["pair_key"]) for item in overlaps if item["relationship"] == "same_direction_consensus"
    )
    conflict_counts = Counter(
        str(item["pair_key"]) for item in overlaps if item["relationship"] == "opposite_direction_conflict"
    )
    observations: list[dict[str, Any]] = []
    registered = list(registry.get("watchlist", []))
    for item in registered:
        candidate_id = str(item.get("candidate_id", ""))
        pair = component_pair(candidate_id)
        if pair is None:
            continue
        left, right = pair
        key = pair_key(left, right)
        shared_days = sorted(active_days.get(left, set()) & active_days.get(right, set()))
        observations.append(
            {
                "registry_id": candidate_id,
                "left_component": left,
                "right_component": right,
                "left_signal_count": sum(str(signal["candidate_id"]) == left for signal in signals),
                "right_signal_count": sum(str(signal["candidate_id"]) == right for signal in signals),
                "shared_active_utc_days": shared_days,
                "shared_active_day_count": len(shared_days),
                "same_symbol_overlaps_within_24h": overlap_counts[key],
                "same_direction_consensus": consensus_counts[key],
                "opposite_direction_conflicts": conflict_counts[key],
                "observation_status": "interaction_observed" if shared_days or overlap_counts[key] else "no_interaction_yet",
                "authorized_for_backtest": False,
            }
        )
    return observations


def build_emergent_pair_observations(
    registry: dict[str, Any], overlaps: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    registered_keys = {
        pair_key(*pair)
        for item in registry.get("watchlist", [])
        if (pair := component_pair(str(item.get("candidate_id", "")))) is not None
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in overlaps:
        grouped[str(item["pair_key"])].append(item)
    emergent: list[dict[str, Any]] = []
    for key, items in sorted(grouped.items()):
        if key in registered_keys:
            continue
        consensus = sum(item["relationship"] == "same_direction_consensus" for item in items)
        conflicts = sum(item["relationship"] == "opposite_direction_conflict" for item in items)
        emergent.append(
            {
                "pair_key": key,
                "same_symbol_overlaps_within_24h": len(items),
                "same_direction_consensus": consensus,
                "opposite_direction_conflicts": conflicts,
                "symbols": sorted({str(item["symbol"]) for item in items}),
                "observation_class": "conflict_candidate" if conflicts > consensus else "consensus_candidate",
                "registry_changed": False,
                "authorized_for_backtest": False,
            }
        )
    return emergent


def build_report(ledger: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    signals = list(ledger.get("signals", []))
    overlaps = signal_pairs_within_window(signals)
    counts_by_day = Counter(utc_day(int(signal["signal_ts"])) for signal in signals)
    counts_by_direction = Counter(str(signal["direction"]) for signal in signals)
    counts_by_regime = Counter(str(signal["regime"]) for signal in signals)
    counts_by_symbol = Counter(str(signal["symbol"]) for signal in signals)
    evaluated = list(ledger.get("evaluated_rule_ids", []))
    active_candidates = sorted({str(signal["candidate_id"]) for signal in signals})
    pair_observations = build_pair_observations(registry, signals, overlaps)
    emergent_pairs = build_emergent_pair_observations(registry, overlaps)
    return {
        "report_type": "prospective_signal_interaction_audit",
        "report_date": "2026-07-14",
        "scope": "signal_metadata_only_no_price_outcome_or_execution_evaluation",
        "prospective_start": ledger.get("prospective_start"),
        "common_data_cutoff": ledger.get("common_data_cutoff"),
        "raw_signal_count": len(signals),
        "active_candidate_count": len(active_candidates),
        "inactive_candidate_count": len(set(evaluated) - set(active_candidates)),
        "active_candidates": active_candidates,
        "inactive_candidates": sorted(set(evaluated) - set(active_candidates)),
        "signal_counts_by_utc_day": dict(sorted(counts_by_day.items())),
        "signal_counts_by_direction": dict(sorted(counts_by_direction.items())),
        "signal_counts_by_regime": dict(sorted(counts_by_regime.items())),
        "top_symbols_by_signal_count": [
            {"symbol": symbol, "signal_count": count} for symbol, count in counts_by_symbol.most_common(10)
        ],
        "same_symbol_interactions_within_24h": {
            "total": len(overlaps),
            "same_direction_consensus": sum(item["relationship"] == "same_direction_consensus" for item in overlaps),
            "opposite_direction_conflicts": sum(item["relationship"] == "opposite_direction_conflict" for item in overlaps),
            "observations": overlaps,
        },
        "registered_pair_observations": pair_observations,
        "emergent_pair_observations": emergent_pairs,
        "interpretation_limits": [
            "Co-activation is not evidence of profitability or diversification.",
            "Raw triggers do not apply cooldown, capacity, exits, or position state.",
            "The current observation window is too short for pair promotion or rejection.",
        ],
        "prices_evaluated": False,
        "outcomes_evaluated": False,
        "exits_evaluated": False,
        "forward_returns_evaluated": False,
        "positions_opened": False,
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    interactions = report["same_symbol_interactions_within_24h"]
    lines = [
        "# Prospective Signal Interaction Audit",
        "",
        "Date: 2026-07-14",
        "",
        "Signal metadata only. No prices, exits, positions, or outcomes were evaluated.",
        "",
        f"- data cutoff: `{report['common_data_cutoff']}`",
        f"- raw signals: {report['raw_signal_count']}",
        f"- active candidates: {report['active_candidate_count']}",
        f"- inactive candidates: {report['inactive_candidate_count']}",
        f"- same-symbol interactions within 24h: {interactions['total']}",
        f"- same-direction consensus: {interactions['same_direction_consensus']}",
        f"- opposite-direction conflicts: {interactions['opposite_direction_conflicts']}",
        "",
        "## Registered Pairs",
        "",
        "| Pair | Shared days | 24h overlaps | Consensus | Conflicts | Status |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["registered_pair_observations"]:
        lines.append(
            f"| `{item['registry_id']}` | {item['shared_active_day_count']} | "
            f"{item['same_symbol_overlaps_within_24h']} | {item['same_direction_consensus']} | "
            f"{item['opposite_direction_conflicts']} | `{item['observation_status']}` |"
        )
    lines.extend(
        [
            "",
            "## Emergent Interactions",
            "",
            "| Component pair | 24h overlaps | Consensus | Conflicts | Class |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in report["emergent_pair_observations"]:
        lines.append(
            f"| `{item['pair_key']}` | {item['same_symbol_overlaps_within_24h']} | "
            f"{item['same_direction_consensus']} | {item['opposite_direction_conflicts']} | "
            f"`{item['observation_class']}` |"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- Co-activation does not authorize a backtest or trade.",
            "- `prices_evaluated = false`",
            "- `outcomes_evaluated = false`",
            "- `forward_returns_evaluated = false`",
            "- `safe_to_enable_trading = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit prospective signal interactions without outcomes.")
    parser.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    parser.add_argument("--registry", type=Path, default=Path("reports/prospective_candidate_registry.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_signal_interaction_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/prospective_signal_interaction_audit_2026-07-14.md"))
    args = parser.parse_args(argv)
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    report = build_report(ledger, registry)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    interactions = report["same_symbol_interactions_within_24h"]
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"signals={report['raw_signal_count']}; interactions={interactions['total']}; "
        f"consensus={interactions['same_direction_consensus']}; conflicts={interactions['opposite_direction_conflicts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

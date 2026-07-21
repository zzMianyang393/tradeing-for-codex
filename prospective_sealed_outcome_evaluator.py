"""Evaluate only mature, integrity-valid prospective observations under the frozen spec."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any

from market import load_quantify_15m_csv, resample_minutes
import prospective_sealed_evaluation_spec as spec


REPORTS = Path("reports")
FOUR_HOURS_MS = 4 * 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000


def _base_symbol(symbol: str) -> str:
    return symbol.split("-", 1)[0]


def _evaluate_observation(observation: dict[str, Any], bars_by_ts: dict[int, Any]) -> dict[str, Any] | None:
    entry_ts = int(observation["signal_ts"]) + spec.ENTRY_DELAY_HOURS * 60 * 60 * 1000
    exit_ts = entry_ts + spec.OBSERVATION_HORIZON_DAYS * DAY_MS
    entry, exit_bar = bars_by_ts.get(entry_ts), bars_by_ts.get(exit_ts)
    if entry is None or exit_bar is None or entry.open <= 0 or exit_bar.close <= 0:
        return None
    gross = exit_bar.close / entry.open - 1.0 if observation["direction"] == "long" else entry.open / exit_bar.close - 1.0
    return {
        "observation_id": observation["observation_id"],
        "hypothesis_id": observation["hypothesis_id"],
        "signal_ts": observation["signal_ts"],
        "symbol": observation["symbol"],
        "direction": observation["direction"],
        "regime": observation["regime"],
        "net_observation_pct": round((gross - spec.ROUND_TRIP_FRICTION_PCT / 100.0) * 100.0, 6),
    }


def _concentration(rows: list[dict[str, Any]], key: str) -> float | None:
    positives = [row for row in rows if row["net_observation_pct"] > 0]
    total = sum(row["net_observation_pct"] for row in positives)
    if total <= 0:
        return None
    contributions: dict[str, float] = defaultdict(float)
    for row in positives:
        group = spec.utc_day(int(row["signal_ts"])) if key == "signal_day" else str(row[key])
        contributions[group] += row["net_observation_pct"]
    return round(max(contributions.values()) / total, 6)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row["net_observation_pct"] for row in rows]
    return {
        "observation_count": len(rows),
        "mean_net_observation_pct": round(mean(values), 6),
        "median_net_observation_pct": round(median(values), 6),
        "positive_rate": round(sum(value > 0 for value in values) / len(values), 6),
        "max_positive_signal_day_contribution": _concentration(rows, "signal_day"),
        "max_positive_symbol_contribution": _concentration(rows, "symbol"),
    }


def _distribution(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        group = spec.utc_day(int(row["signal_ts"])) if key == "signal_day" else spec.utc_month(int(row["signal_ts"])) if key == "signal_month" else str(row[key])
        grouped[group].append(row["net_observation_pct"])
    return {group: {"count": len(values), "net_observation_pct_sum": round(sum(values), 6)} for group, values in sorted(grouped.items())}


def _group_rows(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return grouped


def build(registry: dict[str, Any], maturity: dict[str, Any], integrity: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    mature_ids = {row["observation_id"] for row in maturity.get("observations", []) if row.get("status") == "mature_awaiting_sealed_evaluation"}
    observations = [row for row in registry.get("observations", []) if row.get("observation_id") in mature_ids]
    as_of_ts = int(maturity.get("as_of_ts", 0))
    readiness = spec.evidence_readiness(observations, as_of_ts)
    base = {
        "report_type": "prospective_sealed_outcome_evaluation",
        "spec_version": spec.EVALUATION_SPEC_VERSION,
        "observation_only": True,
        "mature_observation_count": len(observations),
        "evidence_readiness": readiness,
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }
    if integrity.get("integrity_status") != "valid":
        return {**base, "evaluation_status": "blocked_integrity", "outcomes_evaluated": False, "issues": ["registry_integrity_not_valid"]}
    if not observations:
        return {**base, "evaluation_status": "awaiting_maturity", "outcomes_evaluated": False, "issues": []}
    if not readiness["minimum_evidence_ready"]:
        return {**base, "evaluation_status": "insufficient_independent_evidence", "outcomes_evaluated": False, "issues": []}

    outcomes: list[dict[str, Any]] = []
    missing: list[str] = []
    for symbol in sorted({row["symbol"] for row in observations}):
        path = data_dir / f"{_base_symbol(symbol)}_15m.csv"
        bars_by_ts = {bar.ts: bar for bar in resample_minutes(load_quantify_15m_csv(path), 240)} if path.exists() else {}
        for observation in [row for row in observations if row["symbol"] == symbol]:
            outcome = _evaluate_observation(observation, bars_by_ts)
            if outcome is None:
                missing.append(observation["observation_id"])
            else:
                outcomes.append(outcome)
    if missing:
        return {**base, "evaluation_status": "blocked_missing_market_coverage", "outcomes_evaluated": False, "issues": [f"missing_price_coverage:{item}" for item in missing]}

    return {
        **base,
        "evaluation_status": "sealed_evaluation_completed_no_automatic_approval",
        "outcomes_evaluated": True,
        "issues": [],
        "summary": _summary(outcomes),
        "per_hypothesis": {factor: _summary(rows) for factor, rows in sorted(_group_rows(outcomes, "hypothesis_id").items())},
        "contribution_distribution": {
            "signal_day": _distribution(outcomes, "signal_day"),
            "signal_month": _distribution(outcomes, "signal_month"),
            "symbol": _distribution(outcomes, "symbol"),
            "regime": _distribution(outcomes, "regime"),
            "direction": _distribution(outcomes, "direction"),
        },
        "outcomes": outcomes,
    }


def main() -> int:
    def load(name: str) -> dict[str, Any]:
        return json.loads((REPORTS / name).read_text(encoding="utf-8"))
    report = build(load("prospective_observation_registry.json"), load("prospective_maturity_audit.json"), load("prospective_observation_integrity_audit.json"), Path("data"))
    (REPORTS / "prospective_sealed_outcome_evaluation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"evaluation={report['evaluation_status']}; outcomes={report['outcomes_evaluated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

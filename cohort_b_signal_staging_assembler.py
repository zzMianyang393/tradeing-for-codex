"""Assemble independently generated Cohort B signal-only sources for dry-run review."""
from __future__ import annotations

import json
import argparse
from pathlib import Path

from prospective_cohort_b_shadow_ledger import ALLOWED_SIGNAL_FIELDS

PRIMARY = Path("reports/prospective_cohort_b_shadow_ledger.json")
VOLATILITY = Path("reports/prospective_cohort_b_volatility_expansion_staging_ledger.json")
OUTPUT = Path("reports/prospective_cohort_b_combined_staging_ledger.json")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def identity(signal: dict) -> tuple:
    return tuple(signal[key] for key in ("candidate_id", "rule_version", "signal_ts", "symbol", "direction", "regime"))


def build(sources: list[tuple[str, dict]]) -> dict:
    cohort_ids = {source["cohort_id"] for _, source in sources}
    if len(cohort_ids) != 1:
        raise ValueError("all staging sources must share a Cohort B identity")
    signals, seen = [], set()
    source_status = []
    for name, source in sources:
        source_signals = source.get("signals", [])
        for signal in source_signals:
            if set(signal) != ALLOWED_SIGNAL_FIELDS:
                raise ValueError(f"{name} signal schema mismatch")
            key = identity(signal)
            if key in seen:
                raise ValueError(f"duplicate signal identity across sources: {key}")
            seen.add(key)
            signals.append(signal)
        source_status.append({"source": name, "signal_count": len(source_signals), "common_data_cutoff": source.get("common_data_cutoff"), "coverage_status": source.get("coverage_status")})
    signals.sort(key=lambda signal: (signal["signal_ts"], signal["symbol"], signal["candidate_id"]))
    cutoffs = [item["common_data_cutoff"] for item in source_status if item["common_data_cutoff"]]
    return {"report_type": "prospective_cohort_b_combined_staging_ledger", "cohort_id": cohort_ids.pop(),
            "scope": "signal_only_dry_run_input_not_published", "source_status": source_status,
            "common_data_cutoff": min(cutoffs) if cutoffs else None, "signal_count": len(signals), "signals": signals,
            "outcomes_evaluated": False, "positions_opened": False,
            "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rsi-source", type=Path, default=PRIMARY)
    parser.add_argument("--volatility-source", type=Path, default=VOLATILITY)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = build([("rsi_staging", load(args.rsi_source)), ("volatility_expansion_staging", load(args.volatility_source))])
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"sources={len(report['source_status'])}; signals={report['signal_count']}; published=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

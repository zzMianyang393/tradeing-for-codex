"""Merge return-free overlap audit batches without reconstructing signals."""
from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    reports = [json.loads((Path("reports") / f"volatility_volume_overlap_batch_{index}.json").read_text(encoding="utf-8")) for index in range(1, 5)]
    expansion = sum(report["expansion_compatible_event_count"] for report in reports)
    volume = sum(report["volume_shock_short_event_count"] for report in reports)
    overlap = [event for report in reports for event in report["overlap_events"]]
    result = {
        "report_type": "volatility_expansion_volume_shock_overlap_audit", "observation_only": True,
        "scope": "same_symbol_same_completed_daily_signal_only_no_returns",
        "source_batches": [f"reports/volatility_volume_overlap_batch_{index}.json" for index in range(1, 5)],
        "expansion_compatible_event_count": expansion, "volume_shock_short_event_count": volume,
        "same_day_same_symbol_overlap_count": len(overlap),
        "overlap_rate_of_smaller_set": round(len(overlap) / min(expansion, volume), 6) if expansion and volume else 0.0,
        "same_direction_overlap_count": sum(event["same_direction"] for event in overlap), "overlap_events": overlap,
        "conclusion": "overlap_penalty_required_before_any_combo_research" if overlap else "no_same_day_overlap_observed",
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }
    Path("reports/volatility_expansion_volume_shock_overlap_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"expansion={expansion}; volume_short={volume}; overlap={len(overlap)}")


if __name__ == "__main__":
    main()

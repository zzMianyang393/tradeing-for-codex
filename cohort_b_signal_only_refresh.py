"""Build current Cohort B staging sources and run the append-only pipeline in dry-run only."""
from __future__ import annotations

import json
from pathlib import Path

from cohort_b_refresh_pipeline import run_pipeline
from cohort_b_signal_staging_assembler import build as assemble_staging
from prospective_cohort_b_shadow_ledger import DEFAULT_SYMBOLS, build_ledger as build_rsi_staging
from prospective_cohort_b_volatility_expansion_ledger import build as build_volatility_staging

REPORTS = Path("reports")
ACTIVATION = REPORTS / "cohort_b_candidate_activation_registry.json"
RSI_STAGING = REPORTS / "prospective_cohort_b_rsi_staging_ledger.json"
VOLATILITY_STAGING = REPORTS / "prospective_cohort_b_volatility_expansion_staging_ledger.json"
COMBINED_STAGING = REPORTS / "prospective_cohort_b_combined_staging_ledger.json"
OUTPUT = REPORTS / "cohort_b_signal_only_refresh.json"


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _same_day_fast_forward(reports_dir: Path, cutoff: str) -> dict | None:
    rsi = _load(reports_dir / RSI_STAGING.name)
    volatility = _load(reports_dir / VOLATILITY_STAGING.name)
    if not rsi or not volatility:
        return None
    previous = min(str(rsi.get("common_data_cutoff", "")), str(volatility.get("common_data_cutoff", "")))
    if not previous or cutoff <= previous or cutoff[:10] != previous[:10]:
        return None
    for source in (rsi, volatility):
        source["common_data_cutoff"] = cutoff
    write(reports_dir / RSI_STAGING.name, rsi)
    write(reports_dir / VOLATILITY_STAGING.name, volatility)
    combined = assemble_staging([("rsi_staging", rsi), ("volatility_expansion_staging", volatility)])
    combined["report_type"] = "prospective_cohort_b_combined_staging_ledger"
    combined["scope"] = "signal_only_same_utc_day_cutoff_fast_forward"
    combined["common_data_cutoff"] = cutoff
    combined_path = reports_dir / COMBINED_STAGING.name
    write(combined_path, combined)
    pipeline = run_pipeline(combined_path, commit=False)
    return {"rsi": rsi, "volatility": volatility, "combined": combined, "pipeline": pipeline}


def refresh(data_dir: Path, reports_dir: Path = REPORTS, progress=None, known_common_cutoff: str | None = None) -> dict:
    """Refresh sources and validate them through the pipeline without any publish path."""
    announce = progress or (lambda _message: None)
    activation = json.loads((reports_dir / ACTIVATION.name).read_text(encoding="utf-8"))
    fast = _same_day_fast_forward(reports_dir, known_common_cutoff) if known_common_cutoff else None
    if fast:
        announce("stage=same_day_cutoff_fast_forward")
        rsi, volatility, combined, pipeline = fast["rsi"], fast["volatility"], fast["combined"], fast["pipeline"]
    else:
        announce("stage=rsi_staging")
        rsi = build_rsi_staging(data_dir, DEFAULT_SYMBOLS)
        announce("stage=volatility_expansion_staging")
        volatility = build_volatility_staging(data_dir, activation, DEFAULT_SYMBOLS)
        rsi_path = reports_dir / RSI_STAGING.name
        volatility_path = reports_dir / VOLATILITY_STAGING.name
        combined_path = reports_dir / COMBINED_STAGING.name
        write(rsi_path, rsi)
        write(volatility_path, volatility)
        announce("stage=combined_staging")
        combined = assemble_staging([("rsi_staging", rsi), ("volatility_expansion_staging", volatility)])
        combined["report_type"] = "prospective_cohort_b_combined_staging_ledger"
        combined["scope"] = "signal_only_dry_run_input_not_published"
        write(combined_path, combined)
        announce("stage=append_only_dry_run")
        pipeline = run_pipeline(combined_path, commit=False)
    result = {
        "report_type": "cohort_b_signal_only_refresh", "observation_only": True,
        "mode": "same_day_cutoff_fast_forward" if fast else "dry_run_only", "source_cutoffs": {
            "rsi": rsi.get("common_data_cutoff"), "volatility_expansion": volatility.get("common_data_cutoff"),
            "combined": combined.get("common_data_cutoff"),
        },
        "source_signal_counts": {"rsi": rsi.get("signal_count", 0), "volatility_expansion": volatility.get("signal_count", 0), "combined": combined.get("signal_count", 0)},
        "pipeline_decision": pipeline.get("refresh_decision"), "new_observations": pipeline.get("new_observations"),
        "published": pipeline.get("published"), "append_validation": pipeline.get("append_validation"),
        "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False},
    }
    write(reports_dir / OUTPUT.name, result)
    return result


def main() -> int:
    result = refresh(Path("data"), progress=print)
    print(f"decision={result['pipeline_decision']}; new={result['new_observations']}; published={result['published']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

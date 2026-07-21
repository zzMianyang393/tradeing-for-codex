from pathlib import Path
from unittest.mock import patch

from cohort_b_signal_only_refresh import refresh


def _source(candidate, count=0):
    return {"cohort_id": "b", "common_data_cutoff": "2026-07-15 00:45:00", "signal_count": count, "signals": [], "coverage_status": "active", "candidate": candidate}


def test_refresh_always_calls_pipeline_with_commit_false(tmp_path):
    (tmp_path / "cohort_b_candidate_activation_registry.json").write_text("{}", encoding="utf-8")
    combined = _source("combined", 0)
    with patch("cohort_b_signal_only_refresh.build_rsi_staging", return_value=_source("rsi")), \
         patch("cohort_b_signal_only_refresh.build_volatility_staging", return_value=_source("vol")), \
         patch("cohort_b_signal_only_refresh.assemble_staging", return_value=combined), \
         patch("cohort_b_signal_only_refresh.run_pipeline", return_value={"refresh_decision": "no_changes", "new_observations": 0, "published": False, "append_validation": {"valid": True}}) as pipeline:
        progress = []
        result = refresh(tmp_path, tmp_path, progress=progress.append)
    assert result["mode"] == "dry_run_only"
    assert result["published"] is False
    assert pipeline.call_args.kwargs["commit"] is False
    assert progress == ["stage=rsi_staging", "stage=volatility_expansion_staging", "stage=combined_staging", "stage=append_only_dry_run"]


def test_refresh_source_never_imports_runner():
    source = Path("cohort_b_signal_only_refresh.py").read_text(encoding="utf-8")
    assert "import runner" not in source
    assert "--commit" not in source


def test_same_utc_day_fast_forward_never_rebuilds_signals(tmp_path):
    (tmp_path / "cohort_b_candidate_activation_registry.json").write_text("{}", encoding="utf-8")
    for name in ("prospective_cohort_b_rsi_staging_ledger.json", "prospective_cohort_b_volatility_expansion_staging_ledger.json"):
        (tmp_path / name).write_text(__import__("json").dumps(_source(name)), encoding="utf-8")
    combined = _source("combined", 0)
    with patch("cohort_b_signal_only_refresh.build_rsi_staging") as rsi_build, \
         patch("cohort_b_signal_only_refresh.build_volatility_staging") as volatility_build, \
         patch("cohort_b_signal_only_refresh.assemble_staging", return_value=combined), \
         patch("cohort_b_signal_only_refresh.run_pipeline", return_value={"refresh_decision": "no_changes", "new_observations": 0, "published": False, "append_validation": {"valid": True}}) as pipeline:
        result = refresh(tmp_path, tmp_path, known_common_cutoff="2026-07-15 02:00:00")
    assert result["mode"] == "same_day_cutoff_fast_forward"
    rsi_build.assert_not_called()
    volatility_build.assert_not_called()
    assert pipeline.call_args.kwargs["commit"] is False
    assert result["published"] is False

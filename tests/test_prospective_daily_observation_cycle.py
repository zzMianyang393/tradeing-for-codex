from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from prospective_daily_observation_cycle import compact_data_refresh, main, quality_is_valid, run_cycle


def valid_quality() -> dict:
    return {
        "n_eligible_symbols": 28,
        "n_audited": 28,
        "common_cutoff_utc": "2026-07-15 06:30:00",
        "summary": {"total_gaps": 0, "total_duplicates": 0},
    }


def plan() -> dict:
    return {
        "symbol_count": 1,
        "total_append_count": 1,
        "all_contiguous": True,
        "committed": False,
        "symbols": [{"append_count": 1, "local_last_utc": "a", "new_last_utc": "b"}],
    }


def test_quality_gate_requires_complete_gap_free_duplicate_free_audit():
    assert quality_is_valid(valid_quality()) is True
    bad = valid_quality(); bad["summary"]["total_gaps"] = 1
    assert quality_is_valid(bad) is False
    bad = valid_quality(); bad["n_audited"] = 27
    assert quality_is_valid(bad) is False


def test_compact_data_refresh_excludes_raw_bars_and_market_values():
    report = compact_data_refresh(plan())
    assert report["total_append_count"] == 1
    assert "symbols" not in report
    assert "price" not in report


def test_default_cycle_never_commits_data_and_refreshes_b_c_dry_run(tmp_path):
    with patch("prospective_daily_observation_cycle.build_plan", return_value=plan()) as build, \
         patch("prospective_daily_observation_cycle.commit_plan") as commit, \
         patch("prospective_daily_observation_cycle.build_quality_report", return_value=valid_quality()), \
         patch("prospective_daily_observation_cycle.refresh_cohort_b", return_value={"pipeline_decision": "no_changes", "new_observations": 0, "published": False}) as b, \
         patch("prospective_daily_observation_cycle.refresh_cohort_c", return_value={"refresh_decision": "no_changes", "new_observations": 0, "published": False}) as c, \
         patch("prospective_daily_observation_cycle.write_dashboard"):
        result = run_cycle(tmp_path, reports_dir=tmp_path)
    assert result["data_mode"] == "dry_run"
    assert result["data_refresh"]["committed"] is False
    assert result["cycle_decision"] == "completed_observation_dry_runs"
    assert result["cohort_b"]["published"] is False
    assert result["cohort_c"]["published"] is False
    assert not commit.called
    assert build.call_args.kwargs["workers"] == 4
    assert b.call_args.args[0] == tmp_path
    assert c.call_args.kwargs["commit"] is False
    assert c.call_args.kwargs["reports_dir"] == tmp_path


def test_quality_failure_prevents_b_c_refresh(tmp_path):
    invalid = valid_quality(); invalid["summary"]["total_duplicates"] = 1
    with patch("prospective_daily_observation_cycle.build_plan", return_value=plan()), \
         patch("prospective_daily_observation_cycle.build_quality_report", return_value=invalid), \
         patch("prospective_daily_observation_cycle.refresh_cohort_b") as b, \
         patch("prospective_daily_observation_cycle.refresh_cohort_c") as c:
        result = run_cycle(tmp_path, reports_dir=tmp_path)
    assert result["cycle_decision"] == "quality_rejected_no_cohort_refresh"
    assert result["cohort_b"]["executed"] is False
    assert result["cohort_c"]["executed"] is False
    assert not b.called
    assert not c.called


def test_explicit_commit_data_uses_validated_plan_only(tmp_path):
    committed = {**plan(), "committed": True}
    with patch("prospective_daily_observation_cycle.build_plan", return_value=plan()), \
         patch("prospective_daily_observation_cycle.commit_plan", return_value=committed) as commit, \
         patch("prospective_daily_observation_cycle.build_quality_report", return_value=valid_quality()), \
         patch("prospective_daily_observation_cycle.refresh_cohort_b", return_value={"pipeline_decision": "no_changes", "new_observations": 0, "published": False}), \
         patch("prospective_daily_observation_cycle.refresh_cohort_c", return_value={"refresh_decision": "no_changes", "new_observations": 0, "published": False}), \
         patch("prospective_daily_observation_cycle.write_dashboard"):
        result = run_cycle(tmp_path, commit_data=True, reports_dir=tmp_path)
    assert commit.called
    assert result["data_refresh"]["committed"] is True


def test_cohort_c_observation_publication_requires_explicit_data_commit(tmp_path):
    try:
        run_cycle(tmp_path, reports_dir=tmp_path, commit_cohort_c_observations=True)
    except ValueError as exc:
        assert "requires committed source data" in str(exc)
    else:
        raise AssertionError("Cohort C publication without data commit should fail")


def test_cli_rejects_c_observation_publication_without_data_commit():
    with pytest.raises(SystemExit) as exc:
        main(["--commit-cohort-c-observations"])
    assert exc.value.code == 2


def test_explicit_c_observation_publication_is_forwarded_only_after_quality(tmp_path):
    committed = {**plan(), "committed": True}
    with patch("prospective_daily_observation_cycle.build_plan", return_value=plan()), \
         patch("prospective_daily_observation_cycle.commit_plan", return_value=committed), \
         patch("prospective_daily_observation_cycle.build_quality_report", return_value=valid_quality()), \
         patch("prospective_daily_observation_cycle.refresh_cohort_b", return_value={"pipeline_decision": "no_changes", "new_observations": 0, "published": False}), \
         patch("prospective_daily_observation_cycle.refresh_cohort_c", return_value={"refresh_decision": "no_changes", "new_observations": 0, "published": False}) as c, \
         patch("prospective_daily_observation_cycle.write_dashboard"):
        result = run_cycle(tmp_path, commit_data=True, commit_cohort_c_observations=True, reports_dir=tmp_path)
    assert result["cohort_c"]["publication_requested"] is True
    assert c.call_args.kwargs["commit"] is True


def test_cycle_source_never_imports_runner():
    source = Path("prospective_daily_observation_cycle.py").read_text(encoding="utf-8")
    assert "from runner import" not in source
    assert "import runner" not in source

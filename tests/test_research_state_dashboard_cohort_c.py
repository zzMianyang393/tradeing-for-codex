from pathlib import Path

import research_state_dashboard
from research_state_dashboard import build_dashboard


def test_dashboard_exposes_cohort_c_as_future_only_exploration():
    cohort_c = build_dashboard()["cohort_c"]
    assert cohort_c["status"] == "exploration_future_only"
    assert cohort_c["cohort_id"] == "prospective_cohort_c_2026-07-15"
    assert cohort_c["hypothesis_id"] == "daily_volatility_expansion_short_exploration_v1"
    assert cohort_c["activation_not_before_utc"] == "2026-07-16 00:00:00"
    assert cohort_c["separate_from_cohort_b"] is True
    assert cohort_c["not_historical_approval"] is True


def test_dashboard_cohort_c_has_no_outcomes_or_positions_before_first_signal():
    cohort_c = build_dashboard()["cohort_c"]
    assert cohort_c["coverage_status"] == cohort_c["last_refresh"]["coverage_status"]
    assert cohort_c["signal_count"] == 0
    assert cohort_c["outcomes_evaluated"] is False
    assert cohort_c["positions_opened"] is False
    assert cohort_c["formal_observation_count"] == 0
    assert cohort_c["last_refresh"]["refresh_decision"] == "no_changes"
    assert cohort_c["last_refresh"]["published"] is False
    assert cohort_c["common_data_cutoff"] == cohort_c["last_refresh"]["common_data_cutoff"]
    assert cohort_c["sealed_evaluation_preflight"]["readiness_status"] == "awaiting_first_published_observation"
    assert cohort_c["sealed_evaluation_preflight"]["queued_observation_count"] == 0


def test_dashboard_never_reads_legacy_cohort_c_staging_report(monkeypatch):
    original_load_json = research_state_dashboard.load_json
    legacy_path = Path("reports/prospective_cohort_c_short_exploration_staging_ledger.json")

    def guarded_load_json(path):
        assert Path(path) != legacy_path
        return original_load_json(path)

    monkeypatch.setattr(research_state_dashboard, "load_json", guarded_load_json)
    assert build_dashboard()["cohort_c"]["coverage_status"] == "active"

from research_state_dashboard import build_dashboard


def test_dashboard_exposes_cohort_d_as_separate_future_only_exploration():
    cohort_d = build_dashboard()["cohort_d"]
    assert cohort_d["status"] == "exploration_future_only"
    assert cohort_d["hypothesis_id"] == "weekly_cross_sectional_weakness_short_exploration_v1"
    assert cohort_d["activation_not_before_utc"] == "2026-07-20 00:00:00"
    assert cohort_d["separate_from_cohort_b_and_c"] is True
    assert cohort_d["not_historical_approval"] is True


def test_dashboard_cohort_d_has_no_signal_or_outcome_before_activation():
    cohort_d = build_dashboard()["cohort_d"]
    assert cohort_d["coverage_status"] == "awaiting_data_coverage"
    assert cohort_d["signal_count"] == 0
    assert cohort_d["formal_observation_count"] == 0
    assert cohort_d["outcomes_evaluated"] is False
    assert cohort_d["positions_opened"] is False
    assert cohort_d["sealed_evaluation_preflight"]["readiness_status"] == "awaiting_first_published_observation"

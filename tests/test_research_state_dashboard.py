from research_state_dashboard import audit_status, build_dashboard


def test_small_oos_sample_is_insufficient_even_if_raw_status_is_rejected():
    report = {
        "status": "historical_rejected",
        "formation": {"events": 45},
        "oos": {"events": 11},
    }
    assert audit_status(report) == "insufficient_evidence"


def test_dashboard_cohort_b_counts_match_authoritative_checkpoint_and_maturity_audit():
    dashboard = build_dashboard()
    cohort_b = dashboard["cohort_b"]
    assert cohort_b["signal_count"] == cohort_b["checkpoint_count"]
    assert cohort_b["awaiting_count"] + cohort_b["mature_count"] == cohort_b["signal_count"]


def test_dashboard_date_tracks_the_current_observation_cutoff():
    dashboard = build_dashboard()
    latest = max(dashboard["cohort_b"]["common_data_cutoff"], dashboard["cohort_c"]["common_data_cutoff"])
    assert dashboard["generation_date"] == latest[:10]


def test_dashboard_keeps_all_safety_gates_closed():
    gates = build_dashboard()["safety_gates"]
    assert gates["approved_for_paper"] == []
    assert gates["eligible_for_paper"] is False
    assert gates["safe_to_enable_trading"] is False


def test_dashboard_tracks_completed_factor_expansion_audits():
    audits = build_dashboard()["historical_audits"]

    assert audits["daily_kdj_range_reversion"]["report_exists"] is True
    assert audits["daily_kdj_range_reversion"]["verdict"] == "insufficient_evidence"
    assert audits["daily_spring_upthrust_range_reversion"]["report_exists"] is True
    assert audits["daily_spring_upthrust_range_reversion"]["verdict"] == "insufficient_evidence"
    assert audits["daily_bb_squeeze_high_vol_breakout"]["report_exists"] is True
    assert audits["daily_bb_squeeze_high_vol_breakout"]["verdict"] == "insufficient_evidence"
    assert audits["weekly_cross_sectional_short_downtrend"]["report_exists"] is True
    assert audits["weekly_cross_sectional_short_downtrend"]["verdict"] == "historical_rejected"


def test_dashboard_exposes_feature_pool_without_combo_backtest_readiness():
    feature_pool = build_dashboard()["combo_feature_pool"]
    assert feature_pool["feature_count"] == 42
    assert feature_pool["violations"] == []
    assert feature_pool["ready_for_combo_backtest"] is False


def test_dashboard_marks_all_structural_priorities_as_closed():
    queue = build_dashboard()["priority_research_queue"]
    assert queue["closed_count"] == 13
    assert queue["open_research_count"] == 0


def test_dashboard_exposes_combo_observation_without_outcome_or_backtest_claim():
    combo = build_dashboard()["combo_observation"]
    assert combo["status"] == "metadata_only_no_outcomes"
    assert combo["raw_signal_count"] == 28
    assert combo["deduplicated_signal_count"] == 23
    assert combo["arbitration_state_counts"]["same_direction_consensus_no_leverage_addition"] == 1
    assert combo["arbitration_state_counts"]["opposite_direction_conflict_lockout"] == 4
    assert combo["within_24h_same_direction_consensus"] == 3
    assert combo["within_24h_opposite_direction_conflicts"] == 5
    assert combo["outcomes_evaluated"] is False
    assert combo["ready_for_combo_backtest"] is False


def test_dashboard_exposes_rejected_shared_capital_combo_baseline():
    combo = build_dashboard()["historical_combo_baselines"]["shared_capital_four_sleeve"]
    assert combo["status"] == "historical_walk_forward_rejected"
    assert combo["return_pct"] < 0
    assert combo["max_drawdown_pct"] > 20
    assert combo["positive_fold_count"] == 0
    assert combo["realized_pnl_by_component"]["range_bb_reversion_4h"] < 0
    assert len(combo["leave_one_sleeve_out"]) == 4
    assert all(item["diagnostic_only"] and item["not_a_candidate"] for item in combo["leave_one_sleeve_out"].values())
    assert combo["diagnostic_seal"]["seal_status"] == "sealed"
    assert combo["diagnostic_seal"]["historical_diagnostic_only"] is True
    assert combo["diagnostic_seal"]["issues"] == []


def test_dashboard_exposes_rejected_frozen_trend_sleeve():
    sleeve = build_dashboard()["historical_combo_baselines"]["frozen_trend_weak_factor_sleeve"]

    assert sleeve["status"] == "historical_combo_diagnostic_rejected"
    assert sleeve["oos"]["total_return_pct"] < 0
    assert sleeve["diagnostic_only"] is True
    assert sleeve["not_a_candidate"] is True


def test_dashboard_exposes_empty_sealed_queue_while_cohort_a_is_unmatured():
    cohort_a = build_dashboard()["cohort_a"]
    assert cohort_a["sealed_evaluation_preflight"]["readiness_status"] == "awaiting_maturity"
    assert cohort_a["sealed_evaluation_preflight"]["queued_observation_count"] == 0
    assert cohort_a["sealed_outcome_evaluation"]["evaluation_status"] == "awaiting_maturity"
    assert cohort_a["sealed_outcome_evaluation"]["outcomes_evaluated"] is False


def test_dashboard_exposes_structural_cooccurrence_without_combo_readiness():
    dashboard = build_dashboard()
    cooccurrence = dashboard["cohort_a"]["signal_cooccurrence"]
    assert cooccurrence["observation_only"] is True
    assert cooccurrence["observed_signal_count"] == dashboard["cohort_a"]["signal_count"]
    assert dashboard["safety_gates"]["ready_for_combo_backtest"] is False


def test_dashboard_exposes_cohort_b_candidate_evidence_without_enabling_generators():
    cohort_b = build_dashboard()["cohort_b"]
    assert cohort_b["candidate_evidence"]["daily_volatility_expansion_continuation_v1"] == "historical_research_candidate"
    assert cohort_b["generator_status"]["daily_volatility_expansion_continuation_v1"] == "signal_only_staging_ready_no_signal"
    assert cohort_b["activation_readiness"]["eligible_to_generate_observation"] is True
    assert cohort_b["volatility_expansion_staging"]["signal_count"] == 0
    assert cohort_b["combined_staging"]["signal_count"] == 1
    assert cohort_b["last_refresh_dry_run"]["published"] is False
    assert cohort_b["signal_only_refresh"]["pipeline_decision"] == "no_changes"
    assert cohort_b["common_data_cutoff"] == cohort_b["signal_only_refresh"]["source_cutoffs"]["combined"]


def test_dashboard_exposes_active_cohort_cutoff_alignment():
    alignment = build_dashboard()["active_cohort_cutoff_alignment"]
    assert alignment["alignment_status"] == "valid"
    assert alignment["issues"] == []

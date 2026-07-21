from uptrend_regime_structure_audit import (
    consecutive_runs,
    drift_diagnosis,
    forward_return_summary,
    run_age_bucket,
    summarize_observations,
    walk_forward_fold,
)


def test_consecutive_runs_counts_only_target_label():
    assert consecutive_runs(["趋势上行", "趋势上行", "震荡", "趋势上行"]) == [2, 1]


def test_forward_return_summary_reports_location_and_hit_rate():
    result = forward_return_summary([1.0, -0.5, 0.2])
    assert result["observations"] == 3
    assert result["mean_return_pct"] == 0.233333
    assert result["median_return_pct"] == 0.2
    assert result["positive_rate"] == 0.666667


def test_summarize_observations_ignores_unavailable_horizons():
    result = summarize_observations(
        [
            {"forward_returns_pct": {"4h": 0.1, "1d": 0.3}},
            {"forward_returns_pct": {"4h": -0.2}},
        ]
    )
    assert result["4h"]["observations"] == 2
    assert result["1d"]["observations"] == 1
    assert result["10d"]["observations"] == 0


def test_drift_diagnosis_requires_positive_aggregate_and_three_halfyears():
    aggregate = {
        "3d": {"mean_return_pct": 0.2},
        "10d": {"mean_return_pct": 0.5},
    }
    by_halfyear = {
        f"202{i}-H1": {
            "forward_returns": {
                "3d": {"observations": 10, "mean_return_pct": 0.1 if i < 3 else -0.1},
                "10d": {"observations": 10, "mean_return_pct": 0.2 if i < 3 else -0.2},
            }
        }
        for i in range(5)
    }
    result = drift_diagnosis(aggregate, by_halfyear)
    assert result["supports_long_context"] is True
    assert result["next_action"] == "pre_register_independent_uptrend_entry_batch"


def test_walk_forward_fold_keeps_early_july_inside_final_observed_fold():
    from regime_component_walk_forward_audit import parse_day

    assert walk_forward_fold(parse_day("2026-07-05")) == "2026-H1"


def test_run_age_bucket_has_fixed_non_overlapping_boundaries():
    assert run_age_bucket(1) == "first_1d"
    assert run_age_bucket(6) == "first_1d"
    assert run_age_bucket(7) == "day_2_to_3"
    assert run_age_bucket(19) == "day_4_to_10"
    assert run_age_bucket(61) == "older_than_10d"

from directional_regime_conditioned_audit import RANGE_COMPATIBLE_REGIMES
from range_regime_structure_audit import range_runs, signed_path_summary, summarize_observations


RANGE = next(iter(RANGE_COMPATIBLE_REGIMES))


def test_range_runs_counts_consecutive_labels():
    assert range_runs([RANGE, RANGE, "trend", RANGE]) == [2, 1]


def test_signed_path_summary_reports_hit_and_cost_rates():
    result = signed_path_summary([0.20, -0.10, 0.30])
    assert result["observations"] == 3
    assert result["expected_direction_hit_rate"] == 0.666667
    assert result["gross_return_above_cost_rate"] == 0.666667


def test_summarize_observations_ignores_missing_feature_bucket():
    observations = [
        {"bb_reversion": {"4h": 0.2}},
        {"continuation": {"4h": -0.1}},
    ]
    result = summarize_observations(observations, "bb_reversion")
    assert result["4h"]["observations"] == 1
    assert result["12h"]["observations"] == 0


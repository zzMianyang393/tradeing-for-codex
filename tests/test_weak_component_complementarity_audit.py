from weak_component_complementarity_audit import (
    active_days,
    event_interval_overlap,
    jaccard,
    monthly_returns,
    overlap_coefficient,
    pair_reasons,
    pearson,
)


def test_pearson_detects_opposite_series():
    assert pearson([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]) == -1.0


def test_overlap_metrics_use_fixed_denominators():
    assert jaccard({1, 2}, {2, 3}) == 0.333333
    assert overlap_coefficient({1, 2}, {2, 3, 4}) == 0.5


def test_monthly_returns_compound_daily_values():
    result = monthly_returns({0: 0.10, 86_400_000: -0.10})
    assert round(result["1970-01"], 6) == -0.01


def test_active_days_include_entry_and_exit_days():
    positions = [{"entry_ts": 0, "exit_ts": 2 * 86_400_000}]
    assert active_days(positions) == {0, 86_400_000, 2 * 86_400_000}


def test_event_interval_overlap_counts_same_symbol_pairs():
    left = [{"entry_ts": 10, "exit_ts": 20, "symbol": "BTC"}]
    right = [{"entry_ts": 15, "exit_ts": 25, "symbol": "BTC"}]
    result = event_interval_overlap(left, right)
    assert result["overlapping_event_pairs"] == 1
    assert result["same_symbol_overlapping_pairs"] == 1


def test_pair_reasons_accepts_positive_diversifying_pair():
    component = {"accepted_positions": 30, "total_return_pct": 1.0}
    metrics = {
        "active_union_daily_return_correlation": 0.1,
        "monthly_return_correlation": 0.2,
        "negative_day_overlap_coefficient": 0.1,
        "active_day_jaccard": 0.2,
    }
    assert pair_reasons(component, component, metrics) == []

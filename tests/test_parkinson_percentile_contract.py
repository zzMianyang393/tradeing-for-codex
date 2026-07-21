from parkinson_volatility_extreme_reversion_audit import nearest_rank_percentile


def test_nearest_rank_90th_percentile_of_120_values_is_108th_value() -> None:
    assert nearest_rank_percentile(list(range(1, 121)), 0.90) == 108


def test_nearest_rank_rejects_empty_or_invalid_percentile() -> None:
    for values, percentile in (([], 0.90), ([1], 0.0), ([1], 1.1)):
        try:
            nearest_rank_percentile(values, percentile)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid percentile contract must fail")

from weekly_weakest_short_complementarity_audit import duplication_diagnosis


def test_range_complementarity_uses_shared_duplication_contract():
    result = duplication_diagnosis(
        {
            "active_union_daily_return_correlation": -0.1,
            "monthly_return_correlation": 0.2,
            "negative_day_overlap_coefficient": 0.1,
            "active_day_jaccard": 0.2,
        }
    )
    assert result["likely_economic_duplicate"] is False
    assert result["high_operational_overlap"] is False

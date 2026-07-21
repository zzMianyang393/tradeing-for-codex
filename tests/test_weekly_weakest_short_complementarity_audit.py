from weekly_weakest_short_complementarity_audit import duplication_diagnosis


def test_duplication_diagnosis_separates_economic_and_operational_overlap():
    metrics = {
        "active_union_daily_return_correlation": 0.10,
        "monthly_return_correlation": 0.20,
        "negative_day_overlap_coefficient": 0.30,
        "active_day_jaccard": 0.80,
    }
    result = duplication_diagnosis(metrics)
    assert result["likely_economic_duplicate"] is False
    assert result["high_operational_overlap"] is True
    assert result["interpretation"] == "distinct_return_pattern_with_high_simultaneous_risk_usage"


def test_duplication_diagnosis_marks_return_pattern_trigger():
    metrics = {
        "active_union_daily_return_correlation": 0.36,
        "monthly_return_correlation": 0.20,
        "negative_day_overlap_coefficient": 0.30,
        "active_day_jaccard": 0.20,
    }
    result = duplication_diagnosis(metrics)
    assert result["likely_economic_duplicate"] is True
    assert result["economic_duplication_triggers"] == ["daily_return_correlation"]
    assert result["interpretation"] == "economic_duplication_risk"

from weekly_range_cross_sectional_reversal_preflight import select_reversal_cohorts, validate_return_free


def test_select_reversal_cohorts_longs_weakest_and_shorts_strongest():
    scores = {f"S{i}": float(i) for i in range(8)}
    longs, shorts = select_reversal_cohorts(scores)
    assert longs == ["S0", "S1", "S2"]
    assert shorts == ["S7", "S6", "S5"]


def test_validate_return_free_rejects_outcome_field_names():
    assert validate_return_free({"capacity": {"events": 10}}) == []
    assert validate_return_free({"capacity": {"total_return_pct": 1.0}}) == [
        "capacity.total_return_pct"
    ]

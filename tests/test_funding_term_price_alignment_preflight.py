from funding_term_price_alignment_preflight import funding_state, percentile, rolling_funding, validate_return_free


def test_percentile_uses_deterministic_nearest_lower_rank():
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.8) == 4.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.2) == 1.0


def test_rolling_funding_uses_21_settlements():
    points = [(index, float(index)) for index in range(22)]
    result = rolling_funding(points)
    assert result[0] == (20, 10.0)
    assert result[1] == (21, 11.0)


def test_funding_state_requires_450_prior_points():
    rolling = [(index, 1.0) for index in range(449)] + [(449, 2.0)]
    assert funding_state(rolling, 449) is None


def test_validate_return_free_allows_past_price_change_but_not_future_outcome():
    assert validate_return_free({"prior_7d_price_change": 0.1}) == []
    assert validate_return_free({"future_return_pct": 1.0}) == ["future_return_pct"]

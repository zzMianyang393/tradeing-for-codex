from historical_fold_universe_audit import BAR_MS, constant_universe, expected_bar_count, fold_coverage


def test_expected_bar_count_is_inclusive():
    assert expected_bar_count(0, 2 * BAR_MS) == 3


def test_fold_coverage_deduplicates_timestamps():
    result = fold_coverage([0, BAR_MS, BAR_MS, 2 * BAR_MS], 0, 2 * BAR_MS)
    assert result["actual_bars"] == 3
    assert result["coverage_ratio"] == 1.0
    assert result["eligible"] is True


def test_constant_universe_intersects_all_folds():
    assert constant_universe({"a": ["BTC", "ETH"], "b": ["BTC", "SOL"]}) == ["BTC"]

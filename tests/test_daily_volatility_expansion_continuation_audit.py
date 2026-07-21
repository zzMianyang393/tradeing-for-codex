from daily_volatility_expansion_continuation_audit import HIGH_VOL_TRANSITION, true_range, verdict
from market import Bar


def test_true_range_includes_gap_against_prior_close():
    bar = Bar(ts=0, time="1970-01-01 00:00:00", open=110.0, high=112.0, low=109.0, close=111.0, volume_quote=1.0)
    assert true_range(bar, 100.0) == 12.0


def test_high_volatility_label_is_canonical_unicode_value():
    assert HIGH_VOL_TRANSITION == "\u9ad8\u6ce2\u52a8\u8f6c\u6362"


def test_verdict_requires_fifteen_compatible_events_in_both_splits():
    stats = {"events": 14, "mean_pct": 1.0, "positive_return_month_concentration": 0.1,
             "november_2024_positive_return_contribution": 0.0, "excluding_2024_11_net_sum_pct": 1.0}
    assert verdict(stats, stats)[0] == "insufficient_evidence"


def test_verdict_rejects_negative_mean_with_sufficient_samples():
    stats = {"events": 15, "mean_pct": -0.1, "positive_return_month_concentration": 0.1,
             "november_2024_positive_return_contribution": 0.0, "excluding_2024_11_net_sum_pct": 1.0}
    assert verdict(stats, stats)[0] == "historical_rejected"


def test_november_concentration_requires_non_positive_result_after_removal():
    stats = {"events": 15, "mean_pct": 0.1, "positive_return_month_concentration": 0.9,
             "november_2024_positive_return_contribution": 0.3, "excluding_2024_11_net_sum_pct": 0.1}
    assert verdict(stats, stats)[0] == "historical_research_candidate"

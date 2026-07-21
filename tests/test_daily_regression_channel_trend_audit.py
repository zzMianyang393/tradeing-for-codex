from daily_regression_channel_trend_audit import su


def test_summary_includes_positive_month_concentration():
    events = [
        {"net_return_pct": 1.0, "signal_ts": 1704067200000},
        {"net_return_pct": 3.0, "signal_ts": 1706745600000},
    ]

    assert su(events)["positive_return_month_concentration"] == 0.75


def test_empty_summary_has_zero_concentration():
    assert su([])["positive_return_month_concentration"] == 0.0

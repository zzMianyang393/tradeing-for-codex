from daily_rsi_percentile_range_reversion_audit import conc, su


def test_summary_includes_positive_month_concentration():
    events = [
        {"net_return_pct": 1.0, "signal_ts": 1704067200000},
        {"net_return_pct": 3.0, "signal_ts": 1706745600000},
    ]

    assert conc(events) == 0.75
    assert su(events)["positive_return_month_concentration"] == 0.75


def test_empty_summary_has_zero_concentration():
    assert su([])["positive_return_month_concentration"] == 0.0

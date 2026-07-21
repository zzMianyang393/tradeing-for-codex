from daily_volume_shock_reversal_preflight import coverage_reasons, event_direction, panel_summary, true_range
from market import Bar


def test_event_direction_reverses_extreme_close_location():
    assert event_direction(0.10) == "long"
    assert event_direction(0.90) == "short"
    assert event_direction(0.50) is None


def test_true_range_includes_previous_close_gap():
    bar = Bar(ts=0, time="", open=12.0, high=13.0, low=11.0, close=12.0, volume_quote=1.0)
    assert true_range(bar, 9.0) == 4.0


def test_panel_summary_reports_fold_direction_and_concentration():
    events = [
        {"fold": "2024-H1", "direction": "long", "month": "2024-01"},
        {"fold": "2024-H2", "direction": "short", "month": "2024-02"},
    ]
    result = panel_summary(events)
    assert result["events"] == 2
    assert result["folds_with_events"] == 2
    assert result["direction_shares"] == {"long": 0.5, "short": 0.5}
    assert result["top_month_event_share"] == 0.5


def test_coverage_reasons_accepts_balanced_inventory():
    primary = {"events": 15, "folds_with_events": 4}
    secondary = {
        "events": 60,
        "folds_with_at_least_10_events": 3,
        "direction_shares": {"long": 0.5, "short": 0.5},
        "top_month_event_share": 0.2,
    }
    assert coverage_reasons(primary, secondary) == []

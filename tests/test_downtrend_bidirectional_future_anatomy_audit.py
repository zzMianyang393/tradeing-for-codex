from downtrend_bidirectional_future_anatomy_audit import monthly_component_pnl


def test_monthly_component_pnl_identifies_cancellation_and_concentration():
    closed = [
        {"exit_timestamp_utc": "2026-01-02", "component_id": "long", "realized_pnl": 10.0},
        {"exit_timestamp_utc": "2026-01-03", "component_id": "short", "realized_pnl": -4.0},
        {"exit_timestamp_utc": "2026-02-02", "component_id": "long", "realized_pnl": 5.0},
        {"exit_timestamp_utc": "2026-02-03", "component_id": "short", "realized_pnl": 8.0},
    ]
    result = monthly_component_pnl(closed)
    assert result["cancellation_months"] == ["2026-01"]
    assert result["rows"][0]["total_pnl"] == 6.0
    assert result["positive_month_concentration_by_component"]["long"] == 0.666667
    assert result["positive_month_concentration_by_component"]["short"] == 1.0


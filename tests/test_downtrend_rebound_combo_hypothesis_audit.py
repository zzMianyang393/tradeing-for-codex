from __future__ import annotations

from downtrend_rebound_combo_hypothesis_audit import (
    DONCHIAN_FEATURE,
    EMA_FEATURE,
    RSI_FEATURE,
    build_report,
    downtrend_events,
    feature_month_returns,
    h1_donchian_veto,
    h2_ema_confirmation,
    h3_rsi_baseline,
    split_summary,
)


def _timeseries() -> dict:
    return {
        "events": [
            {"entry_regime": "趋势下行", "feature_id": RSI_FEATURE, "month": "2024-01", "split": "formation", "net_return_pct": 2.0},
            {"entry_regime": "趋势下行", "feature_id": RSI_FEATURE, "month": "2024-02", "split": "oos", "net_return_pct": -1.0},
            {"entry_regime": "趋势下行", "feature_id": RSI_FEATURE, "month": "2024-03", "split": "oos", "net_return_pct": 3.0},
            {"entry_regime": "趋势下行", "feature_id": DONCHIAN_FEATURE, "month": "2024-02", "split": "oos", "net_return_pct": -4.0},
            {"entry_regime": "趋势下行", "feature_id": EMA_FEATURE, "month": "2024-03", "split": "oos", "net_return_pct": 5.0},
            {"entry_regime": "震荡", "feature_id": RSI_FEATURE, "month": "2024-04", "split": "oos", "net_return_pct": 9.0},
        ]
    }


def test_downtrend_events_filters_regime():
    assert len(downtrend_events(_timeseries())) == 5


def test_feature_month_returns_groups_returns():
    table = feature_month_returns(downtrend_events(_timeseries()))

    assert table[RSI_FEATURE]["2024-01"] == 2.0
    assert table[DONCHIAN_FEATURE]["2024-02"] == -4.0


def test_h3_baseline_uses_all_downtrend_rsi_events():
    events = downtrend_events(_timeseries())
    table = feature_month_returns(events)

    assert len(h3_rsi_baseline(events, table)) == 3


def test_h1_veto_removes_rsi_months_with_donchian_activity():
    events = downtrend_events(_timeseries())
    table = feature_month_returns(events)

    result = h1_donchian_veto(events, table)

    assert [event["month"] for event in result] == ["2024-01", "2024-03"]


def test_h2_confirmation_keeps_rsi_months_with_ema_activity():
    events = downtrend_events(_timeseries())
    table = feature_month_returns(events)

    result = h2_ema_confirmation(events, table)

    assert [event["month"] for event in result] == ["2024-03"]


def test_split_summary_reports_oos_metrics():
    events = downtrend_events(_timeseries())
    table = feature_month_returns(events)
    result = split_summary(h3_rsi_baseline(events, table))

    assert result["oos"]["events"] == 2
    assert result["oos"]["net_sum_pct"] == 2.0
    assert result["oos"]["win_rate"] == 0.5


def test_build_report_preserves_safety_gates_and_limitations():
    report = build_report(_timeseries())

    assert report["scope"] == "read_only_diagnostic_not_executable_combo_backtest"
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["eligible_for_paper"] is False
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False
    assert any("not executable entry-time rules" in item for item in report["diagnostic_limitations"])

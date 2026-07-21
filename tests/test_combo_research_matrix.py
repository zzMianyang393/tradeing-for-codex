from __future__ import annotations

from combo_research_matrix import (
    build_report,
    build_rows,
    feature_roles,
    missing_months_by_feature,
    months_from_reports,
)


def _directional() -> dict:
    return {
        "monthly_net_return_pct_by_feature": {
            "feat_alpha": {"2024-01": 1.0, "2024-02": -2.0},
        }
    }


def _auxiliary() -> dict:
    return {
        "events": [
            {"feature_id": "feat_context", "role": "context_label"},
            {"feature_id": "feat_risk", "role": "risk_filter_candidate"},
        ],
        "monthly_event_counts_by_feature": {
            "feat_context": {"2024-01": 2},
            "feat_risk": {"2024-02": 1},
        },
        "monthly_value_sums_by_feature": {
            "feat_context": {"2024-01": 3.5},
            "feat_risk": {"2024-02": 1.0},
        },
    }


def test_months_from_reports_uses_union():
    assert months_from_reports(_directional(), _auxiliary()) == ["2024-01", "2024-02"]


def test_feature_roles_combines_directional_and_auxiliary_roles():
    roles = feature_roles(_directional(), _auxiliary())

    assert roles["feat_alpha"] == "directional_weak_signal"
    assert roles["feat_context"] == "context_label"
    assert roles["feat_risk"] == "risk_filter_candidate"


def test_build_rows_aligns_monthly_values():
    rows = build_rows(_directional(), _auxiliary())

    assert rows[0]["month"] == "2024-01"
    assert rows[0]["feat_alpha__net_return_pct"] == 1.0
    assert rows[0]["feat_context__event_count"] == 2
    assert rows[0]["feat_risk__event_count"] == 0
    assert rows[1]["feat_alpha__net_return_pct"] == -2.0
    assert rows[1]["feat_risk__value_sum"] == 1.0


def test_missing_months_by_feature_marks_zero_months():
    rows = build_rows(_directional(), _auxiliary())
    roles = feature_roles(_directional(), _auxiliary())

    result = missing_months_by_feature(rows, roles)

    assert result["feat_context"] == ["2024-02"]
    assert result["feat_risk"] == ["2024-01"]


def test_build_report_preserves_safety_gates():
    report = build_report(_directional(), _auxiliary())

    assert report["n_months"] == 2
    assert report["n_features"] == 3
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False

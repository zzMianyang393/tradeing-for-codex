from __future__ import annotations

from combo_matrix_quality_review import (
    build_report,
    common_months,
    coverage_by_feature,
    feature_column,
    nonzero_months,
    reason_codes,
)


def _matrix() -> dict:
    return {
        "n_months": 3,
        "feature_roles": {
            "feat_a": "directional_weak_signal",
            "feat_b": "directional_weak_signal",
            "feat_risk": "risk_filter_candidate",
            "feat_context": "context_label",
        },
        "rows": [
            {
                "month": "2024-01",
                "feat_a__net_return_pct": 1.0,
                "feat_b__net_return_pct": 2.0,
                "feat_risk__event_count": 1,
                "feat_context__event_count": 0,
            },
            {
                "month": "2024-02",
                "feat_a__net_return_pct": 0.0,
                "feat_b__net_return_pct": -1.0,
                "feat_risk__event_count": 1,
                "feat_context__event_count": 1,
            },
            {
                "month": "2024-03",
                "feat_a__net_return_pct": 3.0,
                "feat_b__net_return_pct": 0.0,
                "feat_risk__event_count": 0,
                "feat_context__event_count": 0,
            },
        ],
    }


def test_feature_column_uses_role_specific_columns():
    assert feature_column("feat_a", "directional_weak_signal") == "feat_a__net_return_pct"
    assert feature_column("feat_risk", "risk_filter_candidate") == "feat_risk__event_count"


def test_nonzero_months_lists_active_months():
    assert nonzero_months(_matrix()["rows"], "feat_a", "directional_weak_signal") == ["2024-01", "2024-03"]


def test_coverage_by_feature_reports_zero_share():
    coverage = coverage_by_feature(_matrix())

    assert coverage["feat_a"]["active_months"] == 2
    assert coverage["feat_a"]["zero_months"] == 1
    assert coverage["feat_context"]["zero_month_share"] == 0.666667


def test_common_months_requires_all_features_active():
    matrix = _matrix()
    result = common_months(matrix["rows"], ["feat_a", "feat_b", "feat_risk"], matrix["feature_roles"])

    assert result == ["2024-01"]


def test_reason_codes_block_insufficient_directional_features_and_common_months():
    matrix = _matrix()
    coverage = coverage_by_feature(matrix)
    reasons = reason_codes(matrix, coverage)

    assert any("directional features 2 < 3" in reason for reason in reasons)
    assert any("directional common active months 1 < 12" in reason for reason in reasons)


def test_build_report_preserves_safety_gates():
    report = build_report(_matrix())

    assert report["ready_for_combo_hypothesis_test"] is False
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False

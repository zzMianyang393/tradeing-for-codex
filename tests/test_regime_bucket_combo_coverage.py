from __future__ import annotations

from regime_bucket_combo_coverage import (
    active_months,
    bucket_status,
    build_report,
    feature_coverage,
    pairwise_overlap,
    regime_monthly_returns,
)


def _events() -> list[dict]:
    return [
        {"entry_regime": "趋势下行", "feature_id": "feat_a", "month": "2024-01", "net_return_pct": 1.0},
        {"entry_regime": "趋势下行", "feature_id": "feat_a", "month": "2024-02", "net_return_pct": 2.0},
        {"entry_regime": "趋势下行", "feature_id": "feat_b", "month": "2024-02", "net_return_pct": 3.0},
        {"entry_regime": "趋势下行", "feature_id": "feat_b", "month": "2024-03", "net_return_pct": -1.0},
        {"entry_regime": "震荡", "feature_id": "feat_c", "month": "2024-01", "net_return_pct": 4.0},
    ]


def test_regime_monthly_returns_groups_by_regime_feature_and_month():
    result = regime_monthly_returns(_events())

    assert result["趋势下行"]["feat_a"]["2024-01"] == 1.0
    assert result["趋势下行"]["feat_b"]["2024-02"] == 3.0
    assert result["震荡"]["feat_c"]["2024-01"] == 4.0


def test_active_months_ignores_zero_values():
    assert active_months({"2024-01": 1.0, "2024-02": 0.0, "2024-03": -1.0}) == ["2024-01", "2024-03"]


def test_feature_coverage_summarizes_return_signs():
    result = feature_coverage({"feat_a": {"2024-01": 1.0, "2024-02": -2.0}})

    assert result["feat_a"]["active_months"] == 2
    assert result["feat_a"]["net_sum_pct"] == -1.0
    assert result["feat_a"]["positive_months"] == 1
    assert result["feat_a"]["negative_months"] == 1


def test_pairwise_overlap_reports_common_active_months():
    result = pairwise_overlap(
        {
            "feat_a": {"2024-01": 1.0, "2024-02": 1.0},
            "feat_b": {"2024-02": 1.0, "2024-03": 1.0},
        }
    )

    assert result[0]["features"] == ["feat_a", "feat_b"]
    assert result[0]["common_active_months"] == 1
    assert result[0]["months"] == ["2024-02"]


def test_bucket_status_blocks_sparse_buckets():
    features = {"feat_a": {"2024-01": 1.0}}
    result = bucket_status(features, pairwise_overlap(features))

    assert result["research_status"] == "coverage_insufficient"
    assert any("features 1 < 2" in reason for reason in result["reasons"])


def test_bucket_status_allows_preflight_candidate_with_pair_overlap():
    features = {
        "feat_a": {"2024-01": 1.0, "2024-02": 1.0, "2024-03": 1.0, "2024-04": 1.0, "2024-05": 1.0, "2024-06": 1.0},
        "feat_b": {"2024-01": 1.0, "2024-02": 1.0, "2024-03": 1.0, "2024-04": 1.0, "2024-07": 1.0, "2024-08": 1.0},
    }

    result = bucket_status(features, pairwise_overlap(features))

    assert result["research_status"] == "preflight_candidate"
    assert result["viable_pair_count"] == 1


def test_build_report_preserves_safety_gates():
    report = build_report({"events": _events()})

    assert report["scope"] == "regime_bucket_coverage_not_combo_backtest"
    assert report["source_event_count"] == 5
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False

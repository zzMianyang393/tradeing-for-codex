from historical_combo_candidate_preflight import build_report, classify, summarize_events


def _event(feature: str, source: str, month: str, value: float) -> dict:
    return {"feature_id": feature, "source_research_id": source, "month": month, "net_return_pct": value}


def test_summary_counts_events_months_and_concentration():
    summary = summarize_events([
        _event("feat_a", "a", "2024-01", 2.0),
        _event("feat_a", "a", "2024-01", 1.0),
        _event("feat_a", "a", "2024-02", 9.0),
    ])["feat_a"]

    assert summary["event_count"] == 3
    assert summary["active_month_count"] == 2
    assert summary["top_positive_month_contribution_share"] == 0.75


def test_classify_requires_coverage_and_low_concentration():
    status, reasons = classify({"event_count": 30, "active_month_count": 12, "top_positive_month_contribution_share": 0.25}, [])

    assert status == "eligible_for_historical_combo_hypothesis"
    assert reasons == []


def test_classify_blocks_posthoc_semantic_repair():
    status, reasons = classify({"event_count": 30, "active_month_count": 12, "top_positive_month_contribution_share": 0.2}, ["posthoc_semantic_repair_requires_future_oos"])

    assert status == "not_eligible_for_historical_combo_hypothesis"
    assert reasons == ["requires_future_oos_semantic_confirmation"]


def test_classify_preserves_high_concentration_as_penalized_combo_feature():
    status, reasons = classify({"event_count": 30, "active_month_count": 12, "top_positive_month_contribution_share": 0.4}, [])

    assert status == "eligible_with_concentration_penalty"
    assert reasons == ["positive_month_concentration_above_limit"]


def test_report_keeps_all_safety_gates_closed():
    events = []
    for month_index in range(12):
        month = f"2024-{month_index + 1:02d}"
        for _ in range(3):
            events.append(_event("feat_a", "a", month, 1.0))
    report = build_report(
        {"events": events},
        {"groups": {"directional_feature_candidates": [{"source_research_id": "a", "tags": []}]}},
    )

    assert report["eligible_directional_feature_ids"] == ["feat_a"]
    assert report["concentration_penalty_feature_ids"] == []
    assert report["ready_for_historical_combo_hypothesis"] is False
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False

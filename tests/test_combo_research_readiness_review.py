from __future__ import annotations

from combo_research_readiness_review import readiness_review


def _preflight(directional: list[dict], context: list[dict] | None = None, risk_filter: list[dict] | None = None) -> dict:
    return {
        "groups": {
            "directional_feature_candidates": directional,
            "context_label_candidates": [{"source_research_id": "ctx"}] if context is None else context,
            "risk_filter_candidates": [{"source_research_id": "risk"}] if risk_filter is None else risk_filter,
            "blocked_features": [{"source_research_id": "blocked"}],
        },
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
        },
    }


def test_current_two_directional_features_are_not_ready_for_combo_backtest():
    report = readiness_review(_preflight([
        {"source_research_id": "donchian_atr_trend_baseline", "requires_concentration_penalty": True},
        {"source_research_id": "daily_bb_mean_revert", "requires_concentration_penalty": True},
    ]))

    assert report["ready_for_combo_backtest"] is False
    assert report["allowed_next_step"] == "feature_timeseries_extraction_only"
    assert any("directional features 2 < 3" in reason for reason in report["reason_codes"])
    assert "all directional candidates require concentration penalty" in report["reason_codes"]


def test_three_diverse_directional_features_can_pass_readiness_gate():
    report = readiness_review(_preflight([
        {"source_research_id": "trend", "requires_concentration_penalty": False},
        {"source_research_id": "revert", "requires_concentration_penalty": True},
        {"source_research_id": "breakout", "requires_concentration_penalty": False},
    ]))

    assert report["ready_for_combo_backtest"] is True
    assert report["allowed_next_step"] == "combo_backtest"
    assert report["reason_codes"] == []


def test_non_empty_approved_for_paper_blocks_readiness():
    data = _preflight([
        {"source_research_id": "trend", "requires_concentration_penalty": False},
        {"source_research_id": "revert", "requires_concentration_penalty": False},
        {"source_research_id": "breakout", "requires_concentration_penalty": False},
    ])
    data["safety_gates"]["approved_for_paper"] = ["bad"]

    report = readiness_review(data)

    assert report["ready_for_combo_backtest"] is False
    assert "approved_for_paper is not empty" in report["reason_codes"]


def test_missing_context_or_risk_filter_warns_but_does_not_block():
    report = readiness_review(_preflight([
        {"source_research_id": "trend", "requires_concentration_penalty": False},
        {"source_research_id": "revert", "requires_concentration_penalty": False},
        {"source_research_id": "breakout", "requires_concentration_penalty": False},
    ], context=[], risk_filter=[]))

    assert report["ready_for_combo_backtest"] is True
    assert "no context labels available for regime diagnostics" in report["warnings"]
    assert "no risk filters available for veto-only diagnostics" in report["warnings"]

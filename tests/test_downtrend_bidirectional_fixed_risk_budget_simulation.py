from __future__ import annotations

from downtrend_bidirectional_combo_simulation import EMA_COMPONENT, RSI_COMPONENT
from downtrend_bidirectional_fixed_risk_budget_simulation import (
    COMPONENT_CAPS,
    baseline_delta,
    render_markdown,
)


def _result(return_pct: float, drawdown: float, accepted: int, exposure: float = 0.5) -> dict:
    return {
        "accepted_positions": accepted,
        "capacity_rejected_events": 0,
        "total_return_pct": return_pct,
        "max_drawdown_pct": drawdown,
        "realized_win_rate": 0.5,
        "average_gross_exposure": exposure,
        "top_positive_month_share": 0.2,
        "component_attribution": {
            RSI_COMPONENT: {
                "accepted_positions": 20,
                "rejected_events": 0,
                "return_contribution_pct": 1.0,
                "realized_win_rate": 0.5,
            },
            EMA_COMPONENT: {
                "accepted_positions": 10,
                "rejected_events": 0,
                "return_contribution_pct": 1.0,
                "realized_win_rate": 0.5,
            },
        },
    }


def test_component_caps_are_frozen_two_long_three_short():
    assert COMPONENT_CAPS == {RSI_COMPONENT: 2, EMA_COMPONENT: 3}


def test_baseline_delta_reports_return_and_drawdown_improvement():
    overlay = _result(5.0, 15.0, 30, 0.4)
    baseline = _result(3.0, 25.0, 40, 0.6)

    delta = baseline_delta(overlay, baseline)

    assert delta["return_delta_pct"] == 2.0
    assert delta["max_drawdown_delta_pct"] == -10.0
    assert delta["accepted_position_delta"] == -10
    assert delta["average_exposure_delta"] == -0.2


def test_render_markdown_marks_overlay_as_unvalidated():
    result = _result(2.0, 10.0, 30)
    report = {
        "results": {
            "formation": result,
            "formation_excluding_2024_11": result,
            "oos": result,
        },
        "baseline_deltas": {
            key: {
                "return_delta_pct": 1.0,
                "max_drawdown_delta_pct": -5.0,
                "accepted_position_delta": -1,
                "average_exposure_delta": -0.1,
            }
            for key in ("formation", "formation_excluding_2024_11", "oos")
        },
        "diagnostic_reasons": [],
        "passes_current_diagnostic_screen": True,
        "validation_status": "posthoc_overlay_requires_future_unseen_window",
    }

    document = render_markdown(report)

    assert "not validated" in document
    assert "eligible_for_paper = false" in document

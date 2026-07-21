from __future__ import annotations

from downtrend_bidirectional_combo_simulation import (
    EMA_COMPONENT,
    RSI_COMPONENT,
    diagnostic_reasons,
    formation_without_november,
    render_markdown,
    tag_components,
)
from two_regime_shared_capital_combo_simulation import component_attribution


def _rsi(month: str = "2024-10") -> dict:
    return {
        "entry_regime": "趋势下行",
        "event_time_inputs_complete": True,
        "prior_downtrend_4h_streak": 5,
        "signal_rsi": 30.0,
        "split": "formation",
        "signal_timestamp_utc": f"{month}-01 00:00:00",
    }


def _ema(month: str = "2024-10") -> dict:
    return {
        "direction": "short",
        "entry_regime": "趋势下行",
        "direction_compatible_regime": True,
        "split": "formation",
        "signal_timestamp_utc": f"{month}-01 00:00:00",
    }


def _portfolio(return_pct: float = 1.0) -> dict:
    return {
        "candidate_events": 40,
        "accepted_positions": 40,
        "capacity_rejected_events": 0,
        "total_return_pct": return_pct,
        "max_drawdown_pct": 10.0,
        "realized_win_rate": 0.5,
        "average_gross_exposure": 0.5,
        "peak_gross_exposure": 1.0,
        "top_positive_month_share": 0.2,
        "component_attribution": {
            RSI_COMPONENT: {"accepted_positions": 20},
            EMA_COMPONENT: {"accepted_positions": 20},
        },
    }


def test_tag_components_preserves_opposing_directions():
    events = tag_components({"events": [_rsi()]}, {"events": [_ema()]})

    by_component = {event["component_id"]: event for event in events}
    assert by_component[RSI_COMPONENT]["direction"] == "long"
    assert by_component[EMA_COMPONENT]["direction"] == "short"


def test_formation_without_november_removes_both_components():
    events = tag_components(
        {"events": [_rsi("2024-10"), _rsi("2024-11")]},
        {"events": [_ema("2024-10"), _ema("2024-11")]},
    )

    result = formation_without_november(events)

    assert len(result) == 2
    assert all("2024-11" not in event["signal_timestamp_utc"] for event in result)


def test_diagnostic_reasons_require_positive_oos():
    reasons = diagnostic_reasons(_portfolio(), _portfolio(), _portfolio(-1.0))

    assert "OOS total return <= 0" in reasons


def test_component_attribution_only_adds_registered_components():
    result = {"initial_equity": 100_000.0, "closed_positions": [], "rejected_events": []}

    attribution = component_attribution(result, (RSI_COMPONENT, EMA_COMPONENT))

    assert set(attribution) == {RSI_COMPONENT, EMA_COMPONENT}


def test_render_markdown_keeps_safety_closed():
    result = _portfolio()
    result["component_attribution"] = {
        RSI_COMPONENT: {
            "accepted_positions": 20,
            "rejected_events": 0,
            "realized_pnl": 100.0,
            "return_contribution_pct": 0.1,
            "realized_win_rate": 0.5,
        },
        EMA_COMPONENT: {
            "accepted_positions": 20,
            "rejected_events": 0,
            "realized_pnl": 100.0,
            "return_contribution_pct": 0.1,
            "realized_win_rate": 0.5,
        },
    }
    report = {
        "results": {
            "formation": result,
            "formation_excluding_2024_11": result,
            "oos": result,
        },
        "diagnostic_reasons": [],
        "passes_diagnostic_screen": True,
    }

    document = render_markdown(report)

    assert "eligible_for_paper = false" in document
    assert "ready_for_combo_backtest = false" in document

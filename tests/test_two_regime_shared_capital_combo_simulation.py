from __future__ import annotations

from two_regime_shared_capital_combo_simulation import (
    DONCHIAN_COMPONENT,
    RSI_COMPONENT,
    combo_screen,
    component_attribution,
    excluding_formation_november,
    tag_components,
)


def _rsi_event(month: str = "2024-10") -> dict:
    return {
        "entry_regime": "趋势下行",
        "event_time_inputs_complete": True,
        "prior_downtrend_4h_streak": 5,
        "signal_rsi": 30.0,
        "split": "formation",
        "signal_timestamp_utc": f"{month}-01 00:00:00",
    }


def _donchian_event(month: str = "2024-10") -> dict:
    return {
        "direction": "long",
        "entry_regime": "趋势上行",
        "declared_compatible_regime": True,
        "split": "formation",
        "signal_timestamp_utc": f"{month}-01 00:00:00",
    }


def test_tag_components_keeps_full_registered_buckets():
    events = tag_components({"events": [_rsi_event()]}, {"events": [_donchian_event()]})

    assert {event["component_id"] for event in events} == {RSI_COMPONENT, DONCHIAN_COMPONENT}
    rsi = next(event for event in events if event["component_id"] == RSI_COMPONENT)
    assert rsi["portfolio_priority"] == 30.0


def test_excluding_formation_november_removes_both_components():
    events = tag_components(
        {"events": [_rsi_event("2024-11"), _rsi_event("2024-10")]},
        {"events": [_donchian_event("2024-11"), _donchian_event("2024-10")]},
    )

    result = excluding_formation_november(events)

    assert len(result) == 2
    assert all("2024-11" not in event["signal_timestamp_utc"] for event in result)


def test_component_attribution_splits_realized_pnl():
    result = {
        "initial_equity": 100_000.0,
        "closed_positions": [
            {"component_id": RSI_COMPONENT, "realized_pnl": 1000.0},
            {"component_id": DONCHIAN_COMPONENT, "realized_pnl": -500.0},
        ],
        "rejected_events": [{"component_id": RSI_COMPONENT}],
    }

    attribution = component_attribution(result)

    assert attribution[RSI_COMPONENT]["return_contribution_pct"] == 1.0
    assert attribution[DONCHIAN_COMPONENT]["return_contribution_pct"] == -0.5
    assert attribution[RSI_COMPONENT]["rejected_events"] == 1


def test_combo_screen_requires_both_components_and_november_stress():
    closed = [
        {"component_id": RSI_COMPONENT, "realized_pnl": 100.0, "exit_timestamp_utc": "2025-01-01 00:00:00"}
        for _ in range(30)
    ]
    oos = {
        "total_return_pct": 3.0,
        "max_drawdown_pct": 5.0,
        "accepted_positions": 30,
        "top_positive_month_share": 0.20,
        "initial_equity": 100_000.0,
        "closed_positions": closed,
        "rejected_events": [],
    }
    formation_ex_november = {"total_return_pct": -1.0}

    reasons = combo_screen(oos, formation_ex_november)

    assert any(DONCHIAN_COMPONENT in reason for reason in reasons)
    assert any("excluding 2024-11" in reason for reason in reasons)


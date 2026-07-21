from __future__ import annotations

from downtrend_bidirectional_combo_simulation import EMA_COMPONENT, RSI_COMPONENT
from downtrend_bidirectional_future_validation import (
    declared_downtrend_rsi_events,
    eligible_symbols_from_coverage,
    validation_reasons,
)


def passing_result():
    return {
        "total_return_pct": 5.0,
        "max_drawdown_pct": 10.0,
        "accepted_positions": 35,
        "top_positive_month_share": 0.24,
        "component_attribution": {
            RSI_COMPONENT: {"accepted_positions": 20, "return_contribution_pct": 3.0},
            EMA_COMPONENT: {"accepted_positions": 15, "return_contribution_pct": 2.0},
        },
        "closed_positions": [{"symbol": "BTC-USDT-SWAP"}],
    }


def test_eligible_symbols_are_sorted_and_empty_values_are_ignored():
    coverage = {"eligible_symbols": ["ETH-USDT-SWAP", "", "BTC-USDT-SWAP"]}
    assert eligible_symbols_from_coverage(coverage) == ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]


def test_rsi_candidates_are_limited_to_declared_downtrend_regime():
    events = [
        {"id": "downtrend", "declared_compatible_regime": True},
        {"id": "range", "declared_compatible_regime": False},
        {"id": "missing"},
    ]
    assert declared_downtrend_rsi_events(events) == [events[0]]


def test_all_pre_registered_thresholds_can_pass():
    assert validation_reasons(passing_result(), {"BTC-USDT-SWAP"}) == []


def test_return_drawdown_count_and_concentration_failures_are_reported():
    result = passing_result()
    result.update(
        total_return_pct=0.0,
        max_drawdown_pct=20.1,
        accepted_positions=29,
        top_positive_month_share=0.251,
    )
    reasons = validation_reasons(result, {"BTC-USDT-SWAP"})
    assert any("return" in reason for reason in reasons)
    assert any("drawdown" in reason for reason in reasons)
    assert any("positions" in reason for reason in reasons)
    assert any("concentration" in reason for reason in reasons)


def test_each_component_must_have_count_and_positive_contribution():
    result = passing_result()
    result["component_attribution"][RSI_COMPONENT] = {
        "accepted_positions": 9,
        "return_contribution_pct": -0.1,
    }
    reasons = validation_reasons(result, {"BTC-USDT-SWAP"})
    assert any(RSI_COMPONENT in reason and "positions" in reason for reason in reasons)
    assert any(RSI_COMPONENT in reason and "contribution" in reason for reason in reasons)


def test_traded_symbol_must_be_inside_frozen_data_universe():
    result = passing_result()
    result["closed_positions"].append({"symbol": "SEI-USDT-SWAP"})
    reasons = validation_reasons(result, {"BTC-USDT-SWAP"})
    assert any("SEI-USDT-SWAP" in reason for reason in reasons)

from __future__ import annotations

from daily_rsi_mean_revert_audit import PriceBar
from downtrend_rebound_capital_constrained_simulator import (
    candidate_priority,
    marked_position_value,
    maximum_drawdown,
    simulate_portfolio,
    simulation_screen,
)


DAY_MS = 24 * 60 * 60 * 1000


def _bar(day: int, open_price: float, close_price: float | None = None) -> PriceBar:
    close = open_price if close_price is None else close_price
    return PriceBar(
        ts=day * DAY_MS,
        timestamp_utc=f"2025-01-{day + 1:02d} 00:00:00",
        open=open_price,
        high=max(open_price, close),
        low=min(open_price, close),
        close=close,
        volume=1.0,
    )


def _event(symbol: str, entry_day: int, exit_day: int, entry: float, exit_: float, rsi: float = 30.0) -> dict:
    return {
        "symbol": symbol,
        "split": "oos",
        "entry_ts": entry_day * DAY_MS,
        "entry_timestamp_utc": f"2025-01-{entry_day + 1:02d} 00:00:00",
        "exit_ts": exit_day * DAY_MS,
        "exit_timestamp_utc": f"2025-01-{exit_day + 1:02d} 00:00:00",
        "entry_price": entry,
        "exit_price": exit_,
        "signal_rsi": rsi,
    }


def test_candidate_priority_uses_lower_rsi_then_symbol():
    events = [_event("B", 0, 1, 100, 101, 20), _event("A", 0, 1, 100, 101, 20), _event("C", 0, 1, 100, 101, 30)]

    ordered = sorted(events, key=candidate_priority)

    assert [event["symbol"] for event in ordered] == ["A", "B", "C"]


def test_candidate_priority_supports_symbol_only_mode():
    events = [_event("B", 1, 2, 100, 101, 10), _event("A", 1, 2, 100, 101, 30)]

    ordered = sorted(events, key=lambda event: candidate_priority(event, "symbol"))

    assert [event["symbol"] for event in ordered] == ["A", "B"]


def test_candidate_priority_supports_pre_registered_event_score():
    events = [
        {**_event("A", 1, 2, 100, 101), "portfolio_priority": 30.0},
        {**_event("B", 1, 2, 100, 101), "portfolio_priority": 10.0},
    ]

    ordered = sorted(events, key=lambda event: candidate_priority(event, "event_score_then_symbol"))

    assert [event["symbol"] for event in ordered] == ["B", "A"]


def test_simulator_applies_capacity_and_costs():
    events = [
        _event("A", 1, 3, 100, 110, 20),
        _event("B", 1, 3, 100, 110, 21),
        _event("C", 1, 3, 100, 110, 22),
    ]
    prices = {
        symbol: {day * DAY_MS: _bar(day, 100, 105 if day == 2 else 100) for day in range(1, 4)}
        for symbol in ("A", "B", "C")
    }

    result = simulate_portfolio(events, prices, initial_capital=100_000, max_positions=2, position_fraction=0.5)

    assert result["accepted_positions"] == 2
    assert result["capacity_rejected_events"] == 1
    assert result["final_equity"] > 100_000
    assert result["max_concurrent_positions"] == 2


def test_exit_is_processed_before_same_timestamp_entry():
    events = [
        _event("A", 1, 2, 100, 100, 20),
        _event("B", 2, 3, 100, 100, 20),
    ]
    prices = {
        symbol: {day * DAY_MS: _bar(day, 100) for day in range(1, 4)}
        for symbol in ("A", "B")
    }

    result = simulate_portfolio(events, prices, max_positions=1, position_fraction=1.0)

    assert result["accepted_positions"] == 2
    assert result["capacity_rejected_events"] == 0
    assert result["max_concurrent_positions"] == 1


def test_intraday_exit_frees_capacity_on_the_same_day():
    entry_a = DAY_MS + 15 * 60 * 1000
    exit_a = 2 * DAY_MS + 6 * 60 * 60 * 1000
    entry_b = 2 * DAY_MS + 12 * 60 * 60 * 1000
    exit_b = 3 * DAY_MS + 15 * 60 * 1000
    events = [
        {**_event("A", 1, 2, 100, 100), "entry_ts": entry_a, "exit_ts": exit_a},
        {**_event("B", 2, 3, 100, 100), "entry_ts": entry_b, "exit_ts": exit_b},
    ]
    prices = {
        symbol: {day * DAY_MS: _bar(day, 100) for day in range(1, 4)}
        for symbol in ("A", "B")
    }

    result = simulate_portfolio(events, prices, max_positions=1, position_fraction=1.0)

    assert result["accepted_positions"] == 2
    assert result["capacity_rejected_events"] == 0


def test_combined_components_cannot_duplicate_active_symbol():
    events = [
        {**_event("A", 1, 3, 100, 105, 20), "component_id": "one"},
        {**_event("A", 2, 4, 101, 106, 20), "component_id": "two"},
    ]
    prices = {"A": {day * DAY_MS: _bar(day, 100) for day in range(1, 5)}}

    result = simulate_portfolio(events, prices, max_positions=5)

    assert result["accepted_positions"] == 1
    assert result["capacity_rejected_events"] == 1
    assert result["rejected_events"][0]["rejection_reason"] == "duplicate_symbol_exposure"


def test_component_position_cap_keeps_unused_capacity_in_cash():
    events = [
        {**_event("A", 1, 3, 100, 105), "component_id": "long_component"},
        {**_event("B", 1, 3, 100, 105), "component_id": "long_component"},
        {**_event("C", 1, 3, 100, 105), "component_id": "long_component"},
    ]
    prices = {
        symbol: {day * DAY_MS: _bar(day, 100) for day in range(1, 4)}
        for symbol in ("A", "B", "C")
    }

    result = simulate_portfolio(
        events,
        prices,
        max_positions=5,
        component_position_caps={"long_component": 2},
    )

    assert result["accepted_positions"] == 2
    assert result["capacity_rejected_events"] == 1
    assert result["rejected_events"][0]["rejection_reason"] == "component_position_capacity"


def test_maximum_drawdown_uses_daily_equity_curve():
    curve = [{"equity": 100.0}, {"equity": 120.0}, {"equity": 90.0}, {"equity": 110.0}]

    assert maximum_drawdown(curve) == 0.25


def test_maximum_drawdown_includes_initial_equity_peak():
    curve = [{"equity": 90.0}, {"equity": 95.0}]

    assert maximum_drawdown(curve, initial_equity=100.0) == 0.10


def test_empty_simulation_preserves_initial_capital():
    result = simulate_portfolio([], {})

    assert result["final_equity"] == 100_000.0
    assert result["total_return_pct"] == 0.0
    assert result["equity_curve"] == []


def test_short_position_gains_when_exit_price_falls():
    event = {**_event("A", 1, 3, 100, 80), "direction": "short"}
    prices = {"A": {day * DAY_MS: _bar(day, 100 if day == 1 else 90) for day in range(1, 4)}}

    result = simulate_portfolio([event], prices, max_positions=1, position_fraction=1.0)

    assert result["accepted_positions"] == 1
    assert result["final_equity"] > 100_000
    assert result["closed_positions"][0]["direction"] == "short"


def test_equity_curve_records_long_short_and_component_exposure():
    events = [
        {**_event("A", 1, 3, 100, 105), "direction": "long", "component_id": "long_component"},
        {**_event("B", 1, 3, 100, 95), "direction": "short", "component_id": "short_component"},
    ]
    prices = {
        symbol: {day * DAY_MS: _bar(day, 100) for day in range(1, 4)}
        for symbol in ("A", "B")
    }

    result = simulate_portfolio(events, prices, max_positions=2, position_fraction=0.5)
    first = result["equity_curve"][0]

    assert first["active_long_positions"] == 1
    assert first["active_short_positions"] == 1
    assert set(first["component_exposure"]) == {"long_component", "short_component"}
    assert abs(first["net_directional_exposure"]) < 0.01


def test_short_mark_value_falls_when_market_price_rises():
    position = {
        "direction": "short",
        "cash_outlay": 1000.0,
        "entry_price": 100.0,
        "quantity": 0.0,
    }

    assert marked_position_value(position, 110.0) < marked_position_value(position, 100.0)


def test_screen_blocks_excess_drawdown_and_small_sample():
    result = {
        "total_return_pct": 5.0,
        "max_drawdown_pct": 25.0,
        "accepted_positions": 10,
        "top_positive_month_share": 0.20,
    }

    reasons = simulation_screen(result)

    assert any("drawdown" in reason for reason in reasons)
    assert any("accepted positions" in reason for reason in reasons)

from dataclasses import replace
from decimal import Decimal

import pytest

from ten_u_event_trend_contract_v1 import EventTrendConfig, EventTrendFormationGate
from ten_u_event_trend_formation_v1 import (
    EntryProposal,
    FundingPoint,
    FourHourBar,
    HourBar,
    InstrumentSpec,
    aggregate_four_hour,
    evaluate_gate,
    find_ignitions,
    simulate_trade,
    wilder_atr,
    _hard_stop_fill_raw,
)
from ten_u_event_trend_data_v1 import HOUR_MS


def bars(count: int, start: int = 0, price: float = 100.0) -> list[HourBar]:
    return [
        HourBar(start + i * HOUR_MS, price, price + 1, price - 1, price, 1000)
        for i in range(count)
    ]


def spec() -> InstrumentSpec:
    return InstrumentSpec("TEST-USDT-SWAP", 1.0, 0.001, 0.001)


def proposal(entry_ts: int = 20 * HOUR_MS, direction: str = "long") -> EntryProposal:
    return EntryProposal(
        symbol="TEST-USDT-SWAP",
        direction=direction,
        ignition_ts=entry_ts - 4 * HOUR_MS,
        entry_ts=entry_ts,
        structural_invalidation=95 if direction == "long" else 105,
        atr_1h=2,
        score=3,
    )


def test_four_hour_aggregation_requires_complete_utc_groups():
    output = aggregate_four_hour(bars(7))
    assert len(output) == 1
    assert output[0].ts == 0


def test_wilder_atr_is_seeded_only_after_full_period():
    output = wilder_atr(bars(15), 14)
    assert output[12] is None
    assert output[13] == pytest.approx(2.0)
    assert output[14] == pytest.approx(2.0)


def test_ignition_baselines_exclude_trigger_bar():
    prior = [FourHourBar(i * 4 * HOUR_MS, 100, 101, 99, 100, 1000, 2) for i in range(20)]
    trigger = FourHourBar(80 * HOUR_MS, 100, 110, 99, 109, 5000, 11)
    config = replace(EventTrendConfig(), symbols=("TEST-USDT-SWAP",), prior_range_break_4h_bars=20)
    found = find_ignitions("TEST-USDT-SWAP", prior + [trigger], config, 0, 100 * HOUR_MS)
    assert len(found) == 1
    assert found[0].tr_ratio == pytest.approx(5.5)


def test_wick_through_structure_does_not_soft_exit_but_hard_stop_does():
    data = bars(80)
    data[20] = HourBar(20 * HOUR_MS, 100, 102, 93.5, 96, 1000)
    result = simulate_trade(
        proposal(), data, [], spec(), EventTrendConfig(symbols=("TEST-USDT-SWAP",)), 10, 80 * HOUR_MS
    )
    assert result["accepted"]
    assert result["exit_reason"] == "hard_disaster_stop"


def test_hard_stop_market_fill_respects_adverse_gap_at_hour_open():
    assert _hard_stop_fill_raw(HourBar(0, 90, 92, 85, 88, 1), "long", 95) == 90
    assert _hard_stop_fill_raw(HourBar(0, 100, 101, 94, 96, 1), "long", 95) == 95
    assert _hard_stop_fill_raw(HourBar(0, 110, 115, 108, 112, 1), "short", 105) == 110
    assert _hard_stop_fill_raw(HourBar(0, 100, 106, 99, 104, 1), "short", 105) == 105


def test_gap_stop_execution_uses_gap_open_and_then_slippage():
    data = bars(80)
    data[20] = HourBar(20 * HOUR_MS, 100, 101, 99, 100, 1000)
    data[21] = HourBar(21 * HOUR_MS, 90, 92, 85, 88, 1000)
    result = simulate_trade(
        proposal(), data, [], spec(), EventTrendConfig(symbols=("TEST-USDT-SWAP",)), 10, 80 * HOUR_MS
    )
    assert result["exit_reason"] == "hard_disaster_stop"
    assert result["exit_raw"] == 90
    assert result["exit_exec"] < 90


def test_hard_stop_sweep_uses_return_to_entry_over_original_trade_horizon():
    data = bars(80)
    data[20] = HourBar(20 * HOUR_MS, 100, 102, 93.5, 96, 1000)
    for index in range(21, 40):
        data[index] = HourBar(index * HOUR_MS, 98, 99, 97, 98, 1000)
    # Recovery happens 20 hours after the stop: outside the former arbitrary
    # 12h diagnostic window, but inside the original 48h intended holding horizon.
    data[40] = HourBar(40 * HOUR_MS, 99, 100.5, 98, 100, 1000)
    result = simulate_trade(
        proposal(), data, [], spec(), EventTrendConfig(symbols=("TEST-USDT-SWAP",)), 10, 80 * HOUR_MS
    )
    assert result["exit_reason"] == "hard_disaster_stop"
    assert result["hard_stop_recovered_entry"] is True
    assert result["hard_stop_recovered_1r"] is False
    assert result["hard_stop_recovery_entry_ts"] == 40 * HOUR_MS
    assert result["hard_stop_recovery_entry_hours"] == 20


def test_winner_capture_measures_price_giveback_not_funding_credit():
    data = bars(90)
    data[20] = HourBar(20 * HOUR_MS, 100, 120, 99, 110, 1000)
    data[68] = HourBar(68 * HOUR_MS, 110, 111, 109, 110, 1000)
    # Negative funding credits a long and must not improve its price-capture score.
    result = simulate_trade(
        proposal(),
        data,
        [FundingPoint(24 * HOUR_MS, -0.10)],
        spec(),
        EventTrendConfig(symbols=("TEST-USDT-SWAP",)),
        10,
        90 * HOUR_MS,
    )
    assert result["exit_reason"] == "time_48h"
    assert result["winner_capture_fraction"] == pytest.approx(0.5)
    assert result["net_winner_capture_fraction"] != pytest.approx(0.5)


def test_marked_equity_includes_estimated_exit_costs():
    result = simulate_trade(
        proposal(), bars(90), [], spec(), EventTrendConfig(symbols=("TEST-USDT-SWAP",)), 10, 90 * HOUR_MS
    )
    assert result["marks"][0]["equity"] < 10


def test_close_beyond_structure_exits_at_next_open_not_at_wick():
    data = bars(80)
    data[20] = HourBar(20 * HOUR_MS, 100, 103, 94.5, 96, 1000)
    # Put the hard stop farther away, so the 94.5 wick is tolerated.
    p = replace(proposal(), atr_1h=4)
    data[21] = HourBar(21 * HOUR_MS, 101, 102, 94.2, 94.8, 1000)
    data[22] = HourBar(22 * HOUR_MS, 97, 98, 96, 97, 1000)
    result = simulate_trade(
        p, data, [], spec(), EventTrendConfig(symbols=("TEST-USDT-SWAP",)), 10, 80 * HOUR_MS
    )
    assert result["exit_reason"] == "structural_close_invalidation"
    assert result["exit_raw"] == 97


def test_time_exit_is_48_hours_at_bar_open():
    data = bars(90)
    result = simulate_trade(
        proposal(), data, [], spec(), EventTrendConfig(symbols=("TEST-USDT-SWAP",)), 10, 90 * HOUR_MS
    )
    assert result["exit_reason"] == "time_48h"
    assert result["holding_hours"] == 48


def test_positive_funding_costs_long_and_credits_short():
    data = bars(90)
    funding = [FundingPoint(24 * HOUR_MS, 0.01)]
    config = EventTrendConfig(symbols=("TEST-USDT-SWAP",))
    long = simulate_trade(proposal(direction="long"), data, funding, spec(), config, 10, 90 * HOUR_MS)
    short = simulate_trade(proposal(direction="short"), data, funding, spec(), config, 10, 90 * HOUR_MS)
    assert long["funding_pnl"] < 0
    assert short["funding_pnl"] > 0


def test_contract_rounding_never_exceeds_requested_notional():
    rounded, quantity = InstrumentSpec("X", 10, 0.1, 0.1).round_notional(17, 2)
    assert rounded == 16
    assert quantity == 8


def test_gate_fails_on_capture_and_stop_recovery_even_if_profitable():
    report = {
        "trades": 20,
        "trades_by_symbol": {"RAVE-USDT-SWAP": 5, "LAB-USDT-SWAP": 5},
        "profit_factor": 2,
        "ending_equity": 20,
        "peak_equity": 22,
        "max_drawdown_fraction": 0.2,
        "peak_profit_retention": 0.8,
        "stopped_then_recovered_fraction": 0.5,
        "median_winner_capture": 0.2,
        "top_trade_gross_profit_contribution": 0.3,
    }
    passed, reasons = evaluate_gate(report, EventTrendFormationGate())
    assert not passed
    assert "stopped_then_recovered_above_maximum" in reasons
    assert "winner_capture_below_minimum" in reasons

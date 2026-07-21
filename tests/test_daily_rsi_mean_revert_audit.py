from __future__ import annotations

from daily_rsi_mean_revert_audit import (
    PriceBar,
    RsiSignal,
    audit_symbol,
    find_exit_index,
    format_utc,
    generate_signals,
    rsi_values,
    simulate_trade,
    split_for_signal,
    summarize,
)


DAY_MS = 24 * 60 * 60 * 1000


def _bar(day: int, close: float, open_price: float | None = None) -> PriceBar:
    ts = day * DAY_MS
    open_value = close if open_price is None else open_price
    return PriceBar(
        ts=ts,
        timestamp_utc=format_utc(ts),
        open=open_value,
        high=max(open_value, close),
        low=min(open_value, close),
        close=close,
        volume=1.0,
    )


def test_rsi_values_returns_none_until_period():
    values = rsi_values([float(item) for item in range(20)], period=14)

    assert values[13] is None
    assert values[14] == 100.0


def test_split_for_signal_uses_formation_then_oos():
    assert split_for_signal(10, 0, 20, 30) == "formation"
    assert split_for_signal(25, 0, 20, 30) == "oos"
    assert split_for_signal(35, 0, 20, 30) is None


def test_generate_signals_emits_when_rsi_below_entry_threshold():
    closes = [100.0] * 15 + [80.0, 78.0, 76.0, 74.0, 72.0]
    daily = [_bar(index, close) for index, close in enumerate(closes)]

    signals = generate_signals("BTC-USDT-SWAP", daily, 0, 40 * DAY_MS, 50 * DAY_MS)

    assert signals
    assert signals[0].split == "formation"
    assert signals[0].rsi < 35.0


def test_find_exit_index_exits_after_rsi_recovery():
    closes = [100.0] * 15 + [80.0, 78.0, 76.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0, 125.0]
    daily = [_bar(index, close) for index, close in enumerate(closes)]

    exit_index, reason = find_exit_index(daily, 16)

    assert exit_index is not None
    assert reason in {"rsi_recovery", "time"}


def test_simulate_trade_applies_round_trip_cost():
    daily = [_bar(index, 100.0) for index in range(40)]
    daily[15] = _bar(15, 80.0, 80.0)
    daily[16] = _bar(16, 90.0, 100.0)
    signal = RsiSignal("BTC-USDT-SWAP", daily[14].ts + DAY_MS, daily[15].timestamp_utc, "formation", 80.0, 20.0)

    trade = simulate_trade(signal, daily, 15)

    assert trade is not None
    assert trade.net_return_pct < trade.gross_return_pct


def test_audit_symbol_skips_overlapping_positions():
    closes = [100.0] * 15 + [80.0, 78.0, 76.0, 74.0, 72.0] + [90.0] * 30
    daily = [_bar(index, close) for index, close in enumerate(closes)]

    events = audit_symbol("BTC-USDT-SWAP", daily, 0, 60 * DAY_MS, 70 * DAY_MS)

    assert len(events) >= 1
    assert all(event.symbol == "BTC-USDT-SWAP" for event in events)


def test_summarize_reports_sum_and_win_rate():
    result = summarize([1.0, -0.5, 2.0])

    assert result["sum_pct"] == 2.5
    assert result["win_rate"] == 0.666667

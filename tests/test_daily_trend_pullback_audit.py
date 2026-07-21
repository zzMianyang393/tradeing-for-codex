from __future__ import annotations

from daily_trend_pullback_audit import (
    PullbackSignal,
    audit_symbol,
    find_exit_index,
    format_utc,
    generate_signals,
    simulate_trade,
    split_for_signal,
    summarize,
)
from daily_ma_alignment_audit import DAY_MS, PriceBar


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


def _trend_with_pullback() -> list[PriceBar]:
    closes = [100.0 + index * 0.5 for index in range(230)]
    closes[220] = closes[219] - 10.0
    closes[221] = closes[220] - 2.0
    closes[222] = closes[221] + 20.0
    return [_bar(index, close) for index, close in enumerate(closes)]


def test_split_for_signal_uses_formation_then_oos():
    assert split_for_signal(10, 0, 20, 30) == "formation"
    assert split_for_signal(25, 0, 20, 30) == "oos"
    assert split_for_signal(35, 0, 20, 30) is None


def test_generate_signals_requires_trend_context_and_pullback():
    daily = _trend_with_pullback()

    signals = generate_signals("BTC-USDT-SWAP", daily, 0, 300 * DAY_MS, 400 * DAY_MS)

    assert signals
    assert signals[0].symbol == "BTC-USDT-SWAP"


def test_find_exit_index_exits_on_ema_recovery_or_time():
    daily = _trend_with_pullback()

    exit_index, reason = find_exit_index(daily, 221)

    assert exit_index is not None
    assert reason in {"ema20_recovery", "time"}


def test_simulate_trade_sets_long_direction_and_cost():
    daily = _trend_with_pullback()
    signal = PullbackSignal("BTC-USDT-SWAP", daily[220].ts + DAY_MS, daily[221].timestamp_utc, "formation", 100.0, 100.0, 99.0, 90.0)

    trade = simulate_trade(signal, daily, 221)

    assert trade is not None
    assert trade.direction == "long"
    assert trade.net_return_pct < trade.gross_return_pct


def test_audit_symbol_returns_non_overlapping_events():
    daily = _trend_with_pullback()

    events = audit_symbol("BTC-USDT-SWAP", daily, 0, 300 * DAY_MS, 400 * DAY_MS)

    assert len(events) >= 1
    assert all(event.direction == "long" for event in events)


def test_summarize_reports_sum_and_win_rate():
    result = summarize([1.0, -0.5, 2.0])

    assert result["sum_pct"] == 2.5
    assert result["win_rate"] == 0.666667

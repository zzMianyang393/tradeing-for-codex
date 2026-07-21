from __future__ import annotations

import unittest

from utc_session_breakout_audit import (
    ATR_STOP_MULTIPLE,
    ATR_TARGET_MULTIPLE,
    FIFTEEN_MINUTES_MS,
    BreakoutSignal,
    PriceBar,
    formation_verdict,
    generate_signals,
    parse_timestamp_ms,
    rolling_atr,
    simulate_trade,
)


def bar(ts: int, open_: float, high: float, low: float, close: float) -> PriceBar:
    return PriceBar(ts, "ts", open_, high, low, close, 1.0)


class UtcSessionBreakoutAuditTests(unittest.TestCase):
    def test_rolling_atr_waits_for_fourteen_completed_15m_bars(self):
        bars = [bar(i * FIFTEEN_MINUTES_MS, 10, 12, 9, 11) for i in range(14)]
        atr = rolling_atr(bars)
        self.assertIsNone(atr[12])
        self.assertIsNotNone(atr[13])

    def test_signal_uses_close_breakout_after_range_completion(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        bars = []
        for i in range(16):
            bars.append(bar(start + i * FIFTEEN_MINUTES_MS, 100, 105, 95, 100))
        bars.append(bar(start + 16 * FIFTEEN_MINUTES_MS, 100, 106, 99, 104))
        bars.append(bar(start + 17 * FIFTEEN_MINUTES_MS, 104, 107, 103, 106))
        bars.append(bar(start + 18 * FIFTEEN_MINUTES_MS, 106, 107, 105, 106))
        signals = generate_signals(
            "BTC-USDT-SWAP",
            bars,
            parse_timestamp_ms("2024-01-01 00:00:00"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertEqual(1, len(signals))
        self.assertEqual(start + 18 * FIFTEEN_MINUTES_MS, signals[0].signal_ts)
        self.assertEqual(105, signals[0].range_high)

    def test_no_signal_from_intrabar_wick_only(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        bars = []
        for i in range(16):
            bars.append(bar(start + i * FIFTEEN_MINUTES_MS, 100, 105, 95, 100))
        bars.append(bar(start + 16 * FIFTEEN_MINUTES_MS, 100, 106, 99, 104))
        bars.append(bar(start + 17 * FIFTEEN_MINUTES_MS, 104, 104.5, 103, 104))
        signals = generate_signals(
            "BTC-USDT-SWAP",
            bars,
            parse_timestamp_ms("2024-01-01 00:00:00"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertEqual([], signals)

    def test_simulate_trade_checks_stop_before_target(self):
        signal_ts = parse_timestamp_ms("2024-01-01 04:30:00")
        signal = BreakoutSignal("BTC-USDT-SWAP", signal_ts, "2024-01-01 04:30:00", signal_ts, signal_ts, 105, 95, 2, "formation")
        bars = [bar(signal_ts, 100, 100 + ATR_TARGET_MULTIPLE * 2 + 1, 100 - ATR_STOP_MULTIPLE * 2 - 1, 101)]
        trade = simulate_trade(signal, bars, 0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("stop", trade.exit_reason)
        self.assertAlmostEqual(96.0, trade.exit_price)

    def test_simulate_trade_exits_at_target(self):
        signal_ts = parse_timestamp_ms("2024-01-01 04:30:00")
        signal = BreakoutSignal("BTC-USDT-SWAP", signal_ts, "2024-01-01 04:30:00", signal_ts, signal_ts, 105, 95, 2, "formation")
        bars = [bar(signal_ts, 100, 106, 99, 105)]
        trade = simulate_trade(signal, bars, 0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("target", trade.exit_reason)
        self.assertAlmostEqual(106.0, trade.exit_price)

    def test_formation_verdict_requires_pre_registered_gates(self):
        summary = {
            "formation": {
                "all": {
                    "observations": 60,
                    "mean_pct": 0.1,
                    "win_rate": 0.44,
                    "profit_factor": 1.3,
                }
            }
        }
        verdict = formation_verdict(summary, {"top_symbol_profit_share": 0.1, "top_month_event_share": 0.1})
        self.assertEqual("rejected", verdict["status"])
        self.assertFalse(verdict["eligible_for_strategy"])


if __name__ == "__main__":
    unittest.main()

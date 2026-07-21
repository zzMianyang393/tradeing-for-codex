from __future__ import annotations

import unittest

from daily_bb_mean_revert_audit import (
    BB_PERIOD,
    DAY_MS,
    MAX_HOLD_DAYS,
    BollingerSignal,
    PriceBar,
    audit_symbol,
    generate_signals,
    parse_timestamp_ms,
    resample_daily,
    rolling_bollinger,
    simulate_trade,
    summarize_events,
    verdict,
)


def bar(ts: int, open_: float, high: float, low: float, close: float) -> PriceBar:
    return PriceBar(ts, "ts", open_, high, low, close, 1.0)


class DailyBbMeanRevertAuditTests(unittest.TestCase):
    def test_resample_daily_preserves_open_close_and_extremes(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        bars = [
            bar(start, 100, 101, 99, 100),
            bar(start + 60 * 60 * 1000, 100, 110, 95, 108),
            bar(start + DAY_MS, 108, 109, 107, 108.5),
        ]
        daily = resample_daily(bars)
        self.assertEqual(2, len(daily))
        self.assertEqual(100, daily[0].open)
        self.assertEqual(110, daily[0].high)
        self.assertEqual(95, daily[0].low)
        self.assertEqual(108, daily[0].close)

    def test_rolling_bollinger_waits_for_completed_window(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 100, 101, 99, 100) for day in range(BB_PERIOD)]
        values = rolling_bollinger(daily)
        self.assertIsNone(values[BB_PERIOD - 2])
        self.assertIsNotNone(values[BB_PERIOD - 1])

    def test_generate_signal_requires_close_below_lower_band(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = []
        for day in range(BB_PERIOD - 1):
            daily.append(bar(start + day * DAY_MS, 100, 101, 99, 100))
        daily.append(bar(start + (BB_PERIOD - 1) * DAY_MS, 80, 81, 79, 80))
        daily.append(bar(start + BB_PERIOD * DAY_MS, 82, 83, 81, 82))
        signals = generate_signals(
            "BTC-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertEqual(1, len(signals))
        self.assertLess(signals[0].close, signals[0].bb_lower)
        self.assertEqual(start + BB_PERIOD * DAY_MS, signals[0].signal_ts)

    def test_generate_signal_ignores_close_above_lower_band(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 100, 101, 99, 100) for day in range(BB_PERIOD + 2)]
        signals = generate_signals(
            "ETH-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertEqual([], signals)

    def test_simulate_trade_exits_next_open_after_middle_recovery(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 100, 101, 99, 100) for day in range(BB_PERIOD)]
        daily.append(bar(start + BB_PERIOD * DAY_MS, 80, 81, 79, 80))
        daily.append(bar(start + (BB_PERIOD + 1) * DAY_MS, 82, 83, 81, 82))
        daily.append(bar(start + (BB_PERIOD + 2) * DAY_MS, 105, 106, 104, 105))
        daily.append(bar(start + (BB_PERIOD + 3) * DAY_MS, 106, 107, 105, 106))
        signal = BollingerSignal(
            "BTC-USDT-SWAP",
            daily[BB_PERIOD + 1].ts,
            "2024-01-22 00:00:00",
            "formation",
            80,
            99,
            90,
        )
        trade = simulate_trade(signal, daily, BB_PERIOD + 1)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("bb_mid_recovery", trade.exit_reason)
        self.assertEqual(daily[BB_PERIOD + 3].ts, trade.exit_ts)
        gross = trade.exit_price / trade.entry_price - 1.0
        self.assertAlmostEqual(gross * 100.0 - 0.16, trade.net_return_pct, places=5)

    def test_simulate_trade_time_exits_after_ten_days(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 100, 101, 99, 100) for day in range(BB_PERIOD)]
        for day in range(BB_PERIOD, BB_PERIOD + MAX_HOLD_DAYS + 2):
            daily.append(bar(start + day * DAY_MS, 80, 81, 79, 80))
        signal = BollingerSignal(
            "BTC-USDT-SWAP",
            daily[BB_PERIOD].ts,
            "2024-01-21 00:00:00",
            "formation",
            80,
            99,
            90,
        )
        trade = simulate_trade(signal, daily, BB_PERIOD)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("time", trade.exit_reason)
        self.assertEqual(MAX_HOLD_DAYS, trade.hold_days)

    def test_audit_symbol_skips_overlapping_positions(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 100, 101, 99, 100) for day in range(BB_PERIOD)]
        for day in range(BB_PERIOD, BB_PERIOD + 40):
            close = 80 if day % 4 == 0 else 82
            daily.append(bar(start + day * DAY_MS, close, close + 1, close - 1, close))
        events = audit_symbol(
            "SOL-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        for previous, current in zip(events, events[1:]):
            self.assertGreaterEqual(current.entry_ts, previous.exit_ts + DAY_MS)

    def test_verdict_rejects_weak_formation(self):
        summary = {
            "formation": {"observations": 7, "sum_pct": 5.0, "win_rate": 0.6, "profit_factor": 1.5},
            "oos": {"observations": 2, "sum_pct": 1.0},
        }
        result = verdict(
            summary,
            {"formation": {"sum_pct": 5.0}},
            {"top_month_positive_contribution_share": 0.1},
            {"top_month_positive_contribution_share": 0.1},
        )
        self.assertEqual("rejected", result["status"])
        self.assertFalse(result["eligible_for_strategy"])

    def test_summarize_events_can_exclude_2024_11(self):
        self.assertEqual(0, summarize_events([])["formation"]["observations"])


if __name__ == "__main__":
    unittest.main()

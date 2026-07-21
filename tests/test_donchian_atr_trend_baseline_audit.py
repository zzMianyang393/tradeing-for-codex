from __future__ import annotations

import unittest

from donchian_atr_trend_baseline_audit import (
    ATR_STOP_MULTIPLE,
    DAY_MS,
    DailySignal,
    PriceBar,
    audit_symbol,
    formation_verdict,
    generate_signals,
    parse_timestamp_ms,
    resample_daily,
    rolling_atr,
    simulate_trade,
    summarize_events,
)


def bar(ts: int, open_: float, high: float, low: float, close: float) -> PriceBar:
    return PriceBar(ts, "ts", open_, high, low, close, 1.0)


class DonchianAtrTrendBaselineAuditTests(unittest.TestCase):
    def test_resample_daily_uses_full_day_extremes(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        bars = [
            bar(start, 100, 101, 99, 100),
            bar(start + 15 * 60 * 1000, 100, 105, 98, 104),
            bar(start + DAY_MS, 104, 106, 103, 105),
        ]
        daily = resample_daily(bars)
        self.assertEqual(2, len(daily))
        self.assertEqual(100, daily[0].open)
        self.assertEqual(105, daily[0].high)
        self.assertEqual(98, daily[0].low)
        self.assertEqual(104, daily[0].close)

    def test_rolling_atr_waits_for_fourteen_completed_days(self):
        daily = [bar(i * DAY_MS, 10, 12, 9, 11) for i in range(14)]
        atr = rolling_atr(daily)
        self.assertIsNone(atr[12])
        self.assertIsNotNone(atr[13])

    def test_signal_uses_prior_twenty_days_without_lookahead(self):
        formation_start = parse_timestamp_ms("2024-01-01 00:00:00")
        formation_end = parse_timestamp_ms("2024-12-31 23:59:59")
        oos_end = parse_timestamp_ms("2025-07-10 23:59:59")
        daily = []
        for i in range(20):
            daily.append(bar(formation_start + i * DAY_MS, 100, 110, 90, 100))
        daily.append(bar(formation_start + 20 * DAY_MS, 100, 112, 99, 111))
        signals = generate_signals("BTC-USDT-SWAP", daily, formation_start, formation_end, oos_end)
        self.assertEqual(1, len(signals))
        self.assertEqual("long", signals[0].direction)
        self.assertEqual(110, signals[0].donchian_high)

    def test_simulate_long_trade_exits_at_fixed_stop(self):
        signal_ts = parse_timestamp_ms("2024-02-01 00:00:00")
        signal = DailySignal(
            "BTC-USDT-SWAP",
            signal_ts,
            "2024-02-01 00:00:00",
            "long",
            120.0,
            110.0,
            90.0,
            5.0,
            "formation",
        )
        bars = [
            bar(signal_ts + 15 * 60 * 1000, 100, 101, 99, 100),
            bar(signal_ts + 30 * 60 * 1000, 100, 101, 100 - ATR_STOP_MULTIPLE * 5.0 - 0.1, 99),
        ]
        trade = simulate_trade(signal, bars, 0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("stop", trade.exit_reason)
        self.assertAlmostEqual(90.0, trade.exit_price)

    def test_audit_symbol_skips_overlapping_signals(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        bars = []
        for day in range(70):
            base = 100 + day
            for slot in range(96):
                ts = start + day * DAY_MS + slot * 15 * 60 * 1000
                bars.append(bar(ts, base, base + 1, base - 1, base + 0.5))
        events = audit_symbol(
            "BTC-USDT-SWAP",
            bars,
            parse_timestamp_ms("2024-01-01 00:00:00"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertGreater(len(events), 0)
        for previous, current in zip(events, events[1:]):
            self.assertGreaterEqual(current.entry_ts, previous.exit_ts + 15 * 60 * 1000)

    def test_formation_verdict_requires_all_pre_registered_gates(self):
        summary = {
            "formation": {
                "all": {
                    "observations": 49,
                    "mean_pct": 1.0,
                    "win_rate": 0.5,
                    "profit_factor": 1.3,
                }
            }
        }
        verdict = formation_verdict(summary, {"top_symbol_share": 0.1, "top_month_share": 0.1})
        self.assertEqual("rejected", verdict["status"])
        self.assertFalse(verdict["eligible_for_strategy"])

    def test_summarize_events_reports_profit_factor(self):
        signal_ts = parse_timestamp_ms("2024-02-01 00:00:00")
        signal = DailySignal("BTC-USDT-SWAP", signal_ts, "2024-02-01 00:00:00", "short", 80, 110, 90, 5, "formation")
        bars = [
            bar(signal_ts + 15 * 60 * 1000, 100, 101, 99, 100),
            bar(signal_ts + 10 * DAY_MS, 90, 91, 89, 90),
        ]
        trade = simulate_trade(signal, bars, 0)
        assert trade is not None
        summary = summarize_events([trade])
        self.assertEqual(1, summary["formation"]["all"]["observations"])
        self.assertIn("profit_factor", summary["formation"]["all"])


if __name__ == "__main__":
    unittest.main()

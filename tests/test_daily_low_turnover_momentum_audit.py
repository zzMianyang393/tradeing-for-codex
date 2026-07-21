from __future__ import annotations

import unittest

from daily_low_turnover_momentum_audit import (
    DAY_MS,
    HOLD_DAYS,
    MOMENTUM_DAYS,
    MomentumSignal,
    PriceBar,
    audit_symbol,
    concentration,
    generate_signals,
    parse_timestamp_ms,
    resample_daily,
    simulate_trade,
    summarize_events,
    verdict,
)


def bar(ts: int, open_: float, high: float, low: float, close: float) -> PriceBar:
    return PriceBar(ts, "ts", open_, high, low, close, 1.0)


class DailyLowTurnoverMomentumAuditTests(unittest.TestCase):
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

    def test_signal_uses_completed_ninety_day_momentum_without_grid(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        daily = [bar(start + day * DAY_MS, 100 + day, 101 + day, 99 + day, 100 + day) for day in range(100)]
        signals = generate_signals(
            "BTC-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertGreater(len(signals), 0)
        self.assertEqual(start + (MOMENTUM_DAYS + 1) * DAY_MS, signals[0].signal_ts)
        self.assertGreater(signals[0].momentum_pct, 0)

    def test_negative_momentum_does_not_emit_signal(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        daily = [bar(start + day * DAY_MS, 200 - day, 201 - day, 199 - day, 200 - day) for day in range(100)]
        signals = generate_signals(
            "ETH-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertEqual([], signals)

    def test_simulate_trade_holds_thirty_days_and_charges_cost(self):
        signal_ts = parse_timestamp_ms("2024-06-01")
        signal = MomentumSignal("BTC-USDT-SWAP", signal_ts, "2024-06-01 00:00:00", "formation", 120, 100, 20)
        daily = [bar(signal_ts + day * DAY_MS, 100, 101, 99, 100 + day) for day in range(HOLD_DAYS + 1)]
        trade = simulate_trade(signal, daily, 0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual(HOLD_DAYS, trade.hold_days)
        self.assertAlmostEqual(30.0 - 0.16, trade.net_return_pct)

    def test_audit_symbol_skips_overlapping_monthly_positions(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 100 + day, 101 + day, 99 + day, 100 + day) for day in range(220)]
        events = audit_symbol(
            "SOL-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertGreater(len(events), 1)
        for previous, current in zip(events, events[1:]):
            self.assertGreaterEqual(current.entry_ts, previous.exit_ts + DAY_MS)

    def test_audit_symbol_does_not_use_exit_after_oos_end(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 100 + day, 101 + day, 99 + day, 100 + day) for day in range(160)]
        oos_end = start + 130 * DAY_MS
        events = audit_symbol(
            "BTC-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            oos_end,
        )
        self.assertTrue(events)
        self.assertTrue(all(event.exit_ts <= oos_end for event in events))

    def test_verdict_rejects_small_or_concentrated_evidence(self):
        summary = {
            "formation": {"observations": 19, "sum_pct": 10.0},
            "oos": {"observations": 3, "sum_pct": 5.0},
        }
        result = verdict(
            summary,
            {"top_month_positive_contribution_share": 0.1},
            {"top_month_positive_contribution_share": 0.1},
        )
        self.assertEqual("rejected", result["status"])
        self.assertFalse(result["eligible_for_strategy"])

    def test_summary_and_concentration_are_reportable(self):
        signal_ts = parse_timestamp_ms("2024-06-01")
        signal = MomentumSignal("BTC-USDT-SWAP", signal_ts, "2024-06-01 00:00:00", "formation", 120, 100, 20)
        daily = [bar(signal_ts + day * DAY_MS, 100, 101, 99, 100 + day) for day in range(HOLD_DAYS + 1)]
        trade = simulate_trade(signal, daily, 0)
        assert trade is not None
        summary = summarize_events([trade])
        self.assertEqual(1, summary["formation"]["observations"])
        month_stats = concentration([trade], "formation")
        self.assertEqual(1.0, month_stats["top_month_event_share"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from daily_ma_alignment_audit import (
    DAY_MS,
    EMA_FAST,
    EMA_MID,
    EMA_SLOW,
    AlignmentSignal,
    PriceBar,
    audit_symbol,
    ema_values,
    generate_signals,
    parse_timestamp_ms,
    resample_daily,
    simulate_trade,
    summarize_events,
    verdict,
)


def bar(ts: int, open_: float, high: float, low: float, close: float) -> PriceBar:
    return PriceBar(ts, "ts", open_, high, low, close, 1.0)


class DailyMaAlignmentAuditTests(unittest.TestCase):
    def test_ema_values_are_none_until_seed_window(self):
        values = [float(i) for i in range(1, EMA_FAST + 2)]
        result = ema_values(values, EMA_FAST)
        self.assertIsNone(result[EMA_FAST - 2])
        self.assertIsNotNone(result[EMA_FAST - 1])
        self.assertIsNotNone(result[EMA_FAST])

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

    def test_generate_signals_emits_only_first_alignment(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 100 + day, 101 + day, 99 + day, 100 + day) for day in range(EMA_SLOW + 30)]
        signals = generate_signals(
            "BTC-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertEqual(1, len(signals))
        self.assertGreater(signals[0].ema_fast, signals[0].ema_mid)
        self.assertGreater(signals[0].ema_mid, signals[0].ema_slow)

    def test_flat_or_downtrend_does_not_emit_signal(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = [bar(start + day * DAY_MS, 300 - day, 301 - day, 299 - day, 300 - day) for day in range(EMA_SLOW + 30)]
        signals = generate_signals(
            "ETH-USDT-SWAP",
            daily,
            parse_timestamp_ms("2024-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertEqual([], signals)

    def test_simulate_trade_exits_next_open_after_cross_under_and_charges_cost(self):
        start = parse_timestamp_ms("2024-01-01")
        daily = []
        for day in range(EMA_SLOW + 20):
            close = 100 + day
            daily.append(bar(start + day * DAY_MS, close, close + 1, close - 1, close))
        for day in range(EMA_SLOW + 20, EMA_SLOW + 90):
            close = 320 - (day - (EMA_SLOW + 20)) * 4
            daily.append(bar(start + day * DAY_MS, close, close + 1, close - 1, close))

        signal = AlignmentSignal(
            "BTC-USDT-SWAP",
            daily[EMA_SLOW].ts + DAY_MS,
            "2024-01-01 00:00:00",
            "formation",
            daily[EMA_SLOW].close,
            120,
            110,
            100,
        )
        trade = simulate_trade(signal, daily, EMA_SLOW + 1)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("ema20_cross_under_ema50", trade.exit_reason)
        self.assertGreater(trade.hold_days, 0)
        gross = trade.exit_price / trade.entry_price - 1.0
        self.assertAlmostEqual(gross * 100.0 - 0.16, trade.net_return_pct, places=5)

    def test_audit_symbol_skips_overlapping_positions(self):
        start = parse_timestamp_ms("2023-01-01")
        daily = [bar(start + day * DAY_MS, 100 + day, 101 + day, 99 + day, 100 + day) for day in range(EMA_SLOW + 40)]
        for day in range(EMA_SLOW + 40, EMA_SLOW + 95):
            close = 340 - (day - (EMA_SLOW + 40)) * 5
            daily.append(bar(start + day * DAY_MS, close, close + 1, close - 1, close))
        for day in range(EMA_SLOW + 95, EMA_SLOW + 180):
            close = 100 + (day - (EMA_SLOW + 95)) * 4
            daily.append(bar(start + day * DAY_MS, close, close + 1, close - 1, close))

        events = audit_symbol(
            "SOL-USDT-SWAP",
            daily,
            parse_timestamp_ms("2023-01-01"),
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        self.assertGreaterEqual(len(events), 1)
        for previous, current in zip(events, events[1:]):
            self.assertGreaterEqual(current.entry_ts, previous.exit_ts + DAY_MS)

    def test_verdict_rejects_small_or_concentrated_evidence(self):
        summary = {
            "formation": {"observations": 7, "sum_pct": 10.0},
            "oos": {"observations": 2, "sum_pct": 5.0},
        }
        result = verdict(
            summary,
            {"formation": {"sum_pct": 10.0}},
            {"top_month_positive_contribution_share": 0.1},
            {"top_month_positive_contribution_share": 0.1},
        )
        self.assertEqual("rejected", result["status"])
        self.assertFalse(result["eligible_for_strategy"])

    def test_summarize_events_can_exclude_2024_11(self):
        start = parse_timestamp_ms("2024-11-01")
        daily = [bar(start + day * DAY_MS, 100, 101, 99, 100 + day) for day in range(EMA_SLOW + 2)]
        signal = AlignmentSignal("BTC-USDT-SWAP", start, "2024-11-01 00:00:00", "formation", 100, 120, 110, 100)
        trade = simulate_trade(signal, daily, 0)
        self.assertIsNone(trade)
        summary = summarize_events([])
        self.assertEqual(0, summary["formation"]["observations"])


if __name__ == "__main__":
    unittest.main()

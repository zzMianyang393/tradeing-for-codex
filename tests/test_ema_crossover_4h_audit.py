from __future__ import annotations

import unittest

from ema_crossover_4h_audit import (
    EMA_FAST,
    EMA_SLOW,
    FIFTEEN_MINUTES_MS,
    FOUR_HOURS_MS,
    EmaSignal,
    PriceBar,
    audit_symbol,
    ema_values,
    formation_verdict,
    generate_signals,
    month_excluded_summary,
    parse_timestamp_ms,
    resample_4h,
    simulate_trade,
)


def bar(ts: int, open_: float, high: float, low: float, close: float) -> PriceBar:
    return PriceBar(ts, "ts", open_, high, low, close, 1.0)


class EmaCrossover4hAuditTests(unittest.TestCase):
    def test_resample_4h_uses_completed_bucket_extremes(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        bars = [
            bar(start, 100, 101, 99, 100),
            bar(start + FIFTEEN_MINUTES_MS, 100, 105, 98, 104),
            bar(start + FOUR_HOURS_MS, 104, 106, 103, 105),
        ]
        result = resample_4h(bars)
        self.assertEqual(2, len(result))
        self.assertEqual(105, result[0].high)
        self.assertEqual(98, result[0].low)
        self.assertEqual(104, result[0].close)

    def test_ema_values_wait_for_full_period(self):
        bars = [bar(i * FOUR_HOURS_MS, 10, 11, 9, float(i + 1)) for i in range(EMA_FAST)]
        values = ema_values(bars, EMA_FAST)
        self.assertIsNone(values[EMA_FAST - 2])
        self.assertIsNotNone(values[EMA_FAST - 1])

    def test_generate_signals_detects_completed_cross_without_lookahead(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        formation_end = parse_timestamp_ms("2024-12-31 23:59:59")
        oos_end = parse_timestamp_ms("2025-07-10 23:59:59")
        bars = []
        for i in range(EMA_SLOW + 10):
            close = 100.0 if i < EMA_SLOW else 100.0 + (i - EMA_SLOW + 1) * 5.0
            bars.append(bar(start + i * FOUR_HOURS_MS, close, close + 1, close - 1, close))
        signals = generate_signals("BTC-USDT-SWAP", bars, start, formation_end, oos_end)
        self.assertTrue(any(signal.direction == "long" for signal in signals))

    def test_simulate_trade_exits_on_opposite_cross_before_time(self):
        signal_ts = parse_timestamp_ms("2024-02-01 00:00:00")
        signal = EmaSignal("BTC-USDT-SWAP", signal_ts, "2024-02-01 00:00:00", "long", 101, 100, "formation")
        opposite = EmaSignal(
            "BTC-USDT-SWAP",
            signal_ts + 8 * FOUR_HOURS_MS,
            "2024-02-02 08:00:00",
            "short",
            99,
            100,
            "formation",
        )
        bars = [
            bar(signal_ts + FIFTEEN_MINUTES_MS, 100, 101, 99, 100),
            bar(opposite.signal_ts + FIFTEEN_MINUTES_MS, 105, 106, 104, 105),
        ]
        trade = simulate_trade(signal, bars, 0, opposite)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("opposite_cross", trade.exit_reason)
        self.assertEqual(opposite.signal_ts + FIFTEEN_MINUTES_MS, trade.exit_ts)

    def test_audit_symbol_skips_overlapping_signals(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        bars = []
        for slot in range(16 * 180):
            ts = start + slot * FIFTEEN_MINUTES_MS
            wave = 10 if (slot // 64) % 2 == 0 else -10
            close = 100 + wave + (slot % 64) * (0.1 if wave > 0 else -0.1)
            bars.append(bar(ts, close, close + 1, close - 1, close))
        events = audit_symbol(
            "BTC-USDT-SWAP",
            bars,
            start,
            parse_timestamp_ms("2024-12-31 23:59:59"),
            parse_timestamp_ms("2025-07-10 23:59:59"),
        )
        for previous, current in zip(events, events[1:]):
            self.assertGreaterEqual(current.entry_ts, previous.exit_ts + FIFTEEN_MINUTES_MS)

    def test_month_excluded_summary_removes_2024_11(self):
        signal_ts = parse_timestamp_ms("2024-11-01 00:00:00")
        signal = EmaSignal("BTC-USDT-SWAP", signal_ts, "2024-11-01 00:00:00", "long", 101, 100, "formation")
        bars = [bar(signal_ts + FIFTEEN_MINUTES_MS, 100, 101, 99, 100), bar(signal_ts + 2 * FIFTEEN_MINUTES_MS, 101, 102, 100, 101)]
        trade = simulate_trade(signal, bars, 0, None)
        assert trade is not None
        result = month_excluded_summary([trade], "formation")
        self.assertEqual(1, result["excluded_events"])
        self.assertEqual(0, result["kept_events"])

    def test_formation_verdict_rejects_negative_ex_2024_11_mean(self):
        summary = {
            "formation": {
                "all": {
                    "observations": 60,
                    "mean_pct": 1.0,
                    "win_rate": 0.5,
                    "profit_factor": 1.2,
                }
            }
        }
        ex_2024_11 = {"kept_summary": {"mean_pct": -0.1, "win_rate": 0.5}}
        verdict = formation_verdict(summary, {"top_symbol_event_share": 0.1, "top_month_event_share": 0.1}, ex_2024_11)
        self.assertEqual("rejected", verdict["status"])
        self.assertFalse(verdict["eligible_for_strategy"])


if __name__ == "__main__":
    unittest.main()

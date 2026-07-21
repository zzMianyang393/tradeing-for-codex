from __future__ import annotations

import unittest

from range_regime_mean_reversion_audit import (
    ATR_STOP_MULTIPLE,
    FIFTEEN_MINUTES_MS,
    FOUR_HOURS_MS,
    FourHourSignal,
    PriceBar,
    formation_verdict,
    generate_signals,
    parse_timestamp_ms,
    resample_4h,
    rolling_atr,
    rolling_bollinger,
    simulate_trade,
)


def bar(ts: int, open_: float, high: float, low: float, close: float) -> PriceBar:
    return PriceBar(ts, "ts", open_, high, low, close, 1.0)


class RangeRegimeMeanReversionAuditTests(unittest.TestCase):
    def test_resample_4h_uses_full_bucket_extremes(self):
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

    def test_rolling_indicators_wait_for_completed_windows(self):
        bars = [bar(i * FOUR_HOURS_MS, 10, 12, 9, 11) for i in range(20)]
        self.assertIsNone(rolling_atr(bars)[12])
        self.assertIsNotNone(rolling_atr(bars)[13])
        self.assertIsNone(rolling_bollinger(bars)[18])
        self.assertIsNotNone(rolling_bollinger(bars)[19])

    def test_signal_requires_range_regime_and_close_below_lower_band(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        formation_end = parse_timestamp_ms("2024-12-31 23:59:59")
        oos_end = parse_timestamp_ms("2025-07-10 23:59:59")
        bars = []
        for i in range(20):
            close = 100.0 if i < 19 else 80.0
            bars.append(bar(start + i * FOUR_HOURS_MS, close, close + 1, close - 1, close))
        labels = [(item.ts + FOUR_HOURS_MS, "震荡") for item in bars]
        signals = generate_signals("BTC-USDT-SWAP", bars, labels, start, formation_end, oos_end)
        self.assertEqual(1, len(signals))
        self.assertEqual("震荡", signals[0].regime)
        self.assertLess(signals[0].close, signals[0].bb_lower)

    def test_signal_rejects_non_range_regime(self):
        start = parse_timestamp_ms("2024-01-01 00:00:00")
        formation_end = parse_timestamp_ms("2024-12-31 23:59:59")
        oos_end = parse_timestamp_ms("2025-07-10 23:59:59")
        bars = []
        for i in range(20):
            close = 100.0 if i < 19 else 80.0
            bars.append(bar(start + i * FOUR_HOURS_MS, close, close + 1, close - 1, close))
        labels = [(item.ts + FOUR_HOURS_MS, "趋势下行") for item in bars]
        signals = generate_signals("BTC-USDT-SWAP", bars, labels, start, formation_end, oos_end)
        self.assertEqual([], signals)

    def test_simulate_trade_checks_stop_before_target(self):
        signal_ts = parse_timestamp_ms("2024-02-01 04:00:00")
        signal = FourHourSignal("BTC-USDT-SWAP", signal_ts, "2024-02-01 04:00:00", 90, 100, 92, 4, "震荡", "formation")
        bars = [
            bar(signal_ts + FIFTEEN_MINUTES_MS, 95, 101, 95 - ATR_STOP_MULTIPLE * 4 - 0.1, 96),
            bar(signal_ts + 2 * FIFTEEN_MINUTES_MS, 96, 97, 95, 96),
        ]
        trade = simulate_trade(signal, bars, 0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("stop", trade.exit_reason)
        self.assertAlmostEqual(89.0, trade.exit_price)

    def test_simulate_trade_exits_at_target(self):
        signal_ts = parse_timestamp_ms("2024-02-01 04:00:00")
        signal = FourHourSignal("BTC-USDT-SWAP", signal_ts, "2024-02-01 04:00:00", 90, 100, 92, 4, "震荡", "formation")
        bars = [bar(signal_ts + FIFTEEN_MINUTES_MS, 95, 101, 94, 100)]
        trade = simulate_trade(signal, bars, 0)
        self.assertIsNotNone(trade)
        assert trade is not None
        self.assertEqual("target", trade.exit_reason)
        self.assertAlmostEqual(100.0, trade.exit_price)

    def test_formation_verdict_requires_pre_registered_gates(self):
        summary = {
            "formation": {
                "all": {
                    "observations": 30,
                    "mean_pct": 0.1,
                    "win_rate": 0.54,
                    "profit_factor": 1.3,
                }
            }
        }
        verdict = formation_verdict(summary, {"top_symbol_profit_share": 0.1, "top_month_event_share": 0.1})
        self.assertEqual("rejected", verdict["status"])
        self.assertFalse(verdict["eligible_for_strategy"])


if __name__ == "__main__":
    unittest.main()

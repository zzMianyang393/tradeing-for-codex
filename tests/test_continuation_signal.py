import unittest
from dataclasses import replace

from config import BacktestConfig
from market import FeatureBar
from strategy import continuation_signal_for


def _trend_bars(direction: int) -> list[FeatureBar]:
    bars = []
    base = 100.0
    for idx in range(280):
        close = base + direction * idx * 0.08
        if idx == 279:
            close += direction * 2.0
        high = close + 0.5
        low = close - 0.5
        donchian_high = high - 0.2 if direction > 0 else high + 3.0
        donchian_low = low - 3.0 if direction > 0 else low + 0.2
        if idx == 279 and direction > 0:
            donchian_high = close * 0.998
        if idx == 279 and direction < 0:
            donchian_low = close * 1.002
        bars.append(
            FeatureBar(
                ts=1_700_000_000_000 + idx * 15 * 60_000,
                time=str(idx),
                open=close - direction * 0.2,
                high=high,
                low=low,
                close=close,
                volume_quote=2_000_000.0,
                ema20=close - direction * 0.6,
                ema50=close - direction * 1.2,
                ema200=close - direction * 2.0,
                atr=0.8,
                atr_pct=0.007,
                rsi=58.0 if direction > 0 else 42.0,
                vol_sma=1_000_000.0,
                donchian_high=donchian_high,
                donchian_low=donchian_low,
                trend_strength=1.8 * direction,
            )
        )
    return bars


class ContinuationSignalTests(unittest.TestCase):
    def test_disabled_by_default(self):
        bars = _trend_bars(1)

        signal = continuation_signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, BacktestConfig())

        self.assertIsNone(signal)

    def test_emits_long_on_volume_backed_uptrend_breakout(self):
        cfg = replace(BacktestConfig(), enable_continuation_module=True)
        bars = _trend_bars(1)

        signal = continuation_signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(1, signal.direction)
        self.assertEqual("continuation_long", signal.reason)

    def test_emits_short_on_volume_backed_downtrend_breakdown(self):
        cfg = replace(BacktestConfig(), enable_continuation_module=True)
        bars = _trend_bars(-1)

        signal = continuation_signal_for("BTC-USDT-SWAP", bars, len(bars) - 1, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(-1, signal.direction)
        self.assertEqual("continuation_short", signal.reason)


if __name__ == "__main__":
    unittest.main()

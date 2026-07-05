import unittest
from dataclasses import replace

from config import BacktestConfig
from market import FeatureBar
from strategy import micro_momentum_signal_for


def _bars(direction: int, volume_ratio: float = 2.2) -> list[FeatureBar]:
    bars = []
    base = 100.0
    for idx in range(280):
        close = base + direction * idx * 0.02
        if idx == 279:
            close += direction * 1.2
        open_price = close - direction * 0.7
        high = max(open_price, close) + 0.2
        low = min(open_price, close) - 0.2
        donchian_high = close * 1.02
        donchian_low = close * 0.98
        if idx == 279 and direction > 0:
            donchian_high = close * 0.999
        if idx == 279 and direction < 0:
            donchian_low = close * 1.001
        bars.append(
            FeatureBar(
                ts=1_700_000_000_000 + idx * 15 * 60_000,
                time=str(idx),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume_quote=volume_ratio * 1_000_000.0,
                ema20=close - direction * 0.2,
                ema50=close - direction * 0.4,
                ema200=close - direction * 0.6,
                atr=0.6,
                atr_pct=0.006,
                rsi=61.0 if direction > 0 else 39.0,
                vol_sma=1_000_000.0,
                donchian_high=donchian_high,
                donchian_low=donchian_low,
                trend_strength=0.8 * direction,
            )
        )
    return bars


class MicroMomentumSignalTests(unittest.TestCase):
    def test_disabled_by_default(self):
        signal = micro_momentum_signal_for("BTC-USDT-SWAP", _bars(1), 279, BacktestConfig())

        self.assertIsNone(signal)

    def test_emits_long_on_volume_backed_breakout_candle(self):
        cfg = replace(BacktestConfig(), enable_micro_momentum_module=True)

        signal = micro_momentum_signal_for("BTC-USDT-SWAP", _bars(1), 279, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(1, signal.direction)
        self.assertEqual("micro_momentum_long", signal.reason)

    def test_emits_short_on_volume_backed_breakdown_candle(self):
        cfg = replace(BacktestConfig(), enable_micro_momentum_module=True)

        signal = micro_momentum_signal_for("BTC-USDT-SWAP", _bars(-1), 279, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(-1, signal.direction)
        self.assertEqual("micro_momentum_short", signal.reason)

    def test_rejects_low_volume_breakout(self):
        cfg = replace(BacktestConfig(), enable_micro_momentum_module=True)

        signal = micro_momentum_signal_for("BTC-USDT-SWAP", _bars(1, volume_ratio=1.1), 279, cfg)

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()

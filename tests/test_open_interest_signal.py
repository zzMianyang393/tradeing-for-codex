import unittest
from dataclasses import replace

from backtester import Backtester
from config import BacktestConfig
from open_interest import OpenInterestFeatureBar
from strategy import Signal, open_interest_signal_for


def _bars(direction: int, oi_change_pct: float = 0.12) -> list[OpenInterestFeatureBar]:
    bars = []
    for idx in range(240):
        close = 100.0 + direction * idx * 0.03
        if idx == 239:
            close += direction * 1.5
        donchian_high = close * 1.02
        donchian_low = close * 0.98
        if idx == 239 and direction > 0:
            donchian_high = close * 0.999
        if idx == 239 and direction < 0:
            donchian_low = close * 1.001
        bars.append(
            OpenInterestFeatureBar(
                ts=1_700_000_000_000 + idx * 15 * 60_000,
                time=str(idx),
                open=close - direction * 0.2,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume_quote=1_000_000.0,
                ema20=close - direction * 0.2,
                ema50=close - direction * 0.4,
                ema200=close - direction * 0.6,
                atr=0.7,
                atr_pct=0.007,
                rsi=58.0 if direction > 0 else 42.0,
                vol_sma=900_000.0,
                donchian_high=donchian_high,
                donchian_low=donchian_low,
                trend_strength=0.8 * direction,
                open_interest=10_000.0,
                open_interest_currency=100.0,
                open_interest_change_pct=oi_change_pct,
                open_interest_ma=9_000.0,
            )
        )
    return bars


class OpenInterestSignalTests(unittest.TestCase):
    def test_disabled_by_default(self):
        signal = open_interest_signal_for("BTC-USDT-SWAP", _bars(1), 239, BacktestConfig())

        self.assertIsNone(signal)

    def test_emits_long_on_rising_open_interest_breakout(self):
        cfg = replace(BacktestConfig(), enable_open_interest_module=True)

        signal = open_interest_signal_for("BTC-USDT-SWAP", _bars(1), 239, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(1, signal.direction)
        self.assertEqual("open_interest_breakout_long", signal.reason)

    def test_emits_short_on_rising_open_interest_breakdown(self):
        cfg = replace(BacktestConfig(), enable_open_interest_module=True)

        signal = open_interest_signal_for("BTC-USDT-SWAP", _bars(-1), 239, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(-1, signal.direction)
        self.assertEqual("open_interest_breakout_short", signal.reason)

    def test_rejects_small_open_interest_change(self):
        cfg = replace(BacktestConfig(), enable_open_interest_module=True)

        signal = open_interest_signal_for("BTC-USDT-SWAP", _bars(1, oi_change_pct=0.01), 239, cfg)

        self.assertIsNone(signal)

    def test_backtester_uses_open_interest_position_parameters(self):
        cfg = replace(
            BacktestConfig(),
            enable_open_interest_module=True,
            open_interest_risk_per_trade=0.02,
            open_interest_stop_atr=1.7,
            open_interest_take_profit_atr=1.1,
        )
        tester = Backtester(cfg)
        signal = Signal("BTC-USDT-SWAP", 1, 3.6, "open_interest", "open_interest_breakout_long")

        self.assertEqual(0.02, tester._risk_per_trade_for_signal(signal))
        self.assertEqual(1.7, tester._stop_atr_for_signal(signal))
        self.assertEqual(1.1, tester._take_profit_atr_for_signal(signal))


if __name__ == "__main__":
    unittest.main()

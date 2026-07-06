import unittest
from dataclasses import replace

from backtester import Backtester
from config import BacktestConfig
from funding_rate import FundingFeatureBar
from strategy import Signal, funding_signal_for


def _bars(funding_rate: float) -> list[FundingFeatureBar]:
    bars = []
    for idx in range(240):
        close = 100.0 + idx * 0.01
        bars.append(
            FundingFeatureBar(
                ts=1_700_000_000_000 + idx * 15 * 60_000,
                time=str(idx),
                open=close,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume_quote=1_000_000.0,
                ema20=close,
                ema50=close,
                ema200=close,
                atr=0.7,
                atr_pct=0.007,
                rsi=52.0,
                vol_sma=1_000_000.0,
                donchian_high=close + 2.0,
                donchian_low=close - 2.0,
                trend_strength=0.2,
                funding_rate=funding_rate,
                funding_realized_rate=funding_rate,
                funding_rate_ma=funding_rate,
            )
        )
    return bars


class FundingSignalTests(unittest.TestCase):
    def test_disabled_by_default(self):
        signal = funding_signal_for("BTC-USDT-SWAP", _bars(-0.001), 239, BacktestConfig())

        self.assertIsNone(signal)

    def test_emits_long_when_funding_is_extremely_negative(self):
        cfg = replace(BacktestConfig(), enable_funding_module=True)

        signal = funding_signal_for("BTC-USDT-SWAP", _bars(-0.001), 239, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(1, signal.direction)
        self.assertEqual("funding_extreme_long", signal.reason)

    def test_emits_short_when_funding_is_extremely_positive(self):
        cfg = replace(BacktestConfig(), enable_funding_module=True)

        signal = funding_signal_for("BTC-USDT-SWAP", _bars(0.001), 239, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(-1, signal.direction)
        self.assertEqual("funding_extreme_short", signal.reason)

    def test_rejects_small_funding_rate(self):
        cfg = replace(BacktestConfig(), enable_funding_module=True)

        signal = funding_signal_for("BTC-USDT-SWAP", _bars(0.0001), 239, cfg)

        self.assertIsNone(signal)

    def test_backtester_uses_funding_position_parameters(self):
        cfg = replace(
            BacktestConfig(),
            enable_funding_module=True,
            funding_risk_per_trade=0.03,
            funding_stop_atr=1.8,
            funding_take_profit_atr=0.9,
        )
        tester = Backtester(cfg)
        signal = Signal("BTC-USDT-SWAP", 1, 3.5, "funding", "funding_extreme_long")

        self.assertEqual(0.03, tester._risk_per_trade_for_signal(signal))
        self.assertEqual(1.8, tester._stop_atr_for_signal(signal))
        self.assertEqual(0.9, tester._take_profit_atr_for_signal(signal))


if __name__ == "__main__":
    unittest.main()

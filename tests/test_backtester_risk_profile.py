import unittest

from backtester import Backtester
from config import BacktestConfig
from market import FeatureBar
from strategy import Signal


class BacktesterRiskProfileTests(unittest.TestCase):
    def test_defensive_range_take_profit_uses_smaller_target_when_equity_is_weak(self):
        cfg = BacktestConfig(
            defensive_range_exit_equity_fraction=1.05,
            defensive_range_take_profit_atr=0.65,
            range_take_profit_atr=1.0,
        )
        tester = Backtester(cfg)
        bar = FeatureBar(
            ts=1,
            time="2026-01-01 00:00:00",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume_quote=1000.0,
            atr=2.0,
            atr_pct=0.02,
        )
        sig = Signal("BTC-USDT-SWAP", 1, 3.0, "range", "range_revert_long")

        pos = tester._open_position(sig, bar, 10, equity=10.0, free_margin_limit=10.0)

        self.assertIsNotNone(pos)
        self.assertAlmostEqual(101.3, pos.take_profit)


if __name__ == "__main__":
    unittest.main()

import unittest

from backtester import Backtester, Position
from config import BacktestConfig
from market import FeatureBar
from strategy import Signal


class BacktesterRiskProfileTests(unittest.TestCase):
    def _position(self, direction: int, stop: float, trail: float) -> Position:
        return Position(
            symbol="BTC-USDT-SWAP", direction=direction, entry_idx=0,
            entry_time="2026-01-01 00:00:00", entry=100.0, notional=100.0,
            margin=10.0, qty=1.0, stop=stop, take_profit=130.0 if direction > 0 else 70.0,
            trail=trail, leverage=10.0, regime="candidate", reason="candidate_test",
        )

    def test_defensive_range_take_profit_uses_smaller_target_when_equity_is_weak(self):
        cfg = BacktestConfig(
            defensive_range_exit_equity_fraction=1.05,
            defensive_range_take_profit_atr=0.65,
            range_take_profit_atr=1.0,
            slippage=0.0,
            taker_fee=0.00005,
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

    def test_long_trail_from_current_close_cannot_stop_same_bar(self):
        tester = Backtester(BacktestConfig(trailing_atr=1.0, early_failure_bars=0))
        pos = self._position(direction=1, stop=95.0, trail=90.0)
        bar = FeatureBar(ts=1, time="2026-01-01 00:15:00", open=100, high=112, low=99, close=110, volume_quote=1, atr=1, atr_pct=0.01, ema20=100)

        exit_price, reason = tester._exit_price(pos, bar, 1)

        self.assertIsNone(exit_price)
        self.assertEqual("", reason)
        self.assertAlmostEqual(109.0, pos.trail)

    def test_short_trail_from_current_close_cannot_stop_same_bar(self):
        tester = Backtester(BacktestConfig(trailing_atr=1.0, early_failure_bars=0))
        pos = self._position(direction=-1, stop=105.0, trail=110.0)
        bar = FeatureBar(ts=1, time="2026-01-01 00:15:00", open=100, high=101, low=88, close=90, volume_quote=1, atr=1, atr_pct=0.01, ema20=100)

        exit_price, reason = tester._exit_price(pos, bar, 1)

        self.assertIsNone(exit_price)
        self.assertEqual("", reason)
        self.assertAlmostEqual(91.0, pos.trail)


if __name__ == "__main__":
    unittest.main()

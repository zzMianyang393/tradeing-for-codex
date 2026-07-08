import unittest

from backtester import Backtester
from config import BacktestConfig
from strategy import Signal


class DynamicStrategyRouterTests(unittest.TestCase):
    def test_blocks_reasons_in_router_blocklist(self):
        config = BacktestConfig(router_blocked_reasons=("trend_long",))
        tester = Backtester(config)
        signal = Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "trend_long")

        self.assertFalse(tester._dynamic_router_allows_signal(signal))

    def test_allows_only_whitelisted_reasons_when_allowlist_is_set(self):
        config = BacktestConfig(router_allowed_reasons=("transition_breakout_long",))
        tester = Backtester(config)
        allowed = Signal("BTC-USDT-SWAP", 1, 3.0, "transition", "transition_breakout_long")
        blocked = Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "trend_long")

        self.assertTrue(tester._dynamic_router_allows_signal(allowed))
        self.assertFalse(tester._dynamic_router_allows_signal(blocked))

    def test_rejects_signals_that_do_not_match_regime_structure(self):
        tester = Backtester(BacktestConfig())
        signal = Signal("BTC-USDT-SWAP", -1, 3.0, "uptrend", "transition_breakout_short")

        self.assertFalse(tester._dynamic_router_allows_signal(signal))

    def test_can_disable_router_for_experiments(self):
        config = BacktestConfig(enable_dynamic_strategy_router=False, router_blocked_reasons=("trend_long",))
        tester = Backtester(config)
        signal = Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "trend_long")

        self.assertTrue(tester._dynamic_router_allows_signal(signal))


if __name__ == "__main__":
    unittest.main()

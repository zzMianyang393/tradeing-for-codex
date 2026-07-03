import unittest
from dataclasses import replace

from config import BacktestConfig


class UniverseConfigTests(unittest.TestCase):
    def test_default_uses_dynamic_universe(self):
        cfg = BacktestConfig()

        self.assertEqual((), cfg.allowed_symbols)
        self.assertGreaterEqual(cfg.active_symbol_limit, 3)

    def test_can_opt_into_fixed_universe_for_research(self):
        cfg = replace(BacktestConfig(), allowed_symbols=("AVAX-USDT-SWAP",))

        self.assertEqual(("AVAX-USDT-SWAP",), cfg.allowed_symbols)

    def test_default_profile_prioritizes_short_window_targets(self):
        cfg = BacktestConfig()

        self.assertLessEqual(cfg.max_margin_fraction, 0.75)
        self.assertLessEqual(cfg.max_total_margin_fraction, 0.60)
        self.assertEqual(30, cfg.short_window_days)
        self.assertEqual(("transition", "range"), cfg.enabled_regimes)
        self.assertTrue(cfg.enable_adaptive_profiles)
        self.assertEqual(("downtrend",), cfg.adaptive_trend_allowed_regimes)
        self.assertLess(cfg.adaptive_trend_risk_per_trade, cfg.risk_per_trade)
        self.assertGreaterEqual(cfg.validation_target_returns[7], 20.0)
        self.assertGreaterEqual(cfg.validation_target_returns[30], 100.0)


if __name__ == "__main__":
    unittest.main()

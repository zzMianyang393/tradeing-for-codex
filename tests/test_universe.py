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

    def test_default_profile_prioritizes_rolling_consistency(self):
        cfg = BacktestConfig()

        self.assertEqual(0.13, cfg.risk_per_trade)
        self.assertLessEqual(cfg.max_margin_fraction, 0.65)
        self.assertLessEqual(cfg.max_total_margin_fraction, 0.55)
        self.assertEqual(2, cfg.max_positions)
        self.assertEqual(30, cfg.short_window_days)
        self.assertEqual(6, cfg.active_symbol_limit)
        self.assertEqual(10, cfg.short_window_symbol_limit)
        self.assertEqual(("transition", "range"), cfg.enabled_regimes)
        self.assertFalse(cfg.transition_long_enabled)
        self.assertFalse(cfg.enable_attack_module)
        self.assertLessEqual(cfg.short_rebound_block_pct, 0.015)
        self.assertGreaterEqual(cfg.selector_min_avg_quote, 250_000.0)
        self.assertLessEqual(cfg.selector_max_micro_noise, 0.0072)
        self.assertTrue(cfg.enable_adaptive_profiles)
        self.assertEqual(("downtrend",), cfg.adaptive_trend_allowed_regimes)
        self.assertLess(cfg.adaptive_trend_risk_per_trade, cfg.risk_per_trade)
        self.assertFalse(cfg.enable_long_window_aggressive_profile)
        self.assertEqual((), cfg.long_window_preferred_symbols)
        self.assertLess(cfg.profit_lock_risk_multiplier, 1.0)
        self.assertLess(cfg.profit_lock_margin_fraction, 1.0)
        self.assertGreaterEqual(cfg.defensive_range_exit_equity_fraction, 1.0)
        self.assertGreater(cfg.defensive_range_take_profit_atr, 0.0)
        self.assertGreaterEqual(cfg.validation_target_returns[7], 2.0)
        self.assertGreaterEqual(cfg.validation_target_returns[30], 20.0)


if __name__ == "__main__":
    unittest.main()

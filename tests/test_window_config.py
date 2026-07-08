import unittest

from backtester import config_for_window
from config import BacktestConfig


class WindowConfigTests(unittest.TestCase):
    def test_long_window_uses_aggressive_overrides(self):
        cfg = BacktestConfig(enable_target_window_profiles=False, enable_long_window_aggressive_profile=True)

        window_cfg = config_for_window(cfg, 365, ("AAA-USDT-SWAP", "BBB-USDT-SWAP"))

        self.assertEqual(cfg.long_window_aggressive_cooldown_bars, window_cfg.cooldown_bars)
        self.assertEqual(cfg.long_window_aggressive_max_total_margin_fraction, window_cfg.max_total_margin_fraction)
        self.assertEqual(cfg.long_window_aggressive_max_margin_fraction, window_cfg.max_margin_fraction)
        self.assertEqual(999.0, window_cfg.profit_lock_equity_fraction)
        self.assertEqual(cfg.long_window_aggressive_leverage, window_cfg.leverage_caps["AAA-USDT-SWAP"].max_leverage)

    def test_shorter_windows_keep_base_config(self):
        cfg = BacktestConfig(enable_target_window_profiles=False)

        window_cfg = config_for_window(cfg, 180, ("AAA-USDT-SWAP",))

        self.assertEqual(cfg.cooldown_bars, window_cfg.cooldown_bars)
        self.assertEqual(cfg.max_total_margin_fraction, window_cfg.max_total_margin_fraction)
        self.assertEqual(cfg.profit_lock_equity_fraction, window_cfg.profit_lock_equity_fraction)

    def test_target_profiles_use_90_day_attack_sizing(self):
        cfg = BacktestConfig()

        window_cfg = config_for_window(cfg, 90, ("AAA-USDT-SWAP",))

        self.assertEqual(0.9, window_cfg.risk_per_trade)
        self.assertEqual(1.0, window_cfg.max_margin_fraction)
        self.assertEqual(1.5, window_cfg.max_total_margin_fraction)
        self.assertEqual(4, window_cfg.max_positions)
        self.assertEqual(1.25, window_cfg.range_take_profit_atr)
        self.assertTrue(window_cfg.enable_attack_module)
        self.assertEqual(cfg.target_window_excluded_symbols, window_cfg.excluded_symbols)

    def test_target_profiles_use_14_day_attack_sizing(self):
        cfg = BacktestConfig()

        window_cfg = config_for_window(cfg, 14, ("AAA-USDT-SWAP",))

        self.assertEqual(0.39, window_cfg.risk_per_trade)
        self.assertEqual(1.65, window_cfg.max_margin_fraction)
        self.assertEqual(1.65, window_cfg.max_total_margin_fraction)
        self.assertEqual(1.0, window_cfg.range_take_profit_atr)
        self.assertFalse(window_cfg.enable_attack_module)
        self.assertEqual(("BNB-USDT-SWAP",), window_cfg.excluded_symbols)

    def test_target_profiles_use_7_day_short_attack_sizing(self):
        cfg = BacktestConfig()

        window_cfg = config_for_window(cfg, 7, ("AAA-USDT-SWAP",))

        self.assertEqual(0.32, window_cfg.risk_per_trade)
        self.assertEqual(2.0, window_cfg.max_total_margin_fraction)
        self.assertEqual(5, window_cfg.short_window_symbol_limit)
        self.assertTrue(window_cfg.enable_attack_module)
        self.assertEqual(("BNB-USDT-SWAP",), window_cfg.excluded_symbols)

    def test_target_profiles_use_365_day_preferred_universe(self):
        cfg = BacktestConfig()

        window_cfg = config_for_window(cfg, 365, ("AAA-USDT-SWAP",))

        self.assertTrue(window_cfg.enable_attack_module)
        self.assertEqual(2.45, window_cfg.min_score)
        self.assertEqual(cfg.target_long_window_preferred_symbols, window_cfg.long_window_preferred_symbols)
        self.assertEqual(cfg.long_window_aggressive_leverage, window_cfg.leverage_caps["AAA-USDT-SWAP"].max_leverage)

    def test_target_profiles_use_180_day_excluded_universe(self):
        cfg = BacktestConfig()

        window_cfg = config_for_window(cfg, 180, ("AAA-USDT-SWAP",))

        self.assertEqual(
            cfg.target_180_excluded_symbols + ("NEAR-USDT-SWAP", "DOT-USDT-SWAP", "ARB-USDT-SWAP"),
            window_cfg.excluded_symbols,
        )
        self.assertIn("SOL-USDT-SWAP", window_cfg.excluded_symbols)
        self.assertIn("UNI-USDT-SWAP", window_cfg.excluded_symbols)


if __name__ == "__main__":
    unittest.main()

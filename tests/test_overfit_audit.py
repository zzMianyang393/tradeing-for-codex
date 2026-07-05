import unittest

from overfit_audit import aggressive_all_windows_config, conservative_all_windows_config
from config import BacktestConfig


class OverfitAuditConfigTests(unittest.TestCase):
    def test_aggressive_config_is_applied_to_all_windows_without_window_gate(self):
        cfg = BacktestConfig()

        aggressive = aggressive_all_windows_config(cfg, ("AAA-USDT-SWAP", "BBB-USDT-SWAP"))

        self.assertFalse(aggressive.enable_long_window_aggressive_profile)
        self.assertEqual(cfg.long_window_aggressive_cooldown_bars, aggressive.cooldown_bars)
        self.assertEqual(cfg.long_window_aggressive_max_total_margin_fraction, aggressive.max_total_margin_fraction)
        self.assertEqual(999.0, aggressive.profit_lock_equity_fraction)
        self.assertEqual(cfg.long_window_aggressive_leverage, aggressive.leverage_caps["AAA-USDT-SWAP"].max_leverage)

    def test_conservative_config_removes_long_window_special_cases(self):
        cfg = BacktestConfig()

        conservative = conservative_all_windows_config(cfg)

        self.assertFalse(conservative.enable_long_window_aggressive_profile)
        self.assertEqual((), conservative.long_window_preferred_symbols)


if __name__ == "__main__":
    unittest.main()

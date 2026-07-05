import unittest
from dataclasses import replace

from config import BacktestConfig
from rolling_window_audit import MS_PER_DAY, rolling_endpoints, summarize_results, window_config_for_audit


class RollingWindowAuditTests(unittest.TestCase):
    def test_rolling_endpoints_walk_back_from_latest(self):
        timeline = [day * MS_PER_DAY for day in range(0, 101)]

        endpoints = rolling_endpoints(timeline, window_days=30, stride_days=14, max_windows=4)

        self.assertEqual([58 * MS_PER_DAY, 72 * MS_PER_DAY, 86 * MS_PER_DAY, 100 * MS_PER_DAY], endpoints)

    def test_rolling_endpoints_skips_when_history_is_too_short(self):
        timeline = [day * MS_PER_DAY for day in range(0, 20)]

        endpoints = rolling_endpoints(timeline, window_days=30, stride_days=7, max_windows=4)

        self.assertEqual([], endpoints)

    def test_summarize_results_reports_profit_rate_and_tail_risk(self):
        results = [
            {"available": True, "pnl": 1.0, "return_pct": 10.0, "max_drawdown_pct": 2.0},
            {"available": True, "pnl": -1.0, "return_pct": -5.0, "max_drawdown_pct": 12.0},
            {"available": True, "pnl": 2.0, "return_pct": 30.0, "max_drawdown_pct": 5.0},
        ]

        summary = summarize_results(results)

        self.assertEqual(3, summary["available"])
        self.assertEqual(2, summary["profitable"])
        self.assertEqual(0.6667, summary["profit_rate"])
        self.assertEqual(10.0, summary["median_return_pct"])
        self.assertEqual(-5.0, summary["worst_return_pct"])
        self.assertEqual(12.0, summary["max_drawdown_pct"])

    def test_window_config_for_audit_uses_target_profiles(self):
        cfg = BacktestConfig()

        window_cfg = window_config_for_audit(cfg, 90, ("AAA-USDT-SWAP",))

        self.assertEqual(0.9, window_cfg.risk_per_trade)
        self.assertEqual(cfg.target_window_excluded_symbols, window_cfg.excluded_symbols)

    def test_window_config_for_audit_can_disable_target_profiles(self):
        cfg = replace(BacktestConfig(), enable_target_window_profiles=False)

        window_cfg = window_config_for_audit(cfg, 90, ("AAA-USDT-SWAP",))

        self.assertEqual(cfg.risk_per_trade, window_cfg.risk_per_trade)


if __name__ == "__main__":
    unittest.main()

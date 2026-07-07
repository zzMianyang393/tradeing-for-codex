import unittest
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from config import BacktestConfig
from rolling_window_audit import (
    MS_PER_DAY,
    data_source_coverage,
    load_market_for_audit,
    rolling_endpoints,
    summarize_results,
    window_config_for_audit,
)


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

    def test_summarize_results_aggregates_reason_stats(self):
        results = [
            {
                "available": True,
                "pnl": 1.0,
                "return_pct": 10.0,
                "max_drawdown_pct": 2.0,
                "by_reason": {
                    "funding_extreme_long": {"trades": 2, "wins": 1, "pnl": 0.5},
                    "range_revert_long": {"trades": 1, "wins": 1, "pnl": 0.5},
                },
            },
            {
                "available": True,
                "pnl": -1.0,
                "return_pct": -5.0,
                "max_drawdown_pct": 12.0,
                "by_reason": {
                    "funding_extreme_long": {"trades": 1, "wins": 0, "pnl": -0.25},
                },
            },
        ]

        summary = summarize_results(results)

        self.assertEqual(3, summary["reasons"]["funding_extreme_long"]["trades"])
        self.assertEqual(1, summary["reasons"]["funding_extreme_long"]["wins"])
        self.assertEqual(0.25, summary["reasons"]["funding_extreme_long"]["pnl"])
        self.assertEqual(1, summary["reasons"]["range_revert_long"]["trades"])

    def test_window_config_for_audit_uses_target_profiles(self):
        cfg = BacktestConfig()

        window_cfg = window_config_for_audit(cfg, 90, ("AAA-USDT-SWAP",))

        self.assertEqual(0.9, window_cfg.risk_per_trade)
        self.assertEqual(cfg.target_window_excluded_symbols, window_cfg.excluded_symbols)

    def test_window_config_for_audit_can_disable_target_profiles(self):
        cfg = replace(BacktestConfig(), enable_target_window_profiles=False)

        window_cfg = window_config_for_audit(cfg, 90, ("AAA-USDT-SWAP",))

        self.assertEqual(cfg.risk_per_trade, window_cfg.risk_per_trade)

    def test_load_market_for_audit_enables_configured_data_sources(self):
        cfg = replace(
            BacktestConfig(),
            enable_funding_module=True,
            enable_open_interest_module=True,
            enable_trade_flow_module=True,
            rm_max_order_book_spread_pct=0.001,
        )

        with patch("rolling_window_audit.load_market", return_value={}) as mocked:
            load_market_for_audit(Path("data"), cfg)

        mocked.assert_called_once_with(
            Path("data"),
            cfg.timeframe_minutes,
            include_funding=True,
            include_open_interest=True,
            include_trade_flow=True,
            include_order_book=True,
        )

    def test_data_source_coverage_counts_available_optional_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / "BTC_15m.csv").write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
            (data_dir / "ETH_15m.csv").write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
            (data_dir / "BTC-USDT-SWAP_trades.csv").write_text("symbol\n", encoding="utf-8")
            (data_dir / "ETH-USDT-SWAP_funding.csv").write_text("symbol\n", encoding="utf-8")

            coverage = data_source_coverage(data_dir)

        self.assertEqual(2, coverage["symbols"])
        self.assertEqual(1, coverage["funding"]["files"])
        self.assertEqual(0.5, coverage["funding"]["coverage"])
        self.assertEqual(1, coverage["trade_flow"]["files"])
        self.assertEqual(["BTC-USDT-SWAP"], coverage["trade_flow"]["symbols"])
        self.assertEqual(0, coverage["open_interest"]["files"])


if __name__ == "__main__":
    unittest.main()

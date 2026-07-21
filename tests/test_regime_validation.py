from __future__ import annotations

import unittest

from market import FeatureBar
from regime_validation import FOUR_HOURS_MS, conditional_trade_report, regime_at_entry, regime_gated_provider
from strategy import Signal


class RegimeValidationTests(unittest.TestCase):
    def test_label_is_not_available_until_4h_bar_has_closed(self):
        labels = [(FOUR_HOURS_MS, "趋势上行")]
        self.assertEqual("样本不足", regime_at_entry(labels, FOUR_HOURS_MS - 1))
        self.assertEqual("趋势上行", regime_at_entry(labels, FOUR_HOURS_MS))

    def test_conditional_report_groups_trades_by_pre_entry_label(self):
        bars = [
            FeatureBar(ts=index * 15 * 60 * 1000, time=f"2024-01-01 {index // 4:02d}:00:00", open=100 + index, high=101 + index, low=99 + index, close=100 + index, volume_quote=1)
            for index in range(80)
        ]
        trades = [{"symbol": "BTC-USDT-SWAP", "entry_time": "2024-01-01 16:00:00", "pnl_pct_equity": 1.0}]
        report = conditional_trade_report(trades, {"BTC-USDT-SWAP": bars})
        self.assertEqual(1, sum(item["trades"] for item in report.values()))

    def test_regime_gate_blocks_unapproved_label(self):
        bars = [
            FeatureBar(ts=index * 15 * 60 * 1000, time=f"2024-01-01 {index // 4:02d}:00:00", open=100, high=101, low=99, close=100, volume_quote=1)
            for index in range(80)
        ]
        provider = lambda symbol, _bars, _index: Signal(symbol, 1, 1.0, "candidate", "test")
        gated = regime_gated_provider(provider, {"BTC-USDT-SWAP": bars}, {"不存在的行情"})
        self.assertIsNone(gated("BTC-USDT-SWAP", bars, 70))


if __name__ == "__main__":
    unittest.main()

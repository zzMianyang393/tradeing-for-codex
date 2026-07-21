from __future__ import annotations

import unittest

from native_oi_research import DailyBar, _oi_zscore, run_oi_flush_reversal


class NativeOiResearchTests(unittest.TestCase):
    def test_oi_zscore_detects_unusual_flush(self):
        bars = [DailyBar(str(index), 100, 101, 99, 100, 100 + index * 0.1) for index in range(65)]
        bars[-1] = DailyBar("64", 100, 101, 90, 96, 80)
        self.assertLess(_oi_zscore(bars, 64) or 0, -2.0)

    def test_empty_trade_report_is_well_formed(self):
        bars = [DailyBar(str(index), 100, 101, 99, 100, 100) for index in range(70)]
        result = run_oi_flush_reversal(bars)
        self.assertEqual(0, result["trades"])
        self.assertEqual(0.0, result["return_pct"])


if __name__ == "__main__":
    unittest.main()

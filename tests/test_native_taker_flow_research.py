from __future__ import annotations

import unittest

from native_taker_flow_research import DailyFlowBar, _flow_zscore, run_taker_absorption


class NativeTakerFlowResearchTests(unittest.TestCase):
    def test_flow_zscore_uses_only_prior_days(self):
        bars = [DailyFlowBar(str(index), 100, 101, 99, 100, 0.9 if index % 2 else 1.1) for index in range(61)]
        bars[-1] = DailyFlowBar("60", 100, 101, 99, 100, 10.0)
        self.assertIsNone(_flow_zscore(bars, 59))
        self.assertGreater(_flow_zscore(bars, 60) or 0.0, 2.0)

    def test_absorption_report_has_no_trade_without_opposite_close(self):
        bars = []
        for index in range(70):
            ratio = 10.0 if index == 60 else 1.0
            bars.append(DailyFlowBar(str(index), 100, 101, 99, 101, ratio))
        self.assertEqual(0, run_taker_absorption(bars)["trades"])


if __name__ == "__main__":
    unittest.main()

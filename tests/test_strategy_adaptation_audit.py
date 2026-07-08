import unittest

from strategy_adaptation_audit import (
    adaptability_level,
    aggregate_reason_months,
    reason_strategy_family,
    suitable_market_for_reason,
    translate_reason,
    translate_regime,
)


class StrategyAdaptationAuditTests(unittest.TestCase):
    def test_translate_reason_returns_chinese_strategy_name(self):
        self.assertEqual(translate_reason("trend_long"), "趋势做多")
        self.assertEqual(translate_reason("open_interest_breakout_long"), "持仓量突破做多")

    def test_translate_regime_returns_chinese_market_label(self):
        self.assertEqual(translate_regime("uptrend"), "上涨趋势")
        self.assertEqual(translate_regime("transition"), "趋势转换/突破")

    def test_reason_strategy_family_groups_variants(self):
        self.assertEqual(reason_strategy_family("attack_breakout_long"), "攻击突破")
        self.assertEqual(reason_strategy_family("range_revert_short"), "震荡反转")

    def test_suitable_market_for_reason_prefers_strategy_definition(self):
        self.assertEqual(suitable_market_for_reason("transition_breakout_long"), "趋势转换/突破")
        self.assertEqual(suitable_market_for_reason("range_revert_short"), "震荡区间")

    def test_aggregate_reason_months_counts_profitable_months_once_per_month(self):
        report = {
            "months": [
                {
                    "month": 1,
                    "candidates": [
                        {
                            "rank": "a",
                            "result": {
                                "by_reason": {
                                    "trend_long": {"pnl": 3.0, "trades": 2, "wins": 1},
                                    "range_revert_long": {"pnl": -1.0, "trades": 1, "wins": 0},
                                },
                                "by_regime": {"uptrend": {"pnl": 3.0, "trades": 2}},
                            },
                        },
                        {
                            "rank": "b",
                            "result": {"by_reason": {"trend_long": {"pnl": -1.0, "trades": 1, "wins": 0}}},
                        },
                    ],
                },
                {
                    "month": 2,
                    "candidates": [
                        {"rank": "a", "result": {"by_reason": {"trend_long": {"pnl": 4.0, "trades": 2, "wins": 2}}}}
                    ],
                },
            ]
        }

        rows = aggregate_reason_months(report)
        trend = next(row for row in rows if row["reason"] == "trend_long")

        self.assertEqual(trend["months_seen"], 2)
        self.assertEqual(trend["profitable_months"], 2)
        self.assertEqual(trend["trades"], 5)
        self.assertEqual(trend["strategy_cn"], "趋势做多")
        self.assertEqual(trend["family_cn"], "趋势跟随")

    def test_adaptability_level_uses_month_coverage_profitability_and_drawdown(self):
        self.assertEqual(adaptability_level(months_seen=10, profitable_months=7, median_pnl=3.0, win_rate=0.55), "强")
        self.assertEqual(adaptability_level(months_seen=4, profitable_months=2, median_pnl=0.5, win_rate=0.5), "中")
        self.assertEqual(adaptability_level(months_seen=2, profitable_months=0, median_pnl=-1.0, win_rate=0.3), "弱")


if __name__ == "__main__":
    unittest.main()

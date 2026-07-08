import unittest

from overfit_report import (
    adjacent_validation_results,
    build_overfit_matrix,
    decay_ratio,
    strategy_label,
)


class OverfitReportTests(unittest.TestCase):
    def test_strategy_label_combines_rank_regime_and_reason(self):
        month = {
            "rank": "goal#1",
            "result": {"dominant_regime": "uptrend", "dominant_reason": "trend_long"},
        }

        self.assertEqual(strategy_label(month), "goal#1|uptrend|trend_long")

    def test_adjacent_validation_results_selects_neighbor_months_for_same_rank(self):
        report = {
            "months": [
                {"month": 1, "rank": "a", "result": {"pnl": 1}},
                {"month": 2, "rank": "b", "result": {"pnl": 2}, "candidates": [{"rank": "a", "result": {"pnl": 3}}]},
                {"month": 3, "rank": "c", "result": {"pnl": 4}, "candidates": [{"rank": "a", "result": {"pnl": 5}}]},
            ]
        }

        adjacent = adjacent_validation_results(report, rank="a", target_month=2, radius=1)

        self.assertEqual([item["month"] for item in adjacent], [1, 3])
        self.assertEqual([item["result"]["pnl"] for item in adjacent], [1, 5])

    def test_decay_ratio_compares_target_to_validation_median(self):
        ratio = decay_ratio(target_return_pct=100.0, validation_returns_pct=[20.0, 40.0, 60.0])

        self.assertEqual(ratio, 0.4)

    def test_build_overfit_matrix_marks_high_risk_when_adjacent_and_regime_fail(self):
        report = {
            "months": [
                {
                    "month": 1,
                    "rank": "a",
                    "result": {"pnl": 100, "return_pct": 100, "dominant_regime": "range", "dominant_reason": "r"},
                    "candidates": [{"rank": "a", "result": {"pnl": 100, "return_pct": 100, "dominant_regime": "range", "dominant_reason": "r"}}],
                },
                {
                    "month": 2,
                    "rank": "b",
                    "result": {"pnl": 1, "return_pct": 1, "dominant_regime": "range", "dominant_reason": "r"},
                    "candidates": [{"rank": "a", "result": {"pnl": -5, "return_pct": -5, "dominant_regime": "range", "dominant_reason": "r"}}],
                },
            ]
        }

        matrix = build_overfit_matrix(report, target_months=[1])

        self.assertEqual(matrix[0]["month"], 1)
        self.assertEqual(matrix[0]["risk_level"], "high")
        self.assertIn("adjacent validation is weak", matrix[0]["risk_reasons"])


if __name__ == "__main__":
    unittest.main()

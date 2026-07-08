import unittest

from monthly_goal import (
    annotate_overfit_risks,
    assess_overfit_risk,
    classify_month,
    compact_month_result,
    month_windows,
    parse_month_targets,
    results_by_rank,
    select_month_winner,
    select_qualified_month_winner,
    select_target_months,
)


class MonthlyGoalTests(unittest.TestCase):
    def test_month_windows_splits_latest_year_into_12_contiguous_windows(self):
        day = 86_400_000
        timeline = [index * day for index in range(366)]

        windows = month_windows(timeline, months=12, total_days=360)

        self.assertEqual(len(windows), 12)
        self.assertEqual(windows[0][0], 5 * day)
        self.assertEqual(windows[-1][1], 365 * day)
        self.assertTrue(all(left[1] == right[0] for left, right in zip(windows, windows[1:])))

    def test_select_month_winner_prefers_profit_with_lower_drawdown_tiebreak(self):
        candidates = [
            {"rank": 1, "result": {"pnl": 5.0, "max_drawdown_pct": 40.0, "win_rate": 0.6, "trades": 12}},
            {"rank": 2, "result": {"pnl": 5.0, "max_drawdown_pct": 20.0, "win_rate": 0.55, "trades": 12}},
            {"rank": 3, "result": {"pnl": 4.0, "max_drawdown_pct": 10.0, "win_rate": 0.7, "trades": 12}},
        ]

        winner = select_month_winner(candidates)

        self.assertEqual(winner["rank"], 2)

    def test_select_qualified_month_winner_prefers_candidate_that_passes_constraints(self):
        candidates = [
            {"rank": 1, "result": {"pnl": 20.0, "max_drawdown_pct": 70.0, "win_rate": 0.7, "trades": 20}},
            {"rank": 2, "result": {"pnl": 10.0, "max_drawdown_pct": 20.0, "win_rate": 0.55, "trades": 12}},
        ]

        winner = select_qualified_month_winner(
            candidates,
            min_pnl=0.0,
            max_drawdown_pct=45.0,
            min_win_rate=0.48,
            min_trades=4,
        )

        self.assertEqual(winner["rank"], 2)

    def test_classify_month_reports_failure_reasons(self):
        result = {"pnl": -1.0, "max_drawdown_pct": 45.0, "win_rate": 0.42, "trades": 3}

        audit = classify_month(result, min_pnl=0.5, max_drawdown_pct=35.0, min_win_rate=0.5, min_trades=8)

        self.assertFalse(audit["qualified"])
        self.assertEqual(
            audit["failures"],
            [
                "pnl -1 < 0.5",
                "drawdown 45.00% > 35.00%",
                "win_rate 42.00% < 50.00%",
                "trades 3 < 8",
            ],
        )

    def test_compact_month_result_keeps_strategy_explanation_inputs(self):
        result = {
            "pnl": 2.5,
            "return_pct": 25.0,
            "max_drawdown_pct": 12.0,
            "win_rate": 0.6,
            "trades": 10,
            "by_regime": {"range": {"pnl": 2.0, "trades": 8}, "uptrend": {"pnl": 0.5, "trades": 2}},
            "by_reason": {"range_revert_long": {"pnl": 2.0, "trades": 8}},
            "equity_curve": [["ignored", 10.0]],
        }

        compact = compact_month_result(result)

        self.assertNotIn("equity_curve", compact)
        self.assertEqual(compact["dominant_regime"], "range")
        self.assertEqual(compact["dominant_reason"], "range_revert_long")

    def test_select_target_months_returns_unqualified_month_numbers(self):
        report = {
            "months": [
                {"month": 1, "audit": {"qualified": True}},
                {"month": 2, "audit": {"qualified": False}},
                {"month": 3, "audit": {"qualified": False}},
            ]
        }

        self.assertEqual(select_target_months(report), [2, 3])

    def test_parse_month_targets_supports_comma_separated_months(self):
        self.assertEqual(parse_month_targets("2,4,6,8,10,11"), [2, 4, 6, 8, 10, 11])
        self.assertEqual(parse_month_targets(""), [])

    def test_assess_overfit_risk_marks_isolated_spike_as_high_risk(self):
        target_result = {"pnl": 100.0, "return_pct": 100.0, "dominant_regime": "range"}
        validation_results = [
            {"pnl": -5.0, "return_pct": -5.0, "dominant_regime": "range"},
            {"pnl": 2.0, "return_pct": 2.0, "dominant_regime": "range"},
            {"pnl": 50.0, "return_pct": 50.0, "dominant_regime": "uptrend"},
        ]

        risk = assess_overfit_risk(target_result, validation_results)

        self.assertEqual(risk["level"], "high")
        self.assertIn("same-regime median return is weak", risk["reasons"])

    def test_assess_overfit_risk_accepts_stable_same_regime_performance(self):
        target_result = {"pnl": 10.0, "return_pct": 20.0, "dominant_regime": "range"}
        validation_results = [
            {"pnl": 3.0, "return_pct": 6.0, "dominant_regime": "range"},
            {"pnl": 5.0, "return_pct": 8.0, "dominant_regime": "range"},
            {"pnl": -2.0, "return_pct": -4.0, "dominant_regime": "uptrend"},
        ]

        risk = assess_overfit_risk(target_result, validation_results)

        self.assertEqual(risk["level"], "low")

    def test_results_by_rank_groups_month_results_for_validation(self):
        report = {
            "months": [
                {"month": 1, "rank": "a", "result": {"pnl": 1}},
                {"month": 2, "rank": "b", "result": {"pnl": 2}, "candidates": [{"rank": "a", "result": {"pnl": 3}}]},
            ]
        }

        grouped = results_by_rank(report)

        self.assertEqual([item["month"] for item in grouped["a"]], [1, 2])
        self.assertEqual(grouped["a"][1]["result"]["pnl"], 3)

    def test_annotate_overfit_risks_adds_risk_to_target_months(self):
        report = {
            "months": [
                {
                    "month": 1,
                    "rank": "a",
                    "result": {"pnl": 10, "return_pct": 20, "dominant_regime": "range"},
                    "candidates": [{"rank": "a", "result": {"pnl": 10, "return_pct": 20, "dominant_regime": "range"}}],
                },
                {
                    "month": 2,
                    "rank": "b",
                    "result": {"pnl": -1, "return_pct": -2, "dominant_regime": "range"},
                    "candidates": [{"rank": "a", "result": {"pnl": 4, "return_pct": 8, "dominant_regime": "range"}}],
                },
            ]
        }

        annotated = annotate_overfit_risks(report, target_months=[1])

        self.assertEqual(annotated["months"][0]["overfit_risk"]["level"], "low")
        self.assertNotIn("overfit_risk", annotated["months"][1])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from low_turnover_research_gate import (
    ResearchGateInput,
    build_low_turnover_policy_report,
    evaluate_low_turnover_candidate,
    round_trip_cost_for_legs,
)


class LowTurnoverResearchGateTests(unittest.TestCase):
    def test_round_trip_cost_for_common_leg_counts(self):
        self.assertEqual(0.0016, round_trip_cost_for_legs(2))
        self.assertEqual(0.0032, round_trip_cost_for_legs(4))
        with self.assertRaises(ValueError):
            round_trip_cost_for_legs(0)

    def test_rejects_short_hold_high_turnover_candidate(self):
        result = evaluate_low_turnover_candidate(ResearchGateInput("intraday", 0.25, 80, 2))
        self.assertFalse(result.passed)
        self.assertIn("hold_period_too_short", result.failures)
        self.assertIn("too_many_events_per_month", result.failures)
        self.assertIn("turnover_cost_too_high", result.failures)

    def test_accepts_low_turnover_candidate_for_research_card_only(self):
        result = evaluate_low_turnover_candidate(ResearchGateInput("weekly", 7.0, 4, 2))
        self.assertTrue(result.passed)
        self.assertEqual(0.0064, result.projected_monthly_cost)

    def test_policy_report_is_meta_only(self):
        report = build_low_turnover_policy_report()
        self.assertEqual("meta_only_not_strategy", report["decision"])
        self.assertEqual(3.0, report["thresholds"]["min_hold_days"])
        self.assertTrue(report["hard_rules"])


if __name__ == "__main__":
    unittest.main()

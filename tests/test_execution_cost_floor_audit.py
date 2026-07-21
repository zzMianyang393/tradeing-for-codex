from __future__ import annotations

import unittest

from execution_cost_floor_audit import (
    build_cost_floor_audit,
    cost_for_legs,
    daily_cost_drag,
    scenario,
)


class ExecutionCostFloorAuditTests(unittest.TestCase):
    def test_cost_for_legs_uses_fixed_per_leg_floor(self):
        self.assertEqual(0.0016, cost_for_legs(2))
        self.assertEqual(0.0032, cost_for_legs(4))
        with self.assertRaises(ValueError):
            cost_for_legs(0)

    def test_scenario_sets_required_gross_thresholds(self):
        item = scenario("calendar", 4)
        self.assertEqual(0.0032, item.min_gross_for_zero_net)
        self.assertEqual(0.0042, item.min_gross_for_10bp_net)
        self.assertEqual(0.0057, item.min_gross_for_25bp_net)

    def test_turnover_cost_drag_scales_linearly(self):
        self.assertEqual(0.032, daily_cost_drag(0.0032, 10))
        with self.assertRaises(ValueError):
            daily_cost_drag(0.0032, -1)

    def test_report_is_meta_only_and_contains_hard_rules(self):
        report = build_cost_floor_audit()
        self.assertEqual("meta_only_not_strategy", report["decision"])
        self.assertEqual(3, len(report["scenarios"]))
        self.assertTrue(report["hard_rules"])


if __name__ == "__main__":
    unittest.main()

import unittest

from strategy_policy import build_strategy_policy, policy_action_for_risk


class StrategyPolicyTests(unittest.TestCase):
    def test_policy_action_for_risk_requires_confirmation_for_high_risk(self):
        self.assertEqual(policy_action_for_risk("high"), "requires_confirmation")
        self.assertEqual(policy_action_for_risk("medium"), "allow_with_risk_limit")
        self.assertEqual(policy_action_for_risk("low"), "allow")

    def test_build_strategy_policy_labels_enable_and_disable_rules(self):
        matrix = [
            {
                "strategy": "rank#1|uptrend|trend_long",
                "risk_level": "high",
                "target_drawdown_pct": 30.0,
                "target_win_rate": 0.6,
                "target_trades": 20,
                "risk_reasons": ["adjacent validation is weak"],
            }
        ]

        policy = build_strategy_policy(matrix)

        item = policy["strategies"][0]
        self.assertEqual(item["rank"], "rank#1")
        self.assertEqual(item["regime"], "uptrend")
        self.assertEqual(item["reason"], "trend_long")
        self.assertEqual(item["action"], "requires_confirmation")
        self.assertIn("regime == uptrend", item["enable_when"])
        self.assertIn("overfit_risk == high and no secondary confirmation", item["disable_when"])


if __name__ == "__main__":
    unittest.main()

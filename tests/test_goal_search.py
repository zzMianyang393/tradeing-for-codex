import unittest

from goal_search import score_goal_results


class GoalSearchTests(unittest.TestCase):
    def test_score_prioritizes_windows_above_profit_target(self):
        one_pass = {
            60: {"pnl": 12.0, "max_drawdown_pct": 20.0},
            30: {"pnl": 5.0, "max_drawdown_pct": 10.0},
        }
        two_pass = {
            60: {"pnl": 11.0, "max_drawdown_pct": 50.0},
            30: {"pnl": 10.5, "max_drawdown_pct": 40.0},
        }

        self.assertGreater(score_goal_results(two_pass, 10.0), score_goal_results(one_pass, 10.0))

    def test_score_uses_min_gap_when_pass_count_matches(self):
        worse_gap = {
            60: {"pnl": 15.0, "max_drawdown_pct": 20.0},
            30: {"pnl": 2.0, "max_drawdown_pct": 10.0},
        }
        better_gap = {
            60: {"pnl": 11.0, "max_drawdown_pct": 20.0},
            30: {"pnl": 8.0, "max_drawdown_pct": 10.0},
        }

        self.assertGreater(score_goal_results(better_gap, 10.0), score_goal_results(worse_gap, 10.0))


if __name__ == "__main__":
    unittest.main()

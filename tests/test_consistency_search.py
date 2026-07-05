import unittest

from consistency_search import parse_windows, score_rolling_report, score_rolling_summary


class ConsistencySearchTests(unittest.TestCase):
    def test_score_rewards_consistent_profitable_windows(self):
        strong = {
            "profit_rate": 0.9,
            "median_return_pct": 18.0,
            "worst_return_pct": -4.0,
            "max_drawdown_pct": 12.0,
        }
        weak = {
            "profit_rate": 0.5,
            "median_return_pct": 30.0,
            "worst_return_pct": -40.0,
            "max_drawdown_pct": 45.0,
        }

        self.assertGreater(score_rolling_summary(strong), score_rolling_summary(weak))

    def test_score_penalizes_negative_median_even_with_high_best_case(self):
        bad_tail = {
            "profit_rate": 0.4,
            "median_return_pct": -12.0,
            "worst_return_pct": -55.0,
            "max_drawdown_pct": 60.0,
        }
        steady_low = {
            "profit_rate": 0.75,
            "median_return_pct": 6.0,
            "worst_return_pct": -8.0,
            "max_drawdown_pct": 18.0,
        }

        self.assertGreater(score_rolling_summary(steady_low), score_rolling_summary(bad_tail))

    def test_report_score_prioritizes_180_day_stability_over_short_window_strength(self):
        short_strong_long_weak = {
            "windows": {
                "180": {"summary": {"profit_rate": 0.2, "median_return_pct": -15.0, "worst_return_pct": -35.0, "max_drawdown_pct": 40.0}},
                "90": {"summary": {"profit_rate": 0.5, "median_return_pct": -2.0, "worst_return_pct": -8.0, "max_drawdown_pct": 15.0}},
                "60": {"summary": {"profit_rate": 1.0, "median_return_pct": 25.0, "worst_return_pct": 5.0, "max_drawdown_pct": 10.0}},
                "30": {"summary": {"profit_rate": 1.0, "median_return_pct": 20.0, "worst_return_pct": 4.0, "max_drawdown_pct": 8.0}},
                "14": {"summary": {"profit_rate": 1.0, "median_return_pct": 12.0, "worst_return_pct": 3.0, "max_drawdown_pct": 6.0}},
                "7": {"summary": {"profit_rate": 1.0, "median_return_pct": 8.0, "worst_return_pct": 2.0, "max_drawdown_pct": 4.0}},
            }
        }
        long_stable_short_modest = {
            "windows": {
                "180": {"summary": {"profit_rate": 0.7, "median_return_pct": 4.0, "worst_return_pct": -8.0, "max_drawdown_pct": 18.0}},
                "90": {"summary": {"profit_rate": 0.7, "median_return_pct": 3.0, "worst_return_pct": -6.0, "max_drawdown_pct": 14.0}},
                "60": {"summary": {"profit_rate": 0.6, "median_return_pct": 2.0, "worst_return_pct": -5.0, "max_drawdown_pct": 12.0}},
                "30": {"summary": {"profit_rate": 0.6, "median_return_pct": 1.0, "worst_return_pct": -4.0, "max_drawdown_pct": 10.0}},
                "14": {"summary": {"profit_rate": 0.6, "median_return_pct": 1.0, "worst_return_pct": -4.0, "max_drawdown_pct": 8.0}},
                "7": {"summary": {"profit_rate": 0.6, "median_return_pct": 1.0, "worst_return_pct": -4.0, "max_drawdown_pct": 6.0}},
            }
        }

        short_score, _ = score_rolling_report(short_strong_long_weak)
        stable_score, _ = score_rolling_report(long_stable_short_modest)

        self.assertGreater(stable_score, short_score)

    def test_parse_windows_accepts_comma_separated_days(self):
        self.assertEqual((180, 90, 30), parse_windows("180,90,30"))


if __name__ == "__main__":
    unittest.main()

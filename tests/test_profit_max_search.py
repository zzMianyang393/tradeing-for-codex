import unittest

from profit_max_search import concentration_ratio, score_candidate


def _result(pnl, drawdown=5.0, trades=10, trade_pnls=None):
    if trade_pnls is None:
        trade_pnls = [pnl / max(trades, 1)] * trades
    return {
        "available": True,
        "pnl": pnl,
        "return_pct": pnl * 10.0,
        "max_drawdown_pct": drawdown,
        "trades": trades,
        "win_rate": 0.75,
        "trades_detail": [{"pnl": item} for item in trade_pnls],
    }


class ProfitMaxSearchTests(unittest.TestCase):
    def test_concentration_ratio_reports_largest_positive_trade_share(self):
        result = _result(10.0, trades=3, trade_pnls=[7.0, 2.0, 1.0])

        self.assertEqual(0.7, concentration_ratio(result))

    def test_score_rewards_short_window_improvement(self):
        baseline = {7: 0.4, 14: 10.0, 30: 11.0, 60: 11.0, 90: 15.0, 180: 15.0, 365: 41.0}
        weak = {day: _result(pnl) for day, pnl in baseline.items()}
        improved = {day: _result(pnl + (5.0 if day in (7, 14, 30, 90) else 1.0)) for day, pnl in baseline.items()}

        self.assertGreater(score_candidate(improved, baseline)["score"], score_candidate(weak, baseline)["score"])

    def test_score_penalizes_one_trade_short_window_result(self):
        baseline = {14: 10.0}
        balanced = {14: _result(20.0, trades=5, trade_pnls=[4.0, 4.0, 4.0, 4.0, 4.0])}
        concentrated = {14: _result(20.0, trades=2, trade_pnls=[18.0, 2.0])}

        balanced_score = score_candidate(balanced, baseline)
        concentrated_score = score_candidate(concentrated, baseline)

        self.assertGreater(balanced_score["score"], concentrated_score["score"])
        self.assertIn("14d concentration 90.00% > 70.00%", concentrated_score["warnings"])

    def test_score_penalizes_bad_rolling_audit_summary(self):
        baseline = {14: 10.0}
        results = {14: _result(40.0, trades=6)}
        rolling = {
            "14": {
                "summary": {
                    "profit_rate": 0.75,
                    "worst_return_pct": -482.87,
                    "max_drawdown_pct": 39.11,
                }
            }
        }

        clean_score = score_candidate(results, baseline)["score"]
        rolling_score = score_candidate(results, baseline, rolling_report=rolling)

        self.assertLess(rolling_score["score"], clean_score - 200.0)
        self.assertIn("14d rolling worst return -482.87% < -35.00%", rolling_score["warnings"])

    def test_score_penalizes_low_rolling_profit_rate(self):
        baseline = {180: 15.0}
        results = {180: _result(40.0, trades=25)}
        rolling = {
            "180": {
                "summary": {
                    "profit_rate": 0.5,
                    "worst_return_pct": -20.0,
                    "max_drawdown_pct": 35.0,
                }
            }
        }

        scored = score_candidate(results, baseline, rolling_report=rolling)

        self.assertIn("180d rolling profit rate 50.00% < 70.00%", scored["warnings"])


if __name__ == "__main__":
    unittest.main()

import unittest

from validation import audit_report


class ValidationAuditTests(unittest.TestCase):
    def test_flags_missing_required_windows(self):
        report = {
            "windows": {
                "365": {"available": False, "reason": "missing"},
                "180": {"available": True, "pnl": 1.0, "win_rate": 0.7},
                "90": {"available": True, "pnl": 1.0, "win_rate": 0.7},
                "60": {"available": True, "pnl": 1.0, "win_rate": 0.7},
                "30": {"available": True, "pnl": 1.0, "win_rate": 0.7},
                "7": {"available": True, "pnl": 1.0, "win_rate": 0.7},
            }
        }

        audit = audit_report(report)

        self.assertFalse(audit["complete"])
        self.assertIn("365d unavailable", audit["failures"])

    def test_requires_profit_and_minimum_win_rate(self):
        report = {
            "windows": {
                "90": {"available": True, "pnl": -0.1, "win_rate": 0.7},
                "60": {"available": True, "pnl": 1.0, "win_rate": 0.59},
            }
        }

        audit = audit_report(report, required_windows=(90, 60))

        self.assertFalse(audit["complete"])
        self.assertIn("90d pnl -0.1 <= 0", audit["failures"])
        self.assertIn("60d win rate 59.00% < 60.00%", audit["failures"])

    def test_marks_complete_when_all_requirements_pass(self):
        report = {
            "windows": {
                "90": {"available": True, "pnl": 0.1, "win_rate": 0.61},
                "60": {"available": True, "pnl": 0.1, "win_rate": 0.62},
            }
        }

        audit = audit_report(report, required_windows=(90, 60))

        self.assertTrue(audit["complete"])
        self.assertEqual([], audit["failures"])

    def test_uses_custom_minimum_win_rate(self):
        report = {
            "windows": {
                "30": {"available": True, "pnl": 1.0, "win_rate": 0.6667},
            }
        }

        audit = audit_report(report, required_windows=(30,), min_win_rate=0.68)

        self.assertFalse(audit["complete"])
        self.assertIn("30d win rate 66.67% < 68.00%", audit["failures"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from okx_oi_audit import DAY_MS, audit_series


class OkxOiAuditTests(unittest.TestCase):
    def test_reports_daily_gaps_and_change_distribution(self):
        report = audit_series([
            (0, 100.0),
            (DAY_MS, 110.0),
            (DAY_MS * 3, 99.0),
        ])
        self.assertEqual(1, report["non_daily_gap_count"])
        self.assertEqual(2.0, report["max_gap_days"])
        self.assertEqual(2, report["daily_change"]["count"])
        self.assertEqual(2, report["daily_change"]["abs_ge_5pct_events"])

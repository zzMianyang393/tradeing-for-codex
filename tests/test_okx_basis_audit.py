from __future__ import annotations

import unittest

from okx_basis_audit import BAR_MS, audit_pair


class OkxBasisAuditTests(unittest.TestCase):
    def test_reports_cost_qualified_premium_runs(self):
        spot = {0: 100.0, BAR_MS: 100.0, BAR_MS * 2: 100.0}
        swap = {0: 100.3, BAR_MS: 100.4, BAR_MS * 2: 100.0}
        report = audit_pair(spot, swap)
        self.assertEqual(2, report["swap_premium"]["bars_at_or_above_cost"])
        self.assertEqual(2, report["swap_premium"]["max_run_15m_bars"])

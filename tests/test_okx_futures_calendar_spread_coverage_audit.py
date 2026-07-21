from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
import tempfile

from okx_futures_calendar_spread_coverage_audit import CloseSeries, audit_calendar_spread_coverage, discover_futures_paths
from okx_futures_calendar_spread_pipeline import parse_utc_ms


class OkxFuturesCalendarSpreadCoverageAuditTests(unittest.TestCase):
    def test_passes_when_selected_futures_align_with_swap_days(self):
        ts1 = parse_utc_ms("2024-07-11 00:00:00")
        ts2 = parse_utc_ms("2024-07-12 00:00:00")
        futures = [CloseSeries("BTC-USDT-240927", {ts1: 101.0, ts2: 102.0})]
        swap = CloseSeries("BTC-USDT-SWAP", {ts1: 100.0, ts2: 100.0})
        report = audit_calendar_spread_coverage("BTC-USDT", futures, swap, date(2024, 7, 11), date(2024, 7, 12), min_active_days=2)
        self.assertTrue(report["passed"])
        self.assertEqual("coverage_ready", report["decision"])
        self.assertEqual(2, report["active_days"])
        self.assertEqual({"BTC-USDT-240927": 2}, report["rows_by_contract"])

    def test_blocks_when_selected_future_rows_are_missing(self):
        ts1 = parse_utc_ms("2024-07-11 00:00:00")
        ts2 = parse_utc_ms("2024-07-12 00:00:00")
        futures = [CloseSeries("BTC-USDT-240927", {ts1: 101.0})]
        swap = CloseSeries("BTC-USDT-SWAP", {ts1: 100.0, ts2: 100.0})
        report = audit_calendar_spread_coverage("BTC-USDT", futures, swap, date(2024, 7, 11), date(2024, 7, 12), min_active_days=2)
        self.assertFalse(report["passed"])
        self.assertEqual("coverage_blocked", report["decision"])
        self.assertEqual(1, report["missing_selected_futures_rows"])

    def test_uses_rollover_rule_when_old_contract_enters_final_72h(self):
        before_roll = parse_utc_ms("2024-09-24 07:59:00")
        after_roll = parse_utc_ms("2024-09-24 08:00:00")
        futures = [
            CloseSeries("BTC-USDT-240927", {before_roll: 101.0, after_roll: 999.0}),
            CloseSeries("BTC-USDT-241227", {after_roll: 103.0}),
        ]
        swap = CloseSeries("BTC-USDT-SWAP", {before_roll: 100.0, after_roll: 100.0})
        report = audit_calendar_spread_coverage("BTC-USDT", futures, swap, date(2024, 9, 24), date(2024, 9, 24), min_active_days=1)
        self.assertTrue(report["passed"])
        self.assertEqual({"BTC-USDT-240927": 1, "BTC-USDT-241227": 1}, report["rows_by_contract"])

    def test_discovers_family_futures_files_from_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "BTC-USDT-240927_future_1m.csv").write_text("", encoding="utf-8")
            (root / "ETH-USDT-240927_future_1m.csv").write_text("", encoding="utf-8")
            paths = discover_futures_paths("BTC-USDT", root)
        self.assertEqual(["BTC-USDT-240927_future_1m.csv"], [path.name for path in paths])


if __name__ == "__main__":
    unittest.main()

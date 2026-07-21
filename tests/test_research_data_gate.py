from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_data_gate import assess_csv, assess_metadata, audit_data_directory


class ResearchDataGateTests(unittest.TestCase):
    def test_okx_ohlcv_with_full_year_is_execution_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTC_15m.csv"
            path.write_text(
                "timestamp,open\n2024-01-01 00:00:00,1\n2025-01-01 00:00:00,2\n",
                encoding="utf-8",
            )
            result = assess_csv(path)
        self.assertTrue(result.annual_research_eligible)
        self.assertTrue(result.execution_compatible)

    def test_short_okx_funding_is_rejected_for_annual_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTC-USDT-SWAP_funding.csv"
            path.write_text(
                "timestamp_utc,funding_rate\n2026-01-01 00:00:00,0\n2026-04-01 00:00:00,0\n",
                encoding="utf-8",
            )
            result = assess_csv(path)
        self.assertFalse(result.annual_research_eligible)
        self.assertIn("低于 365 天", result.reasons[0])

    def test_external_proxy_with_sparse_fields_is_not_execution_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metrics.meta.json"
            path.write_text(json.dumps({
                "source": "binance", "execution_compatibility": "research_proxy_only_not_okx_execution",
                "requested_start": "2024-01-01", "requested_end": "2025-01-02", "rows": 367,
                "field_coverage": {"oi": {"coverage_ratio": 1.0}, "top_trader": {"coverage_ratio": 0.1}},
            }), encoding="utf-8")
            result = assess_metadata(path)
        self.assertFalse(result.annual_research_eligible)
        self.assertEqual(("top_trader",), result.sparse_fields)

    def test_metadata_accepts_first_and_last_epoch_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "funding.meta.json"
            path.write_text(json.dumps({
                "source": "binance", "execution_compatibility": "research_proxy_only_not_okx_execution",
                "first_ts": 1704067200000, "last_ts": 1735776000000, "rows": 367,
            }), encoding="utf-8")
            result = assess_metadata(path)
        self.assertEqual(367.0, result.duration_days)
        self.assertIn("研究代理", result.reasons[0])

    def test_directory_report_separates_eligible_and_ineligible_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "BTC_15m.csv").write_text(
                "timestamp,open\n2024-01-01 00:00:00,1\n2025-01-01 00:00:00,2\n", encoding="utf-8"
            )
            (data / "BTC-USDT-SWAP_open_interest.csv").write_text(
                "timestamp_utc,open_interest\n2026-07-01 00:00:00,1\n2026-07-02 00:00:00,2\n", encoding="utf-8"
            )
            report = audit_data_directory(data)
        self.assertEqual(2, report["summary"]["total"])
        self.assertEqual(1, report["summary"]["annual_execution_eligible"])
        self.assertIn("funding", report["summary"]["annual_execution_data_gaps"])


if __name__ == "__main__":
    unittest.main()

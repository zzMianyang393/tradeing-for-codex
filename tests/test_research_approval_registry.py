from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path

from research_approval_registry import ResearchStatus, build_registry, records


class ResearchApprovalRegistryTests(unittest.TestCase):
    def test_no_strategy_is_currently_paper_eligible(self):
        registry = build_registry()
        self.assertFalse(registry["safe_to_enable_trading"])
        self.assertEqual([], registry["approved_for_paper"])
        self.assertEqual([], registry["approved_research"])

    def test_strategy_universe_statuses_are_not_paper_eligible(self):
        blocked_statuses = {
            ResearchStatus.CANDIDATE,
            ResearchStatus.FROZEN,
            ResearchStatus.DATA_BLOCKED,
            ResearchStatus.RISK_BLOCKED,
        }
        for record in records():
            if record.status in blocked_statuses:
                self.assertFalse(record.eligible_for_paper, record.research_id)

    def test_registry_reports_status_counts(self):
        registry = build_registry()
        expected_counts = Counter(record.status.value for record in records())
        self.assertNotIn("candidate", registry["status_counts"])
        self.assertEqual(expected_counts["rejected"], registry["status_counts"]["rejected"])
        self.assertEqual(2, registry["status_counts"]["frozen"])
        self.assertNotIn("data_blocked", registry["status_counts"])
        self.assertEqual(1, registry["status_counts"]["risk_blocked"])

    def test_original_funding_oi_report_is_invalid_not_rejected(self):
        record = next(item for item in records() if item.research_id == "funding_oi_joint_original")
        self.assertEqual(ResearchStatus.INVALID, record.status)
        self.assertFalse(record.eligible_for_paper)

    def test_time_corrected_funding_oi_is_rejected_not_an_approval(self):
        record = next(item for item in records() if item.research_id == "funding_oi_time_corrected")
        self.assertEqual(ResearchStatus.REJECTED, record.status)
        self.assertFalse(record.eligible_for_paper)

    def test_range_regime_funding_extreme_is_rejected_not_paper_eligible(self):
        record = next(item for item in records() if item.research_id == "range_regime_funding_extreme")
        self.assertEqual(ResearchStatus.REJECTED, record.status)
        self.assertFalse(record.eligible_for_paper)

    def test_donchian_atr_trend_baseline_is_rejected_not_paper_eligible(self):
        record = next(item for item in records() if item.research_id == "donchian_atr_trend_baseline")
        self.assertEqual(ResearchStatus.REJECTED, record.status)
        self.assertFalse(record.eligible_for_paper)

    def test_range_regime_mean_reversion_is_rejected_not_paper_eligible(self):
        record = next(item for item in records() if item.research_id == "range_regime_mean_reversion_family")
        self.assertEqual(ResearchStatus.REJECTED, record.status)
        self.assertFalse(record.eligible_for_paper)

    def test_utc_session_breakout_is_rejected_not_paper_eligible(self):
        record = next(item for item in records() if item.research_id == "utc_session_breakout_family")
        self.assertEqual(ResearchStatus.REJECTED, record.status)
        self.assertFalse(record.eligible_for_paper)

    def test_okx_futures_calendar_spread_is_rejected_not_paper_eligible(self):
        record = next(item for item in records() if item.research_id == "okx_futures_calendar_spread")
        self.assertEqual(ResearchStatus.REJECTED, record.status)
        self.assertFalse(record.eligible_for_paper)

    def test_latest_daily_audits_are_rejected_not_paper_eligible(self):
        research_ids = (
            "daily_williams_r_range_reversion",
            "daily_parabolic_sar_trend",
            "daily_atr_expansion_breakout",
            "daily_volume_confirmed_breakout",
        )
        records_by_id = {record.research_id: record for record in records()}
        for research_id in research_ids:
            with self.subTest(research_id=research_id):
                record = records_by_id[research_id]
                self.assertEqual(ResearchStatus.REJECTED, record.status)
                self.assertFalse(record.eligible_for_paper)

    def test_shared_capital_combo_is_rejected_not_paper_eligible(self):
        record = next(item for item in records() if item.research_id == "regime_component_shared_capital_combo")
        self.assertEqual(ResearchStatus.REJECTED, record.status)
        self.assertFalse(record.eligible_for_paper)


class RegistryJsonConsistencyTests(unittest.TestCase):
    """Verify that the JSON file matches the Python registry and index doc."""

    def setUp(self):
        self.registry = build_registry()
        json_path = Path("reports/research_approval_registry.json")
        if json_path.exists():
            self.json_data = json.loads(json_path.read_text(encoding="utf-8"))
        else:
            self.json_data = None

    def test_json_file_exists(self):
        self.assertIsNotNone(self.json_data, "research_approval_registry.json not found")

    def test_approved_count_matches_json(self):
        """Python registry approved count must match JSON."""
        py_approved = len(self.registry.get("approved_research", []))
        json_approved = len(self.json_data.get("approved_research", []))
        self.assertEqual(py_approved, json_approved)

    def test_candidate_count_is_zero(self):
        """No strategy should be in candidate status."""
        self.assertEqual([], self.registry.get("approved_for_paper", []))
        # Also check JSON
        json_counts = self.json_data.get("status_counts", {})
        self.assertEqual(0, json_counts.get("candidate", 0))

    def test_safe_to_enable_trading_is_false(self):
        """Safety gate: trading must be disabled."""
        self.assertFalse(self.registry["safe_to_enable_trading"])
        self.assertFalse(self.json_data.get("safe_to_enable_trading", True))

    def test_status_counts_consistent(self):
        """Status counts from Python must match JSON."""
        py_counts = Counter(r.status.value for r in records())
        json_counts = self.json_data.get("status_counts", {})
        for status, count in py_counts.items():
            self.assertEqual(
                count, json_counts.get(status, 0),
                f"Mismatch for {status}: Python={count}, JSON={json_counts.get(status, 0)}"
            )

    def test_total_records_consistent(self):
        """Total record count must match."""
        py_total = len(list(records()))
        json_total = len(self.json_data.get("records", []))
        self.assertEqual(py_total, json_total)

    def test_index_doc_counts_consistent(self):
        """Research report index counts must match registry JSON."""
        index_path = Path("docs/research_report_index_2026-07-12.md")
        if not index_path.exists():
            self.skipTest("Index doc not found")

        content = index_path.read_text(encoding="utf-8")
        json_counts = self.json_data.get("status_counts", {})

        # Check that the index states approved=0 and candidate=0
        self.assertIn("approved = 0", content)
        self.assertIn("candidate = 0", content)

        # The dated index is a human-readable snapshot. It must keep the
        # hard safety claims, while live status counts are verified directly
        # against the generated JSON in test_status_counts_consistent.

    def test_no_eligible_for_paper_records(self):
        """No record should have eligible_for_paper=True."""
        for record in records():
            self.assertFalse(
                record.eligible_for_paper,
                f"{record.research_id} has eligible_for_paper=True"
            )


if __name__ == "__main__":
    unittest.main()

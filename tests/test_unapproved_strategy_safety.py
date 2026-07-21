from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from config import BacktestConfig
from runner import main


class UnapprovedStrategySafetyTests(unittest.TestCase):
    def test_default_configuration_disables_all_research_entry_engines(self):
        config = BacktestConfig()
        self.assertFalse(config.enable_rule_trading)
        self.assertFalse(config.enable_pairs_trading)
        self.assertFalse(config.enable_candidate_pool)
        self.assertFalse(config.enable_ml_module)
        self.assertFalse(config.enable_funding_module)
        self.assertFalse(config.enable_open_interest_module)
        self.assertFalse(config.enable_trade_flow_module)
        self.assertFalse(config.enable_order_book_module)

    def test_cli_rejects_manual_enablement_of_unapproved_rule_strategies(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([
                    "--once",
                    "--db", str(Path(tmp) / "state.db"),
                    "--enable-rule-strategies",
                ])
        payload = json.loads(output.getvalue())
        self.assertEqual(2, code)
        self.assertEqual(["--enable-rule-strategies"], payload["blocked_flags"])

    def test_cli_rejects_manual_enablement_of_unapproved_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = main([
                    "--once",
                    "--db", str(Path(tmp) / "state.db"),
                    "--enable-pairs",
                    "--pairs", "FIL-OP",
                ])
        payload = json.loads(output.getvalue())
        self.assertEqual(2, code)
        self.assertEqual(["--enable-pairs"], payload["blocked_flags"])


if __name__ == "__main__":
    unittest.main()

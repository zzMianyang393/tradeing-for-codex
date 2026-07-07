from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from config import BacktestConfig
from monte_carlo import MonteCarloReport
from param_sensitivity import SensitivityReport
from walk_forward import WalkForwardReport


class FullValidationTests(unittest.TestCase):
    def test_single_trade_contribution_flags_top_two_dominance(self):
        from full_validation import check_single_trade_contribution

        result = check_single_trade_contribution(
            [{"pnl": 8.0}, {"pnl": 1.0}, {"pnl": 1.0}, {"pnl": -2.0}],
            top_n=2,
            max_share=0.70,
        )

        self.assertFalse(result["passed"])
        self.assertEqual(0.9, result["top_positive_share"])
        self.assertEqual(2, result["top_n"])

    def test_drawdown_stress_flags_excessive_stressed_drawdown(self):
        from full_validation import run_drawdown_stress

        result = run_drawdown_stress(
            [{"pnl": 2.0}, {"pnl": -6.0}, {"pnl": 1.0}],
            initial_equity=10.0,
            loss_multiplier=2.0,
            max_drawdown_limit=0.45,
        )

        self.assertFalse(result["passed"])
        self.assertGreater(result["max_drawdown"], 0.45)

    def test_run_full_validation_combines_validation_sections(self):
        from full_validation import run_full_validation

        latest_report = {
            "windows": {
                "7": {"available": True, "pnl": 1.0, "return_pct": 10.0, "win_rate": 0.7},
            },
            "trades_detail": [{"pnl": 0.4}, {"pnl": -0.1}, {"pnl": 0.2}],
        }

        with (
            patch("full_validation.run_walk_forward", return_value=WalkForwardReport(passed=True)),
            patch("full_validation.run_sensitivity", return_value=SensitivityReport(passed=True)),
            patch("full_validation.run_monte_carlo", return_value=MonteCarloReport(n_simulations=10, passed=True)),
        ):
            report = run_full_validation(
                market={"BTC-USDT-SWAP": []},
                config=BacktestConfig(),
                latest_report=latest_report,
                required_windows=(7,),
                monte_carlo_simulations=10,
            )

        self.assertIn("latest", report)
        self.assertIn("walk_forward", report)
        self.assertIn("sensitivity", report)
        self.assertIn("monte_carlo", report)
        self.assertIn("single_trade_contribution", report)
        self.assertIn("drawdown_stress", report)
        self.assertTrue(report["complete"])

    def test_main_writes_full_validation_report(self):
        from full_validation import main

        latest_report = {
            "windows": {
                "7": {"available": True, "pnl": 1.0, "return_pct": 10.0, "win_rate": 0.7},
            },
            "trades_detail": [{"pnl": 0.4}, {"pnl": -0.1}, {"pnl": 0.2}],
        }

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "full_validation.json"
            with (
                patch("full_validation.load_market", return_value={"BTC-USDT-SWAP": []}),
                patch("full_validation.run_report", return_value=latest_report),
                patch("full_validation.run_walk_forward", return_value=WalkForwardReport(passed=True)),
                patch("full_validation.run_sensitivity", return_value=SensitivityReport(passed=True)),
                patch("full_validation.run_monte_carlo", return_value=MonteCarloReport(n_simulations=10, passed=True)),
            ):
                code = main(["--out", str(out), "--required-windows", "7", "--monte-carlo-sims", "10"])

            self.assertEqual(0, code)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(payload["complete"])
            self.assertEqual(asdict(WalkForwardReport(passed=True)), payload["walk_forward"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from monte_carlo import (
    MonteCarloResult, MonteCarloReport,
    run_monte_carlo, _max_drawdown, _sharpe_ratio, _percentile,
    save_monte_carlo_report, load_monte_carlo_report,
)
from walk_forward import (
    WindowResult, WalkForwardReport,
    save_walk_forward_report, load_walk_forward_report,
)
from param_sensitivity import (
    ParamResult, SensitivityReport,
    save_sensitivity_report, load_sensitivity_report,
)


# ---------------------------------------------------------------------------
# Monte Carlo tests
# ---------------------------------------------------------------------------

class TestMonteCarloDataclasses(unittest.TestCase):
    def test_result_defaults(self):
        r = MonteCarloResult()
        self.assertEqual(r.simulation_id, 0)
        self.assertEqual(r.total_pnl, 0.0)

    def test_report_defaults(self):
        r = MonteCarloReport()
        self.assertEqual(r.n_simulations, 0)
        self.assertFalse(r.passed)


class TestMaxDrawdown(unittest.TestCase):
    def test_no_drawdown(self):
        pnls = [1.0, 1.0, 1.0]
        dd = _max_drawdown(pnls, 10.0)
        self.assertAlmostEqual(dd, 0.0)

    def test_simple_drawdown(self):
        pnls = [1.0, -3.0, 1.0]
        dd = _max_drawdown(pnls, 10.0)
        self.assertGreater(dd, 0)

    def test_empty(self):
        dd = _max_drawdown([], 10.0)
        self.assertAlmostEqual(dd, 0.0)


class TestSharpeRatio(unittest.TestCase):
    def test_positive_returns(self):
        pnls = [0.1, 0.2, 0.15, 0.12]
        sharpe = _sharpe_ratio(pnls)
        self.assertGreater(sharpe, 0)

    def test_negative_returns(self):
        pnls = [-0.1, -0.2, -0.15]
        sharpe = _sharpe_ratio(pnls)
        self.assertLess(sharpe, 0)

    def test_zero_std(self):
        pnls = [0.1, 0.1, 0.1]
        sharpe = _sharpe_ratio(pnls)
        self.assertAlmostEqual(sharpe, 0.0, places=5)

    def test_empty(self):
        sharpe = _sharpe_ratio([])
        self.assertEqual(sharpe, 0)


class TestPercentile(unittest.TestCase):
    def test_basic(self):
        values = [1, 2, 3, 4, 5]
        self.assertAlmostEqual(_percentile(values, 0.5), 3.0)

    def test_low(self):
        values = [1, 2, 3, 4, 5]
        self.assertAlmostEqual(_percentile(values, 0.0), 1.0)

    def test_high(self):
        values = [1, 2, 3, 4, 5]
        self.assertAlmostEqual(_percentile(values, 1.0), 5.0)

    def test_empty(self):
        self.assertEqual(_percentile([], 0.5), 0.0)


class TestRunMonteCarlo(unittest.TestCase):
    def test_basic(self):
        trades = [{"pnl": 1.0}, {"pnl": -0.5}, {"pnl": 2.0}, {"pnl": -0.3}]
        report = run_monte_carlo(trades, n_simulations=100, seed=42)
        self.assertEqual(report.n_simulations, 100)
        self.assertGreater(report.mean_pnl, 0)
        self.assertEqual(report.original_pnl, 2.2)

    def test_empty_trades(self):
        report = run_monte_carlo([], n_simulations=100)
        self.assertEqual(report.n_simulations, 0)

    def test_single_trade(self):
        trades = [{"pnl": 1.0}]
        report = run_monte_carlo(trades, n_simulations=10, seed=42)
        self.assertEqual(report.n_simulations, 10)

    def test_statistics(self):
        trades = [{"pnl": 1.0}] * 10 + [{"pnl": -0.5}] * 5
        report = run_monte_carlo(trades, n_simulations=100, seed=42)
        self.assertGreaterEqual(report.p75_pnl, report.p25_pnl)
        self.assertGreaterEqual(report.p50_pnl, report.p5_pnl)


class TestMonteCarloCache(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mc.json"
            report = MonteCarloReport(
                n_simulations=10,
                mean_pnl=1.5,
                passed=True,
                results=[MonteCarloResult(simulation_id=0, total_pnl=1.0)],
            )
            save_monte_carlo_report(report, path)
            loaded = load_monte_carlo_report(path)
            self.assertEqual(loaded.n_simulations, 10)
            self.assertTrue(loaded.passed)


# ---------------------------------------------------------------------------
# Walk-Forward tests
# ---------------------------------------------------------------------------

class TestWalkForwardDataclasses(unittest.TestCase):
    def test_window_result_defaults(self):
        w = WindowResult()
        self.assertEqual(w.train_days, 0)

    def test_report_defaults(self):
        r = WalkForwardReport()
        self.assertFalse(r.passed)


class TestWalkForwardCache(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wf.json"
            report = WalkForwardReport(
                windows=[WindowResult(train_days=90, test_days=30, train_pnl=5.0, test_pnl=3.0)],
                avg_oos_pnl=3.0,
                passed=True,
            )
            save_walk_forward_report(report, path)
            loaded = load_walk_forward_report(path)
            self.assertTrue(loaded.passed)
            self.assertEqual(len(loaded.windows), 1)

    def test_load_nonexistent(self):
        loaded = load_walk_forward_report(Path("/nonexistent"))
        self.assertFalse(loaded.passed)


# ---------------------------------------------------------------------------
# Parameter Sensitivity tests
# ---------------------------------------------------------------------------

class TestSensitivityDataclasses(unittest.TestCase):
    def test_param_result_defaults(self):
        r = ParamResult()
        self.assertEqual(r.param_name, "")

    def test_report_defaults(self):
        r = SensitivityReport()
        self.assertFalse(r.passed)


class TestSensitivityCache(unittest.TestCase):
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sens.json"
            report = SensitivityReport(
                params_tested=5,
                overall_stability=0.8,
                passed=True,
                results=[ParamResult(param_name="risk_per_trade")],
            )
            save_sensitivity_report(report, path)
            loaded = load_sensitivity_report(path)
            self.assertTrue(loaded.passed)
            self.assertEqual(loaded.params_tested, 5)


# ---------------------------------------------------------------------------
# Integration: Monte Carlo + trades
# ---------------------------------------------------------------------------

class TestMonteCarloIntegration(unittest.TestCase):
    def test_with_realistic_trades(self):
        """Test with realistic trade data."""
        trades = [
            {"pnl": 0.5, "win": True},
            {"pnl": -0.3, "win": False},
            {"pnl": 1.2, "win": True},
            {"pnl": -0.1, "win": False},
            {"pnl": 0.8, "win": True},
            {"pnl": -0.4, "win": False},
            {"pnl": 2.0, "win": True},
            {"pnl": -0.2, "win": False},
        ]
        report = run_monte_carlo(trades, n_simulations=500, seed=42)
        self.assertEqual(report.n_simulations, 500)
        self.assertGreater(report.original_pnl, 0)
        self.assertGreater(report.positive_pct, 0.5)

    def test_consistency_with_seed(self):
        """Same seed should produce same results."""
        trades = [{"pnl": 1.0}, {"pnl": -0.5}]
        r1 = run_monte_carlo(trades, n_simulations=50, seed=123)
        r2 = run_monte_carlo(trades, n_simulations=50, seed=123)
        self.assertAlmostEqual(r1.mean_pnl, r2.mean_pnl)


if __name__ == "__main__":
    unittest.main()

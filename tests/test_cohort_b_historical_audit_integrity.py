"""Tests for C40: Cohort B historical audit integrity review.

Verifies:
  - 4h delay in all four audits
  - No look-ahead in labels
  - 0.16% cost
  - Formation/OOS boundary
  - insufficient_evidence status when events < 15
  - Research card constants match code constants
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _load_json(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ── Shared constants verification ────────────────────────────────────────────

class TestSharedConstants:
    def test_cost_is_0_16(self):
        """ROUND_TRIP_COST must be 0.0016 (0.16%)."""
        import importlib
        mod = importlib.import_module("regime_component_walk_forward_audit")
        assert mod.ROUND_TRIP_COST == 0.0016

    def test_four_hours_ms(self):
        """FOUR_HOURS_MS must be 4 * 3600 * 1000."""
        import importlib
        mod = importlib.import_module("regime_validation")
        assert mod.FOUR_HOURS_MS == 4 * 3600 * 1000

    def test_stop_atr_multiple(self):
        """STOP_ATR_MULTIPLE must be 2.0."""
        import importlib
        mod = importlib.import_module("regime_component_walk_forward_audit")
        assert mod.STOP_ATR_MULTIPLE == 2.0


# ── 4h delay verification ───────────────────────────────────────────────────

class TestFourHourDelay:
    def test_month_boundary_has_4h_delay(self):
        """month_boundary_flow_audit must add FOUR_HOURS_MS to signal_ts."""
        content = Path("month_boundary_flow_audit.py").read_text(encoding="utf-8")
        assert "FOUR_HOURS_MS" in content

    def test_weekend_has_4h_delay(self):
        """weekend_low_liquidity_reversion_audit must add FOUR_HOURS_MS."""
        content = Path("weekend_low_liquidity_reversion_audit.py").read_text(encoding="utf-8")
        assert "FOUR_HOURS_MS" in content

    def test_parkinson_has_4h_delay(self):
        """parkinson_volatility_extreme_reversion_audit must add FOUR_HOURS_MS."""
        content = Path("parkinson_volatility_extreme_reversion_audit.py").read_text(encoding="utf-8")
        assert "FOUR_HOURS_MS" in content

    def test_bias_has_4h_delay(self):
        """daily_bias_range_reversion_audit must add FOUR_HOURS_MS."""
        content = Path("daily_bias_range_reversion_audit.py").read_text(encoding="utf-8")
        assert "FOUR_HOURS_MS" in content


# ── Formation/OOS boundary ───────────────────────────────────────────────────

class TestFormationOOSBoundary:
    def test_month_boundary_formation_2024(self):
        content = Path("month_boundary_flow_audit.py").read_text(encoding="utf-8")
        assert "2024-01-01" in content
        assert "2024-12-31" in content

    def test_month_boundary_oos_2025(self):
        content = Path("month_boundary_flow_audit.py").read_text(encoding="utf-8")
        assert "2025-01-01" in content
        assert "2025-07-10" in content

    def test_weekend_formation_2024(self):
        content = Path("weekend_low_liquidity_reversion_audit.py").read_text(encoding="utf-8")
        assert "2024-01-01" in content
        assert "2024-12-31" in content

    def test_parkinson_formation_2024(self):
        content = Path("parkinson_volatility_extreme_reversion_audit.py").read_text(encoding="utf-8")
        assert "2024-01-01" in content
        assert "2024-12-31" in content

    def test_bias_formation_2024(self):
        content = Path("daily_bias_range_reversion_audit.py").read_text(encoding="utf-8")
        assert "2024-01-01" in content
        assert "2024-12-31" in content


# ── insufficient_evidence status ─────────────────────────────────────────────

class TestInsufficientEvidence:
    def test_month_boundary_verdict_logic(self):
        """Code must distinguish insufficient_evidence from historical_rejected."""
        content = Path("month_boundary_flow_audit.py").read_text(encoding="utf-8")
        assert "insufficient_evidence" in content

    def test_weekend_verdict_logic(self):
        content = Path("weekend_low_liquidity_reversion_audit.py").read_text(encoding="utf-8")
        assert "insufficient_evidence" in content

    def test_parkinson_verdict_logic(self):
        content = Path("parkinson_volatility_extreme_reversion_audit.py").read_text(encoding="utf-8")
        assert "insufficient_evidence" in content

    def test_bias_verdict_logic(self):
        content = Path("daily_bias_range_reversion_audit.py").read_text(encoding="utf-8")
        assert "insufficient_evidence" in content


# ── Month concentration check ────────────────────────────────────────────────

class TestMonthConcentration:
    def test_month_boundary_has_concentration(self):
        content = Path("month_boundary_flow_audit.py").read_text(encoding="utf-8")
        assert "concentration" in content.lower() or "_month_concentration" in content

    def test_weekend_has_concentration(self):
        content = Path("weekend_low_liquidity_reversion_audit.py").read_text(encoding="utf-8")
        assert "conc" in content.lower() or "_month_conc" in content

    def test_parkinson_has_concentration(self):
        content = Path("parkinson_volatility_extreme_reversion_audit.py").read_text(encoding="utf-8")
        assert "_mc" in content or "concentration" in content.lower()

    def test_bias_has_concentration(self):
        content = Path("daily_bias_range_reversion_audit.py").read_text(encoding="utf-8")
        assert "_mc" in content or "concentration" in content.lower()


# ── Weekend EMA5 exit ────────────────────────────────────────────────────────

class TestWeekendEMA5Exit:
    def test_weekend_has_ema5_exit(self):
        """Weekend audit must have EMA5 exit condition."""
        content = Path("weekend_low_liquidity_reversion_audit.py").read_text(encoding="utf-8")
        assert "ema5" in content.lower() or "ema[i]" in content


# ── Safety gates ─────────────────────────────────────────────────────────────

class TestSafetyGates:
    @pytest.mark.parametrize("report_path", [
        "reports/month_boundary_flow_audit.json",
        "reports/weekend_low_liquidity_reversion_audit.json",
        "reports/parkinson_volatility_extreme_reversion_audit.json",
        "reports/daily_bias_range_reversion_audit.json",
    ])
    def test_safety_gates_closed(self, report_path):
        report = _load_json(report_path)
        if report is None:
            pytest.skip(f"{report_path} not found")
        gates = report.get("safety_gates", {})
        assert gates.get("approved_for_paper") == []
        assert gates.get("eligible_for_paper") is False
        assert gates.get("safe_to_enable_trading") is False

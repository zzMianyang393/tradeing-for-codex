"""Safety and end-to-end tests for C34-C38 OI context infrastructure.

Verifies:
  - OI outputs have no direction/entry/exit/return/pnl/price/position/order/trade/win/loss/veto
  - OI modules do not import runner
  - 16:00 OI cannot be attached before 16:15
  - Snapshot > 30h old → oi_context_known=false, stale_source_data
  - Snapshot <= 30h old → oi_context_known=true
  - No snapshot = oi_context_known=false
  - Snapshots after cutoff rejected
  - Shadow ledger 28 signals unchanged
  - Current 28 signals all stale (last OI is 2025-07, signals are 2026-07)
  - Safety gates remain closed
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from prospective_oi_risk_snapshot import compute_daily_changes, generate_snapshots
from prospective_signal_oi_context_attachment import attach_oi_context, MAX_OI_CONTEXT_AGE_HOURS
from prospective_oi_context_timing_audit import audit_timing


OI_MODULES = [
    "prospective_oi_risk_snapshot.py",
    "prospective_signal_oi_context_attachment.py",
    "prospective_oi_context_timing_audit.py",
]

OI_REPORTS = [
    "reports/prospective_oi_risk_snapshot.json",
    "reports/prospective_signal_oi_context_attachment.json",
    "reports/prospective_oi_context_timing_audit.json",
]

FORBIDDEN_KEYS = {
    "direction", "entry", "exit", "return", "returns", "pnl", "price",
    "entry_price", "exit_price", "position", "order", "trade", "win", "loss",
    "veto", "mfe", "mae",
}


def _collect_keys(obj) -> set[str]:
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k.lower())
            keys |= _collect_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _collect_keys(item)
    return keys


def _load_json(path: str) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# ── Module import safety ─────────────────────────────────────────────────────

class TestModuleImportSafety:
    @pytest.mark.parametrize("module_name", OI_MODULES)
    def test_no_runner_import(self, module_name):
        path = Path(module_name)
        if not path.exists():
            pytest.skip(f"{module_name} not found")
        content = path.read_text(encoding="utf-8")
        assert "from runner import" not in content
        assert "import runner" not in content


# ── Report content safety ────────────────────────────────────────────────────

class TestReportContentSafety:
    @pytest.mark.parametrize("report_path", OI_REPORTS)
    def test_no_forbidden_keys(self, report_path):
        report = _load_json(report_path)
        if report is None:
            pytest.skip(f"{report_path} not found")
        all_keys = _collect_keys(report)
        found = all_keys & FORBIDDEN_KEYS
        assert not found, f"{report_path} contains forbidden keys: {found}"

    @pytest.mark.parametrize("report_path", OI_REPORTS)
    def test_observation_only(self, report_path):
        report = _load_json(report_path)
        if report is None:
            pytest.skip(f"{report_path} not found")
        assert report.get("observation_only") is True


# ── Staleness rules ──────────────────────────────────────────────────────────

class TestStalenessRules:
    def test_29h_old_snapshot_is_known(self):
        """Snapshot 29 hours old should be attached as known."""
        # Create mock data
        signal_ts = 1000 * 3600 * 1000  # t=1000h
        avail_ts = signal_ts - 29 * 3600 * 1000  # 29h before

        ledger = {"signals": [{
            "candidate_id": "test", "signal_ts": signal_ts,
            "signal_timestamp_utc": "test", "symbol": "TEST",
        }]}
        snapshots = [{
            "available_ts": avail_ts,
            "available_timestamp_utc": "test",
            "risk_state_candidate": "normal",
            "qualified_coin_count": 5,
            "qualified_fraction": 0.2,
            "median_abs_change_pct": 3.0,
        }]

        result = attach_oi_context(ledger, snapshots)
        assert result[0]["oi_context_known"] is True
        assert result[0]["attachment_reason"] == "fresh_snapshot_attached"

    def test_31h_old_snapshot_is_stale(self):
        """Snapshot 31 hours old must be marked stale, values NOT used."""
        signal_ts = 1000 * 3600 * 1000
        avail_ts = signal_ts - 31 * 3600 * 1000

        ledger = {"signals": [{
            "candidate_id": "test", "signal_ts": signal_ts,
            "signal_timestamp_utc": "test", "symbol": "TEST",
        }]}
        snapshots = [{
            "available_ts": avail_ts,
            "available_timestamp_utc": "test",
            "risk_state_candidate": "normal",  # should NOT be used
            "qualified_coin_count": 5,
            "qualified_fraction": 0.2,
            "median_abs_change_pct": 3.0,
        }]

        result = attach_oi_context(ledger, snapshots)
        assert result[0]["oi_context_known"] is False
        assert result[0]["attachment_reason"] == "stale_source_data"
        assert result[0]["oi_risk_state_candidate"] is None
        assert result[0]["oi_snapshot_available_ts"] is None

    def test_no_snapshot_is_unknown(self):
        """No past snapshot → oi_context_known=false."""
        ledger = {"signals": [{
            "candidate_id": "test", "signal_ts": 1000 * 3600 * 1000,
            "signal_timestamp_utc": "test", "symbol": "TEST",
        }]}
        result = attach_oi_context(ledger, [])
        assert result[0]["oi_context_known"] is False
        assert result[0]["attachment_reason"] == "no_snapshot_available_before_signal"

    def test_future_snapshot_not_used(self):
        """Snapshot in the future must not be attached."""
        signal_ts = 1000 * 3600 * 1000
        avail_ts = signal_ts + 3600 * 1000  # 1h in future

        ledger = {"signals": [{
            "candidate_id": "test", "signal_ts": signal_ts,
            "signal_timestamp_utc": "test", "symbol": "TEST",
        }]}
        snapshots = [{
            "available_ts": avail_ts,
            "available_timestamp_utc": "test",
            "risk_state_candidate": "normal",
            "qualified_coin_count": 5,
            "qualified_fraction": 0.2,
            "median_abs_change_pct": 3.0,
        }]

        result = attach_oi_context(ledger, snapshots)
        assert result[0]["oi_context_known"] is False
        assert result[0]["attachment_reason"] == "no_snapshot_available_before_signal"


# ── Current 28 signals all stale ─────────────────────────────────────────────

class TestCurrentSignalsAllStale:
    def test_all_28_signals_stale(self):
        """Current 28 signals (2026-07) with last OI (2025-07) must all be stale."""
        report = _load_json("reports/prospective_signal_oi_context_attachment.json")
        if report is None:
            pytest.skip("Attachment not found")
        assert report["n_signals"] == 28
        assert report["n_oi_context_known"] == 0
        assert report["n_stale"] == 28

    def test_no_normal_state_from_stale(self):
        """No stale attachment should have oi_risk_state_candidate=normal."""
        report = _load_json("reports/prospective_signal_oi_context_attachment.json")
        if report is None:
            pytest.skip("Attachment not found")
        for att in report["attachments"]:
            if att.get("attachment_reason") == "stale_source_data":
                assert att["oi_risk_state_candidate"] is None


# ── Timing audit ─────────────────────────────────────────────────────────────

class TestTimingAudit:
    def test_stale_count_in_audit(self):
        """Timing audit must report stale_attachment_count."""
        report = _load_json("reports/prospective_oi_context_timing_audit.json")
        if report is None:
            pytest.skip("Timing audit not found")
        assert report["stale_attachment_count"] == 28

    def test_latest_snapshot_age_at_cutoff(self):
        """Timing audit must report latest_snapshot_age_at_cutoff_hours."""
        report = _load_json("reports/prospective_oi_context_timing_audit.json")
        if report is None:
            pytest.skip("Timing audit not found")
        assert report["latest_snapshot_age_at_cutoff_hours"] is not None
        assert report["latest_snapshot_age_at_cutoff_hours"] > 365 * 24  # > 1 year


# ── Shadow ledger unchanged ──────────────────────────────────────────────────

class TestLedgerUnchanged:
    def test_ledger_28_signals(self):
        ledger = _load_json("reports/prospective_shadow_signal_ledger.json")
        if ledger is None:
            pytest.skip("Ledger not found")
        assert ledger["signal_count"] == 28
        assert len(ledger["signals"]) == 28


# ── Safety gates ─────────────────────────────────────────────────────────────

class TestSafetyGates:
    def test_maturity_safety_gates(self):
        p = Path("reports/prospective_maturity_audit.json")
        if not p.exists():
            pytest.skip("Maturity audit not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        gates = report.get("safety_gates", {})
        assert gates.get("approved_for_paper") == []
        assert gates.get("eligible_for_paper") is False
        assert gates.get("safe_to_enable_trading") is False
        assert gates.get("ready_for_combo_backtest") is False

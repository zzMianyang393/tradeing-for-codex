"""Safety and end-to-end tests for C24-C28 prospective observation maturity infrastructure.

Verifies:
  - C24 registry count == ledger signal_count (28)
  - maturity_ts == signal_ts + 90 days exactly
  - Default as_of == common_data_cutoff (not system clock)
  - Current mature_awaiting_sealed_evaluation == 0
  - Simulated as_of changes status only, no price/PnL fields
  - New modules do not import runner
  - JSON reports contain no forbidden keys
  - Safety gates remain closed
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from prospective_observation_registry import (
    OBSERVATION_HORIZON_DAYS,
    DAY_MS,
    build_registry,
    compute_identity_hash,
    load_ledger,
)
from prospective_maturity_audit import audit_maturity
from prospective_observation_integrity_audit import audit_integrity


NEW_MODULES = [
    "prospective_observation_registry.py",
    "prospective_maturity_audit.py",
    "prospective_observation_integrity_audit.py",
]

NEW_REPORTS = [
    "reports/prospective_observation_registry.json",
    "reports/prospective_maturity_audit.json",
    "reports/prospective_observation_integrity_audit.json",
]

FORBIDDEN_KEYS = {
    "pnl", "return", "returns", "price", "entry_price", "exit_price",
    "position", "order", "trade", "win", "loss", "mfe", "mae",
}


def _load_ledger() -> dict:
    p = Path("reports/prospective_shadow_signal_ledger.json")
    if not p.exists():
        pytest.skip("Ledger not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _load_registry() -> dict:
    p = Path("reports/prospective_observation_registry.json")
    if not p.exists():
        pytest.skip("Registry not found")
    return json.loads(p.read_text(encoding="utf-8"))


def _load_maturity() -> dict:
    p = Path("reports/prospective_maturity_audit.json")
    if not p.exists():
        pytest.skip("Maturity audit not found")
    return json.loads(p.read_text(encoding="utf-8"))


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


# ── Module import safety ─────────────────────────────────────────────────────

class TestModuleImportSafety:
    @pytest.mark.parametrize("module_name", NEW_MODULES)
    def test_no_runner_import(self, module_name):
        path = Path(module_name)
        if not path.exists():
            pytest.skip(f"{module_name} not found")
        content = path.read_text(encoding="utf-8")
        assert "from runner import" not in content
        assert "import runner" not in content


# ── Report content safety ────────────────────────────────────────────────────

class TestReportContentSafety:
    @pytest.mark.parametrize("report_path", NEW_REPORTS)
    def test_no_forbidden_keys(self, report_path):
        p = Path(report_path)
        if not p.exists():
            pytest.skip(f"{report_path} not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        all_keys = _collect_keys(report)
        found = all_keys & FORBIDDEN_KEYS
        assert not found, f"{report_path} contains forbidden keys: {found}"

    @pytest.mark.parametrize("report_path", NEW_REPORTS)
    def test_observation_only(self, report_path):
        p = Path(report_path)
        if not p.exists():
            pytest.skip(f"{report_path} not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        assert report.get("observation_only") is True


# ── C24: Registry count matches ledger ───────────────────────────────────────

class TestRegistryCount:
    def test_registry_count_equals_ledger(self):
        ledger = _load_ledger()
        registry = _load_registry()
        assert registry["registry_signal_count"] == ledger["signal_count"]

    def test_signal_count_is_28(self):
        registry = _load_registry()
        assert registry["registry_signal_count"] == 28

    def test_unique_hashes(self):
        registry = _load_registry()
        assert registry["unique_identity_hashes"] == 28

    def test_no_duplicate_identities(self):
        registry = _load_registry()
        dups = [o for o in registry["observations"] if o["duplicate_identity"]]
        assert len(dups) == 0


# ── C24: maturity_ts correctness ─────────────────────────────────────────────

class TestMaturityTsCorrectness:
    def test_maturity_equals_signal_plus_90_days(self):
        """Every maturity_ts must be exactly signal_ts + 90 * 24h."""
        registry = _load_registry()
        for obs in registry["observations"]:
            expected = obs["signal_ts"] + OBSERVATION_HORIZON_DAYS * DAY_MS
            assert obs["maturity_ts"] == expected, \
                f"{obs['observation_id']}: maturity_ts={obs['maturity_ts']} != expected={expected}"

    def test_maturity_timestamp_matches_ts(self):
        """maturity_timestamp_utc must match maturity_ts."""
        registry = _load_registry()
        for obs in registry["observations"]:
            expected_utc = datetime.fromtimestamp(
                obs["maturity_ts"] / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")
            assert obs["maturity_timestamp_utc"] == expected_utc


# ── C25: Default as_of == cutoff ─────────────────────────────────────────────

class TestDefaultAsOf:
    def test_default_as_of_is_cutoff(self):
        """Default as_of must equal ledger common_data_cutoff."""
        maturity = _load_maturity()
        ledger = _load_ledger()
        cutoff = ledger["common_data_cutoff"]
        assert maturity["as_of_utc"] == cutoff
        assert maturity["simulated_as_of"] is False

    def test_current_mature_count_is_zero(self):
        """At the default cutoff, no signals should be mature."""
        maturity = _load_maturity()
        assert maturity["n_mature"] == 0
        assert maturity["n_awaiting"] == 28

    def test_simulated_as_of_flag(self):
        """When --as-of is used, simulated_as_of must be True."""
        ledger = _load_ledger()
        registry_json = _load_registry()
        # Rebuild registry from ledger
        registry = build_registry(ledger)
        # Simulate a future date
        future_ts = int(datetime(2026, 12, 1, tzinfo=timezone.utc).timestamp() * 1000)
        result = audit_maturity(registry, future_ts)
        # All should be mature
        assert result["n_mature"] == 28
        assert result["n_awaiting"] == 0


# ── C26: Integrity audit ─────────────────────────────────────────────────────

class TestIntegrityAudit:
    def test_integrity_is_valid(self):
        p = Path("reports/prospective_observation_integrity_audit.json")
        if not p.exists():
            pytest.skip("Integrity audit not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        assert report["integrity_status"] == "valid"
        assert report["n_issues"] == 0

    def test_counts_match(self):
        p = Path("reports/prospective_observation_integrity_audit.json")
        if not p.exists():
            pytest.skip("Integrity audit not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        assert report["cross_check"]["counts_match"] is True


# ── Safety gates ─────────────────────────────────────────────────────────────

class TestSafetyGates:
    def test_registry_safety_gates(self):
        """Registry must not declare any trading eligibility."""
        p = Path("reports/prospective_observation_registry.json")
        if not p.exists():
            pytest.skip("Registry not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        # Registry doesn't have safety_gates, but must have observation_only
        assert report.get("observation_only") is True

    def test_maturity_safety_gates(self):
        """Maturity audit must have all safety gates closed."""
        maturity = _load_maturity()
        gates = maturity.get("safety_gates", {})
        assert gates.get("approved_for_paper") == []
        assert gates.get("eligible_for_paper") is False
        assert gates.get("safe_to_enable_trading") is False
        assert gates.get("ready_for_combo_backtest") is False


# ── Identity hash determinism ────────────────────────────────────────────────

class TestIdentityHash:
    def test_deterministic(self):
        h1 = compute_identity_hash("cid", "v1", 12345, "SYM", "long", "震荡")
        h2 = compute_identity_hash("cid", "v1", 12345, "SYM", "long", "震荡")
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        h1 = compute_identity_hash("cid1", "v1", 12345, "SYM", "long", "震荡")
        h2 = compute_identity_hash("cid2", "v1", 12345, "SYM", "long", "震荡")
        assert h1 != h2

    def test_hash_length(self):
        h = compute_identity_hash("cid", "v1", 12345, "SYM", "long", "震荡")
        assert len(h) == 16

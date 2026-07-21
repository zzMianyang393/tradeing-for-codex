"""Safety gate and end-to-end tests for C18-C23 infrastructure.

Verifies:
  - New modules do not import runner
  - Reports have no PnL/return/exit/position/order fields
  - All shadow outputs are observation_only=true
  - approved_for_paper is empty
  - safe_to_enable_trading is false
  - blocked/invalid/risk_blocked cannot enter directional factor matrix
  - Directional factors cannot be marked compliant when label is unavailable
  - C21 n_signals_total == ledger signal_count (28)
  - Every ledger factor maps to matrix
  - Unknown regime labels marked missing/invalid
  - Coverage rate never exceeds 1.0
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from factor_regime_compatibility_matrix import (
    CANDIDATE_TO_FACTOR,
    REGIME_VOCABULARY,
    REGIME_VOCABULARY_VERSION,
    STANDARD_REGIMES,
    get_entry_by_candidate_id,
    normalize_regime,
    is_regime_known,
    compute_dedirected_overlaps,
    get_matrix,
)


NEW_MODULES = [
    "regime_label_coverage_audit.py",
    "regime_label_transition_audit.py",
    "factor_regime_compatibility_matrix.py",
    "prospective_signal_regime_audit.py",
    "combo_regime_coverage_gap_audit.py",
]

NEW_REPORTS = [
    "reports/regime_label_coverage_audit.json",
    "reports/regime_label_transition_audit.json",
    "reports/factor_regime_compatibility_matrix.json",
    "reports/prospective_signal_regime_audit.json",
    "reports/combo_regime_coverage_gap_audit.json",
]

FORBIDDEN_FIELDS = {"pnl", "return", "returns", "exit", "position", "order", "pnl_pct_equity"}


# ── Module import safety ─────────────────────────────────────────────────────

class TestModuleImportSafety:
    @pytest.mark.parametrize("module_name", NEW_MODULES)
    def test_no_runner_import(self, module_name):
        path = Path(module_name)
        if not path.exists():
            pytest.skip(f"{module_name} not found")
        content = path.read_text(encoding="utf-8")
        assert "from runner import" not in content, f"{module_name} imports runner"
        assert "import runner" not in content, f"{module_name} imports runner"


# ── Report content safety ────────────────────────────────────────────────────

class TestReportContentSafety:
    def _load_report(self, path_str: str) -> dict | None:
        p = Path(path_str)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _collect_keys(self, obj, prefix="") -> set[str]:
        keys = set()
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(k.lower())
                keys |= self._collect_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                keys |= self._collect_keys(item)
        return keys

    @pytest.mark.parametrize("report_path", NEW_REPORTS)
    def test_no_forbidden_fields(self, report_path):
        report = self._load_report(report_path)
        if report is None:
            pytest.skip(f"{report_path} not found")
        all_keys = self._collect_keys(report)
        forbidden_found = all_keys & FORBIDDEN_FIELDS
        assert not forbidden_found, f"{report_path} contains forbidden fields: {forbidden_found}"

    @pytest.mark.parametrize("report_path", NEW_REPORTS)
    def test_observation_only_flag(self, report_path):
        report = self._load_report(report_path)
        if report is None:
            pytest.skip(f"{report_path} not found")
        assert report.get("observation_only") is True, f"{report_path} missing observation_only=true"


# ── Registry safety gates ────────────────────────────────────────────────────

class TestRegistrySafetyGates:
    def _load_registry(self) -> dict:
        p = Path("reports/research_approval_registry.json")
        if not p.exists():
            pytest.skip("Registry not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_approved_for_paper_empty(self):
        reg = self._load_registry()
        assert reg.get("approved_for_paper", []) == []

    def test_safe_to_enable_trading_false(self):
        reg = self._load_registry()
        assert reg.get("safe_to_enable_trading", True) is False


# ── Factor matrix safety ─────────────────────────────────────────────────────

class TestFactorMatrixSafety:
    def _load_matrix_report(self) -> dict:
        p = Path("reports/factor_regime_compatibility_matrix.json")
        if not p.exists():
            pytest.skip("Matrix not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def _load_registry(self) -> dict:
        p = Path("reports/research_approval_registry.json")
        if not p.exists():
            return {"records": []}
        return json.loads(p.read_text(encoding="utf-8"))

    def test_blocked_not_in_directional(self):
        matrix_report = self._load_matrix_report()
        registry = self._load_registry()
        blocked_ids = set()
        for rec in registry.get("records", []):
            if rec.get("status") in ("blocked", "invalid", "risk_blocked"):
                blocked_ids.add(rec["research_id"])
        for entry in matrix_report.get("matrix", []):
            if entry["factor_id"] in blocked_ids:
                assert entry["allowed_role"] != "directional_weak_signal", \
                    f"{entry['factor_id']} is blocked but entered directional matrix"

    def test_all_factors_have_allowed_role(self):
        matrix_report = self._load_matrix_report()
        for entry in matrix_report.get("matrix", []):
            assert entry["allowed_role"] in (
                "directional_weak_signal", "context_only", "risk_filter_only"
            )


# ── Regime vocabulary tests ──────────────────────────────────────────────────

class TestRegimeVocabulary:
    def test_version_exists(self):
        assert REGIME_VOCABULARY_VERSION  # non-empty string

    def test_standard_regimes_mapped(self):
        for regime in STANDARD_REGIMES:
            assert regime in REGIME_VOCABULARY
            assert REGIME_VOCABULARY[regime] == regime

    def test_unknown_label_returns_none(self):
        assert normalize_regime("completely_unknown_label_xyz") is None

    def test_unknown_label_not_known(self):
        assert not is_regime_known("completely_unknown_label_xyz")

    def test_known_labels_mapped(self):
        known_non_standard = ["low_volatility_drift_v2", "downtrend", "mean_reverting_range_v2",
                              "cross_sectional_weakness_continuation"]
        for label in known_non_standard:
            assert is_regime_known(label), f"'{label}' should be known"
            assert normalize_regime(label) is not None, f"'{label}' should map to non-None"

    def test_all_mappings_target_standard(self):
        for raw, mapped in REGIME_VOCABULARY.items():
            if mapped is not None:
                assert mapped in STANDARD_REGIMES, f"'{raw}' maps to non-standard '{mapped}'"


# ── Candidate-factor mapping ─────────────────────────────────────────────────

class TestCandidateFactorMapping:
    def test_all_matrix_entries_have_candidate_id(self):
        matrix = get_matrix()
        for entry in matrix:
            assert entry.candidate_id, f"{entry.factor_id} missing candidate_id"

    def test_candidate_to_factor_roundtrip(self):
        for cid, fid in CANDIDATE_TO_FACTOR.items():
            entry = get_entry_by_candidate_id(cid)
            assert entry is not None, f"candidate_id '{cid}' not found"
            assert entry.factor_id == fid


# ── Overlap deduplication ────────────────────────────────────────────────────

class TestOverlapDeduplication:
    def test_no_symmetric_pairs(self):
        matrix = get_matrix()
        overlaps = compute_dedirected_overlaps(matrix)
        pairs = {(o["factor_a"], o["factor_b"]) for o in overlaps}
        for a, b in pairs:
            assert (b, a) not in pairs, f"Symmetric pair found: {a}-{b} and {b}-{a}"

    def test_overlap_types_valid(self):
        matrix = get_matrix()
        overlaps = compute_dedirected_overlaps(matrix)
        valid_types = {"same_direction", "opposite_direction", "semantic_only"}
        for o in overlaps:
            assert o["overlap_type"] in valid_types, f"Invalid overlap type: {o['overlap_type']}"


# ── Coverage rate bounds ─────────────────────────────────────────────────────

class TestCoverageRateBounds:
    def test_coverage_rate_never_exceeds_one(self):
        p = Path("reports/regime_label_coverage_audit.json")
        if not p.exists():
            pytest.skip("Coverage audit not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        for sym, info in report.get("per_symbol", {}).items():
            for period in ["formation", "oos"]:
                rate = info.get(period, {}).get("coverage_rate", 0)
                assert 0 <= rate <= 1.0, f"{sym}/{period} coverage_rate={rate} out of [0,1]"

    def test_coverage_rate_non_negative(self):
        p = Path("reports/regime_label_coverage_audit.json")
        if not p.exists():
            pytest.skip("Coverage audit not found")
        report = json.loads(p.read_text(encoding="utf-8"))
        for sym, info in report.get("per_symbol", {}).items():
            for period in ["formation", "oos"]:
                rate = info.get(period, {}).get("coverage_rate", 0)
                assert rate >= 0, f"{sym}/{period} coverage_rate={rate} < 0"


# ── End-to-end: C21 ledger integration ───────────────────────────────────────

class TestEndToEndLedgerIntegration:
    def _load_ledger(self) -> dict:
        p = Path("reports/prospective_shadow_signal_ledger.json")
        if not p.exists():
            pytest.skip("Shadow signal ledger not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def _load_audit(self) -> dict:
        p = Path("reports/prospective_signal_regime_audit.json")
        if not p.exists():
            pytest.skip("Signal regime audit not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def test_signal_count_matches_ledger(self):
        """C21 n_signals_total must equal ledger signal_count (28)."""
        ledger = self._load_ledger()
        audit = self._load_audit()
        assert audit["n_signals_total"] == ledger["signal_count"], \
            f"Audit signals {audit['n_signals_total']} != ledger {ledger['signal_count']}"

    def test_signal_count_is_28(self):
        """Current ledger has exactly 28 signals."""
        ledger = self._load_ledger()
        assert ledger["signal_count"] == 28

    def test_every_ledger_factor_maps_to_matrix(self):
        """Every candidate_id in ledger must map to a matrix entry."""
        ledger = self._load_ledger()
        for sig in ledger["signals"]:
            cid = sig["candidate_id"]
            entry = get_entry_by_candidate_id(cid)
            assert entry is not None, f"candidate_id '{cid}' has no matrix entry"

    def test_unknown_regime_not_auto_passed(self):
        """Unknown regime labels must be marked non-compliant, not auto-passed."""
        audit = self._load_audit()
        for detail in audit.get("signal_details", []):
            if not detail["regime_known"]:
                assert not detail["compliant"], \
                    f"Unknown regime '{detail['raw_regime']}' was auto-passed"

    def test_all_regimes_in_ledger_are_known(self):
        """All regime labels in the ledger should have vocabulary mappings."""
        ledger = self._load_ledger()
        unknown = set()
        for sig in ledger["signals"]:
            regime = sig.get("regime", "")
            if not is_regime_known(regime):
                unknown.add(regime)
        assert not unknown, f"Unknown regimes in ledger: {unknown}"

    def test_audit_has_no_pnl_fields(self):
        """C21 audit must not contain PnL/return/exit fields."""
        audit = self._load_audit()
        forbidden = {"pnl", "return", "returns", "exit", "position", "order"}
        all_keys = set()
        self._collect_keys_recursive(audit, all_keys)
        found = all_keys & forbidden
        assert not found, f"C21 audit contains forbidden fields: {found}"

    def _collect_keys_recursive(self, obj, keys: set):
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(k.lower())
                self._collect_keys_recursive(v, keys)
        elif isinstance(obj, list):
            for item in obj:
                self._collect_keys_recursive(item, keys)


# ── Source consistency: matrix vs candidate registry ──────────────────────────

class TestSourceConsistency:
    """Matrix declared_regimes and direction must match candidate registry."""

    def _load_registry(self) -> dict:
        p = Path("reports/prospective_candidate_registry.json")
        if not p.exists():
            pytest.skip("Candidate registry not found")
        return json.loads(p.read_text(encoding="utf-8"))

    def _get_registry_entry(self, registry: dict, candidate_id: str) -> dict | None:
        for entry in registry.get("frozen_candidates", []) + registry.get("watchlist", []):
            if entry.get("candidate_id") == candidate_id:
                return entry
        return None

    def test_weekly_microtrend_regime_is_oscillation(self):
        """weekly_range_microtrend declared_regime must map to 震荡."""
        entry = get_entry_by_candidate_id("weekly_range_microtrend_continuation_v1_long")
        assert entry is not None
        assert "震荡" in entry.declared_regimes, \
            f"Expected 震荡 in declared_regimes, got {entry.declared_regimes}"

    def test_weekly_microtrend_not_in_trend_regimes(self):
        """weekly_range_microtrend must NOT declare 趋势上行 or 趋势下行."""
        entry = get_entry_by_candidate_id("weekly_range_microtrend_continuation_v1_long")
        assert entry is not None
        assert "趋势上行" not in entry.declared_regimes
        assert "趋势下行" not in entry.declared_regimes

    def test_weekly_cross_sectional_regime_is_downtrend(self):
        """weekly_cross_sectional declared_regime must map to 趋势下行."""
        entry = get_entry_by_candidate_id("weekly_cross_sectional_momentum_v1_short")
        assert entry is not None
        assert "趋势下行" in entry.declared_regimes, \
            f"Expected 趋势下行 in declared_regimes, got {entry.declared_regimes}"

    def test_weekly_cross_sectional_not_in_uptrend(self):
        """weekly_cross_sectional must NOT declare 趋势上行."""
        entry = get_entry_by_candidate_id("weekly_cross_sectional_momentum_v1_short")
        assert entry is not None
        assert "趋势上行" not in entry.declared_regimes

    def test_weekly_pair_is_opposite_direction(self):
        """weekly_cross_sectional (short) vs weekly_microtrend (long) = opposite_direction."""
        entry = get_entry_by_candidate_id("weekly_cross_sectional_momentum_v1_short")
        assert entry is not None
        assert entry.overlap_type == "opposite_direction", \
            f"Expected opposite_direction, got {entry.overlap_type}"

    def test_weekly_microtrend_5_signals_now_compliant(self):
        """After fix, weekly_range_microtrend's 5 ledger signals should be compliant."""
        audit_path = Path("reports/prospective_signal_regime_audit.json")
        if not audit_path.exists():
            pytest.skip("Audit not found")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        pf = audit.get("per_factor", {}).get("weekly_range_microtrend_continuation_v1_long", {})
        n = pf.get("n_signals", 0)
        compliant = pf.get("n_compliant", 0)
        assert n == 5, f"Expected 5 signals, got {n}"
        assert compliant == 5, f"Expected 5 compliant, got {compliant}"

    def test_registry_and_matrix_regimes_consistent(self):
        """Every matrix factor's declared_regime must match registry after normalization."""
        registry = self._load_registry()
        matrix = get_matrix()
        for entry in matrix:
            reg_entry = self._get_registry_entry(registry, entry.candidate_id)
            if reg_entry is None:
                continue  # combo entries not in registry
            raw_regime = reg_entry.get("declared_regime", "")
            normalized = normalize_regime(raw_regime)
            if normalized is not None:
                assert normalized in entry.declared_regimes, \
                    (f"{entry.factor_id}: registry regime '{raw_regime}' -> '{normalized}' "
                     f"not in matrix declared_regimes {entry.declared_regimes}")

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from ten_u_event_trend_contract_v1 import (
    EventTrendConfig,
    EventTrendFormationGate,
    EventTrendResearchWindows,
    build_preregistration,
)


def test_default_contract_is_single_position_and_at_most_three_symbols():
    config = EventTrendConfig()
    assert len(config.symbols) == 3
    assert config.maximum_concurrent_positions == 1
    assert config.maximum_holding_hours == 48


def test_contract_is_immutable_and_fingerprint_is_stable():
    config = EventTrendConfig()
    assert config.fingerprint() == EventTrendConfig().fingerprint()
    with pytest.raises(FrozenInstanceError):
        config.pullback_wait_hours = 16
    with pytest.raises(TypeError):
        config.sensitivity_variants["new"] = {}


def test_fingerprint_changes_with_rule_change():
    assert EventTrendConfig().fingerprint() != EventTrendConfig(
        pullback_wait_hours=16
    ).fingerprint()


def test_funding_history_and_leverage_guard_are_mandatory():
    with pytest.raises(ValueError):
        EventTrendConfig(funding_cost_status="not_applied")
    with pytest.raises(ValueError):
        EventTrendConfig(maximum_effective_leverage=4)


def test_windows_permanently_classify_inspected_case_as_contaminated():
    windows = EventTrendResearchWindows()
    assert windows.classify("2026-03-01T00:00:00Z") == "formation"
    assert windows.classify("2026-04-15T00:00:00Z") == "retrospective_validation"
    assert windows.classify("2026-06-29T07:00:00Z") == "contaminated_case_only"
    assert windows.classify("2026-07-16T00:00:00Z") == "prospective_oos"


def test_preregistration_locks_later_phases_and_parameter_selection():
    preregistration = build_preregistration()
    assert preregistration["phase_unlock"] == {
        "formation": True,
        "retrospective_validation": False,
        "prospective_oos": False,
    }
    assert preregistration["contamination_policy"]["may_validate"] is False
    assert preregistration["anti_overfit"]["parameter_search_allowed"] is False
    assert preregistration["anti_overfit"]["sensitivity_variant_selection_allowed"] is False


def test_gate_fingerprint_is_stable():
    assert EventTrendFormationGate().fingerprint() == EventTrendFormationGate().fingerprint()


def test_saved_preregistration_exactly_matches_frozen_builder():
    path = Path(__file__).parents[1] / "reports" / "ten_u_event_trend_preregistration_v1.json"
    assert json.loads(path.read_text(encoding="utf-8")) == build_preregistration()

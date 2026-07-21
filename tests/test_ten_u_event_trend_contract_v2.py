from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from ten_u_event_trend_contract_v2 import (
    PersistentEventTrendConfig,
    PersistentEventTrendWindows,
    build_preregistration_v2,
)


def test_v2_replaces_single_bar_direction_with_twelve_hour_persistence():
    config = PersistentEventTrendConfig()
    assert config.persistence_completed_4h_bars == 3
    assert config.post_confirmation_pullback_wait_hours == 8


def test_v2_is_immutable_and_has_no_sensitivity_grid():
    config = PersistentEventTrendConfig()
    with pytest.raises(FrozenInstanceError):
        config.persistence_completed_4h_bars = 2
    assert "sensitivity" not in config.to_dict()


def test_v2_fingerprint_is_stable():
    assert PersistentEventTrendConfig().fingerprint() == PersistentEventTrendConfig().fingerprint()


def test_v2_sealed_screen_is_only_unlocked_historical_interval():
    prereg = build_preregistration_v2()
    assert prereg["phase_access"] == {
        "v1_development_interval": False,
        "sealed_screen": True,
        "case_contaminated": False,
        "prospective_outcomes": False,
    }
    windows = PersistentEventTrendWindows()
    assert windows.prospective_minimum_days == 90
    assert windows.prospective_minimum_trades == 6


def test_saved_v2_preregistration_matches_code_exactly():
    path = Path(__file__).parents[1] / "reports" / "ten_u_event_trend_preregistration_v2.json"
    assert json.loads(path.read_text(encoding="utf-8")) == build_preregistration_v2()

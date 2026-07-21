from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from prospective_legacy_weak_factor_preflight import (
    LEGACY_FACTOR_ROLE,
    LEGACY_FACTOR_VALIDITY_DAYS,
    exact_overlap_summary,
    factor_decisions,
)


def _signal(candidate: str, ts: int, symbol: str, direction: str) -> dict:
    return {"candidate_id": candidate, "signal_ts": ts, "symbol": symbol, "direction": direction}


def test_five_rejected_factors_are_reused_only_as_weak_features() -> None:
    assert len(LEGACY_FACTOR_VALIDITY_DAYS) == 5
    assert "rejected_standalone" in LEGACY_FACTOR_ROLE
    assert LEGACY_FACTOR_VALIDITY_DAYS["daily_trend_pullback"] == 15


def test_exact_overlap_distinguishes_same_and_opposite_direction() -> None:
    legacy = [_signal("daily_bb_mean_revert", 1, "BTC", "long")]
    existing = [
        _signal("a", 1, "BTC", "long"),
        _signal("b", 1, "BTC", "short"),
    ]
    result = exact_overlap_summary(legacy, existing)
    assert result["same_direction_exact_overlap_count"] == 1
    assert result["opposite_direction_exact_overlap_count"] == 1


def test_factor_decisions_never_authorize_standalone_or_combo_backtest() -> None:
    factor = "daily_bb_mean_revert"
    raw = [_signal(factor, 1, "BTC", "long")]
    exact = {
        "same_direction_exact_overlaps": [],
        "opposite_direction_exact_overlaps": [],
    }
    decisions = factor_decisions(raw, raw, raw, exact)
    selected = next(item for item in decisions if item["factor_id"] == factor)
    assert selected["preflight_status"] == "eligible_for_shadow_observation_only"
    assert selected["allowed_as_standalone"] is False
    assert selected["authorized_for_combo_backtest"] is False


def test_incompatible_regime_signals_cannot_enter_shadow_observation() -> None:
    factor = "daily_rsi_mean_revert"
    raw = [_signal(factor, 1, "BTC", "long")]
    exact = {"same_direction_exact_overlaps": [], "opposite_direction_exact_overlaps": []}
    decisions = factor_decisions(raw, [], [], exact)
    selected = next(item for item in decisions if item["factor_id"] == factor)
    assert selected["declared_regime_compatible_signal_count"] == 0
    assert selected["preflight_status"] == "signals_only_in_declared_incompatible_regimes"


def test_module_has_no_runner_or_outcome_calls() -> None:
    tree = ast.parse(Path("prospective_legacy_weak_factor_preflight.py").read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "runner" not in imports
    assert "trade_event" not in calls
    assert "simulate_trade" not in calls
    assert "simulate_portfolio" not in calls


def test_generated_report_keeps_reuse_observational() -> None:
    path = Path("reports/prospective_legacy_weak_factor_preflight.json")
    if not path.exists():
        pytest.skip("legacy weak-factor report not generated")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["forward_prices_evaluated"] is False
    assert report["outcomes_evaluated"] is False
    assert report["registry_changed"] is False
    assert report["safety_gates"]["approved_for_paper"] == []
    for item in report["factor_preflight_decisions"]:
        assert item["allowed_as_standalone"] is False
        assert item["authorized_for_combo_backtest"] is False
    for signal in report["signals"]:
        assert signal["declared_regime_compatible"] is True

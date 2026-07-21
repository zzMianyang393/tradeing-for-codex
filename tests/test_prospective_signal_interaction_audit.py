from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from prospective_signal_interaction_audit import (
    build_emergent_pair_observations,
    build_report,
    component_pair,
    signal_pairs_within_window,
)


def _signal(candidate: str, ts: int, symbol: str, direction: str) -> dict:
    return {
        "candidate_id": candidate,
        "signal_ts": ts,
        "symbol": symbol,
        "direction": direction,
        "regime": "test_regime",
    }


def test_component_pair_parses_combo_and_pair_ids() -> None:
    assert component_pair("combo::a__b") == ("a", "b")
    assert component_pair("pair_watchlist::a__b") == ("a", "b")
    assert component_pair("a") is None


def test_signal_pairs_classify_consensus_and_conflict() -> None:
    signals = [
        _signal("a", 0, "BTC", "long"),
        _signal("b", 60 * 60 * 1000, "BTC", "long"),
        _signal("c", 2 * 60 * 60 * 1000, "BTC", "short"),
        _signal("d", 0, "ETH", "short"),
    ]
    result = signal_pairs_within_window(signals)
    relationships = [item["relationship"] for item in result]
    assert relationships.count("same_direction_consensus") == 1
    assert relationships.count("opposite_direction_conflict") == 2


def test_build_report_never_opens_combo_gate() -> None:
    ledger = {
        "prospective_start": "2026-07-11",
        "common_data_cutoff": "2026-07-13 08:15:00",
        "evaluated_rule_ids": ["a", "b"],
        "signals": [_signal("a", 1_784_000_000_000, "BTC", "long")],
    }
    registry = {"watchlist": [{"candidate_id": "pair_watchlist::a__b"}]}
    report = build_report(ledger, registry)
    assert report["prices_evaluated"] is False
    assert report["outcomes_evaluated"] is False
    assert report["forward_returns_evaluated"] is False
    assert report["registered_pair_observations"][0]["authorized_for_backtest"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False


def test_emergent_pairs_exclude_registered_pairs_and_stay_observational() -> None:
    registry = {"watchlist": [{"candidate_id": "pair_watchlist::a__b"}]}
    overlaps = [
        {"pair_key": "a__b", "relationship": "same_direction_consensus", "symbol": "BTC"},
        {"pair_key": "a__c", "relationship": "opposite_direction_conflict", "symbol": "ETH"},
    ]
    result = build_emergent_pair_observations(registry, overlaps)
    assert [item["pair_key"] for item in result] == ["a__c"]
    assert result[0]["observation_class"] == "conflict_candidate"
    assert result[0]["registry_changed"] is False
    assert result[0]["authorized_for_backtest"] is False


def test_module_does_not_import_runner_or_trade_functions() -> None:
    tree = ast.parse(Path("prospective_signal_interaction_audit.py").read_text(encoding="utf-8"))
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
    assert "simulate_portfolio" not in calls


def test_generated_report_is_signal_metadata_only() -> None:
    path = Path("reports/prospective_signal_interaction_audit.json")
    if not path.exists():
        pytest.skip("interaction report not generated")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["prices_evaluated"] is False
    assert report["outcomes_evaluated"] is False
    assert report["exits_evaluated"] is False
    assert report["positions_opened"] is False
    for item in report["registered_pair_observations"]:
        assert item["authorized_for_backtest"] is False
    for item in report["emergent_pair_observations"]:
        assert item["registry_changed"] is False
        assert item["authorized_for_backtest"] is False

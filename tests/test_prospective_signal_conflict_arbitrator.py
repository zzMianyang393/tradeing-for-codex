from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from prospective_signal_conflict_arbitrator import (
    DAY_MS,
    SIGNAL_VALIDITY_DAYS,
    UPTREND_TREND_SLEEVE,
    arbitration_state,
    build_arbitration_snapshots,
    build_report,
    deduplicate_signals,
)


def _signal(candidate: str, ts: int, symbol: str = "BTC", direction: str = "long") -> dict:
    return {"candidate_id": candidate, "signal_ts": ts, "symbol": symbol, "direction": direction}


def test_frozen_validity_days_cover_all_seven_rules() -> None:
    assert len(SIGNAL_VALIDITY_DAYS) == 7
    assert SIGNAL_VALIDITY_DAYS["ema_continuation_short_downtrend_v1"] == 5
    assert SIGNAL_VALIDITY_DAYS["persistent_uptrend_ema20_reclaim_v1"] == 10
    assert SIGNAL_VALIDITY_DAYS["donchian_atr_trend_baseline"] == 10


def test_deduplication_uses_fixed_validity_without_outcomes() -> None:
    signals = [_signal("a", 0), _signal("a", DAY_MS), _signal("a", 3 * DAY_MS)]
    retained, suppressed = deduplicate_signals(signals, {"a": 3})
    assert [item["signal_ts"] for item in retained] == [0, 3 * DAY_MS]
    assert [item["signal_ts"] for item in suppressed] == [DAY_MS]


def test_arbitration_state_caps_consensus_and_locks_conflict() -> None:
    consensus = [
        {"candidate_id": "a", "direction": "short"},
        {"candidate_id": "b", "direction": "short"},
    ]
    conflict = consensus + [{"candidate_id": "c", "direction": "long"}]
    assert arbitration_state(consensus) == ("same_direction_consensus_no_leverage_addition", "short")
    assert arbitration_state(conflict) == ("opposite_direction_conflict_lockout", None)


def test_simultaneous_arrivals_are_order_independent() -> None:
    signals = [_signal("a", 0, direction="long"), _signal("b", 0, direction="short")]
    snapshots = build_arbitration_snapshots(signals, {"a": 1, "b": 1})
    assert len(snapshots) == 1
    assert snapshots[0]["arbitration_state"] == "opposite_direction_conflict_lockout"
    assert snapshots[0]["notional_vote_cap"] == 0


def test_uptrend_components_share_first_signal_window_without_extension() -> None:
    donchian = "donchian_atr_trend_baseline"
    reclaim = "persistent_uptrend_ema20_reclaim_v1"
    assert UPTREND_TREND_SLEEVE == frozenset({donchian, reclaim})
    signals = [
        _signal(donchian, 0, symbol="ETH", direction="long"),
        _signal(reclaim, 9 * DAY_MS, symbol="ETH", direction="long"),
    ]
    snapshots = build_arbitration_snapshots(signals)
    assert snapshots[-1]["arbitration_state"] == "same_direction_consensus_no_leverage_addition"
    assert snapshots[-1]["notional_vote_cap"] == 1
    assert snapshots[-1]["uptrend_trend_sleeve_components"] == [donchian, reclaim]
    assert snapshots[-1]["uptrend_trend_sleeve_start_ts"] == 0


def test_uptrend_sleeve_expires_from_first_signal_not_later_component() -> None:
    donchian = "donchian_atr_trend_baseline"
    reclaim = "persistent_uptrend_ema20_reclaim_v1"
    signals = [
        _signal(donchian, 0, symbol="ETH", direction="long"),
        _signal(reclaim, 9 * DAY_MS, symbol="ETH", direction="long"),
        _signal("ema_continuation_short_downtrend_v1", 10 * DAY_MS, symbol="ETH", direction="short"),
    ]
    snapshots = build_arbitration_snapshots(signals)
    assert snapshots[-1]["uptrend_trend_sleeve_active"] is False
    assert snapshots[-1]["active_components"] == ["ema_continuation_short_downtrend_v1"]


def test_report_keeps_every_execution_gate_closed() -> None:
    ledger = {
        "prospective_start": "2026-07-11",
        "common_data_cutoff": "2026-07-13 08:15:00",
        "signals": [_signal("ema_continuation_short_downtrend_v1", 0, direction="short")],
    }
    report = build_report(ledger)
    assert report["prices_evaluated"] is False
    assert report["outcomes_evaluated"] is False
    assert report["exits_evaluated"] is False
    assert report["positions_opened"] is False
    assert report["orders_created"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False


def test_module_has_no_runner_or_execution_calls() -> None:
    tree = ast.parse(Path("prospective_signal_conflict_arbitrator.py").read_text(encoding="utf-8"))
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


def test_generated_report_is_observation_only() -> None:
    path = Path("reports/prospective_signal_conflict_arbitration.json")
    if not path.exists():
        pytest.skip("arbitration report not generated")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["prices_evaluated"] is False
    assert report["outcomes_evaluated"] is False
    assert report["orders_created"] is False
    for snapshot in report["snapshots"]:
        assert snapshot["observation_only"] is True

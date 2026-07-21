from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from prospective_second_batch_factor_preflight import (
    SECOND_BATCH_VALIDITY_DAYS,
    exact_overlap_count,
    factor_decisions,
    percentile,
)


def _signal(candidate: str, ts: int, symbol: str = "BTC", direction: str = "long") -> dict:
    return {"candidate_id": candidate, "signal_ts": ts, "symbol": symbol, "direction": direction}


def test_second_batch_has_four_distinct_low_turnover_mechanisms() -> None:
    assert len(SECOND_BATCH_VALIDITY_DAYS) == 4
    assert SECOND_BATCH_VALIDITY_DAYS["donchian55_trend_breakout_v1"] == 20
    assert SECOND_BATCH_VALIDITY_DAYS["weekly_cross_sectional_momentum_90d_long_v1"] == 7


def test_percentile_is_deterministic_and_uses_lower_order_statistic() -> None:
    assert percentile(list(range(1, 101)), 0.05) == 5


def test_exact_overlap_uses_timestamp_symbol_and_direction() -> None:
    candidate = [_signal("new", 1, "BTC", "long")]
    existing = [_signal("old", 1, "BTC", "long"), _signal("old", 1, "BTC", "short")]
    assert exact_overlap_count(candidate, existing) == 1


def test_incompatible_signals_cannot_pass_preflight() -> None:
    factor = "daily_rsi_5pct_range_reversal_v1"
    raw = [_signal(factor, 1)]
    decisions = factor_decisions(raw, [], [], [])
    selected = next(item for item in decisions if item["factor_id"] == factor)
    assert selected["preflight_status"] == "signals_only_in_declared_incompatible_regimes"
    assert selected["allowed_as_standalone"] is False


def test_module_has_no_runner_or_outcome_calls() -> None:
    tree = ast.parse(Path("prospective_second_batch_factor_preflight.py").read_text(encoding="utf-8"))
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


def test_generated_report_keeps_gates_closed() -> None:
    path = Path("reports/prospective_second_batch_factor_preflight.json")
    if not path.exists():
        pytest.skip("second-batch report not generated")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["forward_prices_evaluated"] is False
    assert report["outcomes_evaluated"] is False
    assert report["registry_changed"] is False
    for item in report["factor_preflight_decisions"]:
        assert item["allowed_as_standalone"] is False
        assert item["authorized_for_combo_backtest"] is False

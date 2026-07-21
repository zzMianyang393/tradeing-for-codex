from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from market import Bar
from prospective_shadow_signal_ledger import (
    ALLOWED_SIGNAL_FIELDS,
    INDEPENDENT_RULES,
    signal_record,
    validate_signal_schema,
)


def test_signal_record_has_only_signal_time_fields() -> None:
    item = signal_record("candidate", 1_700_000_000_000, "BTC-USDT-SWAP", "long", "range", {"rank": 1})
    assert set(item) == ALLOWED_SIGNAL_FIELDS
    assert item["observation_only"] is True


def test_signal_schema_rejects_outcome_fields() -> None:
    item = signal_record("candidate", 1_700_000_000_000, "BTC-USDT-SWAP", "long", "range", {})
    item["exit_ts"] = 1_700_000_900_000
    with pytest.raises(ValueError, match="unexpected signal fields"):
        validate_signal_schema([item])


def test_module_has_no_execution_or_outcome_calls() -> None:
    path = Path("prospective_shadow_signal_ledger.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "runner" not in imported
    assert "trade_event" not in called
    assert "simulate_portfolio" not in called


def test_generated_report_keeps_all_gates_closed() -> None:
    path = Path("reports/prospective_shadow_signal_ledger.json")
    if not path.exists():
        pytest.skip("prospective ledger not generated")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["outcomes_evaluated"] is False
    assert report["exits_evaluated"] is False
    assert report["forward_returns_evaluated"] is False
    assert report["positions_opened"] is False
    assert set(report["signal_counts_by_candidate"]) == INDEPENDENT_RULES
    assert report["safety_gates"] == {
        "approved_for_paper": [],
        "eligible_for_paper": False,
        "safe_to_enable_trading": False,
        "ready_for_combo_backtest": False,
    }
    for signal in report["signals"]:
        assert set(signal) == ALLOWED_SIGNAL_FIELDS


def test_test_fixture_bar_import_remains_lightweight() -> None:
    bar = Bar(0, "1970-01-01 00:00:00", 1.0, 1.0, 1.0, 1.0, 0.0)
    assert bar.close == 1.0

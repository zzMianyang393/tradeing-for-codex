from __future__ import annotations

import ast
import json
from pathlib import Path

from prospective_signal_cooccurrence_audit import SAFETY_GATES, audit


def signal(candidate_id: str, timestamp: int, symbol: str, direction: str, regime: str) -> dict:
    return {
        "candidate_id": candidate_id,
        "signal_ts": timestamp,
        "signal_timestamp_utc": "2026-07-13 00:00:00",
        "symbol": symbol,
        "direction": direction,
        "regime": regime,
    }


def test_exact_same_symbol_timestamp_is_the_only_cooccurrence():
    ledger = {"signal_count": 3, "common_data_cutoff": "2026-07-13 08:15:00", "signals": [
        signal("ema_continuation_short_downtrend_v1", 1, "ATOM-USDT-SWAP", "short", "趋势下行"),
        signal("weekly_cross_sectional_momentum_v1_short", 1, "ATOM-USDT-SWAP", "short", "趋势下行"),
        signal("donchian_atr_trend_baseline", 1, "UNI-USDT-SWAP", "long", "趋势上行"),
    ]}
    report = audit(ledger)
    assert report["multi_factor_event_count"] == 1
    assert report["pair_observation_count"] == 1
    assert report["signals_in_multi_factor_events"] == 2
    assert report["pair_observations"][0]["direction_relation"] == "same"
    assert report["pair_observations"][0]["regime_relation"] == "same"


def test_unknown_candidates_are_not_silently_paired():
    ledger = {"signal_count": 2, "signals": [
        signal("ema_continuation_short_downtrend_v1", 1, "ATOM-USDT-SWAP", "short", "趋势下行"),
        signal("unknown_factor", 1, "ATOM-USDT-SWAP", "long", "趋势上行"),
    ]}
    report = audit(ledger)
    assert report["unknown_candidate_count"] == 1
    assert report["multi_factor_event_count"] == 0
    assert report["pair_observation_count"] == 0


def test_current_sealed_ledger_is_counted_without_outcome_fields():
    ledger = json.loads(Path("reports/prospective_shadow_signal_ledger.json").read_text(encoding="utf-8"))
    report = audit(ledger)
    assert report["signal_count_match"] is True
    assert report["observed_signal_count"] == 28
    encoded = json.dumps(report).lower()
    for forbidden in ("pnl", "return", "price", "position", "order", "entry", "exit"):
        assert forbidden not in encoded


def test_safety_gates_are_closed_and_module_never_imports_runner():
    assert SAFETY_GATES["approved_for_paper"] == []
    assert SAFETY_GATES["eligible_for_paper"] is False
    assert SAFETY_GATES["safe_to_enable_trading"] is False
    tree = ast.parse(Path("prospective_signal_cooccurrence_audit.py").read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert "runner" not in imported

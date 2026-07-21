import json
from datetime import datetime, timezone
from pathlib import Path

from ten_u_event_trend_evaluation_v2 import (
    assess_maturity,
    build_evaluator_registration,
    evaluate_replay,
    run_sealed_evaluation,
)
from ten_u_event_trend_prospective_v2 import (
    ProspectiveMaturityGateV2,
    append_signal_records,
    build_empty_ledger,
)


def _registration():
    gate = ProspectiveMaturityGateV2()
    return {
        "strategy_id": "v2",
        "config_fingerprint": "c" * 64,
        "prospective_start": "2026-07-16T00:00:00Z",
        "earliest_evaluation": "2026-10-14T00:00:00Z",
        "gate_fingerprint": gate.fingerprint(),
    }


def _signal(day: int, symbol: str):
    text = f"2026-07-{day:02d}T00:00:00Z"
    timestamp = int(
        datetime(2026, 7, day, tzinfo=timezone.utc).timestamp() * 1000
    )
    return {
        "symbol": symbol,
        "direction": "long",
        "ignition_ts": timestamp - 16 * 3_600_000,
        "confirmation_ts": timestamp - 4 * 3_600_000,
        "entry_ts": timestamp,
        "entry_time": text,
        "observed_at": text,
        "structural_invalidation": 1.0,
        "atr_1h": 0.1,
        "score": 2.5,
    }


def _mature_ledger():
    ledger = build_empty_ledger(_registration())
    symbols = ("RAVE-USDT-SWAP", "LAB-USDT-SWAP")
    for index, day in enumerate(range(17, 23)):
        record = _signal(day, symbols[index % 2])
        ledger = append_signal_records(ledger, [record], record["entry_time"])
    return append_signal_records(ledger, [], "2026-10-14T00:00:00Z")


def test_maturity_requires_calendar_coverage_and_six_completed_outcomes():
    ledger = _mature_ledger()
    mature = assess_maturity(_registration(), ledger, "2026-10-14T00:00:00Z")
    assert mature["outcomes_may_be_accessed"] is True
    assert mature["eligible_completed_signal_records"] == 6
    early = assess_maturity(_registration(), ledger, "2026-10-13T23:00:00Z")
    assert early["outcomes_may_be_accessed"] is False
    assert "calendar_days_below_minimum" in early["reasons"]


def test_gate_freezes_concentration_and_execution_sample_rules():
    replay = {
        "trades": 6,
        "wins": 2,
        "distinct_traded_symbols": 2,
        "profit_factor": 2.0,
        "ending_equity": 12.0,
        "max_drawdown_fraction": 0.50,
        "peak_profit_retention": 0.70,
        "stopped_then_recovered_fraction": 0.20,
        "median_winner_capture": 0.40,
        "top_winner_gross_profit_contribution": 0.60,
    }
    assert evaluate_replay(replay) == ("prospective_pass", [])
    status, reasons = evaluate_replay(
        {**replay, "top_winner_gross_profit_contribution": 0.90}
    )
    assert status == "prospective_fail"
    assert "top_winner_contribution_above_maximum" in reasons
    assert evaluate_replay({**replay, "trades": 5}) == (
        "prospective_insufficient_executed_trades",
        ["executed_trades_below_minimum"],
    )


def test_real_current_evaluator_cannot_touch_outcomes_before_maturity(tmp_path):
    root = Path(__file__).parents[1]
    calls = []

    def forbidden_loader(*args):
        calls.append(args)
        raise AssertionError("outcome loader must remain sealed")

    report = run_sealed_evaluation(
        root / "reports/ten_u_event_trend_prospective_registration_v2.json",
        root / "reports/ten_u_event_trend_evaluator_registration_v2.json",
        root / "reports/ten_u_event_trend_baseline_dataset_manifest_v2.json",
        root / "reports/ten_u_event_trend_prospective_ledger_v2.json",
        root / "reports/ten_u_event_trend_prospective_refresh_audit_v2.json",
        tmp_path / "data_must_not_be_read",
        tmp_path / "manifest_must_not_be_read.json",
        "2026-07-16T12:00:00Z",
        outcome_loader=forbidden_loader,
    )
    assert calls == []
    assert report["outcomes_accessed"] is False
    assert report["formal_status"] == "prospective_not_mature"


def test_saved_evaluator_registration_matches_frozen_sources():
    root = Path(__file__).parents[1]
    saved = json.loads(
        (root / "reports/ten_u_event_trend_evaluator_registration_v2.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved == build_evaluator_registration(root)

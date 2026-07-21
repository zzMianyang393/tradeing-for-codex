import copy
import json
from pathlib import Path

import pytest

from ten_u_event_trend_prospective_v2 import (
    ProspectiveMaturityGateV2,
    append_signal_records,
    build_empty_ledger,
    build_prospective_registration,
    validate_ledger,
)


def registration():
    gate = ProspectiveMaturityGateV2()
    return {
        "strategy_id": "v2",
        "config_fingerprint": "c" * 64,
        "prospective_start": "2026-07-16T00:00:00Z",
        "gate_fingerprint": gate.fingerprint(),
    }


def signal():
    return {
        "symbol": "RAVE-USDT-SWAP",
        "direction": "long",
        "ignition_ts": 1,
        "confirmation_ts": 2,
        "entry_ts": 1784246400000,
        "entry_time": "2026-07-17T00:00:00Z",
        "observed_at": "2026-07-17T00:00:00Z",
        "structural_invalidation": 0.3,
        "atr_1h": 0.01,
        "score": 2.5,
    }


def test_empty_ledger_is_valid_and_outcomes_are_sealed():
    ledger = build_empty_ledger(registration())
    validate_ledger(ledger)
    assert ledger["outcomes_accessed"] is False


def test_append_is_hash_chained_and_idempotent():
    ledger = build_empty_ledger(registration())
    first = append_signal_records(ledger, [signal()], "2026-07-17T00:00:00Z")
    second = append_signal_records(first, [signal()], "2026-07-18T00:00:00Z")
    assert len(first["records"]) == len(second["records"]) == 1
    validate_ledger(second)


def test_append_rejects_outcomes_backfill_and_future_records():
    ledger = build_empty_ledger(registration())
    with pytest.raises(ValueError):
        append_signal_records(ledger, [{**signal(), "net_pnl": 10}], "2026-07-17T00:00:00Z")
    with pytest.raises(ValueError):
        append_signal_records(
            ledger,
            [{**signal(), "entry_time": "2026-07-15T00:00:00Z"}],
            "2026-07-17T00:00:00Z",
        )
    with pytest.raises(ValueError):
        append_signal_records(
            ledger,
            [{**signal(), "entry_time": "2026-07-18T00:00:00Z"}],
            "2026-07-17T00:00:00Z",
        )


def test_append_rejects_signal_not_recorded_at_first_causal_availability():
    ledger = build_empty_ledger(registration())
    with pytest.raises(ValueError, match="first causal availability"):
        append_signal_records(
            ledger,
            [{**signal(), "observed_at": "2026-07-17T01:00:00Z"}],
            "2026-07-17T01:00:00Z",
        )


def test_append_rejects_timestamp_mismatch_and_direct_backfill():
    ledger = build_empty_ledger(registration())
    with pytest.raises(ValueError, match="entry_ts"):
        append_signal_records(
            ledger, [{**signal(), "entry_ts": signal()["entry_ts"] + 1}],
            "2026-07-17T00:00:00Z",
        )
    with pytest.raises(ValueError, match="backfilled"):
        append_signal_records(
            ledger, [signal()], "2026-07-17T01:00:00Z"
        )


def test_hash_tampering_is_detected():
    ledger = append_signal_records(
        build_empty_ledger(registration()), [signal()], "2026-07-17T00:00:00Z"
    )
    broken = copy.deepcopy(ledger)
    broken["records"][0]["direction"] = "short"
    with pytest.raises(ValueError):
        validate_ledger(broken)


def test_saved_registration_and_empty_ledger_match_builders():
    root = Path(__file__).parents[1]
    manifest = root / "reports" / "ten_u_event_trend_baseline_dataset_manifest_v2.json"
    saved_registration = json.loads(
        (root / "reports" / "ten_u_event_trend_prospective_registration_v2.json").read_text(
            encoding="utf-8"
        )
    )
    assert saved_registration == build_prospective_registration(manifest)
    saved_ledger = json.loads(
        (root / "reports" / "ten_u_event_trend_prospective_ledger_v2.json").read_text(
            encoding="utf-8"
        )
    )
    initial_ledger = build_empty_ledger(saved_registration)
    for key, value in initial_ledger.items():
        if key not in {"records", "head_hash"}:
            assert saved_ledger[key] == value
    assert saved_ledger["records"] == []
    assert saved_ledger["head_hash"] == initial_ledger["head_hash"]
    assert saved_ledger["available_through"] >= saved_registration["prospective_start"]
    validate_ledger(saved_ledger)
    validate_ledger(saved_ledger)

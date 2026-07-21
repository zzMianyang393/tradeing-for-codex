import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from funding_rate import FundingRate, parse_funding_rows
from ten_u_event_trend_data_v1 import HOUR_MS, FullHourlyCandle
from ten_u_event_trend_refresh_v2 import (
    append_refresh_audit,
    collect_incremental_completed,
    collect_incremental_funding,
    merge_incremental,
    merge_incremental_funding,
    RefreshLock,
    validate_funding_history,
    validate_refresh_audit,
    classify_new_signal_records,
    late_signal_keys_from_audit,
    FileRollbackGuard,
    validate_instrument_snapshot,
)


def candle(ts: int, close: str = "10", confirmed: bool = True) -> FullHourlyCandle:
    return FullHourlyCandle(
        ts,
        f"1970-01-01T{ts // HOUR_MS:02d}:00:00+00:00",
        "10",
        "11",
        "9",
        close,
        "1",
        "10",
        "100",
        confirmed,
    )


def row(ts: int, confirm: str = "1") -> list[str]:
    return [str(ts), "10", "11", "9", "10", "1", "10", "100", confirm]


def funding(ts: int, rate: float = 0.0001) -> FundingRate:
    return parse_funding_rows([funding_row(ts, str(rate))])[0]


def funding_row(ts: int, rate: str = "0.0001") -> dict[str, str]:
    return {
        "instId": "TEST-USDT-SWAP",
        "fundingTime": str(ts),
        "fundingRate": rate,
        "realizedRate": rate,
    }


def test_incremental_collection_stops_at_frozen_overlap_and_excludes_live_bar():
    last = 3 * HOUR_MS
    pages = {
        None: [row(6 * HOUR_MS, "0"), row(5 * HOUR_MS), row(4 * HOUR_MS), row(3 * HOUR_MS)],
    }

    def fetcher(symbol, after, limit):
        return pages.get(after, [])

    additions = collect_incremental_completed(
        "TEST", last, page_fetcher=fetcher, sleep_seconds=0
    )
    assert [item.timestamp_ms for item in additions] == [4 * HOUR_MS, 5 * HOUR_MS]


def test_merge_is_append_only_and_rejects_gaps():
    existing = [candle(HOUR_MS), candle(2 * HOUR_MS), candle(3 * HOUR_MS)]
    merged = merge_incremental(existing, [candle(4 * HOUR_MS)])
    assert [item.timestamp_ms for item in merged] == [
        HOUR_MS,
        2 * HOUR_MS,
        3 * HOUR_MS,
        4 * HOUR_MS,
    ]
    with pytest.raises(ValueError):
        merge_incremental(existing, [candle(5 * HOUR_MS)])


def test_merge_rejects_rewrite_of_frozen_candle():
    existing = [candle(HOUR_MS), candle(2 * HOUR_MS)]
    with pytest.raises(ValueError):
        merge_incremental(existing, [candle(2 * HOUR_MS, close="9")])


def test_funding_increment_is_causal_complete_and_idempotent():
    existing = [funding(0), funding(8 * HOUR_MS)]

    def fetcher(symbol, after=None, limit=100):
        return [
            funding_row(24 * HOUR_MS),
            funding_row(16 * HOUR_MS),
            funding_row(8 * HOUR_MS),
        ]

    additions = collect_incremental_funding(
        "TEST-USDT-SWAP",
        existing,
        24 * HOUR_MS,
        page_fetcher=fetcher,
        sleep_seconds=0,
    )
    assert [item.ts for item in additions] == [16 * HOUR_MS, 24 * HOUR_MS]
    merged = merge_incremental_funding(
        "TEST-USDT-SWAP", existing, additions, 24 * HOUR_MS
    )
    assert validate_funding_history(
        "TEST-USDT-SWAP", merged, 24 * HOUR_MS
    )["status"] == "PASS"
    assert merge_incremental_funding(
        "TEST-USDT-SWAP", merged, [], 24 * HOUR_MS
    ) == merged


def test_funding_rejects_history_rewrite_gap_and_future_record():
    existing = [funding(0), funding(8 * HOUR_MS)]

    def rewritten(symbol, after=None, limit=100):
        return [funding_row(8 * HOUR_MS, "0.0002")]

    with pytest.raises(ValueError, match="rewrite"):
        collect_incremental_funding(
            "TEST-USDT-SWAP",
            existing,
            24 * HOUR_MS,
            page_fetcher=rewritten,
            sleep_seconds=0,
        )
    with pytest.raises(ValueError, match="coverage"):
        merge_incremental_funding(
            "TEST-USDT-SWAP", existing, [funding(24 * HOUR_MS)], 24 * HOUR_MS
        )
    with pytest.raises(ValueError, match="exceeds"):
        merge_incremental_funding(
            "TEST-USDT-SWAP", existing, [funding(32 * HOUR_MS)], 24 * HOUR_MS
        )


def test_refresh_audit_is_append_only_and_detects_tampering(tmp_path):
    path = tmp_path / "refresh_audit.json"
    report = {
        "formal_status": "signal_only_outcomes_sealed",
        "available_through": "2026-07-16T12:00:00Z",
        "manifest_sha256_before": "a" * 64,
        "manifest_sha256_after": "a" * 64,
        "ledger_head_hash_before": "b" * 64,
        "ledger_head_hash_after": "b" * 64,
        "outcomes_accessed": False,
        "pnl_fields_written": False,
        "historical_records_rewritten": False,
    }
    first = append_refresh_audit(path, report, "2026-07-16T12:00:01Z")
    second = append_refresh_audit(path, report, "2026-07-16T12:00:02Z")
    assert len(first["records"]) == 1
    assert len(second["records"]) == 2
    assert second["records"][1]["previous_hash"] == first["head_hash"]
    validate_refresh_audit(second)
    broken = copy.deepcopy(second)
    broken["records"][0]["available_through"] = "2026-07-16T13:00:00Z"
    with pytest.raises(ValueError):
        validate_refresh_audit(broken)


def test_refresh_audit_rejects_semantic_discontinuity_even_with_valid_new_hash(tmp_path):
    path = tmp_path / "refresh_audit.json"
    base = {
        "formal_status": "signal_only_outcomes_sealed",
        "available_through": "2026-07-16T12:00:00Z",
        "manifest_sha256_before": "a" * 64,
        "manifest_sha256_after": "b" * 64,
        "ledger_head_hash_before": "c" * 64,
        "ledger_head_hash_after": "d" * 64,
        "outcomes_accessed": False,
        "pnl_fields_written": False,
        "historical_records_rewritten": False,
    }
    append_refresh_audit(path, base, "2026-07-16T12:00:01Z")
    discontinuous = {
        **base,
        "manifest_sha256_before": "e" * 64,
        "manifest_sha256_after": "e" * 64,
        "ledger_head_hash_before": "d" * 64,
        "available_through": "2026-07-16T13:00:00Z",
    }
    with pytest.raises(ValueError, match="manifest hash continuity"):
        append_refresh_audit(path, discontinuous, "2026-07-16T13:00:01Z")


def test_refresh_lock_is_single_instance_and_recovers_stale_file(tmp_path):
    path = tmp_path / "refresh.lock"
    with RefreshLock(path):
        assert path.exists()
        with pytest.raises(RuntimeError, match="already running"):
            with RefreshLock(path):
                pass
    assert not path.exists()
    stale = datetime.now(timezone.utc) - timedelta(hours=1)
    path.write_text(
        json.dumps({"token": "old", "started_at": stale.isoformat().replace("+00:00", "Z")}),
        encoding="utf-8",
    )
    with RefreshLock(path):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["token"] != "old"
    assert not path.exists()


def test_late_signal_is_rejected_and_counted_only_once():
    record = {"symbol": "RAVE-USDT-SWAP", "entry_ts": 10 * HOUR_MS}
    first = classify_new_signal_records([record], set(), set(), 12 * HOUR_MS)
    assert first["late"] == [record]
    key = {("RAVE-USDT-SWAP", 10 * HOUR_MS)}
    repeated = classify_new_signal_records([record], set(), key, 13 * HOUR_MS)
    assert repeated["late"] == []
    assert repeated["previously_rejected_late"] == 1


def test_late_signal_keys_are_hash_chained_and_cannot_repeat(tmp_path):
    path = tmp_path / "late_audit.json"
    base = {
        "formal_status": "signal_only_outcomes_sealed",
        "available_through": "2026-07-16T12:00:00Z",
        "manifest_sha256_before": "a" * 64,
        "manifest_sha256_after": "a" * 64,
        "ledger_head_hash_before": "b" * 64,
        "ledger_head_hash_after": "b" * 64,
        "late_signal_keys": [{"symbol": "RAVE-USDT-SWAP", "entry_ts": 1784200000000}],
        "outcomes_accessed": False,
        "pnl_fields_written": False,
        "historical_records_rewritten": False,
    }
    first = append_refresh_audit(path, base, "2026-07-16T12:00:01Z")
    assert late_signal_keys_from_audit(first) == {("RAVE-USDT-SWAP", 1784200000000)}
    with pytest.raises(ValueError, match="more than once"):
        append_refresh_audit(path, base, "2026-07-16T12:00:02Z")


def test_refresh_file_guard_rolls_back_modified_and_new_files(tmp_path):
    existing = tmp_path / "existing.json"
    created = tmp_path / "created.json"
    existing.write_bytes(b"frozen-before")
    with pytest.raises(RuntimeError, match="synthetic refresh failure"):
        with FileRollbackGuard([existing, created]):
            existing.write_bytes(b"partially-updated")
            created.write_bytes(b"partial-new-file")
            raise RuntimeError("synthetic refresh failure")
    assert existing.read_bytes() == b"frozen-before"
    assert not created.exists()


def test_refresh_file_guard_keeps_complete_success(tmp_path):
    target = tmp_path / "manifest.json"
    target.write_bytes(b"before")
    with FileRollbackGuard([target]):
        target.write_bytes(b"committed")
    assert target.read_bytes() == b"committed"


def test_instrument_snapshot_accepts_numeric_format_but_rejects_sizing_drift():
    frozen = {
        "instId": "RAVE-USDT-SWAP",
        "state": "live",
        "ctVal": "10",
        "ctValCcy": "RAVE",
        "lotSz": "0.01",
        "minSz": "0.01",
        "settleCcy": "USDT",
        "lever": "20",
    }
    same = {**frozen, "ctVal": "10.0", "lotSz": "0.010"}
    assert validate_instrument_snapshot(
        frozen["instId"], frozen, same, Decimal("3")
    )["status"] == "PASS"
    changed = {**same, "ctVal": "1"}
    result = validate_instrument_snapshot(
        frozen["instId"], frozen, changed, Decimal("3")
    )
    assert result["status"] == "FAIL"
    assert "ctVal_drift" in result["reasons"]


def test_instrument_snapshot_rejects_delisting_and_insufficient_exchange_leverage():
    frozen = {
        "instId": "LAB-USDT-SWAP",
        "state": "live",
        "ctVal": "10",
        "ctValCcy": "LAB",
        "lotSz": "0.1",
        "minSz": "0.1",
        "settleCcy": "USDT",
        "lever": "10",
    }
    current = {**frozen, "state": "suspend", "lever": "2"}
    result = validate_instrument_snapshot(
        frozen["instId"], frozen, current, Decimal("3")
    )
    assert result["status"] == "FAIL"
    assert "state_drift" in result["reasons"]
    assert "exchange_leverage_below_strategy_cap" in result["reasons"]

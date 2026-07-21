"""Incremental, signal-only prospective refresh for event-trend v2."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable
import uuid

from funding_rate import (
    FundingRate,
    fetch_funding_page,
    load_funding_rates,
    parse_funding_rows,
    save_funding_rates,
)
from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig, PersistentEventTrendWindows
from ten_u_event_trend_data_v1 import (
    HOUR_MS,
    FullHourlyCandle,
    fetch_page,
    format_utc,
    load_hourly,
    parse_utc,
    validate_hourly,
    write_hourly,
    fetch_instrument,
)
from ten_u_event_trend_formation_v1 import load_bars
from ten_u_event_trend_prospective_v2 import append_signal_records, validate_ledger
from ten_u_event_trend_screen_v2 import build_v2_proposals, find_persistence_confirmations


FetchPage = Callable[[str, int | None, int], list[list[str]]]
FundingFetchPage = Callable[..., list[dict[str, Any]]]
InstrumentFetcher = Callable[[str], dict[str, Any]]
SignalKey = tuple[str, int]


def validate_instrument_snapshot(
    symbol: str,
    frozen: dict[str, Any],
    current: dict[str, Any],
    maximum_effective_leverage: Decimal,
) -> dict[str, Any]:
    """Fail closed on changes that alter contract sizing or executability."""
    reasons: list[str] = []
    exact_fields = ("instId", "state", "ctValCcy", "settleCcy")
    numeric_fields = ("ctVal", "lotSz", "minSz")
    for field in exact_fields:
        if current.get(field) != frozen.get(field):
            reasons.append(f"{field}_drift")
    for field in numeric_fields:
        try:
            if Decimal(str(current.get(field))) != Decimal(str(frozen.get(field))):
                reasons.append(f"{field}_drift")
        except InvalidOperation:
            reasons.append(f"{field}_invalid")
    try:
        if Decimal(str(current.get("lever"))) < maximum_effective_leverage:
            reasons.append("exchange_leverage_below_strategy_cap")
    except InvalidOperation:
        reasons.append("lever_invalid")
    critical = {field: current.get(field) for field in exact_fields + numeric_fields}
    return {
        "status": "PASS" if not reasons else "FAIL",
        "symbol": symbol,
        "critical_fingerprint": hashlib.sha256(_canonical(critical).encode()).hexdigest(),
        "reasons": reasons,
    }


class FileRollbackGuard:
    """Restore a bounded set of files byte-for-byte when a refresh raises."""

    def __init__(self, paths: list[Path]):
        self.paths = list(dict.fromkeys(Path(path) for path in paths))
        self.before: dict[Path, bytes | None] = {}

    def __enter__(self) -> "FileRollbackGuard":
        self.before = {
            path: path.read_bytes() if path.exists() else None for path in self.paths
        }
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            return False
        restore_errors: list[str] = []
        for path, content in self.before.items():
            try:
                if content is None:
                    if path.exists():
                        path.unlink()
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
            except OSError as restore_error:
                restore_errors.append(f"{path}:{restore_error}")
        if restore_errors:
            raise RuntimeError(
                "prospective refresh failed and rollback was incomplete: "
                + "; ".join(restore_errors)
            ) from exc
        return False


class RefreshLock:
    """Atomic single-process guard for the hourly prospective refresh."""

    def __init__(self, path: Path, stale_after: timedelta = timedelta(minutes=45)):
        self.path = path
        self.stale_after = stale_after
        self.token = uuid.uuid4().hex

    def __enter__(self) -> "RefreshLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        if self.path.exists():
            try:
                existing = json.loads(self.path.read_text(encoding="utf-8"))
                started = _utc_timestamp(existing["started_at"])
            except (KeyError, ValueError, json.JSONDecodeError):
                started = datetime.min.replace(tzinfo=timezone.utc)
            if now - started <= self.stale_after:
                raise RuntimeError("prospective refresh is already running")
            self.path.unlink()
        payload = json.dumps(
            {
                "token": self.token,
                "pid": os.getpid(),
                "started_at": now.isoformat().replace("+00:00", "Z"),
            }
        ).encode()
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as exc:
            raise RuntimeError("prospective refresh lock acquisition raced") from exc
        try:
            os.write(descriptor, payload)
        finally:
            os.close(descriptor)
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            existing = json.loads(self.path.read_text(encoding="utf-8"))
            if existing.get("token") == self.token:
                self.path.unlink()
        except (FileNotFoundError, json.JSONDecodeError):
            pass


def _utc_timestamp(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("lock timestamp must use UTC Z")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def collect_incremental_completed(
    symbol: str,
    last_existing_ts: int,
    *,
    page_fetcher: FetchPage = fetch_page,
    sleep_seconds: float = 0.12,
) -> list[FullHourlyCandle]:
    additions: dict[int, FullHourlyCandle] = {}
    after: int | None = None
    previous_oldest: int | None = None
    while True:
        page = page_fetcher(symbol, after, 100)
        if not page:
            break
        candles = [FullHourlyCandle.from_okx(row) for row in page]
        for candle in candles:
            if candle.confirmed and candle.timestamp_ms > last_existing_ts:
                additions[candle.timestamp_ms] = candle
        oldest = min(candle.timestamp_ms for candle in candles)
        if oldest <= last_existing_ts:
            break
        if previous_oldest is not None and oldest >= previous_oldest:
            raise RuntimeError("OKX incremental pagination did not move backward")
        previous_oldest = oldest
        after = oldest
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return [additions[timestamp] for timestamp in sorted(additions)]


def merge_incremental(
    existing: list[FullHourlyCandle], additions: list[FullHourlyCandle]
) -> list[FullHourlyCandle]:
    if not existing:
        raise ValueError("prospective refresh requires a frozen historical base")
    merged = {candle.timestamp_ms: candle for candle in existing}
    for candle in additions:
        if candle.timestamp_ms <= existing[-1].timestamp_ms:
            old = merged.get(candle.timestamp_ms)
            if old is not None and old != candle:
                raise ValueError("incremental API attempted to rewrite a frozen candle")
            continue
        merged[candle.timestamp_ms] = candle
    ordered = [merged[timestamp] for timestamp in sorted(merged)]
    validation = validate_hourly(ordered)
    if validation["status"] != "PASS":
        raise ValueError(f"incremental hourly coverage failed: {validation}")
    return ordered


def validate_funding_history(
    symbol: str, rates: list[FundingRate], available_through_ms: int
) -> dict[str, Any]:
    reasons: list[str] = []
    timestamps = [rate.ts for rate in rates]
    if not rates:
        return {"status": "FAIL", "rows": 0, "reasons": ["no_funding_rows"]}
    if timestamps != sorted(set(timestamps)):
        reasons.append("funding_timestamps_not_strictly_increasing")
    if any(rate.symbol != symbol for rate in rates):
        reasons.append("funding_symbol_mismatch")
    if any(rate.ts > available_through_ms for rate in rates):
        reasons.append("funding_after_available_cutoff")
    gaps = [
        (right - left) / HOUR_MS for left, right in zip(timestamps, timestamps[1:])
    ]
    maximum_gap_hours = max(gaps, default=0.0)
    boundary_lag_hours = (available_through_ms - timestamps[-1]) / HOUR_MS
    if maximum_gap_hours > 8:
        reasons.append("funding_gap_above_8h")
    if not 0 <= boundary_lag_hours <= 8:
        reasons.append("funding_cutoff_not_covered")
    return {
        "status": "PASS" if not reasons else "FAIL",
        "rows": len(rates),
        "first_timestamp_ms": timestamps[0],
        "last_timestamp_ms": timestamps[-1],
        "maximum_gap_hours": maximum_gap_hours,
        "boundary_lag_hours": boundary_lag_hours,
        "reasons": reasons,
    }


def collect_incremental_funding(
    symbol: str,
    existing: list[FundingRate],
    available_through_ms: int,
    *,
    page_fetcher: FundingFetchPage = fetch_funding_page,
    sleep_seconds: float = 0.12,
) -> list[FundingRate]:
    if not existing:
        raise ValueError("funding refresh requires a frozen historical base")
    existing_by_ts = {rate.ts: rate for rate in existing}
    last_existing_ts = existing[-1].ts
    additions: dict[int, FundingRate] = {}
    after: int | None = None
    previous_oldest: int | None = None
    while True:
        page = page_fetcher(symbol, after=after, limit=100)
        if not page:
            break
        parsed = parse_funding_rows(page)
        if not parsed:
            break
        for rate in parsed:
            old = existing_by_ts.get(rate.ts)
            if old is not None and old != rate:
                raise ValueError("OKX attempted to rewrite a frozen funding record")
            if last_existing_ts < rate.ts <= available_through_ms:
                additions[rate.ts] = rate
        oldest = min(rate.ts for rate in parsed)
        if oldest <= last_existing_ts:
            break
        if previous_oldest is not None and oldest >= previous_oldest:
            raise RuntimeError("OKX funding pagination did not move backward")
        previous_oldest = oldest
        after = oldest
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return [additions[timestamp] for timestamp in sorted(additions)]


def merge_incremental_funding(
    symbol: str,
    existing: list[FundingRate],
    additions: list[FundingRate],
    available_through_ms: int,
) -> list[FundingRate]:
    if not existing:
        raise ValueError("funding refresh requires a frozen historical base")
    merged = {rate.ts: rate for rate in existing}
    last_existing_ts = existing[-1].ts
    for rate in additions:
        old = merged.get(rate.ts)
        if rate.ts <= last_existing_ts:
            if old is not None and old != rate:
                raise ValueError("incremental funding attempted to rewrite history")
            continue
        if rate.ts > available_through_ms:
            raise ValueError("incremental funding exceeds the candle cutoff")
        merged[rate.ts] = rate
    ordered = [merged[timestamp] for timestamp in sorted(merged)]
    validation = validate_funding_history(symbol, ordered, available_through_ms)
    if validation["status"] != "PASS":
        raise ValueError(f"incremental funding coverage failed: {validation}")
    return ordered


def _iso_z(timestamp_ms: int) -> str:
    return format_utc(timestamp_ms).replace("+00:00", "Z")


def _prospective_signal_records(
    manifest: dict[str, Any], available_through_ms: int
) -> list[dict[str, Any]]:
    config = PersistentEventTrendConfig()
    windows = PersistentEventTrendWindows()
    start_ms = parse_utc(windows.prospective_start)
    records: list[dict[str, Any]] = []
    for symbol in config.symbols:
        bars = load_bars(Path(manifest["symbols"][symbol]["path"]))
        confirmations = find_persistence_confirmations(
            symbol, bars, config, start_ms, available_through_ms
        )
        confirmation_by_ignition = {
            confirmation.ignition_ts: confirmation for confirmation in confirmations
        }
        proposals = build_v2_proposals(
            symbol,
            bars,
            confirmations,
            config,
            available_through_ms,
            allow_entry_at_end=True,
        )
        for proposal in proposals:
            confirmation = confirmation_by_ignition[proposal.ignition_ts]
            records.append(
                {
                    "symbol": proposal.symbol,
                    "direction": proposal.direction,
                    "ignition_ts": proposal.ignition_ts,
                    "confirmation_ts": confirmation.confirmation_ts,
                    "entry_ts": proposal.entry_ts,
                    "entry_time": _iso_z(proposal.entry_ts),
                    "observed_at": _iso_z(proposal.entry_ts),
                    "structural_invalidation": proposal.structural_invalidation,
                    "atr_1h": proposal.atr_1h,
                    "score": proposal.score,
                }
            )
    return sorted(records, key=lambda item: (item["entry_ts"], item["symbol"]))


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def validate_refresh_audit(audit: dict[str, Any]) -> None:
    header = {
        "audit_version": audit["audit_version"],
        "strategy_id": audit["strategy_id"],
        "config_fingerprint": audit["config_fingerprint"],
    }
    previous = _hash(header)
    previous_record: dict[str, Any] | None = None
    seen_late_signal_keys: set[SignalKey] = set()
    for sequence, record in enumerate(audit["records"], start=1):
        if record["sequence"] != sequence or record["previous_hash"] != previous:
            raise ValueError("prospective refresh audit chain is broken")
        payload = {key: value for key, value in record.items() if key != "record_hash"}
        if _hash(payload) != record["record_hash"]:
            raise ValueError("prospective refresh audit record was modified")
        required = (
            "recorded_at",
            "available_through",
            "manifest_sha256_before",
            "manifest_sha256_after",
            "ledger_head_hash_before",
            "ledger_head_hash_after",
            "outcomes_accessed",
            "pnl_fields_written",
            "historical_records_rewritten",
        )
        if any(key not in record for key in required):
            raise ValueError("prospective refresh audit record is incomplete")
        if (
            record["outcomes_accessed"] is not False
            or record["pnl_fields_written"] is not False
            or record["historical_records_rewritten"] is not False
        ):
            raise ValueError("prospective refresh audit violated sealed-data policy")
        _utc_timestamp(record["recorded_at"])
        _utc_timestamp(record["available_through"])
        if previous_record is not None:
            if record["manifest_sha256_before"] != previous_record["manifest_sha256_after"]:
                raise ValueError("manifest hash continuity is broken across refreshes")
            if record["ledger_head_hash_before"] != previous_record["ledger_head_hash_after"]:
                raise ValueError("ledger head continuity is broken across refreshes")
            if _utc_timestamp(record["available_through"]) < _utc_timestamp(
                previous_record["available_through"]
            ):
                raise ValueError("prospective data cutoff moved backward")
            if _utc_timestamp(record["recorded_at"]) < _utc_timestamp(
                previous_record["recorded_at"]
            ):
                raise ValueError("prospective refresh recorded_at moved backward")
            current_funding_before = record.get("funding_sha256_before")
            previous_funding_after = previous_record.get("funding_sha256_after")
            if current_funding_before is not None and previous_funding_after is not None:
                if current_funding_before != previous_funding_after:
                    raise ValueError("funding hash continuity is broken across refreshes")
        if "funding_validation" in record and any(
            item.get("status") != "PASS"
            for item in record["funding_validation"].values()
        ):
            raise ValueError("failed funding coverage was written to refresh audit")
        if "instrument_validation" in record and any(
            item.get("status") != "PASS"
            for item in record["instrument_validation"].values()
        ):
            raise ValueError("failed instrument contract check was written to refresh audit")
        for item in record.get("late_signal_keys", []):
            if set(item) != {"symbol", "entry_ts"}:
                raise ValueError("late signal audit key contains unsafe fields")
            key = (str(item["symbol"]), int(item["entry_ts"]))
            if key in seen_late_signal_keys:
                raise ValueError("late signal was recorded more than once")
            if key[1] >= parse_utc(record["available_through"]):
                raise ValueError("late signal key is not earlier than its detection cutoff")
            seen_late_signal_keys.add(key)
        previous = record["record_hash"]
        previous_record = record
    if audit["head_hash"] != previous:
        raise ValueError("prospective refresh audit head hash mismatch")


def late_signal_keys_from_audit(audit: dict[str, Any]) -> set[SignalKey]:
    validate_refresh_audit(audit)
    return {
        (str(item["symbol"]), int(item["entry_ts"]))
        for record in audit["records"]
        for item in record.get("late_signal_keys", [])
    }


def classify_new_signal_records(
    signal_records: list[dict[str, Any]],
    existing_keys: set[SignalKey],
    previously_rejected_late_keys: set[SignalKey],
    available_through_ms: int,
) -> dict[str, Any]:
    """Classify each signal once without ever making a late signal tradable."""
    causal: list[dict[str, Any]] = []
    late: list[dict[str, Any]] = []
    previously_recorded = 0
    previously_rejected = 0
    for record in signal_records:
        key = (record["symbol"], int(record["entry_ts"]))
        if key in existing_keys:
            previously_recorded += 1
        elif key in previously_rejected_late_keys:
            previously_rejected += 1
        elif record["entry_ts"] == available_through_ms:
            causal.append(record)
        elif record["entry_ts"] < available_through_ms:
            late.append(record)
        else:
            raise ValueError("signal record is later than the completed-data cutoff")
    return {
        "causal": causal,
        "late": late,
        "previously_recorded": previously_recorded,
        "previously_rejected_late": previously_rejected,
    }


def append_refresh_audit(
    audit_path: Path, report: dict[str, Any], recorded_at: str | None = None
) -> dict[str, Any]:
    config = PersistentEventTrendConfig()
    header = {
        "audit_version": "v1.0.0",
        "strategy_id": config.strategy_id,
        "config_fingerprint": config.fingerprint(),
    }
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        validate_refresh_audit(audit)
        if any(audit[key] != value for key, value in header.items()):
            raise ValueError("prospective refresh audit header drift")
    else:
        audit = {**header, "records": [], "head_hash": _hash(header)}
    payload = {
        "sequence": len(audit["records"]) + 1,
        "previous_hash": audit["head_hash"],
        "recorded_at": recorded_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **report,
    }
    payload["record_hash"] = _hash(payload)
    audit["records"].append(payload)
    audit["head_hash"] = payload["record_hash"]
    validate_refresh_audit(audit)
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    return audit


def _refresh_unprotected(
    manifest_path: Path,
    ledger_path: Path,
    report_path: Path,
    audit_path: Path | None = None,
    *,
    page_fetcher: FetchPage = fetch_page,
    funding_page_fetcher: FundingFetchPage = fetch_funding_page,
    instrument_fetcher: InstrumentFetcher = fetch_instrument,
    sleep_seconds: float = 0.12,
) -> dict[str, Any]:
    manifest_before_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_before_bytes)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    validate_ledger(ledger)
    if audit_path is not None and audit_path.exists():
        prior_audit = json.loads(audit_path.read_text(encoding="utf-8"))
        validate_refresh_audit(prior_audit)
        if prior_audit["records"]:
            last_audit = prior_audit["records"][-1]
            if last_audit["manifest_sha256_after"] != hashlib.sha256(
                manifest_before_bytes
            ).hexdigest():
                raise ValueError("working manifest is not the audited successor")
            if last_audit["ledger_head_hash_after"] != ledger["head_hash"]:
                raise ValueError("working ledger is not the audited successor")
        previously_rejected_late_keys = late_signal_keys_from_audit(prior_audit)
    else:
        previously_rejected_late_keys = set()
    config = PersistentEventTrendConfig()
    instrument_validation: dict[str, dict[str, Any]] = {}
    for symbol in config.symbols:
        frozen_instrument = manifest["symbols"][symbol]["instrument"]
        current_instrument = instrument_fetcher(symbol)
        validation = validate_instrument_snapshot(
            symbol,
            frozen_instrument,
            current_instrument,
            config.maximum_effective_leverage,
        )
        instrument_validation[symbol] = validation
    if any(item["status"] != "PASS" for item in instrument_validation.values()):
        raise ValueError(f"instrument contract drift detected: {instrument_validation}")
    additions_by_symbol: dict[str, int] = {}
    latest_close_by_symbol: dict[str, int] = {}
    for symbol in config.symbols:
        item = manifest["symbols"][symbol]
        path = Path(item["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"working dataset fingerprint drift before refresh: {symbol}")
        existing = load_hourly(path)
        additions = collect_incremental_completed(
            symbol,
            existing[-1].timestamp_ms,
            page_fetcher=page_fetcher,
            sleep_seconds=sleep_seconds,
        )
        merged = merge_incremental(existing, additions)
        sha256 = write_hourly(path, merged)
        validation = validate_hourly(merged)
        item["sha256"] = sha256
        item["validation"] = validation
        additions_by_symbol[symbol] = len(additions)
        latest_close_by_symbol[symbol] = merged[-1].timestamp_ms + HOUR_MS
    available_through_ms = min(latest_close_by_symbol.values())
    available_through = _iso_z(available_through_ms)
    funding_additions_by_symbol: dict[str, int] = {}
    funding_sha256_before: dict[str, str] = {}
    funding_sha256_after: dict[str, str] = {}
    funding_validation: dict[str, dict[str, Any]] = {}
    for symbol in config.symbols:
        item = manifest["symbols"][symbol]
        funding_item = item.get("funding", {})
        funding_path = Path(
            funding_item.get(
                "path", str(manifest_path.parent / f"{symbol}_funding.csv")
            )
        )
        before_hash = hashlib.sha256(funding_path.read_bytes()).hexdigest()
        expected_hash = funding_item.get("sha256")
        if expected_hash is not None and before_hash != expected_hash:
            raise ValueError(f"working funding fingerprint drift before refresh: {symbol}")
        existing_funding = load_funding_rates(funding_path)
        funding_additions = collect_incremental_funding(
            symbol,
            existing_funding,
            available_through_ms,
            page_fetcher=funding_page_fetcher,
            sleep_seconds=sleep_seconds,
        )
        merged_funding = merge_incremental_funding(
            symbol, existing_funding, funding_additions, available_through_ms
        )
        save_funding_rates(funding_path, merged_funding)
        after_hash = hashlib.sha256(funding_path.read_bytes()).hexdigest()
        validation = validate_funding_history(
            symbol, merged_funding, available_through_ms
        )
        item["funding"] = {
            "path": str(funding_path).replace("\\", "/"),
            "sha256": after_hash,
            "source": "OKX historical archive plus public funding-rate-history",
            "actual_realized_rates": True,
            "validation": validation,
        }
        funding_additions_by_symbol[symbol] = len(funding_additions)
        funding_sha256_before[symbol] = before_hash
        funding_sha256_after[symbol] = after_hash
        funding_validation[symbol] = validation
    manifest["requested_end"] = available_through
    manifest["coverage_status"] = (
        "PASS"
        if all(item["validation"]["status"] == "PASS" for item in manifest["symbols"].values())
        else "FAIL"
    )
    if manifest["coverage_status"] != "PASS":
        raise ValueError("working manifest coverage failed after refresh")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    old_count = len(ledger["records"])
    signal_records = _prospective_signal_records(manifest, available_through_ms)
    existing_keys = {
        (record["symbol"], record["entry_ts"]) for record in ledger["records"]
    }
    classified = classify_new_signal_records(
        signal_records,
        existing_keys,
        previously_rejected_late_keys,
        available_through_ms,
    )
    causal_records = classified["causal"]
    late_records = classified["late"]
    late_signal_keys = [
        {"symbol": record["symbol"], "entry_ts": record["entry_ts"]}
        for record in late_records
    ]
    updated_ledger = append_signal_records(ledger, causal_records, available_through)
    ledger_path.write_text(json.dumps(updated_ledger, indent=2), encoding="utf-8")

    report = {
        "report_type": "ten_u_event_trend_prospective_signal_refresh_v2",
        "formal_status": "signal_only_outcomes_sealed",
        "strategy_id": config.strategy_id,
        "config_fingerprint": config.fingerprint(),
        "available_through": available_through,
        "added_completed_hourly_bars": additions_by_symbol,
        "added_realized_funding_points": funding_additions_by_symbol,
        "funding_sha256_before": funding_sha256_before,
        "funding_sha256_after": funding_sha256_after,
        "funding_validation": funding_validation,
        "instrument_validation": instrument_validation,
        "candidate_signal_records_found": len(signal_records),
        "previously_recorded_signal_records": classified["previously_recorded"],
        "previously_rejected_late_signal_records": classified["previously_rejected_late"],
        "late_signal_records_rejected": len(late_records),
        "late_signal_keys": late_signal_keys,
        "new_signal_records_appended": len(updated_ledger["records"]) - old_count,
        "total_signal_records": len(updated_ledger["records"]),
        "manifest_sha256_before": hashlib.sha256(manifest_before_bytes).hexdigest(),
        "manifest_sha256_after": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "ledger_head_hash_before": ledger["head_hash"],
        "ledger_head_hash_after": updated_ledger["head_hash"],
        "outcomes_accessed": False,
        "pnl_fields_written": False,
        "historical_records_rewritten": False,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if audit_path is not None:
        append_refresh_audit(audit_path, report)
    return report


def refresh(
    manifest_path: Path,
    ledger_path: Path,
    report_path: Path,
    audit_path: Path | None = None,
    *,
    page_fetcher: FetchPage = fetch_page,
    funding_page_fetcher: FundingFetchPage = fetch_funding_page,
    instrument_fetcher: InstrumentFetcher = fetch_instrument,
    sleep_seconds: float = 0.12,
) -> dict[str, Any]:
    """Run one refresh as an exception-atomic filesystem transaction."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutation_paths = [manifest_path, ledger_path, report_path]
    if audit_path is not None:
        mutation_paths.append(audit_path)
    for symbol, item in manifest["symbols"].items():
        mutation_paths.append(Path(item["path"]))
        funding_item = item.get("funding", {})
        mutation_paths.append(
            Path(
                funding_item.get(
                    "path", str(manifest_path.parent / f"{symbol}_funding.csv")
                )
            )
        )
    with FileRollbackGuard(mutation_paths):
        return _refresh_unprotected(
            manifest_path,
            ledger_path,
            report_path,
            audit_path,
            page_fetcher=page_fetcher,
            funding_page_fetcher=funding_page_fetcher,
            instrument_fetcher=instrument_fetcher,
            sleep_seconds=sleep_seconds,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/event_trend_v1/hourly_dataset_manifest_v1.json"),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path("reports/ten_u_event_trend_prospective_ledger_v2.json"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("reports/ten_u_event_trend_prospective_refresh_v2.json"),
    )
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path("reports/ten_u_event_trend_prospective_refresh_audit_v2.json"),
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path("reports/ten_u_event_trend_refresh_v2.lock"),
    )
    args = parser.parse_args()
    with RefreshLock(args.lock):
        print(
            json.dumps(
                refresh(args.manifest, args.ledger, args.report, args.audit), indent=2
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Append-only prospective signal ledger and maturity gate for v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from ten_u_event_trend_contract_v1 import _jsonable, _utc
from ten_u_event_trend_contract_v2 import (
    PersistentEventTrendConfig,
    PersistentEventTrendWindows,
)


FORBIDDEN_OUTCOME_KEYS = frozenset(
    {
        "exit_ts",
        "exit_time",
        "exit_price",
        "exit_reason",
        "pnl",
        "net_pnl",
        "return",
        "return_fraction",
        "equity",
        "equity_after",
        "mfe",
        "mae",
        "winner",
        "outcome",
    }
)


@dataclass(frozen=True)
class ProspectiveMaturityGateV2:
    minimum_calendar_days: int = 0
    minimum_trades: int = 6
    minimum_wins: int = 2
    minimum_distinct_traded_symbols: int = 2
    minimum_profit_factor: Decimal = Decimal("1.25")
    minimum_ending_equity: Decimal = Decimal("10")
    maximum_drawdown_fraction: Decimal = Decimal("0.70")
    minimum_peak_profit_retention: Decimal = Decimal("0.50")
    maximum_stopped_then_recovered_fraction: Decimal = Decimal("0.35")
    minimum_median_winner_capture: Decimal = Decimal("0.35")
    maximum_top_winner_gross_profit_contribution: Decimal = Decimal("0.75")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def fingerprint(self) -> str:
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def build_prospective_registration(dataset_manifest_path: Path) -> dict[str, Any]:
    config = PersistentEventTrendConfig()
    windows = PersistentEventTrendWindows()
    gate = ProspectiveMaturityGateV2()
    start = _utc(windows.prospective_start)
    earliest = start + timedelta(days=gate.minimum_calendar_days)
    manifest_hash = hashlib.sha256(dataset_manifest_path.read_bytes()).hexdigest()
    return {
        "strategy_id": config.strategy_id,
        "config_fingerprint": config.fingerprint(),
        "formal_status": "prospective_signal_observation_not_mature",
        "prospective_start": windows.prospective_start,
        "earliest_evaluation": earliest.isoformat().replace("+00:00", "Z"),
        "gate": gate.to_dict(),
        "gate_fingerprint": gate.fingerprint(),
        "baseline_dataset_manifest_sha256": manifest_hash,
        "historical_screen_status": "sealed_screen_insufficient_evidence",
        "outcomes_may_be_evaluated": False,
        "promotion_before_maturity": False,
    }


def build_empty_ledger(registration: dict[str, Any]) -> dict[str, Any]:
    header = {
        "ledger_version": "v1.1.0",
        "strategy_id": registration["strategy_id"],
        "config_fingerprint": registration["config_fingerprint"],
        "prospective_start": registration["prospective_start"],
        "gate_fingerprint": registration["gate_fingerprint"],
    }
    return {
        **header,
        "formal_status": "append_only_signal_ledger_outcomes_sealed",
        "records": [],
        "head_hash": _hash(header),
        "outcomes_accessed": False,
    }


def append_signal_records(
    ledger: dict[str, Any],
    records: Iterable[dict[str, Any]],
    available_through: str,
) -> dict[str, Any]:
    validate_ledger(ledger)
    start = _utc(ledger["prospective_start"])
    cutoff = _utc(available_through)
    if cutoff < start:
        raise ValueError("available_through predates prospective start")
    output = json.loads(json.dumps(ledger))
    existing_keys = {
        (record["symbol"], record["entry_ts"])
        for record in output["records"]
    }
    previous_hash = output["head_hash"]
    ordered = sorted(records, key=lambda item: (item["entry_ts"], item["symbol"]))
    for raw in ordered:
        forbidden = FORBIDDEN_OUTCOME_KEYS.intersection(raw)
        if forbidden:
            raise ValueError(f"prospective signal record contains outcome fields: {sorted(forbidden)}")
        key = (raw["symbol"], raw["entry_ts"])
        if key in existing_keys:
            continue
        entry_time = _utc(raw["entry_time"])
        if entry_time < start or entry_time > cutoff:
            raise ValueError("signal record falls outside the append cutoff")
        if int(entry_time.timestamp() * 1000) != raw["entry_ts"]:
            raise ValueError("entry_ts does not match entry_time")
        observed_at = _utc(raw["observed_at"])
        if observed_at != entry_time:
            raise ValueError(
                "prospective signals must be recorded at first causal availability"
            )
        if observed_at > cutoff:
            raise ValueError("signal observation falls after the append cutoff")
        if observed_at != cutoff:
            raise ValueError("new signal cannot be backfilled after its causal cutoff")
        payload = {
            "sequence": len(output["records"]) + 1,
            "previous_hash": previous_hash,
            "symbol": raw["symbol"],
            "direction": raw["direction"],
            "ignition_ts": raw["ignition_ts"],
            "confirmation_ts": raw["confirmation_ts"],
            "entry_ts": raw["entry_ts"],
            "entry_time": raw["entry_time"],
            "observed_at": raw["observed_at"],
            "structural_invalidation": raw["structural_invalidation"],
            "atr_1h": raw["atr_1h"],
            "score": raw["score"],
            "config_fingerprint": ledger["config_fingerprint"],
        }
        record_hash = _hash(payload)
        payload["record_hash"] = record_hash
        output["records"].append(payload)
        previous_hash = record_hash
        existing_keys.add(key)
    output["head_hash"] = previous_hash
    output["available_through"] = available_through
    validate_ledger(output)
    return output


def validate_ledger(ledger: dict[str, Any]) -> None:
    if ledger.get("ledger_version") != "v1.1.0":
        raise ValueError("unsupported prospective ledger version")
    if ledger.get("outcomes_accessed") is not False:
        raise ValueError("prospective ledger must keep outcomes sealed")
    header = {
        "ledger_version": ledger["ledger_version"],
        "strategy_id": ledger["strategy_id"],
        "config_fingerprint": ledger["config_fingerprint"],
        "prospective_start": ledger["prospective_start"],
        "gate_fingerprint": ledger["gate_fingerprint"],
    }
    expected_previous = _hash(header)
    for sequence, record in enumerate(ledger["records"], start=1):
        if FORBIDDEN_OUTCOME_KEYS.intersection(record):
            raise ValueError("ledger record contains outcomes")
        if record["sequence"] != sequence or record["previous_hash"] != expected_previous:
            raise ValueError("prospective hash chain is broken")
        payload = {key: value for key, value in record.items() if key != "record_hash"}
        if _hash(payload) != record["record_hash"]:
            raise ValueError("prospective record fingerprint drift")
        expected_previous = record["record_hash"]
    if ledger["head_hash"] != expected_previous:
        raise ValueError("prospective ledger head hash mismatch")


def main() -> int:
    manifest = Path("reports/ten_u_event_trend_baseline_dataset_manifest_v2.json")
    registration = build_prospective_registration(manifest)
    registration_path = Path("reports/ten_u_event_trend_prospective_registration_v2.json")
    ledger_path = Path("reports/ten_u_event_trend_prospective_ledger_v2.json")
    if registration_path.exists() and json.loads(registration_path.read_text(encoding="utf-8")) != registration:
        raise ValueError("prospective registration drift")
    if ledger_path.exists():
        validate_ledger(json.loads(ledger_path.read_text(encoding="utf-8")))
    print(json.dumps({"registration": registration, "empty_ledger": build_empty_ledger(registration)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

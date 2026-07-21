"""Operational health check for the signal-only event-trend v2 observer."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from funding_rate import load_funding_rates
from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig
from ten_u_event_trend_data_v1 import HOUR_MS, load_hourly, parse_utc, validate_hourly
from ten_u_event_trend_evaluation_v2 import build_evaluator_registration
from ten_u_event_trend_prospective_v2 import validate_ledger
from ten_u_event_trend_refresh_v2 import (
    validate_funding_history,
    validate_refresh_audit,
)


def _utc(value: str) -> datetime:
    if not value.endswith("Z"):
        raise ValueError("health timestamps must use UTC Z")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return parsed


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_health(
    manifest_path: Path,
    ledger_path: Path,
    audit_path: Path,
    evaluator_registration_path: Path,
    as_of: str,
    maximum_staleness_hours: int = 2,
) -> dict[str, Any]:
    now = _utc(as_of)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    evaluator_registration = json.loads(
        evaluator_registration_path.read_text(encoding="utf-8")
    )
    reasons: list[str] = []
    try:
        validate_ledger(ledger)
    except (KeyError, ValueError) as exc:
        reasons.append(f"ledger_invalid:{exc}")
    try:
        validate_refresh_audit(audit)
    except (KeyError, ValueError) as exc:
        reasons.append(f"refresh_audit_invalid:{exc}")
    if evaluator_registration != build_evaluator_registration():
        reasons.append("evaluator_source_drift")
    config = PersistentEventTrendConfig()
    cutoff_text = manifest.get("requested_end", "")
    try:
        cutoff_ms = parse_utc(cutoff_text)
        cutoff = datetime.fromtimestamp(cutoff_ms / 1000, tz=timezone.utc)
        staleness_hours = (now - cutoff).total_seconds() / 3600
        if not 0 <= staleness_hours <= maximum_staleness_hours:
            reasons.append("market_data_stale_or_future")
    except (TypeError, ValueError):
        cutoff_ms = 0
        staleness_hours = None
        reasons.append("manifest_cutoff_invalid")
    symbol_health: dict[str, Any] = {}
    for symbol in config.symbols:
        item = manifest.get("symbols", {}).get(symbol)
        symbol_reasons: list[str] = []
        if not item:
            reasons.append(f"symbol_missing:{symbol}")
            continue
        candle_path = Path(item["path"])
        candle_hash_ok = _hash(candle_path) == item["sha256"]
        if not candle_hash_ok:
            symbol_reasons.append("candle_hash_drift")
        candles = load_hourly(candle_path)
        candle_validation = validate_hourly(candles)
        if candle_validation["status"] != "PASS":
            symbol_reasons.append("candle_validation_failed")
        if candles and candles[-1].timestamp_ms + HOUR_MS != cutoff_ms:
            symbol_reasons.append("candle_cutoff_mismatch")
        funding_item = item.get("funding")
        funding_hash_ok = False
        funding_validation: dict[str, Any] = {"status": "FAIL"}
        if not funding_item:
            symbol_reasons.append("funding_binding_missing")
        else:
            funding_path = Path(funding_item["path"])
            funding_hash_ok = _hash(funding_path) == funding_item["sha256"]
            if not funding_hash_ok:
                symbol_reasons.append("funding_hash_drift")
            funding_validation = validate_funding_history(
                symbol, load_funding_rates(funding_path), cutoff_ms
            )
            if funding_validation["status"] != "PASS":
                symbol_reasons.append("funding_validation_failed")
        symbol_health[symbol] = {
            "status": "PASS" if not symbol_reasons else "FAIL",
            "candle_hash_ok": candle_hash_ok,
            "candle_validation": candle_validation,
            "funding_hash_ok": funding_hash_ok,
            "funding_validation": funding_validation,
            "reasons": symbol_reasons,
        }
        reasons.extend(f"{symbol}:{reason}" for reason in symbol_reasons)
    if audit.get("records"):
        latest_audit = audit["records"][-1]
        if latest_audit.get("ledger_head_hash_after") != ledger.get("head_hash"):
            reasons.append("audit_ledger_head_mismatch")
        if latest_audit.get("available_through") != cutoff_text:
            reasons.append("audit_manifest_cutoff_mismatch")
        try:
            audit_age_hours = (now - _utc(latest_audit["recorded_at"])).total_seconds() / 3600
            if not 0 <= audit_age_hours <= maximum_staleness_hours:
                reasons.append("refresh_audit_stale_or_future")
        except (KeyError, ValueError):
            audit_age_hours = None
            reasons.append("refresh_audit_time_invalid")
    else:
        audit_age_hours = None
        reasons.append("refresh_audit_empty")
    return {
        "report_type": "ten_u_event_trend_observer_health_v2",
        "formal_status": "PASS" if not reasons else "FAIL",
        "as_of": as_of,
        "available_through": cutoff_text,
        "market_data_staleness_hours": staleness_hours,
        "refresh_audit_age_hours": audit_age_hours,
        "signal_records": len(ledger.get("records", [])),
        "symbols": symbol_health,
        "reasons": reasons,
        "outcome_metrics_computed": False,
        "strategy_parameters_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--as-of",
        default=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    parser.add_argument("--manifest", type=Path, default=Path("data/event_trend_v1/hourly_dataset_manifest_v1.json"))
    parser.add_argument("--ledger", type=Path, default=Path("reports/ten_u_event_trend_prospective_ledger_v2.json"))
    parser.add_argument("--audit", type=Path, default=Path("reports/ten_u_event_trend_prospective_refresh_audit_v2.json"))
    parser.add_argument("--evaluator-registration", type=Path, default=Path("reports/ten_u_event_trend_evaluator_registration_v2.json"))
    parser.add_argument("--report", type=Path, default=Path("reports/ten_u_event_trend_health_v2.json"))
    args = parser.parse_args()
    report = check_health(
        args.manifest,
        args.ledger,
        args.audit,
        args.evaluator_registration,
        args.as_of,
    )
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["formal_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""One-command signal-only hourly observation cycle for event-trend v2."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

from ten_u_event_trend_health_v2 import check_health
from ten_u_event_trend_refresh_v2 import RefreshLock, refresh


SAFE_SIGNAL_FIELDS = (
    "symbol",
    "direction",
    "entry_time",
    "structural_invalidation",
    "atr_1h",
    "record_hash",
)


def run_cycle(
    manifest_path: Path,
    ledger_path: Path,
    refresh_report_path: Path,
    refresh_audit_path: Path,
    evaluator_registration_path: Path,
    health_report_path: Path,
    cycle_report_path: Path,
    lock_path: Path,
    *,
    now: str | None = None,
) -> dict[str, Any]:
    with RefreshLock(lock_path):
        refresh_report = refresh(
            manifest_path,
            ledger_path,
            refresh_report_path,
            refresh_audit_path,
        )
        as_of = now or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        health = check_health(
            manifest_path,
            ledger_path,
            refresh_audit_path,
            evaluator_registration_path,
            as_of,
        )
        health_report_path.write_text(json.dumps(health, indent=2), encoding="utf-8")
        new_count = int(refresh_report["new_signal_records_appended"])
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        safe_signals = [
            {key: record[key] for key in SAFE_SIGNAL_FIELDS}
            for record in ledger["records"][-new_count:]
        ] if new_count else []
        report = {
            "report_type": "ten_u_event_trend_signal_only_cycle_v2",
            "formal_status": health["formal_status"],
            "as_of": as_of,
            "available_through": refresh_report["available_through"],
            "added_completed_hourly_bars": refresh_report["added_completed_hourly_bars"],
            "added_realized_funding_points": refresh_report["added_realized_funding_points"],
            "new_signal_records_appended": new_count,
            "late_signal_records_rejected": refresh_report["late_signal_records_rejected"],
            "safe_new_signals": safe_signals,
            "ledger_head_hash": refresh_report["ledger_head_hash_after"],
            "health_reasons": health["reasons"],
            "outcome_metrics_computed": False,
            "strategy_parameters_modified": False,
        }
        cycle_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report


def main() -> int:
    # Automations are project-scoped and may start one directory above this
    # module.  Resolve every default path against the strategy workspace.
    os.chdir(Path(__file__).resolve().parent)
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("data/event_trend_v1/hourly_dataset_manifest_v1.json"))
    parser.add_argument("--ledger", type=Path, default=Path("reports/ten_u_event_trend_prospective_ledger_v2.json"))
    parser.add_argument("--refresh-report", type=Path, default=Path("reports/ten_u_event_trend_prospective_refresh_v2.json"))
    parser.add_argument("--refresh-audit", type=Path, default=Path("reports/ten_u_event_trend_prospective_refresh_audit_v2.json"))
    parser.add_argument("--evaluator-registration", type=Path, default=Path("reports/ten_u_event_trend_evaluator_registration_v2.json"))
    parser.add_argument("--health-report", type=Path, default=Path("reports/ten_u_event_trend_health_v2.json"))
    parser.add_argument("--cycle-report", type=Path, default=Path("reports/ten_u_event_trend_cycle_v2.json"))
    parser.add_argument("--lock", type=Path, default=Path("reports/ten_u_event_trend_refresh_v2.lock"))
    args = parser.parse_args()
    report = run_cycle(
        args.manifest,
        args.ledger,
        args.refresh_report,
        args.refresh_audit,
        args.evaluator_registration,
        args.health_report,
        args.cycle_report,
        args.lock,
    )
    print(json.dumps(report, indent=2))
    return 0 if report["formal_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Prospective OI context timing and coverage audit.

Checks:
  - No attachment uses future available_ts
  - All snapshots within common cutoff
  - 16:15 UTC availability timing correct
  - Stale attachment count (snapshot > 30h old at signal time)
  - Coverage gaps per signal: fresh / stale_source_data / no_snapshot_available
  - Latest snapshot freshness at cutoff
  - No market performance data

This is a READ-ONLY audit.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from prospective_signal_oi_context_attachment import MAX_OI_CONTEXT_AGE_HOURS, HOUR_MS


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def audit_timing(
    attachments: list[dict],
    snapshots: list[dict],
    cutoff_ts: int,
) -> dict:
    """Audit timing correctness of OI context attachments."""
    issues: list[str] = []

    for att in attachments:
        signal_ts = att.get("signal_ts", 0)
        avail_ts = att.get("oi_snapshot_available_ts")

        if avail_ts is not None:
            if avail_ts > signal_ts:
                issues.append(
                    f"Signal {att.get('candidate_id')}: available_ts > signal_ts (future data)"
                )
            if avail_ts > cutoff_ts:
                issues.append(
                    f"Signal {att.get('candidate_id')}: available_ts > cutoff"
                )
            avail_dt = datetime.fromtimestamp(avail_ts / 1000, tz=timezone.utc)
            if avail_dt.hour != 16 or avail_dt.minute != 15:
                issues.append(
                    f"Signal {att.get('candidate_id')}: available_ts not 16:15 UTC"
                )

    # Coverage by reason
    reason_counts = Counter(a.get("attachment_reason", "unknown") for a in attachments)

    # Latest snapshot info
    latest_snap = max(snapshots, key=lambda s: s["available_ts"]) if snapshots else None
    latest_age_hours = None
    if latest_snap:
        latest_age_ms = cutoff_ts - latest_snap["available_ts"]
        latest_age_hours = round(latest_age_ms / HOUR_MS, 1)

    # Stale count from attachments
    stale_count = sum(1 for a in attachments if a.get("attachment_reason") == "stale_source_data")

    return {
        "audit_type": "prospective_oi_context_timing",
        "audit_date": "2026-07-14",
        "observation_only": True,
        "max_age_hours": MAX_OI_CONTEXT_AGE_HOURS,
        "n_issues": len(issues),
        "issues": issues[:10],
        "coverage": {
            "total_signals": len(attachments),
            "oi_context_known": sum(1 for a in attachments if a.get("oi_context_known")),
            "oi_context_unknown": sum(1 for a in attachments if not a.get("oi_context_known")),
        },
        "attachment_reason_counts": dict(reason_counts),
        "stale_attachment_count": stale_count,
        "latest_snapshot_available_ts": latest_snap["available_ts"] if latest_snap else None,
        "latest_snapshot_available_utc": latest_snap["available_timestamp_utc"] if latest_snap else None,
        "latest_snapshot_age_at_cutoff_hours": latest_age_hours,
        "n_snapshots_total": len(snapshots),
        "n_snapshots_within_cutoff": sum(1 for s in snapshots if s.get("available_ts", 0) <= cutoff_ts),
        "cutoff_ts": cutoff_ts,
        "cutoff_utc": datetime.fromtimestamp(cutoff_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "methodology_notes": [
            f"Freshness limit: {MAX_OI_CONTEXT_AGE_HOURS} hours.",
            "Checks no future available_ts used.",
            "Checks all snapshots within cutoff.",
            "Checks 16:15 UTC availability timing.",
            "Stale attachments counted separately.",
            "No market performance data.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Prospective OI context timing audit.")
    p.add_argument("--attachments", type=Path, default=Path("reports/prospective_signal_oi_context_attachment.json"))
    p.add_argument("--snapshots", type=Path, default=Path("reports/prospective_oi_risk_snapshot.json"))
    p.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    p.add_argument("--out", type=Path, default=Path("reports/prospective_oi_context_timing_audit.json"))
    args = p.parse_args(argv)

    att_data = load_json(args.attachments)
    snap_data = load_json(args.snapshots)
    ledger = load_json(args.ledger)

    if not att_data or not snap_data:
        print("ERROR: Cannot load attachments or snapshots")
        return 1

    if ledger:
        cutoff_str = ledger.get("common_data_cutoff", "2026-07-13 08:15:00")
    else:
        cutoff_str = "2026-07-13 08:15:00"
    cutoff_ts = int(
        datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc).timestamp() * 1000
    )

    result = audit_timing(
        att_data.get("attachments", []),
        snap_data.get("snapshots", []),
        cutoff_ts,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Issues: {result['n_issues']}")
    print(f"Known: {result['coverage']['oi_context_known']}, Unknown: {result['coverage']['oi_context_unknown']}")
    print(f"Stale: {result['stale_attachment_count']}")
    print(f"Latest snapshot age at cutoff: {result['latest_snapshot_age_at_cutoff_hours']}h")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

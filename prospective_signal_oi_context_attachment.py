"""Prospective signal OI context attachment.

Attaches OI risk snapshots to shadow signals using only snapshots
available at or before the signal timestamp AND within freshness limit.

Freshness rule: MAX_OI_CONTEXT_AGE_HOURS = 30.
  - OI forms at 16:00 UTC, available at 16:15 UTC.
  - A snapshot older than 30 hours at signal time is stale.
  - Stale snapshots produce oi_context_known=false, attachment_reason=stale_source_data.
  - Stale snapshot values (risk_state, qualified_fraction, etc.) are NOT used.

This is a READ-ONLY context attachment.  It does NOT:
  - Filter, delete, or modify any signal
  - Calculate returns or PnL
  - Import runner.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


MAX_OI_CONTEXT_AGE_HOURS = 30
HOUR_MS = 3600 * 1000


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def attach_oi_context(
    ledger: dict,
    snapshots: list[dict],
    max_age_hours: float = MAX_OI_CONTEXT_AGE_HOURS,
) -> list[dict]:
    """Attach the latest available OI snapshot to each signal.

    A snapshot is only attached if:
      1. available_ts <= signal_ts (no future data)
      2. (signal_ts - available_ts) <= max_age_hours * HOUR_MS (fresh enough)

    If a past snapshot exists but is stale, oi_context_known=false and
    attachment_reason=stale_source_data.  No values from the stale snapshot
    are used.
    """
    sorted_snaps = sorted(snapshots, key=lambda s: s["available_ts"])
    max_age_ms = int(max_age_hours * HOUR_MS)

    signals = ledger.get("signals", [])
    attachments = []

    for sig in signals:
        signal_ts = sig.get("signal_ts", 0)
        candidate_id = sig.get("candidate_id", "")
        symbol = sig.get("symbol", "")
        signal_ts_utc = sig.get("signal_timestamp_utc", "")

        # Find latest snapshot with available_ts <= signal_ts
        best_snap = None
        for snap in reversed(sorted_snaps):
            if snap["available_ts"] <= signal_ts:
                best_snap = snap
                break

        if best_snap is None:
            # No past snapshot at all
            attachments.append({
                "candidate_id": candidate_id,
                "signal_ts": signal_ts,
                "signal_timestamp_utc": signal_ts_utc,
                "symbol": symbol,
                "oi_snapshot_available_ts": None,
                "oi_snapshot_available_timestamp_utc": None,
                "oi_risk_state_candidate": None,
                "oi_qualified_coin_count": None,
                "oi_qualified_fraction": None,
                "oi_median_abs_change_pct": None,
                "oi_context_known": False,
                "oi_age_hours": None,
                "attachment_reason": "no_snapshot_available_before_signal",
                "observation_only": True,
            })
        else:
            age_ms = signal_ts - best_snap["available_ts"]
            age_hours = age_ms / HOUR_MS

            if age_ms > max_age_ms:
                # Snapshot exists but is stale — do NOT use its values
                attachments.append({
                    "candidate_id": candidate_id,
                    "signal_ts": signal_ts,
                    "signal_timestamp_utc": signal_ts_utc,
                    "symbol": symbol,
                    "oi_snapshot_available_ts": None,
                    "oi_snapshot_available_timestamp_utc": None,
                    "oi_risk_state_candidate": None,
                    "oi_qualified_coin_count": None,
                    "oi_qualified_fraction": None,
                    "oi_median_abs_change_pct": None,
                    "oi_context_known": False,
                    "oi_age_hours": round(age_hours, 1),
                    "attachment_reason": "stale_source_data",
                    "observation_only": True,
                })
            else:
                # Fresh snapshot — use its values
                attachments.append({
                    "candidate_id": candidate_id,
                    "signal_ts": signal_ts,
                    "signal_timestamp_utc": signal_ts_utc,
                    "symbol": symbol,
                    "oi_snapshot_available_ts": best_snap["available_ts"],
                    "oi_snapshot_available_timestamp_utc": best_snap["available_timestamp_utc"],
                    "oi_risk_state_candidate": best_snap["risk_state_candidate"],
                    "oi_qualified_coin_count": best_snap["qualified_coin_count"],
                    "oi_qualified_fraction": best_snap["qualified_fraction"],
                    "oi_median_abs_change_pct": best_snap["median_abs_change_pct"],
                    "oi_context_known": True,
                    "oi_age_hours": round(age_hours, 1),
                    "attachment_reason": "fresh_snapshot_attached",
                    "observation_only": True,
                })

    return attachments


def main(argv=None):
    p = argparse.ArgumentParser(description="Prospective signal OI context attachment.")
    p.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    p.add_argument("--snapshots", type=Path, default=Path("reports/prospective_oi_risk_snapshot.json"))
    p.add_argument("--max-age-hours", type=float, default=MAX_OI_CONTEXT_AGE_HOURS)
    p.add_argument("--out", type=Path, default=Path("reports/prospective_signal_oi_context_attachment.json"))
    args = p.parse_args(argv)

    ledger = load_json(args.ledger)
    if not ledger:
        print("ERROR: Cannot load ledger")
        return 1

    snap_data = load_json(args.snapshots)
    if not snap_data:
        print("ERROR: Cannot load snapshots")
        return 1

    snapshots = snap_data.get("snapshots", [])
    attachments = attach_oi_context(ledger, snapshots, args.max_age_hours)

    known_count = sum(1 for a in attachments if a["oi_context_known"])
    unknown_count = sum(1 for a in attachments if not a["oi_context_known"])
    stale_count = sum(1 for a in attachments if a.get("attachment_reason") == "stale_source_data")
    no_snap_count = sum(1 for a in attachments if a.get("attachment_reason") == "no_snapshot_available_before_signal")

    # Latest snapshot info
    latest_snap = max(snapshots, key=lambda s: s["available_ts"]) if snapshots else None

    output = {
        "attachment_type": "prospective_signal_oi_context",
        "generation_date": "2026-07-14",
        "observation_only": True,
        "max_age_hours": args.max_age_hours,
        "n_signals": len(attachments),
        "n_oi_context_known": known_count,
        "n_oi_context_unknown": unknown_count,
        "n_stale": stale_count,
        "n_no_snapshot": no_snap_count,
        "latest_snapshot_available_ts": latest_snap["available_ts"] if latest_snap else None,
        "latest_snapshot_available_utc": latest_snap["available_timestamp_utc"] if latest_snap else None,
        "attachments": attachments,
        "methodology_notes": [
            f"Freshness limit: {args.max_age_hours} hours.",
            "Only snapshots with available_ts <= signal_ts AND age <= max_age_hours are used.",
            "Stale snapshots produce oi_context_known=false; values are NOT used.",
            "This is a context attachment, NOT a filter or veto.",
            "No returns, PnL, or price data.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Signals: {len(attachments)}, Known: {known_count}, Stale: {stale_count}, No-snap: {no_snap_count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

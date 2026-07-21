"""Prospective maturity audit: check which observations have reached 90-day maturity.

Default as_of = ledger common_data_cutoff (never system clock).
Statuses: awaiting_maturity / mature_awaiting_sealed_evaluation / invalid_identity / duplicate_identity

This is a READ-ONLY audit.  It does NOT:
  - Calculate returns or PnL
  - Read market data after the cutoff
  - Modify any strategy or approval status
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def audit_maturity(registry: dict, as_of_ts: int) -> dict:
    """Audit maturity status of each observation."""
    observations = registry.get("observations", [])

    results: list[dict] = []
    for obs in observations:
        obs_id = obs.get("observation_id", "")
        maturity_ts = obs.get("maturity_ts", 0)
        is_dup = obs.get("duplicate_identity", False)

        if is_dup:
            status = "duplicate_identity"
        elif as_of_ts < maturity_ts:
            status = "awaiting_maturity"
        else:
            status = "mature_awaiting_sealed_evaluation"

        results.append({
            "observation_id": obs_id,
            "candidate_id": obs.get("candidate_id", ""),
            "symbol": obs.get("symbol", ""),
            "signal_ts": obs.get("signal_ts"),
            "maturity_ts": maturity_ts,
            "maturity_timestamp_utc": obs.get("maturity_timestamp_utc", ""),
            "status": status,
        })

    status_counts = Counter(r["status"] for r in results)

    # Timing info
    maturity_tss = [obs["maturity_ts"] for obs in observations if not obs.get("duplicate_identity")]
    earliest = min(maturity_tss) if maturity_tss else 0
    latest = max(maturity_tss) if maturity_tss else 0

    # Next maturing
    awaiting = [r for r in results if r["status"] == "awaiting_maturity"]
    next_maturity_ts = min(r["maturity_ts"] for r in awaiting) if awaiting else None
    next_maturity_utc = (
        datetime.fromtimestamp(next_maturity_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        if next_maturity_ts else None
    )

    return {
        "audit_type": "prospective_maturity_audit",
        "audit_date": "2026-07-14",
        "observation_only": True,
        "as_of_ts": as_of_ts,
        "as_of_utc": datetime.fromtimestamp(as_of_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "simulated_as_of": False,
        "source_cutoff": registry.get("common_data_cutoff", ""),
        "n_observations": len(results),
        "status_counts": dict(status_counts),
        "earliest_maturity_utc": datetime.fromtimestamp(earliest / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if earliest else None,
        "latest_maturity_utc": datetime.fromtimestamp(latest / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if latest else None,
        "next_maturity_utc": next_maturity_utc,
        "n_awaiting": status_counts.get("awaiting_maturity", 0),
        "n_mature": status_counts.get("mature_awaiting_sealed_evaluation", 0),
        "n_duplicate": status_counts.get("duplicate_identity", 0),
        "n_invalid": status_counts.get("invalid_identity", 0),
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
        "observations": results,
        "methodology_notes": [
            "as_of defaults to ledger common_data_cutoff, not system clock.",
            "mature_awaiting_sealed_evaluation does NOT imply approval.",
            "No returns, PnL, or price data included.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Prospective maturity audit.")
    p.add_argument("--registry", type=Path, default=Path("reports/prospective_observation_registry.json"))
    p.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    p.add_argument("--as-of", type=str, default=None, help="Override as_of (simulated)")
    p.add_argument("--out", type=Path, default=Path("reports/prospective_maturity_audit.json"))
    args = p.parse_args(argv)

    registry = load_json(args.registry)
    if not registry:
        print("ERROR: Cannot load observation registry")
        return 1

    # Determine as_of
    simulated = False
    if args.as_of:
        as_of_ts = int(
            datetime.strptime(args.as_of, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000
        )
        simulated = True
    else:
        # Default to ledger cutoff
        ledger = load_json(args.ledger) or {}
        cutoff_str = ledger.get("common_data_cutoff", "2026-07-13 08:15:00")
        as_of_ts = int(
            datetime.strptime(cutoff_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000
        )

    result = audit_maturity(registry, as_of_ts)
    result["simulated_as_of"] = simulated

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")

    print(f"\nas_of: {result['as_of_utc']} (simulated={simulated})")
    print(f"Observations: {result['n_observations']}")
    print(f"  awaiting_maturity: {result['n_awaiting']}")
    print(f"  mature: {result['n_mature']}")
    print(f"  duplicate: {result['n_duplicate']}")
    print(f"Next maturity: {result['next_maturity_utc']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

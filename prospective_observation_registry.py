"""Prospective observation immutable registry.

Reads from: reports/prospective_shadow_signal_ledger.json
Creates an immutable observation registry with:
  - observation_id (identity hash)
  - maturity_ts = signal_ts + 90 days
  - No price/return/PnL fields

This is a READ-ONLY infrastructure module.  It does NOT:
  - Calculate returns or PnL
  - Read market data
  - Modify any strategy or approval status
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OBSERVATION_HORIZON_DAYS = 90
DAY_MS = 24 * 3600 * 1000


def load_ledger(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def compute_identity_hash(
    candidate_id: str,
    rule_version: str,
    signal_ts: int,
    symbol: str,
    direction: str,
    regime: str,
) -> str:
    """Compute deterministic identity hash for an observation."""
    payload = f"{candidate_id}|{rule_version}|{signal_ts}|{symbol}|{direction}|{regime}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def build_registry(ledger: dict) -> dict[str, Any]:
    """Build the immutable observation registry from the ledger."""
    signals = ledger.get("signals", [])
    common_cutoff = ledger.get("common_data_cutoff", "")
    ledger_signal_count = ledger.get("signal_count", 0)

    observations: list[dict] = []
    seen_hashes: dict[str, int] = {}

    for i, sig in enumerate(signals):
        candidate_id = sig.get("candidate_id", "")
        rule_version = sig.get("rule_version", "")
        signal_ts = sig.get("signal_ts", 0)
        signal_ts_utc = sig.get("signal_timestamp_utc", "")
        symbol = sig.get("symbol", "")
        direction = sig.get("direction", "")
        regime = sig.get("regime", "")

        maturity_ts = signal_ts + OBSERVATION_HORIZON_DAYS * DAY_MS
        maturity_utc = datetime.fromtimestamp(
            maturity_ts / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")

        obs_hash = compute_identity_hash(
            candidate_id, rule_version, signal_ts, symbol, direction, regime
        )

        duplicate = obs_hash in seen_hashes
        seen_hashes[obs_hash] = i

        observations.append({
            "observation_id": obs_hash,
            "candidate_id": candidate_id,
            "rule_version": rule_version,
            "signal_ts": signal_ts,
            "signal_timestamp_utc": signal_ts_utc,
            "symbol": symbol,
            "direction": direction,
            "regime": regime,
            "observation_start_ts": signal_ts,
            "maturity_ts": maturity_ts,
            "maturity_timestamp_utc": maturity_utc,
            "observation_horizon_days": OBSERVATION_HORIZON_DAYS,
            "observation_only": True,
            "duplicate_identity": duplicate,
        })

    unique_hashes = len(set(seen_hashes.keys()))

    return {
        "registry_type": "prospective_observation_registry",
        "generation_date": "2026-07-14",
        "observation_only": True,
        "source_ledger": "reports/prospective_shadow_signal_ledger.json",
        "ledger_signal_count": ledger_signal_count,
        "common_data_cutoff": common_cutoff,
        "registry_signal_count": len(observations),
        "unique_identity_hashes": unique_hashes,
        "hash_consistent": len(observations) == ledger_signal_count,
        "observations": observations,
        "methodology_notes": [
            "This is an immutable observation registry.",
            "maturity_ts = signal_ts + 90 * 24h (exact).",
            "Identity hash covers candidate_id, rule_version, signal_ts, symbol, direction, regime.",
            "No price, return, PnL, or exit fields.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Build prospective observation registry.")
    p.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    p.add_argument("--out", type=Path, default=Path("reports/prospective_observation_registry.json"))
    args = p.parse_args(argv)

    ledger = load_ledger(args.ledger)
    if not ledger:
        print("ERROR: Cannot load ledger")
        return 1

    registry = build_registry(ledger)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Signals: {registry['registry_signal_count']}, Unique hashes: {registry['unique_identity_hashes']}")

    # Check for duplicates
    dups = [o for o in registry["observations"] if o["duplicate_identity"]]
    if dups:
        print(f"WARNING: {len(dups)} duplicate identities found")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

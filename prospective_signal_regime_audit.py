"""Prospective signal regime audit: check shadow signals against declared regimes.

Reads: reports/prospective_shadow_signal_ledger.json (28 signals)
Uses: factor_regime_compatibility_matrix for regime vocabulary and factor mapping

Only checks whether signals fired in their declared applicable regime.
Does NOT calculate returns, exits, positions, or PnL.

This is an OBSERVATION-ONLY audit.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from factor_regime_compatibility_matrix import (
    CANDIDATE_TO_FACTOR,
    REGIME_VOCABULARY_VERSION,
    get_entry_by_candidate_id,
    normalize_regime,
    is_regime_known,
)


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def audit_signal(
    signal: dict,
    matrix_entry: Any | None,
) -> dict:
    """Audit a single signal for regime compliance."""
    candidate_id = signal.get("candidate_id", "unknown")
    raw_regime = signal.get("regime", "")
    signal_ts = signal.get("signal_ts")
    signal_ts_utc = signal.get("signal_timestamp_utc", "")
    symbol = signal.get("symbol", "unknown")
    direction = signal.get("direction", "unknown")

    # Normalize regime
    normalized_regime = normalize_regime(raw_regime)
    regime_known = is_regime_known(raw_regime)

    # Check compliance
    if not regime_known:
        return {
            "candidate_id": candidate_id,
            "factor_id": CANDIDATE_TO_FACTOR.get(candidate_id, "unknown"),
            "signal_ts": signal_ts,
            "signal_timestamp_utc": signal_ts_utc,
            "symbol": symbol,
            "direction": direction,
            "raw_regime": raw_regime,
            "normalized_regime": None,
            "regime_known": False,
            "compliant": False,
            "reason": f"Unknown regime label '{raw_regime}' — not in vocabulary v{REGIME_VOCABULARY_VERSION}",
        }

    if matrix_entry is None:
        return {
            "candidate_id": candidate_id,
            "factor_id": CANDIDATE_TO_FACTOR.get(candidate_id, "unknown"),
            "signal_ts": signal_ts,
            "signal_timestamp_utc": signal_ts_utc,
            "symbol": symbol,
            "direction": direction,
            "raw_regime": raw_regime,
            "normalized_regime": normalized_regime,
            "regime_known": True,
            "compliant": False,
            "reason": f"Factor '{candidate_id}' not found in compatibility matrix",
        }

    # Check if normalized regime is in declared regimes
    declared = set(matrix_entry.declared_regimes)
    compliant = normalized_regime in declared

    reason = ""
    if not compliant:
        reason = (f"Regime '{normalized_regime}' not in declared regimes {sorted(declared)} "
                  f"for factor '{matrix_entry.factor_id}'")

    return {
        "candidate_id": candidate_id,
        "factor_id": matrix_entry.factor_id,
        "signal_ts": signal_ts,
        "signal_timestamp_utc": signal_ts_utc,
        "symbol": symbol,
        "direction": direction,
        "raw_regime": raw_regime,
        "normalized_regime": normalized_regime,
        "regime_known": True,
        "compliant": compliant,
        "reason": reason,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Prospective signal regime audit.")
    p.add_argument("--ledger", type=Path, default=Path("reports/prospective_shadow_signal_ledger.json"))
    p.add_argument("--out", type=Path, default=Path("reports/prospective_signal_regime_audit.json"))
    args = p.parse_args(argv)

    # Load ledger
    ledger = load_json(args.ledger)
    if not ledger:
        print("ERROR: Cannot load shadow signal ledger")
        return 1

    signals = ledger.get("signals", [])
    common_cutoff = ledger.get("common_data_cutoff", "")
    ledger_signal_count = ledger.get("signal_count", 0)

    print(f"Ledger: {len(signals)} signals, cutoff={common_cutoff}")

    # Audit each signal
    results: list[dict] = []
    for sig in signals:
        candidate_id = sig.get("candidate_id", "")
        matrix_entry = get_entry_by_candidate_id(candidate_id)
        result = audit_signal(sig, matrix_entry)
        results.append(result)

    # Summary
    total = len(results)
    compliant = sum(1 for r in results if r["compliant"])
    non_compliant = sum(1 for r in results if not r["compliant"])
    unknown_regime = sum(1 for r in results if not r["regime_known"])

    # Per-factor summary
    per_factor: dict[str, dict] = {}
    for r in results:
        fid = r["factor_id"]
        if fid not in per_factor:
            per_factor[fid] = {"n_signals": 0, "n_compliant": 0, "n_non_compliant": 0, "n_unknown_regime": 0}
        per_factor[fid]["n_signals"] += 1
        if r["compliant"]:
            per_factor[fid]["n_compliant"] += 1
        elif not r["regime_known"]:
            per_factor[fid]["n_unknown_regime"] += 1
        else:
            per_factor[fid]["n_non_compliant"] += 1

    for fid, pf in per_factor.items():
        pf["compliance_rate"] = round(pf["n_compliant"] / pf["n_signals"], 3) if pf["n_signals"] > 0 else None

    output = {
        "audit_type": "prospective_signal_regime",
        "audit_date": "2026-07-13",
        "observation_only": True,
        "common_data_cutoff": common_cutoff,
        "regime_vocabulary_version": REGIME_VOCABULARY_VERSION,
        "n_signals_total": total,
        "ledger_signal_count": ledger_signal_count,
        "signal_count_match": total == ledger_signal_count,
        "total_compliant": compliant,
        "total_non_compliant": non_compliant,
        "total_unknown_regime": unknown_regime,
        "per_factor": per_factor,
        "signal_details": results,
        "methodology_notes": [
            "Signals from prospective_shadow_signal_ledger.json.",
            "Regime labels normalized via versioned vocabulary.",
            "Unknown labels marked as non-compliant (not auto-passed).",
            "No returns, exits, positions, or PnL calculated.",
        ],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")

    # Print summary
    print(f"\nTotal: {total} signals")
    print(f"Compliant: {compliant}, Non-compliant: {non_compliant}, Unknown regime: {unknown_regime}")
    for fid, pf in sorted(per_factor.items()):
        cr = f"{pf['compliance_rate']:.1%}" if pf["compliance_rate"] is not None else "N/A"
        print(f"  {fid}: {pf['n_compliant']}/{pf['n_signals']} compliant ({cr})")
        if pf["n_unknown_regime"] > 0:
            print(f"    WARNING: {pf['n_unknown_regime']} signals with unknown regime")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

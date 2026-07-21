"""Data quality audit for frozen 28 eligible symbols.

Reads eligible_symbols from prospective_candidate_registry.json frozen_candidates.
Only audits those symbols — does NOT auto-scan the data directory.

Reports per-symbol: first/last timestamp, row count, gaps, duplicates,
and a common cutoff.

This is a READ-ONLY audit.  Does NOT calculate returns or fix gaps.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path("data")
FIFTEEN_MIN_MS = 15 * 60 * 1000


def load_registry(p: Path = Path("reports/prospective_candidate_registry.json")) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def get_eligible_symbols(registry: dict) -> list[str]:
    """Extract eligible_symbols from frozen_candidates."""
    for fc in registry.get("frozen_candidates", []):
        syms = fc.get("eligible_symbols", [])
        if syms:
            # Convert from SWAP format to base: AAVE-USDT-SWAP -> AAVE
            return [s.split("-")[0] for s in syms]
    return []


def audit_symbol(path: Path) -> dict:
    """Audit a single 15m CSV file."""
    rows = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                ts_str = r.get("timestamp", "")
                ts = int(datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc).timestamp() * 1000)
                rows.append(ts)
            except (KeyError, ValueError):
                continue

    if not rows:
        return {"symbol": path.stem.replace("_15m", ""), "error": "no_data"}

    rows.sort()
    first_ts = rows[0]
    last_ts = rows[-1]
    n_rows = len(rows)

    # Detect gaps
    gaps = []
    for i in range(1, len(rows)):
        diff = rows[i] - rows[i - 1]
        if diff > FIFTEEN_MIN_MS * 2:
            gap_bars = diff // FIFTEEN_MIN_MS - 1
            gaps.append({
                "from_ts": rows[i - 1],
                "to_ts": rows[i],
                "missing_bars": int(gap_bars),
                "from_utc": datetime.fromtimestamp(rows[i - 1] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "to_utc": datetime.fromtimestamp(rows[i] / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
            })

    # Detect duplicates
    ts_counts = Counter(rows)
    dup_count = sum(1 for c in ts_counts.values() if c > 1)

    # Expected vs actual
    total_span_ms = last_ts - first_ts
    expected_bars = total_span_ms // FIFTEEN_MIN_MS + 1
    coverage = n_rows / expected_bars if expected_bars > 0 else 0

    return {
        "symbol": path.stem.replace("_15m", ""),
        "first_ts": first_ts,
        "first_utc": datetime.fromtimestamp(first_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "last_ts": last_ts,
        "last_utc": datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
        "n_rows": n_rows,
        "expected_bars": int(expected_bars),
        "coverage": round(coverage, 4),
        "n_gaps": len(gaps),
        "total_missing_bars": sum(g["missing_bars"] for g in gaps),
        "n_duplicate_timestamps": dup_count,
        "largest_gap_bars": max((g["missing_bars"] for g in gaps), default=0),
        "gaps": gaps[:5],
    }


def actual_common_cutoff(valid: list[dict]) -> tuple[int, str]:
    """Return the oldest latest bar across the audited frozen-symbol files."""
    if not valid:
        return 0, ""
    cutoff = min(int(item["last_ts"]) for item in valid)
    return cutoff, datetime.fromtimestamp(cutoff / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def build_report(
    data_dir: Path = DATA_DIR,
    registry: dict | None = None,
    cutoff_override: str | None = None,
) -> dict:
    """Build the read-only quality report without writing files."""
    registry = registry or load_registry()
    if not registry:
        raise ValueError("Cannot load prospective_candidate_registry.json")
    eligible_symbols = get_eligible_symbols(registry)
    if not eligible_symbols:
        raise ValueError("No eligible_symbols found in frozen_candidates")

    all_data_files = {p.stem.replace("_15m", "") for p in data_dir.glob("*_15m.csv")}
    excluded_symbols = sorted(all_data_files - set(eligible_symbols))
    results = []
    for sym in eligible_symbols:
        path = data_dir / f"{sym}_15m.csv"
        results.append(audit_symbol(path) if path.exists() else {"symbol": sym, "error": "file_not_found"})

    valid = [item for item in results if "error" not in item]
    if cutoff_override:
        common_cutoff_str = cutoff_override
        common_cutoff_ts = int(
            datetime.strptime(common_cutoff_str, "%Y-%m-%d %H:%M:%S")
            .replace(tzinfo=timezone.utc).timestamp() * 1000
        )
    else:
        common_cutoff_ts, common_cutoff_str = actual_common_cutoff(valid)

    return {
        "audit_type": "data_quality",
        "audit_date": "2026-07-14",
        "observation_only": True,
        "eligible_symbols_source": "prospective_candidate_registry.json frozen_candidates",
        "n_eligible_symbols": len(eligible_symbols),
        "n_audited": len(valid),
        "excluded_symbols": excluded_symbols,
        "exclusion_reason": "not_in_frozen_candidates_eligible_symbols",
        "common_cutoff_ts": common_cutoff_ts,
        "common_cutoff_utc": common_cutoff_str,
        "per_symbol": results,
        "summary": {
            "total_rows": sum(item.get("n_rows", 0) for item in results),
            "total_gaps": sum(item.get("n_gaps", 0) for item in results),
            "total_missing_bars": sum(item.get("total_missing_bars", 0) for item in results),
            "total_duplicates": sum(item.get("n_duplicate_timestamps", 0) for item in results),
            "min_coverage": min((item.get("coverage", 0) for item in valid), default=0),
            "max_coverage": max((item.get("coverage", 0) for item in valid), default=0),
        },
        "methodology_notes": [
            "Eligible symbols from prospective_candidate_registry.json frozen_candidates only.",
            "SEI and other non-frozen symbols are excluded.",
            "Common cutoff is the oldest latest completed 15m bar across the audited frozen-symbol files.",
            "A ledger's published cutoff is immutable evidence and is not reused as live data-coverage metadata.",
            "No returns or strategy performance calculated.",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Data quality audit for frozen eligible symbols.")
    p.add_argument("--cutoff-override", type=str, default=None, help="Override common cutoff")
    p.add_argument("--out", type=Path, default=Path("reports/data_quality_audit.json"))
    args = p.parse_args(argv)

    try:
        output = build_report(cutoff_override=args.cutoff_override)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Eligible: {output['n_eligible_symbols']}, Audited: {output['n_audited']}, Excluded: {len(output['excluded_symbols'])}")
    print(f"Excluded: {output['excluded_symbols']}")
    print(f"Common cutoff: {output['common_cutoff_utc']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

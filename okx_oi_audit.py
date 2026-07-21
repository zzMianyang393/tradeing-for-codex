"""Describe quality and event distribution of downloaded OKX daily OI data."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any


DAY_MS = 24 * 60 * 60 * 1000


def load_oi_usd(path: Path) -> list[tuple[int, float]]:
    values: list[tuple[int, float]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                values.append((int(row["ts"]), float(row["open_interest_usd"])))
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(set(values))


def audit_series(values: list[tuple[int, float]]) -> dict[str, Any]:
    if len(values) < 2:
        return {"rows": len(values), "error": "insufficient_rows"}
    gaps = [later - earlier for (earlier, _), (later, _) in zip(values, values[1:]) if later - earlier != DAY_MS]
    changes = [later / earlier - 1.0 for (_, earlier), (_, later) in zip(values, values[1:]) if earlier > 0]
    ordered_changes = sorted(changes)
    return {
        "rows": len(values),
        "first_ts": values[0][0],
        "last_ts": values[-1][0],
        "coverage_days": (values[-1][0] - values[0][0]) / DAY_MS,
        "non_daily_gap_count": len(gaps),
        "max_gap_days": max(gaps, default=DAY_MS) / DAY_MS,
        "oi_usd_first": values[0][1],
        "oi_usd_last": values[-1][1],
        "daily_change": {
            "count": len(changes),
            "median": median(changes) if changes else 0.0,
            "p05": ordered_changes[max(0, int(len(ordered_changes) * 0.05) - 1)] if ordered_changes else 0.0,
            "p95": ordered_changes[min(len(ordered_changes) - 1, int(len(ordered_changes) * 0.95))] if ordered_changes else 0.0,
            "abs_ge_5pct_events": sum(1 for change in changes if abs(change) >= 0.05),
        },
    }


def audit_paths(paths: list[Path]) -> dict[str, Any]:
    return {path.stem: audit_series(load_oi_usd(path)) for path in paths}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit downloaded OKX daily OI files without generating signals.")
    parser.add_argument("--paths", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/okx_oi_audit.json"))
    args = parser.parse_args(argv)
    report = audit_paths(args.paths)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

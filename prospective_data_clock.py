"""Timestamp-only prospective data accumulation monitor; never reads prices."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market import _parse_timestamp
from prospective_candidate_registry import APPROVAL_GRADE_DAYS, INTERIM_DAYS, PROSPECTIVE_START


BAR_MS = 15 * 60 * 1000


def start_timestamp() -> int:
    return int(datetime.strptime(PROSPECTIVE_START, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def read_timestamps(path: Path) -> list[int]:
    values: list[int] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                values.append(_parse_timestamp(row["timestamp"]))
            except (KeyError, ValueError):
                continue
    return sorted(set(values))


def build_clock(registry: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    symbols = sorted(
        {
            symbol
            for item in registry.get("frozen_candidates", [])
            for symbol in item.get("eligible_symbols", [])
        }
    )
    if not symbols:
        coverage = json.loads(Path("reports/future_window_data_coverage_audit.json").read_text(encoding="utf-8"))
        symbols = sorted(coverage.get("eligible_symbols", []))
    start_ts = start_timestamp()
    timestamps_by_symbol: dict[str, list[int]] = {}
    for symbol in symbols:
        base = symbol.split("-", 1)[0]
        timestamps_by_symbol[symbol] = [ts for ts in read_timestamps(data_dir / f"{base}_15m.csv") if ts >= start_ts]
    latest_by_symbol = {symbol: max(values) if values else 0 for symbol, values in timestamps_by_symbol.items()}
    common_latest = min(latest_by_symbol.values()) if latest_by_symbol and all(latest_by_symbol.values()) else 0
    expected_bars = ((common_latest - start_ts) // BAR_MS + 1) if common_latest >= start_ts else 0
    missing_by_symbol = {
        symbol: expected_bars - sum(start_ts <= ts <= common_latest for ts in values)
        for symbol, values in timestamps_by_symbol.items()
    }
    elapsed_days = (common_latest - start_ts + BAR_MS) / (24 * 60 * 60 * 1000) if common_latest else 0.0
    return {
        "report_type": "prospective_data_clock",
        "report_date": "2026-07-13",
        "scope": "timestamp_only_no_price_or_return_peeking",
        "prospective_start": PROSPECTIVE_START,
        "symbol_count": len(symbols),
        "common_latest_timestamp": datetime.fromtimestamp(common_latest / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S") if common_latest else None,
        "expected_15m_bars_per_symbol": expected_bars,
        "elapsed_days": round(elapsed_days, 6),
        "interim_target_days": INTERIM_DAYS,
        "interim_progress": round(min(elapsed_days / INTERIM_DAYS, 1.0), 6),
        "approval_grade_target_days": APPROVAL_GRADE_DAYS,
        "approval_grade_progress": round(min(elapsed_days / APPROVAL_GRADE_DAYS, 1.0), 6),
        "missing_bars_by_symbol": missing_by_symbol,
        "all_symbols_complete_through_common_latest": all(value == 0 for value in missing_by_symbol.values()),
        "returns_evaluated": False,
        "signals_evaluated": False,
        "safety_gates": {
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Prospective Data Clock",
            "",
            "Date: 2026-07-13",
            "",
            "Timestamp-only monitor. No prices, signals, or returns were evaluated.",
            "",
            f"- prospective start: `{report['prospective_start']}`",
            f"- common latest timestamp: `{report['common_latest_timestamp']}`",
            f"- symbols: {report['symbol_count']}",
            f"- complete 15m bars per symbol: {report['expected_15m_bars_per_symbol']}",
            f"- elapsed: {report['elapsed_days']:.4f} days",
            f"- 90-day interim progress: {report['interim_progress']:.2%}",
            f"- 365-day approval-grade progress: {report['approval_grade_progress']:.2%}",
            f"- complete through common latest: `{str(report['all_symbols_complete_through_common_latest']).lower()}`",
            "- `returns_evaluated = false`",
            "- `signals_evaluated = false`",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Monitor prospective data without looking at prices or results.")
    parser.add_argument("--registry", type=Path, default=Path("reports/prospective_candidate_registry.json"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_data_clock.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/prospective_data_clock_2026-07-13.md"))
    args = parser.parse_args(argv)
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    report = build_clock(registry, args.data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(f"elapsed={report['elapsed_days']:.4f} days; complete={report['all_symbols_complete_through_common_latest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


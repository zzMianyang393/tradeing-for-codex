"""Audit 15m OHLCV readiness for the untouched future validation window."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market import _normalize_timestamp


BAR_MS = 15 * 60 * 1000
TARGET_START = "2025-07-11 00:00:00"
TARGET_END = "2026-07-10 23:45:00"
MIN_COVERAGE_RATIO = 0.995
MAX_SINGLE_GAP_BARS = 16


def parse_timestamp(value: str) -> int:
    stripped = value.strip()
    if stripped.isdigit():
        return _normalize_timestamp(int(stripped))
    return int(datetime.strptime(stripped, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp() * 1000)


def format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def audit_file(path: Path, target_start_ts: int, target_end_ts: int) -> dict[str, Any]:
    first_ts = last_ts = previous_ts = 0
    rows = duplicates = out_of_order = 0
    missing_bars = target_missing_bars = 0
    gap_count = target_gap_count = 0
    max_gap_bars = target_max_gap_bars = 0
    target_gap_preview: list[dict[str, Any]] = []
    target_timestamps: set[int] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = row.get("timestamp_ms") or row.get("timestamp")
            if not raw:
                continue
            try:
                ts = parse_timestamp(raw)
            except ValueError:
                continue
            rows += 1
            if first_ts == 0:
                first_ts = ts
            if previous_ts:
                delta = ts - previous_ts
                if delta == 0:
                    duplicates += 1
                elif delta < 0:
                    out_of_order += 1
                elif delta > BAR_MS:
                    gap_bars = max(0, delta // BAR_MS - 1)
                    missing_bars += gap_bars
                    gap_count += 1
                    max_gap_bars = max(max_gap_bars, gap_bars)
                    if previous_ts <= target_end_ts and ts >= target_start_ts:
                        overlap_start = max(previous_ts + BAR_MS, target_start_ts)
                        overlap_end = min(ts - BAR_MS, target_end_ts)
                        overlap_missing = max(0, (overlap_end - overlap_start) // BAR_MS + 1) if overlap_end >= overlap_start else 0
                        if overlap_missing:
                            target_missing_bars += overlap_missing
                            target_gap_count += 1
                            target_max_gap_bars = max(target_max_gap_bars, overlap_missing)
                            if len(target_gap_preview) < 10:
                                target_gap_preview.append(
                                    {
                                        "after_timestamp_utc": format_utc(previous_ts),
                                        "before_timestamp_utc": format_utc(ts),
                                        "missing_bars": overlap_missing,
                                    }
                                )
            previous_ts = ts
            last_ts = ts
            if target_start_ts <= ts <= target_end_ts:
                target_timestamps.add(ts)

    expected_target_rows = (target_end_ts - target_start_ts) // BAR_MS + 1
    target_rows = len(target_timestamps)
    coverage_ratio = target_rows / expected_target_rows if expected_target_rows > 0 else 0.0
    eligible = (
        first_ts <= target_start_ts
        and last_ts >= target_end_ts
        and coverage_ratio >= MIN_COVERAGE_RATIO
        and target_max_gap_bars <= MAX_SINGLE_GAP_BARS
        and out_of_order == 0
    )
    return {
        "symbol": f"{path.stem.removesuffix('_15m')}-USDT-SWAP",
        "path": str(path),
        "rows": rows,
        "first_ts": first_ts,
        "first_timestamp_utc": format_utc(first_ts) if first_ts else "",
        "last_ts": last_ts,
        "last_timestamp_utc": format_utc(last_ts) if last_ts else "",
        "duplicates": duplicates,
        "out_of_order": out_of_order,
        "gap_count": gap_count,
        "missing_bars": missing_bars,
        "max_gap_bars": max_gap_bars,
        "target_rows": target_rows,
        "expected_target_rows": expected_target_rows,
        "target_coverage_ratio": round(coverage_ratio, 6),
        "target_gap_count": target_gap_count,
        "target_missing_bars": target_missing_bars,
        "target_max_gap_bars": target_max_gap_bars,
        "target_gap_preview": target_gap_preview,
        "future_window_eligible": eligible,
    }


def build_report(data_dir: Path, target_start: str = TARGET_START, target_end: str = TARGET_END) -> dict[str, Any]:
    start_ts = parse_timestamp(target_start)
    end_ts = parse_timestamp(target_end)
    files = sorted(data_dir.glob("*_15m.csv"))
    records = [audit_file(path, start_ts, end_ts) for path in files]
    eligible = sorted(record["symbol"] for record in records if record["future_window_eligible"])
    blocked = sorted(record["symbol"] for record in records if not record["future_window_eligible"])
    common_latest = min((int(record["last_ts"]) for record in records), default=0)
    common_earliest = max((int(record["first_ts"]) for record in records), default=0)
    return {
        "report_type": "future_window_data_coverage_audit",
        "report_date": "2026-07-13",
        "target_window": {
            "start": target_start,
            "end": target_end,
            "expected_15m_rows": (end_ts - start_ts) // BAR_MS + 1,
            "days": round((end_ts - start_ts + BAR_MS) / 86_400_000, 6),
        },
        "requirements": {
            "minimum_coverage_ratio": MIN_COVERAGE_RATIO,
            "maximum_single_gap_bars": MAX_SINGLE_GAP_BARS,
            "out_of_order_allowed": False,
        },
        "symbols_total": len(records),
        "eligible_symbols": eligible,
        "blocked_symbols": blocked,
        "eligible_symbol_count": len(eligible),
        "all_frozen_universe_ready": bool(records) and not blocked,
        "common_file_coverage": {
            "earliest_common_start": format_utc(common_earliest) if common_earliest else "",
            "latest_common_end": format_utc(common_latest) if common_latest else "",
        },
        "records": records,
        "safety_gates": {
            "future_validation_executed": False,
            "validated": False,
            "approved_for_paper": [],
            "safe_to_enable_trading": False,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    target = report["target_window"]
    lines = [
        "# Future Window 15m Data Coverage Audit",
        "",
        "Date: 2026-07-13",
        "",
        f"Target untouched window: `{target['start']}` through `{target['end']}` ({target['days']:.0f} days).",
        "",
        f"Eligible symbols: {report['eligible_symbol_count']} / {report['symbols_total']}",
        "",
        "| Symbol | First | Last | Target Rows | Coverage | Target Gaps | Max Gap Bars | Eligible |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["records"]:
        lines.append(
            f"| `{item['symbol']}` | {item['first_timestamp_utc']} | {item['last_timestamp_utc']} | "
            f"{item['target_rows']} | {item['target_coverage_ratio']:.2%} | {item['target_gap_count']} | "
            f"{item['target_max_gap_bars']} | {'yes' if item['future_window_eligible'] else 'no'} |"
        )
    lines.extend(
        [
            "",
            "## Current Gate",
            "",
            f"- all frozen-universe symbols ready: `{str(report['all_frozen_universe_ready']).lower()}`",
            f"- blocked symbols: {', '.join(report['blocked_symbols']) if report['blocked_symbols'] else 'none'}",
            f"- latest common file timestamp: {report['common_file_coverage']['latest_common_end']}",
            "- future validation has not yet executed",
            "- `validated = false`",
            "- `approved_for_paper = []`",
            "- `safe_to_enable_trading = false`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit untouched future-window 15m data coverage.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--start", default=TARGET_START)
    parser.add_argument("--end", default=TARGET_END)
    parser.add_argument("--out", type=Path, default=Path("reports/future_window_data_coverage_audit.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/future_window_data_coverage_audit_2026-07-13.md"))
    args = parser.parse_args(argv)
    report = build_report(args.data, args.start, args.end)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(
        f"eligible={report['eligible_symbol_count']}/{report['symbols_total']}; "
        f"blocked={','.join(report['blocked_symbols']) or 'none'}; "
        f"all_ready={report['all_frozen_universe_ready']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import csv

from future_window_data_coverage_audit import BAR_MS, audit_file, build_report


def _write(path, timestamps: list[int]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for ts in timestamps:
            writer.writerow([str(ts), "1", "1", "1", "1", "1"])


def test_audit_file_accepts_complete_target_window(tmp_path):
    start = 1_750_000_000_000
    path = tmp_path / "BTC_15m.csv"
    _write(path, [start, start + BAR_MS, start + 2 * BAR_MS])

    result = audit_file(path, start, start + 2 * BAR_MS)

    assert result["target_coverage_ratio"] == 1.0
    assert result["target_gap_count"] == 0
    assert result["future_window_eligible"] is True


def test_audit_file_reports_missing_target_bars(tmp_path):
    start = 1_750_000_000_000
    path = tmp_path / "ETH_15m.csv"
    _write(path, [start, start + 2 * BAR_MS])

    result = audit_file(path, start, start + 2 * BAR_MS)

    assert result["target_missing_bars"] == 1
    assert result["target_gap_preview"][0]["missing_bars"] == 1
    assert result["target_coverage_ratio"] < 1.0
    assert result["future_window_eligible"] is False


def test_audit_file_reports_duplicates_and_out_of_order(tmp_path):
    start = 1_750_000_000_000
    path = tmp_path / "SOL_15m.csv"
    _write(path, [start, start, start - BAR_MS, start + BAR_MS])

    result = audit_file(path, start - BAR_MS, start + BAR_MS)

    assert result["duplicates"] == 1
    assert result["out_of_order"] == 1
    assert result["future_window_eligible"] is False


def test_build_report_keeps_future_validation_closed(tmp_path):
    start = 1_750_000_000_000
    path = tmp_path / "BTC_15m.csv"
    _write(path, [start, start + BAR_MS])

    report = build_report(tmp_path, "2025-06-15 15:06:40", "2025-06-15 15:21:40")

    assert report["symbols_total"] == 1
    assert report["safety_gates"]["future_validation_executed"] is False
    assert report["safety_gates"]["validated"] is False
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False

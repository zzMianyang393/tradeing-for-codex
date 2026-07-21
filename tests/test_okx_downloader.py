from __future__ import annotations

import csv

import okx_downloader
from okx_downloader import (
    output_path,
    parse_timestamp_ms,
    read_existing_rows,
    repair_symbol_range,
    write_rows,
)


def test_parse_timestamp_ms_accepts_space_and_iso_t_formats():
    expected = 1_769_476_500_000
    assert parse_timestamp_ms("2026-01-27 01:15:00") == expected
    assert parse_timestamp_ms("2026-01-27T01:15:00") == expected


def test_15m_output_path_matches_existing_quantify_files(tmp_path):
    assert output_path("BTC-USDT-SWAP", tmp_path, "15m") == tmp_path / "BTC_15m.csv"


def test_read_and_write_15m_rows_preserve_existing_timestamps(tmp_path):
    path = tmp_path / "BTC_15m.csv"
    rows = [
        ["1750000000000", "1", "2", "0.5", "1.5", "10", "10", "15"],
        ["1750000900000", "1.5", "2.5", "1", "2", "12", "12", "24"],
    ]
    write_rows(path, rows, "15m")

    loaded = read_existing_rows(path, "15m")

    assert sorted(loaded) == [1_750_000_000_000, 1_750_000_900_000]
    assert loaded[1_750_000_000_000][1:5] == ["1", "2", "0.5", "1.5"]


def test_write_rows_sorts_are_controlled_by_caller_without_truncating_fields(tmp_path):
    path = tmp_path / "ETH_15m.csv"
    rows = [["1750000000000", "1", "2", "0.5", "1.5", "10", "11", "12"]]

    write_rows(path, rows, "15m")

    with path.open("r", encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert len(written) == 1
    assert written[0]["timestamp"] == "2025-06-15 15:06:40"
    assert written[0]["volume"] == "11"


def test_repair_symbol_range_merges_only_internal_gap(monkeypatch, tmp_path):
    start = 1_750_000_000_000
    step = 15 * 60 * 1000
    path = tmp_path / "BTC_15m.csv"
    existing = [
        [str(start), "1", "1", "1", "1", "1", "1", "1"],
        [str(start + 4 * step), "1", "1", "1", "1", "1", "1", "1"],
    ]
    write_rows(path, existing, "15m")
    page = [
        [str(start + 3 * step), "1", "1", "1", "1", "1", "1", "1"],
        [str(start + 2 * step), "1", "1", "1", "1", "1", "1", "1"],
        [str(start + step), "1", "1", "1", "1", "1", "1", "1"],
    ]
    monkeypatch.setattr(okx_downloader, "fetch_page_with_retry", lambda *args, **kwargs: page)

    result = repair_symbol_range(
        "BTC-USDT-SWAP",
        start,
        start + 4 * step,
        tmp_path,
        sleep_seconds=0.0,
    )

    assert result["added_rows"] == 3
    assert sorted(read_existing_rows(path, "15m")) == [start + index * step for index in range(5)]

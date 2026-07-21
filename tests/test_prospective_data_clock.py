import csv

from prospective_data_clock import BAR_MS, build_clock, start_timestamp


def write_symbol(path, timestamps):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp"])
        writer.writeheader()
        for ts in timestamps:
            from datetime import datetime, timezone

            writer.writerow({"timestamp": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")})


def test_clock_reads_only_frozen_symbol_timestamps(tmp_path):
    start = start_timestamp()
    timestamps = [start + index * BAR_MS for index in range(4)]
    write_symbol(tmp_path / "BTC_15m.csv", timestamps)
    write_symbol(tmp_path / "ETH_15m.csv", timestamps)
    registry = {
        "frozen_candidates": [
            {"eligible_symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]}
        ]
    }
    report = build_clock(registry, tmp_path)
    assert report["symbol_count"] == 2
    assert report["expected_15m_bars_per_symbol"] == 4
    assert report["all_symbols_complete_through_common_latest"] is True
    assert report["returns_evaluated"] is False


def test_clock_reports_internal_missing_bar(tmp_path):
    start = start_timestamp()
    complete = [start + index * BAR_MS for index in range(4)]
    write_symbol(tmp_path / "BTC_15m.csv", complete)
    write_symbol(tmp_path / "ETH_15m.csv", [complete[0], complete[2], complete[3]])
    registry = {
        "frozen_candidates": [
            {"eligible_symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]}
        ]
    }
    report = build_clock(registry, tmp_path)
    assert report["missing_bars_by_symbol"]["ETH-USDT-SWAP"] == 1
    assert report["all_symbols_complete_through_common_latest"] is False

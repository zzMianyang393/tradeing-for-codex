from __future__ import annotations

import csv
from datetime import datetime, timezone

import pytest

from okx_incremental_15m_refresh import BAR_MS, build_plan, completed_new_rows, plan_symbol, ts_from_text


def remote(ts: int, confirmed="1"):
    return [str(ts), "1", "2", "0.5", "1.5", "10", "20", "30", confirmed]


def write_csv(path, timestamps):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for ts in timestamps:
            timestamp = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            writer.writerow({"timestamp": timestamp, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 20})


def test_completed_rows_exclude_open_candle():
    rows = completed_new_rows([remote(BAR_MS), remote(2 * BAR_MS, "0")], 0)
    assert len(rows) == 1
    assert ts_from_text(rows[0]["timestamp"]) == BAR_MS


def test_plan_rejects_internal_gap(tmp_path):
    write_csv(tmp_path / "BTC_15m.csv", [0, BAR_MS])
    with pytest.raises(ValueError, match="non-contiguous"):
        plan_symbol("BTC-USDT-SWAP", tmp_path, lambda *_args, **_kwargs: [remote(3 * BAR_MS)])


def test_dry_run_plan_does_not_write(tmp_path):
    write_csv(tmp_path / "BTC_15m.csv", [0, BAR_MS])
    before = (tmp_path / "BTC_15m.csv").read_bytes()
    report = build_plan(tmp_path, ["BTC-USDT-SWAP"], lambda *_args, **_kwargs: [remote(2 * BAR_MS)])
    assert report["total_append_count"] == 1
    assert report["committed"] is False
    assert (tmp_path / "BTC_15m.csv").read_bytes() == before


def test_parallel_plan_preserves_input_symbol_order(tmp_path):
    write_csv(tmp_path / "BTC_15m.csv", [0, BAR_MS])
    write_csv(tmp_path / "ETH_15m.csv", [0, BAR_MS])
    report = build_plan(
        tmp_path,
        ["ETH-USDT-SWAP", "BTC-USDT-SWAP"],
        lambda *_args, **_kwargs: [remote(2 * BAR_MS)],
        workers=2,
    )
    assert [item["symbol"] for item in report["symbols"]] == ["ETH-USDT-SWAP", "BTC-USDT-SWAP"]
    assert report["total_append_count"] == 2


def test_plan_rejects_zero_workers(tmp_path):
    write_csv(tmp_path / "BTC_15m.csv", [0, BAR_MS])
    with pytest.raises(ValueError, match="workers"):
        build_plan(tmp_path, ["BTC-USDT-SWAP"], workers=0)

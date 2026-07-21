from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from okx_futures_calendar_spread_pipeline import parse_utc_ms
from okx_futures_calendar_spread_series import write_spread_series


def _write_csv(path: Path, instrument: str, rows: list[tuple[int, float]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["timestamp_ms", "timestamp_utc", "instrument_name", "open", "high", "low", "close", "volume_quote"])
        writer.writeheader()
        for ts, close in rows:
            writer.writerow({
                "timestamp_ms": ts,
                "timestamp_utc": "",
                "instrument_name": instrument,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume_quote": "1",
            })


class OkxFuturesCalendarSpreadSeriesTests(unittest.TestCase):
    def test_writes_spread_first_series_without_stitching_old_future(self):
        ts1 = parse_utc_ms("2024-09-24 07:59:00")
        ts2 = parse_utc_ms("2024-09-24 08:00:00")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_csv(root / "BTC-USDT-240927_future_1m.csv", "BTC-USDT-240927", [(ts1, 101.0), (ts2, 999.0)])
            _write_csv(root / "BTC-USDT-241227_future_1m.csv", "BTC-USDT-241227", [(ts2, 103.0)])
            _write_csv(root / "BTC-USDT_swap_1m.csv", "BTC-USDT-SWAP", [(ts1, 100.0), (ts2, 100.0)])
            metadata = write_spread_series("BTC-USDT", root, root / "BTC-USDT_swap_1m.csv", root / "spread.csv")
            with (root / "spread.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            stored_metadata = json.loads((root / "spread.meta.json").read_text(encoding="utf-8"))
        self.assertEqual(2, metadata["rows"])
        self.assertEqual("spread_first_no_futures_price_stitching", stored_metadata["construction"])
        self.assertEqual(["BTC-USDT-240927", "BTC-USDT-241227"], [row["future_inst_id"] for row in rows])
        self.assertEqual(["1.0000000000", "3.0000000000"], [row["spread_abs"] for row in rows])


if __name__ == "__main__":
    unittest.main()

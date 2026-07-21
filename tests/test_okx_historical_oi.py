from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from okx_historical_oi import download_daily_oi, fetch_oi_page, parse_oi_rows


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class OkxHistoricalOiTests(unittest.TestCase):
    def test_fetches_daily_page_for_specific_swap(self):
        seen = []
        def open_url(request, **_kwargs):
            seen.append(request.full_url)
            return _Response(b'{"code":"0","data":[]}')
        with patch("okx_historical_oi.urllib.request.urlopen", side_effect=open_url):
            self.assertEqual([], fetch_oi_page("BTC-USDT-SWAP", limit=10))
        self.assertIn("instId=BTC-USDT-SWAP", seen[0])
        self.assertIn("period=1D", seen[0])

    def test_parses_oi_usd_field(self):
        record = parse_oi_rows("BTC-USDT-SWAP", [["1720569600000", "1", "2", "3"]])[0]
        self.assertEqual(3.0, record.open_interest_usd)

    def test_paginates_backwards_and_writes_metadata(self):
        first = [["1720742400000", "3", "3", "30"], ["1720656000000", "2", "2", "20"]]
        second = [["1720569600000", "1", "1", "10"]]
        with tempfile.TemporaryDirectory() as tmp, patch(
            "okx_historical_oi.fetch_oi_page", side_effect=[first, second]
        ) as fetch:
            metadata = download_daily_oi("BTC-USDT-SWAP", date(2024, 7, 10), date(2024, 7, 12), Path(tmp), limit=2)
            path = Path(tmp) / "BTC-USDT-SWAP_open_interest_1d.csv"
            with path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(3, metadata["rows"])
        self.assertEqual(2, metadata["pages"])
        self.assertEqual(1720655999999, fetch.call_args_list[1].kwargs["end"])
        self.assertEqual(["10.0", "20.0", "30.0"], [row["open_interest_usd"] for row in rows])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binance_funding_rate import download_history, parse_rows, save_history


def _row(ts: int) -> dict[str, str]:
    return {"symbol": "BTCUSDT", "fundingTime": str(ts), "fundingRate": "0.0001", "markPrice": "50000"}


class BinanceFundingRateTests(unittest.TestCase):
    def test_parse_rows_orders_and_skips_invalid_values(self):
        rows = parse_rows([_row(2), {"fundingTime": "bad"}, _row(1)])
        self.assertEqual([1, 2], [row.ts for row in rows])

    def test_download_history_advances_cursor_after_last_funding_time(self):
        first_page = [_row(index * 100) for index in range(1, 1001)]
        with patch("binance_funding_rate.fetch_funding_page", side_effect=[first_page, [_row(100_100)]]) as fetch:
            rows = download_history("BTCUSDT", 0, 200_000, sleep_seconds=0)
        self.assertEqual([100, 100_000, 100_100], [row.ts for row in (rows[0], rows[-2], rows[-1])])
        self.assertEqual(2, fetch.call_count)
        self.assertEqual(("BTCUSDT", 0, 200_000), fetch.call_args_list[0].args)
        self.assertEqual(("BTCUSDT", 100_001, 200_000), fetch.call_args_list[1].args)

    def test_save_history_writes_proxy_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTCUSDT_binance_funding.csv"
            save_history(path, parse_rows([_row(100)]), 0, 200)
            metadata = path.with_suffix(".meta.json").read_text(encoding="utf-8")
        self.assertIn("research_proxy_only_not_okx_execution", metadata)


if __name__ == "__main__":
    unittest.main()

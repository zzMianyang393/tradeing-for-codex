from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from market import FeatureBar
from open_interest import (
    OpenInterest,
    add_open_interest_features,
    download_open_interest,
    fetch_open_interest_history,
    load_open_interest,
    main,
    parse_open_interest_rows,
    save_open_interest,
)


class TestOpenInterest(unittest.TestCase):
    def test_parse_okx_open_interest_rows(self):
        rows = parse_open_interest_rows(
            "BTC-USDT-SWAP",
            [
                {
                    "ts": "1700000000000",
                    "oi": "12345.6",
                    "oiCcy": "321.5",
                }
            ],
        )

        self.assertEqual(1, len(rows))
        self.assertEqual("BTC-USDT-SWAP", rows[0].symbol)
        self.assertEqual(1_700_000_000_000, rows[0].ts)
        self.assertAlmostEqual(12345.6, rows[0].open_interest)
        self.assertAlmostEqual(321.5, rows[0].open_interest_currency)

    def test_parse_okx_open_interest_array_rows(self):
        rows = parse_open_interest_rows(
            "BTC-USDT-SWAP",
            [["1700000000000", "12345.6", "321.5"]],
        )

        self.assertEqual(1, len(rows))
        self.assertEqual(1_700_000_000_000, rows[0].ts)
        self.assertAlmostEqual(12345.6, rows[0].open_interest)
        self.assertAlmostEqual(321.5, rows[0].open_interest_currency)

    def test_fetch_open_interest_history_queries_instrument_id(self):
        response = MagicMock()
        response.read.return_value = b'{"code":"0","data":[]}'
        response.__enter__.return_value = response

        with patch("open_interest.urllib.request.urlopen", return_value=response) as urlopen:
            fetch_open_interest_history("BTC-USDT-SWAP", period="15m", limit=5)

        request = urlopen.call_args.args[0]
        self.assertIn("instId=BTC-USDT-SWAP", request.full_url)

    def test_save_and_load_open_interest(self):
        items = [
            OpenInterest(
                symbol="BTC-USDT-SWAP",
                ts=1_700_000_000_000,
                time="2023-11-14 22:13:20",
                open_interest=100.0,
                open_interest_currency=2.0,
            )
        ]

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BTC-USDT-SWAP_open_interest.csv"
            save_open_interest(path, items)
            loaded = load_open_interest(path)

        self.assertEqual(items, loaded)

    def test_add_open_interest_features_uses_latest_known_value(self):
        bars = [
            FeatureBar(ts=1000, time="t1", open=1, high=1, low=1, close=1, volume_quote=1),
            FeatureBar(ts=2000, time="t2", open=1, high=1, low=1, close=1, volume_quote=1),
            FeatureBar(ts=3000, time="t3", open=1, high=1, low=1, close=1, volume_quote=1),
        ]
        items = [
            OpenInterest("BTC-USDT-SWAP", 1500, "oi1", 100.0, 10.0),
            OpenInterest("BTC-USDT-SWAP", 2500, "oi2", 120.0, 12.0),
        ]

        enriched = add_open_interest_features(bars, items)

        self.assertEqual(0.0, enriched[0].open_interest)
        self.assertEqual(100.0, enriched[1].open_interest)
        self.assertEqual(120.0, enriched[2].open_interest)
        self.assertAlmostEqual(0.2, enriched[2].open_interest_change_pct)
        self.assertAlmostEqual(110.0, enriched[2].open_interest_ma)

    def test_download_open_interest_merges_existing_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            existing = [
                OpenInterest("BTC-USDT-SWAP", 1_700_000_000_000, "old", 100.0, 10.0),
            ]
            save_open_interest(out_dir / "BTC-USDT-SWAP_open_interest.csv", existing)
            page = [
                {"ts": "1700000900000", "oi": "110", "oiCcy": "11"},
                {"ts": "1700001800000", "oi": "120", "oiCcy": "12"},
            ]

            with patch("open_interest.fetch_open_interest_history", return_value=page) as fetch:
                count = download_open_interest(
                    "BTC-USDT-SWAP",
                    days=1,
                    out_dir=out_dir,
                    period="15m",
                )

            self.assertEqual(3, count)
            fetch.assert_called_once()
            loaded = load_open_interest(out_dir / "BTC-USDT-SWAP_open_interest.csv")
            self.assertEqual(
                [1_700_000_000_000, 1_700_000_900_000, 1_700_001_800_000],
                [item.ts for item in loaded],
            )

    def test_main_downloads_requested_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            page = [{"ts": "1700000000000", "oi": "110", "oiCcy": "11"}]

            with patch("open_interest.fetch_open_interest_history", return_value=page):
                code = main([
                    "--symbols",
                    "BTC-USDT-SWAP",
                    "--days",
                    "1",
                    "--out",
                    str(out_dir),
                ])

            self.assertEqual(0, code)
            self.assertEqual(1, len(load_open_interest(out_dir / "BTC-USDT-SWAP_open_interest.csv")))


if __name__ == "__main__":
    unittest.main()

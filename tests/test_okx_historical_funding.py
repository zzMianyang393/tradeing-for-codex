from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from okx_historical_funding import download_funding_archive, download_funding_history, list_funding_archives


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _zip_payload() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "BTC-USDT-SWAP-fundingrates-2025-09.csv",
            "instrument_name,funding_rate,funding_time\nBTC-USDT-SWAP,0.0001,1756656000000\n",
        )
    return output.getvalue()


class OkxHistoricalFundingTests(unittest.TestCase):
    def test_manifest_flattens_archive_entries(self):
        payload = {"code": "0", "data": [{"details": [{"groupDetails": [{"filename": "a.zip", "url": "https://example/a", "dateTs": "2"}]}]}]}
        seen_urls = []
        def open_url(request, **_kwargs):
            seen_urls.append(request.full_url)
            return _Response(json.dumps(payload).encode())
        with patch("okx_historical_funding.urllib.request.urlopen", side_effect=open_url):
            archives = list_funding_archives("BTC-USDT-SWAP", date(2025, 9, 1), date(2025, 9, 30))
        self.assertEqual("a.zip", archives[0]["filename"])
        self.assertIn("instFamilyList=BTC-USDT", seen_urls[0])

    def test_manifest_paginates_and_deduplicates_calendar_overlap(self):
        archive = {"filename": "a.zip", "url": "https://example/a", "dateTs": "2"}
        with patch("okx_historical_funding._list_funding_archives_page", return_value=[archive]) as fetch:
            archives = list_funding_archives("BTC-USDT-SWAP", date(2024, 1, 1), date(2024, 5, 1))
        self.assertGreater(fetch.call_count, 1)
        self.assertEqual([archive], archives)

    def test_archive_normalizes_to_existing_funding_format(self):
        with patch("okx_historical_funding.urllib.request.urlopen", return_value=_Response(_zip_payload())):
            records = download_funding_archive("https://example/archive.zip")
        self.assertEqual("BTC-USDT-SWAP", records[0].symbol)
        self.assertEqual(1756656000000, records[0].ts)

    def test_download_merges_archives_and_writes_provenance(self):
        archives = [{"filename": "a.zip", "url": "https://example/a", "dateTs": "1756656000000"}]
        with tempfile.TemporaryDirectory() as tmp:
            with patch("okx_historical_funding.list_funding_archives", return_value=archives), patch(
                "okx_historical_funding.download_funding_archive",
                return_value=download_funding_archive_from_fixture(),
            ):
                metadata = download_funding_history("BTC-USDT-SWAP", date(2025, 8, 31), date(2025, 9, 2), Path(tmp))
            stored = json.loads((Path(tmp) / "BTC-USDT-SWAP_funding.meta.json").read_text(encoding="utf-8"))
        self.assertEqual("okx_execution_compatible", metadata["execution_compatibility"])
        self.assertEqual(1, metadata["rows"])
        self.assertEqual(metadata, stored)

    def test_empty_manifest_fails_instead_of_writing_misleading_metadata(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "okx_historical_funding.list_funding_archives", return_value=[]
        ):
            with self.assertRaisesRegex(RuntimeError, "No OKX historical funding archives"):
                download_funding_history("BTC-USDT-SWAP", date(2025, 9, 1), date(2025, 9, 2), Path(tmp))


def download_funding_archive_from_fixture():
    from funding_rate import FundingRate
    return [FundingRate("BTC-USDT-SWAP", 1756656000000, "2025-09-02 00:00:00", 0.0001, 0.0001)]


if __name__ == "__main__":
    unittest.main()

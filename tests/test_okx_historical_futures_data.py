from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from okx_historical_futures_data import download_futures_archive, download_futures_family, list_futures_archives


def _zip_payload() -> bytes:
    output = io.BytesIO()
    rows = "\n".join(
        [
            "instrument_name,open,high,low,close,vol_quote,open_time,confirm",
            "BTC-USDT-240927,1,2,0.5,1.5,100,1720656000000,1",
            "BTC-USDT-241227,2,3,1.5,2.5,200,1720656000000,1",
            "BTC-USDT-240927,9,9,9,9,900,1720656900000,0",
            "BTC-USDT-240927,8,8,8,8,800,1720569600000,1",
            "",
        ]
    )
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("BTC-USDT-futures.csv", rows)
    return output.getvalue()


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class OkxHistoricalFuturesDataTests(unittest.TestCase):
    def test_manifest_uses_futures_family_module_two(self):
        seen = []
        payload = {"code": "0", "data": [{"details": [{"groupDetails": [{"url": "https://example/a", "dateTs": "1"}]}]}]}

        def open_url(request, **_kwargs):
            seen.append(request.full_url)
            return _Response(json.dumps(payload).encode())

        with patch("okx_historical_futures_data.urllib.request.urlopen", side_effect=open_url):
            list_futures_archives("BTC-USDT", date(2025, 9, 1), date(2025, 9, 2))
        self.assertIn("module=2", seen[0])
        self.assertIn("instType=FUTURES", seen[0])
        self.assertIn("instFamilyList=BTC-USDT", seen[0])
        self.assertNotIn("instIdList", seen[0])

    def test_archive_parser_filters_complete_rows_range_and_contracts(self):
        with patch("okx_historical_futures_data.urllib.request.urlopen", return_value=_Response(_zip_payload())):
            rows = download_futures_archive(
                "https://example/a",
                date(2024, 7, 11),
                date(2024, 7, 11),
                contract_ids=["BTC-USDT-240927"],
            )
        self.assertEqual(1, len(rows))
        self.assertEqual("BTC-USDT-240927", rows[0].instrument_name)
        self.assertEqual("1.5", rows[0].close)
        self.assertEqual("2024-07-11 00:00:00", rows[0].timestamp_utc)

    def test_download_family_writes_per_contract_files_and_manifest(self):
        archive = {"url": "https://example/a", "dateTs": "1", "filename": "a.zip"}
        with tempfile.TemporaryDirectory() as tmp, patch("okx_historical_futures_data.list_futures_archives", return_value=[archive]), patch(
            "okx_historical_futures_data.urllib.request.urlopen", return_value=_Response(_zip_payload())
        ):
            manifest = download_futures_family("BTC-USDT", date(2024, 7, 11), date(2024, 7, 11), Path(tmp))
            with (Path(tmp) / "BTC-USDT-240927_future_1m.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            metadata = json.loads((Path(tmp) / "BTC-USDT-240927_future_1m.meta.json").read_text(encoding="utf-8"))
            manifest_payload = json.loads((Path(tmp) / "BTC-USDT_futures_1m_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(manifest["contracts"]))
        self.assertEqual("okx_execution_compatible", metadata["execution_compatibility"])
        self.assertEqual("FUTURES", metadata["inst_type"])
        self.assertEqual("1.5", rows[0]["close"])
        self.assertEqual("okx_execution_compatible", manifest_payload["execution_compatibility"])


if __name__ == "__main__":
    unittest.main()

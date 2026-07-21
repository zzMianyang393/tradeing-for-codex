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

from okx_historical_basis_data import download_leg, list_candle_archives


def _zip_payload() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("BTC-USDT-candlesticks.csv", "instrument_name,open,high,low,close,vol_quote,open_time,confirm\nBTC-USDT,1,2,0.5,1.5,100,1720656000000,1\n")
    return output.getvalue()


class _Response:
    def __init__(self, payload: bytes): self.payload = payload
    def read(self) -> bytes: return self.payload
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class OkxHistoricalBasisDataTests(unittest.TestCase):
    def test_spot_manifest_uses_instrument_id_list(self):
        seen = []
        payload = {"code": "0", "data": [{"details": [{"groupDetails": [{"url": "https://example/a", "dateTs": "1"}]}]}]}
        def open_url(request, **_kwargs):
            seen.append(request.full_url)
            return _Response(json.dumps(payload).encode())
        with patch("okx_historical_basis_data.urllib.request.urlopen", side_effect=open_url):
            list_candle_archives("BTC-USDT", "SPOT", date(2025, 9, 1), date(2025, 9, 2))
        self.assertIn("instIdList=BTC-USDT", seen[0])

    def test_downloads_and_normalizes_complete_rows(self):
        archive = {"url": "https://example/a", "dateTs": "1", "filename": "a.zip"}
        with tempfile.TemporaryDirectory() as tmp, patch("okx_historical_basis_data.list_candle_archives", return_value=[archive]), patch(
            "okx_historical_basis_data.urllib.request.urlopen", return_value=_Response(_zip_payload())
        ):
            metadata = download_leg("BTC-USDT", "SPOT", date(2024, 7, 11), date(2024, 7, 11), Path(tmp))
            with (Path(tmp) / "BTC-USDT_spot_1m.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
        self.assertEqual(1, metadata["rows"])
        self.assertEqual("1.5", rows[0]["close"])


if __name__ == "__main__":
    unittest.main()

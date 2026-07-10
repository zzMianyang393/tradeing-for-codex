from __future__ import annotations

import unittest
from types import SimpleNamespace

from funding_proxy_strategy import EIGHT_HOURS_MS, build_funding_crowding_reversal_provider


class FundingProxyStrategyTests(unittest.TestCase):
    def test_fades_positive_crowding_after_same_way_price_move(self):
        bars = [SimpleNamespace(ts=index * 900_000, close=100.0) for index in range(97)]
        bars[-1] = SimpleNamespace(ts=96 * 900_000, close=104.0)
        bucket = bars[-1].ts // EIGHT_HOURS_MS
        provider = build_funding_crowding_reversal_provider({
            "BTC-USDT-SWAP": {bucket - 2: 0.0004, bucket - 1: 0.0004, bucket: 0.0004}
        })

        signal = provider("BTC-USDT-SWAP", bars, len(bars) - 1)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(-1, signal.direction)
        self.assertEqual("candidate_funding_crowding_reversal", signal.reason)


if __name__ == "__main__":
    unittest.main()

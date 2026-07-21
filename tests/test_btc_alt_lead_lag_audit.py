from __future__ import annotations

import unittest

from btc_alt_lead_lag_audit import LeadLagSpec, audit_btc_alt_lead_lag
from market import FeatureBar


def _bar(index: int, close: float, volume: float = 100.0) -> FeatureBar:
    return FeatureBar(
        ts=index * 900_000,
        time=str(index),
        open=close,
        high=close * 1.01,
        low=close * 0.99,
        close=close,
        volume_quote=volume,
        ema20=close,
        atr_pct=0.01,
    )


class BtcAltLeadLagAuditTests(unittest.TestCase):
    def test_records_delayed_alt_after_btc_impulse(self):
        btc = [_bar(index, 100.0, 100.0) for index in range(35)]
        alt = [_bar(index, 100.0, 100.0) for index in range(35)]
        btc[20] = _bar(20, 103.0, 300.0)
        alt[20] = _bar(20, 101.0, 100.0)
        alt[21] = _bar(21, 101.0, 100.0)
        alt[25] = _bar(25, 103.0, 100.0)
        report = audit_btc_alt_lead_lag(
            {"BTC-USDT-SWAP": btc, "ALT-USDT-SWAP": alt},
            LeadLagSpec(impulse_bars=4, forward_bars=4, cooldown_bars=4, volume_lookback_bars=8),
            round_trip_cost=0.0014,
        )
        self.assertEqual(1, report["overall"]["events"])
        self.assertGreater(report["overall"]["avg_net_return"], 0.0)

    def test_rejects_alt_that_already_fully_followed_btc(self):
        btc = [_bar(index, 100.0, 100.0) for index in range(35)]
        alt = [_bar(index, 100.0, 100.0) for index in range(35)]
        btc[20] = _bar(20, 103.0, 300.0)
        alt[20] = _bar(20, 103.0, 100.0)
        report = audit_btc_alt_lead_lag(
            {"BTC-USDT-SWAP": btc, "ALT-USDT-SWAP": alt},
            LeadLagSpec(impulse_bars=4, forward_bars=4, cooldown_bars=4, volume_lookback_bars=8),
        )
        self.assertEqual(0, report["overall"]["events"])


if __name__ == "__main__":
    unittest.main()

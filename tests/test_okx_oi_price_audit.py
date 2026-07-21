from __future__ import annotations

import unittest

from okx_oi_price_audit import audit_symbol


class OkxOiPriceAuditTests(unittest.TestCase):
    def test_waits_until_following_day_open_before_measuring_returns(self):
        price = {
            "2024-01-01": (100.0, 100.0),
            "2024-01-02": (100.0, 110.0),
            "2024-01-03": (100.0, 105.0),
            "2024-01-04": (105.0, 115.0),
            "2024-01-05": (115.0, 120.0),
            "2024-01-06": (120.0, 121.0),
        }
        oi = {
            "2024-01-01": 100.0,
            "2024-01-02": 100.0,
            "2024-01-03": 110.0,
            "2024-01-04": 110.0,
            "2024-01-05": 110.0,
            "2024-01-06": 110.0,
        }
        report = audit_symbol(price, oi)
        bucket = report["one_day"]["oi_up_price_down"]
        self.assertEqual(1, bucket["events"])
        self.assertAlmostEqual(115.0 / 105.0 - 1.0, bucket["mean_return_pct"] / 100.0)


if __name__ == "__main__":
    unittest.main()

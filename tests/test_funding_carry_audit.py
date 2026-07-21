from __future__ import annotations

import unittest

from funding_carry_audit import BAR_MS, CarrySpec, audit_positive_funding_carry
from funding_rate import FundingRate


def _rate(index: int, value: float) -> FundingRate:
    return FundingRate("BTC-USDT-SWAP", index * 8 * 60 * 60 * 1000, str(index), value, value)


class FundingCarryAuditTests(unittest.TestCase):
    def test_uses_only_future_funding_and_charges_four_legs(self):
        funding = [_rate(0, 0.001), _rate(1, 0.001), _rate(2, 0.001), _rate(3, 0.001)]
        opens = {index * BAR_MS: 100.0 for index in range(100)}
        # Preserve a perfect hedge so funding is the only source of gross profit.
        report = audit_positive_funding_carry(
            "BTC", funding, opens, opens, CarrySpec(funding_periods_held=3, cooldown_periods=3), four_leg_cost=0.0028
        )
        self.assertEqual(1, report["summary"]["events"])
        self.assertAlmostEqual(0.003, report["summary"]["avg_funding_income"])
        self.assertAlmostEqual(0.0002, report["summary"]["avg_net_return"])

    def test_rejects_trigger_below_cost_coverage_threshold(self):
        funding = [_rate(index, 0.0001) for index in range(4)]
        opens = {index * BAR_MS: 100.0 for index in range(100)}
        report = audit_positive_funding_carry("BTC", funding, opens, opens, four_leg_cost=0.0028)
        self.assertEqual(0, report["summary"]["events"])


if __name__ == "__main__":
    unittest.main()

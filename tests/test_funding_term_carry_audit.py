from __future__ import annotations

import unittest

from funding_rate import FundingRate
from funding_term_carry_audit import (
    BAR_MS,
    DAY_MS,
    FOUR_LEG_ROUND_TRIP_COST,
    HOLD_DAYS,
    LOOKBACK_DAYS,
    PERCENTILE_LOOKBACK_DAYS,
    audit_symbol,
    build_verdict,
    first_open_at_or_after,
    percentile,
    rolling_average,
    summarize_events,
)


def rate(index: int, value: float) -> FundingRate:
    ts = index * 8 * 60 * 60 * 1000
    return FundingRate("BTC-USDT-SWAP", ts, str(index), value, value)


class FundingTermCarryAuditTests(unittest.TestCase):
    def test_percentile_uses_sorted_historical_values(self):
        self.assertEqual(3.0, percentile([5.0, 1.0, 3.0, 2.0], 0.80))

    def test_rolling_average_waits_for_full_window(self):
        values = [1.0, 2.0, 3.0]
        self.assertIsNone(rolling_average(values, 1, 3))
        self.assertEqual(2.0, rolling_average(values, 2, 3))

    def test_first_open_searches_forward_from_rounded_bucket(self):
        opens = {BAR_MS * 2: 100.0}
        self.assertEqual((BAR_MS * 2, 100.0), first_open_at_or_after(opens, BAR_MS + 1))

    def test_audit_symbol_collects_only_future_funding_and_four_leg_cost(self):
        warmup = (PERCENTILE_LOOKBACK_DAYS + LOOKBACK_DAYS) * 3
        hold_periods = HOLD_DAYS * 3
        funding = [rate(i, 0.0001) for i in range(warmup + hold_periods + 5)]
        funding[warmup] = rate(warmup, 0.003)
        for i in range(warmup + 1, warmup + hold_periods + 1):
            funding[i] = rate(i, 0.001)
        opens = {i * BAR_MS: 100.0 for i in range(20_000)}
        formation_start = funding[warmup].ts
        events = audit_symbol(
            "BTC-USDT-SWAP",
            funding,
            opens,
            opens,
            formation_start,
            formation_start + 60 * DAY_MS,
            formation_start + 61 * DAY_MS,
            formation_start + 120 * DAY_MS,
        )
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertAlmostEqual(hold_periods * 0.001, event.funding_income)
        self.assertAlmostEqual(event.funding_income - FOUR_LEG_ROUND_TRIP_COST, event.net_return)

    def test_audit_symbol_does_not_use_exit_after_oos_end(self):
        warmup = (PERCENTILE_LOOKBACK_DAYS + LOOKBACK_DAYS) * 3
        funding = [rate(i, 0.001) for i in range(warmup + HOLD_DAYS * 3 + 5)]
        opens = {i * BAR_MS: 100.0 for i in range(20_000)}
        formation_start = funding[warmup].ts
        events = audit_symbol(
            "BTC-USDT-SWAP",
            funding,
            opens,
            opens,
            formation_start,
            formation_start + 60 * DAY_MS,
            formation_start + 61 * DAY_MS,
            formation_start + 3 * DAY_MS,
        )
        self.assertEqual([], events)

    def test_verdict_rejects_negative_or_concentrated_oos(self):
        summary = {
            "formation": {"net": {"observations": 10, "mean_pct": 1.0, "win_rate": 0.6}},
            "oos": {"net": {"observations": 5, "mean_pct": -1.0, "win_rate": 0.4}},
        }
        result = build_verdict(
            summary,
            {"top_month_positive_contribution_share": 0.1},
            {"top_month_positive_contribution_share": 0.1},
        )
        self.assertEqual("rejected", result["status"])
        self.assertFalse(result["eligible_for_strategy"])

    def test_summarize_events_reports_net_and_components(self):
        warmup = (PERCENTILE_LOOKBACK_DAYS + LOOKBACK_DAYS) * 3
        hold_periods = HOLD_DAYS * 3
        funding = [rate(i, 0.0001) for i in range(warmup + hold_periods + 5)]
        funding[warmup] = rate(warmup, 0.003)
        for i in range(warmup + 1, warmup + hold_periods + 1):
            funding[i] = rate(i, 0.001)
        opens = {i * BAR_MS: 100.0 for i in range(20_000)}
        events = audit_symbol(
            "BTC-USDT-SWAP",
            funding,
            opens,
            opens,
            funding[warmup].ts,
            funding[warmup].ts + 60 * DAY_MS,
            funding[warmup].ts + 61 * DAY_MS,
            funding[warmup].ts + 120 * DAY_MS,
        )
        summary = summarize_events(events)
        self.assertEqual(1, summary["formation"]["net"]["observations"])
        self.assertIn("funding_income", summary["formation"])


if __name__ == "__main__":
    unittest.main()

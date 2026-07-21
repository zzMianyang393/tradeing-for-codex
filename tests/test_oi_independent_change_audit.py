from __future__ import annotations

import unittest

from oi_independent_change_audit import (
    FIFTEEN_MINUTES_MS,
    OiChange,
    PriceBar,
    compute_event_returns,
    find_sync_events,
    formation_verdict,
    parse_timestamp_ms,
    summarize_returns,
    tradable_event_concentration,
)


class OiIndependentChangeAuditTests(unittest.TestCase):
    def test_sync_event_requires_declared_fraction_and_direction(self):
        ts = parse_timestamp_ms("2025-01-01 16:00:00")
        changes = {
            f"SYM{i}-USDT-SWAP": [
                OiChange(f"SYM{i}-USDT-SWAP", ts, "2025-01-01 16:00:00", 0.06 if i < 4 else 0.01)
            ]
            for i in range(10)
        }
        events = find_sync_events(changes, min_abs_change=0.05, sync_fraction=0.4, min_coins=10)
        self.assertEqual(1, len(events))
        self.assertEqual("oi_up", events[0]["event_direction"])
        self.assertEqual(4, events[0]["qualified_coins"])

    def test_returns_enter_at_1615_after_oi_snapshot(self):
        event_ts = parse_timestamp_ms("2025-01-01 16:00:00")
        entry_ts = event_ts + FIFTEEN_MINUTES_MS
        symbol = "BTC-USDT-SWAP"
        events = [{
            "event_ts": event_ts,
            "timestamp_utc": "2025-01-01 16:00:00",
            "event_direction": "oi_up",
            "symbols": [symbol],
            "changes": {symbol: 0.08},
        }]
        prices = {
            symbol: {
                event_ts: PriceBar(event_ts, 50.0, 50.0),
                entry_ts: PriceBar(entry_ts, 100.0, 100.0),
                entry_ts + 16 * FIFTEEN_MINUTES_MS: PriceBar(entry_ts + 16 * FIFTEEN_MINUTES_MS, 110.0, 110.0),
            }
        }
        returns = compute_event_returns(events, prices, formation_end_ts=event_ts, horizons_bars=(16,), round_trip_cost=0.0)
        self.assertEqual(entry_ts, returns[0].entry_ts)
        self.assertAlmostEqual(10.0, returns[0].raw_return_pct)

    def test_formation_verdict_rejects_low_event_count(self):
        summary = summarize_returns([])
        concentration = {"formation_events": 0, "top_month_share": 0.0}
        verdict = formation_verdict(summary, concentration)
        self.assertEqual("rejected", verdict["status"])
        self.assertFalse(verdict["eligible_for_strategy"])

    def test_tradable_event_concentration_counts_unique_events_with_returns(self):
        event_ts = parse_timestamp_ms("2025-01-01 16:00:00")
        entry_ts = event_ts + FIFTEEN_MINUTES_MS
        symbol = "BTC-USDT-SWAP"
        events = [{
            "event_ts": event_ts,
            "timestamp_utc": "2025-01-01 16:00:00",
            "event_direction": "oi_up",
            "symbols": [symbol],
            "changes": {symbol: 0.08},
        }]
        prices = {
            symbol: {
                entry_ts: PriceBar(entry_ts, 100.0, 100.0),
                entry_ts + 16 * FIFTEEN_MINUTES_MS: PriceBar(entry_ts + 16 * FIFTEEN_MINUTES_MS, 110.0, 110.0),
            }
        }
        returns = compute_event_returns(events, prices, formation_end_ts=event_ts, horizons_bars=(16,), round_trip_cost=0.0)
        concentration = tradable_event_concentration(returns, formation_end_ts=event_ts)
        self.assertEqual(1, concentration["formation_events"])
        self.assertEqual({"2025-01": 1}, concentration["events_by_month"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from oi_deleveraging_filter_audit import (
    DAY_MS,
    FIFTEEN_MINUTES_MS,
    LeverageState,
    OiRow,
    PriceBar,
    generate_states_for_symbol,
    parse_timestamp_ms,
    percentile,
    trailing_notional,
    verdict,
)


def oi(day: int, value: float) -> OiRow:
    ts = parse_timestamp_ms("2024-01-01 16:00:00") + day * DAY_MS
    return OiRow("BTC-USDT-SWAP", ts, "ts", value)


def bar(ts: int, open_: float, close: float, volume: float = 1.0) -> PriceBar:
    return PriceBar(ts, open_, close, volume)


class OiDeleveragingFilterAuditTests(unittest.TestCase):
    def test_percentile_uses_prior_distribution(self):
        self.assertEqual(3.0, percentile([1.0, 2.0, 3.0, 4.0], 0.80))

    def test_trailing_notional_uses_only_past_24h(self):
        cutoff = parse_timestamp_ms("2024-01-02 16:00:00")
        bars = [
            bar(cutoff - DAY_MS - FIFTEEN_MINUTES_MS, 100, 100, 100),
            bar(cutoff - FIFTEEN_MINUTES_MS, 100, 100, 2),
            bar(cutoff, 100, 100, 3),
            bar(cutoff + FIFTEEN_MINUTES_MS, 100, 100, 999),
        ]
        self.assertEqual(500.0, trailing_notional(bars, cutoff))

    def test_generate_states_enters_after_oi_snapshot(self):
        start = parse_timestamp_ms("2024-01-01 16:00:00")
        oi_rows = [oi(day, 1000.0 + day) for day in range(200)]
        oi_rows[190] = oi(190, 2000.0)
        bars = []
        for day in range(210):
            for slot in range(96):
                ts = start - 16 * 60 * 60 * 1000 + day * DAY_MS + slot * FIFTEEN_MINUTES_MS
                bars.append(bar(ts, 100.0, 101.0, 1.0))
        states = generate_states_for_symbol(
            "BTC-USDT-SWAP",
            oi_rows,
            bars,
            start + 205 * DAY_MS,
            start + 209 * DAY_MS,
        )
        self.assertTrue(states)
        self.assertEqual(oi_rows[190].ts + FIFTEEN_MINUTES_MS, states[0].entry_ts)

    def test_generate_states_does_not_use_exit_after_oos_end(self):
        start = parse_timestamp_ms("2024-01-01 16:00:00")
        oi_rows = [oi(day, 1000.0 + day) for day in range(200)]
        oi_rows[190] = oi(190, 2000.0)
        bars = []
        for day in range(210):
            for slot in range(96):
                ts = start - 16 * 60 * 60 * 1000 + day * DAY_MS + slot * FIFTEEN_MINUTES_MS
                bars.append(bar(ts, 100.0, 101.0, 1.0))
        states = generate_states_for_symbol(
            "BTC-USDT-SWAP",
            oi_rows,
            bars,
            start + 205 * DAY_MS,
            oi_rows[190].ts + 3 * DAY_MS,
        )
        self.assertEqual([], states)

    def test_verdict_is_never_strategy_or_hard_filter_eligible(self):
        summary = {"formation": {"events": 0, "abs_fwd_3d": {"mean_pct": 0.0}}}
        result = verdict(summary, {"top_month_share": 0.0, "top_symbol_share": 0.0})
        self.assertFalse(result["eligible_for_strategy"])
        self.assertFalse(result["eligible_as_hard_filter"])

    def test_leverage_state_shape_contains_forward_shock_fields(self):
        state = LeverageState(
            "BTC-USDT-SWAP",
            "formation",
            1,
            "ts",
            2,
            "entry",
            1.0,
            0.8,
            5.0,
            1000.0,
            -1.0,
            -3.0,
            -5.0,
            3.0,
            5.0,
        )
        self.assertEqual(5.0, state.fwd_7d_abs_return_pct)


if __name__ == "__main__":
    unittest.main()

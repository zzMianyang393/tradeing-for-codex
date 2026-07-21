from __future__ import annotations

import unittest

from okx_futures_calendar_spread_pipeline import (
    FOUR_LEG_ROUND_TRIP_COST,
    ROLLOVER_TWO_LEG_COST,
    assert_four_leg_cost,
    build_spread_rows,
    parse_okx_delivery_contract,
    parse_utc_ms,
    select_current_and_next_quarter,
    selected_current_contract_id,
)


class OkxFuturesCalendarSpreadPipelineTests(unittest.TestCase):
    def test_parse_delivery_contract_expiry_at_0800_utc(self):
        contract = parse_okx_delivery_contract("BTC-USDT-260925")
        self.assertEqual("BTC-USDT", contract.family)
        self.assertEqual(parse_utc_ms("2026-09-25 08:00:00"), contract.expiry_ts)

    def test_rejects_non_delivery_instrument_id(self):
        with self.assertRaises(ValueError):
            parse_okx_delivery_contract("BTC-USDT-SWAP")

    def test_selects_current_and_next_without_future_listings(self):
        contracts = [
            parse_okx_delivery_contract("BTC-USDT-240927", listed_ts=parse_utc_ms("2024-06-01 00:00:00")),
            parse_okx_delivery_contract("BTC-USDT-241227", listed_ts=parse_utc_ms("2024-06-01 00:00:00")),
            parse_okx_delivery_contract("BTC-USDT-250328", listed_ts=parse_utc_ms("2024-12-28 00:00:00")),
        ]
        current, next_contract = select_current_and_next_quarter(contracts, parse_utc_ms("2024-07-01 00:00:00"), "BTC-USDT")
        assert current is not None
        assert next_contract is not None
        self.assertEqual("BTC-USDT-240927", current.inst_id)
        self.assertEqual("BTC-USDT-241227", next_contract.inst_id)

    def test_rolls_before_delivery_by_72h(self):
        old = parse_okx_delivery_contract("BTC-USDT-240927", listed_ts=parse_utc_ms("2024-06-01 00:00:00"))
        new = parse_okx_delivery_contract("BTC-USDT-241227", listed_ts=parse_utc_ms("2024-06-01 00:00:00"))
        contracts = [old, new]
        before_roll = parse_utc_ms("2024-09-24 07:45:00")
        at_roll = parse_utc_ms("2024-09-24 08:00:00")
        self.assertEqual("BTC-USDT-240927", selected_current_contract_id(contracts, before_roll, "BTC-USDT"))
        self.assertEqual("BTC-USDT-241227", selected_current_contract_id(contracts, at_roll, "BTC-USDT"))

    def test_builds_spread_first_rows_without_price_stitching(self):
        ts1 = parse_utc_ms("2024-09-24 07:45:00")
        ts2 = parse_utc_ms("2024-09-24 08:00:00")
        contracts = [
            parse_okx_delivery_contract("BTC-USDT-240927", listed_ts=parse_utc_ms("2024-06-01 00:00:00")),
            parse_okx_delivery_contract("BTC-USDT-241227", listed_ts=parse_utc_ms("2024-06-01 00:00:00")),
        ]
        rows = build_spread_rows(
            {
                "BTC-USDT-240927": {ts1: 101.0, ts2: 999.0},
                "BTC-USDT-241227": {ts1: 102.0, ts2: 103.0},
            },
            {ts1: 100.0, ts2: 100.0},
            contracts,
            "BTC-USDT",
        )
        self.assertEqual(["BTC-USDT-240927", "BTC-USDT-241227"], [row.future_inst_id for row in rows])
        self.assertEqual([1.0, 3.0], [row.spread_abs for row in rows])
        self.assertEqual([0.01, 0.03], [row.spread_pct for row in rows])

    def test_cost_constants_match_pre_registered_floor(self):
        self.assertEqual(0.0032, FOUR_LEG_ROUND_TRIP_COST)
        self.assertEqual(0.0016, ROLLOVER_TWO_LEG_COST)
        assert_four_leg_cost(0.0032)
        with self.assertRaises(ValueError):
            assert_four_leg_cost(0.003199)


if __name__ == "__main__":
    unittest.main()

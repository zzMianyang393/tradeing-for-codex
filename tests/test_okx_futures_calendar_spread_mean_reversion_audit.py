from __future__ import annotations

import unittest

from okx_futures_calendar_spread_mean_reversion_audit import (
    SpreadPoint,
    generate_trades,
    summarize_trades,
)
from okx_futures_calendar_spread_pipeline import parse_utc_ms


class OkxFuturesCalendarSpreadMeanReversionAuditTests(unittest.TestCase):
    def _history(self, start: int, contract: str) -> list[SpreadPoint]:
        return [
            SpreadPoint(start + index * 60_000, contract, 0.001 + (0.00001 if index % 2 else -0.00001))
            for index in range(7 * 24 * 60)
        ]

    def test_generates_short_spread_trade_after_positive_z_reverts(self):
        start = parse_utc_ms("2025-06-01 00:00:00")
        points = self._history(start, "BTC-USDT-250627")
        points.append(SpreadPoint(start + len(points) * 60_000, "BTC-USDT-250627", 0.006))
        points.append(SpreadPoint(start + len(points) * 60_000, "BTC-USDT-250627", 0.001))
        trades = generate_trades(points)
        self.assertEqual(1, len(trades))
        self.assertEqual("short_spread", trades[0].side)
        self.assertEqual("mean_reversion", trades[0].exit_reason)
        self.assertAlmostEqual(0.0018, trades[0].net_return)

    def test_rollover_guard_closes_before_contract_change(self):
        start = parse_utc_ms("2025-06-01 00:00:00")
        points = self._history(start, "BTC-USDT-250627")
        points.append(SpreadPoint(start + len(points) * 60_000, "BTC-USDT-250627", -0.006))
        last_old = SpreadPoint(start + len(points) * 60_000, "BTC-USDT-250627", -0.005)
        points.append(last_old)
        points.append(SpreadPoint(start + len(points) * 60_000, "BTC-USDT-250704", -0.004))
        trades = generate_trades(points)
        self.assertEqual(1, len(trades))
        self.assertEqual("long_spread", trades[0].side)
        self.assertEqual("rollover_guard", trades[0].exit_reason)
        self.assertEqual(last_old.ts, trades[0].exit_ts)

    def test_summary_computes_gate_metrics(self):
        start = parse_utc_ms("2025-06-01 00:00:00")
        points = self._history(start, "BTC-USDT-250627")
        points.append(SpreadPoint(start + len(points) * 60_000, "BTC-USDT-250627", 0.006))
        points.append(SpreadPoint(start + len(points) * 60_000, "BTC-USDT-250627", 0.001))
        summary = summarize_trades(generate_trades(points), start, start + 20_000 * 60_000)
        self.assertEqual(1, summary["events"])
        self.assertEqual(1.0, summary["win_rate"])
        self.assertEqual(1.0, summary["top_month_concentration"])


if __name__ == "__main__":
    unittest.main()

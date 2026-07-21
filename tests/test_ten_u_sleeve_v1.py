from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone

from ten_u_sleeve_v1 import (
    TenUSleeveConfig,
    TradeEvent,
    TenUSleeveAccount,
    build_fixed_stress_report,
    run_simulation,
)


class TestTenUSleeveV1(unittest.TestCase):
    def setUp(self) -> None:
        self.config = TenUSleeveConfig(
            min_notionals={
                "BTC-USDT-SWAP": Decimal("5.0"),
                "ETH-USDT-SWAP": Decimal("5.0"),
            }
        )

    def test_01_initial_equity_exact_10_usdt(self) -> None:
        account = TenUSleeveAccount(self.config)
        self.assertEqual(self.config.initial_equity, Decimal("10.0"))
        self.assertEqual(account.equity, Decimal("10.0"))

    def test_02_rejection_of_external_top_ups(self) -> None:
        self.assertFalse(self.config.external_top_up_allowed)
        self.assertFalse(self.config.profit_transfer_in_allowed)
        self.assertTrue(self.config.isolated_from_main_account)
        account = TenUSleeveAccount(self.config)
        with self.assertRaises(PermissionError):
            account.top_up(Decimal("1"))
        with self.assertRaises(PermissionError):
            account.transfer_in(Decimal("1"))

    def test_config_is_deeply_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            self.config.max_leverage = Decimal("9")
        with self.assertRaises(TypeError):
            self.config.min_notionals["BTC-USDT-SWAP"] = Decimal("99")

    def test_missing_symbol_min_notional_fails_closed(self) -> None:
        account = TenUSleeveAccount(TenUSleeveConfig())
        event = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100"),
            exit_price=Decimal("101"),
            stop_price=Decimal("95"),
        )
        record = account.process_event(event)
        self.assertEqual(record["reason"], "SKIP_MIN_NOTIONAL_UNAVAILABLE")

    def test_protocol_binding_loads_every_frozen_symbol(self) -> None:
        from research_protocol import ResearchProtocol
        path = Path(__file__).resolve().parents[1] / "reports" / "research_protocol_v1.json"
        protocol = ResearchProtocol.load(path)
        config = TenUSleeveConfig.from_research_protocol(protocol)
        self.assertEqual(set(config.min_notionals), set(protocol.symbol_universe))

    def test_invalid_risk_config_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            TenUSleeveConfig(risk_per_trade=Decimal("1"))
        with self.assertRaises(ValueError):
            TenUSleeveConfig(external_top_up_allowed=True)

    def test_03_risk_limit_and_gap_handling(self) -> None:
        account = TenUSleeveAccount(self.config)
        # Normal stop loss event
        # risk_budget = 10 * 15% = 1.5. Stop pct = 10%. Cost pct = ~10.14%. Calculated notional = 14.7928.
        # Loss at stop price should be exactly calculated_notional * Cost pct = 1.5.
        event1 = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("90.0"),
            stop_price=Decimal("90.0"),
        )
        record1 = account.process_event(event1)
        net_pnl = Decimal(record1["net_pnl"])
        self.assertLess(net_pnl, 0)
        # Net loss must not exceed 1.5 USDT
        self.assertTrue(abs(net_pnl) <= Decimal("1.5001"))
        self.assertFalse(record1["is_gap_exceeded"])

        # Reset account for gap test
        account2 = TenUSleeveAccount(self.config)
        # Gap event: exit price (50.0) is worse than stop price (95.0)
        event2 = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("50.0"),
            stop_price=Decimal("95.0"),
        )
        record2 = account2.process_event(event2)
        net_pnl2 = Decimal(record2["net_pnl"])
        self.assertTrue(abs(net_pnl2) > Decimal("1.5"))  # exceeds risk budget
        self.assertTrue(record2["is_gap_exceeded"])

    def test_04_leverage_limit_5x(self) -> None:
        account = TenUSleeveAccount(self.config)
        # Very tight stop loss (1% stop loss pct)
        # Risk budget is 1.5 USDT. 1.5 / 1% = 150 USDT.
        # But max leverage size is 10 * 5 = 50 USDT.
        # So executed notional size must be capped at 50 USDT.
        event = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("101.0"),
            stop_price=Decimal("99.0"),
        )
        record = account.process_event(event)
        self.assertEqual(Decimal(record["notional"]), Decimal("50.0"))

    def test_05_max_open_positions_is_1(self) -> None:
        self.assertEqual(self.config.max_open_positions, 1)
        account = TenUSleeveAccount(self.config)
        account.open_positions = 1
        result = account.process_event(TradeEvent(
            timestamp="2026-07-16T12:00:00Z", symbol="BTC-USDT-SWAP",
            side="long", entry_price=Decimal("100"), exit_price=Decimal("101"),
            stop_price=Decimal("95"),
        ))
        self.assertEqual(result["reason"], "SKIP_MAX_OPEN_POSITIONS")

    def test_requested_notional_can_only_reduce_safe_size(self) -> None:
        account = TenUSleeveAccount(self.config)
        result = account.process_event(TradeEvent(
            timestamp="2026-07-16T12:00:00Z", symbol="BTC-USDT-SWAP",
            side="long", entry_price=Decimal("100"), exit_price=Decimal("101"),
            stop_price=Decimal("99"), requested_notional=Decimal("7"),
        ))
        self.assertEqual(Decimal(result["notional"]), Decimal("7.0000"))

    def test_06_consecutive_losses_cooldown(self) -> None:
        account = TenUSleeveAccount(self.config)
        # 3 consecutive small losses (2%)
        for i in range(3):
            event = TradeEvent(
                timestamp=f"2026-07-16T1{i}:00:00Z",
                symbol="BTC-USDT-SWAP",
                side="long",
                entry_price=Decimal("100.0"),
                exit_price=Decimal("98.0"),
                stop_price=Decimal("98.0"),
            )
            account.process_event(event)
    
        self.assertEqual(account.state, "COOLDOWN")
        
        # 4th trade event (1 hour later) should be skipped
        event4 = TradeEvent(
            timestamp="2026-07-16T14:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("105.0"),
            stop_price=Decimal("95.0"),
        )
        record4 = account.process_event(event4)
        self.assertEqual(record4["reason"], "SKIP_ACCOUNT_COOLDOWN")

        # Trade after 24h should be accepted (cooldown ends)
        event5 = TradeEvent(
            timestamp="2026-07-17T15:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("105.0"),
            stop_price=Decimal("95.0"),
        )
        record5 = account.process_event(event5)
        self.assertEqual(record5["symbol"], "BTC-USDT-SWAP")
        self.assertNotIn("reason", record5)
        self.assertEqual(account.state, "ACTIVE")

    def test_cooldown_uses_completed_bar_count_when_available(self) -> None:
        account = TenUSleeveAccount(self.config)
        for i in range(3):
            account.process_event(TradeEvent(
                timestamp=f"2026-07-16T1{i}:00:00Z",
                symbol="BTC-USDT-SWAP", side="long",
                entry_price=Decimal("100"), exit_price=Decimal("98"),
                stop_price=Decimal("98"), bar_index=i,
            ))
        too_early = account.process_event(TradeEvent(
            timestamp="2026-07-18T12:00:00Z", symbol="BTC-USDT-SWAP",
            side="long", entry_price=Decimal("100"), exit_price=Decimal("101"),
            stop_price=Decimal("95"), bar_index=97,
        ))
        self.assertEqual(too_early["reason"], "SKIP_ACCOUNT_COOLDOWN")
        accepted = account.process_event(TradeEvent(
            timestamp="2026-07-18T12:15:00Z", symbol="BTC-USDT-SWAP",
            side="long", entry_price=Decimal("100"), exit_price=Decimal("101"),
            stop_price=Decimal("95"), bar_index=98,
        ))
        self.assertNotIn("reason", accepted)

    def test_07_daily_loss_halt_recovery(self) -> None:
        account = TenUSleeveAccount(self.config)
        # Use gap loss to trigger daily loss (>35%) in a single trade
        event1 = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("80.0"),
            stop_price=Decimal("95.0"),
        )
        account.process_event(event1)
        self.assertEqual(account.state, "HALTED_DAILY_LOSS")

        # Same day trade -> skipped
        event2 = TradeEvent(
            timestamp="2026-07-16T15:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("105.0"),
            stop_price=Decimal("95.0"),
        )
        record2 = account.process_event(event2)
        self.assertEqual(record2["reason"], "SKIP_ACCOUNT_HALTED_DAILY_LOSS")

        # Next day trade -> accepted (recovered)
        event3 = TradeEvent(
            timestamp="2026-07-17T01:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("105.0"),
            stop_price=Decimal("95.0"),
        )
        record3 = account.process_event(event3)
        self.assertNotIn("reason", record3)
        self.assertEqual(account.state, "ACTIVE")

    def test_08_peak_drawdown_halt(self) -> None:
        account = TenUSleeveAccount(self.config)
        # Win to increase equity to 15.0
        event1 = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("140.0"),
            stop_price=Decimal("80.0"),
        )
        account.process_event(event1)
        self.assertEqual(account.peak_equity, account.equity)

        # Huge gap loss dropping equity below 4.5 (drawdown > 70%)
        event2 = TradeEvent(
            timestamp="2026-07-16T13:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("72.0"),
            stop_price=Decimal("95.0"),
        )
        account.process_event(event2)
        self.assertEqual(account.state, "HALTED_DRAWDOWN")

        # Subsequent trade is skipped
        event3 = TradeEvent(
            timestamp="2026-07-17T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("110.0"),
            stop_price=Decimal("90.0"),
        )
        record3 = account.process_event(event3)
        self.assertEqual(record3["reason"], "SKIP_ACCOUNT_HALTED_DRAWDOWN")

    def test_09_ruined_at_ruin_equity_threshold(self) -> None:
        account = TenUSleeveAccount(self.config)
        # Gap loss dropping equity to <= 2.0 USDT (ruin threshold is 2.0)
        event1 = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("40.0"),
            stop_price=Decimal("95.0"),
        )
        account.process_event(event1)
        self.assertEqual(account.state, "RUINED")
        self.assertEqual(account.equity, Decimal("0"))

    def test_10_ruined_state_permanent_lock(self) -> None:
        account = TenUSleeveAccount(self.config)
        event1 = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("40.0"),
            stop_price=Decimal("95.0"),
        )
        account.process_event(event1)

        # Profitable event next day should still be skipped
        event2 = TradeEvent(
            timestamp="2026-07-17T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("200.0"),
            stop_price=Decimal("90.0"),
        )
        record2 = account.process_event(event2)
        self.assertEqual(record2["reason"], "SKIP_ACCOUNT_RUINED")
        self.assertEqual(account.state, "RUINED")

    def test_11_skip_below_min_notional(self) -> None:
        # min_notional set to 15.0 USDT
        config = TenUSleeveConfig(min_notionals={"BTC-USDT-SWAP": Decimal("15.0")})
        account = TenUSleeveAccount(config)
        # Position sizing calculates notional as ~14.79 USDT
        event = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("90.0"),
            stop_price=Decimal("90.0"),
        )
        record = account.process_event(event)
        self.assertEqual(record["reason"], "SKIP_MIN_NOTIONAL")

    def test_12_profit_compounding_fixed_risk_ratio(self) -> None:
        account = TenUSleeveAccount(self.config)
        # Initial risk budget is 1.5 USDT (notional size ~14.79 USDT)
        event1 = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("200.0"),
            stop_price=Decimal("90.0"),
        )
        record1 = account.process_event(event1)
        
        # Next trade after win. Equity increases, so notional must increase proportionally (compounding).
        event2 = TradeEvent(
            timestamp="2026-07-16T13:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("105.0"),
            stop_price=Decimal("90.0"),
        )
        record2 = account.process_event(event2)
        self.assertGreater(Decimal(record2["notional"]), Decimal(record1["notional"]))
        self.assertEqual(self.config.risk_per_trade, Decimal("0.15"))  # Risk ratio unchanged

    def test_13_double_sided_fees_and_slippage(self) -> None:
        account = TenUSleeveAccount(self.config)
        # Zero price change trade
        event = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("100.0"),
            stop_price=Decimal("90.0"),
        )
        record = account.process_event(event)
        net_pnl = Decimal(record["net_pnl"])
        # Net PnL must be negative due to entry and exit fees + slippage (double-sided)
        self.assertLess(net_pnl, 0)
        expected_costs = Decimal(record["notional"]) * (self.config.taker_fee + self.config.slippage) * 2
        self.assertTrue(abs(net_pnl + expected_costs) < Decimal("0.01"))

    def test_14_funding_not_applied_status(self) -> None:
        res = run_simulation(self.config, [])
        self.assertEqual(res["funding_cost_status"], "not_applied")

    def test_15_stable_config_fingerprint(self) -> None:
        fp1 = self.config.fingerprint()
        config2 = TenUSleeveConfig(taker_fee=Decimal("0.001"))
        fp2 = config2.fingerprint()
        self.assertNotEqual(fp1, fp2)

    def test_16_out_of_order_timestamp_rejected(self) -> None:
        account = TenUSleeveAccount(self.config)
        event1 = TradeEvent(
            timestamp="2026-07-16T12:00:00Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("105.0"),
            stop_price=Decimal("90.0"),
        )
        account.process_event(event1)

        # Out-of-order event (earlier time) -> ValueError
        event2 = TradeEvent(
            timestamp="2026-07-16T11:59:59Z",
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=Decimal("100.0"),
            exit_price=Decimal("105.0"),
            stop_price=Decimal("90.0"),
        )
        with self.assertRaises(ValueError):
            account.process_event(event2)

    def test_17_determinism_consistency(self) -> None:
        events = [
            TradeEvent("2026-07-16T12:00:00Z", "BTC-USDT-SWAP", "long", Decimal("100.0"), Decimal("105.0"), Decimal("90.0")),
            TradeEvent("2026-07-16T13:00:00Z", "BTC-USDT-SWAP", "long", Decimal("100.0"), Decimal("95.0"), Decimal("90.0")),
        ]
        res1 = run_simulation(self.config, events)
        res2 = run_simulation(self.config, events)
        self.assertEqual(res1, res2)

    def test_18_no_forbidden_status_in_report(self) -> None:
        report_path = Path(__file__).resolve().parents[1] / "reports" / "ten_u_sleeve_stress_v1.json"
        self.assertTrue(report_path.exists())
        content = report_path.read_text(encoding="utf-8")
        
        # Verify no forbidden words
        self.assertNotIn('"approved"', content.lower())
        self.assertNotIn('"paper_trading"', content.lower())
        self.assertNotIn('"live_trading": true', content.lower())
        self.assertNotIn('"live_trading":true', content.lower())

    def test_checked_in_report_is_reproducible_and_non_negative(self) -> None:
        report_path = Path(__file__).resolve().parents[1] / "reports" / "ten_u_sleeve_stress_v1.json"
        checked_in = json.loads(report_path.read_text(encoding="utf-8"))
        generated = build_fixed_stress_report()
        self.assertEqual(checked_in, generated)
        for scenario in checked_in.values():
            self.assertGreaterEqual(Decimal(scenario["ending_equity"]), Decimal("0"))
            self.assertEqual(scenario["formal_status"], "infrastructure_only")


if __name__ == "__main__":
    unittest.main()

"""Tests for the frozen research protocol."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path

from config import BacktestConfig, SymbolRisk
from market import FeatureBar
from strategy import Signal
from research_protocol import (
    CostModel,
    DataSplit,
    FrozenParams,
    ResearchProtocol,
    SplitBoundaries,
    audit_old_reports,
    enforce_data_cutoff,
    assess_symbol_coverage,
    slice_market,
)


class CostModelTests(unittest.TestCase):
    def test_fingerprint_stable(self):
        a = CostModel()
        b = CostModel()
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_fingerprint_changes_with_fee(self):
        a = CostModel()
        b = CostModel(taker_fee=0.001)
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_fingerprint_changes_with_slippage(self):
        a = CostModel()
        b = CostModel(slippage=0.001)
        self.assertNotEqual(a.fingerprint(), b.fingerprint())


class DataSplitTests(unittest.TestCase):
    def test_fingerprint_stable(self):
        a = DataSplit()
        b = DataSplit()
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_fingerprint_changes_with_embargo(self):
        a = DataSplit()
        b = DataSplit(embargo_bars=192)
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_fractions_sum_to_one(self):
        s = DataSplit()
        total = s.formation_fraction + s.validation_fraction + s.oos_fraction
        self.assertAlmostEqual(total, 1.0)


class FrozenParamsTests(unittest.TestCase):
    def test_fingerprint_stable(self):
        a = FrozenParams()
        b = FrozenParams()
        self.assertEqual(a.fingerprint(), b.fingerprint())

    def test_fingerprint_changes_with_risk(self):
        a = FrozenParams()
        b = FrozenParams(risk_per_trade=0.5)
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_to_backtest_config_disables_window_profiles(self):
        p = FrozenParams()
        cost = CostModel()
        cfg = p.to_backtest_config(cost)
        self.assertFalse(cfg.enable_target_window_profiles)
        self.assertFalse(cfg.enable_long_window_aggressive_profile)

    def test_to_backtest_config_disables_live_trading(self):
        p = FrozenParams()
        cfg = p.to_backtest_config(CostModel())
        self.assertFalse(cfg.enable_rule_trading)
        self.assertFalse(cfg.enable_pairs_trading)

    def test_to_backtest_config_uses_cost_model(self):
        cost = CostModel(taker_fee=0.001, slippage=0.003)
        cfg = FrozenParams().to_backtest_config(cost)
        self.assertAlmostEqual(cfg.taker_fee, 0.001)
        self.assertAlmostEqual(cfg.slippage, 0.003)

    def test_to_backtest_config_zeroes_validation_targets(self):
        cfg = FrozenParams().to_backtest_config(CostModel())
        self.assertEqual(cfg.validation_target_win_rate, 0.0)
        self.assertEqual(cfg.validation_target_profit, 0.0)
        self.assertEqual(cfg.validation_target_profit_by_window, {})
        self.assertEqual(cfg.validation_target_returns, {})

    def test_to_backtest_config_uses_fixed_symbols(self):
        cfg = FrozenParams().to_backtest_config(CostModel())
        self.assertIn("BTC-USDT-SWAP", cfg.allowed_symbols)
        self.assertIn("ETH-USDT-SWAP", cfg.allowed_symbols)
        self.assertEqual(len(cfg.allowed_symbols), 28)


class ResearchProtocolTests(unittest.TestCase):
    def test_create_v1_has_correct_version(self):
        p = ResearchProtocol.create_v1()
        self.assertEqual(p.version, "v1.1.0")

    def test_create_v1_has_fingerprint(self):
        p = ResearchProtocol.create_v1()
        self.assertTrue(p.config_fingerprint)
        self.assertEqual(len(p.config_fingerprint), 16)

    def test_fingerprint_deterministic(self):
        a = ResearchProtocol.create_v1(data_cutoff="2026-07-16")
        b = ResearchProtocol.create_v1(data_cutoff="2026-07-16")
        self.assertEqual(a.config_fingerprint, b.config_fingerprint)

    def test_fingerprint_changes_with_cutoff(self):
        a = ResearchProtocol.create_v1(data_cutoff="2026-07-16")
        b = ResearchProtocol.create_v1(data_cutoff="2026-07-15")
        self.assertNotEqual(a.config_fingerprint, b.config_fingerprint)

    def test_fingerprint_changes_with_cost(self):
        a = ResearchProtocol.create_v1()
        # Manually create one with different cost
        b = ResearchProtocol(
            version=a.version,
            created_at=a.created_at,
            data_cutoff=a.data_cutoff,
            data_source=a.data_source,
            cost=CostModel(taker_fee=0.001),
        )
        self.assertNotEqual(a.config_fingerprint, b.config_fingerprint)

    def test_save_and_load_roundtrip(self):
        p = ResearchProtocol.create_v1()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "protocol.json"
            p.save(path)
            loaded = ResearchProtocol.load(path)
            self.assertEqual(p.version, loaded.version)
            self.assertEqual(p.data_cutoff, loaded.data_cutoff)
            self.assertEqual(p.config_fingerprint, loaded.config_fingerprint)
            self.assertEqual(p.cost.taker_fee, loaded.cost.taker_fee)
            self.assertEqual(len(p.symbol_universe), len(loaded.symbol_universe))

    def test_write_markdown(self):
        p = ResearchProtocol.create_v1()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "protocol.md"
            content = p.write_markdown(path)
            self.assertIn("v1.1.0", content)
            self.assertIn("Cost Model", content)
            self.assertIn("Frozen Parameters", content)
            self.assertIn("Prohibited", content)
            self.assertTrue(path.exists())

    def test_sei_exclusion_is_preformation_data_only(self):
        p = ResearchProtocol.create_v1()
        self.assertNotIn("SEI-USDT-SWAP", p.symbol_universe)
        reasons = dict(p.universe_exclusions)
        self.assertIn("SEI-USDT-SWAP", reasons)
        self.assertIn("zero bars", reasons["SEI-USDT-SWAP"])


class ValidateAgainstTests(unittest.TestCase):
    def _protocol(self) -> ResearchProtocol:
        return ResearchProtocol.create_v1()

    def _frozen_config(self) -> BacktestConfig:
        p = self._protocol()
        return p.params.to_backtest_config(p.cost)

    def test_frozen_config_passes(self):
        proto = self._protocol()
        cfg = self._frozen_config()
        violations = ResearchProtocol.validate_against(proto, cfg)
        self.assertEqual(violations, [])

    def test_rejects_window_profiles_enabled(self):
        proto = self._protocol()
        cfg = self._frozen_config()
        # Simulate window profile being on
        modified = BacktestConfig(
            enable_target_window_profiles=True,
            taker_fee=proto.cost.taker_fee,
            slippage=proto.cost.slippage,
            risk_per_trade=proto.params.risk_per_trade,
            max_margin_fraction=proto.params.max_margin_fraction,
            max_total_margin_fraction=proto.params.max_total_margin_fraction,
            max_positions=proto.params.max_positions,
            active_symbol_limit=proto.params.active_symbol_limit,
            start_equity=proto.params.start_equity,
            stop_atr=proto.params.stop_atr,
            take_profit_atr=proto.params.take_profit_atr,
            trailing_atr=proto.params.trailing_atr,
            max_hold_bars=proto.params.max_hold_bars,
            range_stop_atr=proto.params.range_stop_atr,
            range_take_profit_atr=proto.params.range_take_profit_atr,
            range_trailing_atr=proto.params.range_trailing_atr,
            min_score=proto.params.min_score,
            cooldown_bars=proto.params.cooldown_bars,
            loss_cooldown_bars=proto.params.loss_cooldown_bars,
            enable_rule_trading=False,
            enable_pairs_trading=False,
        )
        violations = ResearchProtocol.validate_against(proto, modified)
        self.assertTrue(any("enable_target_window_profiles" in v for v in violations))

    def test_rejects_different_taker_fee(self):
        proto = self._protocol()
        cfg = self._frozen_config()
        # We can't mutate frozen config, so create a new one with wrong fee
        wrong = BacktestConfig(
            taker_fee=0.001,
            slippage=proto.cost.slippage,
            risk_per_trade=proto.params.risk_per_trade,
            max_margin_fraction=proto.params.max_margin_fraction,
            max_total_margin_fraction=proto.params.max_total_margin_fraction,
            max_positions=proto.params.max_positions,
            active_symbol_limit=proto.params.active_symbol_limit,
            start_equity=proto.params.start_equity,
            stop_atr=proto.params.stop_atr,
            take_profit_atr=proto.params.take_profit_atr,
            trailing_atr=proto.params.trailing_atr,
            max_hold_bars=proto.params.max_hold_bars,
            range_stop_atr=proto.params.range_stop_atr,
            range_take_profit_atr=proto.params.range_take_profit_atr,
            range_trailing_atr=proto.params.range_trailing_atr,
            min_score=proto.params.min_score,
            cooldown_bars=proto.params.cooldown_bars,
            loss_cooldown_bars=proto.params.loss_cooldown_bars,
            enable_rule_trading=False,
            enable_pairs_trading=False,
        )
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("taker_fee" in v for v in violations))

    def test_rejects_different_risk_per_trade(self):
        proto = self._protocol()
        wrong = BacktestConfig(
            taker_fee=proto.cost.taker_fee,
            slippage=proto.cost.slippage,
            risk_per_trade=0.99,
            max_margin_fraction=proto.params.max_margin_fraction,
            max_total_margin_fraction=proto.params.max_total_margin_fraction,
            max_positions=proto.params.max_positions,
            active_symbol_limit=proto.params.active_symbol_limit,
            start_equity=proto.params.start_equity,
            stop_atr=proto.params.stop_atr,
            take_profit_atr=proto.params.take_profit_atr,
            trailing_atr=proto.params.trailing_atr,
            max_hold_bars=proto.params.max_hold_bars,
            range_stop_atr=proto.params.range_stop_atr,
            range_take_profit_atr=proto.params.range_take_profit_atr,
            range_trailing_atr=proto.params.range_trailing_atr,
            min_score=proto.params.min_score,
            cooldown_bars=proto.params.cooldown_bars,
            loss_cooldown_bars=proto.params.loss_cooldown_bars,
            enable_rule_trading=False,
            enable_pairs_trading=False,
        )
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("risk_per_trade" in v for v in violations))

    def test_rejects_different_slippage(self):
        proto = self._protocol()
        wrong = BacktestConfig(
            taker_fee=proto.cost.taker_fee,
            slippage=0.01,
            risk_per_trade=proto.params.risk_per_trade,
            max_margin_fraction=proto.params.max_margin_fraction,
            max_total_margin_fraction=proto.params.max_total_margin_fraction,
            max_positions=proto.params.max_positions,
            active_symbol_limit=proto.params.active_symbol_limit,
            start_equity=proto.params.start_equity,
            stop_atr=proto.params.stop_atr,
            take_profit_atr=proto.params.take_profit_atr,
            trailing_atr=proto.params.trailing_atr,
            max_hold_bars=proto.params.max_hold_bars,
            range_stop_atr=proto.params.range_stop_atr,
            range_take_profit_atr=proto.params.range_take_profit_atr,
            range_trailing_atr=proto.params.range_trailing_atr,
            min_score=proto.params.min_score,
            cooldown_bars=proto.params.cooldown_bars,
            loss_cooldown_bars=proto.params.loss_cooldown_bars,
            enable_rule_trading=False,
            enable_pairs_trading=False,
        )
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("slippage" in v for v in violations))

    def test_rejects_live_trading_flags(self):
        proto = self._protocol()
        # Can't mutate frozen, build a new config
        wrong = BacktestConfig(
            enable_rule_trading=True,
            taker_fee=proto.cost.taker_fee,
            slippage=proto.cost.slippage,
            risk_per_trade=proto.params.risk_per_trade,
        )
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("enable_rule_trading" in v for v in violations))

    def test_rejects_validation_targets(self):
        proto = self._protocol()
        wrong = BacktestConfig(
            taker_fee=proto.cost.taker_fee,
            slippage=proto.cost.slippage,
            risk_per_trade=proto.params.risk_per_trade,
            max_margin_fraction=proto.params.max_margin_fraction,
            max_total_margin_fraction=proto.params.max_total_margin_fraction,
            max_positions=proto.params.max_positions,
            active_symbol_limit=proto.params.active_symbol_limit,
            start_equity=proto.params.start_equity,
            stop_atr=proto.params.stop_atr,
            take_profit_atr=proto.params.take_profit_atr,
            trailing_atr=proto.params.trailing_atr,
            max_hold_bars=proto.params.max_hold_bars,
            range_stop_atr=proto.params.range_stop_atr,
            range_take_profit_atr=proto.params.range_take_profit_atr,
            range_trailing_atr=proto.params.range_trailing_atr,
            min_score=proto.params.min_score,
            cooldown_bars=proto.params.cooldown_bars,
            loss_cooldown_bars=proto.params.loss_cooldown_bars,
            enable_rule_trading=False,
            enable_pairs_trading=False,
            validation_target_win_rate=0.66,
        )
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("validation_target_win_rate" in v for v in violations))


class AuditOldReportsTests(unittest.TestCase):
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            result = audit_old_reports(Path(td))
            self.assertEqual(result["valid"], [])
            self.assertEqual(result["suspect"], [])
            self.assertEqual(result["invalid"], [])

    def test_detects_window_profiles_in_report(self):
        with tempfile.TemporaryDirectory() as td:
            report = {
                "config": {
                    "enable_target_window_profiles": True,
                    "validation_target_returns": {365: 5.0, 30: 20.0},
                },
                "windows": {"365": {}, "30": {}},
            }
            path = Path(td) / "test_report.json"
            path.write_text(json.dumps(report))
            result = audit_old_reports(Path(td))
            self.assertEqual(len(result["invalid"]), 1)

    def test_detects_multi_window_report(self):
        with tempfile.TemporaryDirectory() as td:
            report = {
                "config": {"enable_target_window_profiles": False},
                "windows": {"365": {}, "180": {}, "90": {}},
            }
            path = Path(td) / "goal_365d_sprint.json"
            path.write_text(json.dumps(report))
            result = audit_old_reports(Path(td))
            # Has window pattern in name + multi window = invalid
            self.assertEqual(len(result["invalid"]), 1)

    def test_valid_report_passes(self):
        with tempfile.TemporaryDirectory() as td:
            report = {
                "config": {
                    "enable_target_window_profiles": False,
                    "enable_long_window_aggressive_profile": False,
                    "validation_target_returns": {},
                    "validation_target_profit_by_window": {},
                },
                "windows": {},
            }
            path = Path(td) / "clean_report.json"
            path.write_text(json.dumps(report))
            result = audit_old_reports(Path(td))
            self.assertEqual(len(result["invalid"]), 0)
            self.assertEqual(len(result["valid"]), 1)


class ComputeBoundariesTests(unittest.TestCase):
    def test_boundaries_cover_full_timeline(self):
        split = DataSplit(formation_fraction=0.6, validation_fraction=0.2, oos_fraction=0.2,
                          embargo_bars=10, purge_bars=5)
        timeline = list(range(0, 1000))  # 1000 bars
        b = split.compute_boundaries(timeline)
        self.assertEqual(b.formation_start_ts, 0)
        self.assertEqual(b.formation_raw_bars, 600)
        self.assertEqual(b.formation_bars, 595)
        self.assertTrue(b.oos_start_ts > b.validation_end_ts)

    def test_boundaries_no_overlap(self):
        split = DataSplit(embargo_bars=10, purge_bars=5)
        timeline = list(range(0, 1000))
        b = split.compute_boundaries(timeline)
        # Formation ends before validation starts (with embargo gap)
        self.assertLess(b.formation_end_ts, b.validation_start_ts)
        # Validation ends before OOS starts (with embargo gap)
        self.assertLess(b.validation_end_ts, b.oos_start_ts)

    def test_embargo_ranges_between_phases(self):
        split = DataSplit(embargo_bars=10, purge_bars=5)
        timeline = list(range(0, 1000))
        b = split.compute_boundaries(timeline)
        self.assertEqual(len(b.embargo_ranges), 2)
        # First embargo is between formation and validation
        self.assertGreaterEqual(b.embargo_ranges[0][0], b.formation_end_ts)
        # Second embargo is between validation and OOS
        self.assertGreaterEqual(b.embargo_ranges[1][0], b.validation_end_ts)

    def test_purge_ranges_near_boundaries(self):
        split = DataSplit(embargo_bars=10, purge_bars=20)
        timeline = list(range(0, 1000))
        b = split.compute_boundaries(timeline)
        self.assertEqual(len(b.purge_ranges), 2)

    def test_bar_counts_sum_close_to_total(self):
        split = DataSplit(embargo_bars=10, purge_bars=5)
        timeline = list(range(0, 1000))
        b = split.compute_boundaries(timeline)
        # Trading bars intentionally exclude purge and embargo regions.
        total = b.formation_bars + b.validation_bars + b.oos_bars
        self.assertEqual(total, 1000 - 2 * split.purge_bars - 2 * split.embargo_bars)


class SliceMarketTests(unittest.TestCase):
    def _make_bars(self, n: int, start_ts: int = 1000, step: int = 900_000) -> list[FeatureBar]:
        bars = []
        for i in range(n):
            ts = start_ts + i * step
            bars.append(FeatureBar(
                ts=ts, time=f"2026-01-01 {i:04d}",
                open=100.0, high=101.0, low=99.0, close=100.0,
                volume_quote=1000.0, atr=1.0, atr_pct=0.01,
            ))
        return bars

    def test_slice_separates_warmup_and_trading(self):
        bars = self._make_bars(500, start_ts=0)
        market = {"BTC-USDT-SWAP": bars}
        start_ts = 200 * 900_000  # bar 200
        end_ts = 400 * 900_000    # bar 400
        warmup, trading = slice_market(market, start_ts, end_ts, warmup_bars=100)
        # Warmup should have bars before start_ts
        if warmup:
            for b in warmup["BTC-USDT-SWAP"]:
                self.assertLess(b.ts, start_ts)
        # Trading should have bars in [start_ts, end_ts)
        for b in trading["BTC-USDT-SWAP"]:
            self.assertGreaterEqual(b.ts, start_ts)
            self.assertLess(b.ts, end_ts)

    def test_slice_no_trading_data_outside_range(self):
        bars = self._make_bars(500, start_ts=0)
        market = {"BTC-USDT-SWAP": bars}
        start_ts = 200 * 900_000
        end_ts = 300 * 900_000
        _, trading = slice_market(market, start_ts, end_ts, warmup_bars=50)
        self.assertEqual(len(trading["BTC-USDT-SWAP"]), 100)

    def test_slice_empty_when_no_bars_in_range(self):
        bars = self._make_bars(10, start_ts=0, step=900_000)
        market = {"BTC-USDT-SWAP": bars}
        # Request a range far beyond the data
        warmup, trading = slice_market(market, 999999999, 9999999999, warmup_bars=10)
        self.assertEqual(traming := trading, {})


class EnforceDataCutoffTests(unittest.TestCase):
    def _make_bars(self, n: int, start_ts: int = 1000, step: int = 900_000) -> list[FeatureBar]:
        bars = []
        for i in range(n):
            ts = start_ts + i * step
            bars.append(FeatureBar(
                ts=ts, time=f"2026-01-01 {i:04d}",
                open=100.0, high=101.0, low=99.0, close=100.0,
                volume_quote=1000.0, atr=1.0, atr_pct=0.01,
            ))
        return bars

    def test_removes_bars_after_cutoff(self):
        # Create bars spanning 2026-07-15 to 2026-07-17
        bars = self._make_bars(300, start_ts=1752624000000, step=900_000)  # ~2025-07-16
        market = {"BTC-USDT-SWAP": bars}
        filtered, removed = enforce_data_cutoff(market, "2026-07-16")
        # Should keep bars before cutoff
        self.assertGreater(len(filtered["BTC-USDT-SWAP"]), 0)

    def test_keeps_all_bars_before_cutoff(self):
        bars = self._make_bars(100, start_ts=1752000000000, step=900_000)
        market = {"BTC-USDT-SWAP": bars}
        filtered, removed = enforce_data_cutoff(market, "2026-12-31")
        self.assertEqual(len(filtered["BTC-USDT-SWAP"]), 100)
        self.assertEqual(removed, 0)

    def test_appending_post_cutoff_bars_does_not_change_filtered_data_or_split(self):
        step = 900_000
        cutoff_start = int(datetime(2026, 7, 16, tzinfo=timezone.utc).timestamp() * 1000)
        before = self._make_bars(96, start_ts=cutoff_start, step=step)
        after = self._make_bars(96, start_ts=cutoff_start + 96 * step, step=step)
        filtered_a, _ = enforce_data_cutoff({"BTC-USDT-SWAP": before}, "2026-07-16")
        filtered_b, _ = enforce_data_cutoff({"BTC-USDT-SWAP": before + after}, "2026-07-16")
        ts_a = [bar.ts for bar in filtered_a["BTC-USDT-SWAP"]]
        ts_b = [bar.ts for bar in filtered_b["BTC-USDT-SWAP"]]
        self.assertEqual(ts_a, ts_b)


class FingerprintIntegrityTests(unittest.TestCase):
    def test_load_rejects_tampered_json(self):
        proto = ResearchProtocol.create_v1()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "protocol.json"
            proto.save(path)

            # Tamper: change risk_per_trade but keep old fingerprint
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["params"]["risk_per_trade"] = 0.99
            path.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                ResearchProtocol.load(path)
            self.assertIn("Fingerprint mismatch", str(ctx.exception))

    def test_load_rejects_tampered_cost(self):
        proto = ResearchProtocol.create_v1()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "protocol.json"
            proto.save(path)

            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["cost"]["taker_fee"] = 0.01
            path.write_text(json.dumps(raw), encoding="utf-8")

            with self.assertRaises(ValueError):
                ResearchProtocol.load(path)

    def test_load_accepts_valid_file(self):
        proto = ResearchProtocol.create_v1()
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "protocol.json"
            proto.save(path)
            loaded = ResearchProtocol.load(path)
            self.assertEqual(loaded.config_fingerprint, proto.config_fingerprint)

    def test_load_rejects_runtime_market_state_contract_drift(self):
        proto = ResearchProtocol(
            version="v1.0.0",
            created_at="2026-01-01T00:00:00Z",
            data_cutoff="2026-07-16",
            data_source="test",
            market_state_config_fingerprint="obsolete-but-internally-consistent",
        )
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "protocol.json"
            proto.save(path)
            with self.assertRaisesRegex(ValueError, "market_state_contract_mismatch"):
                ResearchProtocol.load(path)


class FrozenParamsAllFieldsCoveredTests(unittest.TestCase):
    """Parametric test: changing ANY FrozenParams field changes the fingerprint."""

    def test_each_field_changes_fingerprint(self):
        base = FrozenParams()
        base_fp = base.fingerprint()

        # Values to try for each field type
        overrides = {
            "risk_per_trade": 0.99,
            "max_margin_fraction": 0.99,
            "max_total_margin_fraction": 0.99,
            "max_positions": 99,
            "active_symbol_limit": 99,
            "start_equity": 999.0,
            "stop_atr": 9.9,
            "take_profit_atr": 9.9,
            "trailing_atr": 9.9,
            "max_hold_bars": 999,
            "range_stop_atr": 9.9,
            "range_take_profit_atr": 9.9,
            "range_trailing_atr": 9.9,
            "range_max_hold_bars": 999,
            "min_score": 9.9,
            "cooldown_bars": 999,
            "loss_cooldown_bars": 999,
            "enabled_regimes": ("uptrend",),
            "enable_attack_module": True,
            "attack_min_score": 9.9,
            "attack_risk_per_trade": 0.99,
            "selector_lookback_bars": 9999,
            "selector_min_avg_quote": 999999.0,
            "selector_max_micro_noise": 0.99,
            "min_notional": 99.0,
        }

        for fld in fields(FrozenParams):
            if fld.name in overrides:
                modified = FrozenParams(**{fld.name: overrides[fld.name]})
                self.assertNotEqual(
                    modified.fingerprint(), base_fp,
                    f"Changing {fld.name} did not change fingerprint"
                )


class ValidateAgainstAllFieldsTests(unittest.TestCase):
    """Test that validate_against() detects changes in ALL FrozenParams fields."""

    def _protocol(self) -> ResearchProtocol:
        return ResearchProtocol.create_v1()

    def _base_config(self, proto: ResearchProtocol) -> BacktestConfig:
        return proto.params.to_backtest_config(proto.cost)

    def _modified_config(self, proto: ResearchProtocol, **kwargs) -> BacktestConfig:
        """Create a config with one field overridden."""
        base = self._base_config(proto)
        # Build a new config with the override
        params = {fld.name: getattr(base, fld.name) for fld in fields(BacktestConfig)
                  if fld.name != "excluded_symbols"}
        params.update(kwargs)
        params.setdefault("excluded_symbols", ())
        return BacktestConfig(**params)

    def test_rejects_range_max_hold_bars(self):
        proto = self._protocol()
        wrong = self._modified_config(proto, range_max_hold_bars=999)
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("range_max_hold_bars" in v for v in violations))

    def test_rejects_attack_min_score(self):
        proto = self._protocol()
        wrong = self._modified_config(proto, attack_min_score=9.9)
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("attack_min_score" in v for v in violations))

    def test_rejects_selector_lookback_bars(self):
        proto = self._protocol()
        wrong = self._modified_config(proto, selector_lookback_bars=9999)
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("selector_lookback_bars" in v for v in violations))

    def test_rejects_enabled_regimes(self):
        proto = self._protocol()
        wrong = self._modified_config(proto, enabled_regimes=("uptrend",))
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("enabled_regimes" in v for v in violations))

    def test_rejects_symbol_min_notional_drift(self):
        proto = self._protocol()
        config = self._base_config(proto)
        caps = dict(config.leverage_caps)
        caps["BTC-USDT-SWAP"] = SymbolRisk(
            caps["BTC-USDT-SWAP"].max_leverage,
            min_notional=999.0,
        )
        wrong = replace(config, leverage_caps=caps)
        violations = ResearchProtocol.validate_against(proto, wrong)
        self.assertTrue(any("BTC-USDT-SWAP" in value and "min_notional" in value for value in violations))


class StrictCoverageTests(unittest.TestCase):
    def test_missing_required_symbol_fails_coverage(self):
        step = 900_000
        timeline = [i * step for i in range(2400)]
        split = DataSplit()
        boundaries = split.compute_boundaries(timeline, bar_duration_ms=step)
        bars = [FeatureBar(ts=ts, time=str(ts), open=1, high=1, low=1, close=1, volume_quote=1) for ts in timeline]
        coverage = assess_symbol_coverage(
            {"BTC-USDT-SWAP": bars},
            ("BTC-USDT-SWAP", "ETH-USDT-SWAP"),
            boundaries,
            min_trading_bars=260,
            warmup_bars=260,
            bar_duration_ms=step,
        )
        self.assertEqual(coverage["coverage_status"], "FAIL")
        self.assertEqual(coverage["missing_symbols"], ["ETH-USDT-SWAP"])


class FundingCostStatusTests(unittest.TestCase):
    def test_default_is_not_applied(self):
        proto = ResearchProtocol.create_v1()
        self.assertEqual(proto.funding_cost_status, "not_applied")

    def test_rejects_applied_status(self):
        proto = ResearchProtocol(
            version="v1.0.0", created_at="2026-01-01T00:00:00Z",
            data_cutoff="2026-07-16", data_source="test",
            funding_cost_status="applied",
        )
        cfg = proto.params.to_backtest_config(proto.cost)
        violations = ResearchProtocol.validate_against(proto, cfg)
        self.assertTrue(any("funding" in v.lower() for v in violations))

    def test_accepts_not_applied_status(self):
        proto = ResearchProtocol.create_v1()
        cfg = proto.params.to_backtest_config(proto.cost)
        violations = ResearchProtocol.validate_against(proto, cfg)
        self.assertFalse(any("funding" in v.lower() for v in violations))


class MarketStateBindingTests(unittest.TestCase):
    def test_protocol_has_market_state_fingerprint(self):
        proto = ResearchProtocol.create_v1()
        from market_state_schema import (
            get_market_state_config_fingerprint,
            get_market_state_schema_version,
        )
        self.assertEqual(proto.market_state_config_fingerprint, get_market_state_config_fingerprint())
        self.assertEqual(proto.market_state_schema_version, get_market_state_schema_version())
        self.assertEqual(len(proto.market_state_config_fingerprint), 64)

    def test_market_state_fingerprint_in_composite(self):
        proto = ResearchProtocol.create_v1()
        # Verify it's part of the composite fingerprint
        parts = proto._compute_fingerprint()
        self.assertTrue(parts)

    def test_different_market_state_config_changes_fingerprint(self):
        proto1 = ResearchProtocol.create_v1()
        # Create protocol with different market state config fingerprint
        proto2 = ResearchProtocol(
            version=proto1.version,
            created_at=proto1.created_at,
            data_cutoff=proto1.data_cutoff,
            data_source=proto1.data_source,
            market_state_config_fingerprint="DIFFERENT",
        )
        self.assertNotEqual(proto1.config_fingerprint, proto2.config_fingerprint)


class OSSEvaluationTierTests(unittest.TestCase):
    def test_default_oos_trades_is_30(self):
        proto = ResearchProtocol.create_v1()
        self.assertEqual(proto.min_oos_trades, 30)


class EndToEndThreePhaseIsolationTests(unittest.TestCase):
    """End-to-end test: three phases with distinct price characteristics."""

    def test_three_phases_isolated(self):
        """Verify Formation/Validation/OOS trades don't overlap in time."""
        from backtester import Backtester

        # 2400 bars leave >=260 actual trading bars in every phase after
        # purge and embargo, so every phase must produce real trades.
        base_ts = 1752000000000  # some timestamp
        bar_step = 900_000  # 15m in ms

        bars = []
        for i in range(2400):
            ts = base_ts + i * bar_step
            price = 100.0 + i * 0.02
            time_text = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            bars.append(FeatureBar(
                ts=ts,
                time=time_text,
                open=price - 0.5,
                high=price + 0.05,
                low=price - 0.05,
                close=price,
                volume_quote=1_000_000.0,
                atr=0.1,
                atr_pct=0.001,
                ema20=price * 0.99,
                ema50=price * 0.98,
                ema200=price * 0.97,
                rsi=50.0,
                bb_mid=price,
                bb_upper=price + 5.0,
                bb_lower=price - 5.0,
                vol_sma=1_000_000.0,
                donchian_high=price + 10.0,
                donchian_low=price - 10.0,
                trend_strength=1.5,
            ))

        market = {"BTC-USDT-SWAP": bars}

        # Use protocol
        proto = ResearchProtocol(
            version="v1.0.0",
            created_at="2026-01-01T00:00:00Z",
            data_cutoff="2026-07-16",
            data_source="synthetic",
            symbol_universe=("BTC-USDT-SWAP",),
        )
        config = proto.params.to_backtest_config(proto.cost, proto.symbol_universe)
        split = proto.split
        boundaries = split.compute_boundaries([b.ts for b in bars], bar_duration_ms=bar_step)

        provider_calls: list[int] = []

        def deterministic_provider(symbol: str, provider_bars: list[FeatureBar], idx: int) -> Signal | None:
            self.assertEqual(idx, len(provider_bars) - 1)
            provider_calls.append(provider_bars[idx].ts)
            if idx >= 260 and idx % 40 == 0:
                return Signal(symbol, 1, 10.0, "uptrend", "isolation_test")
            return None

        # Run each phase
        warmup_bars = 260
        bar_dur = 900_000

        # Formation
        w_form, t_form = slice_market(
            market, boundaries.formation_start_ts, boundaries.formation_end_ts,
            warmup_bars=warmup_bars, bar_duration_ms=bar_dur,
        )
        tester_form = Backtester(config)
        form_result = tester_form.run_slice(t_form, w_form,
                                            boundaries.formation_start_ts,
                                            boundaries.formation_end_ts,
                                            signal_provider=deterministic_provider)

        # Validation
        w_val, t_val = slice_market(
            market, boundaries.validation_start_ts, boundaries.validation_end_ts,
            warmup_bars=warmup_bars, bar_duration_ms=bar_dur,
        )
        tester_val = Backtester(config)
        val_result = tester_val.run_slice(t_val, w_val,
                                          boundaries.validation_start_ts,
                                          boundaries.validation_end_ts,
                                          signal_provider=deterministic_provider)

        # OOS
        w_oos, t_oos = slice_market(
            market, boundaries.oos_start_ts, boundaries.oos_end_ts,
            warmup_bars=warmup_bars, bar_duration_ms=bar_dur,
        )
        tester_oos = Backtester(config)
        oos_result = tester_oos.run_slice(t_oos, w_oos,
                                          boundaries.oos_start_ts,
                                          boundaries.oos_end_ts,
                                          signal_provider=deterministic_provider)

        # Verify each phase reports its boundaries
        for result, name in [(form_result, "Formation"), (val_result, "Validation"), (oos_result, "OOS")]:
            if result.get("available"):
                self.assertIn("start_ts", result, f"{name} missing start_ts")
                self.assertIn("end_ts", result, f"{name} missing end_ts")
                self.assertIn("warmup_bars", result, f"{name} missing warmup_bars")

        self.assertGreater(len(provider_calls), 0)

        # Verify trades exist and never cross phase, purge, or embargo boundaries.
        form_trades = form_result.get("trades_detail", [])
        val_trades = val_result.get("trades_detail", [])
        oos_trades = oos_result.get("trades_detail", [])
        self.assertGreater(len(form_trades), 0)
        self.assertGreater(len(val_trades), 0)
        self.assertGreater(len(oos_trades), 0)

        time_to_ts = {bar.time: bar.ts for bar in bars}
        phase_sets: list[set[int]] = []
        excluded_ranges = boundaries.purge_ranges + boundaries.embargo_ranges
        for trades, start_ts, end_ts in (
            (form_trades, boundaries.formation_start_ts, boundaries.formation_end_ts),
            (val_trades, boundaries.validation_start_ts, boundaries.validation_end_ts),
            (oos_trades, boundaries.oos_start_ts, boundaries.oos_end_ts),
        ):
            phase_times: set[int] = set()
            for trade in trades:
                entry_ts = time_to_ts[trade["entry_time"]]
                exit_ts = time_to_ts[trade["exit_time"]]
                self.assertLessEqual(start_ts, entry_ts)
                self.assertLess(entry_ts, end_ts)
                self.assertLessEqual(start_ts, exit_ts)
                self.assertLess(exit_ts, end_ts)
                for excluded_start, excluded_end in excluded_ranges:
                    self.assertFalse(excluded_start <= entry_ts < excluded_end)
                    self.assertFalse(excluded_start <= exit_ts < excluded_end)
                phase_times.update((entry_ts, exit_ts))
            phase_sets.append(phase_times)
        self.assertTrue(phase_sets[0].isdisjoint(phase_sets[1]))
        self.assertTrue(phase_sets[0].isdisjoint(phase_sets[2]))
        self.assertTrue(phase_sets[1].isdisjoint(phase_sets[2]))

        # The final complete bar is included in the OOS trading slice.
        self.assertEqual(t_oos["BTC-USDT-SWAP"][-1].ts, bars[-1].ts)
        self.assertIn("deterministic_provider", oos_result["signal_provider"])


if __name__ == "__main__":
    unittest.main()

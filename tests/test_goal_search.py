import unittest
import tempfile
import json
from dataclasses import asdict
from pathlib import Path

from config import BacktestConfig
from goal_search import (
    audit_goal_results,
    parse_window_targets,
    restore_config_from_report,
    resolve_config_for_search_window,
    candidate_stream,
    market_feature_flags_for_configs,
    seeded_candidate_stream,
    score_goal_results,
)


class GoalSearchTests(unittest.TestCase):
    def test_score_prioritizes_windows_above_profit_target(self):
        one_pass = {
            60: {"pnl": 12.0, "max_drawdown_pct": 20.0},
            30: {"pnl": 5.0, "max_drawdown_pct": 10.0},
        }
        two_pass = {
            60: {"pnl": 11.0, "max_drawdown_pct": 50.0},
            30: {"pnl": 10.5, "max_drawdown_pct": 40.0},
        }

        self.assertGreater(score_goal_results(two_pass, 10.0), score_goal_results(one_pass, 10.0))

    def test_score_uses_min_gap_when_pass_count_matches(self):
        worse_gap = {
            60: {"pnl": 15.0, "max_drawdown_pct": 20.0},
            30: {"pnl": 2.0, "max_drawdown_pct": 10.0},
        }
        better_gap = {
            60: {"pnl": 11.0, "max_drawdown_pct": 20.0},
            30: {"pnl": 8.0, "max_drawdown_pct": 10.0},
        }

        self.assertGreater(score_goal_results(better_gap, 10.0), score_goal_results(worse_gap, 10.0))

    def test_parse_window_targets_supports_absolute_profit_goal(self):
        self.assertEqual(parse_window_targets("30:200,365:2000"), {30: 200.0, 365: 2000.0})

    def test_audit_goal_results_reports_each_target_window(self):
        results = {
            30: {"pnl": 210.0, "max_drawdown_pct": 32.0, "trades": 24, "win_rate": 0.7},
            365: {"pnl": 1500.0, "max_drawdown_pct": 45.0, "trades": 180, "win_rate": 0.62},
        }

        audit = audit_goal_results(results, {30: 200.0, 365: 2000.0}, max_drawdown_pct=55.0)

        self.assertFalse(audit["complete"])
        self.assertEqual(audit["passed_windows"], [30])
        self.assertIn("365d pnl 1500 < 2000", audit["failures"])

    def test_score_uses_per_window_targets(self):
        short_window_only = {
            30: {"pnl": 220.0, "max_drawdown_pct": 20.0, "trades": 20},
            365: {"pnl": 100.0, "max_drawdown_pct": 20.0, "trades": 100},
        }
        closer_to_both_targets = {
            30: {"pnl": 180.0, "max_drawdown_pct": 20.0, "trades": 20},
            365: {"pnl": 1900.0, "max_drawdown_pct": 20.0, "trades": 100},
        }

        self.assertGreater(
            score_goal_results(closer_to_both_targets, {30: 200.0, 365: 2000.0}),
            score_goal_results(short_window_only, {30: 200.0, 365: 2000.0}),
        )

    def test_score_penalizes_zero_trade_candidates(self):
        zero_trade_candidate = {
            30: {"pnl": 0.0, "max_drawdown_pct": 0.0, "trades": 0},
            365: {"pnl": 0.0, "max_drawdown_pct": 0.0, "trades": 0},
        }
        active_candidate = {
            30: {"pnl": -5.0, "max_drawdown_pct": 10.0, "trades": 12},
            365: {"pnl": -20.0, "max_drawdown_pct": 15.0, "trades": 80},
        }

        self.assertGreater(
            score_goal_results(active_candidate, {30: 200.0, 365: 2000.0}, {30: 8, 365: 50}),
            score_goal_results(zero_trade_candidate, {30: 200.0, 365: 2000.0}, {30: 8, 365: 50}),
        )

    def test_restore_config_from_report_uses_report_config(self):
        base = BacktestConfig()
        payload = {"config": asdict(base) | {"risk_per_trade": 0.42, "unknown": "ignored"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            restored = restore_config_from_report(path, base)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.risk_per_trade, 0.42)

    def test_seeded_candidate_stream_uses_top_configs_from_search_reports(self):
        base = BacktestConfig()
        payload = {"top": [{"full_config": asdict(base) | {"risk_per_trade": 0.77}}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "search.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            candidates = list(seeded_candidate_stream(base, 1, 7, (path,)))

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].risk_per_trade, 0.77)

    def test_seeded_candidate_stream_mutates_seed_configs(self):
        base = BacktestConfig()
        payload = {
            "top": [
                {
                    "full_config": asdict(base)
                    | {"risk_per_trade": 0.77, "excluded_symbols": ("BTC-USDT-SWAP",)}
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "search.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            candidates = list(seeded_candidate_stream(base, 2, 7, (path,)))

        self.assertEqual(candidates[1].excluded_symbols, ("BTC-USDT-SWAP",))
        self.assertNotEqual(candidates[1].risk_per_trade, 0.77)

    def test_seeded_candidate_stream_respects_trial_limit(self):
        base = BacktestConfig()

        candidates = list(seeded_candidate_stream(base, 3, 7, ()))

        self.assertEqual(len(candidates), 3)

    def test_resolve_config_for_search_window_can_keep_candidate_config(self):
        config = BacktestConfig(risk_per_trade=1.23)

        resolved = resolve_config_for_search_window(config, 365, ("BTC-USDT-SWAP",), "base")

        self.assertEqual(resolved.risk_per_trade, 1.23)

    def test_resolve_config_for_search_window_can_apply_window_profile(self):
        config = BacktestConfig(risk_per_trade=1.23)

        resolved = resolve_config_for_search_window(config, 365, ("BTC-USDT-SWAP",), "window")

        self.assertNotEqual(resolved.risk_per_trade, 1.23)

    def test_candidate_stream_includes_sprint_risk_cap_candidate(self):
        base = BacktestConfig()

        candidates = list(candidate_stream(base, 8, 7))

        self.assertTrue(any(item.rm_max_total_position_pct > base.rm_max_total_position_pct for item in candidates))

    def test_market_feature_flags_for_configs_include_enabled_modules(self):
        configs = [
            BacktestConfig(enable_funding_module=True),
            BacktestConfig(enable_open_interest_module=True, enable_trade_flow_module=True),
        ]

        flags = market_feature_flags_for_configs(configs)

        self.assertEqual(
            flags,
            {
                "include_funding": True,
                "include_open_interest": True,
                "include_trade_flow": True,
                "include_order_book": False,
            },
        )


if __name__ == "__main__":
    unittest.main()

import unittest

from config import BacktestConfig
from dynamic_router_experiment import (
    apply_router_profile,
    build_router_profile,
    build_transition_long_variants,
    filter_ranked_configs,
)


class DynamicRouterExperimentTests(unittest.TestCase):
    def test_build_router_profile_allows_strong_and_blocks_weak(self):
        adaptation = {
            "strategies": [
                {"reason": "transition_breakout_long", "adaptability_cn": "强"},
                {"reason": "trend_long", "adaptability_cn": "弱"},
                {"reason": "range_revert_long", "adaptability_cn": "弱"},
            ]
        }

        profile = build_router_profile(adaptation, mode="conservative")

        self.assertEqual(profile["allowed_reasons"], ("transition_breakout_long",))
        self.assertEqual(profile["blocked_reasons"], ("range_revert_long", "trend_long"))

    def test_balanced_profile_allows_promising_weak_transition_short(self):
        adaptation = {
            "strategies": [
                {"reason": "transition_breakout_long", "adaptability_cn": "强", "pnl": 10, "median_month_pnl": 2, "profit_month_ratio": 0.8, "win_rate": 0.53, "trades": 50},
                {"reason": "transition_breakout_short", "adaptability_cn": "弱", "pnl": 8, "median_month_pnl": -1, "profit_month_ratio": 0.5, "win_rate": 0.66, "trades": 40},
                {"reason": "range_revert_short", "adaptability_cn": "弱", "pnl": 20, "median_month_pnl": -40, "profit_month_ratio": 0.3, "win_rate": 0.62, "trades": 400},
            ]
        }

        profile = build_router_profile(adaptation, mode="balanced")

        self.assertEqual(profile["allowed_reasons"], ("transition_breakout_long", "transition_breakout_short"))
        self.assertEqual(profile["blocked_reasons"], ("range_revert_short",))

    def test_cautious_profile_downweights_promising_weak_strategies(self):
        adaptation = {
            "strategies": [
                {"reason": "transition_breakout_long", "adaptability_cn": "强", "pnl": 10, "median_month_pnl": 2, "profit_month_ratio": 0.8, "win_rate": 0.53, "trades": 50},
                {"reason": "transition_breakout_short", "adaptability_cn": "弱", "pnl": 8, "median_month_pnl": -1, "profit_month_ratio": 0.5, "win_rate": 0.66, "trades": 40},
            ]
        }

        profile = build_router_profile(adaptation, mode="cautious")

        self.assertEqual(profile["allowed_reasons"], ("transition_breakout_long", "transition_breakout_short"))
        self.assertEqual(profile["reason_risk_multipliers"], {"transition_breakout_short": 0.35})

    def test_apply_router_profile_enables_router_on_config(self):
        profile = {
            "allowed_reasons": ("transition_breakout_long",),
            "blocked_reasons": ("trend_long",),
            "reason_risk_multipliers": {"transition_breakout_short": 0.35},
        }

        routed = apply_router_profile(BacktestConfig(enable_dynamic_strategy_router=False), profile)

        self.assertTrue(routed.enable_dynamic_strategy_router)
        self.assertEqual(routed.router_allowed_reasons, ("transition_breakout_long",))
        self.assertEqual(routed.router_blocked_reasons, ("trend_long",))
        self.assertEqual(routed.reason_risk_multipliers["transition_breakout_short"], 0.35)

    def test_filter_ranked_configs_keeps_requested_ranks_in_order(self):
        ranked = [
            {"rank": "a#1", "config": object()},
            {"rank": "a#7", "config": object()},
            {"rank": "b#3", "config": object()},
        ]

        filtered = filter_ranked_configs(ranked, ("b#3", "a#7"))

        self.assertEqual([item["rank"] for item in filtered], ["a#7", "b#3"])

    def test_build_transition_long_variants_changes_only_targeted_fields(self):
        ranked = [{"rank": "seed#1", "config": BacktestConfig(min_score=3.0, risk_per_trade=0.4)}]

        variants = build_transition_long_variants(ranked)

        self.assertGreater(len(variants), 1)
        self.assertTrue(any(item["rank"].startswith("seed#1.transition") for item in variants[1:]))
        self.assertTrue(all(item["config"].enable_dynamic_strategy_router == ranked[0]["config"].enable_dynamic_strategy_router for item in variants))


if __name__ == "__main__":
    unittest.main()

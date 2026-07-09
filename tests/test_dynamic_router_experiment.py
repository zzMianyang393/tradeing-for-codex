import unittest

from config import BacktestConfig
from dynamic_router_experiment import (
    apply_router_profile,
    build_router_profile,
    build_transition_long_variants,
    compact_result,
    filter_ranked_configs,
    rank_aggregate_prefilter_results,
    rank_prefilter_results,
    score_prefilter_result,
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
        self.assertEqual(profile["reason_allowed_regimes"]["transition_breakout_long"], ("transition",))
        self.assertEqual(profile["reason_allowed_regimes_cn"]["transition_breakout_long"], ("趋势转换",))

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

    def test_trend_short_factor_profile_allows_only_gated_short_candidate(self):
        adaptation = {
            "strategies": [
                {"reason": "transition_breakout_long", "adaptability_cn": "强"},
                {"reason": "trend_short", "adaptability_cn": "弱"},
                {"reason": "trend_long", "adaptability_cn": "弱"},
            ]
        }

        profile = build_router_profile(adaptation, mode="trend_short_factor")

        self.assertEqual(profile["allowed_reasons"], ("transition_breakout_long", "trend_short"))
        self.assertEqual(profile["blocked_reasons"], ("trend_long",))
        self.assertEqual(profile["reason_allowed_regimes"]["trend_short"], ("downtrend",))
        self.assertEqual(profile["reason_risk_multipliers"]["trend_short"], 0.35)
        self.assertTrue(profile["trend_short_factor_gate_enabled"])

    def test_trend_short_factor_profile_adds_candidate_even_when_audit_row_is_missing(self):
        adaptation = {
            "strategies": [
                {"reason": "transition_breakout_long", "adaptability_cn": "强"},
                {"reason": "trend_long", "adaptability_cn": "弱"},
            ]
        }

        profile = build_router_profile(adaptation, mode="trend_short_factor")

        self.assertEqual(profile["allowed_reasons"], ("transition_breakout_long", "trend_short"))
        self.assertEqual(profile["reason_allowed_regimes"]["trend_short"], ("downtrend",))
        self.assertEqual(profile["reason_risk_multipliers"]["trend_short"], 0.35)

    def test_apply_router_profile_enables_router_on_config(self):
        profile = {
            "allowed_reasons": ("transition_breakout_long",),
            "blocked_reasons": ("trend_long",),
            "reason_risk_multipliers": {"transition_breakout_short": 0.35},
            "reason_allowed_regimes": {"transition_breakout_long": ("transition",)},
        }

        routed = apply_router_profile(BacktestConfig(enable_dynamic_strategy_router=False), profile)

        self.assertTrue(routed.enable_dynamic_strategy_router)
        self.assertEqual(routed.router_allowed_reasons, ("transition_breakout_long",))
        self.assertEqual(routed.router_blocked_reasons, ("trend_long",))
        self.assertEqual(routed.reason_risk_multipliers["transition_breakout_short"], 0.35)
        self.assertEqual(routed.router_reason_allowed_regimes["transition_breakout_long"], ("transition",))

    def test_apply_router_profile_enables_trend_short_factor_gate(self):
        profile = {
            "allowed_reasons": ("trend_short",),
            "blocked_reasons": (),
            "trend_short_factor_gate_enabled": True,
        }

        routed = apply_router_profile(BacktestConfig(), profile)

        self.assertTrue(routed.router_trend_short_factor_gate_enabled)

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

    def test_build_transition_long_variants_searches_signal_thresholds(self):
        ranked = [{"rank": "seed#1", "config": BacktestConfig()}]

        variants = build_transition_long_variants(ranked)

        self.assertTrue(
            any(
                item["config"].transition_long_pullback_min_volume_ratio
                != ranked[0]["config"].transition_long_pullback_min_volume_ratio
                for item in variants[1:]
            )
        )
        self.assertTrue(
            any(
                item["config"].transition_long_volume_rsi_max
                != ranked[0]["config"].transition_long_volume_rsi_max
                for item in variants[1:]
            )
        )

    def test_build_transition_long_variants_can_enable_consolidation_pattern(self):
        ranked = [{"rank": "seed#1", "config": BacktestConfig()}]

        variants = build_transition_long_variants(ranked)

        self.assertTrue(
            any(item["config"].transition_long_consolidation_enabled for item in variants[1:])
        )

    def test_compact_result_keeps_router_rejection_stats(self):
        result = {
            "end_equity": 13.0,
            "pnl": 3.0,
            "router_rejections": {
                "total": 2,
                "by_rejection_reason": {"configured_regime_mismatch": 2},
            },
        }

        compacted = compact_result(result)

        self.assertEqual(
            {"total": 2, "by_rejection_reason": {"configured_regime_mismatch": 2}},
            compacted["router_rejections"],
        )

    def test_rank_prefilter_results_prefers_profit_then_lower_drawdown_then_trades(self):
        results = [
            {"rank": "low-profit", "result": {"pnl": 1.0, "max_drawdown_pct": 5.0, "trades": 20}},
            {"rank": "best", "result": {"pnl": 2.0, "max_drawdown_pct": 8.0, "trades": 6}},
            {"rank": "same-profit-high-dd", "result": {"pnl": 2.0, "max_drawdown_pct": 18.0, "trades": 30}},
            {"rank": "same-profit-low-trades", "result": {"pnl": 2.0, "max_drawdown_pct": 8.0, "trades": 3}},
        ]

        ranked = rank_prefilter_results(results, limit=2)

        self.assertEqual(["best", "same-profit-low-trades"], [item["rank"] for item in ranked])

    def test_rank_prefilter_results_preserves_always_keep_ranks(self):
        results = [
            {"rank": "baseline", "result": {"pnl": -1.0, "max_drawdown_pct": 5.0, "trades": 2}},
            {"rank": "variant-a", "result": {"pnl": 3.0, "max_drawdown_pct": 8.0, "trades": 8}},
            {"rank": "variant-b", "result": {"pnl": 2.0, "max_drawdown_pct": 6.0, "trades": 6}},
        ]

        ranked = rank_prefilter_results(results, limit=1, always_keep_ranks=("baseline",))

        self.assertEqual(["baseline", "variant-a"], [item["rank"] for item in ranked])

    def test_score_prefilter_result_penalizes_sparse_and_structurally_distant_candidate(self):
        baseline = {
            "pnl": 1.8,
            "max_drawdown_pct": 10.0,
            "trades": 8,
            "by_reason": {"transition_breakout_long": {"trades": 8}},
        }
        sparse_high_profit = {
            "pnl": 4.2,
            "max_drawdown_pct": 8.0,
            "trades": 1,
            "by_reason": {"transition_breakout_long": {"trades": 1}},
        }
        steadier_candidate = {
            "pnl": 2.4,
            "max_drawdown_pct": 7.0,
            "trades": 7,
            "by_reason": {"transition_breakout_long": {"trades": 7}},
        }

        sparse_score = score_prefilter_result(sparse_high_profit, baseline_result=baseline)
        steady_score = score_prefilter_result(steadier_candidate, baseline_result=baseline)

        self.assertGreater(steady_score, sparse_score)

    def test_rank_aggregate_prefilter_results_prefers_cross_window_consistency(self):
        by_window = {
            90: [
                {"rank": "short-window-winner", "result": {"pnl": 5.0, "max_drawdown_pct": 7.0, "trades": 8}},
                {"rank": "consistent", "result": {"pnl": 2.0, "max_drawdown_pct": 7.0, "trades": 7}},
            ],
            180: [
                {"rank": "short-window-winner", "result": {"pnl": -4.0, "max_drawdown_pct": 28.0, "trades": 4}},
                {"rank": "consistent", "result": {"pnl": 1.5, "max_drawdown_pct": 9.0, "trades": 7}},
            ],
        }

        ranked = rank_aggregate_prefilter_results(by_window, limit=1)

        self.assertEqual(["consistent"], [item["rank"] for item in ranked])


if __name__ == "__main__":
    unittest.main()

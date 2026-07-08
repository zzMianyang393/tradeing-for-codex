import unittest

from config import BacktestConfig
from staged_goal import (
    StageSpec,
    aggregate_stage_results,
    build_stage_specs,
    build_multi_sprint_stage_specs,
    config_for_stage,
    effective_grid_limits,
    expand_ranked_configs_with_mutations,
    is_grid_search_requested,
    load_top_configs_from_report_payload,
    rank_staged_config_pairs,
    staged_market_feature_flags,
    split_stage_ranges,
)


class StagedGoalTests(unittest.TestCase):
    def test_split_stage_ranges_uses_contiguous_latest_window(self):
        timeline = [day * 86_400_000 for day in range(10)]

        ranges = split_stage_ranges(timeline, total_days=6, stages=(2, 4))

        self.assertEqual(ranges, [(3 * 86_400_000, 5 * 86_400_000), (5 * 86_400_000, 9 * 86_400_000)])

    def test_config_for_stage_sets_start_equity_from_previous_stage(self):
        base = BacktestConfig(start_equity=10.0)
        stage = StageSpec("growth", 335, base)

        resolved = config_for_stage(stage, start_equity=42.0)

        self.assertEqual(resolved.start_equity, 42.0)

    def test_aggregate_stage_results_compounds_equity(self):
        report = aggregate_stage_results(
            start_equity=10.0,
            stage_results=[
                {"name": "sprint", "end_equity": 25.0, "pnl": 15.0, "trades": 8, "max_drawdown_pct": 20.0},
                {"name": "growth", "end_equity": 70.0, "pnl": 45.0, "trades": 30, "max_drawdown_pct": 35.0},
            ],
        )

        self.assertEqual(report["end_equity"], 70.0)
        self.assertEqual(report["pnl"], 60.0)
        self.assertEqual(report["trades"], 38)
        self.assertEqual(report["max_drawdown_pct"], 35.0)

    def test_build_stage_specs_supports_growth_first_order(self):
        sprint = BacktestConfig(risk_per_trade=0.2)
        growth = BacktestConfig(risk_per_trade=0.4)

        stages = build_stage_specs(sprint, growth, order="growth-first")

        self.assertEqual([stage.name for stage in stages], ["growth", "sprint"])
        self.assertEqual([stage.days for stage in stages], [335, 30])

    def test_build_multi_sprint_stage_specs_extends_attack_window(self):
        sprint = BacktestConfig(risk_per_trade=0.2)
        growth = BacktestConfig(risk_per_trade=0.4)

        stages = build_multi_sprint_stage_specs(sprint, growth, total_days=365, sprint_days=30, sprint_count=3)

        self.assertEqual([stage.name for stage in stages], ["growth", "sprint_1", "sprint_2", "sprint_3"])
        self.assertEqual([stage.days for stage in stages], [275, 30, 30, 30])
        self.assertEqual(sum(stage.days for stage in stages), 365)

    def test_load_top_configs_from_report_payload_preserves_rank(self):
        payload = {
            "top": [
                {"full_config": {"risk_per_trade": 0.11}},
                {"config": {"risk_per_trade": 0.22}},
            ]
        }

        ranked = load_top_configs_from_report_payload(payload, limit=2)

        self.assertEqual([item["rank"] for item in ranked], [1, 2])
        self.assertEqual([item["config"].risk_per_trade for item in ranked], [0.11, 0.22])

    def test_rank_staged_config_pairs_sorts_reports_by_pnl(self):
        sprint_configs = [
            {"rank": 1, "config": BacktestConfig(risk_per_trade=0.1)},
            {"rank": 2, "config": BacktestConfig(risk_per_trade=0.2)},
        ]
        growth_configs = [
            {"rank": 1, "config": BacktestConfig(max_positions=1)},
            {"rank": 2, "config": BacktestConfig(max_positions=2)},
        ]

        def fake_runner(stages, order):
            sprint_rank = 1 if stages[0 if order == "sprint-first" else 1].config.risk_per_trade == 0.1 else 2
            growth_rank = 1 if stages[1 if order == "sprint-first" else 0].config.max_positions == 1 else 2
            pnl = sprint_rank * 10 + growth_rank
            return {"pnl": pnl, "end_equity": 10.0 + pnl, "trades": pnl, "max_drawdown_pct": 10.0}

        ranked = rank_staged_config_pairs(
            sprint_configs=sprint_configs,
            growth_configs=growth_configs,
            orders=("sprint-first", "growth-first"),
            runner=fake_runner,
        )

        self.assertEqual(ranked[0]["pnl"], 22)
        self.assertEqual(ranked[0]["sprint_rank"], 2)
        self.assertEqual(ranked[0]["growth_rank"], 2)
        self.assertIn(ranked[0]["order"], {"sprint-first", "growth-first"})

    def test_rank_staged_config_pairs_can_use_custom_stage_builder(self):
        sprint_configs = [{"rank": 1, "config": BacktestConfig(risk_per_trade=0.1)}]
        growth_configs = [{"rank": 1, "config": BacktestConfig(risk_per_trade=0.2)}]
        observed_stage_names = []

        def stage_builder(sprint, growth, order):
            return (StageSpec("growth", 305, growth), StageSpec("sprint_1", 30, sprint), StageSpec("sprint_2", 30, sprint))

        def fake_runner(stages, order):
            observed_stage_names.extend(stage.name for stage in stages)
            return {"pnl": 1.0, "end_equity": 11.0, "trades": 2, "max_drawdown_pct": 10.0}

        rank_staged_config_pairs(
            sprint_configs=sprint_configs,
            growth_configs=growth_configs,
            orders=("growth-first",),
            runner=fake_runner,
            stage_builder=stage_builder,
        )

        self.assertEqual(observed_stage_names, ["growth", "sprint_1", "sprint_2"])

    def test_staged_market_feature_flags_use_all_candidate_configs(self):
        sprint_configs = [
            {"rank": 1, "config": BacktestConfig()},
            {"rank": 2, "config": BacktestConfig(enable_trade_flow_module=True)},
        ]
        growth_configs = [
            {"rank": 1, "config": BacktestConfig(enable_funding_module=True)},
            {"rank": 2, "config": BacktestConfig(enable_open_interest_module=True)},
        ]

        flags = staged_market_feature_flags(sprint_configs, growth_configs)

        self.assertEqual(
            flags,
            {
                "include_funding": True,
                "include_open_interest": True,
                "include_trade_flow": True,
                "include_order_book": False,
            },
        )

    def test_effective_grid_limits_can_control_sprint_and_growth_independently(self):
        self.assertEqual(effective_grid_limits(grid_limit=4, sprint_grid_limit=7, growth_grid_limit=3), (7, 3))
        self.assertEqual(effective_grid_limits(grid_limit=4, sprint_grid_limit=0, growth_grid_limit=0), (4, 4))

    def test_is_grid_search_requested_checks_independent_limits(self):
        self.assertTrue(is_grid_search_requested(grid_limit=0, sprint_grid_limit=6, growth_grid_limit=0))
        self.assertTrue(is_grid_search_requested(grid_limit=0, sprint_grid_limit=0, growth_grid_limit=3))
        self.assertFalse(is_grid_search_requested(grid_limit=0, sprint_grid_limit=0, growth_grid_limit=0))

    def test_expand_ranked_configs_with_mutations_keeps_originals_and_labels_mutations(self):
        ranked = [{"rank": 5, "config": BacktestConfig(risk_per_trade=0.4)}]

        expanded = expand_ranked_configs_with_mutations(ranked, seed=11, mutations_per_config=2)

        self.assertEqual(expanded[0]["rank"], 5)
        self.assertEqual([item["source_rank"] for item in expanded[1:]], [5, 5])
        self.assertEqual([item["mutation"] for item in expanded[1:]], [1, 2])
        self.assertTrue(all(item["config"].risk_per_trade != 0.4 for item in expanded[1:]))


if __name__ == "__main__":
    unittest.main()

import unittest

from historical_regime_validation import (
    build_strategy_targets,
    build_strategy_manifest,
    config_fingerprint,
    historical_windows,
    judge_historical_support,
    resolve_target_config,
)


class HistoricalRegimeValidationTests(unittest.TestCase):
    def test_historical_windows_excludes_source_sample_and_steps_backwards(self):
        day = 86_400_000
        timeline = [index * day for index in range(1000)]
        source_start = 700 * day

        windows = historical_windows(
            timeline,
            source_start_ts=source_start,
            window_days=30,
            step_days=30,
            lookback_days=120,
        )

        self.assertEqual(windows, [(580 * day, 610 * day), (610 * day, 640 * day), (640 * day, 670 * day), (670 * day, 700 * day)])
        self.assertTrue(all(end <= source_start for _, end in windows))

    def test_build_strategy_targets_uses_month_rank_regime_and_reason(self):
        report = {
            "months": [
                {
                    "month": 2,
                    "rank": "goal#8",
                    "result": {
                        "return_pct": 82.8,
                        "max_drawdown_pct": 22.69,
                        "dominant_regime": "uptrend",
                        "dominant_reason": "trend_long",
                    },
                }
            ]
        }

        targets = build_strategy_targets(report, [2])

        self.assertEqual(targets[0]["rank"], "goal#8")
        self.assertEqual(targets[0]["regime"], "uptrend")
        self.assertEqual(targets[0]["reason"], "trend_long")
        self.assertEqual(targets[0]["target_return_pct"], 82.8)

    def test_resolve_target_config_matches_rank_without_using_month_result(self):
        configs = [
            {"rank": "goal#1", "config": object()},
            {"rank": "goal#8", "config": "wanted"},
        ]

        self.assertEqual(resolve_target_config("goal#8", configs), "wanted")

    def test_judge_historical_support_marks_weak_same_regime_decay_as_high_risk(self):
        target = {
            "target_return_pct": 80.0,
            "regime": "uptrend",
            "reason": "trend_long",
            "target_drawdown_pct": 25.0,
        }
        validations = [
            {"return_pct": -4.0, "pnl": -0.4, "dominant_regime": "uptrend", "dominant_reason": "trend_long", "max_drawdown_pct": 8.0},
            {"return_pct": 5.0, "pnl": 0.5, "dominant_regime": "uptrend", "dominant_reason": "trend_long", "max_drawdown_pct": 10.0},
            {"return_pct": 30.0, "pnl": 3.0, "dominant_regime": "range", "dominant_reason": "range_revert_long", "max_drawdown_pct": 12.0},
        ]

        support = judge_historical_support(target, validations)

        self.assertEqual(support["risk_level"], "high")
        self.assertEqual(support["same_regime_windows"], 2)
        self.assertIn("same-regime median return decays too much", support["risk_reasons"])

    def test_config_fingerprint_is_stable_for_equal_configs(self):
        class Config:
            risk_per_trade = 0.1
            max_margin_fraction = 0.6
            enable_attack_module = False

        self.assertEqual(config_fingerprint(Config()), config_fingerprint(Config()))

    def test_build_strategy_manifest_marks_reused_parameter_sets(self):
        class Config:
            risk_per_trade = 0.1
            max_margin_fraction = 0.6
            max_total_margin_fraction = 0.5
            stop_atr = 2.0
            take_profit_atr = 1.0
            trailing_atr = 1.5
            max_hold_bars = 8
            range_take_profit_atr = 0.6
            range_trailing_atr = 1.2
            cooldown_bars = 24
            loss_cooldown_bars = 48
            max_positions = 2
            active_symbol_limit = 6
            enable_attack_module = False
            enable_micro_momentum_module = False
            enable_funding_module = False
            enable_open_interest_module = False
            enable_trade_flow_module = False
            enable_order_book_module = False
            enable_long_window_aggressive_profile = False
            enabled_regimes = ("uptrend", "range")

        report = {
            "months": [
                {"month": 1, "rank": "a", "result": {"dominant_regime": "uptrend", "dominant_reason": "trend_long"}},
                {"month": 2, "rank": "b", "result": {"dominant_regime": "range", "dominant_reason": "range_revert_long"}},
            ]
        }
        configs = [{"rank": "a", "config": Config()}, {"rank": "b", "config": Config()}]

        manifest = build_strategy_manifest(report, configs)

        self.assertEqual(manifest[0]["parameter_group"], manifest[1]["parameter_group"])
        self.assertTrue(manifest[0]["same_parameters_as_other_month"])


if __name__ == "__main__":
    unittest.main()

import unittest

from dynamic_router_acceptance import (
    compare_router_reports,
    evaluate_router_report,
    evaluate_window_overfit_risk,
    summarize_router_rejections,
)


class DynamicRouterAcceptanceTests(unittest.TestCase):
    def test_evaluate_router_report_labels_progress_without_goal_pass(self):
        report = {
            "router_profile": {
                "mode": "conservative",
                "allowed_reasons": ["transition_breakout_long"],
                "allowed_reasons_cn": ["转换突破做多"],
            },
            "best": {
                "rank": "seed#7",
                "result": {
                    "end_equity": 13.5609,
                    "pnl": 3.5609,
                    "return_pct": 35.6088,
                    "max_drawdown_pct": 17.985,
                    "trades": 8,
                    "win_rate": 0.375,
                    "by_reason": {
                        "transition_breakout_long": {"trades": 8, "wins": 3, "pnl": 3.687, "win_rate": 0.375}
                    },
                },
            },
        }
        adaptation = {
            "strategies": [
                {
                    "reason": "transition_breakout_long",
                    "strategy_cn": "转换突破做多",
                    "adaptability_cn": "强",
                    "suitable_market_cn": "趋势转换/突破",
                }
            ]
        }

        verdict = evaluate_router_report(report, adaptation, target_end_equity=210.0, min_trades=30)

        self.assertEqual("可继续打磨", verdict["status_cn"])
        self.assertFalse(verdict["target_pass"])
        self.assertEqual("强", verdict["strategies"][0]["adaptability_cn"])
        self.assertIn("交易次数不足", verdict["risk_flags_cn"])
        self.assertIn("未达到收益目标", verdict["risk_flags_cn"])

    def test_evaluate_router_report_flags_weak_allowed_strategy(self):
        report = {
            "router_profile": {
                "mode": "balanced",
                "allowed_reasons": ["transition_breakout_long", "transition_breakout_short"],
                "allowed_reasons_cn": ["转换突破做多", "转换突破做空"],
            },
            "best": {
                "rank": "seed#7",
                "result": {
                    "end_equity": 11.4098,
                    "pnl": 1.4098,
                    "return_pct": 14.0978,
                    "max_drawdown_pct": 24.7359,
                    "trades": 10,
                    "win_rate": 0.3,
                    "by_reason": {
                        "transition_breakout_long": {"trades": 8, "wins": 3, "pnl": 3.2219, "win_rate": 0.375},
                        "transition_breakout_short": {"trades": 2, "wins": 0, "pnl": -1.6709, "win_rate": 0.0},
                    },
                },
            },
        }
        adaptation = {
            "strategies": [
                {"reason": "transition_breakout_long", "strategy_cn": "转换突破做多", "adaptability_cn": "强"},
                {"reason": "transition_breakout_short", "strategy_cn": "转换突破做空", "adaptability_cn": "弱"},
            ]
        }

        verdict = evaluate_router_report(report, adaptation)

        self.assertEqual("不建议实盘启用", verdict["status_cn"])
        self.assertIn("包含弱适应策略", verdict["risk_flags_cn"])
        self.assertEqual(-1.6709, verdict["strategies"][1]["pnl"])

    def test_compare_router_reports_marks_degradation(self):
        conservative = {
            "label": "保守路由",
            "verdict": {
                "result": {"end_equity": 13.5609, "max_drawdown_pct": 17.985, "trades": 8},
                "status_cn": "可继续打磨",
            },
        }
        balanced = {
            "label": "平衡路由",
            "verdict": {
                "result": {"end_equity": 11.4098, "max_drawdown_pct": 24.7359, "trades": 10},
                "status_cn": "不建议实盘启用",
            },
        }

        comparison = compare_router_reports([conservative, balanced])

        self.assertEqual("保守路由", comparison["best_label"])
        self.assertEqual("收益下降且回撤上升", comparison["comparisons"][0]["judgement_cn"])

    def test_compare_router_reports_marks_unchanged_result(self):
        baseline = {
            "label": "原始路由",
            "verdict": {"result": {"end_equity": 13.0, "max_drawdown_pct": 18.0}},
        }
        same = {
            "label": "变体路由",
            "verdict": {"result": {"end_equity": 13.0, "max_drawdown_pct": 18.0}},
        }

        comparison = compare_router_reports([baseline, same])

        self.assertEqual("收益和回撤持平", comparison["comparisons"][0]["judgement_cn"])

    def test_evaluate_window_overfit_risk_flags_prefilter_winner_that_fails_full_window(self):
        report = {
            "best": {
                "rank": "seed#7.transition3",
                "result": {"pnl": -2.8898, "max_drawdown_pct": 28.8978, "trades": 4},
            },
            "prefilter": {
                "days": [90, 180],
                "selected": [
                    {
                        "rank": "seed#7.transition3",
                        "window_results": {
                            90: {"pnl": 4.0844, "max_drawdown_pct": 6.0, "trades": 8},
                            180: {"pnl": 6.3659, "max_drawdown_pct": 9.0, "trades": 12},
                        },
                    }
                ],
            },
        }

        risk = evaluate_window_overfit_risk(report)

        self.assertEqual("高", risk["risk_cn"])
        self.assertIn("短窗口盈利但完整窗口亏损", risk["evidence_cn"])

    def test_evaluate_router_report_includes_high_overfit_flag(self):
        report = {
            "router_profile": {
                "mode": "conservative",
                "allowed_reasons": ["transition_breakout_long"],
                "allowed_reasons_cn": ["转换突破做多"],
            },
            "best": {
                "rank": "seed#7.transition3",
                "result": {
                    "end_equity": 7.1102,
                    "pnl": -2.8898,
                    "return_pct": -28.8978,
                    "max_drawdown_pct": 28.8978,
                    "trades": 4,
                    "win_rate": 0.0,
                    "by_reason": {
                        "transition_breakout_long": {"trades": 4, "wins": 0, "pnl": -2.8898, "win_rate": 0.0}
                    },
                },
            },
            "prefilter": {
                "days": [90, 180],
                "selected": [
                    {
                        "rank": "seed#7.transition3",
                        "window_results": {
                            90: {"pnl": 4.0844, "max_drawdown_pct": 6.0, "trades": 8},
                            180: {"pnl": 6.3659, "max_drawdown_pct": 9.0, "trades": 12},
                        },
                    }
                ],
            },
        }
        adaptation = {
            "strategies": [
                {
                    "reason": "transition_breakout_long",
                    "strategy_cn": "转换突破做多",
                    "adaptability_cn": "强",
                }
            ]
        }

        verdict = evaluate_router_report(report, adaptation)

        self.assertEqual("高", verdict["overfit_risk"]["risk_cn"])
        self.assertIn("跨窗口失效风险高", verdict["risk_flags_cn"])
        self.assertEqual("不建议实盘启用", verdict["status_cn"])

    def test_summarize_router_rejections_prioritizes_heavily_rejected_strategies(self):
        result = {
            "router_rejections": {
                "total": 2546,
                "by_rejection_reason": {"blocked_reason": 1194, "not_allowed_reason": 1352},
                "by_signal_reason": {
                    "trend_short": 1352,
                    "trend_long": 977,
                    "range_revert_long": 135,
                    "range_revert_short": 80,
                    "transition_breakout_short": 2,
                },
                "by_regime": {"downtrend": 1352, "uptrend": 977, "range": 215, "transition": 2},
            }
        }

        summary = summarize_router_rejections(result)

        self.assertEqual(2546, summary["total"])
        self.assertEqual("趋势做空", summary["top_rejected_strategies"][0]["strategy_cn"])
        self.assertEqual("优先审计", summary["top_rejected_strategies"][0]["action_cn"])
        self.assertIn("候选很多但未准入", summary["diagnosis_cn"][0])

    def test_evaluate_router_report_includes_router_rejection_summary(self):
        report = {
            "router_profile": {
                "mode": "conservative",
                "allowed_reasons": ["transition_breakout_long"],
                "allowed_reasons_cn": ["转换突破做多"],
            },
            "best": {
                "rank": "seed#7",
                "result": {
                    "end_equity": 13.5609,
                    "pnl": 3.5609,
                    "return_pct": 35.6088,
                    "max_drawdown_pct": 17.985,
                    "trades": 8,
                    "win_rate": 0.375,
                    "by_reason": {
                        "transition_breakout_long": {"trades": 8, "wins": 3, "pnl": 3.687, "win_rate": 0.375}
                    },
                    "router_rejections": {
                        "total": 2546,
                        "by_rejection_reason": {"blocked_reason": 1194, "not_allowed_reason": 1352},
                        "by_signal_reason": {"trend_short": 1352, "trend_long": 977},
                        "by_regime": {"downtrend": 1352, "uptrend": 977},
                    },
                },
            },
        }
        adaptation = {
            "strategies": [
                {
                    "reason": "transition_breakout_long",
                    "strategy_cn": "转换突破做多",
                    "adaptability_cn": "强",
                }
            ]
        }

        verdict = evaluate_router_report(report, adaptation, target_end_equity=210.0, min_trades=30)

        self.assertEqual(2546, verdict["router_rejection_summary"]["total"])
        self.assertEqual("趋势做空", verdict["router_rejection_summary"]["top_rejected_strategies"][0]["strategy_cn"])


if __name__ == "__main__":
    unittest.main()

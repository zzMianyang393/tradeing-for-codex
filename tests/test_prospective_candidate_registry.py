from prospective_candidate_registry import build_registry


def test_only_passing_drift_report_becomes_frozen_candidate():
    drift = {
        "status": "frozen_prospective_candidate",
        "candidate_reasons": [],
        "position_fraction": 0.1,
        "max_positions": 5,
        "positive_fold_count": 4,
        "aggregate": {"total_return_pct": 64.0, "max_drawdown_pct": 17.0, "accepted_positions": 787},
    }
    combo = {"result": {"component_attribution": {"ema_continuation_short": {"accepted_positions": 42, "return_contribution_pct": 10.0}}}}
    anatomy = {"monthly_component_pnl": {"positive_month_concentration_by_component": {"ema_continuation_short": 0.43}}}
    report = build_registry(drift, combo, anatomy)
    assert len(report["frozen_candidates"]) == 1
    assert report["ready_for_combo_backtest"] is False
    assert report["watchlist"][0]["status"] == "watchlist_concentration_risk"


def test_failed_drift_report_does_not_enter_frozen_registry():
    report = build_registry({"status": "rejected", "candidate_reasons": ["failed"]}, {}, {})
    assert report["frozen_candidates"] == []


def test_concentrated_uptrend_component_enters_watchlist_not_frozen_candidates():
    uptrend = {
        "components": {
            "persistent_uptrend_ema20_reclaim": {
                "status": "weak_feature_watchlist_concentration_penalty",
                "primary_constant_universe": {
                    "aggregate": {
                        "accepted_positions": 90,
                        "total_return_pct": 4.7,
                        "max_drawdown_pct": 2.1,
                        "top_positive_month_share": 0.38,
                    }
                },
            }
        }
    }
    report = build_registry({"status": "rejected", "candidate_reasons": []}, {}, {}, uptrend)
    assert report["frozen_candidates"] == []
    assert report["watchlist"][-1]["candidate_id"] == "persistent_uptrend_ema20_reclaim_v1"
    assert report["regime_coverage"]["uptrend"] == "watchlist_only"


def test_strict_gate_failed_combo_is_watchlist_only():
    combo = {
        "posthoc_risk_adjusted_combo_watchlist": ["left__right"],
        "pairs": {
            "left__right": {
                "aggregate": {
                    "accepted_positions": 100,
                    "total_return_pct": 10.0,
                    "max_drawdown_pct": 5.1,
                    "top_positive_month_share": 0.2,
                },
                "posthoc_risk_adjusted_interpretation": {
                    "drawdown_excess_percentage_points": 0.1,
                },
            }
        },
    }
    report = build_registry({"status": "rejected", "candidate_reasons": []}, {}, {}, None, combo)
    assert report["watchlist"][-1]["status"] == "combo_watchlist_strict_gate_failed"
    assert report["watchlist"][-1]["allowed_in_combo_backtest"] is False


def test_combo_anatomy_is_attached_without_promoting_watchlist():
    combo = {
        "posthoc_risk_adjusted_combo_watchlist": ["left__right"],
        "pairs": {
            "left__right": {
                "aggregate": {},
                "posthoc_risk_adjusted_interpretation": {},
            }
        },
    }
    anatomy = {
        "pairs": {
            "left__right": {
                "failure_classification": {
                    "classification": "minor_additive_loss",
                    "common_failure": False,
                },
                "watchlist_action": "retain_without_common_failure_flag",
            }
        }
    }
    report = build_registry({"status": "rejected", "candidate_reasons": []}, {}, {}, None, combo, anatomy)
    item = report["watchlist"][-1]
    assert item["drawdown_failure_classification"] == "minor_additive_loss"
    assert item["common_failure"] is False
    assert item["status"] == "combo_watchlist_strict_gate_failed"


def test_posthoc_volume_short_and_pairs_are_non_executable_watchlist_items():
    volume = {
        "posthoc_directional_weak_feature_watchlist": [
            {"component_id": "daily_volume_shock_reversal_v1_short"}
        ],
        "posthoc_short_standalone_diagnostic": {
            "aggregate": {
                "accepted_positions": 75,
                "total_return_pct": 9.3,
                "max_drawdown_pct": 11.8,
                "top_positive_month_share": 0.19,
            }
        },
    }
    complementarity = {"retained_prospective_pair_watchlist": ["volume__uptrend"]}
    report = build_registry(
        {"status": "rejected", "candidate_reasons": []},
        {},
        {},
        None,
        None,
        None,
        volume,
        complementarity,
    )
    assert report["watchlist"][-2]["status"] == "posthoc_directional_weak_feature_watchlist"
    assert report["watchlist"][-1]["status"] == "prospective_pair_comparison_only"
    assert report["watchlist"][-1]["allowed_in_combo_backtest"] is False


def test_posthoc_weekly_short_and_complementary_pair_remain_non_executable():
    weekly = {
        "posthoc_sleeve_weak_feature_watchlist": [
            {"component_id": "weekly_cross_sectional_momentum_v1_short"}
        ],
        "posthoc_short_standalone_diagnostic": {
            "aggregate": {
                "accepted_positions": 234,
                "total_return_pct": 76.8,
                "max_drawdown_pct": 14.4,
                "top_positive_month_share": 0.11,
            }
        },
    }
    complementarity = {
        "retained_prospective_pair_watchlist": ["weekly_short__uptrend"]
    }
    report = build_registry(
        {"status": "rejected", "candidate_reasons": []},
        {},
        {},
        None,
        None,
        None,
        None,
        None,
        weekly,
        complementarity,
    )
    assert report["watchlist"][-2]["status"] == "posthoc_sleeve_weak_feature_watchlist"
    assert report["watchlist"][-2]["allowed_in_combo_backtest"] is False
    assert report["watchlist"][-1]["status"] == "prospective_pair_comparison_only"
    assert report["watchlist"][-1]["allowed_in_combo_backtest"] is False
    assert report["regime_coverage"]["cross_sectional_weakness_continuation"] == "watchlist_only"


def test_posthoc_range_long_fills_range_coverage_without_opening_combo_gate():
    range_report = {
        "posthoc_sleeve_weak_feature_watchlist": [
            {"component_id": "weekly_range_microtrend_continuation_v1_long"}
        ],
        "posthoc_standalone_diagnostics": {
            "weekly_range_microtrend_continuation_v1_long": {
                "aggregate": {
                    "accepted_positions": 76,
                    "total_return_pct": 2.0,
                    "max_drawdown_pct": 2.9,
                    "top_positive_month_share": 0.20,
                }
            }
        },
    }
    complementarity = {
        "retained_prospective_pair_watchlist": ["range_long__uptrend"]
    }
    report = build_registry(
        {"status": "rejected", "candidate_reasons": []},
        {},
        {},
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        range_report,
        complementarity,
    )
    assert report["watchlist"][-2]["status"] == "posthoc_regime_sleeve_weak_feature_watchlist"
    assert report["watchlist"][-2]["allowed_in_combo_backtest"] is False
    assert report["watchlist"][-1]["status"] == "prospective_pair_comparison_only"
    assert report["regime_coverage"]["mean_reverting_range_v2"] == "watchlist_only"


def test_regime_gated_donchian_reenters_only_as_non_executable_weak_feature():
    preflight = {
        "factor_preflight_decisions": [
            {
                "factor_id": "donchian_atr_trend_baseline",
                "fixed_window_signal_count": 1,
                "preflight_status": "eligible_for_shadow_observation_only",
            }
        ]
    }
    report = build_registry(
        {"status": "rejected", "candidate_reasons": []},
        {},
        {},
        legacy_weak_preflight=preflight,
    )
    item = report["watchlist"][-1]
    assert item["candidate_id"] == "donchian_atr_trend_baseline"
    assert item["status"] == "rejected_standalone_regime_gated_weak_feature_watchlist"
    assert item["allowed_in_combo_backtest"] is False
    assert report["safe_to_enable_trading"] is False

"""Research state dashboard: machine-readable overview of all research status.

Aggregates:
  - 111 prototype universe status
  - 13 research_card_priority prototypes
  - Cohort A 28 observations
  - Cohort B current signal count
  - Historical audit results (including frozen factor-expansion audits)
  - Safety gates

This is a READ-ONLY aggregation.  Does NOT derive returns or approve strategies.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def audit_status(report: dict | None) -> str:
    """Normalize current and legacy audit verdict fields without inferring results."""
    if not report:
        return "not_run"
    for split in ("formation", "oos"):
        stats = report.get(split)
        if isinstance(stats, dict) and isinstance(stats.get("events"), int) and stats["events"] < 15:
            return "insufficient_evidence"
    if isinstance(report.get("status"), str):
        return report["status"]
    legacy = report.get("formation_verdict", {})
    if isinstance(legacy, dict) and legacy.get("status") == "rejected":
        return "historical_rejected"
    return "unknown"


PRIORITY_AUDITS = {
    "TF_06_kama_trend": "daily_kama_trend_audit.json",
    "TF_08_supertrend": "daily_supertrend_audit.json",
    "TF_09_regression_channel": "daily_regression_channel_trend_audit.json",
    "MR_03_rsi_percentile": "daily_rsi_percentile_range_reversion_audit.json",
    "MR_06_bias": "daily_bias_range_reversion_audit.json",
    "MR_07_zscore": "daily_zscore_range_reversion_audit.json",
    "MR_14_btc_confirmed_alt_momentum": "btc_trend_confirmed_alt_momentum_audit.json",
    "VS_06_parkinson": "parkinson_volatility_extreme_reversion_audit.json",
    "TS_02_weekend": "weekend_low_liquidity_reversion_audit.json",
    "TS_07_month_boundary": "month_boundary_flow_audit.json",
}


def build_dashboard() -> dict:
    """Build the research state dashboard."""

    # 111 prototype universe
    universe = load_json(Path("reports/strategy_prototype_universe_111.json"))
    preflight = load_json(Path("reports/strategy_prototype_batch_preflight.json"))
    priority_queue = load_json(Path("reports/priority_research_queue_audit.json"))
    feature_pool = load_json(Path("reports/strategy_feature_pool.json"))
    feature_preflight = load_json(Path("reports/feature_pool_preflight_review.json"))

    # Cohort A
    cohort_a_ledger = load_json(Path("reports/prospective_shadow_signal_ledger.json"))
    cohort_a_registry = load_json(Path("reports/prospective_observation_registry.json"))
    cohort_a_checkpoint = load_json(Path("reports/prospective_observation_checkpoint.json"))
    cohort_a_maturity = load_json(Path("reports/prospective_maturity_audit.json"))
    cohort_a_cooccurrence = load_json(Path("reports/prospective_signal_cooccurrence_audit.json"))
    signal_arbitration = load_json(Path("reports/prospective_signal_conflict_arbitration.json"))
    signal_interaction = load_json(Path("reports/prospective_signal_interaction_audit.json"))

    # Cohort B
    cohort_b_ledger = load_json(Path("reports/prospective_cohort_b_shadow_ledger.json"))
    cohort_b_checkpoint = load_json(Path("reports/prospective_cohort_b_observation_checkpoint.json"))
    cohort_b_maturity = load_json(Path("reports/prospective_cohort_b_maturity_audit.json"))
    cohort_b_volatility_audit = load_json(Path("reports/daily_volatility_expansion_continuation_audit.json"))
    cohort_b_failed_breakout_audit = load_json(Path("reports/daily_failed_breakout_reversal_audit.json"))
    cohort_b_activation_registry = load_json(Path("reports/cohort_b_candidate_activation_registry.json"))
    cohort_b_activation_readiness = load_json(Path("reports/cohort_b_activation_readiness_audit.json"))
    cohort_b_volatility_staging = load_json(Path("reports/prospective_cohort_b_volatility_expansion_staging_ledger.json"))
    cohort_b_combined_staging = load_json(Path("reports/prospective_cohort_b_combined_staging_ledger.json"))
    cohort_b_refresh = load_json(Path("reports/cohort_b_refresh_pipeline.json"))
    cohort_b_signal_only_refresh = load_json(Path("reports/cohort_b_signal_only_refresh.json"))
    sealed_evaluation_preflight = load_json(Path("reports/prospective_sealed_evaluation_preflight.json"))
    sealed_outcome_evaluation = load_json(Path("reports/prospective_sealed_outcome_evaluation.json"))
    cutoff_alignment = load_json(Path("reports/prospective_cutoff_alignment_audit.json"))

    # Cohort C is deliberately separate: it is a post-hoc hypothesis under future-only observation.
    cohort_c_registry = load_json(Path("reports/prospective_cohort_c_exploration_registry.json"))
    cohort_c_staging = load_json(Path("reports/staging_cohort_c/prospective_cohort_c_short_exploration_ledger.json"))
    cohort_c_refresh = load_json(Path("reports/cohort_c_refresh_pipeline.json"))
    cohort_c_formal_registry = load_json(Path("reports/prospective_cohort_c_observation_registry.json"))
    cohort_c_sealed_preflight = load_json(Path("reports/prospective_cohort_c_sealed_evaluation_preflight.json"))
    # Cohort D is a separate post-hoc cross-sectional weakness observation stream.
    cohort_d_registry = load_json(Path("reports/prospective_cohort_d_exploration_registry.json"))
    cohort_d_staging = load_json(Path("reports/staging_cohort_d/prospective_cohort_d_cross_sectional_weakness_ledger.json"))
    cohort_d_refresh = load_json(Path("reports/cohort_d_refresh_pipeline.json"))
    cohort_d_formal_registry = load_json(Path("reports/prospective_cohort_d_observation_registry.json"))
    cohort_d_sealed_preflight = load_json(Path("reports/prospective_cohort_d_sealed_evaluation_preflight.json"))
    regime_combo_audit = load_json(Path("reports/regime_component_walk_forward_audit.json"))
    combo_diagnostic_seal = load_json(Path("reports/shared_capital_combo_diagnostic_seal.json"))
    trend_sleeve_combo = load_json(Path("reports/frozen_trend_sleeve_combo_diagnostic.json"))
    shared_combo = (regime_combo_audit or {}).get("shared_capital_combo", {})
    leave_one_out = shared_combo.get("leave_one_sleeve_out", {})

    # Historical audits
    month_audit = load_json(Path("reports/month_boundary_flow_audit.json"))
    weekend_audit = load_json(Path("reports/weekend_low_liquidity_reversion_audit.json"))
    parkinson_audit = load_json(Path("reports/parkinson_volatility_extreme_reversion_audit.json"))
    bias_audit = load_json(Path("reports/daily_bias_range_reversion_audit.json"))
    kdj_audit = load_json(Path("reports/daily_kdj_range_reversion_audit.json"))
    spring_upthrust_audit = load_json(Path("reports/daily_spring_upthrust_range_reversion_audit.json"))
    bb_squeeze_audit = load_json(Path("reports/daily_bb_squeeze_high_vol_breakout_audit.json"))
    weekly_cross_sectional_downtrend_audit = load_json(Path("reports/weekly_cross_sectional_short_downtrend_audit.json"))
    priority_audits = {
        research_id: load_json(Path("reports") / filename)
        for research_id, filename in PRIORITY_AUDITS.items()
    }

    # Registry
    registry = load_json(Path("reports/research_approval_registry.json"))

    cutoffs = [
        (cohort_b_signal_only_refresh or {}).get("source_cutoffs", {}).get("combined", ""),
        (cohort_c_refresh or {}).get("common_data_cutoff", ""),
    ]
    current_cutoff = max((cutoff for cutoff in cutoffs if cutoff), default=(cohort_b_maturity or cohort_a_maturity or {}).get("audit_date", "2026-07-14"))
    dashboard = {
        "dashboard_type": "research_state",
        "generation_date": str(current_cutoff)[:10],
        "observation_only": True,

        "prototype_universe": {
            "total": universe.get("prototype_count", 0) if universe else 0,
            "status_counts": universe.get("status_counts", {}) if universe else {},
        },

        "preflight_decisions": {
            "total": preflight.get("source_prototype_count", 0) if preflight else 0,
            "decision_counts": preflight.get("decision_counts", {}) if preflight else {},
            "research_card_priority_count": len(preflight.get("research_card_priority", [])) if preflight else 0,
        },

        "priority_research_queue": {
            "closed_count": priority_queue.get("closed_count", 0) if priority_queue else 0,
            "open_research_count": priority_queue.get("open_research_count", 0) if priority_queue else 0,
            "queue_decision": priority_queue.get("queue_decision", "priority_queue_audit_missing") if priority_queue else "priority_queue_audit_missing",
            "status_counts": priority_queue.get("status_counts", {}) if priority_queue else {},
        },

        "combo_feature_pool": {
            "feature_count": feature_pool.get("n_features", 0) if feature_pool else 0,
            "role_counts": feature_pool.get("role_counts", {}) if feature_pool else {},
            "preflight_group_counts": feature_preflight.get("group_counts", {}) if feature_preflight else {},
            "violations": feature_pool.get("violations", []) if feature_pool else ["feature_pool_report_missing"],
            "observation_only": True,
            "ready_for_combo_backtest": False,
        },

        "combo_observation": {
            "status": "metadata_only_no_outcomes",
            "raw_signal_count": (signal_arbitration or {}).get("raw_signal_count", 0),
            "deduplicated_signal_count": (signal_arbitration or {}).get("deduplicated_signal_count", 0),
            "arbitration_state_counts": (signal_arbitration or {}).get("arbitration_state_counts", {}),
            "within_24h_interactions": (signal_interaction or {}).get("same_symbol_interactions_within_24h", {}).get("total", 0),
            "within_24h_same_direction_consensus": (signal_interaction or {}).get("same_symbol_interactions_within_24h", {}).get("same_direction_consensus", 0),
            "within_24h_opposite_direction_conflicts": (signal_interaction or {}).get("same_symbol_interactions_within_24h", {}).get("opposite_direction_conflicts", 0),
            "outcomes_evaluated": False,
            "ready_for_combo_backtest": False,
        },

        "active_cohort_cutoff_alignment": cutoff_alignment or {
            "alignment_status": "not_run",
            "issues": ["alignment_audit_missing"],
            "observation_only": True,
        },

        "cohort_a": {
            "status": "sealed",
            "common_data_cutoff": cohort_a_ledger.get("common_data_cutoff", "") if cohort_a_ledger else "",
            "signal_count": cohort_a_ledger.get("signal_count", 0) if cohort_a_ledger else 0,
            "registry_count": cohort_a_registry.get("registry_signal_count", 0) if cohort_a_registry else 0,
            "checkpoint_count": cohort_a_checkpoint.get("current_count", 0) if cohort_a_checkpoint else 0,
            "genesis_count": cohort_a_checkpoint.get("genesis_count", 0) if cohort_a_checkpoint else 0,
            "mature_count": cohort_a_maturity.get("n_mature", 0) if cohort_a_maturity else 0,
            "awaiting_count": cohort_a_maturity.get("n_awaiting", 0) if cohort_a_maturity else 0,
            "sealed_evaluation_preflight": sealed_evaluation_preflight or {"readiness_status": "not_run"},
            "sealed_outcome_evaluation": sealed_outcome_evaluation or {"evaluation_status": "not_run", "outcomes_evaluated": False},
            "signal_cooccurrence": cohort_a_cooccurrence or {
                "audit_status": "not_run",
                "observation_only": True,
                "multi_factor_event_count": 0,
            },
        },

        "cohort_b": {
            "status": "active",
            "common_data_cutoff": (
                (cohort_b_signal_only_refresh or {}).get("source_cutoffs", {}).get("combined")
                or (cohort_b_ledger.get("common_data_cutoff", "") if cohort_b_ledger else "")
            ),
            "signal_count": cohort_b_ledger.get("signal_count", 0) if cohort_b_ledger else 0,
            "checkpoint_count": cohort_b_checkpoint.get("current_count", 0) if cohort_b_checkpoint else 0,
            "genesis_count": cohort_b_checkpoint.get("genesis_count", 0) if cohort_b_checkpoint else 0,
            "mature_count": cohort_b_maturity.get("n_mature", 0) if cohort_b_maturity else 0,
            "awaiting_count": cohort_b_maturity.get("n_awaiting", 0) if cohort_b_maturity else 0,
            "admitted_hypotheses": [
                "daily_rsi_downtrend_rebound_v1",
                "daily_volatility_expansion_continuation_v1",
                "daily_failed_breakout_reversal_v1",
            ],
            "candidate_evidence": {
                "daily_rsi_downtrend_rebound_v1": "prospective_active_with_signal",
                "daily_volatility_expansion_continuation_v1": audit_status(cohort_b_volatility_audit),
                "daily_failed_breakout_reversal_v1": audit_status(cohort_b_failed_breakout_audit),
            },
            "generator_status": {
                "daily_rsi_downtrend_rebound_v1": "active",
                "daily_volatility_expansion_continuation_v1": "signal_only_staging_ready_no_signal" if (cohort_b_volatility_staging or {}).get("coverage_status") == "active" and (cohort_b_volatility_staging or {}).get("signal_count") == 0 else "signal_only_staging_not_ready",
                "daily_failed_breakout_reversal_v1": "not_enabled_insufficient_evidence",
            },
            "activation_records": (cohort_b_activation_registry or {}).get("activation_records", []),
            "activation_readiness": cohort_b_activation_readiness or {"readiness_status": "not_audited"},
            "volatility_expansion_staging": cohort_b_volatility_staging or {"coverage_status": "not_generated"},
            "combined_staging": cohort_b_combined_staging or {"signal_count": 0},
            "last_refresh_dry_run": cohort_b_refresh or {"refresh_decision": "not_run"},
            "signal_only_refresh": cohort_b_signal_only_refresh or {"pipeline_decision": "not_run"},
        },

        "cohort_c": {
            "status": "exploration_future_only",
            "cohort_id": (cohort_c_registry or {}).get("cohort_id", "not_registered"),
            "hypothesis_id": (cohort_c_registry or {}).get("hypothesis_id", "not_registered"),
            "activation_not_before_utc": (cohort_c_registry or {}).get("activation_not_before_utc", "not_registered"),
            "common_data_cutoff": (
                (cohort_c_refresh or {}).get("common_data_cutoff")
                or (cohort_c_staging or {}).get("common_data_cutoff", "")
            ),
            "coverage_status": (cohort_c_refresh or {}).get("coverage_status") or (cohort_c_staging or {}).get("coverage_status", "not_generated"),
            "signal_count": (cohort_c_staging or {}).get("signal_count", 0),
            "outcomes_evaluated": (cohort_c_staging or {}).get("outcomes_evaluated", False),
            "positions_opened": (cohort_c_staging or {}).get("positions_opened", False),
            "formal_observation_count": (cohort_c_formal_registry or {}).get("registry_signal_count", 0),
            "last_refresh": cohort_c_refresh or {"refresh_decision": "not_run", "published": False},
            "sealed_evaluation_preflight": cohort_c_sealed_preflight or {"readiness_status": "not_run", "queued_observation_count": 0},
            "separate_from_cohort_b": True,
            "not_historical_approval": True,
        },
        "cohort_d": {
            "status": "exploration_future_only",
            "cohort_id": (cohort_d_registry or {}).get("cohort_id", "not_registered"),
            "hypothesis_id": (cohort_d_registry or {}).get("hypothesis_id", "not_registered"),
            "activation_not_before_utc": (cohort_d_registry or {}).get("activation_not_before_utc", "not_registered"),
            "common_data_cutoff": (cohort_d_refresh or {}).get("common_data_cutoff") or (cohort_d_staging or {}).get("common_data_cutoff", ""),
            "coverage_status": (cohort_d_refresh or {}).get("coverage_status") or (cohort_d_staging or {}).get("coverage_status", "not_generated"),
            "signal_count": (cohort_d_staging or {}).get("signal_count", 0),
            "outcomes_evaluated": (cohort_d_staging or {}).get("outcomes_evaluated", False),
            "positions_opened": (cohort_d_staging or {}).get("positions_opened", False),
            "formal_observation_count": (cohort_d_formal_registry or {}).get("registry_signal_count", 0),
            "last_refresh": cohort_d_refresh or {"refresh_decision": "not_run", "published": False},
            "sealed_evaluation_preflight": cohort_d_sealed_preflight or {"readiness_status": "not_run", "queued_observation_count": 0},
            "separate_from_cohort_b_and_c": True,
            "not_historical_approval": True,
        },

        "historical_combo_baselines": {
            "shared_capital_four_sleeve": {
                "status": shared_combo.get("status", "not_run"),
                "generated_events": shared_combo.get("generated_events", 0),
                "accepted_positions": shared_combo.get("aggregate", {}).get("accepted_positions", 0),
                "return_pct": shared_combo.get("aggregate", {}).get("total_return_pct"),
                "max_drawdown_pct": shared_combo.get("aggregate", {}).get("max_drawdown_pct"),
                "positive_fold_count": shared_combo.get("positive_fold_count", 0),
                "candidate_reasons": shared_combo.get("candidate_reasons", []),
                "realized_pnl_by_component": shared_combo.get("realized_pnl_by_component", {}),
                "leave_one_sleeve_out": {
                    component: {
                        "return_pct": value.get("aggregate", {}).get("total_return_pct"),
                        "max_drawdown_pct": value.get("aggregate", {}).get("max_drawdown_pct"),
                        "positive_fold_count": value.get("positive_fold_count", 0),
                        "diagnostic_only": value.get("diagnostic_only", False),
                        "not_a_candidate": value.get("not_a_candidate", False),
                    }
                    for component, value in leave_one_out.items()
                },
                "diagnostic_seal": {
                    "seal_status": (combo_diagnostic_seal or {}).get("seal_status", "not_run"),
                    "historical_diagnostic_only": (combo_diagnostic_seal or {}).get("historical_diagnostic_only", False),
                    "issues": (combo_diagnostic_seal or {}).get("issues", ["seal_report_missing"]),
                },
            },
            "frozen_trend_weak_factor_sleeve": {
                "status": (trend_sleeve_combo or {}).get("status", "not_run"),
                "formation": (trend_sleeve_combo or {}).get("results", {}).get("formation", {}),
                "oos": (trend_sleeve_combo or {}).get("results", {}).get("oos", {}),
                "oos_diagnostic_reasons": (trend_sleeve_combo or {}).get("oos_diagnostic_reasons", []),
                "diagnostic_only": True,
                "not_a_candidate": True,
            },
        },

        "historical_audits": {
            "month_boundary_flow": {
                "status": "audited",
                "report_exists": month_audit is not None,
                "verdict": audit_status(month_audit),
            },
            "weekend_low_liquidity_reversion": {
                "status": "audited",
                "report_exists": weekend_audit is not None,
                "verdict": audit_status(weekend_audit),
            },
            "parkinson_volatility_extreme_reversion": {
                "status": "audited",
                "report_exists": parkinson_audit is not None,
                "verdict": audit_status(parkinson_audit),
            },
            "daily_bias_range_reversion": {
                "status": "audited",
                "report_exists": bias_audit is not None,
                "verdict": audit_status(bias_audit),
            },
            "daily_kdj_range_reversion": {
                "status": "audited",
                "report_exists": kdj_audit is not None,
                "verdict": audit_status(kdj_audit),
            },
            "daily_spring_upthrust_range_reversion": {
                "status": "audited",
                "report_exists": spring_upthrust_audit is not None,
                "verdict": audit_status(spring_upthrust_audit),
            },
            "daily_bb_squeeze_high_vol_breakout": {
                "status": "audited",
                "report_exists": bb_squeeze_audit is not None,
                "verdict": audit_status(bb_squeeze_audit),
            },
            "weekly_cross_sectional_short_downtrend": {
                "status": "audited",
                "report_exists": weekly_cross_sectional_downtrend_audit is not None,
                "verdict": audit_status(weekly_cross_sectional_downtrend_audit),
            },
        },

        "priority_prototype_batch": {
            "defined_rule_audits": {
                research_id: audit_status(report)
                for research_id, report in priority_audits.items()
            },
            "defined_rule_status_counts": dict(Counter(
                audit_status(report) for report in priority_audits.values()
            )),
            "legacy_reference_only": ["MR_02_daily_bb_mean_revert", "VS_05_volatility_transition"],
            "requires_specification": ["MR_09_demux"],
        },

        "registry_status": {
            "approved": 0,
            "candidate": 0,
            "rejected": registry.get("status_counts", {}).get("rejected", 0) if registry else 0,
            "invalid": registry.get("status_counts", {}).get("invalid", 0) if registry else 0,
            "risk_blocked": registry.get("status_counts", {}).get("risk_blocked", 0) if registry else 0,
            "frozen": registry.get("status_counts", {}).get("frozen", 0) if registry else 0,
            "meta_only": registry.get("status_counts", {}).get("meta_only", 0) if registry else 0,
        },

        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },

        "status_classification": {
            "historical_rejected": [
                "relative_strength_persistence", "btc_trend_pullback",
                "vol_compression_breakout", "pairs_walk_forward",
                "spot_perp_basis", "multi_coin_funding_crowding",
                "btc_alt_lead_lag", "positive_funding_carry",
                "funding_oi_time_corrected", "range_regime_funding_extreme",
                "donchian_atr_trend_baseline", "range_regime_mean_reversion_family",
                "utc_session_breakout_family", "okx_futures_calendar_spread",
                "daily_oi_independent_change",
            ],
            "insufficient_evidence": [
                "month_boundary_flow",
                "weekend_low_liquidity_reversion",
                "parkinson_volatility_extreme_reversion",
                "daily_bias_range_reversion",
            ],
            "prospective_awaiting_maturity": [],  # filled after 90 days
            "prospective_active_no_signal": [
                "daily_volatility_expansion_continuation_v1",
                "daily_failed_breakout_reversal_v1",
            ],
            "prospective_active_with_signal": [
                "daily_rsi_downtrend_rebound_v1",
            ],
            "prospective_exploration_future_only": [
                "daily_volatility_expansion_short_exploration_v1",
                "weekly_cross_sectional_weakness_short_exploration_v1",
            ],
        },

        "methodology_notes": [
            "This dashboard is READ-ONLY.  No strategy is approved.",
            "All safety gates are closed.",
            "No returns, prices, or PnL derived from prospective ledgers.",
            "historical_rejected = formation period failed.",
            "insufficient_evidence = audit completed but insufficient samples.",
            "prospective_awaiting_maturity = signal emitted, 90-day horizon not yet elapsed.",
            "prospective_active_no_signal = admitted hypothesis, no signal emitted yet.",
            "prospective_exploration_future_only = post-hoc hypothesis isolated from Cohort B and historical approval.",
            "signal_cooccurrence is structural only and is not combo performance evidence.",
        ],
    }

    return dashboard


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out-json", type=Path, default=Path("reports/research_state_dashboard.json"))
    p.add_argument("--out-md", type=Path, default=None)
    args = p.parse_args(argv)

    dashboard = build_dashboard()

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"JSON written to {args.out_json}")

    # Generate Markdown
    md = generate_markdown(dashboard)
    out_md = args.out_md or Path("docs") / f"research_state_dashboard_{dashboard['generation_date']}.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")
    print(f"Markdown written to {out_md}")

    return 0


def generate_markdown(d: dict) -> str:
    lines = [
        f"# 研究状态总览（{d['generation_date']}）",
        "",
        "## 一句话状态",
        "",
        "**没有任何策略获准模拟盘或实盘。所有安全闸门关闭。**",
        "",
        "---",
        "",
        "## 111 原型宇宙",
        "",
        f"| 状态 | 数量 |",
        f"|---|---|",
    ]
    for k, v in d["prototype_universe"]["status_counts"].items():
        lines.append(f"| {k} | {v} |")
    lines.append(f"| **合计** | **{d['prototype_universe']['total']}** |")

    lines.extend([
        "",
        "## 结构优先候选（research_card_priority）",
        "",
        f"数量：**{d['preflight_decisions']['research_card_priority_count']}**",
        "",
        "这些原型通过了单腿、低换手、OHLCV-only、免费可复现、无已淘汰家族重叠的筛选。",
        "获得研究卡不等于获批交易。当前已关闭："
        f"**{d['priority_research_queue']['closed_count']}**；开放历史回测："
        f"**{d['priority_research_queue']['open_research_count']}**。",
        f"- 队列结论：`{d['priority_research_queue']['queue_decision']}`",
        "",
        "## Cohort A（已密封）",
        "",
        f"- 信号数：{d['cohort_a']['signal_count']}",
        f"- 共同截止点：{d['cohort_a']['common_data_cutoff']}",
        f"- 已到期：{d['cohort_a']['mature_count']}",
        f"- 未到期：{d['cohort_a']['awaiting_count']}",
        f"- 密封结果评估：{d['cohort_a']['sealed_outcome_evaluation']['evaluation_status']}（已评估：{d['cohort_a']['sealed_outcome_evaluation']['outcomes_evaluated']}）",
        f"- 同标的同时间多因子事件：{d['cohort_a']['signal_cooccurrence'].get('multi_factor_event_count', 0)}",
        f"- 共现信号占比：{d['cohort_a']['signal_cooccurrence'].get('signal_cooccurrence_rate', 0.0):.2%}",
        "- 共现审计只描述结构重叠，不构成组合收益或交易资格证据。",
        "",
        "## 组合特征池（研究层）",
        "",
        f"- 特征数：{d['combo_feature_pool']['feature_count']}",
        f"- 方向弱信号：{d['combo_feature_pool']['role_counts'].get('directional_weak_signal', 0)}",
        f"- 环境标签：{d['combo_feature_pool']['role_counts'].get('context_label', 0)}",
        f"- 风险过滤候选：{d['combo_feature_pool']['role_counts'].get('risk_filter_candidate', 0)}",
        f"- 硬阻断：{d['combo_feature_pool']['role_counts'].get('blocked', 0)}",
        f"- 校验违规：{len(d['combo_feature_pool']['violations'])}",
        "- 组合回测资格：False。",
        "",
        "## Cohort B（活跃）",
        "",
        f"- 信号数：{d['cohort_b']['signal_count']}",
        f"- 共同截止点：{d['cohort_b']['common_data_cutoff']}",
        f"- 已准入假设：{', '.join(d['cohort_b']['admitted_hypotheses'])}",
        "",
        "## 组合观察（仅信号元数据）",
        "",
        f"- 原始 / 去重信号：{d['combo_observation']['raw_signal_count']} / {d['combo_observation']['deduplicated_signal_count']}",
        f"- 严格同向共识：{d['combo_observation']['arbitration_state_counts'].get('same_direction_consensus_no_leverage_addition', 0)}",
        f"- 反向冲突锁定：{d['combo_observation']['arbitration_state_counts'].get('opposite_direction_conflict_lockout', 0)}",
        f"- 24h 同向 / 反向交互：{d['combo_observation']['within_24h_same_direction_consensus']} / {d['combo_observation']['within_24h_opposite_direction_conflicts']}",
        "- 仅描述共现和冲突；未评估价格、收益或结果，不能进入组合回测。",
        "",
        "## 历史组合基线",
        "",
        f"- 四袖套共享资金：`{d['historical_combo_baselines']['shared_capital_four_sleeve']['status']}`",
        f"- 事件 / 接受仓位：{d['historical_combo_baselines']['shared_capital_four_sleeve']['generated_events']} / {d['historical_combo_baselines']['shared_capital_four_sleeve']['accepted_positions']}",
        f"- 收益 / 最大回撤：{d['historical_combo_baselines']['shared_capital_four_sleeve']['return_pct']}% / {d['historical_combo_baselines']['shared_capital_four_sleeve']['max_drawdown_pct']}%",
        f"- 正收益半年窗口：{d['historical_combo_baselines']['shared_capital_four_sleeve']['positive_fold_count']}/5",
        f"- 诊断封存：`{d['historical_combo_baselines']['shared_capital_four_sleeve']['diagnostic_seal']['seal_status']}`",
        "- 该基线已淘汰，不能作为组合候选或权重优化起点。",
        "- 留一袖套剔除仅用于失败归因，所有结果均不是候选。",
        f"- 冻结趋势弱因子袖套：`{d['historical_combo_baselines']['frozen_trend_weak_factor_sleeve']['status']}`；"
        f"OOS 收益 / 最大回撤：{d['historical_combo_baselines']['frozen_trend_weak_factor_sleeve']['oos'].get('total_return_pct')}% / "
        f"{d['historical_combo_baselines']['frozen_trend_weak_factor_sleeve']['oos'].get('max_drawdown_pct')}%。",
        "- 趋势袖套同样已淘汰；仅保留为组合失败证据，不可用于权重优化。",
        "",
        "## Cohort C（前瞻探索）",
        "",
        f"- 假设：{d['cohort_c']['hypothesis_id']}",
        f"- 激活边界：{d['cohort_c']['activation_not_before_utc']}",
        f"- 数据截止点：{d['cohort_c']['common_data_cutoff']}",
        f"- 覆盖状态：{d['cohort_c']['coverage_status']}",
        f"- 信号数：{d['cohort_c']['signal_count']}",
        f"- 最新刷新：{d['cohort_c']['last_refresh']['refresh_decision']}（正式提交：{d['cohort_c']['last_refresh']['published']}）",
        f"- 密封评估预检：{d['cohort_c']['sealed_evaluation_preflight']['readiness_status']}（队列：{d['cohort_c']['sealed_evaluation_preflight'].get('queued_observation_count', 0)}）",
        "- 仅前瞻探索；不属于 Cohort B，不能构成历史批准。",
        "",
        "## Cohort D（前瞻探索）",
        "",
        f"- 假设：{d['cohort_d']['hypothesis_id']}",
        f"- 激活边界：{d['cohort_d']['activation_not_before_utc']}",
        f"- 数据截止点：{d['cohort_d']['common_data_cutoff']}",
        f"- 覆盖状态：{d['cohort_d']['coverage_status']}",
        f"- 信号数：{d['cohort_d']['signal_count']}",
        f"- 最新刷新：{d['cohort_d']['last_refresh']['refresh_decision']}（正式提交：{d['cohort_d']['last_refresh']['published']}）",
        f"- 密封评估预检：{d['cohort_d']['sealed_evaluation_preflight']['readiness_status']}（队列：{d['cohort_d']['sealed_evaluation_preflight'].get('queued_observation_count', 0)}）",
        "- 后验横截面弱势假设；独立于 Cohort B/C，不能构成历史批准。",
        "",
        "## 活跃 Cohort 截止点对齐",
        "",
        f"- 状态：{d['active_cohort_cutoff_alignment']['alignment_status']}",
        f"- 数据质量截止点：{d['active_cohort_cutoff_alignment'].get('data_quality_cutoff', '')}",
        f"- B / C 截止点：{d['active_cohort_cutoff_alignment'].get('active_cohort_cutoffs', {}).get('cohort_b', '')} / {d['active_cohort_cutoff_alignment'].get('active_cohort_cutoffs', {}).get('cohort_c', '')}",
        f"- 问题数：{len(d['active_cohort_cutoff_alignment'].get('issues', []))}",
        "",
        "## 历史审计",
        "",
        "| 审计 | 状态 | 结论 |",
        "|---|---|---|",
    ])
    for name, info in d["historical_audits"].items():
        lines.append(f"| {name} | {info['status']} | {info['verdict']} |")

    lines.extend([
        "",
        "### 组合失败归因（诊断）",
        "",
        "| 剔除袖套 | 收益 | 最大回撤 | 正收益半年窗口 | 仅诊断 |",
        "|---|---:|---:|---:|---|",
    ])
    for component, item in d["historical_combo_baselines"]["shared_capital_four_sleeve"]["leave_one_sleeve_out"].items():
        lines.append(
            f"| {component} | {item['return_pct']}% | {item['max_drawdown_pct']}% | "
            f"{item['positive_fold_count']}/5 | {item['diagnostic_only']} |"
        )

    lines.extend([
        "",
        "## 安全闸门",
        "",
        f"- approved_for_paper: {d['safety_gates']['approved_for_paper']}",
        f"- eligible_for_paper: {d['safety_gates']['eligible_for_paper']}",
        f"- safe_to_enable_trading: {d['safety_gates']['safe_to_enable_trading']}",
        f"- ready_for_combo_backtest: {d['safety_gates']['ready_for_combo_backtest']}",
        "",
        "## 状态分类",
        "",
        f"### historical_rejected ({len(d['status_classification']['historical_rejected'])})",
        "",
    ])
    for s in d["status_classification"]["historical_rejected"]:
        lines.append(f"- {s}")

    lines.extend([
        "",
        f"### insufficient_evidence ({len(d['status_classification']['insufficient_evidence'])})",
        "",
    ])
    for s in d["status_classification"]["insufficient_evidence"]:
        lines.append(f"- {s}")

    lines.extend([
        "",
        f"### prospective_active_with_signal ({len(d['status_classification']['prospective_active_with_signal'])})",
        "",
    ])
    for s in d["status_classification"]["prospective_active_with_signal"]:
        lines.append(f"- {s}")

    lines.extend([
        "",
        f"### prospective_active_no_signal ({len(d['status_classification']['prospective_active_no_signal'])})",
        "",
    ])
    for s in d["status_classification"]["prospective_active_no_signal"]:
        lines.append(f"- {s}")

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())

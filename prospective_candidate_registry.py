"""Separate registry for frozen research candidates awaiting prospective data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROSPECTIVE_START = "2026-07-11"
INTERIM_DAYS = 90
APPROVAL_GRADE_DAYS = 365


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_registry(
    drift: dict[str, Any],
    future_combo: dict[str, Any],
    anatomy: dict[str, Any],
    uptrend_batch: dict[str, Any] | None = None,
    combo_pairs: dict[str, Any] | None = None,
    combo_anatomy: dict[str, Any] | None = None,
    volume_shock: dict[str, Any] | None = None,
    volume_complementarity: dict[str, Any] | None = None,
    weekly_momentum: dict[str, Any] | None = None,
    weekly_complementarity: dict[str, Any] | None = None,
    range_microtrend: dict[str, Any] | None = None,
    range_complementarity: dict[str, Any] | None = None,
    legacy_weak_preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    drift_result = drift.get("aggregate", {})
    ema = future_combo.get("result", {}).get("component_attribution", {}).get("ema_continuation_short", {})
    ema_concentration = anatomy.get("monthly_component_pnl", {}).get("positive_month_concentration_by_component", {}).get(
        "ema_continuation_short", 0.0
    )
    frozen = []
    if drift.get("status") == "frozen_prospective_candidate" and not drift.get("candidate_reasons"):
        frozen.append(
            {
                "candidate_id": "low_volatility_drift_bb_breakout_fixed_risk_v1",
                "status": "frozen_awaiting_prospective",
                "declared_regime": "low_volatility_drift_v2",
                "direction": "bidirectional_breakout_continuation",
                "position_fraction": float(drift.get("position_fraction", 0.10)),
                "max_positions": int(drift.get("max_positions", 5)),
                "eligible_symbols": list(drift.get("eligible_symbols", [])),
                "historical_observed_return_pct": float(drift_result.get("total_return_pct", 0.0)),
                "historical_observed_max_drawdown_pct": float(drift_result.get("max_drawdown_pct", 0.0)),
                "historical_observed_accepted_positions": int(drift_result.get("accepted_positions", 0)),
                "historical_positive_folds": int(drift.get("positive_fold_count", 0)),
                "prospective_start": PROSPECTIVE_START,
                "interim_diagnostic_days": INTERIM_DAYS,
                "approval_grade_days": APPROVAL_GRADE_DAYS,
                "result_peeking_allowed_before_interim": False,
                "allowed_in_combo_backtest": False,
                "evidence": [
                    "reports/low_volatility_drift_breakout_audit.json",
                    "reports/low_volatility_drift_fixed_risk_audit.json",
                ],
            }
        )
    watchlist = [
        {
            "candidate_id": "ema_continuation_short_downtrend_v1",
            "status": "watchlist_concentration_risk",
            "declared_regime": "downtrend",
            "direction": "short",
            "future_window_accepted_positions": int(ema.get("accepted_positions", 0)),
            "future_window_return_contribution_pct": float(ema.get("return_contribution_pct", 0.0)),
            "positive_month_concentration": float(ema_concentration),
            "reason": "positive future contribution but component concentration exceeds 25%",
            "display_summary": (
                f"{float(ema.get('return_contribution_pct', 0.0)):+.6f}% contribution, "
                f"{float(ema_concentration):.2%} positive-month concentration"
            ),
            "allowed_in_combo_backtest": False,
            "evidence": [
                "reports/downtrend_bidirectional_future_validation.json",
                "reports/downtrend_bidirectional_future_anatomy_audit.json",
            ],
        }
    ]
    uptrend_component = (uptrend_batch or {}).get("components", {}).get("persistent_uptrend_ema20_reclaim", {})
    uptrend_primary = uptrend_component.get("primary_constant_universe", {})
    uptrend_result = uptrend_primary.get("aggregate", {})
    if uptrend_component.get("status") == "weak_feature_watchlist_concentration_penalty":
        watchlist.append(
            {
                "candidate_id": "persistent_uptrend_ema20_reclaim_v1",
                "status": "watchlist_concentration_risk",
                "declared_regime": "persistent_uptrend_over_10d_btc_aligned",
                "direction": "long",
                "historical_observed_accepted_positions": int(uptrend_result.get("accepted_positions", 0)),
                "historical_observed_return_pct": float(uptrend_result.get("total_return_pct", 0.0)),
                "historical_observed_max_drawdown_pct": float(uptrend_result.get("max_drawdown_pct", 0.0)),
                "positive_month_concentration": float(uptrend_result.get("top_positive_month_share", 0.0)),
                "reason": "primary BTC/ETH panel passes core weak-feature checks but positive-month concentration exceeds 25%",
                "display_summary": (
                    f"{float(uptrend_result.get('total_return_pct', 0.0)):+.6f}% observed return, "
                    f"{float(uptrend_result.get('top_positive_month_share', 0.0)):.2%} positive-month concentration"
                ),
                "allowed_in_combo_backtest": False,
                "evidence": [
                    "reports/uptrend_regime_structure_audit.json",
                    "reports/uptrend_breadth_context_audit.json",
                    "reports/persistent_uptrend_entry_batch_audit.json",
                ],
            }
        )
    combo_watchlist = set((combo_pairs or {}).get("posthoc_risk_adjusted_combo_watchlist", []))
    for pair_id in sorted(combo_watchlist):
        pair = (combo_pairs or {}).get("pairs", {}).get(pair_id, {})
        aggregate = pair.get("aggregate", {})
        interpretation = pair.get("posthoc_risk_adjusted_interpretation", {})
        anatomy = (combo_anatomy or {}).get("pairs", {}).get(pair_id, {})
        failure = anatomy.get("failure_classification", {})
        watchlist.append(
            {
                "candidate_id": f"combo::{pair_id}",
                "status": "combo_watchlist_strict_gate_failed",
                "declared_regime": "multi_regime_pair",
                "direction": "component_defined",
                "historical_observed_accepted_positions": int(aggregate.get("accepted_positions", 0)),
                "historical_observed_return_pct": float(aggregate.get("total_return_pct", 0.0)),
                "historical_observed_max_drawdown_pct": float(aggregate.get("max_drawdown_pct", 0.0)),
                "positive_month_concentration": float(aggregate.get("top_positive_month_share", 0.0)),
                "reason": "retained post-hoc for risk-adjusted observation but failed the pre-registered absolute drawdown gate",
                "drawdown_failure_classification": failure.get("classification", "not_audited"),
                "common_failure": bool(failure.get("common_failure", False)),
                "watchlist_action": anatomy.get("watchlist_action", "await_drawdown_anatomy"),
                "display_summary": (
                    f"{float(aggregate.get('total_return_pct', 0.0)):+.6f}% observed return, "
                    f"{float(aggregate.get('max_drawdown_pct', 0.0)):.6f}% max DD, "
                    f"{float(interpretation.get('drawdown_excess_percentage_points', 0.0)):+.6f}pp DD excess"
                ),
                "allowed_in_combo_backtest": False,
                "evidence": [
                    "reports/weak_component_complementarity_audit.json",
                    "reports/restricted_weak_pair_combo_simulation.json",
                    "reports/restricted_combo_drawdown_anatomy_audit.json",
                ],
            }
        )
    volume_items = (volume_shock or {}).get("posthoc_directional_weak_feature_watchlist", [])
    volume_short_diagnostic = (volume_shock or {}).get("posthoc_short_standalone_diagnostic", {}).get("aggregate", {})
    for volume_item in volume_items:
        watchlist.append(
            {
                "candidate_id": str(volume_item.get("component_id")),
                "status": "posthoc_directional_weak_feature_watchlist",
                "declared_regime": "daily_volume_shock_upside_exhaustion",
                "direction": "short",
                "historical_observed_accepted_positions": int(volume_short_diagnostic.get("accepted_positions", 0)),
                "historical_observed_return_pct": float(volume_short_diagnostic.get("total_return_pct", 0.0)),
                "historical_observed_max_drawdown_pct": float(volume_short_diagnostic.get("max_drawdown_pct", 0.0)),
                "positive_month_concentration": float(volume_short_diagnostic.get("top_positive_month_share", 0.0)),
                "reason": "short side was discovered after the frozen bidirectional rule failed on its long side",
                "display_summary": (
                    f"{float(volume_short_diagnostic.get('total_return_pct', 0.0)):+.6f}% observed return, "
                    f"{float(volume_short_diagnostic.get('max_drawdown_pct', 0.0)):.6f}% max DD"
                ),
                "allowed_in_combo_backtest": False,
                "evidence": [
                    "reports/daily_volume_shock_reversal_preflight.json",
                    "reports/daily_volume_shock_reversal_audit.json",
                ],
            }
        )
    pair_comparison_watchlist = list((volume_complementarity or {}).get("retained_prospective_pair_watchlist", []))
    for pair_id in sorted(pair_comparison_watchlist):
        watchlist.append(
            {
                "candidate_id": f"pair_watchlist::{pair_id}",
                "status": "prospective_pair_comparison_only",
                "declared_regime": "multi_regime_pair",
                "direction": "component_defined",
                "reason": "pair is complementary but contains a post-hoc directional feature",
                "display_summary": "complementarity gate passed; historical combo simulation prohibited",
                "allowed_in_combo_backtest": False,
                "evidence": ["reports/volume_shock_short_complementarity_audit.json"],
            }
        )
    weekly_items = (weekly_momentum or {}).get("posthoc_sleeve_weak_feature_watchlist", [])
    weekly_short_diagnostic = (weekly_momentum or {}).get("posthoc_short_standalone_diagnostic", {}).get(
        "aggregate", {}
    )
    for weekly_item in weekly_items:
        watchlist.append(
            {
                "candidate_id": str(weekly_item.get("component_id")),
                "status": "posthoc_sleeve_weak_feature_watchlist",
                "declared_regime": "cross_sectional_weakness_continuation",
                "direction": "short",
                "historical_observed_accepted_positions": int(weekly_short_diagnostic.get("accepted_positions", 0)),
                "historical_observed_return_pct": float(weekly_short_diagnostic.get("total_return_pct", 0.0)),
                "historical_observed_max_drawdown_pct": float(weekly_short_diagnostic.get("max_drawdown_pct", 0.0)),
                "positive_month_concentration": float(weekly_short_diagnostic.get("top_positive_month_share", 0.0)),
                "reason": "short sleeve was discovered after the frozen weekly long-short rule failed on its long sleeve",
                "display_summary": (
                    f"{float(weekly_short_diagnostic.get('total_return_pct', 0.0)):+.6f}% observed return, "
                    f"{float(weekly_short_diagnostic.get('max_drawdown_pct', 0.0)):.6f}% max DD"
                ),
                "allowed_in_combo_backtest": False,
                "evidence": [
                    "reports/weekly_cross_sectional_momentum_audit.json",
                    "reports/weekly_weakest_short_complementarity_audit.json",
                ],
            }
        )
    weekly_pair_watchlist = list((weekly_complementarity or {}).get("retained_prospective_pair_watchlist", []))
    for pair_id in sorted(weekly_pair_watchlist):
        watchlist.append(
            {
                "candidate_id": f"pair_watchlist::{pair_id}",
                "status": "prospective_pair_comparison_only",
                "declared_regime": "multi_regime_pair",
                "direction": "component_defined",
                "reason": "pair is complementary but contains a post-hoc weekly short sleeve",
                "display_summary": "complementarity gate passed; historical combo simulation prohibited",
                "allowed_in_combo_backtest": False,
                "evidence": ["reports/weekly_weakest_short_complementarity_audit.json"],
            }
        )
    range_items = (range_microtrend or {}).get("posthoc_sleeve_weak_feature_watchlist", [])
    range_diagnostics = (range_microtrend or {}).get("posthoc_standalone_diagnostics", {})
    for range_item in range_items:
        component_id = str(range_item.get("component_id"))
        diagnostic = range_diagnostics.get(component_id, {}).get("aggregate", {})
        watchlist.append(
            {
                "candidate_id": component_id,
                "status": "posthoc_regime_sleeve_weak_feature_watchlist",
                "declared_regime": "mean_reverting_range_v2",
                "direction": "long",
                "historical_observed_accepted_positions": int(diagnostic.get("accepted_positions", 0)),
                "historical_observed_return_pct": float(diagnostic.get("total_return_pct", 0.0)),
                "historical_observed_max_drawdown_pct": float(diagnostic.get("max_drawdown_pct", 0.0)),
                "positive_month_concentration": float(diagnostic.get("top_positive_month_share", 0.0)),
                "reason": "long sleeve was discovered after the frozen bidirectional range rule failed its fold gate",
                "display_summary": (
                    f"{float(diagnostic.get('total_return_pct', 0.0)):+.6f}% observed return, "
                    f"{float(diagnostic.get('max_drawdown_pct', 0.0)):.6f}% max DD"
                ),
                "allowed_in_combo_backtest": False,
                "evidence": [
                    "reports/weekly_range_cross_sectional_reversal_preflight.json",
                    "reports/weekly_range_microtrend_continuation_audit.json",
                    "reports/range_microtrend_long_complementarity_audit.json",
                ],
            }
        )
    range_pair_watchlist = list((range_complementarity or {}).get("retained_prospective_pair_watchlist", []))
    for pair_id in sorted(range_pair_watchlist):
        watchlist.append(
            {
                "candidate_id": f"pair_watchlist::{pair_id}",
                "status": "prospective_pair_comparison_only",
                "declared_regime": "multi_regime_pair",
                "direction": "component_defined",
                "reason": "pair is complementary but contains a post-hoc range-regime long sleeve",
                "display_summary": "complementarity gate passed; historical combo simulation prohibited",
                "allowed_in_combo_backtest": False,
                "evidence": ["reports/range_microtrend_long_complementarity_audit.json"],
            }
        )
    legacy_decisions = {
        str(item.get("factor_id")): item
        for item in (legacy_weak_preflight or {}).get("factor_preflight_decisions", [])
    }
    donchian = legacy_decisions.get("donchian_atr_trend_baseline", {})
    if donchian.get("preflight_status") == "eligible_for_shadow_observation_only":
        watchlist.append(
            {
                "candidate_id": "donchian_atr_trend_baseline",
                "status": "rejected_standalone_regime_gated_weak_feature_watchlist",
                "declared_regime": "direction_compatible_trend_only",
                "direction": "bidirectional_breakout",
                "prospective_regime_compatible_signals": int(
                    donchian.get("fixed_window_signal_count", 0)
                ),
                "reason": "rejected standalone rule is reused only as a regime-gated weak signal per the combination policy",
                "display_summary": (
                    f"{int(donchian.get('fixed_window_signal_count', 0))} unique regime-compatible "
                    "prospective signal; standalone status remains rejected"
                ),
                "allowed_in_combo_backtest": False,
                "evidence": [
                    "reports/donchian_atr_trend_baseline_audit.json",
                    "reports/donchian_atr_trend_baseline_regime_conditioned_audit.json",
                    "reports/prospective_legacy_weak_factor_preflight.json",
                ],
            }
        )
    return {
        "report_type": "prospective_candidate_registry",
        "report_date": "2026-07-14",
        "prospective_start": PROSPECTIVE_START,
        "frozen_candidates": frozen,
        "watchlist": watchlist,
        "regime_coverage": {
            "uptrend": "watchlist_only" if len(watchlist) > 1 else "none",
            "downtrend": "watchlist_only",
            "mean_reverting_range_v2": "watchlist_only" if range_items else "none",
            "low_volatility_drift_v2": "one_frozen_candidate" if frozen else "none",
            "combo_layer": f"{len(combo_watchlist)}_strict_gate_failed_watchlist",
            "volume_shock_exhaustion": "watchlist_only" if volume_items else "none",
            "cross_sectional_weakness_continuation": "watchlist_only" if weekly_items else "none",
            "regime_gated_trend_breakout": "watchlist_only" if donchian else "none",
            "prospective_pair_comparison_layer": (
                f"{len(pair_comparison_watchlist) + len(weekly_pair_watchlist) + len(range_pair_watchlist)}_watchlist"
            ),
        },
        "approved_for_paper": [],
        "eligible_for_paper": False,
        "safe_to_enable_trading": False,
        "ready_for_combo_backtest": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Prospective Candidate Registry",
        "",
        "Date: 2026-07-14",
        "",
        f"Prospective data start: `{report['prospective_start']}`.",
        "",
        "## Frozen Candidates",
        "",
    ]
    for item in report["frozen_candidates"]:
        lines.extend(
            [
                f"### `{item['candidate_id']}`",
                "",
                f"- regime: `{item['declared_regime']}`",
                f"- historical observed result: {item['historical_observed_return_pct']:+.6f}% return, {item['historical_observed_max_drawdown_pct']:.6f}% max DD",
                f"- accepted positions: {item['historical_observed_accepted_positions']}",
                f"- positive half-year folds: {item['historical_positive_folds']}/5",
                f"- allocation: {item['position_fraction']:.0%} per position, maximum {item['max_positions']}",
                "- no result peeking before the 90-day interim checkpoint",
                "",
            ]
        )
    lines.extend(["## Watchlist", ""])
    for item in report["watchlist"]:
        lines.extend(
            [
                f"- `{item['candidate_id']}`: {item['display_summary']}; not frozen for combo use.",
            ]
        )
    lines.extend(["", "## Regime Coverage", ""])
    for regime, status in report["regime_coverage"].items():
        lines.append(f"- `{regime}`: `{status}`")
    lines.extend(["", "## Safety", "", "- `approved_for_paper = []`", "- `eligible_for_paper = false`", "- `safe_to_enable_trading = false`", "- `ready_for_combo_backtest = false`", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the separate prospective research candidate registry.")
    parser.add_argument("--drift", type=Path, default=Path("reports/low_volatility_drift_fixed_risk_audit.json"))
    parser.add_argument("--future-combo", type=Path, default=Path("reports/downtrend_bidirectional_future_validation.json"))
    parser.add_argument("--anatomy", type=Path, default=Path("reports/downtrend_bidirectional_future_anatomy_audit.json"))
    parser.add_argument("--uptrend-batch", type=Path, default=Path("reports/persistent_uptrend_entry_batch_audit.json"))
    parser.add_argument("--combo-pairs", type=Path, default=Path("reports/restricted_weak_pair_combo_simulation.json"))
    parser.add_argument("--combo-anatomy", type=Path, default=Path("reports/restricted_combo_drawdown_anatomy_audit.json"))
    parser.add_argument("--volume-shock", type=Path, default=Path("reports/daily_volume_shock_reversal_audit.json"))
    parser.add_argument("--volume-complementarity", type=Path, default=Path("reports/volume_shock_short_complementarity_audit.json"))
    parser.add_argument("--weekly-momentum", type=Path, default=Path("reports/weekly_cross_sectional_momentum_audit.json"))
    parser.add_argument("--weekly-complementarity", type=Path, default=Path("reports/weekly_weakest_short_complementarity_audit.json"))
    parser.add_argument("--range-microtrend", type=Path, default=Path("reports/weekly_range_microtrend_continuation_audit.json"))
    parser.add_argument("--range-complementarity", type=Path, default=Path("reports/range_microtrend_long_complementarity_audit.json"))
    parser.add_argument("--legacy-weak-preflight", type=Path, default=Path("reports/prospective_legacy_weak_factor_preflight.json"))
    parser.add_argument("--out", type=Path, default=Path("reports/prospective_candidate_registry.json"))
    parser.add_argument("--doc", type=Path, default=Path("docs/prospective_candidate_registry_2026-07-14.md"))
    args = parser.parse_args(argv)
    report = build_registry(
        load_json(args.drift),
        load_json(args.future_combo),
        load_json(args.anatomy),
        load_json(args.uptrend_batch),
        load_json(args.combo_pairs),
        load_json(args.combo_anatomy),
        load_json(args.volume_shock),
        load_json(args.volume_complementarity),
        load_json(args.weekly_momentum),
        load_json(args.weekly_complementarity),
        load_json(args.range_microtrend),
        load_json(args.range_complementarity),
        load_json(args.legacy_weak_preflight),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.doc.parent.mkdir(parents=True, exist_ok=True)
    args.doc.write_text(render_markdown(report), encoding="utf-8")
    print(f"Report written to {args.out}")
    print(f"Document written to {args.doc}")
    print(f"frozen={len(report['frozen_candidates'])}; watchlist={len(report['watchlist'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

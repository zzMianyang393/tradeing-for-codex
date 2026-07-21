"""Evidence-backed completion audit for the long-running 10U strategy research."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig
from ten_u_event_trend_prospective_v2 import validate_ledger


def build_goal_audit(root: Path) -> dict[str, Any]:
    config = PersistentEventTrendConfig()
    ledger_path = root / "reports/ten_u_event_trend_prospective_ledger_v2.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    validate_ledger(ledger)
    health = json.loads(
        (root / "reports/ten_u_event_trend_health_v2.json").read_text(encoding="utf-8")
    )
    historical = json.loads(
        (root / "reports/ten_u_event_trend_screen_v2.json").read_text(encoding="utf-8")
    )
    prospective_registration = json.loads(
        (root / "reports/ten_u_event_trend_prospective_registration_v2.json")
        .read_text(encoding="utf-8")
    )
    final_registration = json.loads(
        (root / "reports/ten_u_event_trend_final_promotion_preregistration_v2.json")
        .read_text(encoding="utf-8")
    )
    if ledger.get("outcomes_accessed") is not False:
        raise ValueError("prospective outcomes are not sealed")
    historical_account = historical["account"]
    requirements = {
        "single_coin_max_three_universe": {
            "status": "implemented",
            "evidence": {
                "symbols": list(config.symbols),
                "maximum_concurrent_positions": config.maximum_concurrent_positions,
            },
        },
        "one_to_two_day_trend_capture": {
            "status": "implemented_behavior_not_validated_edge",
            "evidence": {
                "persistence_confirmation_hours": config.persistence_completed_4h_bars * 4,
                "maximum_holding_hours": config.maximum_holding_hours,
                "historical_winner_holding_hours": [
                    trade["holding_hours"]
                    for trade in historical_account["trades_detail"]
                    if trade["net_pnl"] > 0
                ],
                "early_risk_exit_allowed": True,
            },
        },
        "automatic_market_judgment": {
            "status": "strategy_local_state_machine_implemented_accuracy_unproven",
            "evidence": {
                "ignition_timeframe": "4h",
                "persistence_completed_4h_bars": config.persistence_completed_4h_bars,
                "entry_timing_timeframe": "1h",
                "entry_rule": config.entry_rule,
            },
        },
        "avoid_stop_sweeps": {
            "status": "not_proven",
            "evidence": {
                "historical_hard_stops": historical_account["hard_stop_count"],
                "historical_stopped_then_recovered_fraction": historical_account[
                    "stopped_then_recovered_fraction"
                ],
                "prospective_hard_stop_outcomes": 0,
                "reason": "one_of_one_historical_hard_stops_recovered_entry",
            },
        },
        "control_drawdown": {
            "status": "risk_mechanism_implemented_forward_performance_unproven",
            "evidence": {
                "risk_per_trade": str(config.risk_per_trade),
                "daily_loss_halt": str(config.daily_loss_halt),
                "peak_drawdown_halt": str(config.peak_drawdown_halt),
                "historical_max_drawdown_fraction": historical_account[
                    "max_drawdown_fraction"
                ],
            },
        },
        "high_return_10u_accumulation": {
            "status": "not_proven",
            "evidence": {
                "historical_starting_equity": historical_account["starting_equity"],
                "historical_ending_equity": historical_account["ending_equity"],
                "historical_trades": historical_account["trades"],
                "historical_formal_status": historical["formal_status"],
                "reason": "three_trade_result_dominated_by_one_rave_winner",
            },
        },
        "avoid_overfitting": {
            "status": "controls_active_validation_not_mature",
            "evidence": {
                "config_fingerprint": config.fingerprint(),
                "prospective_signal_records": len(ledger["records"]),
                "prospective_outcomes_accessed": ledger["outcomes_accessed"],
                "earliest_stage_one_evaluation": prospective_registration[
                    "earliest_evaluation"
                ],
                "stage_two_gate_fingerprint": final_registration["gate_fingerprint"],
                "stage_one_records_reusable_in_stage_two": final_registration[
                    "stage_one_records_reusable"
                ],
            },
        },
        "paper_or_live_readiness": {
            "status": "not_authorized",
            "evidence": {
                "observer_health": health["formal_status"],
                "data_available_through": health["available_through"],
                "prospective_signal_records": health["signal_records"],
                "stage_one_decision": "not_mature",
                "live_capital_enabled": False,
            },
        },
    }
    return {
        "report_type": "ten_u_event_trend_goal_completion_audit_v2",
        "formal_status": "active_research_not_validated",
        "strategy_id": config.strategy_id,
        "config_fingerprint": config.fingerprint(),
        "as_of": health["as_of"],
        "requirements": requirements,
        "proven_complete_requirements": [
            name for name, item in requirements.items() if item["status"] == "implemented"
        ],
        "unproven_or_incomplete_requirements": [
            name for name, item in requirements.items() if item["status"] != "implemented"
        ],
        "next_binding_event": "first_stage_maturity_requires_calendar_and_completed_trade_minimums",
        "outcome_metrics_computed_from_prospective_data": False,
        "strategy_parameters_modified": False,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    print(json.dumps(build_goal_audit(root), indent=2))

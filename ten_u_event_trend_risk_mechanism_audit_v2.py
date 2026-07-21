"""Outcome-safe historical mechanism audit for stop sweeps and profit giveback."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any


def _directional_move(entry: float, price: float, direction: str) -> float:
    return (price / entry - 1.0) * (1.0 if direction == "long" else -1.0)


def build_risk_mechanism_audit(screen: dict[str, Any]) -> dict[str, Any]:
    if screen.get("phase") != "sealed_historical_screen":
        raise ValueError("only the already-open sealed historical screen may be audited")
    for key in ("v1_development_metrics_accessed", "case_contaminated_metrics_accessed", "prospective_metrics_accessed"):
        if screen.get(key) is not False:
            raise ValueError(f"outcome isolation not proven: {key}")

    account = screen["account"]
    trades = account["trades_detail"]
    hard_stops: list[dict[str, Any]] = []
    winners: list[dict[str, Any]] = []
    losses: list[dict[str, Any]] = []
    for trade in trades:
        entry = float(trade["entry_raw"])
        direction = trade["direction"]
        mae_move = _directional_move(entry, float(trade["mae_price"]), direction)
        item = {
            "symbol": trade["symbol"],
            "entry_time": trade["entry_time"],
            "exit_time": trade["exit_time"],
            "exit_reason": trade["exit_reason"],
            "holding_hours": float(trade["holding_hours"]),
            "net_pnl": float(trade["net_pnl"]),
            "equity_return_fraction": float(trade["net_pnl"]) / float(trade["equity_before"]),
            "maximum_adverse_price_move_fraction": mae_move,
        }
        if trade["net_pnl"] > 0:
            capture = float(trade["winner_capture_fraction"])
            winners.append({
                **item,
                "winner_capture_fraction": capture,
                "winner_mfe_giveback_fraction": 1.0 - capture,
            })
        else:
            losses.append(item)
        if trade["exit_reason"] == "hard_disaster_stop":
            stop_move = _directional_move(entry, float(trade["exit_raw"]), direction)
            hard_stops.append({
                **item,
                "hard_stop_price_move_fraction": stop_move,
                "additional_adverse_move_beyond_stop_fraction": abs(mae_move - stop_move),
                "recovered_original_entry": bool(trade["hard_stop_recovered_entry"]),
                "recovered_plus_1r": bool(trade["hard_stop_recovered_1r"]),
                "recovery_entry_hours_after_stop": trade["hard_stop_recovery_entry_hours"],
            })

    peak = float(account["peak_equity"])
    ending = float(account["ending_equity"])
    top_trade = max(trades, key=lambda trade: float(trade["net_pnl"]))
    return {
        "report_type": "ten_u_event_trend_risk_mechanism_audit_v2",
        "formal_status": "historical_diagnostic_only_no_parameter_change",
        "strategy_id": screen["strategy_id"],
        "config_fingerprint": screen["config_fingerprint"],
        "source_phase": screen["phase"],
        "prospective_metrics_accessed": False,
        "parameter_search_performed": False,
        "trades": len(trades),
        "hard_stop_count": len(hard_stops),
        "hard_stops": hard_stops,
        "winners": winners,
        "losses": losses,
        "median_winner_capture_fraction": median(
            item["winner_capture_fraction"] for item in winners
        ) if winners else 0.0,
        "account_peak_to_end_giveback_fraction": (peak - ending) / peak if peak else 0.0,
        "largest_winner_net_pnl_contribution": (
            float(top_trade["net_pnl"])
            / sum(float(trade["net_pnl"]) for trade in trades if trade["net_pnl"] > 0)
        ),
        "diagnosis": {
            "stop_sweep": "observed_once_but_wider_stop_would_have_exposed_materially_deeper_adverse_move",
            "winner_exit": "historical_winners_retained_most_of_their_price_mfe",
            "account_drawdown": "primarily_next_trade_loss_after_large_winner_not_winner_exit_giveback",
            "evidence_strength": "insufficient_three_trades_diagnostic_not_edge_proof",
        },
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    screen = json.loads((root / "reports/ten_u_event_trend_screen_v2.json").read_text(encoding="utf-8"))
    print(json.dumps(build_risk_mechanism_audit(screen), indent=2))

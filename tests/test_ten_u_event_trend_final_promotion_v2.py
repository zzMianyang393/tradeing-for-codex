import hashlib
import json
from pathlib import Path

from ten_u_event_trend_final_promotion_v2 import (
    FinalPromotionGateV2,
    build_final_promotion_preregistration,
    evaluate_final_promotion,
    count_independent_event_clusters,
    robust_profit_metrics,
)


def _replay(pnls, *, ending_equity=18.0, stress=False):
    entries = _independent_entries()
    return {
        "trades": len(pnls),
        "wins": sum(value > 0 for value in pnls),
        "trades_detail": [
            {
                "net_pnl": value,
                "symbol": "RAVE-USDT-SWAP" if index < 6 else "LAB-USDT-SWAP",
                "direction": "long",
                "entry_ts": entries[index],
            }
            for index, value in enumerate(pnls)
        ],
        "trades_by_symbol": {"RAVE-USDT-SWAP": 6, "LAB-USDT-SWAP": 6, "ETH-USDT-SWAP": 0},
        "ending_equity": ending_equity,
        "max_drawdown_fraction": 0.40,
        "peak_profit_retention": 0.75,
        "stopped_then_recovered_fraction": 0.20,
        "median_winner_capture": 0.55,
        **({"slippage_each_side": "0.0010"} if stress else {}),
    }


def _independent_entries(count=20):
    return [index * 49 * 60 * 60 * 1000 for index in range(count)]


def test_preregistration_is_outcome_blind_and_stage_one_is_not_live():
    registration = build_final_promotion_preregistration()
    assert registration["outcomes_accessed_at_registration"] is False
    assert registration["stage_one_role"] == "screen_for_paper_only"
    assert registration["stage_one_records_reusable"] is False


def test_gate_fingerprint_is_deterministic():
    assert FinalPromotionGateV2().fingerprint() == FinalPromotionGateV2().fingerprint()


def test_robust_metric_detects_single_winner_dependency():
    metrics = robust_profit_metrics(
        [{"net_pnl": value} for value in (100.0, 1.0, -20.0, -20.0)]
    )
    assert metrics["profit_factor"] > 1.0
    assert metrics["profit_factor_excluding_top_winner"] < 1.0
    assert metrics["top_winner_gross_profit_contribution"] > 0.60


def test_apparently_profitable_but_concentrated_replay_cannot_pass():
    result = evaluate_final_promotion(
        _replay([100, 2, 2, 2, -8, -8, -8, -8, -8, -8, -8, -8]),
        completed_signal_outcomes=20,
        calendar_days=180,
        completed_signal_entry_ts=_independent_entries(),
    )
    assert result["decision"] == "do_not_enable_live_capital"
    assert "profit_factor_excluding_top_winner_below_minimum" in result["reasons"]
    assert "top_winner_contribution_above_maximum" in result["reasons"]


def test_under_mature_sample_cannot_pass_even_with_good_pnl():
    result = evaluate_final_promotion(
        _replay([4, 4, 4, 4, 4, 4, 4, 4, -1, -1, -1, -1]),
        completed_signal_outcomes=19,
        calendar_days=179,
        completed_signal_entry_ts=_independent_entries(19),
    )
    assert "calendar_days_below_minimum" in result["reasons"]
    assert "completed_signal_outcomes_below_minimum" in result["reasons"]


def test_diversified_non_concentrated_replay_can_reach_capped_pilot_only():
    result = evaluate_final_promotion(
        _replay([5, 5, 5, 5, 4, 4, 3, 3, -2, -2, -2, -2]),
        completed_signal_outcomes=20,
        calendar_days=180,
        completed_signal_entry_ts=_independent_entries(),
        stress_replay=_replay([4, 4, 4, 4, 3, 3, 2, 2, -2, -2, -2, -2], stress=True),
    )
    assert result["formal_status"] == "stage_two_pass"
    assert result["decision"] == "eligible_for_capped_live_pilot"


def test_stage_two_pass_never_claims_full_live_approval():
    result = evaluate_final_promotion(
        _replay([5, 5, 5, 5, 4, 4, 3, 3, -2, -2, -2, -2]),
        completed_signal_outcomes=20,
        calendar_days=180,
        completed_signal_entry_ts=_independent_entries(),
        stress_replay=_replay([4, 4, 4, 4, 3, 3, 2, 2, -2, -2, -2, -2], stress=True),
    )
    assert "full_live" not in result["decision"]


def test_overlapping_cross_symbol_signals_count_as_one_market_event():
    hour = 60 * 60 * 1000
    assert count_independent_event_clusters([0, hour, 2 * hour, 47 * hour]) == 1
    assert count_independent_event_clusters([0, 48 * hour]) == 2


def test_twenty_correlated_signals_do_not_create_a_mature_sample():
    entries = [index * 2 * 60 * 60 * 1000 for index in range(20)]
    result = evaluate_final_promotion(
        _replay([5, 5, 5, 5, 4, 4, 3, 3, -2, -2, -2, -2]),
        completed_signal_outcomes=20,
        calendar_days=180,
        completed_signal_entry_ts=entries,
    )
    assert result["independent_event_clusters"] == 1
    assert "independent_event_clusters_below_minimum" in result["reasons"]


def test_signal_count_cannot_be_decoupled_from_cluster_timestamps():
    import pytest

    with pytest.raises(ValueError, match="one entry timestamp"):
        evaluate_final_promotion(
            _replay([5, 5, 5, 5, 4, 4, 3, 3, -2, -2, -2, -2]),
            completed_signal_outcomes=20,
            calendar_days=180,
            completed_signal_entry_ts=[0],
        )


def test_profitable_base_cannot_pass_when_stressed_costs_erase_edge():
    result = evaluate_final_promotion(
        _replay([5, 5, 5, 5, 4, 4, 3, 3, -2, -2, -2, -2]),
        completed_signal_outcomes=20,
        calendar_days=180,
        completed_signal_entry_ts=_independent_entries(),
        stress_replay=_replay([1, 1, 1, 1, -3, -3, -3, -3, -3, -3, -3, -3], ending_equity=7, stress=True),
    )
    assert "stress_profit_factor_below_minimum" in result["reasons"]
    assert "stress_ending_equity_below_minimum" in result["reasons"]


def test_stress_replay_must_use_same_trades_and_frozen_cost():
    import pytest

    base = _replay([5, 5, 5, 5, 4, 4, 3, 3, -2, -2, -2, -2])
    stress = _replay([4, 4, 4, 4, 3, 3, 2, 2, -2, -2, -2, -2], stress=True)
    stress["trades_detail"][0]["entry_ts"] += 1
    with pytest.raises(ValueError, match="identities differ"):
        evaluate_final_promotion(
            base,
            completed_signal_outcomes=20,
            calendar_days=180,
            completed_signal_entry_ts=_independent_entries(),
            stress_replay=stress,
        )


def test_static_preregistration_matches_builder_and_source_hash():
    root = Path(__file__).resolve().parents[1]
    stored = json.loads(
        (root / "reports/ten_u_event_trend_final_promotion_preregistration_v2.json")
        .read_text(encoding="utf-8")
    )
    built = build_final_promotion_preregistration()
    for key, value in built.items():
        assert stored[key] == value
    source = root / "ten_u_event_trend_final_promotion_v2.py"
    assert stored["source_sha256"][source.name] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert stored["registration_evidence"]["stage_one_signal_records"] == 0
    assert stored["registration_evidence"]["stage_one_outcomes_accessed"] is False

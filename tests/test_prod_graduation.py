"""Tests for local paper graduation evaluator (shipped prod.graduation)."""

from __future__ import annotations

from prod.graduation import (
    GraduationThresholds,
    evaluate_from_runtime_files,
    evaluate_local_paper_graduation,
)
from prod.policy import validate_start_equity, validate_production_bound_universe


def _base_state(**overrides):
    state = {
        "mode": "local_paper",
        "equity": 10.0,
        "closed_trades": [],
        "completed_cycle_count": 0,
        "halt_reason": None,
        "live_allowed": False,
        "places_exchange_orders": False,
        "exchange_orders_submitted": 0,
        "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    }
    state.update(overrides)
    return state


def test_insufficient_history_not_yet():
    result = evaluate_local_paper_graduation(
        _base_state(closed_trades=[], completed_cycle_count=2),
        registry_entry={"status": "paper_prep", "live_allowed": False},
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    )
    assert result.decision == "not_yet"
    assert result.graduated_local is False
    assert result.live_allowed is False
    assert result.places_exchange_orders is False
    assert any("insufficient_paper_history" in r for r in result.reasons)


def test_synthetic_meet_trade_threshold_graduated_local():
    trades = [{"net_pnl": 0.1} for _ in range(20)]
    result = evaluate_local_paper_graduation(
        _base_state(closed_trades=trades, completed_cycle_count=5),
        registry_entry={"status": "paper_prep", "live_allowed": False},
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    )
    assert result.decision == "graduated_local"
    assert result.graduated_local is True
    assert result.live_allowed is False
    assert result.places_exchange_orders is False
    assert result.demo_live_graduation_eligible is True
    assert result.ready_for_demo_stage_consideration is True
    assert result.track_class == "production_bound"


def test_synthetic_meet_cycle_threshold_without_trades():
    result = evaluate_local_paper_graduation(
        _base_state(closed_trades=[], completed_cycle_count=30),
        registry_entry={"status": "paper_prep"},
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    )
    assert result.decision == "graduated_local"
    assert result.graduated_local is True
    assert result.live_allowed is False


def test_halt_blocks_graduation():
    trades = [{"net_pnl": 1.0} for _ in range(25)]
    result = evaluate_local_paper_graduation(
        _base_state(
            closed_trades=trades,
            completed_cycle_count=40,
            halt_reason="ruined",
        ),
        registry_entry={"status": "paper_prep"},
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    )
    assert result.decision == "blocked"
    assert result.graduated_local is False
    assert any(b.startswith("halted:") for b in result.blockers)


def test_exchange_orders_block_graduation():
    trades = [{"net_pnl": 1.0} for _ in range(25)]
    result = evaluate_local_paper_graduation(
        _base_state(
            closed_trades=trades,
            completed_cycle_count=40,
            places_exchange_orders=True,
        ),
        registry_entry={"status": "paper_prep"},
        symbols=["BTC-USDT-SWAP"],
    )
    assert result.decision == "blocked"
    assert "exchange_orders_present_or_enabled" in result.blockers
    assert result.places_exchange_orders is False  # output invariant


def test_live_allowed_true_blocks():
    trades = [{"net_pnl": 1.0} for _ in range(25)]
    result = evaluate_local_paper_graduation(
        _base_state(closed_trades=trades, completed_cycle_count=40, live_allowed=True),
        registry_entry={"status": "paper_prep"},
        symbols=["ETH-USDT-SWAP"],
    )
    assert result.decision == "blocked"
    assert result.live_allowed is False  # output always false


def test_rave_lab_local_experiment_not_demo_ready_even_if_local_graduated():
    trades = [{"net_pnl": 1.0} for _ in range(20)]
    result = evaluate_local_paper_graduation(
        _base_state(
            closed_trades=trades,
            completed_cycle_count=10,
            symbols=["RAVE-USDT-SWAP", "LAB-USDT-SWAP", "ETH-USDT-SWAP"],
        ),
        registry_entry={"status": "paper_prep"},
        symbols=["RAVE-USDT-SWAP", "LAB-USDT-SWAP", "ETH-USDT-SWAP"],
    )
    assert result.decision == "graduated_local"
    assert result.graduated_local is True
    assert result.track_class == "local_experiment"
    assert result.demo_live_graduation_eligible is False
    assert result.ready_for_demo_stage_consideration is False
    assert result.live_allowed is False


def test_equity_policy_still_rejects_above_500():
    assert validate_start_equity(500.0).accepted is True
    assert validate_start_equity(501.0).accepted is False


def test_btc_eth_production_bound_universe():
    u = validate_production_bound_universe(["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    assert u.accepted_for_production_bound is True
    assert u.demo_live_graduation_eligible is True


def test_missing_state_not_yet():
    result = evaluate_from_runtime_files(state=None)
    assert result.decision == "not_yet"
    assert result.graduated_local is False


def test_multi_cycle_count_drives_graduation():
    """Simulate multi-cycle progress: cycles alone can graduate after threshold."""
    thr = GraduationThresholds(minimum_closed_trades=99, minimum_completed_cycles=3)
    early = evaluate_local_paper_graduation(
        _base_state(completed_cycle_count=1),
        registry_entry={"status": "paper_prep"},
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        thresholds=thr,
    )
    assert early.decision == "not_yet"

    later = evaluate_local_paper_graduation(
        _base_state(completed_cycle_count=3),
        registry_entry={"status": "paper_prep"},
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        thresholds=thr,
    )
    assert later.decision == "graduated_local"
    assert later.live_allowed is False
    assert later.places_exchange_orders is False


def test_registry_wrong_status_blocks():
    trades = [{"net_pnl": 1.0} for _ in range(25)]
    result = evaluate_local_paper_graduation(
        _base_state(closed_trades=trades, completed_cycle_count=40),
        registry_entry={"status": "rejected", "live_allowed": False},
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    )
    assert result.decision == "blocked"
    assert any("registry_status_not_paper_prep" in b for b in result.blockers)

"""Tests for ops summary and local paper halt recovery."""

from __future__ import annotations

import json
from pathlib import Path

from prod.halt_recovery import (
    apply_halt_recovery,
    plan_halt_recovery,
    recover_paper_state_file,
)
from prod.ops_summary import build_prod_ops_dashboard, build_sleeve_ops_summary
from prod.graduation import evaluate_local_paper_graduation


def test_ops_summary_ok_path():
    state = {
        "equity": 10.0,
        "peak_equity": 10.0,
        "halt_reason": None,
        "completed_cycle_count": 5,
        "closed_trades": [],
        "open_position": None,
        "live_allowed": False,
        "places_exchange_orders": False,
        "track_class": "production_bound",
        "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        "mode": "local_paper",
        "last_cycle_at": "2026-07-17T00:00:00Z",
    }
    reg = {"status": "paper_prep", "live_allowed": False}
    grad = evaluate_local_paper_graduation(
        state, registry_entry=reg, symbols=state["symbols"]
    )
    summary = build_sleeve_ops_summary(
        strategy_id="prod_majors_donchian_atr_long_v1",
        track_label="majors_production_bound",
        state=state,
        cycle_report=None,
        registry_entry=reg,
        graduation=grad,
    )
    assert summary["health"] == "ok"
    assert summary["places_exchange_orders"] is False
    assert summary["live_allowed"] is False
    assert summary["local_graduation"]["decision"] == "not_yet"


def test_ops_summary_halted():
    state = {
        "equity": 1.5,
        "peak_equity": 10.0,
        "halt_reason": "ruined",
        "completed_cycle_count": 40,
        "closed_trades": [{"net_pnl": -1}] * 25,
        "live_allowed": False,
        "places_exchange_orders": False,
        "track_class": "production_bound",
        "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    }
    reg = {"status": "paper_prep"}
    grad = evaluate_local_paper_graduation(
        state, registry_entry=reg, symbols=state["symbols"]
    )
    summary = build_sleeve_ops_summary(
        strategy_id="s",
        track_label="majors",
        state=state,
        cycle_report=None,
        registry_entry=reg,
        graduation=grad,
    )
    assert summary["health"] == "halted"
    assert any(a.startswith("halt:") for a in summary["alerts"])


def test_dashboard_aggregates():
    ok = build_sleeve_ops_summary(
        strategy_id="a",
        track_label="majors",
        state={
            "equity": 10,
            "peak_equity": 10,
            "halt_reason": None,
            "completed_cycle_count": 1,
            "closed_trades": [],
            "live_allowed": False,
            "places_exchange_orders": False,
            "track_class": "production_bound",
            "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        },
        cycle_report=None,
        registry_entry={"status": "paper_prep"},
    )
    halted = build_sleeve_ops_summary(
        strategy_id="b",
        track_label="ten_u",
        state={
            "equity": 2,
            "peak_equity": 10,
            "halt_reason": "ruined",
            "completed_cycle_count": 1,
            "closed_trades": [],
            "live_allowed": False,
            "places_exchange_orders": False,
            "track_class": "local_experiment",
            "symbols": ["RAVE-USDT-SWAP"],
        },
        cycle_report=None,
        registry_entry={"status": "paper_prep"},
    )
    dash = build_prod_ops_dashboard(majors_summary=ok, ten_u_summary=halted)
    assert dash["overall_health"] == "critical"
    assert dash["default_pipeline_places_exchange_orders"] is False


def test_halt_recovery_clear_and_hard_reset(tmp_path: Path):
    state = {
        "equity": 2.0,
        "peak_equity": 12.0,
        "halt_reason": "ruined",
        "open_position": {"symbol": "BTC-USDT-SWAP"},
        "closed_trades": [{"net_pnl": -1.0}],
        "completed_cycle_count": 9,
        "live_allowed": False,
        "places_exchange_orders": False,
    }
    plan = plan_halt_recovery(state, mode="clear_halt_only")
    assert plan["allowed"] is True
    assert plan["live_allowed_after"] is False

    cleared = apply_halt_recovery(state, mode="clear_halt_only")
    assert cleared["halt_reason"] is None
    assert cleared["open_position"] is not None  # clear_halt keeps open
    assert cleared["live_allowed"] is False
    assert cleared["places_exchange_orders"] is False

    flat = apply_halt_recovery(state, mode="flat_and_clear")
    assert flat["open_position"] is None
    assert flat["closed_trades"]  # history kept

    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    blocked = recover_paper_state_file(
        path, mode="hard_reset_paper", confirm_hard_reset=False
    )
    assert blocked["formal_status"] == "blocked_needs_confirm_hard_reset"

    ok = recover_paper_state_file(
        path,
        mode="hard_reset_paper",
        confirm_hard_reset=True,
        start_equity=10.0,
        operator_note="test reset",
    )
    assert ok["formal_status"] == "ok"
    assert ok["live_allowed"] is False
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["halt_reason"] is None
    assert loaded["equity"] == 10.0
    assert loaded["closed_trades"] == []
    assert loaded["completed_cycle_count"] == 0
    assert loaded["places_exchange_orders"] is False

"""Tests for operator hard constraints in prod.policy (shipped validators)."""

from __future__ import annotations

from prod.admission import admit_from_account_summary
from prod.demo_execution_drill import DEMO_ALLOWED_SYMBOLS, DEMO_BLOCKED_SYMBOLS, plan_demo_drill
from prod.policy import (
    DEFAULT_START_EQUITY_USDT,
    MAX_START_EQUITY_USDT,
    PRODUCTION_BOUND_SYMBOLS,
    annotate_local_paper_cycle,
    classify_symbol,
    default_pipeline_places_exchange_orders,
    is_production_bound_symbol,
    operator_policy_snapshot,
    validate_production_bound_universe,
    validate_start_equity,
)
from prod.registry import default_registry_policy


def test_default_start_equity_accepted():
    result = validate_start_equity(10.0)
    assert result.accepted is True
    assert result.band == "default_10"
    assert result.equity == DEFAULT_START_EQUITY_USDT


def test_capital_sensitivity_100_and_500_accepted():
    for equity in (100.0, 500.0):
        result = validate_start_equity(equity)
        assert result.accepted is True, equity
        assert result.band == "capital_sensitivity"
        assert result.warnings


def test_start_equity_above_500_rejected():
    result = validate_start_equity(500.01)
    assert result.accepted is False
    assert result.band == "rejected"
    assert "start_equity_above_max_500u" in result.reasons


def test_start_equity_below_10_rejected():
    result = validate_start_equity(9.99)
    assert result.accepted is False
    assert "start_equity_below_default_10u" in result.reasons


def test_production_bound_btc_eth_allowed():
    assert is_production_bound_symbol("BTC-USDT-SWAP")
    assert is_production_bound_symbol("ETH")
    assert is_production_bound_symbol("btc-usdt")
    universe = validate_production_bound_universe(["BTC-USDT-SWAP", "ETH-USDT-SWAP"])
    assert universe.accepted_for_production_bound is True
    assert universe.demo_live_graduation_eligible is True
    assert universe.track_class == "production_bound"


def test_rave_lab_local_experiment_not_production_bound():
    rave = classify_symbol("RAVE-USDT-SWAP")
    assert rave.production_bound is False
    assert rave.class_name == "local_experiment"
    assert rave.demo_live_graduation_eligible is False

    universe = validate_production_bound_universe(
        ["RAVE-USDT-SWAP", "LAB-USDT-SWAP", "ETH-USDT-SWAP"]
    )
    assert universe.accepted_for_production_bound is False
    assert universe.demo_live_graduation_eligible is False
    assert universe.track_class == "local_experiment"


def test_non_production_symbol_flagged():
    sol = classify_symbol("SOL-USDT-SWAP")
    assert sol.production_bound is False
    assert sol.class_name == "non_production"
    universe = validate_production_bound_universe(["SOL-USDT-SWAP"])
    assert universe.accepted_for_production_bound is False
    assert "contains_non_production_symbols" in universe.reasons


def test_default_pipeline_never_places_exchange_orders():
    assert default_pipeline_places_exchange_orders() is False
    snap = operator_policy_snapshot()
    assert snap["default_pipeline_places_exchange_orders"] is False
    assert snap["default_start_equity_usdt"] == 10.0
    assert snap["max_start_equity_usdt"] == MAX_START_EQUITY_USDT
    assert set(snap["production_bound_symbols"]) == set(PRODUCTION_BOUND_SYMBOLS)


def test_annotate_local_paper_cycle_marks_legacy_sleeve():
    block = annotate_local_paper_cycle(
        symbols=["RAVE-USDT-SWAP", "LAB-USDT-SWAP", "ETH-USDT-SWAP"],
        start_equity=10.0,
    )
    assert block["places_exchange_orders"] is False
    assert block["live_allowed"] is False
    assert block["demo_live_graduation_eligible"] is False
    assert block["track_class"] == "local_experiment"
    assert block["mode"] == "local_paper"


def test_admission_rejects_start_equity_above_500():
    account = {
        "trades": 8,
        "starting_equity": 1000.0,
        "ending_equity": 1200.0,
        "max_drawdown_fraction": 0.1,
        "profit_factor": 2.0,
        "permanent_account_state": "active_or_temporary_cooldown",
        "trades_detail": [{"net_pnl": 25.0}] * 8,
    }
    result = admit_from_account_summary(
        strategy_id="s",
        track="t",
        account=account,
        high_risk_sleeve=True,
        accept_concentration_risk=True,
        symbols=["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
    )
    assert result.paper_prep_allowed is False
    assert "start_equity_above_max_500u" in result.reasons


def test_admission_flags_local_experiment_universe_but_can_allow_paper():
    account = {
        "trades": 8,
        "starting_equity": 10.0,
        "ending_equity": 50.0,
        "max_drawdown_fraction": 0.1,
        "profit_factor": 2.0,
        "permanent_account_state": "active_or_temporary_cooldown",
        "trades_detail": [{"net_pnl": 5.0}] * 8,
    }
    result = admit_from_account_summary(
        strategy_id="ten_u",
        track="ten_u_high_risk",
        account=account,
        high_risk_sleeve=True,
        accept_concentration_risk=True,
        symbols=["RAVE-USDT-SWAP", "LAB-USDT-SWAP", "ETH-USDT-SWAP"],
    )
    assert result.paper_prep_allowed is True
    assert result.live_allowed is False
    assert result.operator_flags["demo_live_graduation_eligible"] is False
    assert result.operator_flags["default_pipeline_places_exchange_orders"] is False
    assert any("local_experiment" in w for w in result.warnings)


def test_demo_allowlist_matches_production_bound_policy():
    assert DEMO_ALLOWED_SYMBOLS == PRODUCTION_BOUND_SYMBOLS
    assert "RAVE-USDT-SWAP" in DEMO_BLOCKED_SYMBOLS
    blocked = plan_demo_drill("RAVE-USDT-SWAP", confirm_smoke=False)
    assert blocked.allowed is False
    allowed = plan_demo_drill("ETH-USDT-SWAP", confirm_smoke=False)
    assert allowed.allowed is True


def test_registry_policy_includes_operator_constraints():
    policy = default_registry_policy()
    assert policy["default_start_equity_usdt"] == 10.0
    assert policy["max_start_equity_usdt"] == 500.0
    assert policy["default_pipeline_places_exchange_orders"] is False
    assert "BTC-USDT-SWAP" in policy["production_bound_symbols"]
    assert "ETH-USDT-SWAP" in policy["production_bound_symbols"]

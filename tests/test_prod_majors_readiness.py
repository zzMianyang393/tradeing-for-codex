"""Tests for majors local readiness package + conservative compare."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import load_majors_market, replay_majors_account
from prod.majors_contract import (
    CONSERVATIVE_STRATEGY_ID,
    STRATEGY_ID,
    conservative_majors_config,
    primary_majors_config,
)
from prod.majors_readiness import build_admission_notes, build_majors_readiness_package


def test_primary_and_conservative_fingerprints_differ():
    p = primary_majors_config()
    c = conservative_majors_config()
    assert p.strategy_id == STRATEGY_ID
    assert c.strategy_id == CONSERVATIVE_STRATEGY_ID
    assert p.fingerprint() != c.fingerprint()
    assert c.risk_per_trade < p.risk_per_trade
    assert c.donchian_lookback > p.donchian_lookback


def test_config_with_equity_preserves_conservative_fields():
    from prod.majors_account_replay import _config_with_equity

    c = conservative_majors_config(10.0)
    c100 = _config_with_equity(c, 100.0)
    assert c100.strategy_id == CONSERVATIVE_STRATEGY_ID
    assert c100.risk_per_trade == c.risk_per_trade
    assert c100.start_equity == 100.0


def test_admission_notes_flag_negative_primary():
    notes = build_admission_notes(
        primary_10={
            "config_fingerprint": "abc",
            "starting_equity": 10.0,
            "ending_equity": 7.0,
        },
        conservative_10={
            "config_fingerprint": "def",
            "starting_equity": 10.0,
            "ending_equity": 9.0,
        },
        sensitivity={"formal_status": "ok"},
        graduation_decision="not_yet",
        ops_health="ok",
    )
    assert any("primary_10u_fingerprint_negative" in n for n in notes)
    assert "local_paper_only_no_exchange_orders" in notes
    assert any("conservative_rule_is_comparison_only" in n for n in notes)


def test_readiness_package_on_real_data(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists() or not (data / "ETH_15m.csv").exists():
        pytest.skip("data missing")

    # Shared market path used internally
    market = load_majors_market(data)
    assert "BTC-USDT-SWAP" in market

    pkg = build_majors_readiness_package(
        data,
        state_path=tmp_path / "missing_state.json",
        cycle_path=tmp_path / "missing_cycle.json",
        registry_path=tmp_path / "missing_reg.json",
        max_bars=2000,
        include_conservative=True,
    )
    assert pkg["places_exchange_orders"] is False
    assert pkg["live_allowed"] is False
    assert pkg["ready_for_demo"] is False
    assert pkg["ready_for_live"] is False
    assert pkg["primary"]["strategy_id"] == STRATEGY_ID
    assert pkg["primary"]["replay_10u"]["formal_status"] == "ok"
    assert pkg["primary"]["capital_sensitivity"]["formal_status"] in {"ok", "partial"}
    assert len(pkg["primary"]["capital_sensitivity"]["rungs"]) == 3
    assert pkg["conservative_compare"]["strategy_id"] == CONSERVATIVE_STRATEGY_ID
    assert pkg["conservative_compare"]["not_default_paper_runtime"] is True
    assert pkg["conservative_compare"]["replay_10u"]["formal_status"] == "ok"
    assert pkg["primary"]["config"]["config_fingerprint"] != pkg[
        "conservative_compare"
    ]["config"]["config_fingerprint"]
    assert "admission_notes" in pkg and len(pkg["admission_notes"]) >= 3
    # Without registry/state still can be ready_for_local_ops if fingerprint ok
    assert pkg["formal_status"] in {
        "ready_for_local_ops",
        "not_ready_local",
        "local_ops_halted",
    }


def test_conservative_replay_uses_stricter_config():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    market = load_majors_market(data)
    primary = replay_majors_account(
        data, config=primary_majors_config(), max_bars=1500, market=market
    )
    cons = replay_majors_account(
        data, config=conservative_majors_config(), max_bars=1500, market=market
    )
    assert primary["formal_status"] == "ok"
    assert cons["formal_status"] == "ok"
    # Conservative typically fewer or equal trades
    assert cons["account"]["trades"] <= primary["account"]["trades"] + 5

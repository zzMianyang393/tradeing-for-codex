"""Tests for production-bound BTC/ETH majors sleeve (shipped prod modules)."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import replay_majors_account
from prod.majors_contract import MajorsSleeveConfig, STRATEGY_ID
from prod.majors_paper_runtime import run_majors_paper_cycle
from prod.policy import validate_production_bound_universe, validate_start_equity
from prod.registry import PaperPrepEntry, upsert_entry


def test_majors_contract_fingerprint_stable():
    a = MajorsSleeveConfig()
    b = MajorsSleeveConfig()
    assert a.fingerprint() == b.fingerprint()
    assert a.strategy_id == STRATEGY_ID
    assert set(a.symbols) == {"BTC-USDT-SWAP", "ETH-USDT-SWAP"}


def test_majors_contract_rejects_equity_above_500():
    with pytest.raises(ValueError):
        MajorsSleeveConfig(start_equity=501.0)


def test_majors_contract_rejects_non_production_symbols():
    with pytest.raises(ValueError):
        MajorsSleeveConfig(symbols=("BTC-USDT-SWAP", "SOL-USDT-SWAP"))


def test_replay_rejects_equity_above_500(tmp_path: Path):
    # data_dir unused on early reject
    report = replay_majors_account(tmp_path, start_equity=1000.0)
    assert report["formal_status"] == "rejected_equity_policy"
    assert validate_start_equity(1000.0).accepted is False


def test_replay_and_paper_cycle_on_real_data(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists() or not (data / "ETH_15m.csv").exists():
        pytest.skip("BTC/ETH 15m data missing")

    report = replay_majors_account(data, start_equity=10.0, max_bars=8000)
    assert report["formal_status"] == "ok"
    assert report["places_exchange_orders"] is False
    assert report["live_allowed"] is False
    assert report["track_class"] == "production_bound"
    assert report["demo_live_graduation_eligible"] is True
    assert report["account"]["starting_equity"] == 10.0
    assert "config_fingerprint" in report
    u = validate_production_bound_universe(report["symbols"])
    assert u.accepted_for_production_bound is True

    # capital sensitivity 100 still accepted by policy path
    sens = replay_majors_account(data, start_equity=100.0, max_bars=3000)
    assert sens["formal_status"] == "ok"
    assert sens["account"]["starting_equity"] == 100.0

    registry = tmp_path / "registry.json"
    state = tmp_path / "majors_state.json"
    cycle = tmp_path / "majors_cycle.json"
    upsert_entry(
        PaperPrepEntry(
            strategy_id=STRATEGY_ID,
            track="production_bound_majors",
            status="paper_prep",
            config_fingerprint=report["config_fingerprint"],
            admitted_at="2026-07-17T00:00:00Z",
            admission_decision="test_seed",
            live_allowed=False,
            notes="test",
        ),
        registry,
    )
    cycle_report = run_majors_paper_cycle(
        data_dir=data,
        state_path=state,
        registry_path=registry,
        cycle_path=cycle,
    )
    assert cycle_report["formal_status"] == "ok"
    assert cycle_report["places_exchange_orders"] is False
    assert cycle_report["live_allowed"] is False
    assert cycle_report["track_class"] == "production_bound"
    assert cycle_report["demo_live_graduation_eligible"] is True
    assert "local_graduation" in cycle_report
    assert cycle_report["local_graduation"]["live_allowed"] is False
    assert cycle_report["completed_cycle_count"] == 1

    cycle2 = run_majors_paper_cycle(
        data_dir=data,
        state_path=state,
        registry_path=registry,
        cycle_path=cycle,
    )
    assert cycle2["formal_status"] == "ok"
    assert cycle2["completed_cycle_count"] == 2


def test_paper_cycle_blocked_without_registry(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    report = run_majors_paper_cycle(
        data_dir=data,
        state_path=tmp_path / "s.json",
        registry_path=tmp_path / "empty_reg.json",
        cycle_path=tmp_path / "c.json",
        force=False,
    )
    assert report["formal_status"] == "blocked_not_in_paper_prep_registry"

"""Tests for majors capital sensitivity + locked local pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_capital_sensitivity import run_majors_capital_sensitivity
from prod.majors_contract import STRATEGY_ID
from prod.majors_pipeline import (
    majors_data_preflight,
    run_majors_locked_pipeline,
    run_majors_watch_loop,
)
from prod.policy import validate_start_equity
from prod.registry import PaperPrepEntry, upsert_entry


def test_capital_sensitivity_rejects_above_500_in_ladder(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    report = run_majors_capital_sensitivity(
        data,
        equities=(10.0, 100.0, 501.0),
        max_bars=2500,
    )
    assert report["places_exchange_orders"] is False
    assert report["live_allowed"] is False
    assert any(r["equity"] == 501.0 for r in report["rejected"])
    assert validate_start_equity(501.0).accepted is False
    # baseline 10 present when data ok
    assert any(abs(r["equity"] - 10.0) < 1e-9 for r in report["rungs"])


def test_capital_sensitivity_ladder_10_100_500(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists() or not (data / "ETH_15m.csv").exists():
        pytest.skip("data missing")
    report = run_majors_capital_sensitivity(
        data,
        equities=(10.0, 100.0, 500.0),
        max_bars=2500,
    )
    assert report["formal_status"] in {"ok", "partial"}
    assert report["track_class"] == "production_bound"
    assert len(report["rungs"]) == 3
    for rung in report["rungs"]:
        assert rung["full_formal_status"] == "ok"
        assert rung["summary"]["starting_equity"] == rung["equity"]
    # 10U baseline required
    base = next(r for r in report["rungs"] if r["equity"] == 10.0)
    assert base["band"] == "default_10"
    assert base["summary"]["formal_status"] == "ok"


def test_preflight_and_locked_pipeline(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    pre = majors_data_preflight(data)
    assert pre["formal_status"] == "ok"
    assert pre["places_exchange_orders"] is False

    registry = tmp_path / "reg.json"
    state = tmp_path / "state.json"
    cycle = tmp_path / "cycle.json"
    lock = tmp_path / "lock"
    upsert_entry(
        PaperPrepEntry(
            strategy_id=STRATEGY_ID,
            track="production_bound_majors",
            status="paper_prep",
            config_fingerprint="test",
            admitted_at="2026-07-17T00:00:00Z",
            admission_decision="test",
            live_allowed=False,
        ),
        registry,
    )
    pipeline = run_majors_locked_pipeline(
        data_dir=data,
        state_path=state,
        registry_path=registry,
        cycle_path=cycle,
        lock_path=lock,
    )
    assert pipeline["formal_status"] == "ok"
    assert pipeline["places_exchange_orders"] is False
    assert pipeline["paper_cycle"]["formal_status"] == "ok"
    assert pipeline["paper_cycle"]["track_class"] == "production_bound"

    watch = run_majors_watch_loop(
        iterations=2,
        interval_seconds=0.0,
        data_dir=data,
        state_path=state,
        registry_path=registry,
        cycle_path=cycle,
        lock_path=lock,
        report_path=tmp_path / "watch.json",
        sleep_fn=lambda _s: None,
    )
    assert watch["formal_status"] == "ok"
    assert watch["places_exchange_orders"] is False
    assert len(watch["cycles"]) == 2
    assert watch["cycles"][1]["paper_cycle"]["completed_cycle_count"] == 3

"""Tests for majors hourly job and Stage-3 demo checklist."""

from __future__ import annotations

from pathlib import Path

from prod.demo_stage_checklist import evaluate_demo_stage_checklist
from prod.majors_pipeline import run_majors_refresh_then_paper, run_majors_watch_loop
from prod.registry import PaperPrepEntry, upsert_entry
from prod.majors_contract import STRATEGY_ID


def test_refresh_then_paper_with_stub_refresh(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        import pytest

        pytest.skip("data missing")

    registry = tmp_path / "reg.json"
    state = tmp_path / "state.json"
    cycle = tmp_path / "cycle.json"
    lock = tmp_path / "lock"
    upsert_entry(
        PaperPrepEntry(
            strategy_id=STRATEGY_ID,
            track="production_bound_majors",
            status="paper_prep",
            config_fingerprint="t",
            admitted_at="2026-07-17T00:00:00Z",
            admission_decision="test",
            live_allowed=False,
        ),
        registry,
    )

    def fake_refresh(data_dir, commit=False, workers=1):
        return {
            "formal_status": "ok",
            "committed": commit,
            "total_append_count": 0,
            "places_exchange_orders": False,
        }

    job = run_majors_refresh_then_paper(
        data_dir=data,
        state_path=state,
        registry_path=registry,
        cycle_path=cycle,
        lock_path=lock,
        refresh_data=True,
        commit_refresh=True,
        refresh_fn=fake_refresh,
    )
    assert job["report_type"] == "majors_hourly_job"
    assert job["places_exchange_orders"] is False
    assert job["live_allowed"] is False
    assert job["formal_status"] == "ok"
    assert job["data_refresh"]["total_append_count"] == 0
    assert job["paper_pipeline"]["formal_status"] == "ok"


def test_watch_with_refresh_flag(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        import pytest

        pytest.skip("data missing")
    registry = tmp_path / "reg.json"
    state = tmp_path / "state.json"
    cycle = tmp_path / "cycle.json"
    lock = tmp_path / "lock"
    upsert_entry(
        PaperPrepEntry(
            strategy_id=STRATEGY_ID,
            track="production_bound_majors",
            status="paper_prep",
            config_fingerprint="t",
            admitted_at="2026-07-17T00:00:00Z",
            admission_decision="test",
            live_allowed=False,
        ),
        registry,
    )
    calls = {"n": 0}

    def fake_refresh(data_dir, commit=False, workers=1):
        calls["n"] += 1
        return {"formal_status": "ok", "committed": False, "total_append_count": 0}

    def pipeline_once():
        return run_majors_refresh_then_paper(
            data_dir=data,
            state_path=state,
            registry_path=registry,
            cycle_path=cycle,
            lock_path=lock,
            refresh_data=True,
            commit_refresh=False,
            refresh_fn=fake_refresh,
        )

    watch = run_majors_watch_loop(
        iterations=2,
        interval_seconds=0,
        data_dir=data,
        state_path=state,
        registry_path=registry,
        cycle_path=cycle,
        lock_path=lock,
        refresh_data=True,
        commit_refresh=False,
        report_path=tmp_path / "watch.json",
        pipeline_fn=pipeline_once,
        sleep_fn=lambda _s: None,
    )
    assert watch["formal_status"] == "ok"
    assert watch["refresh_data"] is True
    assert calls["n"] == 2
    assert watch["places_exchange_orders"] is False


def test_demo_checklist_never_enables_trading():
    result = evaluate_demo_stage_checklist(
        data_dir=Path("data"),
        require_local_graduation=False,
        require_demo_credentials=False,
    )
    assert result.auto_trading_enabled is False
    assert result.places_exchange_orders is False
    assert result.live_allowed is False
    assert result.demo_strategy_loop_enabled is False
    payload = result.to_dict()
    assert payload["auto_trading_enabled"] is False
    # Should have items
    assert len(result.items) >= 8
    ids = {i.id for i in result.items}
    assert "default_pipeline_no_exchange" in ids
    assert "production_bound_universe_btc_eth" in ids

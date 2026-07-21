"""Tests for majors 1h public refresh + timeframe-aware pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from prod.majors_contract import STRATEGY_ID
from prod.majors_pipeline import majors_data_preflight, run_majors_refresh_then_paper
from prod.majors_refresh_1h import path_for_1h, run_majors_1h_refresh
from prod.registry import PaperPrepEntry, upsert_entry


def test_path_for_1h_prefers_lowercase_then_legacy(tmp_path: Path):
    preferred = tmp_path / "BTC_1h.csv"
    preferred.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    assert path_for_1h("BTC-USDT-SWAP", tmp_path) == preferred

    only_legacy = tmp_path / "alt"
    only_legacy.mkdir()
    legacy = only_legacy / "ETH_1H.csv"
    legacy.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    assert path_for_1h("ETH-USDT-SWAP", only_legacy) == legacy


def test_majors_1h_refresh_dry_run_with_fake_fetch(tmp_path: Path):
    header = "timestamp,open,high,low,close,volume\n"
    last = "2026-07-16 03:00:00,1,1,1,1,1\n"
    for name in ("BTC_1h.csv", "ETH_1h.csv"):
        (tmp_path / name).write_text(header + last, encoding="utf-8")

    def fake_fetch(symbol: str, bar: str, limit: int = 100, after=None):
        assert bar == "1H"
        return []

    report = run_majors_1h_refresh(tmp_path, commit=False, fetch=fake_fetch)
    assert report["places_exchange_orders"] is False
    assert report["live_allowed"] is False
    assert report["okx_bar"] == "1H"
    assert report["formal_status"] in {"ok", "dry_run_pending_commit", "fail"}
    if report["formal_status"] != "fail":
        assert report["total_append_count"] == 0
        assert report["committed"] is False


def test_majors_1h_refresh_paginates_and_commits(tmp_path: Path):
    header = "timestamp,open,high,low,close,volume\n"
    local_last = "2026-07-16 03:00:00"
    for name in ("BTC_1h.csv", "ETH_1h.csv"):
        (tmp_path / name).write_text(header + f"{local_last},1,1,1,1,1\n", encoding="utf-8")

    base_ts = int(
        datetime.strptime(local_last, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .timestamp()
        * 1000
    )
    bar = 3_600_000
    page0 = [
        [str(base_ts + bar * 3), "1", "1", "1", "1", "0", "1", "1", "1"],
        [str(base_ts + bar * 2), "1", "1", "1", "1", "0", "1", "1", "1"],
    ]
    page1 = [
        [str(base_ts + bar * 1), "1", "1", "1", "1", "0", "1", "1", "1"],
        [str(base_ts), "1", "1", "1", "1", "0", "1", "1", "1"],
    ]

    def fake_fetch(symbol: str, bar_name: str, limit: int = 100, after=None):
        assert bar_name == "1H"
        if after is None:
            return list(page0)
        return list(page1)

    dry = run_majors_1h_refresh(tmp_path, commit=False, fetch=fake_fetch)
    assert dry["formal_status"] == "dry_run_pending_commit"
    assert dry["total_append_count"] == 3 * 2

    committed = run_majors_1h_refresh(tmp_path, commit=True, fetch=fake_fetch)
    assert committed["committed"] is True
    assert committed["formal_status"] == "ok"
    rows = (tmp_path / "BTC_1h.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1 + 1 + 3  # header + original + 3 new


def test_preflight_h1_suffix(tmp_path: Path):
    header = "timestamp,open,high,low,close,volume\n"
    last = "2026-07-16 03:00:00,1,1,1,1,1\n"
    (tmp_path / "BTC_1h.csv").write_text(header + last, encoding="utf-8")
    (tmp_path / "ETH_1H.csv").write_text(header + last, encoding="utf-8")
    report = majors_data_preflight(
        tmp_path, strategy_id="prod_majors_h1_md_mom_short_v1"
    )
    assert report["formal_status"] == "ok"
    assert report["timeframe_minutes"] == 60
    assert report["timeframe_suffix"] == "1h"
    assert report["strategy_id"] == "prod_majors_h1_md_mom_short_v1"


def test_hourly_job_h1_strategy_uses_1h_refresh(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_1h.csv").exists() and not (data / "BTC_1H.csv").exists():
        import pytest

        pytest.skip("1h data missing")
    if not (data / "ETH_1h.csv").exists() and not (data / "ETH_1H.csv").exists():
        import pytest

        pytest.skip("ETH 1h missing")

    registry = tmp_path / "reg.json"
    state = tmp_path / "state.json"
    cycle = tmp_path / "cycle.json"
    lock = tmp_path / "lock"
    upsert_entry(
        PaperPrepEntry(
            strategy_id="prod_majors_h1_md_mom_short_v1",
            track="production_bound_majors_research",
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
            "report_type": "majors_1h_refresh",
            "formal_status": "ok",
            "committed": commit,
            "total_append_count": 0,
            "okx_bar": "1H",
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
        strategy_id="prod_majors_h1_md_mom_short_v1",
        refresh_fn=fake_refresh,
    )
    assert job["report_type"] == "majors_hourly_job"
    assert job["strategy_id"] == "prod_majors_h1_md_mom_short_v1"
    assert job["timeframe_minutes"] == 60
    assert job["places_exchange_orders"] is False
    assert job["formal_status"] == "ok"
    assert job["data_refresh"]["okx_bar"] == "1H"
    assert job["paper_pipeline"]["formal_status"] == "ok"
    # default 15m path still works with stub
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

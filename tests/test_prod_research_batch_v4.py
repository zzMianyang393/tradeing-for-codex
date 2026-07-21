"""Tests for native daily batch v4 and sparse OOS helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import _bars_per_day
from prod.majors_contract import MajorsSleeveConfig
from prod.research_batch_majors_v4 import research_catalog_v4, run_majors_research_batch_v4
from prod.research_sparse_oos import run_weekly_candidates_oos


def test_bars_per_day_scales():
    assert _bars_per_day(MajorsSleeveConfig(timeframe_minutes=15)) == 96
    assert _bars_per_day(MajorsSleeveConfig(timeframe_minutes=1440)) == 1


def test_v4_catalog_daily_tf():
    cat = research_catalog_v4()
    assert len(cat) >= 8
    assert all(c["config"].timeframe_minutes == 1440 for c in cat)


def test_v4_batch_if_data():
    data = Path("data")
    if not (data / "BTC_1d.csv").exists():
        pytest.skip("daily data missing")
    report = run_majors_research_batch_v4(data, start_equity=10.0)
    assert report["formal_status"] == "ok"
    assert report["timeframe_minutes"] == 1440
    assert report["places_exchange_orders"] is False


def test_weekly_oos_runs():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    report = run_weekly_candidates_oos(data)
    assert report["formal_status"] == "ok"
    assert len(report["results"]) >= 1

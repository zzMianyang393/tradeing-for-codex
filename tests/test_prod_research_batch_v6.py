"""Tests for batch v6 + multiwindow OOS + v6 OOS."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.research_batch_majors_v6 import research_catalog_v6, run_majors_research_batch_v6
from prod.research_h1_multiwindow_oos import candidate_specs, run_h1_multiwindow_oos
from prod.research_v6_oos import run_v6_interesting_oos


def test_v6_catalog_timeframes():
    cat = research_catalog_v6()
    assert len(cat) >= 20
    tfs = {c["config"].timeframe_minutes for c in cat}
    assert 60 in tfs
    assert 240 in tfs
    assert any("dual_" in c["config"].signal_family for c in cat)


def test_multiwindow_candidate_specs():
    specs = candidate_specs()
    names = {s["name"] for s in specs}
    assert "h1_md_mom_short" in names
    assert "h1_dual_md_mom_short" in names


def test_v6_batch_if_data():
    data = Path("data")
    if not (data / "BTC_1h.csv").exists() and not (data / "BTC_1H.csv").exists():
        pytest.skip("1h missing")
    if not (data / "BTC_4h.csv").exists() and not (data / "BTC_4H.csv").exists():
        pytest.skip("4h missing")
    report = run_majors_research_batch_v6(data, max_bars=2000, start_equity=10.0)
    assert report["formal_status"] == "ok"
    assert report["candidate_count"] >= 20
    assert report["places_exchange_orders"] is False


def test_multiwindow_oos_if_data():
    data = Path("data")
    if not (data / "BTC_1h.csv").exists() and not (data / "BTC_1H.csv").exists():
        pytest.skip("1h missing")
    report = run_h1_multiwindow_oos(
        data,
        formation_fracs=(0.60,),
        embargo_bars=24,
    )
    assert report["formal_status"] == "ok"
    assert len(report["results"]) == 2
    assert report["places_exchange_orders"] is False


def test_v6_oos_named_if_data():
    data = Path("data")
    if not (data / "BTC_4h.csv").exists() and not (data / "BTC_4H.csv").exists():
        pytest.skip("4h missing")
    report = run_v6_interesting_oos(
        data,
        names=["h4_md_mom_short"],
        start_equity=10.0,
    )
    assert report["formal_status"] == "ok"
    assert len(report["results"]) == 1
    assert report["results"][0]["name"] == "h4_md_mom_short"

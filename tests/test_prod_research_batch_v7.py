"""Tests for batch v7 structural families + gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import _signal_table, resolve_entry_signal
from prod.majors_contract import MajorsSleeveConfig, TRACK_RESEARCH
from prod.research_batch_majors_v7 import research_catalog_v7, run_majors_research_batch_v7
from prod.research_v7_gates import run_v7_gates


def test_v7_signal_families_registered():
    table = _signal_table()
    for fam in (
        "high_vol_donchian_short",
        "failed_breakout_short",
        "ny_session_mom_short",
        "asia_session_range_long",
        "outside_reversal_short",
        "low_vol_bb_long",
    ):
        assert fam in table


def test_v7_catalog():
    cat = research_catalog_v7()
    assert len(cat) >= 25
    tfs = {c["config"].timeframe_minutes for c in cat}
    assert {15, 60, 240} <= tfs
    families = {c["config"].signal_family for c in cat}
    assert "rel_weak_md_mom_short" in families
    assert "failed_breakout_short" in families


def test_rel_weak_family_in_resolve():
    # empty market -> None, but family path must not raise
    cfg = MajorsSleeveConfig(
        strategy_id="t",
        track=TRACK_RESEARCH,
        signal_family="rel_weak_md_mom_short",
    )
    assert (
        resolve_entry_signal({}, {}, 0, cfg, ("BTC-USDT-SWAP", "ETH-USDT-SWAP"))
        is None
    )


def test_v7_batch_if_data():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("15m missing")
    report = run_majors_research_batch_v7(data, max_bars=2500, start_equity=10.0)
    assert report["formal_status"] == "ok"
    assert report["candidate_count"] >= 25
    assert report["places_exchange_orders"] is False


def test_v7_gates_named_if_data():
    data = Path("data")
    if not (data / "BTC_4h.csv").exists() and not (data / "BTC_4H.csv").exists():
        pytest.skip("4h missing")
    report = run_v7_gates(
        data,
        names=["h4_weekly_mom_short_recheck"],
        formation_fracs=(0.60,),
    )
    assert report["formal_status"] == "ok"
    assert len(report["results"]) == 1
    assert report["places_exchange_orders"] is False

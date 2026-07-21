"""Tests for majors research batch runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import _signal_direction
from prod.majors_contract import MajorsSleeveConfig
from prod.research_batch_majors import research_catalog, run_majors_research_batch


def test_catalog_has_multiple_distinct_families():
    cat = research_catalog()
    assert len(cat) >= 8
    families = {c["config"].signal_family for c in cat}
    assert "donchian_breakout" in families
    assert "htf_pullback_short" in families
    assert "ema_cross_short" in families
    ids = {c["config"].strategy_id for c in cat}
    assert len(ids) == len(cat)


def test_short_signal_family_registered():
    cfg = MajorsSleeveConfig(signal_family="donchian_short", strategy_id="t", track="t")
    # early index → None
    assert _signal_direction([], 0, cfg) is None


def test_batch_runs_shared_market():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    report = run_majors_research_batch(data, max_bars=2500, start_equity=10.0)
    assert report["formal_status"] == "ok"
    assert report["places_exchange_orders"] is False
    assert report["candidate_count"] >= 8
    assert len(report["ranking"]) == report["candidate_count"]
    for row in report["results"]:
        assert row["starting_equity"] == 10.0
        assert "research_decision" in row

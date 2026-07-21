"""Tests for majors research batch v2 (low turnover)."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import _signal_direction
from prod.majors_contract import MajorsSleeveConfig
from prod.research_batch_majors_v2 import research_catalog_v2, run_majors_research_batch_v2


def test_v2_catalog_low_turnover_families():
    cat = research_catalog_v2()
    assert len(cat) >= 8
    families = {c["config"].signal_family for c in cat}
    assert "daily_breakout_long" in families
    assert "slow_ema_cross_long" in families
    assert "multi_day_momentum_short" in families
    assert len({c["config"].strategy_id for c in cat}) == len(cat)


def test_v2_signals_registered():
    cfg = MajorsSleeveConfig(
        signal_family="slow_ema_cross_long",
        strategy_id="t",
        track="t",
    )
    assert _signal_direction([], 0, cfg) is None


def test_v2_batch_runs():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    report = run_majors_research_batch_v2(data, max_bars=3000, start_equity=10.0)
    assert report["formal_status"] == "ok"
    assert report["theme"] == "low_turnover_sparse_event"
    assert report["candidate_count"] >= 8
    assert report["places_exchange_orders"] is False

"""Tests for majors research batch v3."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import DUAL_FAMILY_BASE, resolve_entry_signal
from prod.research_batch_majors_v3 import research_catalog_v3, run_majors_research_batch_v3


def test_v3_catalog_has_dual_families():
    cat = research_catalog_v3()
    assert len(cat) >= 8
    families = {c["config"].signal_family for c in cat}
    assert "dual_md_mom_short" in families
    assert "dual_md_mom_short" in DUAL_FAMILY_BASE
    assert "weekly_mom_short" in families


def test_v3_batch_runs():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    report = run_majors_research_batch_v3(data, max_bars=4000, start_equity=10.0)
    assert report["formal_status"] == "ok"
    assert report["theme"] == "dual_confirm_and_calendar_sparse"
    assert report["candidate_count"] >= 8
    assert report["places_exchange_orders"] is False

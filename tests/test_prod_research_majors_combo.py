"""Tests for majors combo research protocols."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.research_majors_combo import combo_legs_catalog, run_majors_combo_research


def test_combo_legs_include_primary():
    cat = combo_legs_catalog()
    assert "h1_high_vol_donchian_short" in cat
    assert cat["h1_high_vol_donchian_short"].role == "primary"


def test_combo_research_if_data():
    data = Path("data")
    if not (data / "BTC_1h.csv").exists() and not (data / "BTC_1H.csv").exists():
        pytest.skip("1h missing")
    report = run_majors_combo_research(data, start_equity=10.0)
    assert report["formal_status"] == "ok"
    assert report["places_exchange_orders"] is False
    assert report["baseline_primary"]["return_fraction"] is not None
    assert "operator_action" in report
    assert len(report["experiments"]) >= 5

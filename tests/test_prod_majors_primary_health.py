"""Tests for 15m primary health check helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.research_majors_primary_health import (
    run_h4_weekly_regime_diagnosis,
    run_majors_primary_health,
)


def test_primary_health_if_data():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists() or not (data / "ETH_15m.csv").exists():
        pytest.skip("15m missing")
    report = run_majors_primary_health(
        data,
        formation_fracs=(0.60,),
        embargo_bars=96,
        include_capital_ladder=False,
    )
    assert report["formal_status"] == "ok"
    assert report["places_exchange_orders"] is False
    assert len(report["sleeves"]) == 2
    assert "overall_primary_action" in report
    primary = next(s for s in report["sleeves"] if s["name"] == "primary_donchian_long")
    assert primary["health"]["alpha_quality"]
    assert primary["window_count"] == 1


def test_h4_weekly_regime_if_data():
    data = Path("data")
    if not (data / "BTC_4h.csv").exists() and not (data / "BTC_4H.csv").exists():
        pytest.skip("4h missing")
    report = run_h4_weekly_regime_diagnosis(data)
    assert report["formal_status"] == "ok"
    assert report["interpretation"]["admit"] is False
    assert report["places_exchange_orders"] is False

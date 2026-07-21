"""Tests for multi_day_momentum_short deep validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import replay_majors_account, load_majors_market
from prod.majors_contract import primary_majors_config
from prod.research_batch_majors_v2 import research_catalog_v2
from prod.research_md_mom_short_validate import run_md_mom_short_validation


def test_single_symbol_replay_works():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    cfg = next(c["config"] for c in research_catalog_v2() if c["name"] == "multi_day_momentum_short")
    market = load_majors_market(data, primary_majors_config())
    r = replay_majors_account(
        data,
        config=cfg,
        market=market,
        symbol_subset=("BTC-USDT-SWAP",),
        max_bars=2000,
    )
    assert r["formal_status"] == "ok"
    assert r["symbols"] == ["BTC-USDT-SWAP"]


def test_timeline_first_last():
    data = Path("data")
    if not (data / "ETH_15m.csv").exists():
        pytest.skip("data missing")
    cfg = next(c["config"] for c in research_catalog_v2() if c["name"] == "multi_day_momentum_short")
    market = load_majors_market(data, primary_majors_config())
    a = replay_majors_account(
        data, config=cfg, market=market, max_bars=1500, timeline_side="first"
    )
    b = replay_majors_account(
        data, config=cfg, market=market, max_bars=1500, timeline_side="last"
    )
    assert a["formal_status"] == "ok" and b["formal_status"] == "ok"


def test_validation_runs():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    # Use shorter path via monkeypatch? full validation is slow but OK once
    report = run_md_mom_short_validation(data, start_equity=10.0)
    assert report["report_type"] == "md_mom_short_deep_validation_v1"
    assert "decision" in report
    assert report["places_exchange_orders"] is False
    assert report["live_allowed"] is False
    assert "formation" in report and "oos" in report
    assert "BTC-USDT-SWAP" in report["by_symbol"]

"""Tests for HTF pullback research candidate."""

from __future__ import annotations

from pathlib import Path

import pytest

from prod.majors_account_replay import _signal_htf_pullback, load_majors_market, replay_majors_account
from prod.majors_contract import HTF_PULLBACK_STRATEGY_ID, htf_pullback_majors_config
from prod.research_htf_pullback import run_htf_pullback_research


def test_htf_config_frozen_universe_and_family():
    cfg = htf_pullback_majors_config()
    assert cfg.strategy_id == HTF_PULLBACK_STRATEGY_ID
    assert cfg.signal_family == "htf_pullback"
    assert set(cfg.symbols) == {"BTC-USDT-SWAP", "ETH-USDT-SWAP"}
    assert cfg.start_equity == 10.0


def test_signal_htf_pullback_false_on_early_index():
    cfg = htf_pullback_majors_config()
    assert _signal_htf_pullback([], 0, cfg) is None


def test_research_runs_on_real_data():
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        pytest.skip("data missing")
    report = run_htf_pullback_research(
        data,
        max_bars=4000,
        include_baseline_compare=True,
        include_sensitivity=True,
    )
    assert report["formal_status"] == "ok"
    assert report["places_exchange_orders"] is False
    assert report["live_allowed"] is False
    assert report["not_default_paper_runtime"] is True
    assert report["candidate_10u"]["starting_equity"] == 10.0
    assert report["candidate_10u"]["trades"] is not None
    assert report["baseline_donchian_10u"] is not None
    assert "research_decision" in report


def test_replay_uses_htf_family():
    data = Path("data")
    if not (data / "ETH_15m.csv").exists():
        pytest.skip("data missing")
    cfg = htf_pullback_majors_config()
    market = load_majors_market(data, cfg)
    out = replay_majors_account(data, config=cfg, max_bars=2000, market=market)
    assert out["strategy_id"] == HTF_PULLBACK_STRATEGY_ID
    assert out["formal_status"] == "ok"

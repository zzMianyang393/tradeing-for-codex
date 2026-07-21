"""Tests for majors 15m refresh wrapper + readiness pointer on ops dashboard."""

from __future__ import annotations

import json
from pathlib import Path

from prod.majors_refresh import majors_symbols, run_majors_15m_refresh
from prod.ops_summary import (
    build_prod_ops_dashboard,
    build_sleeve_ops_summary,
    compact_readiness_pointer,
    load_readiness_package_file,
)
from prod.policy import PRODUCTION_BOUND_SYMBOLS


def test_majors_symbols_are_production_bound_only():
    syms = majors_symbols()
    assert set(syms) == set(PRODUCTION_BOUND_SYMBOLS)
    assert "RAVE-USDT-SWAP" not in syms


def test_majors_refresh_dry_run_with_fake_fetch(tmp_path: Path):
    # minimal valid 15m CSVs
    header = "timestamp,open,high,low,close,volume\n"
    # last bar
    last = "2026-07-16 03:30:00,1,1,1,1,1\n"
    for name in ("BTC_15m.csv", "ETH_15m.csv"):
        (tmp_path / name).write_text(header + last, encoding="utf-8")

    def fake_fetch(symbol: str, bar: str, limit: int = 100, after=None):
        # no new completed bars
        return []

    report = run_majors_15m_refresh(
        tmp_path, commit=False, fetch=fake_fetch
    )
    assert report["places_exchange_orders"] is False
    assert report["live_allowed"] is False
    assert report["formal_status"] in {"ok", "dry_run_pending_commit", "fail"}
    # empty remote -> append 0 -> ok
    if report["formal_status"] != "fail":
        assert report["total_append_count"] == 0
        assert report["committed"] is False


def test_majors_refresh_paginates_to_fill_gap(tmp_path: Path):
    """Synthetic: local ends at T; remote pages need pagination to reach T+15m."""
    from datetime import datetime, timezone

    header = "timestamp,open,high,low,close,volume\n"
    local_last = "2026-07-16 03:30:00"
    for name in ("BTC_15m.csv", "ETH_15m.csv"):
        (tmp_path / name).write_text(header + f"{local_last},1,1,1,1,1\n", encoding="utf-8")

    base_ts = int(
        datetime.strptime(local_last, "%Y-%m-%d %H:%M:%S")
        .replace(tzinfo=timezone.utc)
        .timestamp()
        * 1000
    )
    bar = 900_000
    # page0: newest far ahead; page1: connects to local
    page0 = [
        [str(base_ts + bar * 5), "1", "1", "1", "1", "0", "1", "1", "1"],
        [str(base_ts + bar * 4), "1", "1", "1", "1", "0", "1", "1", "1"],
    ]
    page1 = [
        [str(base_ts + bar * 3), "1", "1", "1", "1", "0", "1", "1", "1"],
        [str(base_ts + bar * 2), "1", "1", "1", "1", "0", "1", "1", "1"],
        [str(base_ts + bar * 1), "1", "1", "1", "1", "0", "1", "1", "1"],
        [str(base_ts), "1", "1", "1", "1", "0", "1", "1", "1"],
    ]
    calls = {"n": 0}

    def fake_fetch(symbol: str, bar_name: str, limit: int = 100, after=None):
        calls["n"] += 1
        if after is None:
            return list(page0)
        return list(page1)

    report = run_majors_15m_refresh(tmp_path, commit=False, fetch=fake_fetch)
    assert report["formal_status"] == "dry_run_pending_commit"
    assert report["total_append_count"] == 5 * 2  # 5 new bars x 2 symbols
    assert report["committed"] is False
    assert calls["n"] >= 2


def test_compact_readiness_pointer_and_dashboard(tmp_path: Path):
    package = {
        "report_type": "majors_local_readiness_package",
        "as_of": "2026-07-17T00:00:00Z",
        "formal_status": "ready_for_local_ops",
        "places_exchange_orders": False,
        "live_allowed": False,
        "ready_for_demo": False,
        "ready_for_live": False,
        "primary": {
            "config": {"config_fingerprint": "fp1"},
            "replay_10u": {
                "ending_equity": 8.2,
                "trades": 46,
                "config_fingerprint": "fp1",
            },
        },
        "conservative_compare": {
            "replay_10u": {"ending_equity": 9.4, "trades": 35},
        },
        "local_graduation": {"decision": "not_yet"},
        "admission_notes": ["local_paper_only_no_exchange_orders", "n2", "n3"],
    }
    path = tmp_path / "pkg.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    loaded = load_readiness_package_file(path)
    pointer = compact_readiness_pointer(loaded)
    assert pointer is not None
    assert pointer["formal_status"] == "ready_for_local_ops"
    assert pointer["ready_for_demo"] is False
    assert pointer["primary_10u_trades"] == 46

    majors = build_sleeve_ops_summary(
        strategy_id="prod_majors_donchian_atr_long_v1",
        track_label="majors",
        state={
            "equity": 10,
            "peak_equity": 10,
            "halt_reason": None,
            "completed_cycle_count": 2,
            "closed_trades": [],
            "live_allowed": False,
            "places_exchange_orders": False,
            "track_class": "production_bound",
            "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        },
        cycle_report=None,
        registry_entry={"status": "paper_prep"},
    )
    ten_u = build_sleeve_ops_summary(
        strategy_id="ten_u",
        track_label="ten_u",
        state=None,
        cycle_report=None,
        registry_entry=None,
    )
    dash = build_prod_ops_dashboard(
        majors_summary=majors,
        ten_u_summary=ten_u,
        majors_readiness_pointer=pointer,
        majors_refresh_status={"formal_status": "ok", "total_append_count": 0},
    )
    assert dash["majors_readiness_pointer"]["primary_fingerprint"] == "fp1"
    assert dash["default_pipeline_places_exchange_orders"] is False

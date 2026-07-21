"""Tests for server handoff contract and majors-first bootstrap."""

from __future__ import annotations

import json
from pathlib import Path

from prod.bootstrap_server import (
    ensure_majors_15m_data,
    run_bootstrap,
    seed_majors_registry,
)
from prod.majors_contract import STRATEGY_ID as MAJORS_ID
from prod.registry import get_entry
from prod.server_handoff import build_server_handoff_contract, write_server_handoff_contract


def test_handoff_contract_server_only_no_secrets():
    c = build_server_handoff_contract()
    assert c["report_type"] == "server_agent_handoff_contract"
    assert c["invariants"]["api_keys_on_research_workstation"] is False
    assert c["invariants"]["demo_live_execution_environment"] == "server_only"
    assert c["invariants"]["places_exchange_orders_default"] is False
    assert "OKX_API_KEY" in c["execution_split"]["server_only_secrets"]
    assert MAJORS_ID == c["production_bound"]["strategy_id"]
    assert "BTC-USDT-SWAP" in c["production_bound"]["symbols"]
    assert any("majors-hourly" in x for x in c["commands"]["daily_or_hourly_paper"])
    # no secret values present
    blob = json.dumps(c)
    assert "sk-" not in blob
    assert "BEGIN" not in blob


def test_write_handoff(tmp_path: Path):
    path = tmp_path / "handoff.json"
    report = write_server_handoff_contract(path)
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["version"] == report["version"]


def test_seed_majors_registry(tmp_path: Path):
    reg = tmp_path / "registry.json"
    r1 = seed_majors_registry(reg)
    assert r1["action"] == "seeded"
    entry = get_entry(MAJORS_ID, reg)
    assert entry is not None
    assert entry["status"] == "paper_prep"
    assert entry["live_allowed"] is False
    r2 = seed_majors_registry(reg)
    assert r2["action"] == "keep_existing"


def test_bootstrap_majors_skip_download_with_existing_data(tmp_path: Path):
    data = Path("data")
    if not (data / "BTC_15m.csv").exists():
        import pytest

        pytest.skip("BTC 15m missing")
    reg = tmp_path / "reg.json"
    report = run_bootstrap(
        mode="majors",
        majors_data_dir=data,
        registry_path=reg,
        skip_download=True,
        seed_registry=True,
        write_handoff=False,
    )
    assert report["mode"] == "majors"
    assert report["primary_sleeve"] == "majors_production_bound"
    assert report["api_keys_written"] is False
    assert report["places_exchange_orders"] is False
    assert report["sleeves"]["majors"]["formal_status"] in {"ok", "partial"}
    assert get_entry(MAJORS_ID, reg)["status"] == "paper_prep"


def test_ensure_majors_reports_exists(tmp_path: Path):
    data = Path("data")
    if not (data / "ETH_15m.csv").exists():
        import pytest

        pytest.skip("data missing")
    out = ensure_majors_15m_data(data, skip_download=True)
    assert out["formal_status"] == "ok"
    assert out["symbols"]["BTC-USDT-SWAP"]["action"] == "exists"

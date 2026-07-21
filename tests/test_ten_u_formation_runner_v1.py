from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from market import FeatureBar
from ten_u_formation_runner_v1 import FormationGate, _is_raw_breakout, _weekly_monday_utc


def _bars(count: int, start_ts: int, *, breakout: bool = False) -> list[FeatureBar]:
    out = []
    for i in range(count):
        close, high = (103.0, 104.0) if breakout and i == count - 2 else (100.0, 101.0)
        out.append(FeatureBar(
            ts=start_ts + i * 900_000, time="2024-01-01 00:00:00",
            open=100.0, high=high, low=99.0, close=close, volume_quote=1000.0,
        ))
    return out


def test_gate_fingerprint_is_complete_and_deterministic():
    assert len(FormationGate().fingerprint()) == 64
    assert FormationGate().fingerprint() == FormationGate().fingerprint()


def test_weekly_resample_requires_complete_monday_utc_week():
    monday = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    assert _weekly_monday_utc(_bars(671, monday)) == []
    weekly = _weekly_monday_utc(_bars(672, monday))
    assert len(weekly) == 1
    assert weekly[0].ts == monday


def test_raw_breakout_uses_previous_completed_bar_only():
    monday = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    bars = _bars(48, monday, breakout=True)
    assert _is_raw_breakout(bars, 47)
    bars[-1].close = 999.0
    assert _is_raw_breakout(bars, 47)


def test_checked_in_report_is_formation_only_and_failed():
    path = Path(__file__).resolve().parents[1] / "reports" / "ten_u_warlord_formation_v1.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["phase"] == "formation"
    assert report["coverage"]["coverage_status"] == "PASS"
    assert report["validation_metrics_accessed"] is False
    assert report["oos_metrics_accessed"] is False
    assert report["formal_status"] == "formation_fail"
    assert report["gate_pass"] is False
    assert report["trades"] >= 30


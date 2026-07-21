from __future__ import annotations

import json

import pytest

from merge_daily_atr_expansion_breakout_audit import merge


def write_batch(path, parameters, events):
    path.write_text(json.dumps({"rule_id": "daily_atr_expansion_breakout_v1", "parameters": parameters, "events": events}), encoding="utf-8")


def event(split, value, ts):
    return {"split": split, "net_return_pct": value, "signal_ts": ts, "symbol": "BTC-USDT-SWAP", "direction": "long"}


def test_merge_recomputes_full_summary(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    write_batch(first, {"channel_days": 20}, [event("formation", 1.0, 1)])
    write_batch(second, {"channel_days": 20}, [event("oos", 1.0, 2)])
    report = merge([first, second])
    assert report["formation"]["events"] == 1
    assert report["oos"]["events"] == 1
    assert report["safety_gates"]["eligible_for_paper"] is False


def test_merge_rejects_mismatched_parameters(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    write_batch(first, {"channel_days": 20}, [])
    write_batch(second, {"channel_days": 21}, [])
    with pytest.raises(ValueError, match="mismatch"):
        merge([first, second])

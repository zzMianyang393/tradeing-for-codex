from __future__ import annotations

import json

import pytest

from merge_daily_williams_r_range_reversion_audit import merge


def write_batch(path, rule_id="daily_williams_r_range_reversion_v1", parameters=None, events=None):
    path.write_text(json.dumps({"rule_id": rule_id, "parameters": parameters or {"lookback": 14}, "events": events or []}), encoding="utf-8")


def event(split, value, ts):
    return {"split": split, "net_return_pct": value, "signal_ts": ts, "symbol": "BTC-USDT-SWAP", "direction": "long"}


def test_merge_recomputes_full_universe_summary(tmp_path):
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    write_batch(first, events=[event("formation", 1.0, 1), event("oos", 1.0, 3)])
    write_batch(second, events=[event("formation", 1.0, 2), event("oos", -1.0, 4)])
    report = merge([first, second])
    assert report["formation"]["events"] == 2
    assert report["oos"]["events"] == 2
    assert report["events"][0]["signal_ts"] == 1
    assert report["safety_gates"]["safe_to_enable_trading"] is False


def test_merge_rejects_parameter_mismatch(tmp_path):
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    write_batch(first, parameters={"lookback": 14})
    write_batch(second, parameters={"lookback": 20})
    with pytest.raises(ValueError, match="mismatch"):
        merge([first, second])

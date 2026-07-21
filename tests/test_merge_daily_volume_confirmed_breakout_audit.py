import json
import pytest
from merge_daily_volume_confirmed_breakout_audit import merge


def write(path, parameters, events): path.write_text(json.dumps({"rule_id": "daily_volume_confirmed_breakout_v1", "parameters": parameters, "events": events}), encoding="utf-8")
def event(split, value, ts): return {"split": split, "net_return_pct": value, "signal_ts": ts, "symbol": "BTC-USDT-SWAP", "direction": "long"}


def test_merge_recomputes_total(tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"; write(first, {"channel_days": 20}, [event("formation", 1, 1)]); write(second, {"channel_days": 20}, [event("oos", 1, 2)])
    report = merge([first, second]); assert report["formation"]["events"] == 1 and report["oos"]["events"] == 1 and report["safety_gates"]["safe_to_enable_trading"] is False


def test_merge_rejects_different_parameters(tmp_path):
    first, second = tmp_path / "a.json", tmp_path / "b.json"; write(first, {"channel_days": 20}, []); write(second, {"channel_days": 10}, [])
    with pytest.raises(ValueError, match="mismatch"): merge([first, second])

from __future__ import annotations

from volatility_expansion_stability_audit import leave_one_symbol_out, positive_contribution, split_audit


def event(symbol, direction, value, ts):
    return {"symbol": symbol, "direction": direction, "net_return_pct": value, "signal_ts": ts}


def test_positive_contribution_uses_only_positive_groups():
    result = positive_contribution({"BTC": {"net_sum_pct": 3.0}, "ETH": {"net_sum_pct": -1.0}, "SOL": {"net_sum_pct": 1.0}})
    assert result["leader"] == "BTC"
    assert result["leader_positive_contribution"] == 0.75


def test_leave_one_symbol_out_recomputes_remaining_sample():
    rows = [event("BTC", "long", 2.0, 0), event("ETH", "short", -1.0, 86_400_000)]
    result = leave_one_symbol_out(rows)
    assert result["BTC"]["remaining_mean_pct"] == -1.0
    assert result["ETH"]["remaining_mean_pct"] == 2.0


def test_split_audit_is_descriptive_and_does_not_mutate_events():
    rows = [event("BTC", "long", 1.0, 0), event("ETH", "short", -1.0, 86_400_000)]
    audit = split_audit(rows)
    assert audit["events"] == 2
    assert rows[0]["symbol"] == "BTC"

from prospective_cohort_b_checkpoint import build_checkpoint
from prospective_cohort_b_checkpoint_append import append_checkpoint


def test_empty_checkpoint_accepts_a_later_observation_as_append() -> None:
    base = build_checkpoint({"signal_count": 0, "signals": [], "common_data_cutoff": "2026-07-14 07:45:00"})["checkpoint"]
    ledger = {"signal_count": 1, "common_data_cutoff": "2026-07-15 00:00:00", "signals": [{
        "cohort_id": "prospective_cohort_b_2026-07-14", "candidate_id": "daily_rsi_downtrend_rebound_v1", "rule_version": "frozen_2026-07-14",
        "signal_ts": 1784073600000, "signal_timestamp_utc": "2026-07-15 00:00:00", "symbol": "BTC-USDT-SWAP", "direction": "long", "regime": "趋势下行", "trigger_metrics": {"rsi14": 20}, "observation_only": True,
    }]}
    result = append_checkpoint(ledger, base)
    assert result["new_count"] == 1
    assert result["checkpoint"]["genesis_count"] == 0

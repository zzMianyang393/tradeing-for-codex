from prospective_cohort_b_admission import COHORT_ID
from prospective_cohort_b_checkpoint import build_checkpoint


def test_empty_active_cohort_initializes_without_paper_permission() -> None:
    result = build_checkpoint({"signal_count": 0, "signals": [], "common_data_cutoff": "2026-07-14 07:45:00"})
    checkpoint = result["checkpoint"]
    assert checkpoint["cohort_id"] == COHORT_ID
    assert checkpoint["genesis_count"] == 0
    assert checkpoint["current_count"] == 0
    assert checkpoint["safety_gates"]["approved_for_paper"] == []


def test_checkpoint_rejects_signal_before_cohort_start() -> None:
    ledger = {"signal_count": 1, "common_data_cutoff": "2026-07-14 07:45:00", "signals": [{
        "candidate_id": "daily_rsi_downtrend_rebound_v1", "rule_version": "frozen_2026-07-14", "signal_ts": 1,
        "signal_timestamp_utc": "1970-01-01 00:00:00", "symbol": "BTC-USDT-SWAP", "direction": "long",
        "regime": "趋势下行", "trigger_metrics": {"rsi14": 20}, "observation_only": True, "cohort_id": COHORT_ID,
    }]}
    try:
        build_checkpoint(ledger)
    except ValueError:
        pass
    else:
        raise AssertionError("backfill must be rejected")

from prospective_cohort_b_admission import COHORT_ID
from prospective_cohort_b_shadow_ledger import ALLOWED_SIGNAL_FIELDS, RULE_ID, validate


def test_cohort_b_schema_rejects_outcome_fields() -> None:
    signal = {"cohort_id": COHORT_ID, "candidate_id": RULE_ID, "rule_version": "frozen_2026-07-14", "signal_ts": 1,
              "signal_timestamp_utc": "1970-01-01 00:00:00", "symbol": "BTC-USDT-SWAP", "direction": "long",
              "regime": "趋势下行", "trigger_metrics": {"rsi14": 20.0}, "observation_only": True}
    assert set(signal) == ALLOWED_SIGNAL_FIELDS
    try:
        validate([signal | {"pnl": 1.0}], 0)
    except ValueError:
        pass
    else:
        raise AssertionError("outcome field must be rejected")


def test_cohort_b_schema_rejects_backfill() -> None:
    signal = {"cohort_id": COHORT_ID, "candidate_id": RULE_ID, "rule_version": "frozen_2026-07-14", "signal_ts": 9,
              "signal_timestamp_utc": "1970-01-01 00:00:00", "symbol": "BTC-USDT-SWAP", "direction": "long",
              "regime": "趋势下行", "trigger_metrics": {"rsi14": 20.0}, "observation_only": True}
    try:
        validate([signal], 10)
    except ValueError:
        pass
    else:
        raise AssertionError("pre-start signal must be rejected")

from prospective_cohort_b_volatility_expansion_ledger import RULE_ID, validate


def test_validate_rejects_signal_before_activation_boundary():
    signal = {"cohort_id": "b", "candidate_id": RULE_ID, "rule_version": "x", "signal_ts": 9,
              "signal_timestamp_utc": "x", "symbol": "BTC-USDT-SWAP", "direction": "long", "regime": "x",
              "trigger_metrics": {}, "observation_only": True}
    try:
        validate([signal], 10)
    except ValueError as error:
        assert "activation" in str(error)
    else:
        raise AssertionError("pre-activation signal unexpectedly accepted")


def test_validate_rejects_outcome_field():
    signal = {"cohort_id": "b", "candidate_id": RULE_ID, "rule_version": "x", "signal_ts": 10,
              "signal_timestamp_utc": "x", "symbol": "BTC-USDT-SWAP", "direction": "long", "regime": "x",
              "trigger_metrics": {}, "observation_only": True, "pnl": 1}
    try:
        validate([signal], 10)
    except ValueError as error:
        assert "schema" in str(error)
    else:
        raise AssertionError("outcome field unexpectedly accepted")

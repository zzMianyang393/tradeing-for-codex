from cohort_b_signal_staging_assembler import build


def _signal(candidate="rsi", ts=1):
    return {"cohort_id": "b", "candidate_id": candidate, "rule_version": "v", "signal_ts": ts,
            "signal_timestamp_utc": "x", "symbol": "BTC-USDT-SWAP", "direction": "long", "regime": "x",
            "trigger_metrics": {}, "observation_only": True}


def _source(signals):
    return {"cohort_id": "b", "common_data_cutoff": "2026-07-15 00:00:00", "coverage_status": "active", "signals": signals}


def test_assembler_combines_distinct_signal_identities():
    report = build([("a", _source([_signal("rsi", 1)])), ("b", _source([_signal("vol", 2)]))])
    assert report["signal_count"] == 2
    assert report["outcomes_evaluated"] is False


def test_assembler_rejects_duplicate_identity_across_sources():
    try:
        build([("a", _source([_signal()])), ("b", _source([_signal()]))])
    except ValueError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate identity unexpectedly accepted")

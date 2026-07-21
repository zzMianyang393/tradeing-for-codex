from cohort_b_candidate_activation_registry import DAY_MS, build, next_daily_open_after


def test_activation_is_strictly_after_existing_checkpoint_maximum():
    checkpoint = {"cohort_id": "b", "max_signal_ts": 2 * DAY_MS}
    audit = {"status": "historical_research_candidate"}
    record = build(checkpoint, audit)["activation_records"][0]
    assert record["not_before_signal_ts"] == 3 * DAY_MS
    assert record["not_before_signal_ts"] > record["existing_checkpoint_max_signal_ts"]
    assert record["activation_status"] == "signal_only_generator_enabled"
    assert "paper or trading eligibility" in record["remaining_requirements"][-1]


def test_unqualified_candidate_cannot_receive_activation_boundary():
    checkpoint = {"cohort_id": "b", "max_signal_ts": 0}
    try:
        build(checkpoint, {"status": "insufficient_evidence"})
    except ValueError as error:
        assert "qualified" in str(error)
    else:
        raise AssertionError("unqualified candidate unexpectedly received activation")

from cohort_b_activation_readiness_audit import build


def _activation(ts=100):
    return {"activation_records": [{"candidate_id": "x", "not_before_signal_ts": ts, "not_before_signal_utc": "1970-01-01 00:00:00"}]}


def _data(value):
    return {"common_cutoff_utc": value}


def _overlap():
    return {"conclusion": "overlap_penalty_required_before_any_combo_research"}


def _generator():
    return {"generator_available": True}


def test_pre_activation_cutoff_cannot_generate_observation():
    result = build(_activation(100), _data("1970-01-01 00:00:00"), _overlap(), {"current_count": 1}, _generator())
    assert result["readiness_status"] == "awaiting_common_data_cutoff"
    assert result["eligible_to_generate_observation"] is False


def test_ready_data_still_does_not_enable_generator_or_trading():
    result = build(_activation(0), _data("1970-01-01 00:00:00"), _overlap(), {"current_count": 1}, _generator())
    assert result["readiness_status"] == "ready_for_signal_only_generation"
    assert result["eligible_to_generate_observation"] is True
    assert result["safety_gates"]["safe_to_enable_trading"] is False

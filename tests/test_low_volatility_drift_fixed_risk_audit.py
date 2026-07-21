from low_volatility_drift_fixed_risk_audit import candidate_events_from_result


def test_candidate_events_reconstructs_accepted_and_rejected_inputs():
    result = {
        "closed_positions": [{"id": "accepted"}],
        "rejected_events": [{"id": "capacity"}, {"id": "duplicate"}],
    }
    assert candidate_events_from_result(result) == [
        {"id": "accepted"},
        {"id": "capacity"},
        {"id": "duplicate"},
    ]


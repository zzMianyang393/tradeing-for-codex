from prospective_sealed_evaluation_preflight import build


def _maturity(status):
    return {"as_of_ts": 0, "as_of_utc": "x", "source_cutoff": "x", "observations": [
        {"observation_id": "a", "candidate_id": "c", "symbol": "BTC-USDT-SWAP", "signal_ts": 1, "maturity_ts": 2, "status": status}
    ]}


def test_unmatured_observation_cannot_enter_queue_or_result_evaluation():
    result = build(_maturity("awaiting_maturity"), {"integrity_status": "valid"})
    assert result["readiness_status"] == "awaiting_maturity"
    assert result["queued_observation_count"] == 0
    assert result["result_evaluation_performed"] is False


def test_mature_observation_requires_valid_integrity_before_queueing():
    result = build(_maturity("mature_awaiting_sealed_evaluation"), {"integrity_status": "invalid"})
    assert result["readiness_status"] == "blocked_integrity"
    assert result["queued_observation_count"] == 0


def test_mature_valid_observation_queues_metadata_only():
    result = build(_maturity("mature_awaiting_sealed_evaluation"), {"integrity_status": "valid"})
    assert result["readiness_status"] == "sealed_evaluation_queue_ready"
    assert result["queued_observation_count"] == 1
    assert {"return", "pnl", "price", "entry", "exit"}.isdisjoint(result["queue"][0])

from prospective_cohort_c_refresh_pipeline import HORIZON_DAYS, DAY_MS, identity, maturity
from prospective_cohort_c_sealed_preflight import build


def signal(ts=1000):
    return {"hypothesis_id": "h", "rule_version": "v", "signal_ts": ts, "symbol": "BTC-USDT-SWAP", "direction": "short", "regime": "高波动转换"}


def artifacts(as_of_ts=1000 + HORIZON_DAYS * DAY_MS):
    source_signal = signal()
    observation = {"observation_id": identity(source_signal), "hypothesis_id": "h", "rule_version": "v", "signal_ts": 1000, "symbol": "BTC-USDT-SWAP", "direction": "short", "regime": "高波动转换", "maturity_ts": 1000 + HORIZON_DAYS * DAY_MS, "maturity_timestamp_utc": "x"}
    ledger = {"signal_count": 1, "signals": [source_signal], "common_data_cutoff": "2026-01-01 00:00:00"}
    registry = {"registry_signal_count": 1, "observations": [observation]}
    maturity_report = {"as_of_ts": as_of_ts, "as_of_utc": "2026-01-01 00:00:00", "observations": [{"observation_id": "id", "hypothesis_id": "h", "symbol": "BTC-USDT-SWAP", "signal_ts": 1000, "maturity_ts": observation["maturity_ts"], "status": "mature_awaiting_sealed_evaluation"}]}
    return ledger, registry, maturity_report


def test_missing_formal_artifacts_cannot_queue_or_evaluate():
    report = build(None, None, None)
    assert report["readiness_status"] == "awaiting_first_published_observation"
    assert report["queued_observation_count"] == 0
    assert report["result_evaluation_performed"] is False


def test_valid_mature_artifact_queues_metadata_only():
    ledger, registry, maturity_report = artifacts()
    report = build(ledger, registry, maturity_report)
    assert report["readiness_status"] == "sealed_evaluation_queue_ready"
    assert report["queued_observation_count"] == 1
    assert {"return", "pnl", "price", "entry", "exit"}.isdisjoint(report["queue"][0])


def test_identity_mismatch_blocks_the_queue():
    ledger, registry, maturity_report = artifacts()
    registry["observations"][0]["observation_id"] = "wrong"
    report = build(ledger, registry, maturity_report)
    assert report["readiness_status"] == "blocked_integrity"
    assert report["queued_observation_count"] == 0


def test_cohort_c_maturity_has_per_observation_status_without_outcomes():
    registry = {"common_data_cutoff": "1970-04-02 00:00:00", "observations": [{"observation_id": "x", "hypothesis_id": "h", "symbol": "BTC-USDT-SWAP", "signal_ts": 1000, "maturity_ts": 1000 + HORIZON_DAYS * DAY_MS, "maturity_timestamp_utc": "x"}]}
    report = maturity(registry)
    assert report["observations"][0]["status"] == "mature_awaiting_sealed_evaluation"
    assert report["outcomes_evaluated"] is False


def test_preflight_source_cannot_import_runner_or_evaluate_results():
    source = open("prospective_cohort_c_sealed_preflight.py", encoding="utf-8").read()
    assert "from runner import" not in source
    assert "import runner" not in source
    assert "result_evaluation_performed\": False" in source

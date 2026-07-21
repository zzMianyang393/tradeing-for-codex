from datetime import datetime, timezone

from prospective_cohort_d_refresh_pipeline import DAY_MS, HORIZON_DAYS, build_registry, maturity
from prospective_cohort_d_sealed_preflight import build
from prospective_cohort_d_cross_sectional_weakness import ACTIVATION_TS


def signal():
    return {"cohort_id": "prospective_cohort_d_2026-07-16", "hypothesis_id": "weekly_cross_sectional_weakness_short_exploration_v1", "rule_version": "frozen_2026-07-16", "signal_ts": ACTIVATION_TS, "signal_timestamp_utc": "2026-07-20 00:00:00", "symbol": "BTC-USDT-SWAP", "direction": "short", "regime": "weekly_cross_sectional_rank", "trigger_metrics": {}, "observation_only": True}


def ledger(rows, cutoff="2026-07-20 00:00:00"):
    return {"cohort_id": signal()["cohort_id"], "hypothesis_id": signal()["hypothesis_id"], "signal_count": len(rows), "common_data_cutoff": cutoff, "signals": rows, "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}


def test_missing_formal_artifacts_cannot_create_a_queue():
    report = build(None, None, None)
    assert report["readiness_status"] == "awaiting_first_published_observation"
    assert report["queued_observation_count"] == 0 and report["result_evaluation_performed"] is False


def test_mature_observation_is_only_queued_after_integrity_check():
    maturity_ts = ACTIVATION_TS + HORIZON_DAYS * DAY_MS
    cutoff = datetime.fromtimestamp(maturity_ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    data = ledger([signal()], cutoff); registry = build_registry(data); audited = maturity(registry)
    report = build(data, registry, audited)
    assert report["integrity"]["integrity_status"] == "valid"
    assert report["queued_observation_count"] == 1 and report["result_evaluation_performed"] is False

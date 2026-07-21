import json
from pathlib import Path

from ten_u_event_trend_health_v2 import check_health


def _latest_observer_time(root: Path) -> str:
    audit = json.loads(
        (root / "reports/ten_u_event_trend_prospective_refresh_audit_v2.json")
        .read_text(encoding="utf-8")
    )
    return audit["records"][-1]["recorded_at"]


def test_current_observer_health_passes_without_outcome_metrics():
    root = Path(__file__).parents[1]
    report = check_health(
        root / "data/event_trend_v1/hourly_dataset_manifest_v1.json",
        root / "reports/ten_u_event_trend_prospective_ledger_v2.json",
        root / "reports/ten_u_event_trend_prospective_refresh_audit_v2.json",
        root / "reports/ten_u_event_trend_evaluator_registration_v2.json",
        _latest_observer_time(root),
    )
    assert report["formal_status"] == "PASS"
    assert report["outcome_metrics_computed"] is False
    assert all(item["status"] == "PASS" for item in report["symbols"].values())


def test_health_detects_ledger_tampering_before_any_outcome_work(tmp_path):
    root = Path(__file__).parents[1]
    ledger = json.loads(
        (root / "reports/ten_u_event_trend_prospective_ledger_v2.json").read_text(
            encoding="utf-8"
        )
    )
    ledger["head_hash"] = "0" * 64
    broken = tmp_path / "ledger.json"
    broken.write_text(json.dumps(ledger), encoding="utf-8")
    report = check_health(
        root / "data/event_trend_v1/hourly_dataset_manifest_v1.json",
        broken,
        root / "reports/ten_u_event_trend_prospective_refresh_audit_v2.json",
        root / "reports/ten_u_event_trend_evaluator_registration_v2.json",
        "2026-07-16T13:00:00Z",
    )
    assert report["formal_status"] == "FAIL"
    assert any(reason.startswith("ledger_invalid:") for reason in report["reasons"])
    assert report["outcome_metrics_computed"] is False

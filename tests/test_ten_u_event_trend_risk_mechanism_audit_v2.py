import json
from pathlib import Path

import pytest

from ten_u_event_trend_risk_mechanism_audit_v2 import build_risk_mechanism_audit


ROOT = Path(__file__).resolve().parents[1]


def _screen():
    return json.loads((ROOT / "reports/ten_u_event_trend_screen_v2.json").read_text(encoding="utf-8"))


def test_audit_uses_only_isolated_historical_screen():
    report = build_risk_mechanism_audit(_screen())
    assert report["formal_status"] == "historical_diagnostic_only_no_parameter_change"
    assert report["prospective_metrics_accessed"] is False
    assert report["parameter_search_performed"] is False


def test_wrong_or_contaminated_source_is_rejected():
    screen = _screen()
    screen["prospective_metrics_accessed"] = True
    with pytest.raises(ValueError, match="outcome isolation"):
        build_risk_mechanism_audit(screen)


def test_hard_stop_both_swept_and_prevented_deeper_immediate_exposure():
    trade = build_risk_mechanism_audit(_screen())["hard_stops"][0]
    assert trade["symbol"] == "LAB-USDT-SWAP"
    assert trade["recovered_original_entry"] is True
    assert trade["recovered_plus_1r"] is False
    assert trade["recovery_entry_hours_after_stop"] == 14.0
    assert trade["hard_stop_price_move_fraction"] == pytest.approx(-0.18113, abs=1e-4)
    assert trade["maximum_adverse_price_move_fraction"] == pytest.approx(-0.34828, abs=1e-4)
    assert trade["additional_adverse_move_beyond_stop_fraction"] > 0.16


def test_winner_giveback_and_account_giveback_are_separate():
    report = build_risk_mechanism_audit(_screen())
    captures = [trade["winner_capture_fraction"] for trade in report["winners"]]
    assert captures == pytest.approx([0.7019138097, 0.9169752629])
    assert report["median_winner_capture_fraction"] == pytest.approx(0.8094445363)
    assert report["account_peak_to_end_giveback_fraction"] == pytest.approx(0.16536, abs=1e-4)


def test_report_explicitly_refuses_edge_claim():
    report = build_risk_mechanism_audit(_screen())
    assert report["diagnosis"]["evidence_strength"].startswith("insufficient_three_trades")


def test_stored_audit_is_reproducible():
    stored = json.loads(
        (ROOT / "reports/ten_u_event_trend_risk_mechanism_audit_v2.json")
        .read_text(encoding="utf-8")
    )
    assert stored == build_risk_mechanism_audit(_screen())

from merge_daily_supertrend_audit import summary, verdict


def _event(ts, result):
    return {"signal_ts": ts, "net_return_pct": result}


def test_summary_calculates_positive_month_concentration():
    stats = summary([_event(1704067200000, 2.0), _event(1704153600000, 1.0), _event(1706745600000, -1.0)])
    assert stats["events"] == 3
    assert stats["mean_pct"] == round(2 / 3, 6)
    assert stats["positive_return_month_concentration"] == 1.0


def test_verdict_reports_all_failed_gates_when_sample_is_sufficient():
    stats = {"events": 15, "mean_pct": -0.1, "positive_return_month_concentration": 0.3}
    status, reasons = verdict(stats, stats)
    assert status == "historical_rejected"
    assert len(reasons) == 4


def test_verdict_preserves_insufficient_evidence_precedence():
    stats = {"events": 14, "mean_pct": -0.1, "positive_return_month_concentration": 0.3}
    status, _ = verdict(stats, stats)
    assert status == "insufficient_evidence"

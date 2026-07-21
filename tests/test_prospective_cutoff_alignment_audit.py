from prospective_cutoff_alignment_audit import build


def test_matching_active_cohort_cutoffs_are_valid():
    report = build(
        {"common_cutoff_utc": "2026-07-16 01:45:00"},
        {"source_cutoffs": {"combined": "2026-07-16 01:45:00"}},
        {"common_data_cutoff": "2026-07-16 01:45:00"},
    )
    assert report["alignment_status"] == "valid"
    assert report["issues"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False


def test_missing_or_lagging_active_cutoff_is_invalid():
    report = build(
        {"common_cutoff_utc": "2026-07-16 01:45:00"},
        {"source_cutoffs": {"combined": "2026-07-16 01:30:00"}},
        {},
    )
    assert report["alignment_status"] == "invalid"
    assert len(report["issues"]) == 2

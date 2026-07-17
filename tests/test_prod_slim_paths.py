from prod.slim_paths import (
    decide_archive_target,
    is_preserved,
    plan_default_slim,
)


def test_preserve_event_trend_and_prod():
    assert is_preserved("data/event_trend_v1/RAVE_1h_full.csv")
    assert is_preserved("reports/prod/ten_u_paper_state.json")
    assert is_preserved("data/BTC_15m.csv")


def test_archive_candidate_pool():
    d = decide_archive_target("reports/candidate_pool")
    assert d.action == "archive"
    assert decide_archive_target("data/event_trend_v1").action == "preserve"


def test_plan_includes_preserve_when_present():
    plan = plan_default_slim(
        [
            "reports/candidate_pool",
            "data/basis",
            "data/event_trend_v1",
            "reports/prod",
        ]
    )
    actions = {p.relative_path: p.action for p in plan}
    assert actions["reports/candidate_pool"] == "archive"
    assert actions["data/event_trend_v1"] == "preserve"
    assert actions["reports/prod"] == "preserve"

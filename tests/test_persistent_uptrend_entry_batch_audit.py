from persistent_uptrend_entry_batch_audit import (
    classify_panel,
    expanding_panel_events,
    persistent_context,
    run_ages,
    screen_reasons,
)


def test_run_ages_reset_outside_uptrend():
    labels = [(1, "趋势上行"), (2, "趋势上行"), (3, "震荡"), (4, "趋势上行")]
    assert run_ages(labels) == [1, 2, 0, 1]


def test_persistent_context_requires_age_local_and_btc_labels():
    assert persistent_context("趋势上行", 61, "趋势上行") is True
    assert persistent_context("趋势上行", 60, "趋势上行") is False
    assert persistent_context("趋势上行", 61, "震荡") is False


def test_expanding_panel_events_obeys_fold_specific_universe():
    from regime_component_walk_forward_audit import parse_day

    events = [
        {"symbol": "BTC", "entry_ts": parse_day("2024-01-02")},
        {"symbol": "ETH", "entry_ts": parse_day("2024-01-02")},
    ]
    universe = {"eligible_symbols_by_fold": {"2024-H1": ["BTC"]}}
    assert expanding_panel_events(events, universe) == [events[0]]


def test_screen_reasons_accepts_complete_low_risk_panel():
    aggregate = {
        "accepted_positions": 30,
        "total_return_pct": 1.0,
        "max_drawdown_pct": 10.0,
        "top_positive_month_share": 0.20,
    }
    folds = {str(i): {"total_return_pct": 1.0 if i < 3 else -1.0} for i in range(5)}
    assert screen_reasons(aggregate, folds) == []


def test_classify_panel_retains_concentrated_core_pass_as_weak_feature():
    aggregate = {
        "accepted_positions": 90,
        "total_return_pct": 4.0,
        "max_drawdown_pct": 3.0,
        "top_positive_month_share": 0.40,
    }
    folds = {str(i): {"total_return_pct": 1.0 if i < 3 else -1.0} for i in range(5)}
    assert classify_panel(aggregate, folds) == "weak_feature_watchlist_concentration_penalty"

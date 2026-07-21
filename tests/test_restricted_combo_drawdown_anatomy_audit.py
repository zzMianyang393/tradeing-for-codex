from restricted_combo_drawdown_anatomy_audit import drawdown_episode, failure_classification


def test_drawdown_episode_finds_peak_trough_and_recovery():
    result = {
        "initial_equity": 100.0,
        "equity_curve": [
            {"ts": 0, "equity": 100.0},
            {"ts": 86_400_000, "equity": 120.0},
            {"ts": 2 * 86_400_000, "equity": 90.0},
            {"ts": 3 * 86_400_000, "equity": 121.0},
        ],
    }
    episode = drawdown_episode(result)
    assert episode["max_drawdown_pct"] == 25.0
    assert episode["peak_to_trough_days"] == 1
    assert episode["recovery_days"] == 1


def test_failure_classification_uses_frozen_twenty_percent_share():
    assert failure_classification({"a": -80.0, "b": -20.0})["classification"] == "common_failure"
    assert failure_classification({"a": -90.0, "b": -10.0})["classification"] == "minor_additive_loss"
    assert failure_classification({"a": -90.0, "b": 10.0})["classification"] == "offsetting_component"

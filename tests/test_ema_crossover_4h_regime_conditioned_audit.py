from __future__ import annotations

from ema_crossover_4h_regime_conditioned_audit import (
    annotate_events,
    compatible_with_direction,
    conditional_summary,
    summarize,
    verdict,
)


def test_compatible_with_direction_requires_matching_trend_direction():
    assert compatible_with_direction({"direction": "long"}, "趋势上行") is True
    assert compatible_with_direction({"direction": "long"}, "趋势下行") is False
    assert compatible_with_direction({"direction": "short"}, "趋势下行") is True


def test_annotate_events_adds_entry_regime_and_compatibility_flags():
    events = [{"symbol": "BTC-USDT-SWAP", "entry_ts": 100, "direction": "long"}]
    labels = {"BTC-USDT-SWAP": [(100, "趋势上行")]}

    result = annotate_events(events, labels)

    assert result[0]["entry_regime"] == "趋势上行"
    assert result[0]["trend_compatible_regime"] is True
    assert result[0]["direction_compatible_regime"] is True


def test_summarize_reports_net_sum_and_win_rate():
    result = summarize([1.0, -0.5, 2.0])

    assert result["observations"] == 3
    assert result["net_sum_pct"] == 2.5
    assert result["win_rate"] == 0.666667


def test_conditional_summary_splits_trend_and_non_trend():
    events = [
        {"split": "oos", "direction": "long", "net_return_pct": 1.0, "entry_regime": "趋势上行", "trend_compatible_regime": True, "direction_compatible_regime": True},
        {"split": "oos", "direction": "long", "net_return_pct": -2.0, "entry_regime": "震荡", "trend_compatible_regime": False, "direction_compatible_regime": False},
    ]

    result = conditional_summary(events)

    assert result["oos"]["trend_compatible_regime"]["all"]["observations"] == 1
    assert result["oos"]["non_trend_regime"]["all"]["net_sum_pct"] == -2.0


def test_verdict_rejects_negative_oos_trend_mean():
    summary = {
        "oos": {
            "trend_compatible_regime": {"all": {"observations": 30, "mean_pct": -0.1, "win_rate": 0.5}},
            "direction_compatible_regime": {"all": {"mean_pct": 0.1}},
        }
    }

    result = verdict(summary)

    assert result["status"] == "regime_conditioned_rejected"
    assert result["eligible_as_combo_directional_feature"] is False

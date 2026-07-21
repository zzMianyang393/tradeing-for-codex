from __future__ import annotations

from directional_regime_conditioned_audit import (
    annotate_events,
    build_report,
    conditional_summary,
    is_declared_compatible,
    summarize,
    verdict,
)


def test_declared_compatibility_for_donchian_trend_profile():
    assert is_declared_compatible({"direction": "long"}, "趋势上行", "donchian_trend") is True
    assert is_declared_compatible({"direction": "long"}, "趋势下行", "donchian_trend") is False
    assert is_declared_compatible({"direction": "short"}, "趋势下行", "donchian_trend") is True
    assert is_declared_compatible({"direction": "short"}, "震荡", "donchian_trend") is False


def test_declared_compatibility_for_daily_bb_range_profile():
    assert is_declared_compatible({"direction": "long"}, "震荡", "daily_bb_range") is True
    assert is_declared_compatible({"direction": "long"}, "趋势上行", "daily_bb_range") is False


def test_declared_compatibility_for_daily_rsi_downtrend_rebound_profile():
    assert is_declared_compatible({"direction": "long"}, "趋势下行", "daily_rsi_downtrend_rebound") is True
    assert is_declared_compatible({"direction": "long"}, "震荡", "daily_rsi_downtrend_rebound") is False
    assert is_declared_compatible({"direction": "long"}, "趋势上行", "daily_rsi_downtrend_rebound") is False


def test_annotate_events_adds_all_regime_flags():
    events = [{"symbol": "BTC-USDT-SWAP", "entry_ts": 100, "direction": "long"}]
    labels = {"BTC-USDT-SWAP": [(100, "趋势上行")]}

    result = annotate_events(events, labels, "donchian_trend")

    assert result[0]["entry_regime"] == "趋势上行"
    assert result[0]["trend_compatible_regime"] is True
    assert result[0]["range_compatible_regime"] is False
    assert result[0]["direction_compatible_regime"] is True
    assert result[0]["declared_compatible_regime"] is True


def test_conditional_summary_splits_declared_compatible_events():
    events = [
        {
            "split": "oos",
            "direction": "long",
            "net_return_pct": 1.0,
            "entry_regime": "震荡",
            "trend_compatible_regime": False,
            "range_compatible_regime": True,
            "declared_compatible_regime": True,
        },
        {
            "split": "oos",
            "direction": "long",
            "net_return_pct": -2.0,
            "entry_regime": "趋势下行",
            "trend_compatible_regime": True,
            "range_compatible_regime": False,
            "declared_compatible_regime": False,
        },
    ]

    result = conditional_summary(events)

    assert result["oos"]["declared_compatible_regime"]["all"]["net_sum_pct"] == 1.0
    assert result["oos"]["declared_incompatible_regime"]["all"]["net_sum_pct"] == -2.0


def test_summarize_reports_profit_factor_and_net_sum():
    result = summarize([2.0, -1.0, 1.0])

    assert result["observations"] == 3
    assert result["net_sum_pct"] == 2.0
    assert result["profit_factor"] == 3.0


def test_verdict_rejects_negative_oos_declared_mean():
    summary = {
        "formation": {"declared_compatible_regime": {"all": {"observations": 20, "mean_pct": 0.1}}},
        "oos": {"declared_compatible_regime": {"all": {"observations": 20, "mean_pct": -0.1, "win_rate": 0.5}}},
    }

    result = verdict(summary)

    assert result["status"] == "regime_conditioned_rejected"
    assert result["eligible_as_combo_directional_feature"] is False


def test_build_report_preserves_safety_gates(monkeypatch):
    monkeypatch.setattr(
        "directional_regime_conditioned_audit.build_regime_labels",
        lambda data_dir, events: {"BTC-USDT-SWAP": [(100, "震荡")]},
    )
    audit = {
        "research_id": "daily_bb_mean_revert",
        "events": [
            {
                "symbol": "BTC-USDT-SWAP",
                "split": "oos",
                "entry_ts": 100,
                "net_return_pct": 1.0,
            }
        ],
    }

    report = build_report(audit, data_dir=None, profile="daily_bb_range")

    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["events"][0]["declared_compatible_regime"] is True

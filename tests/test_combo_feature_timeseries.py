from __future__ import annotations

import json
from pathlib import Path

from combo_feature_timeseries import (
    build_report,
    concentration_by_feature,
    extract_feature_events,
    monthly_correlation,
    monthly_series,
    normalize_event,
    should_include_event,
)


def _preflight() -> dict:
    return {
        "groups": {
            "directional_feature_candidates": [
                {"source_research_id": "alpha"},
                {"source_research_id": "beta"},
            ],
            "context_label_candidates": [
                {"source_research_id": "context_only"},
            ],
        }
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_normalize_event_defaults_long_direction():
    event = normalize_event("alpha", {
        "symbol": "BTC-USDT-SWAP",
        "split": "formation",
        "signal_ts": 1,
        "signal_timestamp_utc": "2024-01-02 00:00:00",
        "net_return_pct": "1.25",
        "gross_return_pct": "1.41",
    })

    assert event["feature_id"] == "feat_alpha"
    assert event["direction"] == "long"
    assert event["direction_sign"] == 1
    assert event["month"] == "2024-01"


def test_ema_crossover_keeps_only_direction_compatible_events():
    assert should_include_event("4h_ema_crossover", {"direction_compatible_regime": True})
    assert not should_include_event("4h_ema_crossover", {"direction_compatible_regime": False})
    assert should_include_event("alpha", {"direction_compatible_regime": False})


def test_parabolic_sar_keeps_only_trend_regimes():
    assert should_include_event("daily_parabolic_sar_trend", {"entry_regime": "趋势上行"})
    assert should_include_event("daily_parabolic_sar_trend", {"entry_regime": "趋势下行"})
    assert not should_include_event("daily_parabolic_sar_trend", {"entry_regime": "震荡"})


def test_regime_conditioned_reports_keep_only_declared_compatible_events():
    assert should_include_event("donchian_atr_trend_baseline", {"declared_compatible_regime": True})
    assert not should_include_event("donchian_atr_trend_baseline", {"declared_compatible_regime": False})
    assert should_include_event("daily_bb_mean_revert", {"declared_compatible_regime": True})
    assert not should_include_event("daily_bb_mean_revert", {"declared_compatible_regime": False})
    assert should_include_event("daily_rsi_mean_revert", {"declared_compatible_regime": True})
    assert not should_include_event("daily_rsi_mean_revert", {"declared_compatible_regime": False})
    assert should_include_event("daily_trend_pullback", {"declared_compatible_regime": True})
    assert not should_include_event("daily_trend_pullback", {"declared_compatible_regime": False})


def test_extract_feature_events_uses_only_directional_candidates(tmp_path):
    alpha = _write_json(tmp_path / "alpha.json", {
        "events": [
            {"symbol": "BTC", "split": "formation", "signal_ts": 1, "signal_timestamp_utc": "2024-01-01 00:00:00", "net_return_pct": 1},
        ]
    })
    beta = _write_json(tmp_path / "beta.json", {
        "event_preview": [
            {"symbol": "ETH", "split": "oos", "signal_ts": 2, "signal_timestamp_utc": "2024-02-01 00:00:00", "direction": "short", "net_return_pct": -2},
        ]
    })

    events, diagnostics = extract_feature_events(_preflight(), {"alpha": alpha, "beta": beta})

    assert len(events) == 2
    assert {event["source_research_id"] for event in events} == {"alpha", "beta"}
    assert diagnostics["alpha"]["truncated"] is False
    assert diagnostics["beta"]["truncated"] is True


def test_monthly_series_sums_net_return_by_feature_and_month():
    events = [
        {"feature_id": "feat_alpha", "month": "2024-01", "net_return_pct": 1.0},
        {"feature_id": "feat_alpha", "month": "2024-01", "net_return_pct": 2.0},
        {"feature_id": "feat_beta", "month": "2024-02", "net_return_pct": -1.0},
    ]

    result = monthly_series(events)

    assert result["feat_alpha"]["2024-01"] == 3.0
    assert result["feat_beta"]["2024-02"] == -1.0


def test_monthly_correlation_uses_union_of_months():
    series = {
        "feat_alpha": {"2024-01": 1.0, "2024-02": 2.0, "2024-03": 3.0},
        "feat_beta": {"2024-01": 2.0, "2024-02": 4.0, "2024-03": 6.0},
    }

    result = monthly_correlation(series)

    assert result["months"] == ["2024-01", "2024-02", "2024-03"]
    assert result["matrix"]["feat_alpha"]["feat_beta"] == 1.0


def test_concentration_by_feature_reports_top_positive_month_share():
    events = [
        {"feature_id": "feat_alpha", "month": "2024-01", "split": "formation", "net_return_pct": 1.0},
        {"feature_id": "feat_alpha", "month": "2024-02", "split": "formation", "net_return_pct": 3.0},
        {"feature_id": "feat_alpha", "month": "2024-02", "split": "oos", "net_return_pct": -5.0},
    ]

    result = concentration_by_feature(events)

    assert result["feat_alpha"]["events"] == 3
    assert result["feat_alpha"]["top_month_positive_contribution_share"] == 0.75
    assert result["feat_alpha"]["split_counts"] == {"formation": 2, "oos": 1}


def test_build_report_preserves_safety_gates(tmp_path):
    alpha = _write_json(tmp_path / "alpha.json", {
        "events": [
            {"symbol": "BTC", "split": "formation", "signal_ts": 1, "signal_timestamp_utc": "2024-01-01 00:00:00", "net_return_pct": 1},
        ]
    })
    beta = _write_json(tmp_path / "beta.json", {
        "events": [
            {"symbol": "ETH", "split": "formation", "signal_ts": 2, "signal_timestamp_utc": "2024-02-01 00:00:00", "net_return_pct": 2},
        ]
    })

    report = build_report(_preflight(), {"alpha": alpha, "beta": beta})

    assert report["scope"] == "read_only_feature_diagnostics_not_combo_backtest"
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False

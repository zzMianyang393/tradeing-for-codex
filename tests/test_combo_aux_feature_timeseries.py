from __future__ import annotations

import json
from pathlib import Path

from combo_aux_feature_timeseries import (
    build_report,
    event_series_path,
    extract_aux_events,
    monthly_event_counts,
    monthly_value_sums,
    normalize_event,
    ready_features,
)


def _write_json(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _feature(feature_id: str, research_id: str, role: str, path: str) -> dict:
    return {
        "feature_id": feature_id,
        "source_research_id": research_id,
        "role": role,
        "extractability": "event_series_available",
        "evidence_paths": [{"path": path, "kind": "event_series_available"}],
    }


def test_event_series_path_uses_event_evidence(tmp_path):
    path = str(tmp_path / "report.json")
    feature = {"evidence_paths": [{"path": "note.md", "kind": "document_only"}, {"path": path, "kind": "event_series_available"}]}

    assert event_series_path(feature) == Path(path)


def test_ready_features_keeps_only_auxiliary_event_series():
    inventory = {
        "features": [
            {"role": "context_label", "extractability": "event_series_available"},
            {"role": "risk_filter_candidate", "extractability": "event_series_available"},
            {"role": "directional_weak_signal", "extractability": "event_series_available"},
            {"role": "context_label", "extractability": "aggregate_only"},
        ]
    }

    assert len(ready_features(inventory)) == 2


def test_normalize_context_event_preserves_diagnostic_return():
    feature = {"feature_id": "feat_ctx", "source_research_id": "ctx", "role": "context_label"}
    event = {
        "symbol": "BTC-USDT-SWAP",
        "split": "formation",
        "signal_ts": 1,
        "signal_timestamp_utc": "2024-01-01 00:00:00",
        "net_return_pct": -1.25,
    }

    result = normalize_event(feature, event)

    assert result["veto_flag"] == 0
    assert result["value"] == -1.25
    assert result["diagnostic_return_pct"] == -1.25
    assert result["allowed_as_directional"] is False


def test_normalize_risk_event_uses_veto_flag_not_return():
    feature = {"feature_id": "feat_risk", "source_research_id": "risk", "role": "risk_filter_candidate"}
    event = {
        "symbols": ["BTC-USDT-SWAP", "ETH-USDT-SWAP"],
        "event_ts": 2,
        "timestamp_utc": "2024-02-01 16:00:00",
        "qualified_fraction": 0.7,
    }

    result = normalize_event(feature, event)

    assert result["symbol"] == "MULTI"
    assert result["veto_flag"] == 1
    assert result["value"] == 1.0
    assert result["eligible_for_paper"] is False


def test_extract_aux_events_reads_ready_reports(tmp_path):
    context_path = _write_json(tmp_path / "context.json", {
        "events": [{"signal_ts": 1, "signal_timestamp_utc": "2024-01-01 00:00:00", "net_return_pct": 2.0}]
    })
    risk_path = _write_json(tmp_path / "risk.json", {
        "events": [{"event_ts": 2, "timestamp_utc": "2024-02-01 16:00:00", "symbols": ["BTC"]}]
    })
    inventory = {
        "features": [
            _feature("feat_ctx", "ctx", "context_label", context_path),
            _feature("feat_risk", "risk", "risk_filter_candidate", risk_path),
        ]
    }

    events, diagnostics = extract_aux_events(inventory)

    assert len(events) == 2
    assert diagnostics["ctx"]["events"] == 1
    assert diagnostics["risk"]["role"] == "risk_filter_candidate"


def test_monthly_tables_count_and_sum_values():
    events = [
        {"feature_id": "feat_a", "month": "2024-01", "value": 1.5},
        {"feature_id": "feat_a", "month": "2024-01", "value": 2.5},
        {"feature_id": "feat_b", "month": "2024-02", "value": 1.0},
    ]

    assert monthly_event_counts(events)["feat_a"]["2024-01"] == 2
    assert monthly_value_sums(events)["feat_a"]["2024-01"] == 4.0


def test_build_report_preserves_safety_gates(tmp_path):
    path = _write_json(tmp_path / "context.json", {
        "events": [{"signal_ts": 1, "signal_timestamp_utc": "2024-01-01 00:00:00", "net_return_pct": 2.0}]
    })
    inventory = {"features": [_feature("feat_ctx", "ctx", "context_label", path)]}

    report = build_report(inventory)

    assert report["event_count"] == 1
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    assert report["safety_gates"]["ready_for_combo_backtest"] is False

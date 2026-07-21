from __future__ import annotations

import json
from pathlib import Path

from combo_context_risk_feature_inventory import (
    build_inventory,
    classify_evidence_path,
    feature_lookup,
    inventory_item,
    recommended_next_step,
    strongest_extractability,
)


def _write_json(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_classify_evidence_path_detects_full_events(tmp_path):
    path = _write_json(tmp_path / "report.json", {"events": [{"x": 1}, {"x": 2}]})

    result = classify_evidence_path(path)

    assert result["kind"] == "event_series_available"
    assert result["event_count"] == 2


def test_classify_evidence_path_detects_preview_only(tmp_path):
    path = _write_json(tmp_path / "report.json", {"event_preview": [{"x": 1}]})

    result = classify_evidence_path(path)

    assert result["kind"] == "preview_only"
    assert result["preview_count"] == 1


def test_classify_evidence_path_detects_aggregate_json(tmp_path):
    path = _write_json(tmp_path / "report.json", {"summary": {"n": 3}})

    result = classify_evidence_path(path)

    assert result["kind"] == "aggregate_only"


def test_classify_evidence_path_detects_document_only(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("research note", encoding="utf-8")

    result = classify_evidence_path(str(path))

    assert result["kind"] == "document_only"


def test_strongest_extractability_prefers_events_over_preview():
    result = strongest_extractability([
        {"kind": "preview_only"},
        {"kind": "event_series_available"},
    ])

    assert result == "event_series_available"


def test_recommended_next_step_marks_risk_filters_as_veto_series():
    assert recommended_next_step("risk_filter_candidate", "event_series_available") == "extract_veto_series"
    assert recommended_next_step("context_label", "event_series_available") == "extract_context_event_series"


def test_feature_lookup_maps_by_source_research_id():
    pool = {"features": [{"source_research_id": "alpha", "evidence_paths": ["x.json"]}]}

    result = feature_lookup(pool)

    assert result["alpha"]["evidence_paths"] == ["x.json"]


def test_inventory_item_never_allows_directional_or_paper(tmp_path):
    path = _write_json(tmp_path / "report.json", {"events": [{"x": 1}]})
    item = {"feature_id": "feat_alpha", "source_research_id": "alpha", "tags": ["state"]}
    pool = {"alpha": {"evidence_paths": [path]}}

    result = inventory_item(item, "risk_filter_candidate", pool)

    assert result["extractability"] == "event_series_available"
    assert result["allowed_as_directional"] is False
    assert result["allowed_as_standalone_strategy"] is False
    assert result["eligible_for_paper"] is False
    assert result["veto_only"] is True


def test_build_inventory_uses_only_context_and_risk_groups(tmp_path):
    context_path = _write_json(tmp_path / "context.json", {"events": [{"x": 1}]})
    risk_path = _write_json(tmp_path / "risk.json", {"summary": {"n": 1}})
    preflight = {
        "groups": {
            "directional_feature_candidates": [{"feature_id": "feat_dir", "source_research_id": "dir"}],
            "context_label_candidates": [{"feature_id": "feat_ctx", "source_research_id": "ctx"}],
            "risk_filter_candidates": [{"feature_id": "feat_risk", "source_research_id": "risk"}],
        }
    }
    pool = {
        "features": [
            {"source_research_id": "ctx", "evidence_paths": [context_path]},
            {"source_research_id": "risk", "evidence_paths": [risk_path]},
            {"source_research_id": "dir", "evidence_paths": [context_path]},
        ]
    }

    result = build_inventory(preflight, pool)

    assert result["n_features"] == 2
    assert result["counts_by_role"] == {"context_label": 1, "risk_filter_candidate": 1}
    assert result["counts_by_extractability"] == {"aggregate_only": 1, "event_series_available": 1}
    assert result["ready_for_series_extraction"] == ["feat_ctx"]
    assert result["safety_gates"]["approved_for_paper"] == []
    assert result["safety_gates"]["safe_to_enable_trading"] is False

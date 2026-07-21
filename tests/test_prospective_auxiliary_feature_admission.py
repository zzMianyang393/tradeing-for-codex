from __future__ import annotations

import ast
import json
from pathlib import Path

from prospective_auxiliary_feature_admission import build_report, classify_source


def test_outcome_tainted_source_requires_raw_rebuild() -> None:
    source = {"path": "unused", "role": "context_label", "availability_contract": "raw rebuild"}
    result = classify_source("feature", source, {"events": [{"signal_ts": 1, "net_return_pct": 2.0}]})
    assert result["provenance_status"] == "outcome_tainted_rebuild_from_raw_required"
    assert result["forward_attach_allowed"] is False


def test_timestamped_clean_source_is_still_not_auto_attached() -> None:
    source = {"path": "unused", "role": "risk_filter_candidate", "availability_contract": "16:15 UTC"}
    result = classify_source("feature", source, {"events": [{"event_ts": 1, "qualified_fraction": 0.5}]})
    assert result["provenance_status"] == "raw_rebuild_candidate"
    assert result["forward_attach_allowed"] is False


def test_current_admission_report_blocks_all_forward_attachment() -> None:
    report = build_report()
    assert report["feature_count"] == 5
    assert report["admitted_for_forward_attachment"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False
    oi = next(item for item in report["features"] if item["feature_id"] == "feat_daily_oi_independent_change")
    assert oi["provenance_status"] == "raw_rebuild_candidate"


def test_module_has_no_runner_import() -> None:
    tree = ast.parse(Path("prospective_auxiliary_feature_admission.py").read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "runner" not in imports


def test_generated_report_has_no_result_fields() -> None:
    path = Path("reports/prospective_auxiliary_feature_admission.json")
    if not path.exists():
        return
    report = json.loads(path.read_text(encoding="utf-8"))
    serialized_keys = set()

    def collect(value):
        if isinstance(value, dict):
            serialized_keys.update(key.lower() for key in value)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(report)
    assert not serialized_keys & {"pnl", "return", "returns", "price", "position", "order", "trade"}

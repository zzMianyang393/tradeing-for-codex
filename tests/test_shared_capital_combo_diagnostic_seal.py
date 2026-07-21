from __future__ import annotations

import json
from pathlib import Path

from shared_capital_combo_diagnostic_seal import build_seal


ROOT = Path(__file__).resolve().parents[1]


def load_report(name: str) -> dict:
    return json.loads((ROOT / "reports" / name).read_text(encoding="utf-8"))


def test_current_shared_capital_combo_is_sealed():
    report = build_seal(
        load_report("regime_component_walk_forward_audit.json"),
        load_report("research_approval_registry.json"),
        load_report("strategy_feature_pool.json"),
        load_report("feature_pool_preflight_review.json"),
    )
    assert report["seal_status"] == "sealed"
    assert report["historical_diagnostic_only"] is True
    assert all(report["checks"].values())


def test_diagnostic_candidate_flag_breaks_the_seal():
    combo = {
        "shared_capital_combo": {
            "status": "historical_walk_forward_rejected",
            "leave_one_sleeve_out": {
                name: {"diagnostic_only": True, "not_a_candidate": True}
                for name in (
                    "uptrend_donchian_55_20_long",
                    "uptrend_supertrend_4h_long",
                    "range_bb_reversion_4h",
                    "range_rsi_reversion_4h",
                )
            },
        },
        "safety_gates": {
            "approved_for_paper": [],
            "eligible_for_paper": False,
            "safe_to_enable_trading": False,
            "ready_for_combo_backtest": False,
        },
    }
    combo["shared_capital_combo"]["leave_one_sleeve_out"]["range_bb_reversion_4h"]["not_a_candidate"] = False
    registry = {"records": [{"research_id": "regime_component_shared_capital_combo", "status": "rejected", "eligible_for_paper": False}]}
    feature_pool = {"features": [{"source_research_id": "regime_component_shared_capital_combo", "feature_role": "blocked", "allowed_in_combo_research": False, "allowed_as_standalone_strategy": False, "eligible_for_paper": False}]}
    preflight = {"groups": {"blocked_features": [{"source_research_id": "regime_component_shared_capital_combo"}]}}
    report = build_seal(combo, registry, feature_pool, preflight)
    assert report["seal_status"] == "invalid"
    assert report["checks"]["all_diagnostics_not_candidates"] is False


def test_missing_feature_hard_block_breaks_the_seal():
    combo = {"shared_capital_combo": {"status": "historical_walk_forward_rejected", "leave_one_sleeve_out": {}}, "safety_gates": {}}
    report = build_seal(combo, {"records": []}, {"features": []}, {"groups": {"blocked_features": []}})
    assert report["seal_status"] == "invalid"
    assert report["checks"]["feature_pool_hard_blocked"] is False


def test_seal_module_does_not_import_runner():
    content = (ROOT / "shared_capital_combo_diagnostic_seal.py").read_text(encoding="utf-8")
    assert "from runner import" not in content
    assert "import runner" not in content

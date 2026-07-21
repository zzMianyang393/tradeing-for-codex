from pathlib import Path

from strategy_prototype_universe_111 import build_report


def test_frozen_draft_exports_all_111_classified_prototypes() -> None:
    report = build_report(Path("docs/strategy_prototype_universe_100_draft_2026-07-13.md"))
    assert report["prototype_count"] == 111
    assert sum(report["status_counts"].values()) == 111
    assert all(item["status"] for item in report["prototypes"])
    assert report["safety_gates"]["approved_for_paper"] == []

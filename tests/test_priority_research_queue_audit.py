from priority_research_queue_audit import build_report


def test_all_structural_priorities_are_resolved_without_open_backtests():
    report = build_report()
    assert report["source_priority_count"] == 13
    assert report["closed_count"] == 13
    assert report["open_research_count"] == 0


def test_special_non_backtest_items_remain_explicitly_limited():
    items = {item["prototype_id"]: item for item in build_report()["items"]}
    assert items["MR_02"]["queue_status"] == "legacy_limited_scope_evidence"
    assert items["VS_05"]["queue_status"] == "observation_only"
    assert items["MR_09"]["queue_status"] == "requires_specification"


def test_queue_audit_does_not_open_research_or_trading_gates():
    report = build_report()
    assert all(item["requires_new_backtest"] is False for item in report["items"])
    assert report["safety_gates"]["approved_for_paper"] == []
    assert report["safety_gates"]["safe_to_enable_trading"] is False

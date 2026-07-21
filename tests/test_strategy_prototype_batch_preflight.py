from strategy_prototype_batch_preflight import screen


def test_single_leg_low_turnover_ohlcv_rule_can_reach_research_card_priority() -> None:
    item = {"prototype_id": "MR_06", "name_cn": "乖离率反转", "description": "价格偏离日线均线达极值做回归。", "status": "eligible_for_research",
            "attributes_raw": "[免费可复现: 是] [受阻数据: 否] [持有期: 3d-7d] [换手率: 低] [执行腿数: 1] [换壳嫌疑: 否]"}
    assert screen(item)[0] == "research_card_priority"


def test_multi_leg_or_blocked_data_rule_is_deferred() -> None:
    item = {"prototype_id": "FC_04", "name_cn": "Funding Carry", "description": "中期费率套利。", "status": "eligible_for_research",
            "attributes_raw": "[免费可复现: 是] [受阻数据: 否] [持有期: 10d-20d] [换手率: 极低] [执行腿数: 4] [换壳嫌疑: 否]"}
    decision, reasons = screen(item)
    assert decision == "structurally_deferred"
    assert reasons

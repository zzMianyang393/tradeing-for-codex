from volatility_expansion_volume_shock_overlap_audit import decision_key


def test_decision_key_requires_both_symbol_and_completed_daily_timestamp():
    assert decision_key("BTC-USDT-SWAP", 1) != decision_key("ETH-USDT-SWAP", 1)
    assert decision_key("BTC-USDT-SWAP", 1) != decision_key("BTC-USDT-SWAP", 2)

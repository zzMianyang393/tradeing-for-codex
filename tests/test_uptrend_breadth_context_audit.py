from uptrend_breadth_context_audit import asset_group, breadth_bucket, context_key, summarize_groups


def test_breadth_bucket_uses_fixed_boundaries():
    assert breadth_bucket(0.2499) == "narrow_lt_25pct"
    assert breadth_bucket(0.25) == "mixed_25_to_50pct"
    assert breadth_bucket(0.4999) == "mixed_25_to_50pct"
    assert breadth_bucket(0.50) == "broad_ge_50pct"


def test_context_key_preserves_btc_alignment_and_breadth():
    assert context_key(True, "broad_ge_50pct") == "btc_uptrend__broad_ge_50pct"
    assert context_key(False, "narrow_lt_25pct") == "btc_not_uptrend__narrow_lt_25pct"


def test_summarize_groups_keeps_horizon_statistics():
    groups = {
        "x": [
            {"forward_returns_pct": {"3d": 1.0}},
            {"forward_returns_pct": {"3d": -0.5}},
        ]
    }
    result = summarize_groups(groups)
    assert result["x"]["3d"]["observations"] == 2
    assert result["x"]["3d"]["mean_return_pct"] == 0.25


def test_asset_group_keeps_majors_separate_from_other_alts():
    assert asset_group("BTC-USDT-SWAP") == "BTC"
    assert asset_group("SOL-USDT-SWAP") == "SOL"
    assert asset_group("ADA-USDT-SWAP") == "other_alts"

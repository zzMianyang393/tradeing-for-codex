"""Tests for the 3-layer candidate pool pipeline."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market import FeatureBar
from candidate_pool import (
    scan_candidates,
    Candidate,
    CandidateEventStore,
    save_candidates,
    load_candidates,
)
from mfe_labeler import label_candidates
from candidate_filter import (
    CandidateFilter, RuleFilterConfig, MLFilterConfig,
    SimpleGradientBoosting, features_to_array, extract_features,
)


def _make_bar(
    ts: int = 1000,
    close: float = 100.0,
    open_: float = 99.0,
    high: float = 101.0,
    low: float = 98.0,
    ema20: float = 99.5,
    ema50: float = 99.0,
    ema200: float = 98.0,
    atr: float = 1.5,
    atr_pct: float = 0.015,
    rsi: float = 55.0,
    bb_upper: float = 103.0,
    bb_lower: float = 96.0,
    bb_mid: float = 99.5,
    vol_sma: float = 500_000.0,
    donchian_high: float = 101.0,
    donchian_low: float = 97.0,
    trend_strength: float = 1.0,
    volume_quote: float = 600_000.0,
) -> FeatureBar:
    return FeatureBar(
        ts=ts, time="2025-01-01 00:00:00",
        open=open_, high=high, low=low, close=close,
        volume_quote=volume_quote,
        ema20=ema20, ema50=ema50, ema200=ema200,
        atr=atr, atr_pct=atr_pct, rsi=rsi,
        bb_mid=bb_mid, bb_upper=bb_upper, bb_lower=bb_lower,
        vol_sma=vol_sma,
        donchian_high=donchian_high, donchian_low=donchian_low,
        trend_strength=trend_strength,
    )


def test_near_breakout_long():
    """Bar close to donchian high should generate a breakout long candidate."""
    prev = _make_bar(ts=999, close=99.0, donchian_high=101.0)
    # Current bar close at 100.8, near donchian high 101.0
    bar = _make_bar(
        ts=1000, close=100.8, open_=100.0, high=101.0, low=99.5,
        donchian_high=101.0, ema20=100.0, ema50=99.5, volume_quote=800_000,
    )
    bars = [prev, bar]
    cands = scan_candidates("BTC-USDT-SWAP", bars, idx=1, min_proximity=0.1)
    longs = [c for c in cands if c.direction == 1 and c.pattern_type == "breakout"]
    assert len(longs) >= 1, f"Expected breakout long candidate, got {cands}"
    assert longs[0].proximity_score > 0.1
    print("  ✓ near_breakout_long")


def test_near_pullback_long():
    """Bar bouncing off EMA20 should generate pullback candidate."""
    prev = _make_bar(ts=999, close=98.5, ema20=99.0)  # prev below EMA20
    bar = _make_bar(
        ts=1000, close=99.8, open_=99.0, ema20=99.5, ema50=99.0,
        volume_quote=600_000, rsi=52,
    )
    bars = [prev, bar]
    cands = scan_candidates("BTC-USDT-SWAP", bars, idx=1, min_proximity=0.1)
    pullbacks = [c for c in cands if c.direction == 1 and c.pattern_type == "pullback"]
    assert len(pullbacks) >= 1, f"Expected pullback long, got {cands}"
    print("  ✓ near_pullback_long")


def test_near_range_revert():
    """Bar near BB lower with low RSI should generate range revert candidate."""
    prev = _make_bar(ts=999, close=97.0)
    bar = _make_bar(
        ts=1000, close=96.2, open_=96.5, bb_lower=96.0, bb_upper=104.0,
        bb_mid=100.0, rsi=28, volume_quote=400_000, vol_sma=500_000,
        ema20=97.0, ema50=97.0, ema200=97.0, donchian_low=96.0,
        donchian_high=98.0, trend_strength=0.1, atr_pct=0.003,
    )
    bars = [prev, bar]
    cands = scan_candidates("BTC-USDT-SWAP", bars, idx=1, min_proximity=0.1)
    range_reverts = [c for c in cands if c.direction == 1 and c.pattern_type == "range_revert"]
    assert len(range_reverts) >= 1, f"Expected range revert long, got {cands}"
    print("  ✓ near_range_revert_long")


def test_no_candidates_for_flat_bar():
    """Flat, boring bar should produce no candidates."""
    prev = _make_bar(ts=999, close=100.0)
    bar = _make_bar(
        ts=1000, close=100.01, open_=100.0, high=100.05, low=99.95,
        donchian_high=105.0, donchian_low=95.0, rsi=50.0,
        volume_quote=100_000, vol_sma=500_000,
        ema20=100.0, ema50=100.0, ema200=100.0,
        bb_upper=101.0, bb_lower=99.0,
        trend_strength=0.0, atr_pct=0.003,
    )
    bars = [prev, bar]
    cands = scan_candidates("BTC-USDT-SWAP", bars, idx=1, min_proximity=0.4)
    assert len(cands) == 0, f"Expected no candidates for flat bar, got {cands}"
    print("  ✓ no_candidates_for_flat_bar")


def test_mfe_labeling():
    """Label candidates with forward MFE/MAE."""
    # Build 20 bars: bar 5 is the candidate, bars 6-13 show a rally
    bars = []
    for i in range(20):
        if i < 5:
            bars.append(_make_bar(ts=i, close=100.0 + i * 0.1, ema20=100.0, donchian_high=102.0))
        elif i == 5:
            # Candidate bar — close near donchian high
            bars.append(_make_bar(
                ts=i, close=101.8, open_=101.0, high=102.0, low=100.5,
                ema20=101.0, ema50=100.5, donchian_high=102.0,
                volume_quote=800_000,
            ))
        else:
            # Forward bars — rally to 104
            rally_close = 102.0 + (i - 5) * 0.25
            bars.append(_make_bar(
                ts=i, close=rally_close, high=rally_close + 0.3, low=rally_close - 0.2,
            ))

    # Scan candidate at bar 5
    cands = scan_candidates("BTC-USDT-SWAP", bars, idx=5, min_proximity=0.1)
    assert len(cands) > 0, "Should find candidates at bar 5"

    # Build index
    market = {"BTC-USDT-SWAP": bars}
    index = {"BTC-USDT-SWAP": {bar.ts: i for i, bar in enumerate(bars)}}

    # Label
    labeled = label_candidates(cands, market, index, horizon_bars=8, min_mfe_pct=0.003)
    assert len(labeled) > 0, "Should have labeled candidates"

    for c in labeled:
        assert c.mfe_pct >= 0, f"MFE should be >= 0, got {c.mfe_pct}"
        assert c.mae_pct >= 0, f"MAE should be >= 0, got {c.mae_pct}"
        assert c.net_pnl_pct > -1.0, f"Net exit PnL should be finite, got {c.net_pnl_pct}"
        assert c.label in (0, 1), f"Label should be 0 or 1, got {c.label}"
        assert c.label_horizon_bars == 8

    print(f"  ✓ mfe_labeling ({len(labeled)} candidates labeled)")


def test_net_exit_label_uses_executable_path():
    """The label follows the configured exit path, not MFE alone."""
    bars = [_make_bar(ts=i, close=100.0, ema20=100.0) for i in range(5)]
    bars[1] = _make_bar(ts=1, close=100.0, high=100.2, low=99.8, atr=1.0, atr_pct=0.01)
    bars[2] = _make_bar(ts=2, close=101.5, high=102.0, low=100.5, ema20=100.0, atr=1.0, atr_pct=0.01)
    candidate = Candidate(
        symbol="BTC-USDT-SWAP", ts=1, time="t", direction=1, regime="transition",
        pattern_type="breakout", proximity_score=0.5, close=100.0, open_=99.8,
        high=100.2, low=99.8, ema20=100.0, ema50=99.0, ema200=98.0, atr=1.0,
        atr_pct=0.01, rsi=55.0, bb_upper=103.0, bb_lower=96.0, bb_mid=99.5,
        donchian_high=101.0, donchian_low=97.0, trend_strength=1.0,
        vol_ratio=1.2, candle_body_pct=0.01, candle_range_pct=0.02, move_1d=0.01,
    )
    market = {candidate.symbol: bars}
    index = {candidate.symbol: {bar.ts: i for i, bar in enumerate(bars)}}
    labeled = label_candidates(
        [candidate], market, index, horizon_bars=2,
        stop_atr=1.0, take_profit_atr=1.0, trailing_atr=1.0,
        max_hold_bars=2, taker_fee=0.0, slippage=0.0,
    )
    assert len(labeled) == 1
    assert labeled[0].net_pnl_pct > 0
    assert labeled[0].label == 1


def test_mfe_labeling_respects_cutoff():
    """Candidates whose forward window crosses the cutoff are not labeled."""
    bars = [_make_bar(ts=i, close=100.0 + i * 0.1) for i in range(12)]
    cands = [Candidate(
        symbol="BTC-USDT-SWAP", ts=5, time="t", direction=1, regime="uptrend",
        pattern_type="breakout", proximity_score=0.5, close=100.5, open_=100.0,
        high=101.0, low=99.5, ema20=100.0, ema50=99.0, ema200=98.0,
        atr=1.5, atr_pct=0.015, rsi=55.0, bb_upper=103.0, bb_lower=96.0,
        bb_mid=99.5, donchian_high=101.0, donchian_low=97.0,
        trend_strength=1.0, vol_ratio=1.2, candle_body_pct=0.01,
        candle_range_pct=0.03, move_1d=0.005,
    )]
    market = {"BTC-USDT-SWAP": bars}
    index = {"BTC-USDT-SWAP": {bar.ts: i for i, bar in enumerate(bars)}}
    labeled = label_candidates(
        cands, market, index, horizon_bars=4, label_cutoff_ts=8,
    )
    assert labeled == [], "Incomplete forward windows must not enter training"
    print("  ✓ mfe_labeling_respects_cutoff")


def test_save_load_candidates():
    """Save and load candidates round-trip."""
    import tempfile
    c = Candidate(
        symbol="BTC-USDT-SWAP", ts=1000, time="2025-01-01",
        direction=1, regime="uptrend", pattern_type="breakout",
        proximity_score=0.5, close=100.0, open_=99.0, high=101.0, low=98.0,
        ema20=99.5, ema50=99.0, ema200=98.0, atr=1.5, atr_pct=0.015,
        rsi=55.0, bb_upper=103.0, bb_lower=96.0, bb_mid=99.5,
        donchian_high=101.0, donchian_low=97.0, trend_strength=1.0,
        vol_ratio=1.2, candle_body_pct=0.01, candle_range_pct=0.03,
        move_1d=0.005, mfe_pct=0.01, mae_pct=0.005, forward_pnl_pct=0.008,
        label=1, label_horizon_bars=8,
    )
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    save_candidates([c], path)
    loaded = load_candidates(path)
    assert len(loaded) == 1
    assert loaded[0].symbol == c.symbol
    assert loaded[0].mfe_pct == c.mfe_pct
    assert loaded[0].label == c.label
    path.unlink()
    print("  ✓ save_load_candidates")


def test_candidate_event_store():
    """Event store should retrieve only candidates for the requested timestamp."""
    import tempfile
    candidates = []
    for ts in (1000, 1001):
        candidates.append(Candidate(
            symbol="BTC", ts=ts, time="t", direction=1, regime="transition",
            pattern_type="breakout", proximity_score=0.5, close=100.0,
            open_=99.0, high=101.0, low=98.0, ema20=99.5, ema50=99.0,
            ema200=98.0, atr=1.5, atr_pct=0.015, rsi=55.0, bb_upper=103.0,
            bb_lower=96.0, bb_mid=99.5, donchian_high=101.0, donchian_low=97.0,
            trend_strength=1.0, vol_ratio=1.2, candle_body_pct=0.01,
            candle_range_pct=0.03, move_1d=0.005,
        ))
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    save_candidates(candidates, path)
    store = CandidateEventStore(path)
    try:
        assert [c.ts for c in store.get("BTC", 1001)] == [1001]
        assert store.get("BTC", 9999) == []
    finally:
        store.close()
        path.unlink()
    print("  ✓ candidate_event_store")


def test_rule_filter():
    """Rule-based filter should reject low-quality candidates."""
    filt = CandidateFilter(use_ml=False)

    # Good candidate
    good = Candidate(
        symbol="BTC", ts=1000, time="t", direction=1, regime="uptrend",
        pattern_type="breakout", proximity_score=0.5, close=100.0,
        open_=99.0, high=101.0, low=98.0, ema20=99.5, ema50=99.0,
        ema200=98.0, atr=1.5, atr_pct=0.015, rsi=55.0, bb_upper=103.0,
        bb_lower=96.0, bb_mid=99.5, donchian_high=101.0, donchian_low=97.0,
        trend_strength=1.0, vol_ratio=1.2, candle_body_pct=0.01,
        candle_range_pct=0.03, move_1d=0.005,
    )
    passed, reason, _ = filt.should_trade(good)
    assert passed, f"Good candidate should pass, got: {reason}"

    # Bad candidate: low proximity
    bad = Candidate(
        symbol="BTC", ts=1000, time="t", direction=1, regime="uptrend",
        pattern_type="breakout", proximity_score=0.1, close=100.0,
        open_=99.0, high=101.0, low=98.0, ema20=99.5, ema50=99.0,
        ema200=98.0, atr=1.5, atr_pct=0.015, rsi=55.0, bb_upper=103.0,
        bb_lower=96.0, bb_mid=99.5, donchian_high=101.0, donchian_low=97.0,
        trend_strength=1.0, vol_ratio=1.2, candle_body_pct=0.01,
        candle_range_pct=0.03, move_1d=0.005,
    )
    passed, reason, _ = filt.should_trade(bad)
    assert not passed, f"Bad candidate should fail, got: {reason}"
    print("  ✓ rule_filter")


def test_gradient_boosting():
    """Simple gradient boosting should learn a basic pattern."""
    # Create simple dataset: vol_ratio > 1.0 => positive
    X = []
    y = []
    for i in range(200):
        vr = 0.3 + (i % 10) * 0.2  # 0.3 to 2.1
        prox = 0.2 + (i // 10) * 0.04  # 0.2 to 0.98
        label = 1 if vr > 1.0 else 0
        X.append([vr, prox])
        y.append(label)

    model = SimpleGradientBoosting(n_estimators=80, learning_rate=0.15)
    model.fit(X, y)
    acc = model.score(X, y)
    assert acc > 0.85, f"Expected >85% accuracy, got {acc:.2%}"

    # Test prediction
    prob_good = model.predict_proba([[1.5, 0.6]])[0]
    prob_bad = model.predict_proba([[0.3, 0.1]])[0]
    assert prob_good > prob_bad, f"Good sample ({prob_good:.2f}) should score higher than bad ({prob_bad:.2f})"
    print(f"  ✓ gradient_boosting (acc={acc:.2%}, good_prob={prob_good:.2f}, bad_prob={prob_bad:.2f})")


def test_feature_extraction():
    """Features should be finite and correctly dimensioned."""
    c = Candidate(
        symbol="BTC", ts=1000, time="t", direction=1, regime="transition",
        pattern_type="volume_surge", proximity_score=0.6, close=100.0,
        open_=99.0, high=101.0, low=98.0, ema20=99.5, ema50=99.0,
        ema200=98.0, atr=1.5, atr_pct=0.015, rsi=55.0, bb_upper=103.0,
        bb_lower=96.0, bb_mid=99.5, donchian_high=101.0, donchian_low=97.0,
        trend_strength=1.0, vol_ratio=1.2, candle_body_pct=0.01,
        candle_range_pct=0.03, move_1d=0.005,
    )
    feats = extract_features(c)
    assert len(feats) == len(features_to_array(c))
    assert all(math.isfinite(v) for v in feats.values()), "All features should be finite"
    assert feats["regime_transition"] == 1.0
    assert feats["pattern_volume_surge"] == 1.0
    assert feats["direction"] == 1.0
    print("  ✓ feature_extraction")


if __name__ == "__main__":
    print("Running candidate pipeline tests...\n")
    test_near_breakout_long()
    test_near_pullback_long()
    test_near_range_revert()
    test_no_candidates_for_flat_bar()
    test_mfe_labeling()
    test_save_load_candidates()
    test_rule_filter()
    test_gradient_boosting()
    test_feature_extraction()
    print("\n✅ All tests passed!")

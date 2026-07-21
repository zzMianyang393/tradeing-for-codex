from __future__ import annotations

import json
from datetime import datetime, timezone
import unittest
from typing import Any

from market import FeatureBar
from market_state import calculate_market_state, detect_conflicts, get_completed_bars
from market_state_schema import (
    DailyState,
    H4State,
    M15State,
    MarketRegimeState,
    MarketState,
    MarketStateConfig,
    MarketStateSnapshot,
    MarketStateTransition,
    WeeklyState,
    ensure_utc,
    timeframe_state_from_dict,
    generate_snapshot_id,
    get_market_state_schema_version,
    get_market_state_config_fingerprint,
)


def make_mock_bar(
    ts: int,
    close: float,
    ema20: float,
    ema200: float,
    atr: float = 1.0,
    rsi: float = 50.0,
    vol: float = 60000.0,
) -> FeatureBar:
    return FeatureBar(
        ts=ts,
        time="mock",
        open=close,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume_quote=vol,
        ema20=ema20,
        ema50=ema20,
        ema200=ema200,
        atr=atr,
        atr_pct=0.01,
        rsi=rsi,
        bb_mid=close,
        bb_upper=close + 2.0,
        bb_lower=close - 2.0,
        vol_sma=vol,
        donchian_high=close + 5.0,
        donchian_low=close - 5.0,
        trend_strength=0.0,
    )


class TestMarketStateSchemaAndCalculation(unittest.TestCase):
    def test_utc_timezone_handling(self) -> None:
        # UTC string with Z
        dt_str_z = "2026-07-16T08:14:59Z"
        dt_z = ensure_utc(dt_str_z)
        self.assertEqual(dt_z.tzinfo, timezone.utc)
        self.assertEqual(dt_z.hour, 8)

        # UTC string with offset
        dt_str_offset = "2026-07-16T08:14:59+00:00"
        dt_offset = ensure_utc(dt_str_offset)
        self.assertEqual(dt_offset.tzinfo, timezone.utc)

        # Invalid formats should raise ValueError
        with self.assertRaises(ValueError):
            ensure_utc("invalid-date-format")

        with self.assertRaises(TypeError):
            ensure_utc(12345)  # type: ignore

    def test_naive_datetime_rejected(self) -> None:
        # Naive datetime must raise ValueError
        with self.assertRaises(ValueError):
            ensure_utc(datetime(2026, 7, 16, 8, 14, 59))

        # String without offset or Z suffix must raise ValueError
        with self.assertRaises(ValueError):
            ensure_utc("2026-07-16 08:14:59")

    def test_invalid_enum_rejected(self) -> None:
        # Invalid Weekly direction must raise ValueError
        with self.assertRaises(ValueError):
            WeeklyState(timeframe="1w", direction="super-trend")
            
        # Invalid volatility_state in DailyState
        with self.assertRaises(ValueError):
            DailyState(timeframe="1d", volatility_state="huge")

        # Invalid tradable_regime in H4State
        with self.assertRaises(ValueError):
            H4State(timeframe="4h", tradable_regime="scalping")

        # Invalid momentum in M15State
        with self.assertRaises(ValueError):
            M15State(timeframe="15m", momentum="super-bullish")

        # Invalid btc_state in MarketRegimeState
        with self.assertRaises(ValueError):
            MarketRegimeState(btc_state="sideways")

    def test_confidence_bounds(self) -> None:
        weekly = WeeklyState(timeframe="1w")
        daily = DailyState(timeframe="1d")
        h4 = H4State(timeframe="4h")
        m15 = M15State(timeframe="15m")
        regime = MarketRegimeState()
        available_at = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        source_close = datetime(2026, 7, 16, 11, 45, 0, tzinfo=timezone.utc)
        started_at = datetime(2026, 7, 15, 0, 0, 0, tzinfo=timezone.utc)

        # confidence < 0.0
        with self.assertRaises(ValueError):
            MarketState(
                weekly=weekly, daily=daily, h4=h4, m15=m15, market_regime=regime,
                available_at=available_at, source_bar_close_time=source_close,
                confidence=-0.1, state_started_at=started_at, version="v1.1.0"
            )

        # confidence > 1.0
        with self.assertRaises(ValueError):
            MarketState(
                weekly=weekly, daily=daily, h4=h4, m15=m15, market_regime=regime,
                available_at=available_at, source_bar_close_time=source_close,
                confidence=1.05, state_started_at=started_at, version="v1.1.0"
            )

    def test_source_close_later_than_available_at(self) -> None:
        weekly = WeeklyState(timeframe="1w")
        daily = DailyState(timeframe="1d")
        h4 = H4State(timeframe="4h")
        m15 = M15State(timeframe="15m")
        regime = MarketRegimeState()
        available_at = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        started_at = datetime(2026, 7, 15, 0, 0, 0, tzinfo=timezone.utc)

        # source_bar_close_time > available_at
        future_close = datetime(2026, 7, 16, 12, 0, 1, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            MarketState(
                weekly=weekly, daily=daily, h4=h4, m15=m15, market_regime=regime,
                available_at=available_at, source_bar_close_time=future_close,
                confidence=0.8, state_started_at=started_at, version="v1.1.0"
            )

    def test_snapshot_timestamp_mismatch(self) -> None:
        weekly = WeeklyState(timeframe="1w")
        daily = DailyState(timeframe="1d")
        h4 = H4State(timeframe="4h")
        m15 = M15State(timeframe="15m")
        regime = MarketRegimeState()
        available_at = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        started_at = datetime(2026, 7, 15, 0, 0, 0, tzinfo=timezone.utc)

        state = MarketState(
            weekly=weekly, daily=daily, h4=h4, m15=m15, market_regime=regime,
            available_at=available_at, source_bar_close_time=available_at,
            confidence=0.8, state_started_at=started_at, version="v1.1.0"
        )

        # snapshot.timestamp != state.available_at
        mismatched_time = datetime(2026, 7, 16, 12, 0, 1, tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            MarketStateSnapshot(
                snapshot_id="snap-1",
                timestamp=mismatched_time,
                symbol="BTC-USDT-SWAP",
                state=state,
                version="v1.1.0"
            )

    def test_deterministic_snapshot_id(self) -> None:
        weekly = WeeklyState(timeframe="1w")
        daily = DailyState(timeframe="1d")
        h4 = H4State(timeframe="4h")
        m15 = M15State(timeframe="15m")
        regime = MarketRegimeState()
        available_at = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        started_at = datetime(2026, 7, 15, 0, 0, 0, tzinfo=timezone.utc)

        state1 = MarketState(
            weekly=weekly, daily=daily, h4=h4, m15=m15, market_regime=regime,
            available_at=available_at, source_bar_close_time=available_at,
            confidence=0.8, state_started_at=started_at, version="v1.1.0"
        )

        state2 = MarketState(
            weekly=weekly, daily=daily, h4=h4, m15=m15, market_regime=regime,
            available_at=available_at, source_bar_close_time=available_at,
            confidence=0.8, state_started_at=started_at, version="v1.1.0"
        )

        id1 = generate_snapshot_id("BTC-USDT-SWAP", available_at, "fingerprint-abc", state1)
        id2 = generate_snapshot_id("BTC-USDT-SWAP", available_at, "fingerprint-abc", state2)

        # Identical inputs must yield identical ID
        self.assertEqual(id1, id2)

        # Changing config fingerprint changes ID
        id3 = generate_snapshot_id("BTC-USDT-SWAP", available_at, "fingerprint-xyz", state1)
        self.assertNotEqual(id1, id3)

        # Changing symbol changes ID
        id4 = generate_snapshot_id("ETH-USDT-SWAP", available_at, "fingerprint-abc", state1)
        self.assertNotEqual(id1, id4)

    def test_config_fingerprint_changes(self) -> None:
        config1 = MarketStateConfig()
        config2 = MarketStateConfig(trend_strength_threshold=2.0)
        
        # Verify default fingerprint
        fp1 = config1.fingerprint()
        fp2 = config2.fingerprint()
        
        self.assertNotEqual(fp1, fp2)
        self.assertEqual(len(fp1), 64)  # SHA-256 is 64 characters

    def test_backward_compatibility(self) -> None:
        # JSON without H4 direction (old format)
        old_h4_json = {
            "timeframe": "4h",
            "tradable_regime": "trend_following",
            "trend_stage": "mature",
            "breakout_or_pullback": "pullback",
            "volatility_state": "normal"
        }
        
        h4_state = H4State.from_dict(old_h4_json)
        self.assertEqual(h4_state.direction, "unknown")  # Defaulted successfully
        self.assertEqual(h4_state.tradable_regime, "trend_following")

    def test_json_roundtrip_not_losing_fields(self) -> None:
        weekly = WeeklyState(timeframe="1w", direction="uptrend", trend_strength=1.8, volatility_state="normal", risk_cycle="low_risk")
        daily = DailyState(timeframe="1d", direction="downtrend", trend_stage="mature", volatility_state="expanding", structure="pullback")
        h4 = H4State(timeframe="4h", direction="uptrend", tradable_regime="trend_following", trend_stage="early", breakout_or_pullback="breakout", volatility_state="normal")
        m15 = M15State(timeframe="15m", entry_context="oversold", momentum="strong_bearish", local_structure="lower_low", liquidity_state="normal")
        regime = MarketRegimeState(btc_state="uptrend", eth_state="uptrend", market_breadth=0.75, alt_relative_strength="alt-led", cross_section_dispersion=0.02)

        available_at = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        source_close = datetime(2026, 7, 16, 11, 45, 0, tzinfo=timezone.utc)
        started_at = datetime(2026, 7, 15, 0, 0, 0, tzinfo=timezone.utc)

        state = MarketState(
            weekly=weekly,
            daily=daily,
            h4=h4,
            m15=m15,
            market_regime=regime,
            available_at=available_at,
            source_bar_close_time=source_close,
            confidence=0.85,
            state_started_at=started_at,
            version="v1.1.0",
            insufficient_data_reasons=[],
            conflicts=[],
            is_consistent=True,
        )

        snapshot = MarketStateSnapshot(
            snapshot_id="snap-12345",
            timestamp=available_at,
            symbol="BTC-USDT-SWAP",
            state=state,
            version="v1.1.0",
        )

        transition = MarketStateTransition(
            transition_id="trans-9999",
            symbol="BTC-USDT-SWAP",
            previous_state=None,
            current_state=state,
            transition_time=available_at,
            changed_fields=["daily.direction"],
            trigger_event="new_bar",
            version="v1.1.0",
        )

        # Roundtrip Snapshot
        snap_dict = snapshot.to_dict()
        snap_json = json.dumps(snap_dict)
        snap_loaded = json.loads(snap_json)
        snap_restored = MarketStateSnapshot.from_dict(snap_loaded)

        self.assertEqual(snap_restored.snapshot_id, "snap-12345")
        self.assertEqual(snap_restored.timestamp, available_at)
        self.assertEqual(snap_restored.symbol, "BTC-USDT-SWAP")
        self.assertEqual(snap_restored.state.weekly.direction, "uptrend")
        self.assertEqual(snap_restored.state.weekly.trend_strength, 1.8)
        self.assertEqual(snap_restored.state.daily.trend_stage, "mature")
        self.assertEqual(snap_restored.state.h4.direction, "uptrend")
        self.assertEqual(snap_restored.state.h4.breakout_or_pullback, "breakout")
        self.assertEqual(snap_restored.state.m15.entry_context, "oversold")
        self.assertEqual(snap_restored.state.market_regime.alt_relative_strength, "alt-led")
        self.assertEqual(snap_restored.state.available_at, available_at)
        self.assertEqual(snap_restored.state.source_bar_close_time, source_close)
        self.assertEqual(snap_restored.state.state_started_at, started_at)
        self.assertEqual(snap_restored.state.confidence, 0.85)
        self.assertEqual(snap_restored.state.is_consistent, True)

        # Roundtrip Transition
        trans_dict = transition.to_dict()
        trans_json = json.dumps(trans_dict)
        trans_loaded = json.loads(trans_json)
        trans_restored = MarketStateTransition.from_dict(trans_loaded)

        self.assertEqual(trans_restored.transition_id, "trans-9999")
        self.assertEqual(trans_restored.transition_time, available_at)
        self.assertEqual(trans_restored.changed_fields, ["daily.direction"])
        self.assertIsNone(trans_restored.previous_state)

    def test_state_conflict_detection_and_consistency(self) -> None:
        weekly = WeeklyState(timeframe="1w", direction="uptrend")
        daily = DailyState(timeframe="1d", direction="downtrend")  # High conflict
        h4 = H4State(timeframe="4h", tradable_regime="mean_reversion")  # Medium conflict with Daily (downtrend)
        m15 = M15State(timeframe="15m", momentum="strong_bearish")

        config = MarketStateConfig()
        conflicts = detect_conflicts(weekly, daily, h4, m15, config)

        # We expect two conflicts: weekly vs daily direction, daily vs h4 regime
        self.assertEqual(len(conflicts), 2)

        weekly_vs_daily = [c for c in conflicts if c.field == "direction"]
        self.assertEqual(len(weekly_vs_daily), 1)
        self.assertEqual(weekly_vs_daily[0].severity, "high")

        daily_vs_h4 = [c for c in conflicts if c.field == "direction_regime"]
        self.assertEqual(len(daily_vs_h4), 1)
        self.assertEqual(daily_vs_h4[0].severity, "medium")

    def test_insufficient_data_propagation(self) -> None:
        config = MarketStateConfig()

        w_bars = [make_mock_bar(1000 + i * 604800000, 100.0, 100.0, 100.0) for i in range(5)]
        d_bars = [make_mock_bar(1000 + i * 86400000, 100.0, 100.0, 100.0) for i in range(10)]
        h4_bars = [make_mock_bar(1000 + i * 14400000, 100.0, 100.0, 100.0) for i in range(10)]
        m15_bars = [make_mock_bar(1000 + i * 900000, 100.0, 100.0, 100.0) for i in range(10)]

        available_at = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)

        state = calculate_market_state(
            symbol="BTC-USDT-SWAP",
            weekly_bars=w_bars,
            daily_bars=d_bars,
            h4_bars=h4_bars,
            m15_bars=m15_bars,
            market_regime_info={},
            config=config,
            available_at=available_at,
        )

        self.assertFalse(state.is_consistent)
        self.assertEqual(len(state.insufficient_data_reasons), 4)
        self.assertEqual(state.weekly.direction, "unknown")
        self.assertEqual(state.daily.direction, "unknown")
        self.assertEqual(state.h4.volatility_state, "unknown")
        self.assertEqual(state.m15.entry_context, "unknown")

    def test_lookahead_prevention_filter(self) -> None:
        available_at_ts = 1700000000
        available_at = datetime.fromtimestamp(available_at_ts, tz=timezone.utc)
        available_at_ms = available_at_ts * 1000.0

        weekly_duration_ms = 604800000

        bar1 = make_mock_bar(int(available_at_ms - 2 * weekly_duration_ms), 100.0, 100.0, 100.0)
        bar2 = make_mock_bar(int(available_at_ms - weekly_duration_ms), 100.0, 100.0, 100.0)
        bar3 = make_mock_bar(int(available_at_ms - 86400000), 100.0, 100.0, 100.0)
        bar4 = make_mock_bar(int(available_at_ms + 1000), 100.0, 100.0, 100.0)

        bars = [bar1, bar2, bar3, bar4]

        comp = get_completed_bars(bars, weekly_duration_ms, available_at_ms)

        self.assertEqual(len(comp), 2)
        self.assertIn(bar1, comp)
        self.assertIn(bar2, comp)
        self.assertNotIn(bar3, comp)
        self.assertNotIn(bar4, comp)


if __name__ == "__main__":
    unittest.main()

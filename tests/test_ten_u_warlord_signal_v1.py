from __future__ import annotations

import unittest
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market import FeatureBar
from market_state_schema import WeeklyState, DailyState, H4State, M15State, MarketRegimeState, MarketState, StateConflict
from ten_u_warlord_signal_v1 import check_signal, SignalProposal


def make_mock_bar(ts: int, close: float, high: float, low: float, atr: float = 1.0) -> FeatureBar:
    return FeatureBar(
        ts=ts,
        time="mock",
        open=close,
        high=high,
        low=low,
        close=close,
        volume_quote=60000.0,
        ema20=100.0,
        ema50=100.0,
        ema200=100.0,
        atr=atr,
        atr_pct=0.01,
        rsi=50.0,
        bb_mid=100.0,
        bb_upper=102.0,
        bb_lower=98.0,
        vol_sma=60000.0,
        donchian_high=105.0,
        donchian_low=95.0,
        trend_strength=0.0,
    )


def make_mock_market_state(
    weekly_dir: str = "uptrend",
    daily_dir: str = "uptrend",
    h4_dir: str = "uptrend",
    h4_regime: str = "trend_following",
    confidence: float = 0.8,
    conflicts: list = None,
    available_at: datetime = None,
) -> MarketState:
    if available_at is None:
        available_at = datetime(2026, 7, 16, 12, 0, 0, tzinfo=timezone.utc)
        
    return MarketState(
        weekly=WeeklyState(timeframe="1w", direction=weekly_dir),
        daily=DailyState(timeframe="1d", direction=daily_dir),
        h4=H4State(timeframe="4h", direction=h4_dir, tradable_regime=h4_regime),
        m15=M15State(timeframe="15m"),
        market_regime=MarketRegimeState(),
        available_at=available_at,
        source_bar_close_time=available_at,
        confidence=confidence,
        state_started_at=available_at,
        version="v1.1.0",
        insufficient_data_reasons=[],
        conflicts=conflicts or [],
        is_consistent=True,
    )


class TestTenUWarlordSignalV1(unittest.TestCase):
    def test_01_long_breakout_under_uptrend(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        
        # Create 47 completed bars (bar.ts + 15m <= available_at)
        available_at_ms = state.available_at.timestamp() * 1000
        bars = []
        for i in range(47):
            ts = int(available_at_ms - (47 - i) * 900000)
            # High for the lookback window is 105.0
            high = 105.0 if i < 46 else 110.0 # Lookback window runs from i=14 to 45 (indices completed_15m_bars[-33:-1])
            # Set lookup window high to 105
            b_high = 105.0 if (14 <= i < 46) else 100.0
            bars.append(make_mock_bar(ts, 100.0, b_high, 95.0, atr=2.0))

        # Trigger bar (last bar index 46): close is 108.0 (breakout above 105.0 lookback high)
        trigger_ts = int(available_at_ms - 900000)
        bars[-1] = make_mock_bar(trigger_ts, 108.0, 109.0, 100.0, atr=2.0)

        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.direction, "long")
        self.assertEqual(proposal.reference_close, Decimal("108.0"))
        self.assertEqual(proposal.stop_price, (proposal.reference_close - Decimal("1.5") * proposal.atr).quantize(Decimal("0.0001")))
        self.assertEqual(proposal.target_price, (proposal.reference_close + Decimal("4.5") * proposal.atr).quantize(Decimal("0.0001")))

    def test_02_short_breakdown_under_downtrend(self) -> None:
        state = make_mock_market_state(weekly_dir="downtrend", daily_dir="downtrend", h4_dir="downtrend")
        
        available_at_ms = state.available_at.timestamp() * 1000
        bars = []
        for i in range(47):
            ts = int(available_at_ms - (47 - i) * 900000)
            # Set lookup window low to 95
            b_low = 95.0 if (14 <= i < 46) else 100.0
            bars.append(make_mock_bar(ts, 100.0, 105.0, b_low, atr=2.0))

        # Trigger bar (last bar index 46): close is 93.0 (breakdown below 95.0 lookback low)
        trigger_ts = int(available_at_ms - 900000)
        bars[-1] = make_mock_bar(trigger_ts, 93.0, 100.0, 92.0, atr=2.0)

        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.direction, "short")
        self.assertEqual(proposal.reference_close, Decimal("93.0"))
        self.assertEqual(proposal.stop_price, (proposal.reference_close + Decimal("1.5") * proposal.atr).quantize(Decimal("0.0001")))
        self.assertEqual(proposal.target_price, (proposal.reference_close - Decimal("4.5") * proposal.atr).quantize(Decimal("0.0001")))

    def test_03_no_signal_in_range(self) -> None:
        state = make_mock_market_state(weekly_dir="range", daily_dir="range", h4_dir="range")
        bars = [make_mock_bar(i * 900000, 100.0, 105.0, 95.0, atr=2.0) for i in range(50)]
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNone(proposal)

    def test_04_no_signal_under_direction_conflict(self) -> None:
        # conflicts in macro directions: weekly is uptrend but daily is downtrend
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="downtrend", h4_dir="uptrend")
        bars = [make_mock_bar(i * 900000, 100.0, 105.0, 95.0, atr=2.0) for i in range(50)]
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNone(proposal)

    def test_05_no_signal_under_low_confidence(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend", confidence=0.65)
        bars = [make_mock_bar(i * 900000, 100.0, 105.0, 95.0, atr=2.0) for i in range(50)]
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNone(proposal)

    def test_06_no_signal_under_high_severity_conflict(self) -> None:
        conflict = StateConflict(timeframe_a="1w", timeframe_b="1d", field="direction", value_a="uptrend", value_b="downtrend", severity="high", description="weekly daily mismatch")
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend", conflicts=[conflict])
        bars = [make_mock_bar(i * 900000, 100.0, 105.0, 95.0, atr=2.0) for i in range(50)]
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNone(proposal)

    def test_07_15m_counter_momentum_not_overriding_macro(self) -> None:
        state = make_mock_market_state(weekly_dir="downtrend", daily_dir="downtrend", h4_dir="downtrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = []
        for i in range(47):
            ts = int(available_at_ms - (47 - i) * 900000)
            bars.append(make_mock_bar(ts, 100.0, 105.0, 95.0, atr=2.0))
        # Long breakout on 15m (108.0 > 105.0) but macro direction is downtrend
        bars[-1] = make_mock_bar(int(available_at_ms - 900000), 108.0, 109.0, 100.0, atr=2.0)
        
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNone(proposal)  # Should return None (long signal prohibited under downtrend)

    def test_08_trigger_bar_not_in_lookback_window(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = []
        for i in range(47):
            ts = int(available_at_ms - (47 - i) * 900000)
            # Lookback window high is 105.0
            bars.append(make_mock_bar(ts, 100.0, 105.0, 95.0, atr=2.0))

        # Trigger bar (index 46): close is 108.0, high is 110.0.
        # If trigger bar itself was included, close (108.0) would not be strictly higher than highest high (110.0).
        # Since it is excluded, close (108.0) is higher than lookback high (105.0) -> Triggers.
        bars[-1] = make_mock_bar(int(available_at_ms - 900000), 108.0, 110.0, 100.0, atr=2.0)

        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNotNone(proposal)

    def test_09_filter_uncompleted_bars(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = []
        for i in range(47):
            ts = int(available_at_ms - (47 - i) * 900000)
            bars.append(make_mock_bar(ts, 100.0, 105.0, 95.0, atr=2.0))

        # Set trigger bar's timestamp to close *after* available_at (so not completed)
        bars[-1] = make_mock_bar(int(available_at_ms), 108.0, 109.0, 100.0, atr=2.0)

        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNone(proposal)  # Trigger bar is filtered out, lookback triggers fail

    def test_10_insufficient_bars_count(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        # Provide only 40 bars (requires 47)
        bars = [make_mock_bar(i * 900000, 100.0, 105.0, 95.0, atr=2.0) for i in range(40)]
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNone(proposal)

    def test_11_next_open_does_not_affect_proposal(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = []
        for i in range(48):  # 48 bars, index 47 starts at available_at_ms (next bar)
            ts = int(available_at_ms - (47 - i) * 900000)
            b_high = 105.0 if i < 46 else 100.0
            bars.append(make_mock_bar(ts, 100.0, b_high, 95.0, atr=2.0))
        bars[46] = make_mock_bar(int(available_at_ms - 900000), 108.0, 109.0, 100.0, atr=2.0)

        proposal1 = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        
        # Modify the next bar (index 47)
        bars[47] = make_mock_bar(int(available_at_ms), 120.0, 125.0, 115.0, atr=2.0)
        proposal2 = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")

        self.assertEqual(proposal1, proposal2)

    def test_12_stop_atr_distance(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = [make_mock_bar(int(available_at_ms - (47 - i) * 900000), 100.0, 105.0, 95.0, atr=2.0) for i in range(47)]
        bars[-1] = make_mock_bar(int(available_at_ms - 900000), 108.0, 109.0, 100.0, atr=2.0)
        
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNotNone(proposal)
        stop_dist = abs(proposal.reference_close - proposal.stop_price)
        self.assertLessEqual(abs(stop_dist - Decimal("1.5") * proposal.atr), Decimal("0.0001"))

    def test_13_target_atr_distance(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = [make_mock_bar(int(available_at_ms - (47 - i) * 900000), 100.0, 105.0, 95.0, atr=2.0) for i in range(47)]
        bars[-1] = make_mock_bar(int(available_at_ms - 900000), 108.0, 109.0, 100.0, atr=2.0)
        
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNotNone(proposal)
        target_dist = abs(proposal.target_price - proposal.reference_close)
        self.assertLessEqual(abs(target_dist - Decimal("4.5") * proposal.atr), Decimal("0.0001"))

    def test_stale_completed_trigger_is_not_released_late(self) -> None:
        state = make_mock_market_state(
            available_at=datetime(2026, 7, 16, 12, 15, tzinfo=timezone.utc)
        )
        available_at_ms = int(state.available_at.timestamp() * 1000)
        bars = [
            make_mock_bar(available_at_ms - (48 - i) * 900000, 100, 105, 95)
            for i in range(47)
        ]
        bars[-1] = make_mock_bar(available_at_ms - 2 * 900000, 108, 109, 100)
        self.assertIsNone(check_signal("BTC-USDT-SWAP", state, bars, "snap-123"))

    def test_14_planned_r_multiple(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = [make_mock_bar(int(available_at_ms - (47 - i) * 900000), 100.0, 105.0, 95.0, atr=2.0) for i in range(47)]
        bars[-1] = make_mock_bar(int(available_at_ms - 900000), 108.0, 109.0, 100.0, atr=2.0)
        
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.planned_r_multiple, Decimal("3.0"))

    def test_15_long_stop_below_target_above(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = [make_mock_bar(int(available_at_ms - (47 - i) * 900000), 100.0, 105.0, 95.0, atr=2.0) for i in range(47)]
        bars[-1] = make_mock_bar(int(available_at_ms - 900000), 108.0, 109.0, 100.0, atr=2.0)
        
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNotNone(proposal)
        self.assertLess(proposal.stop_price, proposal.reference_close)
        self.assertGreater(proposal.target_price, proposal.reference_close)

    def test_16_short_stop_above_target_below(self) -> None:
        state = make_mock_market_state(weekly_dir="downtrend", daily_dir="downtrend", h4_dir="downtrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars = [make_mock_bar(int(available_at_ms - (47 - i) * 900000), 100.0, 105.0, 95.0, atr=2.0) for i in range(47)]
        bars[-1] = make_mock_bar(int(available_at_ms - 900000), 93.0, 100.0, 92.0, atr=2.0)
        
        proposal = check_signal("BTC-USDT-SWAP", state, bars, "snap-123")
        self.assertIsNotNone(proposal)
        self.assertGreater(proposal.stop_price, proposal.reference_close)
        self.assertLess(proposal.target_price, proposal.reference_close)

    def test_17_determinism_fingerprint(self) -> None:
        state = make_mock_market_state(weekly_dir="uptrend", daily_dir="uptrend", h4_dir="uptrend")
        available_at_ms = state.available_at.timestamp() * 1000
        bars1 = [make_mock_bar(int(available_at_ms - (47 - i) * 900000), 100.0, 105.0, 95.0, atr=2.0) for i in range(47)]
        bars1[-1] = make_mock_bar(int(available_at_ms - 900000), 108.0, 109.0, 100.0, atr=2.0)

        proposal1 = check_signal("BTC-USDT-SWAP", state, bars1, "snap-123")
        proposal2 = check_signal("BTC-USDT-SWAP", state, bars1, "snap-123")

        self.assertEqual(proposal1.signal_fingerprint, proposal2.signal_fingerprint)

    def test_18_no_parameter_search_interface(self) -> None:
        # Check that there is no public parameters or grids exposed in ten_u_warlord_signal_v1
        import ten_u_warlord_signal_v1
        attrs = dir(ten_u_warlord_signal_v1)
        self.assertNotIn("search_params", attrs)
        self.assertNotIn("tune_parameters", attrs)

    def test_19_does_not_read_balance_or_backtest_state(self) -> None:
        import inspect
        sig = inspect.signature(check_signal)
        params = list(sig.parameters.keys())
        self.assertNotIn("balance", params)
        self.assertNotIn("equity", params)
        self.assertNotIn("backtest_stage", params)

    def test_20_no_runner_executor_imports(self) -> None:
        # Verify source code of ten_u_warlord_signal_v1 does not import runner or executor
        src_path = Path(__file__).resolve().parents[1] / "ten_u_warlord_signal_v1.py"
        content = src_path.read_text(encoding="utf-8")
        self.assertNotIn("import runner", content)
        self.assertNotIn("import executor", content)
        self.assertNotIn("from runner import", content)
        self.assertNotIn("from executor import", content)


if __name__ == "__main__":
    unittest.main()

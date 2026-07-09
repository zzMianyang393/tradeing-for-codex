import unittest

from backtester import Backtester
from config import BacktestConfig
from market import FeatureBar
from strategy import Signal


def feature_bar(**overrides):
    values = {
        "ts": 1,
        "time": "2026-01-01 00:00:00",
        "open": 100.0,
        "high": 101.0,
        "low": 98.0,
        "close": 99.0,
        "volume_quote": 160.0,
        "ema20": 100.0,
        "ema50": 102.0,
        "ema200": 105.0,
        "atr": 2.0,
        "atr_pct": 0.02,
        "rsi": 45.0,
        "vol_sma": 100.0,
        "trend_strength": -2.4,
    }
    values.update(overrides)
    return FeatureBar(**values)


class DynamicStrategyRouterTests(unittest.TestCase):
    def test_blocks_reasons_in_router_blocklist(self):
        config = BacktestConfig(router_blocked_reasons=("trend_long",))
        tester = Backtester(config)
        signal = Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "trend_long")

        self.assertFalse(tester._dynamic_router_allows_signal(signal))

    def test_allows_only_whitelisted_reasons_when_allowlist_is_set(self):
        config = BacktestConfig(router_allowed_reasons=("transition_breakout_long",))
        tester = Backtester(config)
        allowed = Signal("BTC-USDT-SWAP", 1, 3.0, "transition", "transition_breakout_long")
        blocked = Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "trend_long")

        self.assertTrue(tester._dynamic_router_allows_signal(allowed))
        self.assertFalse(tester._dynamic_router_allows_signal(blocked))

    def test_rejects_signals_that_do_not_match_regime_structure(self):
        tester = Backtester(BacktestConfig())
        signal = Signal("BTC-USDT-SWAP", -1, 3.0, "uptrend", "transition_breakout_short")

        self.assertFalse(tester._dynamic_router_allows_signal(signal))

    def test_rejects_reason_outside_configured_allowed_regimes(self):
        config = BacktestConfig(
            router_allowed_reasons=("transition_breakout_long",),
            router_reason_allowed_regimes={"transition_breakout_long": ("transition",)},
        )
        tester = Backtester(config)
        allowed = Signal("BTC-USDT-SWAP", 1, 3.0, "transition", "transition_breakout_long")
        blocked = Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "transition_breakout_long")

        self.assertTrue(tester._dynamic_router_allows_signal(allowed))
        self.assertFalse(tester._dynamic_router_allows_signal(blocked))

    def test_explains_dynamic_router_rejection_reason(self):
        config = BacktestConfig(
            router_allowed_reasons=("transition_breakout_long", "transition_breakout_short"),
            router_blocked_reasons=("trend_long",),
            router_reason_allowed_regimes={"transition_breakout_long": ("transition",)},
        )
        tester = Backtester(config)

        self.assertEqual(
            "blocked_reason",
            tester._dynamic_router_rejection_reason(Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "trend_long")),
        )
        self.assertEqual(
            "not_allowed_reason",
            tester._dynamic_router_rejection_reason(Signal("BTC-USDT-SWAP", 1, 3.0, "range", "range_revert_long")),
        )
        self.assertEqual(
            "configured_regime_mismatch",
            tester._dynamic_router_rejection_reason(
                Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "transition_breakout_long")
            ),
        )
        self.assertEqual(
            "regime_structure_mismatch",
            tester._dynamic_router_rejection_reason(
                Signal("BTC-USDT-SWAP", -1, 3.0, "uptrend", "transition_breakout_short")
            ),
        )

    def test_trend_short_factor_gate_allows_only_audited_structure(self):
        config = BacktestConfig(
            router_allowed_reasons=("trend_short",),
            router_reason_allowed_regimes={"trend_short": ("downtrend",)},
            router_trend_short_factor_gate_enabled=True,
        )
        tester = Backtester(config)
        signal = Signal("BTC-USDT-SWAP", -1, 3.0, "downtrend", "trend_short")

        self.assertIsNone(tester._dynamic_router_rejection_reason(signal, feature_bar()))
        self.assertEqual(
            "trend_short_factor_mismatch",
            tester._dynamic_router_rejection_reason(signal, feature_bar(volume_quote=90.0)),
        )
        self.assertEqual(
            "trend_short_factor_mismatch",
            tester._dynamic_router_rejection_reason(signal, feature_bar(rsi=28.0)),
        )

    def test_can_disable_router_for_experiments(self):
        config = BacktestConfig(enable_dynamic_strategy_router=False, router_blocked_reasons=("trend_long",))
        tester = Backtester(config)
        signal = Signal("BTC-USDT-SWAP", 1, 3.0, "uptrend", "trend_long")

        self.assertTrue(tester._dynamic_router_allows_signal(signal))


if __name__ == "__main__":
    unittest.main()

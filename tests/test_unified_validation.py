from __future__ import annotations

import unittest
from types import SimpleNamespace

from unified_validation import _duplicate_fingerprints, signal_context_symbols, strategy_fingerprint
from candidate_signal_audit import audit_signals
from candidate_strategies import (
    build_btc_trend_pullback_provider,
    low_turnover_trend_signal,
    post_shock_reversal_signal,
)


class UnifiedValidationTests(unittest.TestCase):
    def test_fingerprint_changes_when_entry_changes(self):
        first = {"trades_detail": [{"symbol": "BTC", "direction": "long", "entry_time": "t1", "reason": "a"}]}
        second = {"trades_detail": [{"symbol": "BTC", "direction": "short", "entry_time": "t1", "reason": "a"}]}
        self.assertNotEqual(strategy_fingerprint(first), strategy_fingerprint(second))

    def test_duplicate_fingerprints_fail_integrity(self):
        fingerprint = "same"
        results = {
            "one": {"all_90d": {"trades": 1, "signal_fingerprint": fingerprint}},
            "two": {"all_90d": {"trades": 1, "signal_fingerprint": fingerprint}},
        }
        self.assertEqual(
            [{"window": "all_90d", "first": "one", "duplicate": "two"}],
            _duplicate_fingerprints(results),
        )

    def test_empty_trade_sets_do_not_claim_duplicate_strategy(self):
        results = {
            "one": {"all_90d": {"trades": 0, "signal_fingerprint": "same"}},
            "two": {"all_90d": {"trades": 0, "signal_fingerprint": "same"}},
        }
        self.assertEqual([], _duplicate_fingerprints(results))

    def test_low_turnover_trend_only_emits_on_completed_four_hour_breakout(self):
        bars = []
        for index in range(896):
            close = 100.0 + index * 0.02
            bars.append(SimpleNamespace(close=close))
        bars[-1] = SimpleNamespace(close=120.0)

        signal = low_turnover_trend_signal("BTC-USDT-SWAP", bars, len(bars) - 1)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(1, signal.direction)
        self.assertEqual("candidate_low_turnover_trend", signal.reason)
        self.assertIsNone(low_turnover_trend_signal("BTC-USDT-SWAP", bars, len(bars) - 2))

    def test_post_shock_reversal_requires_flush_volume_and_reclaim(self):
        bars = []
        for index in range(304):
            close = 100.0 if index < 16 else 86.0
            bars.append(SimpleNamespace(close=close, volume_quote=100.0, vol_sma=100.0, rsi=30.0))
        bars[-2] = SimpleNamespace(close=85.0, volume_quote=100.0, vol_sma=100.0, rsi=30.0)
        bars[-1] = SimpleNamespace(close=86.0, volume_quote=200.0, vol_sma=100.0, rsi=30.0)

        signal = post_shock_reversal_signal("BTC-USDT-SWAP", bars, len(bars) - 1)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(1, signal.direction)
        self.assertEqual("candidate_post_shock_reversal", signal.reason)

    def test_btc_trend_pullback_requires_btc_trend_and_completed_alt_reclaim(self):
        bars_by_symbol = {}
        for symbol in ("BTC-USDT-SWAP", "SOL-USDT-SWAP"):
            bars = []
            for index in range(656):
                close = 100.0 + index * 0.03
                bars.append(SimpleNamespace(ts=index, close=close, ema20=close - 0.1))
            bars_by_symbol[symbol] = bars
        alt = bars_by_symbol["SOL-USDT-SWAP"]
        alt[-49] = SimpleNamespace(ts=607, close=120.0, ema20=119.0)
        alt[-17] = SimpleNamespace(ts=639, close=116.0, ema20=115.0)
        alt[-1] = SimpleNamespace(ts=655, close=117.0, ema20=116.0)

        signal = build_btc_trend_pullback_provider(bars_by_symbol)("SOL-USDT-SWAP", alt, len(alt) - 1)

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(1, signal.direction)
        self.assertEqual("candidate_btc_trend_pullback", signal.reason)

    def test_signal_audit_counts_actual_provider_events(self):
        bars_by_symbol = {}
        for symbol in ("BTC-USDT-SWAP", "SOL-USDT-SWAP"):
            bars = [SimpleNamespace(ts=index, close=100.0 + index * 0.03, ema20=99.0) for index in range(656)]
            bars_by_symbol[symbol] = bars
        alt = bars_by_symbol["SOL-USDT-SWAP"]
        alt[-49] = SimpleNamespace(ts=607, close=120.0, ema20=119.0)
        alt[-17] = SimpleNamespace(ts=639, close=116.0, ema20=115.0)
        alt[-1] = SimpleNamespace(ts=655, close=117.0, ema20=116.0)

        report = audit_signals(bars_by_symbol, "btc_trend_pullback", SimpleNamespace())

        self.assertEqual(1, report["raw_signals"])
        self.assertEqual({"SOL-USDT-SWAP": 1}, report["by_symbol"])

    def test_cross_market_candidates_keep_btc_context_without_making_it_tradable(self):
        symbols = signal_context_symbols("btc_trend_pullback", ["SOL-USDT-SWAP", "AVAX-USDT-SWAP"])
        self.assertEqual(["AVAX-USDT-SWAP", "BTC-USDT-SWAP", "SOL-USDT-SWAP"], symbols)
        self.assertEqual(["SOL-USDT-SWAP"], signal_context_symbols("intraday_reversal", ["SOL-USDT-SWAP"]))


if __name__ == "__main__":
    unittest.main()

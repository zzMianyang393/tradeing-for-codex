from __future__ import annotations

import unittest
from types import SimpleNamespace

from unified_validation import _duplicate_fingerprints, strategy_fingerprint
from candidate_strategies import low_turnover_trend_signal, post_shock_reversal_signal


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


if __name__ == "__main__":
    unittest.main()

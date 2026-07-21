from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from candidate_signal_audit import audit_entry_timing
from market import FeatureBar
from strategy import Signal


class EntryTimingAuditTests(unittest.TestCase):
    def test_uses_next_open_and_groups_extended_entries(self):
        bars = []
        for index in range(110):
            close = 100.0 + index
            bars.append(
                FeatureBar(
                    ts=index,
                    time=str(index),
                    open=close + 0.5,
                    high=close + 2.0,
                    low=close - 1.0,
                    close=close,
                    volume_quote=1.0,
                    ema20=close - 4.0,
                    atr=2.0,
                )
            )

        provider = lambda symbol, _bars, index: Signal(symbol, 1, 3.0, "candidate", "test") if index == 100 else None
        with patch("candidate_signal_audit.provider_for", return_value=provider):
            report = audit_entry_timing({"ALT-USDT-SWAP": bars}, "test", SimpleNamespace(), horizons=(4,))

        overall = report["overall"]
        self.assertEqual(1, overall["signals"])
        self.assertAlmostEqual(2.0, overall["avg_extension_atr"])
        self.assertEqual(1, overall["forward"]["4x15m"]["signals"])
        # Entry is index 101's open (201.5), rather than the signal close (200).
        self.assertAlmostEqual((205.0 / 201.5 - 1.0), overall["forward"]["4x15m"]["avg_return"])
        self.assertIn("1-2 ATR", report["by_extension_bucket"])

    def test_rejects_same_bar_execution_assumption(self):
        with self.assertRaises(ValueError):
            audit_entry_timing({}, "test", SimpleNamespace(), execution_delay_bars=0)


if __name__ == "__main__":
    unittest.main()

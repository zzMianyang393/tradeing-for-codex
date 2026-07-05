import unittest
from dataclasses import replace

from backtester import select_symbols
from config import BacktestConfig
from market import FeatureBar


def _bars(symbol_seed: int, noise: float, quote: float) -> list[FeatureBar]:
    bars = []
    for idx in range(300):
        ts = 1_700_000_000_000 + idx * 15 * 60_000
        close = 100.0 + symbol_seed + idx * 0.01
        bars.append(
            FeatureBar(
                ts=ts,
                time=str(ts),
                open=close,
                high=close * (1.0 + noise),
                low=close * (1.0 - noise),
                close=close,
                volume_quote=quote,
                atr=close * 0.01,
                atr_pct=0.01,
                trend_strength=0.5,
            )
        )
    return bars


class SelectorQualityTests(unittest.TestCase):
    def test_selector_can_filter_noisy_symbols(self):
        clean = _bars(1, noise=0.002, quote=1_000_000.0)
        noisy = _bars(2, noise=0.08, quote=1_000_000.0)
        cfg = replace(BacktestConfig(), selector_max_micro_noise=0.02)

        selected = select_symbols(
            {"CLEAN-USDT-SWAP": clean, "NOISY-USDT-SWAP": noisy},
            clean[-1].ts,
            limit=2,
            config=cfg,
        )

        self.assertEqual(["CLEAN-USDT-SWAP"], selected)

    def test_selector_can_filter_low_quote_symbols(self):
        liquid = _bars(1, noise=0.002, quote=1_000_000.0)
        thin = _bars(2, noise=0.002, quote=100.0)
        cfg = replace(BacktestConfig(), selector_min_avg_quote=10_000.0)

        selected = select_symbols(
            {"LIQUID-USDT-SWAP": liquid, "THIN-USDT-SWAP": thin},
            liquid[-1].ts,
            limit=2,
            config=cfg,
        )

        self.assertEqual(["LIQUID-USDT-SWAP"], selected)

    def test_selector_skips_excluded_symbols(self):
        keep = _bars(1, noise=0.002, quote=1_000_000.0)
        skip = _bars(2, noise=0.002, quote=1_000_000.0)
        cfg = replace(BacktestConfig(), excluded_symbols=("SKIP-USDT-SWAP",))

        selected = select_symbols(
            {"KEEP-USDT-SWAP": keep, "SKIP-USDT-SWAP": skip},
            keep[-1].ts,
            limit=2,
            config=cfg,
        )

        self.assertEqual(["KEEP-USDT-SWAP"], selected)


if __name__ == "__main__":
    unittest.main()

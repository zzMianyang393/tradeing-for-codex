import unittest
from dataclasses import replace

from backtester import Backtester
from config import BacktestConfig
from order_book import OrderBookFeatureBar
from strategy import Signal, order_book_signal_for


def _bars(direction: int, imbalance: float = 0.5, spread_pct: float = 0.001) -> list[OrderBookFeatureBar]:
    bars = []
    for idx in range(240):
        close = 100.0 + direction * idx * 0.03
        if idx == 239:
            close += direction * 1.4
        donchian_high = close * 1.02
        donchian_low = close * 0.98
        if idx == 239 and direction > 0:
            donchian_high = close * 0.999
        if idx == 239 and direction < 0:
            donchian_low = close * 1.001
        depth_imbalance = imbalance if direction > 0 else -imbalance
        bars.append(
            OrderBookFeatureBar(
                ts=1_700_000_000_000 + idx * 15 * 60_000,
                time=str(idx),
                open=close - direction * 0.2,
                high=close + 0.5,
                low=close - 0.5,
                close=close,
                volume_quote=1_000_000.0,
                ema20=close - direction * 0.2,
                ema50=close - direction * 0.4,
                ema200=close - direction * 0.6,
                atr=0.7,
                atr_pct=0.007,
                rsi=59.0 if direction > 0 else 41.0,
                vol_sma=900_000.0,
                donchian_high=donchian_high,
                donchian_low=donchian_low,
                trend_strength=0.8 * direction,
                best_bid=99.9,
                best_ask=100.1,
                order_book_spread_pct=spread_pct,
                bid_depth_quote=1_500_000.0,
                ask_depth_quote=500_000.0,
                depth_imbalance=depth_imbalance,
            )
        )
    return bars


class OrderBookSignalTests(unittest.TestCase):
    def test_disabled_by_default(self):
        signal = order_book_signal_for("BTC-USDT-SWAP", _bars(1), 239, BacktestConfig())

        self.assertIsNone(signal)

    def test_emits_long_on_bid_depth_breakout(self):
        cfg = replace(BacktestConfig(), enable_order_book_module=True)

        signal = order_book_signal_for("BTC-USDT-SWAP", _bars(1), 239, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(1, signal.direction)
        self.assertEqual("order_book_imbalance_long", signal.reason)

    def test_emits_short_on_ask_depth_breakdown(self):
        cfg = replace(BacktestConfig(), enable_order_book_module=True)

        signal = order_book_signal_for("BTC-USDT-SWAP", _bars(-1), 239, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(-1, signal.direction)
        self.assertEqual("order_book_imbalance_short", signal.reason)

    def test_rejects_weak_imbalance_and_wide_spread(self):
        cfg = replace(BacktestConfig(), enable_order_book_module=True)

        self.assertIsNone(order_book_signal_for("BTC-USDT-SWAP", _bars(1, imbalance=0.1), 239, cfg))
        self.assertIsNone(order_book_signal_for("BTC-USDT-SWAP", _bars(1, spread_pct=0.02), 239, cfg))

    def test_backtester_uses_order_book_position_parameters(self):
        cfg = replace(
            BacktestConfig(),
            enable_order_book_module=True,
            order_book_risk_per_trade=0.025,
            order_book_stop_atr=1.6,
            order_book_take_profit_atr=1.05,
        )
        tester = Backtester(cfg)
        signal = Signal("BTC-USDT-SWAP", 1, 3.6, "order_book", "order_book_imbalance_long")

        self.assertEqual(0.025, tester._risk_per_trade_for_signal(signal))
        self.assertEqual(1.6, tester._stop_atr_for_signal(signal))
        self.assertEqual(1.05, tester._take_profit_atr_for_signal(signal))


if __name__ == "__main__":
    unittest.main()

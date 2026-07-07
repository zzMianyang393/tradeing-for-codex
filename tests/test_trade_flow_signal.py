import unittest
from dataclasses import replace

from backtester import Backtester
from config import BacktestConfig
from strategy import Signal, trade_flow_signal_for
from trade_flow import TradeFlowFeatureBar


def _bars(direction: int, imbalance: float = 0.7, flow_quote: float = 1_200_000.0) -> list[TradeFlowFeatureBar]:
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
        buy_quote = flow_quote * (1.0 + imbalance) / 2.0
        sell_quote = flow_quote - buy_quote
        if direction < 0:
            buy_quote, sell_quote = sell_quote, buy_quote
        bars.append(
            TradeFlowFeatureBar(
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
                active_buy_quote=buy_quote,
                active_sell_quote=sell_quote,
                active_buy_ratio=buy_quote / flow_quote if flow_quote else 0.0,
                trade_flow_imbalance=(buy_quote - sell_quote) / flow_quote if flow_quote else 0.0,
            )
        )
    return bars


class TradeFlowSignalTests(unittest.TestCase):
    def test_disabled_by_default(self):
        signal = trade_flow_signal_for("BTC-USDT-SWAP", _bars(1), 239, BacktestConfig())

        self.assertIsNone(signal)

    def test_emits_long_on_buy_flow_breakout(self):
        cfg = replace(BacktestConfig(), enable_trade_flow_module=True)

        signal = trade_flow_signal_for("BTC-USDT-SWAP", _bars(1), 239, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(1, signal.direction)
        self.assertEqual("trade_flow_breakout_long", signal.reason)

    def test_emits_short_on_sell_flow_breakdown(self):
        cfg = replace(BacktestConfig(), enable_trade_flow_module=True)

        signal = trade_flow_signal_for("BTC-USDT-SWAP", _bars(-1), 239, cfg)

        self.assertIsNotNone(signal)
        self.assertEqual(-1, signal.direction)
        self.assertEqual("trade_flow_breakout_short", signal.reason)

    def test_rejects_weak_imbalance(self):
        cfg = replace(BacktestConfig(), enable_trade_flow_module=True)

        signal = trade_flow_signal_for("BTC-USDT-SWAP", _bars(1, imbalance=0.1), 239, cfg)

        self.assertIsNone(signal)

    def test_rejects_low_trade_flow(self):
        cfg = replace(BacktestConfig(), enable_trade_flow_module=True)

        signal = trade_flow_signal_for("BTC-USDT-SWAP", _bars(1, flow_quote=100_000.0), 239, cfg)

        self.assertIsNone(signal)

    def test_backtester_uses_trade_flow_position_parameters(self):
        cfg = replace(
            BacktestConfig(),
            enable_trade_flow_module=True,
            trade_flow_risk_per_trade=0.025,
            trade_flow_stop_atr=1.6,
            trade_flow_take_profit_atr=1.05,
        )
        tester = Backtester(cfg)
        signal = Signal("BTC-USDT-SWAP", 1, 3.6, "trade_flow", "trade_flow_breakout_long")

        self.assertEqual(0.025, tester._risk_per_trade_for_signal(signal))
        self.assertEqual(1.6, tester._stop_atr_for_signal(signal))
        self.assertEqual(1.05, tester._take_profit_atr_for_signal(signal))


if __name__ == "__main__":
    unittest.main()

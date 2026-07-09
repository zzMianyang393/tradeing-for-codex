import unittest

from market import FeatureBar
from trend_factor_audit import audit_trend_factor_buckets, trend_factor_tags


def bar(**overrides):
    values = {
        "ts": 1,
        "time": "2026-01-01 00:00:00",
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "close": 102.0,
        "volume_quote": 150.0,
        "ema20": 100.0,
        "ema50": 98.0,
        "ema200": 95.0,
        "atr": 2.0,
        "atr_pct": 0.02,
        "rsi": 56.0,
        "vol_sma": 100.0,
        "donchian_high": 103.0,
        "donchian_low": 90.0,
        "trend_strength": 2.4,
    }
    values.update(overrides)
    return FeatureBar(**values)


class TrendFactorAuditTests(unittest.TestCase):
    def test_trend_factor_tags_describe_structure_in_chinese(self):
        tags = trend_factor_tags(bar(), direction=1)

        self.assertIn("强趋势", tags)
        self.assertIn("放量", tags)
        self.assertIn("RSI中性", tags)
        self.assertIn("贴近均线", tags)

    def test_audit_trend_factor_buckets_groups_trade_performance(self):
        market = {
            "BTC-USDT-SWAP": [
                bar(time="2026-01-01 00:00:00", trend_strength=2.4, rsi=55, volume_quote=160),
                bar(time="2026-01-01 00:15:00", trend_strength=2.5, rsi=56, volume_quote=155),
                bar(time="2026-01-01 00:30:00", trend_strength=2.6, rsi=57, volume_quote=150),
            ],
            "ETH-USDT-SWAP": [
                bar(time="2026-01-01 00:00:00", trend_strength=-2.2, rsi=45, volume_quote=160),
            ],
        }
        trades = [
            {"symbol": "BTC-USDT-SWAP", "entry_time": "2026-01-01 00:00:00", "reason": "trend_long", "pnl": 1.0, "win": True},
            {"symbol": "BTC-USDT-SWAP", "entry_time": "2026-01-01 00:15:00", "reason": "trend_long", "pnl": 0.8, "win": True},
            {"symbol": "BTC-USDT-SWAP", "entry_time": "2026-01-01 00:30:00", "reason": "trend_long", "pnl": -0.2, "win": False},
            {"symbol": "ETH-USDT-SWAP", "entry_time": "2026-01-01 00:00:00", "reason": "trend_short", "pnl": -1.2, "win": False},
        ]

        audit = audit_trend_factor_buckets({"trades_detail": trades}, market, min_trades=3)

        self.assertEqual(4, audit["total_trend_trades"])
        self.assertEqual("趋势做多|强趋势|放量|RSI中性|贴近均线", audit["buckets"][0]["factor_key"])
        self.assertEqual("可候选复核", audit["buckets"][0]["action_cn"])
        self.assertEqual(1.6, audit["buckets"][0]["pnl"])

    def test_audit_trend_factor_buckets_reads_window_reports(self):
        market = {
            "BTC-USDT-SWAP": [
                bar(time="2026-01-01 00:00:00", trend_strength=2.4, rsi=55, volume_quote=160),
            ],
        }
        report = {
            "windows": {
                "30": {
                    "trades_detail": [
                        {
                            "symbol": "BTC-USDT-SWAP",
                            "entry_time": "2026-01-01 00:00:00",
                            "reason": "trend_long",
                            "pnl": 1.0,
                            "win": True,
                        }
                    ]
                }
            }
        }

        audit = audit_trend_factor_buckets(report, market, min_trades=1)

        self.assertEqual(1, audit["total_trend_trades"])
        self.assertEqual(1, audit["matched_trend_trades"])


if __name__ == "__main__":
    unittest.main()

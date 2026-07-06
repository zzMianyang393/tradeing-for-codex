from __future__ import annotations

import json
import unittest

from exchange import ExchangeError, OKXExchange, OrderResult


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, method, url, headers, body):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "body": body,
            }
        )
        return self.response


class TestOKXExchange(unittest.TestCase):
    def test_get_ticker_sends_signed_sandbox_request(self):
        transport = FakeTransport(
            {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "last": "50100.5",
                        "bidPx": "50100.0",
                        "askPx": "50101.0",
                    }
                ],
            }
        )
        exchange = OKXExchange("key", "secret", "passphrase", transport=transport)

        ticker = exchange.get_ticker("BTC-USDT-SWAP")

        self.assertEqual("BTC-USDT-SWAP", ticker.symbol)
        self.assertAlmostEqual(50100.5, ticker.last)
        call = transport.calls[0]
        self.assertEqual("GET", call["method"])
        self.assertIn("/api/v5/market/ticker?instId=BTC-USDT-SWAP", call["url"])
        self.assertEqual("key", call["headers"]["OK-ACCESS-KEY"])
        self.assertEqual("passphrase", call["headers"]["OK-ACCESS-PASSPHRASE"])
        self.assertEqual("1", call["headers"]["x-simulated-trading"])
        self.assertIn("OK-ACCESS-SIGN", call["headers"])
        self.assertIsNone(call["body"])

    def test_place_order_maps_long_limit_payload(self):
        transport = FakeTransport(
            {
                "code": "0",
                "data": [
                    {
                        "ordId": "okx-1",
                        "sCode": "0",
                        "sMsg": "",
                    }
                ],
            }
        )
        exchange = OKXExchange("key", "secret", "passphrase", transport=transport)

        result = exchange.place_order(
            "BTC-USDT-SWAP",
            "long",
            0.1,
            order_type="limit",
            price=50000.0,
        )

        self.assertIsInstance(result, OrderResult)
        self.assertEqual("okx-1", result.order_id)
        self.assertEqual("BTC-USDT-SWAP", result.symbol)
        self.assertEqual("long", result.direction)
        self.assertEqual("live", result.status)
        call = transport.calls[0]
        self.assertEqual("POST", call["method"])
        self.assertTrue(call["url"].endswith("/api/v5/trade/order"))
        payload = json.loads(call["body"])
        self.assertEqual(
            {
                "instId": "BTC-USDT-SWAP",
                "tdMode": "cross",
                "side": "buy",
                "ordType": "limit",
                "sz": "0.1",
                "px": "50000.0",
            },
            payload,
        )

    def test_okx_error_response_raises_exchange_error(self):
        transport = FakeTransport({"code": "51000", "msg": "bad request", "data": []})
        exchange = OKXExchange("key", "secret", "passphrase", transport=transport)

        with self.assertRaises(ExchangeError) as cm:
            exchange.get_ticker("BTC-USDT-SWAP")

        self.assertIn("51000", str(cm.exception))
        self.assertIn("bad request", str(cm.exception))

    def test_get_positions_maps_okx_positions_for_reconciliation(self):
        transport = FakeTransport(
            {
                "code": "0",
                "data": [
                    {
                        "instId": "BTC-USDT-SWAP",
                        "posSide": "long",
                        "pos": "0.2",
                        "avgPx": "50000",
                        "upl": "12.5",
                    },
                    {
                        "instId": "ETH-USDT-SWAP",
                        "posSide": "short",
                        "pos": "1",
                        "avgPx": "3000",
                        "upl": "-2.0",
                    },
                ],
            }
        )
        exchange = OKXExchange("key", "secret", "passphrase", transport=transport)

        positions = exchange.get_positions()

        self.assertEqual(
            [
                {
                    "symbol": "BTC-USDT-SWAP",
                    "direction": "long",
                    "qty": 0.2,
                    "entry_price": 50000.0,
                    "unrealized_pnl": 12.5,
                },
                {
                    "symbol": "ETH-USDT-SWAP",
                    "direction": "short",
                    "qty": 1.0,
                    "entry_price": 3000.0,
                    "unrealized_pnl": -2.0,
                },
            ],
            positions,
        )


if __name__ == "__main__":
    unittest.main()

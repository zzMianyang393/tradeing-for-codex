from __future__ import annotations

import hashlib
import hmac
import json
import time
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import requests


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AccountInfo:
    total_equity: float = 0.0
    available_balance: float = 0.0
    used_margin: float = 0.0
    unrealized_pnl: float = 0.0
    currency: str = "USDT"


@dataclass
class PositionInfo:
    symbol: str = ""
    direction: str = ""  # "long" / "short"
    entry_price: float = 0.0
    current_price: float = 0.0
    qty: float = 0.0
    notional: float = 0.0
    margin: float = 0.0
    leverage: float = 1.0
    unrealized_pnl: float = 0.0
    liquidation_price: float = 0.0
    margin_mode: str = "cross"  # "cross" / "isolated"


@dataclass
class Ticker:
    symbol: str = ""
    last: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    volume_24h: float = 0.0
    timestamp: int = 0


@dataclass
class OrderResult:
    success: bool = False
    order_id: str = ""
    client_order_id: str = ""
    error_code: str = ""
    error_message: str = ""


@dataclass
class OrderStatus:
    order_id: str = ""
    symbol: str = ""
    status: str = ""  # "pending" / "filled" / "partially_filled" / "cancelled" / "failed"
    side: str = ""
    order_type: str = ""
    price: float = 0.0
    qty: float = 0.0
    filled_qty: float = 0.0
    filled_price: float = 0.0
    fee: float = 0.0
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# OKX Exchange
# ---------------------------------------------------------------------------

class OKXExchange:
    """OKX V5 REST API wrapper for paper trading (sandbox) or live.

    Usage::

        exchange = OKXExchange(api_key, secret, passphrase, sandbox=True)
        balance = exchange.get_account_balance()
        positions = exchange.get_positions()
        result = exchange.place_order("BTC-USDT-SWAP", "buy", 0.01)
    """

    BASE_URL_SANDBOX = "https://www.okx.com"
    BASE_URL_LIVE = "https://www.okx.com"

    def __init__(
        self,
        api_key: str,
        secret: str,
        passphrase: str,
        sandbox: bool = True,
    ) -> None:
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        self.sandbox = sandbox
        self.base_url = self.BASE_URL_SANDBOX if sandbox else self.BASE_URL_LIVE
        self._session = requests.Session()
        self._session.headers.update({
            "OK-ACCESS-KEY": api_key,
            "Content-Type": "application/json",
        })

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = timestamp + method.upper() + path + body
        mac = hmac.new(
            self.secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode("utf-8")

    def _headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        sign = self._sign(timestamp, method, path, body)
        return {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = self.base_url + path
        body_str = json.dumps(body) if body else ""
        headers = self._headers(method, path, body_str)

        if self.sandbox:
            headers["x-simulated-trading"] = "1"

        resp = self._session.request(
            method,
            url,
            params=params,
            data=body_str if body else None,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0":
            raise OKXAPIError(data.get("code", ""), data.get("msg", ""))
        return data

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account_balance(self) -> AccountInfo:
        data = self._request("GET", "/api/v5/account/balance")
        details = data.get("data", [{}])[0].get("details", [])
        for d in details:
            if d.get("ccy") == "USDT":
                return AccountInfo(
                    total_equity=float(d.get("eq", 0)),
                    available_balance=float(d.get("availBal", 0)),
                    used_margin=float(d.get("frozenBal", 0)),
                    unrealized_pnl=float(d.get("unrealizedPnl", 0)),
                    currency="USDT",
                )
        return AccountInfo()

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        params: dict[str, str] = {}
        if symbol:
            params["instId"] = symbol
        data = self._request("GET", "/api/v5/account/positions", params=params)
        positions = []
        for p in data.get("data", []):
            pos_amt = float(p.get("pos", 0))
            if pos_amt == 0:
                continue
            direction = "long" if pos_amt > 0 else "short"
            positions.append(PositionInfo(
                symbol=p.get("instId", ""),
                direction=direction,
                entry_price=float(p.get("avgPx", 0)),
                current_price=float(p.get("markPx", 0) or p.get("last", 0)),
                qty=abs(pos_amt),
                notional=float(p.get("notionalUsd", 0)),
                margin=float(p.get("margin", 0)),
                leverage=float(p.get("lever", 1)),
                unrealized_pnl=float(p.get("upl", 0)),
                liquidation_price=float(p.get("liqPx", 0)),
                margin_mode=p.get("mgnMode", "cross"),
            ))
        return positions

    # ------------------------------------------------------------------
    # Ticker
    # ------------------------------------------------------------------

    def get_ticker(self, symbol: str) -> Ticker:
        data = self._request("GET", "/api/v5/market/ticker", params={"instId": symbol})
        t = data.get("data", [{}])[0]
        return Ticker(
            symbol=t.get("instId", ""),
            last=float(t.get("last", 0)),
            bid=float(t.get("bidPx", 0)),
            ask=float(t.get("askPx", 0)),
            high_24h=float(t.get("high24h", 0)),
            low_24h=float(t.get("low24h", 0)),
            volume_24h=float(t.get("vol24h", 0)),
            timestamp=int(t.get("ts", 0)),
        )

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,  # "buy" / "sell"
        size: float,
        order_type: str = "market",  # "market" / "limit"
        price: float | None = None,
        td_mode: str = "cross",  # "cross" / "isolated"
        client_order_id: str = "",
    ) -> OrderResult:
        body: dict[str, Any] = {
            "instId": symbol,
            "tdMode": td_mode,
            "side": side,
            "ordType": order_type,
            "sz": str(size),
        }
        if price is not None:
            body["px"] = str(price)
        if client_order_id:
            body["clOrdId"] = client_order_id

        try:
            data = self._request("POST", "/api/v5/trade/order", body=body)
            result = data.get("data", [{}])[0]
            return OrderResult(
                success=result.get("sCode", "") == "0",
                order_id=result.get("ordId", ""),
                client_order_id=result.get("clOrdId", ""),
                error_code=result.get("sCode", ""),
                error_message=result.get("sMsg", ""),
            )
        except (OKXAPIError, requests.RequestException) as e:
            return OrderResult(
                success=False,
                error_code=str(type(e).__name__),
                error_message=str(e),
            )

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            data = self._request("POST", "/api/v5/trade/cancel-order", body={
                "instId": symbol,
                "ordId": order_id,
            })
            result = data.get("data", [{}])[0]
            return result.get("sCode", "") == "0"
        except (OKXAPIError, requests.RequestException):
            return False

    def get_order_status(self, order_id: str, symbol: str) -> OrderStatus:
        data = self._request("GET", "/api/v5/trade/order", params={
            "instId": symbol,
            "ordId": order_id,
        })
        o = data.get("data", [{}])[0]
        return OrderStatus(
            order_id=o.get("ordId", ""),
            symbol=o.get("instId", ""),
            status=o.get("state", ""),
            side=o.get("side", ""),
            order_type=o.get("ordType", ""),
            price=float(o.get("px", 0)),
            qty=float(o.get("sz", 0)),
            filled_qty=float(o.get("fillSz", 0)),
            filled_price=float(o.get("avgPx", 0)),
            fee=float(o.get("fee", 0)),
            created_at=o.get("cTime", ""),
            updated_at=o.get("uTime", ""),
        )

    # ------------------------------------------------------------------
    # Leverage & Position Mode
    # ------------------------------------------------------------------

    def set_leverage(self, symbol: str, leverage: int, margin_mode: str = "cross") -> bool:
        try:
            data = self._request("POST", "/api/v5/account/set-leverage", body={
                "instId": symbol,
                "lever": str(leverage),
                "mgnMode": margin_mode,
            })
            return data.get("code") == "0"
        except (OKXAPIError, requests.RequestException):
            return False

    def set_position_mode(self, mode: str = "long_short_mode") -> bool:
        """Set position mode: 'long_short_mode' or 'net_mode'."""
        try:
            data = self._request("POST", "/api/v5/account/set-position-mode", body={
                "posMode": mode,
            })
            return data.get("code") == "0"
        except (OKXAPIError, requests.RequestException):
            return False

    # ------------------------------------------------------------------
    # Klines (for fetching latest bars)
    # ------------------------------------------------------------------

    def get_klines(self, symbol: str, bar: str = "15m", limit: int = 300) -> list[dict]:
        """Fetch kline/candlestick data.

        Returns list of dicts with keys: ts, open, high, low, close, volume.
        """
        data = self._request("GET", "/api/v5/market/candles", params={
            "instId": symbol,
            "bar": bar,
            "limit": str(limit),
        })
        candles = []
        for c in data.get("data", []):
            candles.append({
                "ts": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            })
        return list(reversed(candles))  # OKX returns newest first

    # ------------------------------------------------------------------
    # Funding Rate
    # ------------------------------------------------------------------

    def get_funding_rate(self, symbol: str) -> dict:
        data = self._request("GET", "/api/v5/public/funding-rate", params={
            "instId": symbol,
        })
        fr = data.get("data", [{}])[0]
        return {
            "symbol": fr.get("instId", ""),
            "funding_rate": float(fr.get("fundingRate", 0)),
            "next_funding_rate": float(fr.get("nextFundingRate", 0)),
            "funding_time": fr.get("fundingTime", ""),
        }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class OKXAPIError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"OKX API error {code}: {message}")

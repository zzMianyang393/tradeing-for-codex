from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger("exchange")

# Transient HTTP status codes that are safe to retry
_TRANSIENT_HTTP_CODES = {408, 429, 500, 502, 503, 504}


@dataclass
class OrderResult:
    order_id: str = ""
    symbol: str = ""
    direction: str = ""
    qty: float = 0.0
    status: str = ""
    fill_price: float | None = None
    fill_qty: float | None = None
    fee: float = 0.0
    reason: str = ""
    success: bool = False
    client_order_id: str = ""
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        if not self.success and self.status in ("filled", "live", "pending", "partially_filled"):
            self.success = True


@dataclass
class AccountInfo:
    equity: float = 0.0
    available_margin: float = 0.0
    used_margin: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    total_equity: float = 0.0
    available_balance: float = 0.0
    unrealized_pnl: float = 0.0
    currency: str = "USDT"

    def __post_init__(self) -> None:
        if self.total_equity and not self.equity:
            self.equity = self.total_equity
        if self.equity and not self.total_equity:
            self.total_equity = self.equity
        if self.available_balance and not self.available_margin:
            self.available_margin = self.available_balance
        if self.available_margin and not self.available_balance:
            self.available_balance = self.available_margin


@dataclass
class PositionInfo:
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    current_price: float = 0.0
    qty: float = 0.0
    notional: float = 0.0
    margin: float = 0.0
    leverage: float = 1.0
    unrealized_pnl: float = 0.0
    liquidation_price: float = 0.0
    margin_mode: str = "cross"


@dataclass
class Ticker:
    symbol: str = ""
    last: float = 0.0
    bid: float | None = None
    ask: float | None = None
    raw: dict[str, Any] | None = None
    high_24h: float = 0.0
    low_24h: float = 0.0
    volume_24h: float = 0.0
    timestamp: int = 0


@dataclass
class OrderStatus:
    order_id: str = ""
    symbol: str = ""
    status: str = ""
    side: str = ""
    order_type: str = ""
    price: float = 0.0
    qty: float = 0.0
    filled_qty: float = 0.0
    filled_price: float = 0.0
    fee: float = 0.0
    created_at: str = ""
    updated_at: str = ""


class ExchangeError(RuntimeError):
    pass


class OKXAPIError(ExchangeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"OKX API error {code}: {message}")


Transport = Callable[[str, str, dict[str, str], str | None], Any]


class OKXExchange:
    """Minimal OKX REST wrapper for simulated trading and integration tests."""

    def __init__(
        self,
        api_key: str,
        secret: str,
        passphrase: str,
        sandbox: bool = True,
        base_url: str = "https://www.okx.com",
        transport: Transport | None = None,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        request_timeout: float = 15.0,
        max_slippage_pct: float = 0.005,
    ) -> None:
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        self.sandbox = sandbox
        self.base_url = base_url.rstrip("/")
        self.transport = transport
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.request_timeout = request_timeout
        self.max_slippage_pct = max_slippage_pct

    def get_account_balance(self) -> AccountInfo:
        payload = self._request("GET", "/api/v5/account/balance")
        data = self._first_data(payload)
        details = data.get("details") or []
        equity = self._float(data.get("totalEq"))
        available_margin = 0.0
        used_margin = 0.0
        for detail in details:
            available_margin += self._float(detail.get("availEq") or detail.get("availBal"))
            used_margin += self._float(detail.get("imr"))
        return AccountInfo(
            equity=equity,
            available_margin=available_margin,
            used_margin=used_margin,
            raw=data,
        )

    def get_positions(self) -> list[dict]:
        payload = self._request("GET", "/api/v5/account/positions")
        positions = []
        for item in payload.get("data", []):
            direction = self._direction_from_position(item)
            if not direction:
                continue
            positions.append(
                {
                    "symbol": item.get("instId", ""),
                    "direction": direction,
                    "qty": abs(self._float(item.get("pos"))),
                    "entry_price": self._float(item.get("avgPx")),
                    "unrealized_pnl": self._float(item.get("upl")),
                }
            )
        return positions

    def get_ticker(self, symbol: str) -> Ticker:
        payload = self._request("GET", "/api/v5/market/ticker", query={"instId": symbol})
        data = self._first_data(payload)
        return Ticker(
            symbol=data.get("instId", symbol),
            last=self._float(data.get("last")),
            bid=self._optional_float(data.get("bidPx")),
            ask=self._optional_float(data.get("askPx")),
            raw=data,
        )

    def place_order(
        self,
        symbol: str,
        direction: str,
        qty: float,
        order_type: str = "market",
        price: float | None = None,
        fee: float = 0.0,
    ) -> OrderResult:
        side = self._side_from_direction(direction)
        payload: dict[str, str] = {
            "instId": symbol,
            "tdMode": "cross",
            "side": side,
            "ordType": order_type,
            "sz": str(qty),
        }

        # Slippage protection: for market orders without a price, use limit order
        # with a price guard based on the current ticker
        if price is not None:
            payload["px"] = str(price)
        elif order_type == "market" and self.max_slippage_pct > 0:
            try:
                ticker = self.get_ticker(symbol)
                ref_price = ticker.last
                if ref_price > 0:
                    if direction in ("long", "buy"):
                        limit_price = ref_price * (1.0 + self.max_slippage_pct)
                    else:
                        limit_price = ref_price * (1.0 - self.max_slippage_pct)
                    payload["ordType"] = "limit"
                    payload["px"] = f"{limit_price:.6f}"
                    logger.info("Slippage guard: %s market→limit at %.6f (ref=%.6f, slip=%.4f%%)",
                                symbol, limit_price, ref_price, self.max_slippage_pct * 100)
            except Exception as exc:
                logger.warning("Slippage guard ticker fetch failed for %s: %s", symbol, exc)
                # Fall back to plain market order

        response = self._request("POST", "/api/v5/trade/order", body=payload)
        data = self._first_data(response)
        code = data.get("sCode", "0")
        if code != "0":
            raise ExchangeError(f"OKX order rejected {code}: {data.get('sMsg', '')}")

        return OrderResult(
            order_id=data.get("ordId", ""),
            symbol=symbol,
            direction=direction,
            qty=qty,
            status="live",
            fee=fee,
            reason=data.get("sMsg", ""),
        )

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        payload = {"instId": symbol, "ordId": order_id}
        return self._request("POST", "/api/v5/trade/cancel-order", body=payload)

    def get_order_status(self, symbol: str, order_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v5/trade/order",
            query={"instId": symbol, "ordId": order_id},
        )

    def set_leverage(self, symbol: str, leverage: float, margin_mode: str = "cross") -> dict[str, Any]:
        payload = {"instId": symbol, "lever": str(leverage), "mgnMode": margin_mode}
        return self._request("POST", "/api/v5/account/set-leverage", body=payload)

    def set_position_mode(self, mode: str = "long_short_mode") -> dict[str, Any]:
        return self._request("POST", "/api/v5/account/set-position-mode", body={"posMode": mode})

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        request_path = path
        if query:
            request_path = f"{path}?{urlencode(query)}"
        body_text = json.dumps(body, separators=(",", ":")) if body is not None else None
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        headers = self._headers(timestamp, method, request_path, body_text or "")
        url = f"{self.base_url}{request_path}"

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                if self.transport is not None:
                    response = self.transport(method, url, headers, body_text)
                else:
                    response = self._urlopen(method, url, headers, body_text)

                payload = self._parse_response(response)
                code = str(payload.get("code", "0"))
                if code != "0":
                    raise ExchangeError(f"OKX error {code}: {payload.get('msg', '')}")
                return payload
            except (ExchangeError, HTTPError, URLError, TimeoutError, OSError) as exc:
                last_error = exc
                is_transient = self._is_transient_error(exc)
                if not is_transient or attempt >= self.max_retries:
                    raise
                delay = self.retry_base_delay * (2 ** attempt)
                logger.warning("OKX request %s %s attempt %d/%d failed (%s), retrying in %.1fs",
                               method, path, attempt + 1, self.max_retries, exc, delay)
                time.sleep(delay)
        raise last_error  # type: ignore[misc]

    def _is_transient_error(self, exc: Exception) -> bool:
        """Check if an error is transient and safe to retry."""
        if isinstance(exc, HTTPError):
            return exc.code in _TRANSIENT_HTTP_CODES
        if isinstance(exc, (URLError, TimeoutError, OSError)):
            return True
        if isinstance(exc, ExchangeError):
            msg = str(exc).lower()
            return "rate limit" in msg or "too many" in msg or "timeout" in msg
        return False

    def _headers(self, timestamp: str, method: str, path: str, body: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": self._sign(timestamp, method, path, body),
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
        }
        if self.sandbox:
            headers["x-simulated-trading"] = "1"
        return headers

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = f"{timestamp}{method.upper()}{path}{body}".encode("utf-8")
        digest = hmac.new(self.secret.encode("utf-8"), message, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("ascii")

    def _urlopen(self, method: str, url: str, headers: dict[str, str], body: str | None) -> str:
        data = body.encode("utf-8") if body is not None else None
        request = Request(url, data=data, headers=headers, method=method)
        with urlopen(request, timeout=self.request_timeout) as response:
            return response.read().decode("utf-8")

    def _parse_response(self, response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            return response
        if isinstance(response, bytes):
            response = response.decode("utf-8")
        if isinstance(response, str):
            return json.loads(response)
        raise ExchangeError(f"Unsupported OKX response type: {type(response)!r}")

    def _first_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data") or []
        if not data:
            return {}
        return data[0]

    def _side_from_direction(self, direction: str) -> str:
        if direction in ("long", "buy"):
            return "buy"
        if direction in ("short", "sell"):
            return "sell"
        raise ValueError(f"Unsupported direction: {direction}")

    def _direction_from_position(self, position: dict[str, Any]) -> str:
        side = position.get("posSide") or position.get("side")
        if side in ("long", "short"):
            return side
        qty = self._float(position.get("pos"))
        if qty > 0:
            return "long"
        if qty < 0:
            return "short"
        return ""

    def _float(self, value: Any) -> float:
        if value in (None, ""):
            return 0.0
        return float(value)

    def _optional_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        return float(value)


class DryRunExchange:
    """Local exchange stub that fills orders immediately at the requested price."""

    def __init__(self, equity: float = 10.0) -> None:
        self._next_order_id = 1
        self.orders: list[OrderResult] = []
        self.positions: list[dict] = []
        self._equity = equity

    def get_account_balance(self) -> AccountInfo:
        used_margin = sum(p.get("margin", 0.0) for p in self.positions)
        return AccountInfo(
            equity=self._equity,
            available_margin=max(0.0, self._equity - used_margin),
            used_margin=used_margin,
        )

    def get_ticker(self, symbol: str) -> Any:
        """Return a stub ticker. For dry-run, prices come from market data."""
        from types import SimpleNamespace
        return SimpleNamespace(symbol=symbol, last=0.0, bid=0.0, ask=0.0)

    def place_order(
        self,
        symbol: str,
        direction: str,
        qty: float,
        order_type: str = "market",
        price: float | None = None,
        fee: float = 0.0,
    ) -> OrderResult:
        fill_price = price if price is not None else 0.0
        result = OrderResult(
            order_id=f"dry-{self._next_order_id}",
            symbol=symbol,
            direction=direction,
            qty=qty,
            status="filled",
            fill_price=fill_price,
            fill_qty=qty,
            fee=fee,
        )
        self._next_order_id += 1
        self.orders.append(result)
        self.positions.append({"symbol": symbol, "direction": direction})
        return result

    def get_positions(self) -> list[dict]:
        return [dict(position) for position in self.positions]

    def close_position(
        self,
        symbol: str,
        direction: str,
        qty: float,
        price: float,
        fee: float = 0.0,
    ) -> OrderResult:
        opposite = "short" if direction == "long" else "long"
        result = self.place_order(
            symbol,
            opposite,
            qty,
            order_type="market",
            price=price,
            fee=fee,
        )
        for idx, position in enumerate(self.positions):
            if position["symbol"] == symbol and position["direction"] == direction:
                del self.positions[idx]
                break
        for idx, position in enumerate(self.positions):
            if position["symbol"] == symbol and position["direction"] == opposite:
                del self.positions[idx]
                break
        return result

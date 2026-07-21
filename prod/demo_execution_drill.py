"""OKX simulated-trading execution drill for majors only (ETH/BTC).

Never submits orders for RAVE/LAB. Live trading is not supported here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Protocol


from prod.policy import LOCAL_EXPERIMENT_SYMBOLS, PRODUCTION_BOUND_SYMBOLS

DEMO_ALLOWED_SYMBOLS = PRODUCTION_BOUND_SYMBOLS
DEMO_BLOCKED_SYMBOLS = LOCAL_EXPERIMENT_SYMBOLS


class ExchangeLike(Protocol):
    def get_account_balance(self) -> Any: ...
    def get_ticker(self, symbol: str) -> Any: ...
    def get_positions(self) -> list: ...
    def place_order(
        self,
        symbol: str,
        direction: str,
        qty: float,
        order_type: str = "market",
        price: float | None = None,
        fee: float = 0.0,
    ) -> Any: ...
    def cancel_order(self, symbol: str, order_id: str) -> Any: ...


ExchangeFactory = Callable[[], tuple[ExchangeLike | None, dict[str, Any] | None]]


@dataclass(frozen=True)
class DrillPlan:
    symbol: str
    action: str  # readiness | smoke_limit_cancel
    allowed: bool
    reason: str


def plan_demo_drill(
    symbol: str,
    *,
    confirm_smoke: bool,
) -> DrillPlan:
    """Pure decision: which demo drill is allowed for a symbol."""
    sym = symbol.strip().upper()
    if not sym.endswith("-SWAP"):
        # normalize common forms
        if sym in {"ETH", "ETH-USDT"}:
            sym = "ETH-USDT-SWAP"
        elif sym in {"BTC", "BTC-USDT"}:
            sym = "BTC-USDT-SWAP"
    if sym in DEMO_BLOCKED_SYMBOLS:
        return DrillPlan(
            symbol=sym,
            action="blocked",
            allowed=False,
            reason="symbol_not_supported_on_okx_demo_for_this_track",
        )
    if sym not in DEMO_ALLOWED_SYMBOLS:
        return DrillPlan(
            symbol=sym,
            action="blocked",
            allowed=False,
            reason="symbol_not_in_demo_execution_allowlist",
        )
    if confirm_smoke:
        return DrillPlan(
            symbol=sym,
            action="smoke_limit_cancel",
            allowed=True,
            reason="confirmed_smoke_on_demo_major",
        )
    return DrillPlan(
        symbol=sym,
        action="readiness",
        allowed=True,
        reason="readiness_only_no_order_without_confirm",
    )


def credentials_from_env(env: dict[str, str] | None = None) -> dict[str, str]:
    source = env if env is not None else os.environ
    return {
        "OKX_API_KEY": source.get("OKX_API_KEY", "") or "",
        "OKX_API_SECRET": source.get("OKX_API_SECRET", "") or "",
        "OKX_API_PASSPHRASE": source.get("OKX_API_PASSPHRASE", "") or "",
    }


def missing_credential_names(creds: dict[str, str]) -> list[str]:
    return [name for name, value in creds.items() if not value]


def default_exchange_factory() -> tuple[ExchangeLike | None, dict[str, Any] | None]:
    from exchange import OKXExchange

    creds = credentials_from_env()
    missing = missing_credential_names(creds)
    if missing:
        return None, {"error": f"Missing OKX credentials: {', '.join(missing)}"}
    return (
        OKXExchange(
            creds["OKX_API_KEY"],
            creds["OKX_API_SECRET"],
            creds["OKX_API_PASSPHRASE"],
            sandbox=True,
        ),
        None,
    )


def run_demo_execution_drill(
    *,
    symbol: str = "ETH-USDT-SWAP",
    confirm_smoke: bool = False,
    qty: float = 0.01,
    limit_offset_pct: float = 0.05,
    exchange_factory: ExchangeFactory = default_exchange_factory,
    report_path: Path | None = Path("reports/prod/demo_execution_drill.json"),
) -> dict[str, Any]:
    plan = plan_demo_drill(symbol, confirm_smoke=confirm_smoke)
    as_of = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    base: dict[str, Any] = {
        "report_type": "okx_demo_execution_drill",
        "as_of": as_of,
        "sandbox": True,
        "live_trading": False,
        "plan": asdict(plan),
    }
    if not plan.allowed:
        base["formal_status"] = "blocked"
        base["error"] = plan.reason
        _write(report_path, base)
        return base

    exchange, err = exchange_factory()
    if err or exchange is None:
        base["formal_status"] = "blocked_missing_credentials"
        base["error"] = (err or {}).get("error", "exchange_unavailable")
        _write(report_path, base)
        return base

    try:
        account = exchange.get_account_balance()
        ticker = exchange.get_ticker(plan.symbol)
        positions = exchange.get_positions()
        base["account"] = {
            "equity": getattr(account, "equity", None),
            "available_margin": getattr(account, "available_margin", None),
            "used_margin": getattr(account, "used_margin", None),
        }
        last = float(getattr(ticker, "last", 0.0) or 0.0)
        base["ticker"] = {
            "symbol": getattr(ticker, "symbol", plan.symbol),
            "last": last,
            "bid": getattr(ticker, "bid", None),
            "ask": getattr(ticker, "ask", None),
        }
        base["open_positions"] = len(positions)

        if plan.action == "readiness":
            base["formal_status"] = "readiness_ok"
            base["order_submitted"] = False
            _write(report_path, base)
            return base

        # smoke: far limit then cancel (unlikely to fill)
        if last <= 0:
            base["formal_status"] = "fail"
            base["error"] = "invalid_ticker_last"
            _write(report_path, base)
            return base
        # Buy far below market so it rests; then cancel.
        price = round(last * (1.0 - abs(limit_offset_pct)), 6)
        if price <= 0:
            price = last * 0.5
        order = exchange.place_order(
            plan.symbol,
            "long",
            qty,
            order_type="limit",
            price=price,
        )
        order_id = getattr(order, "order_id", "") or ""
        cancel = exchange.cancel_order(plan.symbol, order_id)
        base["formal_status"] = "smoke_ok"
        base["order_submitted"] = True
        base["order_id"] = order_id
        base["order_status"] = getattr(order, "status", None)
        base["limit_price"] = price
        base["qty"] = qty
        base["cancel_response"] = cancel
    except Exception as exc:
        base["formal_status"] = "fail"
        base["error"] = str(exc)
        _write(report_path, base)
        return base

    _write(report_path, base)
    return base


def _write(path: Path | None, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

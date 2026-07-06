from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from config import BacktestConfig
from exchange import DryRunExchange
from risk_manager import RiskManager
from state_db import ReconcileResult, StateDB
from strategy import Signal

if TYPE_CHECKING:
    from market import FeatureBar


@dataclass(frozen=True)
class ExecutionRequest:
    symbol: str
    direction: int
    price: float
    qty: float
    notional: float
    margin: float
    leverage: float
    signal_reason: str = ""
    regime: str = ""
    stop_loss: float | None = None
    take_profit: float | None = None

    @classmethod
    def from_signal(
        cls,
        signal: Signal,
        price: float,
        notional: float,
        margin: float,
        leverage: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> ExecutionRequest:
        qty = notional / price if price > 0 else 0.0
        return cls(
            symbol=signal.symbol,
            direction=signal.direction,
            price=price,
            qty=qty,
            notional=notional,
            margin=margin,
            leverage=leverage,
            signal_reason=signal.reason,
            regime=signal.regime,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )


@dataclass
class ExecutionResult:
    accepted: bool = False
    status: str = ""
    reason: str = ""
    order_id: str | None = None
    position_id: str | None = None
    fill_price: float | None = None
    fill_qty: float | None = None
    success: bool | None = None
    symbol: str = ""
    direction: str = ""
    notional: float = 0.0
    margin: float = 0.0
    error: str = ""
    risk_decision: str = ""

    def __post_init__(self) -> None:
        if self.success is None:
            self.success = self.accepted
        else:
            self.accepted = self.success
        if self.error and not self.reason:
            self.reason = self.error


@dataclass
class SyncResult:
    consistent: bool = True
    local_only: list[dict] | None = None
    exchange_only: list[dict] | None = None
    matches: list[dict] | None = None
    details: str = ""

    @property
    def local_only_count(self) -> int:
        return len(self.local_only or [])

    @property
    def exchange_only_count(self) -> int:
        return len(self.exchange_only or [])


@dataclass(frozen=True)
class PositionAction:
    position_id: str
    symbol: str
    direction: str
    reason: str
    exit_price: float
    pnl: float


class Executor:
    """Executes risk-approved signals through an exchange and persists state."""

    def __init__(
        self,
        exchange: DryRunExchange,
        risk_manager: RiskManager,
        state_db: StateDB,
        config: BacktestConfig,
        dry_run: bool = False,
    ) -> None:
        self.exchange = exchange
        self.risk_manager = risk_manager
        self.state_db = state_db
        self.config = config
        self.dry_run = dry_run

    def execute_signal(
        self,
        request: ExecutionRequest | Signal,
        equity: float | None = None,
        current_step: int = 0,
        bars: list[FeatureBar] | None = None,
        idx: int = 0,
    ) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            return self._execute_signal_object(request, bars or [], idx)
        if equity is None:
            equity = 0.0
        bars = bars or []
        current_margin = sum(position["margin"] for position in self.state_db.get_open_positions())
        decision = self.risk_manager.check_order(
            request.symbol,
            request.direction,
            request.notional,
            request.margin,
            equity,
            current_step,
            bars,
            idx,
            current_positions_margin=current_margin,
            current_positions_count=len(self.state_db.get_open_positions()),
        )
        if not decision.allowed:
            self.state_db.save_risk_event(
                "reject",
                {
                    "symbol": request.symbol,
                    "direction": _direction_label(request.direction),
                    "reason": decision.reason,
                    "signal_reason": request.signal_reason,
                },
            )
            return ExecutionResult(False, "rejected", decision.reason)

        direction = _direction_label(request.direction)
        fee = request.notional * self.config.taker_fee
        order_id = self.state_db.save_order(
            request.symbol,
            direction,
            request.qty,
            price=request.price,
            signal_reason=request.signal_reason,
            risk_decision="allowed",
            meta={"regime": request.regime, "notional": request.notional, "margin": request.margin},
        )
        fill = self.exchange.place_order(
            request.symbol,
            direction,
            request.qty,
            order_type="market",
            price=request.price,
            fee=fee,
        )
        self.state_db.update_order_status(
            order_id,
            fill.status,
            fill_price=fill.fill_price,
            fill_qty=fill.fill_qty,
            fee=fill.fee,
            exchange_order_id=fill.order_id,
        )
        if fill.status != "filled":
            accepted = fill.status in ("live", "pending", "partially_filled")
            return ExecutionResult(accepted, fill.status, fill.reason, order_id=order_id)

        position_id = self.state_db.save_position(
            request.symbol,
            direction,
            entry_price=fill.fill_price if fill.fill_price is not None else request.price,
            qty=fill.fill_qty if fill.fill_qty is not None else request.qty,
            notional=request.notional,
            margin=request.margin,
            leverage=request.leverage,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
        )
        self.risk_manager._track_open(request.symbol, request.margin)
        return ExecutionResult(
            True,
            "filled",
            order_id=order_id,
            position_id=position_id,
            fill_price=fill.fill_price,
            fill_qty=fill.fill_qty,
        )

    def sync_state(self, current_step: int = 0) -> SyncResult:
        reconciliation = self.state_db.reconcile_positions(self.exchange.get_positions())
        result = _sync_result_from_reconcile(reconciliation)
        if not result.consistent:
            self.state_db.save_risk_event(
                "position_inconsistency",
                {
                    "local_only": result.local_only,
                    "exchange_only": result.exchange_only,
                    "matches": result.matches,
                },
            )
            if self.config.rm_pause_on_inconsistency:
                self.risk_manager.pause("position_inconsistency", current_step)
        return result

    def manage_positions(self, current_prices: dict[str, float], current_step: int) -> list[PositionAction]:
        actions: list[PositionAction] = []
        for position in self.state_db.get_open_positions():
            symbol = position["symbol"]
            current_price = current_prices.get(symbol)
            if current_price is None:
                continue
            exit_reason = _exit_reason_for_position(position, current_price)
            if exit_reason is None:
                continue
            direction = position["direction"]
            qty = position["qty"]
            notional = position["notional"]
            fee = notional * self.config.taker_fee
            fill = self.exchange.close_position(symbol, direction, qty, current_price, fee=fee)
            exit_price = fill.fill_price if fill.fill_price is not None else current_price
            pnl = _pnl_for_position(position, exit_price) - fee
            entry_price = position["entry_price"]
            pnl_pct = pnl / position["margin"] * 100.0 if position["margin"] else 0.0
            self.state_db.close_position(position["id"])
            self.state_db.save_trade(
                symbol=symbol,
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_time=position["opened_at"],
                exit_time=position["updated_at"],
                pnl=round(pnl, 8),
                pnl_pct=round(pnl_pct, 4),
                exit_reason=exit_reason,
            )
            self.risk_manager.on_trade_close(pnl, current_step, symbol=symbol, margin=position["margin"])
            actions.append(
                PositionAction(
                    position_id=position["id"],
                    symbol=symbol,
                    direction=direction,
                    reason=exit_reason,
                    exit_price=exit_price,
                    pnl=pnl,
                )
            )
        return actions

    def _execute_signal_object(self, signal: Signal, bars: list[FeatureBar], idx: int) -> ExecutionResult:
        symbol = signal.symbol
        try:
            ticker = self.exchange.get_ticker(symbol)
            current_price = ticker.last
            account = self.exchange.get_account_balance()
            equity = getattr(account, "equity", 0.0) or getattr(account, "total_equity", 0.0)
        except Exception as exc:
            return ExecutionResult(False, "error", error=str(exc), symbol=symbol)

        leverage = 1.0
        risk = self.config.leverage_caps.get(symbol)
        if risk is not None:
            leverage = min(float(risk.max_leverage), 10.0)
        notional = equity * self.config.risk_per_trade * leverage
        margin = notional / leverage if leverage else notional
        decision = self.risk_manager.check_order(
            symbol,
            signal.direction,
            notional,
            margin,
            equity,
            idx,
            bars,
            idx,
        )
        if not decision.allowed:
            return ExecutionResult(
                False,
                "rejected",
                error=f"Risk rejected: {decision.reason}",
                symbol=symbol,
                risk_decision=decision.reason,
            )

        direction = "long" if signal.direction > 0 else "short"
        if self.dry_run:
            return ExecutionResult(
                True,
                "dry_run",
                symbol=symbol,
                direction=direction,
                notional=notional,
                margin=margin,
                fill_price=current_price,
                risk_decision=decision.reason,
            )

        qty = notional / current_price if current_price > 0 else 0.0
        fill = self.exchange.place_order(symbol, direction, qty, order_type="market", price=current_price)
        order_id = ""
        if self.state_db is not None:
            order_id = self.state_db.save_order(
                symbol,
                direction,
                qty,
                price=current_price,
                signal_reason=getattr(signal, "reason", ""),
                risk_decision=decision.reason,
            )
        accepted = bool(getattr(fill, "success", False) or getattr(fill, "status", "") in ("filled", "live", "pending"))
        return ExecutionResult(
            accepted,
            getattr(fill, "status", "live" if accepted else "failed"),
            order_id=getattr(fill, "order_id", "") or order_id,
            symbol=symbol,
            direction=direction,
            notional=notional,
            margin=margin,
            fill_price=current_price,
            error=getattr(fill, "error_message", ""),
            risk_decision=decision.reason,
        )


def _direction_label(direction: int) -> str:
    return "long" if direction > 0 else "short"


def _sync_result_from_reconcile(reconciliation: ReconcileResult) -> SyncResult:
    return SyncResult(
        consistent=reconciliation.consistent,
        local_only=reconciliation.local_only,
        exchange_only=reconciliation.exchange_only,
        matches=reconciliation.matches,
    )


def _exit_reason_for_position(position: dict, current_price: float) -> str | None:
    direction = position["direction"]
    stop_loss = position["stop_loss"]
    take_profit = position["take_profit"]
    if direction == "long":
        if take_profit is not None and current_price >= take_profit:
            return "take_profit"
        if stop_loss is not None and current_price <= stop_loss:
            return "stop_loss"
    else:
        if take_profit is not None and current_price <= take_profit:
            return "take_profit"
        if stop_loss is not None and current_price >= stop_loss:
            return "stop_loss"
    return None


def _pnl_for_position(position: dict, exit_price: float) -> float:
    entry_price = position["entry_price"]
    notional = position["notional"]
    if entry_price <= 0:
        return 0.0
    if position["direction"] == "long":
        return (exit_price - entry_price) / entry_price * notional
    return (entry_price - exit_price) / entry_price * notional

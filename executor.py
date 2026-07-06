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

        entry_price = fill.fill_price if fill.fill_price is not None else request.price
        trail = request.stop_loss  # initialize trail at stop loss level
        position_id = self.state_db.save_position(
            request.symbol,
            direction,
            entry_price=entry_price,
            qty=fill.fill_qty if fill.fill_qty is not None else request.qty,
            notional=request.notional,
            margin=request.margin,
            leverage=request.leverage,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            trail=trail,
            signal_reason=request.signal_reason,
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

    def manage_positions(
        self,
        current_prices: dict[str, float],
        current_step: int,
        bars_by_symbol: dict[str, list] | None = None,
    ) -> list[PositionAction]:
        bars_by_symbol = bars_by_symbol or {}
        actions: list[PositionAction] = []
        for position in self.state_db.get_open_positions():
            symbol = position["symbol"]
            current_price = current_prices.get(symbol)
            if current_price is None:
                continue
            bars = bars_by_symbol.get(symbol)
            exit_reason, new_trail = _exit_reason_for_position(
                position, current_price, bars, self.config,
            )
            if new_trail is not None and new_trail != position.get("trail"):
                self.state_db.update_position_trail(position["id"], new_trail)
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


def _trailing_params_for_reason(reason: str, config: BacktestConfig) -> tuple[float, int]:
    """Return (trailing_atr, max_hold_bars) for a signal reason."""
    if reason.startswith("attack_"):
        return config.attack_trailing_atr, config.attack_max_hold_bars
    if reason.startswith("micro_momentum_"):
        return config.micro_momentum_trailing_atr, config.micro_momentum_max_hold_bars
    if reason.startswith("funding_"):
        return config.funding_trailing_atr, config.funding_max_hold_bars
    if reason.startswith("open_interest_"):
        return config.open_interest_trailing_atr, config.open_interest_max_hold_bars
    if reason.startswith("continuation_"):
        return config.continuation_trailing_atr, config.continuation_max_hold_bars
    if reason.startswith("range_revert_"):
        return config.range_trailing_atr, config.range_max_hold_bars
    return config.trailing_atr, config.max_hold_bars


def _exit_reason_for_position(
    position: dict,
    current_price: float,
    bars: list | None,
    config: BacktestConfig,
) -> tuple[str | None, float | None]:
    """Return (exit_reason, new_trail). None exit_reason means stay open."""
    direction = position["direction"]
    stop_loss = position["stop_loss"]
    take_profit = position["take_profit"]
    trail = position.get("trail") or stop_loss
    reason = position.get("signal_reason", "")
    trailing_atr, max_hold_bars = _trailing_params_for_reason(reason, config)

    # Update trailing stop if we have bar data
    new_trail = trail
    if bars and len(bars) > 0:
        bar = bars[-1]
        atr = getattr(bar, "atr", 0.0) or 0.0
        entry_price = position["entry_price"]
        trail_dist = max(atr * trailing_atr, entry_price * 0.002) if atr > 0 else entry_price * 0.002
        if direction == "long":
            new_trail = max(trail, bar.close - trail_dist)
        else:
            new_trail = min(trail, bar.close + trail_dist) if trail > 0 else bar.close + trail_dist

    # Check stop / trailing stop
    if direction == "long":
        effective_stop = max(stop_loss or 0, new_trail or 0)
        if effective_stop > 0 and current_price <= effective_stop:
            return "stop_or_trail", new_trail
        if take_profit is not None and current_price >= take_profit:
            return "take_profit", new_trail
        # Time exit
        if bars and len(bars) > 0 and max_hold_bars > 0:
            bar = bars[-1]
            bars_held = _estimate_bars_held(position, bars)
            ema20 = getattr(bar, "ema20", 0.0)
            if bars_held >= max_hold_bars and ema20 > 0 and bar.close < ema20:
                return "time_exit", new_trail
    else:
        effective_stop = min(stop_loss or float("inf"), new_trail or float("inf"))
        if effective_stop < float("inf") and current_price >= effective_stop:
            return "stop_or_trail", new_trail
        if take_profit is not None and current_price <= take_profit:
            return "take_profit", new_trail
        # Time exit
        if bars and len(bars) > 0 and max_hold_bars > 0:
            bar = bars[-1]
            bars_held = _estimate_bars_held(position, bars)
            ema20 = getattr(bar, "ema20", 0.0)
            if bars_held >= max_hold_bars and ema20 > 0 and bar.close > ema20:
                return "time_exit", new_trail

    return None, new_trail


def _estimate_bars_held(position: dict, bars: list) -> int:
    """Estimate bars held from opened_at timestamp vs latest bar time."""
    opened_at = position.get("opened_at", "")
    if not opened_at or not bars:
        return 0
    # Try to match by timestamp string prefix (date part)
    latest_time = getattr(bars[-1], "time", "")
    if not latest_time:
        return 0
    # If bars have integer timestamps, compute from those
    latest_ts = getattr(bars[-1], "ts", 0)
    # Find the bar closest to opened_at
    # Simple approach: count bars from the end, assuming ~15m per bar
    # For precision, we'd need to parse opened_at and match against bar times
    # Use a heuristic: bars list is chronological, estimate position in list
    opened_prefix = opened_at[:16] if len(opened_at) >= 16 else opened_at
    for i, bar in enumerate(bars):
        bar_time = getattr(bar, "time", "")
        if bar_time and bar_time[:16] >= opened_prefix:
            return len(bars) - 1 - i
    return len(bars)  # fallback: assume held since start


def _pnl_for_position(position: dict, exit_price: float) -> float:
    entry_price = position["entry_price"]
    notional = position["notional"]
    if entry_price <= 0:
        return 0.0
    if position["direction"] == "long":
        return (exit_price - entry_price) / entry_price * notional
    return (entry_price - exit_price) / entry_price * notional

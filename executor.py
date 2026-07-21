from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from config import BacktestConfig
from exchange import DryRunExchange
from risk_manager import RiskManager
from state_db import ReconcileResult, StateDB
from strategy import Signal

if TYPE_CHECKING:
    from market import FeatureBar

logger = logging.getLogger("executor")


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

    def poll_order_fill(
        self,
        symbol: str,
        order_id: str,
        max_wait_seconds: float = 30.0,
        poll_interval: float = 2.0,
    ) -> dict | None:
        """Poll exchange for order fill status. Returns order info dict or None on timeout."""
        deadline = time.monotonic() + max_wait_seconds
        while time.monotonic() < deadline:
            try:
                result = self.exchange.get_order_status(symbol, order_id)
                data = result.get("data", [{}])
                if data:
                    status = data[0].get("state", "")
                    if status in ("filled", "canceled", "failed"):
                        return data[0]
                    if status == "partially_filled":
                        logger.info("Order %s partially filled: %s/%s",
                                    order_id, data[0].get("accFillSz", 0), data[0].get("sz", 0))
            except Exception as exc:
                logger.warning("Poll order %s failed: %s", order_id, exc)
            time.sleep(poll_interval)
        logger.warning("Order %s poll timeout after %.0fs", order_id, max_wait_seconds)
        return None

    def cancel_stale_orders(self, max_age_minutes: float = 30.0) -> list[str]:
        """Cancel live/pending orders older than max_age_minutes. Returns cancelled order IDs."""
        cancelled: list[str] = []
        active_orders = self.state_db.get_active_exchange_orders()
        now_ts = time.time() * 1000  # ms
        max_age_ms = max_age_minutes * 60 * 1000
        for order in active_orders:
            exchange_order_id = order.get("exchange_order_id", "")
            symbol = order.get("symbol", "")
            created_at = order.get("created_at", "")
            if not exchange_order_id or not symbol:
                continue
            # Estimate age from created_at if available
            try:
                created_at_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if created_at_dt.tzinfo is None:
                    created_at_dt = created_at_dt.replace(tzinfo=timezone.utc)
                created_ts = created_at_dt.timestamp() * 1000
                age_ms = now_ts - created_ts
                if age_ms < max_age_ms:
                    continue
            except (ValueError, TypeError):
                continue
            try:
                self.exchange.cancel_order(symbol, exchange_order_id)
                self.state_db.update_order_status(order["id"], "cancelled")
                cancelled.append(exchange_order_id)
                logger.info("Cancelled stale order %s for %s (age=%.0fmin)",
                            exchange_order_id, symbol, age_ms / 60000)
            except Exception as exc:
                logger.warning("Failed to cancel stale order %s: %s", exchange_order_id, exc)
        return cancelled

    def execute_pairs_signal(
        self,
        pair_key: str,
        symbol_a: str,
        symbol_b: str,
        direction_a: int,
        direction_b: int,
        notional_a: float,
        notional_b: float,
        margin: float,
        leverage: float,
        entry_z: float,
        beta: float,
        alpha: float,
        price_a: float,
        price_b: float,
        current_step: int = 0,
    ) -> ExecutionResult:
        """Executes a double-legged pairs trading signal concurrently.

        Ensures atomic execution or immediate recovery (leg-lock prevention).
        """
        fee_rate = self.config.taker_fee
        dir_a_str = "long" if direction_a == 1 else "short"
        dir_b_str = "long" if direction_b == 1 else "short"
        
        qty_a = notional_a / price_a
        qty_b = notional_b / price_b
        
        # 1. Save local order state for both legs
        order_id_a = self.state_db.save_order(
            symbol_a, dir_a_str, qty_a, price=price_a, signal_reason=f"pairs_entry_{pair_key}", risk_decision="allowed"
        )
        order_id_b = self.state_db.save_order(
            symbol_b, dir_b_str, qty_b, price=price_b, signal_reason=f"pairs_entry_{pair_key}", risk_decision="allowed"
        )
        
        # 2. Concurrently place both orders to exchange
        import concurrent.futures
        
        def place_order_safe(symbol, direction, qty, price, fee):
            try:
                return self.exchange.place_order(
                    symbol, direction, qty, order_type="market", price=price, fee=fee
                ), None
            except Exception as e:
                return None, e

        fee_a = notional_a * fee_rate
        fee_b = notional_b * fee_rate
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as th_executor:
            fut_a = th_executor.submit(place_order_safe, symbol_a, dir_a_str, qty_a, price_a, fee_a)
            fut_b = th_executor.submit(place_order_safe, symbol_b, dir_b_str, qty_b, price_b, fee_b)
            
            fill_a, err_a = fut_a.result()
            fill_b, err_b = fut_b.result()

        # 3. Handle errors and execution status
        # Update order status
        if fill_a:
            self.state_db.update_order_status(
                order_id_a, fill_a.status, fill_price=fill_a.fill_price, fill_qty=fill_a.fill_qty, fee=fill_a.fee, exchange_order_id=fill_a.order_id
            )
        else:
            self.state_db.update_order_status(order_id_a, "failed")
            
        if fill_b:
            self.state_db.update_order_status(
                order_id_b, fill_b.status, fill_price=fill_b.fill_price, fill_qty=fill_b.fill_qty, fee=fill_b.fee, exchange_order_id=fill_b.order_id
            )
        else:
            self.state_db.update_order_status(order_id_b, "failed")

        # Check for Leg-Lock: one filled, one failed
        filled_a = fill_a and fill_a.status == "filled"
        filled_b = fill_b and fill_b.status == "filled"
        
        if filled_a and not filled_b:
            logger.warning(f"Leg-lock detected: {symbol_a} filled, {symbol_b} failed ({err_b}). Reversing {symbol_a} order.")
            try:
                reverse_dir = "short" if dir_a_str == "long" else "long"
                self.exchange.place_order(symbol_a, reverse_dir, fill_a.fill_qty, order_type="market", price=fill_a.fill_price, fee=fee_a)
            except Exception as e:
                logger.critical(f"Failed to reverse leg-locked position for {symbol_a}: {e}")
                self.risk_manager.pause("pairs_leg_lock", current_step)
            return ExecutionResult(False, "failed", f"Leg-lock: {symbol_b} failed. {symbol_a} reversed.", error=str(err_b))
            
        elif filled_b and not filled_a:
            logger.warning(f"Leg-lock detected: {symbol_b} filled, {symbol_a} failed ({err_a}). Reversing {symbol_b} order.")
            try:
                reverse_dir = "short" if dir_b_str == "long" else "long"
                self.exchange.place_order(symbol_b, reverse_dir, fill_b.fill_qty, order_type="market", price=fill_b.fill_price, fee=fee_b)
            except Exception as e:
                logger.critical(f"Failed to reverse leg-locked position for {symbol_b}: {e}")
                self.risk_manager.pause("pairs_leg_lock", current_step)
            return ExecutionResult(False, "failed", f"Leg-lock: {symbol_a} failed. {symbol_b} reversed.", error=str(err_a))
            
        elif not filled_a and not filled_b:
            return ExecutionResult(False, "failed", "Both orders failed to execute.", error=str(err_a or err_b))

        # Both succeeded! Save pairs position
        entry_price_a = fill_a.fill_price if fill_a.fill_price is not None else price_a
        entry_price_b = fill_b.fill_price if fill_b.fill_price is not None else price_b
        
        pos_id = self.state_db.save_pairs_position(
            pair_key=pair_key,
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            direction_a=dir_a_str,
            direction_b=dir_b_str,
            entry_price_a=entry_price_a,
            entry_price_b=entry_price_b,
            qty_a=fill_a.fill_qty if fill_a.fill_qty is not None else qty_a,
            qty_b=fill_b.fill_qty if fill_b.fill_qty is not None else qty_b,
            notional_a=notional_a,
            notional_b=notional_b,
            margin=margin,
            leverage=leverage,
            entry_z=entry_z,
            beta=beta,
            alpha=alpha,
        )
        
        return ExecutionResult(
            True,
            "filled",
            order_id=f"{order_id_a},{order_id_b}",
            position_id=pos_id,
            fill_price=entry_price_a,
            fill_qty=qty_a,
        )

    def manage_pairs_positions(
        self,
        pairs_signals: dict[str, dict[str, Any]],
        current_prices: dict[str, float],
        current_step: int = 0,
    ) -> list[PositionAction]:
        """Manages open pairs positions, checking for mean-reversion, time stop or stop-loss exits.

        Closes both legs concurrently on exit.
        """
        import math
        from datetime import datetime, timezone

        actions = []
        fee_rate = self.config.taker_fee
        max_hold_bars = self.config.pairs_max_hold_bars
        timeframe_minutes = self.config.timeframe_minutes

        open_positions = self.state_db.get_open_pairs_positions()

        for pos in open_positions:
            pair_key = pos["pair_key"]
            s1 = pos["symbol_a"]
            s2 = pos["symbol_b"]

            sig_info = pairs_signals.get(pair_key, {})
            signal = sig_info.get("signal", "hold")

            # --- Time stop: force exit if held too long ---
            if signal != "exit" and max_hold_bars > 0:
                opened_at_str = pos.get("opened_at", "")
                if opened_at_str:
                    try:
                        opened_at = datetime.fromisoformat(opened_at_str.replace("Z", "+00:00"))
                        # If naive (no timezone info), assume UTC
                        if opened_at.tzinfo is None:
                            opened_at = opened_at.replace(tzinfo=timezone.utc)
                        now_utc = datetime.now(timezone.utc)
                        elapsed_minutes = (now_utc - opened_at).total_seconds() / 60.0
                        bars_held = math.floor(elapsed_minutes / max(timeframe_minutes, 1))
                        if bars_held >= max_hold_bars:
                            signal = "exit"
                            sig_info = dict(sig_info)
                            sig_info["_exit_reason"] = "time_stop"
                    except (ValueError, TypeError):
                        pass

            if signal != "exit":
                continue
                
            # Exit triggered! Close both legs concurrently
            dir_a = pos["direction_a"]
            dir_b = pos["direction_b"]
            qty_a = pos["qty_a"]
            qty_b = pos["qty_b"]
            
            price_a = current_prices.get(s1) or sig_info.get("price_a") or pos["entry_price_a"]
            price_b = current_prices.get(s2) or sig_info.get("price_b") or pos["entry_price_b"]
            
            import concurrent.futures
            
            def close_leg(symbol, direction, qty, price, fee):
                try:
                    return self.exchange.close_position(symbol, direction, qty, price, fee=fee), None
                except Exception as e:
                    return None, e
                    
            fee_a = qty_a * price_a * fee_rate
            fee_b = qty_b * price_b * fee_rate
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as th_executor:
                fut_a = th_executor.submit(close_leg, s1, dir_a, qty_a, price_a, fee_a)
                fut_b = th_executor.submit(close_leg, s2, dir_b, qty_b, price_b, fee_b)
                
                fill_a, err_a = fut_a.result()
                fill_b, err_b = fut_b.result()
                
            # Compute PnL
            exit_a = fill_a.fill_price if (fill_a and fill_a.fill_price is not None) else price_a
            exit_b = fill_b.fill_price if (fill_b and fill_b.fill_price is not None) else price_b
            
            if dir_a == "long":
                pnl_a = (exit_a - pos["entry_price_a"]) * qty_a
            else:
                pnl_a = (pos["entry_price_a"] - exit_a) * qty_a
                
            if dir_b == "long":
                pnl_b = (exit_b - pos["entry_price_b"]) * qty_b
            else:
                pnl_b = (pos["entry_price_b"] - exit_b) * qty_b
                
            total_fee = fee_a + fee_b
            net_pnl = pnl_a + pnl_b - total_fee
            pnl_pct = (net_pnl / pos["margin"]) * 100.0 if pos["margin"] else 0.0

            # Determine exit reason
            if sig_info.get("_exit_reason") == "time_stop":
                exit_reason = "time_stop"
            elif abs(sig_info.get("zscore", 0.0)) >= self.config.pairs_stop_z:
                exit_reason = "stop_loss"
            else:
                exit_reason = "mean_reversion"

            self.state_db.close_pairs_position(
                pos["id"],
                exit_price_a=exit_a,
                exit_price_b=exit_b,
                pnl=net_pnl,
                pnl_pct=pnl_pct,
                fee=total_fee,
                exit_reason=exit_reason,
            )
            self.risk_manager.on_trade_close(net_pnl, current_step)

            actions.append(
                PositionAction(
                    position_id=pos["id"],
                    symbol=pair_key,
                    direction=f"{dir_a}/{dir_b}",
                    reason=exit_reason,
                    exit_price=(exit_a + exit_b) / 2.0,
                    pnl=net_pnl,
                )
            )
            
        return actions


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
    if reason.startswith("trade_flow_"):
        return config.trade_flow_trailing_atr, config.trade_flow_max_hold_bars
    if reason.startswith("order_book_"):
        return config.order_book_trailing_atr, config.order_book_max_hold_bars
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

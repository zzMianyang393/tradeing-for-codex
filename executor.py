from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from config import BacktestConfig
from exchange import OKXExchange, OrderResult, PositionInfo
from risk_manager import RiskManager
from state_db import StateDB
from strategy import Signal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    success: bool = False
    order_id: str = ""
    symbol: str = ""
    direction: str = ""
    notional: float = 0.0
    margin: float = 0.0
    fill_price: float = 0.0
    error: str = ""
    risk_decision: str = ""


@dataclass
class SyncResult:
    consistent: bool = True
    local_only_count: int = 0
    exchange_only_count: int = 0
    details: str = ""


@dataclass
class PositionAction:
    symbol: str = ""
    action: str = ""  # "close" / "update_stop" / "update_trail"
    reason: str = ""
    current_price: float = 0.0
    unrealized_pnl: float = 0.0


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class Executor:
    """Bridges strategy signals to exchange execution.

    Flow: signal → risk check → order → fill → state sync → position management
    """

    def __init__(
        self,
        exchange: OKXExchange,
        risk_manager: RiskManager | None,
        state_db: StateDB | None,
        config: BacktestConfig,
        dry_run: bool = False,
    ) -> None:
        self.exchange = exchange
        self.risk_manager = risk_manager
        self.state_db = state_db
        self.config = config
        self.dry_run = dry_run
        self._open_positions: dict[str, dict] = {}  # symbol -> tracking info

    # ------------------------------------------------------------------
    # Signal execution
    # ------------------------------------------------------------------

    def execute_signal(self, signal: Signal, bars: list, idx: int) -> ExecutionResult:
        """Execute a trading signal after risk checks."""
        symbol = signal.symbol
        direction = "buy" if signal.direction > 0 else "sell"

        # 1. Get current price
        try:
            ticker = self.exchange.get_ticker(symbol)
            current_price = ticker.last
        except Exception as e:
            return ExecutionResult(success=False, symbol=symbol, error=f"Ticker error: {e}")

        # 2. Calculate position size
        try:
            account = self.exchange.get_account_balance()
            equity = account.total_equity
        except Exception as e:
            return ExecutionResult(success=False, symbol=symbol, error=f"Account error: {e}")

        # 3. Calculate notional and margin
        risk = self.config.leverage_caps.get(symbol)
        leverage = min(risk.max_leverage if risk else 10, 10)
        notional = equity * self.config.risk_per_trade * leverage
        margin = notional / leverage

        # 4. Risk check
        risk_decision = ""
        if self.risk_manager is not None:
            decision = self.risk_manager.check_order(
                symbol, signal.direction, notional, margin, equity,
                idx, bars, idx,
            )
            risk_decision = decision.reason
            if not decision.allowed:
                logger.info(f"Risk rejected {symbol}: {decision.reason}")
                return ExecutionResult(
                    success=False, symbol=symbol, direction=direction,
                    error=f"Risk rejected: {decision.reason}",
                    risk_decision=risk_decision,
                )

        # 5. Place order
        if self.dry_run:
            logger.info(f"[DRY RUN] Would place {direction} {symbol} notional={notional:.2f}")
            return ExecutionResult(
                success=True, symbol=symbol, direction=direction,
                notional=notional, margin=margin, fill_price=current_price,
                risk_decision=risk_decision,
            )

        # Calculate size (OKX uses contract size for swaps)
        # For USDT-margined linear swaps, sz is in contracts
        # Default ctVal for most contracts is 0.01 BTC equivalent
        # We need to look up the actual contract value
        ct_val = self._get_contract_value(symbol)
        size = notional / (current_price * ct_val) if current_price > 0 and ct_val > 0 else 0
        size = max(1, round(size))  # Must be at least 1 contract

        result = self.exchange.place_order(
            symbol=symbol,
            side=direction,
            size=size,
            order_type="market",
            td_mode="cross",
        )

        if not result.success:
            logger.error(f"Order failed {symbol}: {result.error_message}")
            return ExecutionResult(
                success=False, symbol=symbol, direction=direction,
                error=result.error_message, risk_decision=risk_decision,
            )

        # 6. Track position
        self._open_positions[symbol] = {
            "order_id": result.order_id,
            "direction": direction,
            "entry_price": current_price,
            "notional": notional,
            "margin": margin,
            "entry_time": time.time(),
        }

        if self.risk_manager is not None:
            self.risk_manager._track_open(symbol, margin)

        # 7. Save to state DB
        if self.state_db is not None:
            order_id = self.state_db.save_order(
                symbol=symbol,
                direction=direction,
                qty=size,
                price=current_price,
                signal_reason=signal.reason,
                risk_decision=risk_decision,
            )

        logger.info(f"Order placed: {direction} {symbol} size={size} price={current_price}")
        return ExecutionResult(
            success=True, order_id=result.order_id, symbol=symbol,
            direction=direction, notional=notional, margin=margin,
            fill_price=current_price, risk_decision=risk_decision,
        )

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def manage_positions(self, current_bars: dict[str, Any]) -> list[PositionAction]:
        """Check and manage existing positions (stops, exits, trailing)."""
        actions = []
        try:
            positions = self.exchange.get_positions()
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return actions

        for pos in positions:
            action = self._check_position_exit(pos, current_bars)
            if action is not None:
                actions.append(action)

        return actions

    def _check_position_exit(self, pos: PositionInfo, current_bars: dict) -> PositionAction | None:
        """Check if a position should be closed based on stop/take-profit/time."""
        # Get current bar for this symbol
        bar = current_bars.get(pos.symbol)
        if bar is None:
            return None

        # Time-based exit
        tracking = self._open_positions.get(pos.symbol)
        if tracking:
            bars_held = bar.get("bars_held", 0) if isinstance(bar, dict) else 0
            if bars_held >= self.config.max_hold_bars:
                return PositionAction(
                    symbol=pos.symbol,
                    action="close",
                    reason="time_exit",
                    current_price=pos.current_price,
                    unrealized_pnl=pos.unrealized_pnl,
                )

        return None

    def close_position(self, symbol: str, reason: str = "manual") -> ExecutionResult:
        """Close an open position."""
        try:
            positions = self.exchange.get_positions(symbol)
            if not positions:
                return ExecutionResult(success=False, symbol=symbol, error="No open position")

            pos = positions[0]
            close_side = "sell" if pos.direction == "long" else "buy"

            if self.dry_run:
                logger.info(f"[DRY RUN] Would close {symbol} reason={reason}")
                return ExecutionResult(
                    success=True, symbol=symbol, direction=close_side,
                    fill_price=pos.current_price,
                )

            result = self.exchange.place_order(
                symbol=symbol,
                side=close_side,
                size=pos.qty,
                order_type="market",
            )

            if result.success:
                pnl = pos.unrealized_pnl
                if self.risk_manager is not None:
                    self.risk_manager.on_trade_close(pnl, 0, symbol, pos.margin)
                    self.risk_manager._track_close(symbol)

                if self.state_db is not None:
                    self.state_db.close_position(
                        self._open_positions.get(symbol, {}).get("order_id", "")
                    )

                self._open_positions.pop(symbol, None)
                logger.info(f"Position closed: {symbol} reason={reason} pnl={pnl:.4f}")

            return ExecutionResult(
                success=result.success, order_id=result.order_id,
                symbol=symbol, direction=close_side, fill_price=pos.current_price,
                error=result.error_message,
            )
        except Exception as e:
            return ExecutionResult(success=False, symbol=symbol, error=str(e))

    # ------------------------------------------------------------------
    # Contract value lookup
    # ------------------------------------------------------------------

    def _get_contract_value(self, symbol: str) -> float:
        """Get contract value (ctVal) for an instrument.

        For OKX USDT-margined linear swaps:
        - BTC-USDT-SWAP: 0.01 BTC per contract
        - ETH-USDT-SWAP: 0.1 ETH per contract
        - Most others: varies

        Returns 1.0 for spot/non-swap instruments.
        """
        # Default contract values for common symbols
        defaults = {
            "BTC-USDT-SWAP": 0.01,
            "ETH-USDT-SWAP": 0.1,
        }
        if symbol in defaults:
            return defaults[symbol]

        # Try to fetch from exchange
        try:
            data = self.exchange._request("GET", "/api/v5/public/instruments", params={
                "instType": "SWAP",
                "instId": symbol,
            })
            instruments = data.get("data", [])
            if instruments:
                return float(instruments[0].get("ctVal", 1.0))
        except Exception:
            pass

        # Default to 1.0 for unknown contracts
        return 1.0

    # ------------------------------------------------------------------
    # State sync
    # ------------------------------------------------------------------

    def sync_state(self) -> SyncResult:
        """Reconcile local state with exchange positions."""
        try:
            exchange_positions = self.exchange.get_positions()
            exchange_list = [
                {"symbol": p.symbol, "direction": p.direction}
                for p in exchange_positions
            ]

            if self.state_db is not None:
                result = self.state_db.reconcile_positions(exchange_list)
                if not result.consistent:
                    logger.warning(
                        f"Position mismatch: local_only={len(result.local_only)}, "
                        f"exchange_only={len(result.exchange_only)}"
                    )
                    # Pause risk manager on inconsistency
                    if self.risk_manager is not None:
                        self.risk_manager._is_paused = True
                        self.risk_manager._pause_reason = "position_inconsistency"

                return SyncResult(
                    consistent=result.consistent,
                    local_only_count=len(result.local_only),
                    exchange_only_count=len(result.exchange_only),
                )

            return SyncResult(consistent=True)
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return SyncResult(consistent=False, details=str(e))

    # ------------------------------------------------------------------
    # Account snapshot
    # ------------------------------------------------------------------

    def snapshot_account(self) -> dict:
        """Take an account snapshot and save to state DB."""
        try:
            account = self.exchange.get_account_balance()
            positions = self.exchange.get_positions()

            snapshot = {
                "equity": account.total_equity,
                "available_margin": account.available_balance,
                "used_margin": account.used_margin,
                "unrealized_pnl": account.unrealized_pnl,
                "open_positions": len(positions),
            }

            if self.state_db is not None:
                risk_status = ""
                if self.risk_manager is not None:
                    from dataclasses import asdict
                    risk_status = str(asdict(self.risk_manager.get_status()))

                self.state_db.snapshot_account(
                    equity=account.total_equity,
                    available_margin=account.available_balance,
                    used_margin=account.used_margin,
                    unrealized_pnl=account.unrealized_pnl,
                    open_positions=len(positions),
                    risk_status=risk_status,
                )

            return snapshot
        except Exception as e:
            logger.error(f"Snapshot failed: {e}")
            return {}

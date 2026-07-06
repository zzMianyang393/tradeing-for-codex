from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from config import BacktestConfig

if TYPE_CHECKING:
    from market import FeatureBar


@dataclass
class RiskStatus:
    is_paused: bool = False
    pause_reason: str = ""
    pause_until_step: int = -1
    daily_pnl: float = 0.0
    weekly_pnl: float = 0.0
    consecutive_losses: int = 0
    open_positions_count: int = 0
    total_margin_used: float = 0.0


@dataclass
class RiskDecision:
    allowed: bool = True
    reason: str = ""


class RiskManager:
    """Pure-logic risk controller for the backtest engine.

    Checks are evaluated in order; the first failure short-circuits and
    returns a ``RiskDecision(allowed=False, ...)``.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self.config = config
        self._daily_pnl: float = 0.0
        self._weekly_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._is_paused: bool = False
        self._pause_reason: str = ""
        self._pause_until_step: int = -1
        self._pauses_count: int = 0
        self._rejections_count: int = 0
        self._open_margins: dict[str, float] = {}
        self._last_daily_reset_step: int = 0
        self._last_weekly_reset_step: int = 0

    # ------------------------------------------------------------------
    # Internal position tracking (called by the backtester)
    # ------------------------------------------------------------------

    @property
    def _total_margin_used(self) -> float:
        return sum(self._open_margins.values())

    def _track_open(self, symbol: str, margin: float) -> None:
        self._open_margins[symbol] = margin

    def _track_close(self, symbol: str) -> None:
        self._open_margins.pop(symbol, None)

    # ------------------------------------------------------------------
    # Pause helpers
    # ------------------------------------------------------------------

    def _activate_pause(self, reason: str, current_step: int) -> None:
        self._is_paused = True
        self._pause_reason = reason
        self._pause_until_step = current_step + self.config.rm_consecutive_loss_pause_bars
        self._pauses_count += 1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all state for a new backtest window."""
        self._daily_pnl = 0.0
        self._weekly_pnl = 0.0
        self._consecutive_losses = 0
        self._is_paused = False
        self._pause_reason = ""
        self._pause_until_step = -1
        self._pauses_count = 0
        self._rejections_count = 0
        self._open_margins.clear()
        self._last_daily_reset_step = 0
        self._last_weekly_reset_step = 0

    def check_order(
        self,
        symbol: str,
        direction: int,
        notional: float,
        margin: float,
        equity: float,
        current_step: int,
        bars: list[FeatureBar],
        idx: int,
        current_positions_margin: float = 0.0,
        current_positions_count: int = 0,
    ) -> RiskDecision:
        """Evaluate all risk rules for a proposed order.

        Returns ``RiskDecision(allowed=True)`` when the order may proceed,
        otherwise ``RiskDecision(allowed=False, reason=...)``.
        """
        # Master switch – when disabled, skip every check
        if not self.config.rm_enabled:
            return RiskDecision(True, "")

        # 1. Pause check
        if self._is_paused and current_step < self._pause_until_step:
            self._rejections_count += 1
            return RiskDecision(False, f"paused: {self._pause_reason}")

        # Clear expired pause
        if self._is_paused and current_step >= self._pause_until_step:
            self._is_paused = False
            self._pause_reason = ""

        # 2. Single-position limit
        if equity > 0:
            single_pct = notional / equity
            if single_pct > self.config.rm_max_single_position_pct:
                self._rejections_count += 1
                return RiskDecision(
                    False,
                    f"single position {single_pct:.4f} > {self.config.rm_max_single_position_pct}",
                )

        # 3. Total-position limit
        if equity > 0:
            used_margin = current_positions_margin if current_positions_margin > 0 else self._total_margin_used
            total_pct = (used_margin + margin) / equity
            if total_pct > self.config.rm_max_total_position_pct:
                self._rejections_count += 1
                return RiskDecision(
                    False,
                    f"total position {total_pct:.4f} > {self.config.rm_max_total_position_pct}",
                )

        # 4. Daily loss limit (only when losing)
        if self._daily_pnl < 0 and equity > 0:
            daily_loss_pct = abs(self._daily_pnl) / equity * 100.0
            if daily_loss_pct > self.config.rm_max_daily_loss_pct:
                self._rejections_count += 1
                return RiskDecision(
                    False,
                    f"daily loss {daily_loss_pct:.2f}% > {self.config.rm_max_daily_loss_pct}%",
                )

        # 5. Weekly loss limit (only when losing)
        if self._weekly_pnl < 0 and equity > 0:
            weekly_loss_pct = abs(self._weekly_pnl) / equity * 100.0
            if weekly_loss_pct > self.config.rm_max_weekly_loss_pct:
                self._rejections_count += 1
                return RiskDecision(
                    False,
                    f"weekly loss {weekly_loss_pct:.2f}% > {self.config.rm_max_weekly_loss_pct}%",
                )

        # 6. Consecutive-loss pause
        if self._consecutive_losses >= self.config.rm_consecutive_loss_pause:
            self._activate_pause("consecutive_losses", current_step)
            self._rejections_count += 1
            return RiskDecision(
                False,
                f"consecutive losses {self._consecutive_losses} >= {self.config.rm_consecutive_loss_pause}",
            )

        # 7. Volatility halt
        if 0 <= idx < len(bars):
            bar = bars[idx]
            if bar.atr_pct > self.config.rm_volatility_halt_threshold:
                self._activate_pause("volatility", current_step)
                self._rejections_count += 1
                return RiskDecision(
                    False,
                    f"volatility {bar.atr_pct:.4f} > {self.config.rm_volatility_halt_threshold}",
                )

        # 8. Liquidation-distance protection
        if notional > 0 and margin > 0:
            liq_distance = margin / notional
            if liq_distance < self.config.rm_min_liquidation_distance_pct:
                self._rejections_count += 1
                return RiskDecision(
                    False,
                    f"liquidation distance {liq_distance:.4f} < {self.config.rm_min_liquidation_distance_pct}",
                )

        return RiskDecision(True, "")

    def on_trade_close(
        self,
        pnl: float,
        current_step: int,
        symbol: str = "",
        margin: float = 0.0,
    ) -> None:
        """Update risk state after a position is closed."""
        if symbol:
            self._open_margins.pop(symbol, None)

        # Reset daily PnL every 96 steps (~1 day for 15m bars)
        if current_step - self._last_daily_reset_step >= 96:
            self._daily_pnl = 0.0
            self._last_daily_reset_step = current_step

        # Reset weekly PnL every 672 steps (~1 week for 15m bars)
        if current_step - self._last_weekly_reset_step >= 672:
            self._weekly_pnl = 0.0
            self._last_weekly_reset_step = current_step

        self._daily_pnl += pnl
        self._weekly_pnl += pnl
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def get_status(self) -> RiskStatus:
        return RiskStatus(
            is_paused=self._is_paused,
            pause_reason=self._pause_reason,
            pause_until_step=self._pause_until_step,
            daily_pnl=self._daily_pnl,
            weekly_pnl=self._weekly_pnl,
            consecutive_losses=self._consecutive_losses,
            open_positions_count=len(self._open_margins),
            total_margin_used=self._total_margin_used,
        )

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field, replace
from typing import Any
from pathlib import Path

from config import BacktestConfig
from exchange import DryRunExchange, ExchangeError, OKXExchange
from executor import ExecutionRequest, Executor
from health_report import HealthAlertTracker, HealthReport, build_health_report
from market import FeatureBar, load_market
from notifier import NotificationResult, Notifier, create_notifier_from_env
from portfolio import PortfolioConfig, select_portfolio_signals
from risk_manager import RiskManager
from state_db import StateDB
from strategy import Signal, generate_all_signals

logger = logging.getLogger("runner")


@dataclass(frozen=True)
class RunInput:
    equity: float
    current_step: int
    current_prices: dict[str, float]
    bars_by_symbol: dict[str, list]
    signal_requests: list[ExecutionRequest] = field(default_factory=list)


@dataclass(frozen=True)
class RunReport:
    executed_orders: int = 0
    rejected_orders: int = 0
    closed_positions: int = 0
    open_positions: int = 0
    sync_consistent: bool = True
    risk_status: dict | str = field(default_factory=dict)
    timestamp: str = ""
    equity: float = 0.0
    signals_generated: int = 0
    orders_placed: int = 0
    orders_rejected: int = 0
    errors: list[str] | None = None


@dataclass(frozen=True)
class _RiskBar:
    atr_pct: float = 0.0


class TradingRunner:
    """One-cycle dry-run trading orchestrator.

    The runner intentionally delegates execution details to ``Executor`` so the
    same cycle can later be wired to a real exchange adapter.
    """

    def __init__(
        self,
        config: BacktestConfig,
        executor: Executor,
        state_db: StateDB | None = None,
        exchange: DryRunExchange | OKXExchange | None = None,
        symbols: list[str] | None = None,
        dry_run: bool = False,
        data_dir: Path | None = None,
        pairs: list[str] | None = None,
    ) -> None:
        self.config = config
        self.executor = executor
        self.state_db = state_db
        self.exchange = exchange if exchange is not None else executor.exchange
        self.symbols = symbols or []
        self.dry_run = dry_run
        self.data_dir = data_dir
        self.pairs = pairs or []
        self._market: dict[str, list[FeatureBar]] = {}
        self._step = 0
        from pairs_signal import PairsSignalGenerator
        self.pairs_generator = PairsSignalGenerator(self.config)

    def load_market_data(self) -> dict[str, list[FeatureBar]]:
        """Load or reload market data from the data directory."""
        if self.data_dir is None:
            return {}
        market = load_market(
            self.data_dir,
            self.config.timeframe_minutes,
            include_funding=getattr(self.config, "enable_funding_module", False),
            include_open_interest=getattr(self.config, "enable_open_interest_module", False),
            include_trade_flow=getattr(self.config, "enable_trade_flow_module", False),
            include_order_book=getattr(self.config, "enable_order_book_module", False),
        )
        # Filter to selected symbols if specified
        if self.symbols:
            market = {s: bars for s, bars in market.items() if s in self.symbols}
        self._market = market
        return market

    def _select_active_symbols(self, market: dict[str, list[FeatureBar]]) -> list[str]:
        """Select top symbols for the current cycle."""
        from backtester import select_symbols
        if not market:
            return []
        # Use the latest timestamp from the data
        all_ts = set()
        for bars in market.values():
            if bars:
                all_ts.add(bars[-1].ts)
        if not all_ts:
            return []
        end_ts = max(all_ts)
        limit = self.config.active_symbol_limit
        if self.symbols:
            # If user specified symbols, use those (up to limit)
            return self.symbols[:limit]
        return select_symbols(market, end_ts, limit=limit, config=self.config)

    def _get_current_prices(self, market: dict[str, list[FeatureBar]], symbols: list[str]) -> dict[str, float]:
        """Extract latest close prices for active symbols."""
        prices = {}
        for symbol in symbols:
            bars = market.get(symbol)
            if bars:
                prices[symbol] = bars[-1].close
        return prices

    def _generate_signals(
        self, market: dict[str, list[FeatureBar]], symbols: list[str]
    ) -> list[Signal]:
        """Generate all strategy signals for active symbols."""
        signals: list[Signal] = []
        min_score = self.config.min_score
        enabled_regimes = set(self.config.enabled_regimes) if self.config.enabled_regimes else None
        for symbol in symbols:
            bars = market.get(symbol)
            if not bars or len(bars) < 260:
                continue
            idx = len(bars) - 1
            for sig in generate_all_signals(symbol, bars, idx, self.config):
                if sig.score < min_score:
                    continue
                if enabled_regimes and sig.regime not in enabled_regimes:
                    continue
                signals.append(sig)
        # Sort by score descending — best signals first
        decisions = select_portfolio_signals(signals, PortfolioConfig(max_signals=self.config.max_positions))
        return [decision.signal for decision in decisions]

    def _size_and_execute_signal(
        self, sig: Signal, market: dict[str, list[FeatureBar]], equity: float, current_step: int
    ) -> ExecutionResult | None:
        """Size a signal and execute it through the executor."""
        bars = market.get(sig.symbol)
        if not bars:
            return None
        bar = bars[-1]
        risk = self.config.leverage_caps.get(sig.symbol)
        leverage_cap = risk.max_leverage if risk else 10.0
        leverage = min(leverage_cap, max(2.0, 1.0 / max(bar.atr_pct * 3.4, 0.02)))
        entry = bar.close

        # Determine stop/take-profit from signal reason
        stop_atr, take_profit_atr = _stop_tp_for_signal(sig, self.config)
        risk_per_trade = _risk_per_trade_for_signal(sig, self.config)
        if equity < self.config.start_equity * self.config.defensive_equity_fraction:
            risk_per_trade *= self.config.defensive_risk_multiplier
        if equity > self.config.start_equity * self.config.profit_lock_equity_fraction:
            risk_per_trade *= self.config.profit_lock_risk_multiplier

        stop_dist = max(bar.atr * stop_atr, entry * 0.0025)
        symbol_risk_mult = self.config.symbol_risk_multipliers.get(sig.symbol, 1.0)
        reason_risk_mult = self.config.reason_risk_multipliers.get(sig.reason, 1.0)
        score_factor = min(1.25, sig.score / 2.6)
        risk_amount = equity * risk_per_trade * symbol_risk_mult * reason_risk_mult * score_factor
        notional_by_risk = risk_amount / (stop_dist / entry) if stop_dist > 0 else 0.0

        open_positions = self.state_db.get_open_positions() if self.state_db else []
        used_margin = sum(p["margin"] for p in open_positions)
        free_margin = max(0.0, equity * self.config.max_total_margin_fraction - used_margin)
        margin_cap = min(equity * self.config.max_margin_fraction, free_margin)
        notional = min(notional_by_risk, margin_cap * leverage)

        min_notional = risk.min_notional if risk else 5.0
        if notional < min_notional:
            return None

        margin = notional / leverage
        stop_loss = entry - sig.direction * stop_dist
        take_profit = entry + sig.direction * max(bar.atr * take_profit_atr, entry * 0.0022)

        request = ExecutionRequest.from_signal(
            sig,
            price=entry,
            notional=notional,
            margin=margin,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        return self.executor.execute_signal(
            request,
            equity=equity,
            current_step=current_step,
            bars=bars,
            idx=len(bars) - 1,
        )

    def _run_pairs_trading_cycle(self, equity: float) -> tuple[int, int, int]:
        """Runs the pairs trading cycle for this step: manages positions, checks signals, and executes entries.

        Returns (executed_orders, rejected_orders, closed_positions_count).
        """
        if not self.config.enable_pairs_trading or not self.state_db:
            return 0, 0, 0

        # 1. Gather current price of all assets in our pairs
        unique_coins = set()
        for pair in self.pairs:
            parts = pair.split("-")
            if len(parts) == 2:
                unique_coins.add(parts[0])
                unique_coins.add(parts[1])

        # Get current prices for these coins from market data if available, or fetch from exchange
        current_prices = {}
        for coin in unique_coins:
            symbol = f"{coin}-USDT-SWAP"
            # Try to get from self._market
            if symbol in self._market and self._market[symbol]:
                current_prices[symbol] = self._market[symbol][-1].close
            else:
                try:
                    current_prices[symbol] = self.exchange.get_ticker(symbol).last
                except Exception:
                    current_prices[symbol] = 1.0

        # 2. Check and generate signals for all candidate pairs
        pairs_signals = {}
        for pair in self.pairs:
            parts = pair.split("-")
            if len(parts) != 2:
                continue
            coin_a, coin_b = parts[0], parts[1]
            s1 = f"{coin_a}-USDT-SWAP"
            s2 = f"{coin_b}-USDT-SWAP"

            # Check if there is an open position for this pair
            open_pos = None
            for pos in self.state_db.get_open_pairs_positions():
                if pos["pair_key"] == pair:
                    open_pos = pos
                    break

            current_pos_dir = 0
            if open_pos:
                current_pos_dir = 1 if open_pos["direction_a"] == "long" else -1

            try:
                # Data synchronization is an explicit background concern, not
                # a latency-sensitive order-management operation.
                sig_res = self.pairs_generator.get_latest_zscore(s1, s2, sync=False)
                
                # Derive signal using z-score
                z = sig_res["zscore"]
                entry_z = self.config.pairs_entry_z
                exit_z = self.config.pairs_exit_z
                stop_z = self.config.pairs_stop_z
                
                signal = "hold"
                if current_pos_dir == 0:
                    if z > entry_z and z < stop_z:
                        signal = "entry_short"
                    elif z < -entry_z and z > -stop_z:
                        signal = "entry_long"
                else:
                    should_exit = False
                    if abs(z) >= stop_z:
                        should_exit = True
                    elif current_pos_dir == 1 and z >= exit_z:
                        should_exit = True
                    elif current_pos_dir == -1 and z <= -exit_z:
                        should_exit = True
                    if should_exit:
                        signal = "exit"
                
                sig_res["signal"] = signal
                pairs_signals[pair] = sig_res
            except Exception as e:
                logger.error(f"Error checking signal for pair {pair}: {e}")

        # 3. Manage existing pairs positions (exits)
        closed_actions = self.executor.manage_pairs_positions(pairs_signals, current_prices, current_step=self._step)
        for action in closed_actions:
            logger.info(
                "Pairs Position closed: %s legs=%s reason=%s pnl=%.4f",
                action.symbol, action.direction, action.reason, action.pnl,
            )

        # 4. Check entry signals for non-open pairs
        open_pairs = {pos["pair_key"] for pos in self.state_db.get_open_pairs_positions()}
        max_active = self.config.pairs_max_active
        allocation_fraction = self.config.pairs_allocation_fraction

        executed_orders = 0
        rejected_orders = 0

        # Filter entry signals
        entry_candidates = []
        for pair, sig_info in pairs_signals.items():
            if pair in open_pairs:
                continue
            signal = sig_info.get("signal", "hold")
            if signal in ("entry_long", "entry_short"):
                entry_candidates.append((pair, sig_info))

        if entry_candidates:
            # Sort by Z-score absolute value descending
            entry_candidates.sort(key=lambda x: abs(x[1]["zscore"]), reverse=True)

            for pair, sig_info in entry_candidates:
                current_open_count = len(self.state_db.get_open_pairs_positions())
                if current_open_count >= max_active:
                    logger.info(f"Pairs portfolio full: {current_open_count}/{max_active} active pairs. Skipping {pair}.")
                    break

                normal_margin = sum(p["margin"] for p in self.state_db.get_open_positions())
                pairs_margin = sum(p["margin"] for p in self.state_db.get_open_pairs_positions())
                pair_margin = equity * allocation_fraction
                if normal_margin + pairs_margin + pair_margin > equity * self.config.max_total_margin_fraction:
                    rejected_orders += 1
                    logger.info("Pairs entry rejected: %s exceeds portfolio margin limit.", pair)
                    continue
                parts = pair.split("-")
                s1 = f"{parts[0]}-USDT-SWAP"
                s2 = f"{parts[1]}-USDT-SWAP"
                
                risk_a = self.config.leverage_caps.get(s1)
                risk_b = self.config.leverage_caps.get(s2)
                leverage_a = min(float(risk_a.max_leverage), 10.0) if risk_a else 10.0
                leverage_b = min(float(risk_b.max_leverage), 10.0) if risk_b else 10.0
                leverage = min(leverage_a, leverage_b)

                # The log-spread is log(A) - beta * log(B), so beta must
                # determine the two dollar legs.  ``pair_margin * leverage``
                # is total gross exposure, not exposure per leg.
                beta_abs = abs(float(sig_info["beta"]))
                gross_notional = pair_margin * leverage
                notional_a = gross_notional / (1.0 + beta_abs)
                notional_b = gross_notional - notional_a

                direction_a = 1 if sig_info["signal"] == "entry_long" else -1
                direction_b = -direction_a

                latest_bar = (self._market.get(s1) or [_RiskBar()])[-1]
                atr_pct = getattr(latest_bar, "atr_pct", 0.0)
                risk_bar = _RiskBar(atr_pct=float(atr_pct) if isinstance(atr_pct, (int, float)) else 0.0)
                decision = self.executor.risk_manager.check_order(
                    pair,
                    direction_a,
                    notional_a + notional_b,
                    pair_margin,
                    equity,
                    self._step,
                    [risk_bar],
                    0,
                    current_positions_margin=normal_margin + pairs_margin,
                    current_positions_count=len(self.state_db.get_open_positions()) + current_open_count,
                )
                if not decision.allowed:
                    rejected_orders += 1
                    logger.info("Pairs entry rejected: %s risk=%s", pair, decision.reason)
                    continue

                res = self.executor.execute_pairs_signal(
                    pair_key=pair,
                    symbol_a=s1,
                    symbol_b=s2,
                    direction_a=direction_a,
                    direction_b=direction_b,
                    notional_a=notional_a,
                    notional_b=notional_b,
                    margin=pair_margin,
                    leverage=leverage,
                    entry_z=sig_info["zscore"],
                    beta=sig_info["beta"],
                    alpha=sig_info["alpha"],
                    price_a=sig_info["price_a"],
                    price_b=sig_info["price_b"],
                    current_step=self._step,
                )

                if res.accepted:
                    executed_orders += 1
                    logger.info(
                        "Pairs entry executed: %s direction=%s zscore=%.2f",
                        pair, sig_info["signal"], sig_info["zscore"]
                    )
                else:
                    rejected_orders += 1
                    logger.info(
                        "Pairs entry rejected: %s reason=%s",
                        pair, res.reason
                    )

        return executed_orders, rejected_orders, len(closed_actions)

    def run_once(self, run_input: RunInput | None = None) -> RunReport:
        """Run one trading cycle: load data, manage positions, generate signals, execute."""
        if run_input is not None:
            return self._run_once_with_input(run_input)

        # Real trading cycle
        market = self._market or self.load_market_data()
        if not market:
            account = self.exchange.get_account_balance()
            return RunReport(
                equity=getattr(account, "equity", 0.0) or getattr(account, "total_equity", 0.0),
                errors=["No market data loaded. Use --data to specify data directory."],
            )

        active_symbols = self._select_active_symbols(market)
        current_prices = self._get_current_prices(market, active_symbols)

        # Get account equity
        account = self.exchange.get_account_balance()
        equity = getattr(account, "equity", 0.0) or getattr(account, "total_equity", 0.0)
        if self.state_db:
            open_positions = self.state_db.get_open_positions()
            open_pairs_positions = self.state_db.get_open_pairs_positions()
            used_margin = sum(p["margin"] for p in open_positions) + sum(p["margin"] for p in open_pairs_positions)
        else:
            open_positions = []
            open_pairs_positions = []
            used_margin = 0.0

        # Manage existing positions (stop/trail/time exit)
        closed = self.executor.manage_positions(
            current_prices, self._step, bars_by_symbol=market,
        )
        for action in closed:
            logger.info(
                "Position closed: %s %s reason=%s pnl=%.4f",
                action.symbol, action.direction, action.reason, action.pnl,
            )

        # Generate signals
        signals = self._generate_signals(market, active_symbols) if self.config.enable_rule_trading else []

        # Filter out symbols already in position
        open_symbols = {p["symbol"] for p in open_positions}
        signals = [s for s in signals if s.symbol not in open_symbols]

        # Check available slots
        max_positions = self.config.max_positions
        available_slots = max(0, max_positions - len(open_positions))

        # Execute top signals
        executed_orders = 0
        rejected_orders = 0
        for sig in signals[:available_slots]:
            result = self._size_and_execute_signal(sig, market, equity, self._step)
            if result is None:
                continue
            if result.accepted:
                executed_orders += 1
                logger.info(
                    "Signal executed: %s %s score=%.2f reason=%s",
                    sig.symbol, "long" if sig.direction > 0 else "short",
                    sig.score, sig.reason,
                )
            else:
                rejected_orders += 1
                logger.info(
                    "Signal rejected: %s %s reason=%s risk=%s",
                    sig.symbol, "long" if sig.direction > 0 else "short",
                    sig.reason, result.reason,
                )

        # Execute pairs trading cycle
        pairs_executed, pairs_rejected, pairs_closed = self._run_pairs_trading_cycle(equity)
        executed_orders += pairs_executed
        rejected_orders += pairs_rejected

        # Sync state
        sync_consistent = True
        if self.state_db:
            sync = self.executor.sync_state(self._step)
            sync_consistent = sync.consistent
            open_positions = self.state_db.get_open_positions()
            open_pairs_positions = self.state_db.get_open_pairs_positions()
            used_margin = sum(p["margin"] for p in open_positions) + sum(p["margin"] for p in open_pairs_positions)
            risk_status = asdict(self.executor.risk_manager.get_status())
            self.state_db.snapshot_account(
                equity=equity,
                available_margin=max(0.0, equity - used_margin),
                used_margin=used_margin,
                unrealized_pnl=0.0,
                open_positions=len(open_positions) + len(open_pairs_positions),
                risk_status=json.dumps(risk_status, ensure_ascii=False),
            )
        else:
            open_pairs_positions = []
            risk_status = {}

        self._step += 1
        return RunReport(
            executed_orders=executed_orders,
            rejected_orders=rejected_orders,
            closed_positions=len(closed) + pairs_closed,
            open_positions=len(open_positions) + len(open_pairs_positions),
            sync_consistent=sync_consistent,
            risk_status=risk_status,
            signals_generated=len(signals) + len(self.pairs),
            equity=equity,
        )

    def _run_once_with_input(self, run_input: RunInput) -> RunReport:
        """Legacy path: run with explicit RunInput (used by --once with manual data)."""
        if self.state_db is None:
            return RunReport(errors=["state_db is required for RunInput execution"])
        closed = self.executor.manage_positions(run_input.current_prices, run_input.current_step)
        executed_orders = 0
        rejected_orders = 0
        for request in run_input.signal_requests:
            bars = run_input.bars_by_symbol.get(request.symbol)
            if not bars:
                continue
            result = self.executor.execute_signal(
                request,
                equity=run_input.equity,
                current_step=run_input.current_step,
                bars=bars,
                idx=len(bars) - 1,
            )
            if result.accepted:
                executed_orders += 1
            else:
                rejected_orders += 1

        sync = self.executor.sync_state(run_input.current_step)
        open_positions = self.state_db.get_open_positions()
        used_margin = sum(position["margin"] for position in open_positions)
        risk_status = asdict(self.executor.risk_manager.get_status())
        self.state_db.snapshot_account(
            equity=run_input.equity,
            available_margin=max(0.0, run_input.equity - used_margin),
            used_margin=used_margin,
            unrealized_pnl=0.0,
            open_positions=len(open_positions),
            risk_status=json.dumps(risk_status, ensure_ascii=False),
        )
        return RunReport(
            executed_orders=executed_orders,
            rejected_orders=rejected_orders,
            closed_positions=len(closed),
            open_positions=len(open_positions),
            sync_consistent=sync.consistent,
            risk_status=risk_status,
        )

    def run_loop(self, interval_seconds: int = 900) -> None:
        """Run repeated trading cycles with real market data."""
        logger.info("Starting trading loop (interval=%ds)", interval_seconds)
        # Load market data once at start
        market = self.load_market_data()
        if not market:
            logger.error("No market data loaded. Check --data path.")
            return
        logger.info("Loaded %d symbols from %s", len(market), self.data_dir)

        cycle = 0
        while True:
            cycle += 1
            try:
                # Reload data for fresh bars
                market = self.load_market_data()
                report = self.run_once()
                logger.info(
                    "Cycle %d: signals=%d executed=%d rejected=%d closed=%d positions=%d equity=%.4f",
                    cycle,
                    report.signals_generated,
                    report.executed_orders,
                    report.rejected_orders,
                    report.closed_positions,
                    report.open_positions,
                    report.equity,
                )
            except Exception:
                logger.exception("Error in trading cycle %d", cycle)
            if interval_seconds > 0:
                time.sleep(interval_seconds)

    def stop(self) -> None:
        return None


def _stop_tp_for_signal(sig: Signal, config: BacktestConfig) -> tuple[float, float]:
    """Return (stop_atr, take_profit_atr) for a signal based on its reason prefix."""
    if sig.reason.startswith("attack_"):
        return config.attack_stop_atr, config.attack_take_profit_atr
    if sig.reason.startswith("micro_momentum_"):
        return config.micro_momentum_stop_atr, config.micro_momentum_take_profit_atr
    if sig.reason.startswith("funding_"):
        return config.funding_stop_atr, config.funding_take_profit_atr
    if sig.reason.startswith("open_interest_"):
        return config.open_interest_stop_atr, config.open_interest_take_profit_atr
    if sig.reason.startswith("trade_flow_"):
        return config.trade_flow_stop_atr, config.trade_flow_take_profit_atr
    if sig.reason.startswith("order_book_"):
        return config.order_book_stop_atr, config.order_book_take_profit_atr
    if sig.reason.startswith("continuation_"):
        return config.continuation_stop_atr, config.continuation_take_profit_atr
    if sig.reason.startswith("range_revert_"):
        return config.range_stop_atr, config.range_take_profit_atr
    return config.stop_atr, config.take_profit_atr


def _risk_per_trade_for_signal(sig: Signal, config: BacktestConfig) -> float:
    """Return risk_per_trade for a signal based on its reason prefix."""
    if sig.reason.startswith("attack_"):
        return config.attack_risk_per_trade
    if sig.reason.startswith("micro_momentum_"):
        return config.micro_momentum_risk_per_trade
    if sig.reason.startswith("funding_"):
        return config.funding_risk_per_trade
    if sig.reason.startswith("open_interest_"):
        return config.open_interest_risk_per_trade
    if sig.reason.startswith("trade_flow_"):
        return config.trade_flow_risk_per_trade
    if sig.reason.startswith("order_book_"):
        return config.order_book_risk_per_trade
    if sig.reason.startswith("continuation_"):
        return config.continuation_risk_per_trade
    return config.risk_per_trade


def _setup_logging() -> None:
    """Configure structured logging for console and file."""
    log_dir = Path("reports")
    log_dir.mkdir(exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Console handler
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    # File handler
    file_handler = logging.FileHandler(log_dir / "trades.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run trading runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="Print local account/position status as JSON")
    mode.add_argument("--once", action="store_true", help="Run one trading cycle with signal generation")
    mode.add_argument("--loop", action="store_true", help="Run repeated trading cycles with signal generation")
    mode.add_argument("--reconcile", action="store_true", help="Reconcile local positions against dry-run exchange state")
    mode.add_argument("--okx-check", action="store_true", help="Check OKX simulated account, ticker, and positions")
    mode.add_argument("--okx-smoke-order", action="store_true", help="Place then cancel one OKX simulated limit order")
    mode.add_argument("--okx-submit-signal", action="store_true", help="Submit one risk-checked signal to OKX simulated trading")
    mode.add_argument("--okx-sync-orders", action="store_true", help="Sync local live orders from OKX simulated trading")
    mode.add_argument("--okx-close-position", action="store_true", help="Submit an OKX simulated close order for a local position")
    mode.add_argument("--okx-snapshot", action="store_true", help="Write an OKX simulated runtime account snapshot")
    mode.add_argument("--okx-monitor-loop", action="store_true", help="Run finite OKX simulated sync/snapshot monitor cycles")
    mode.add_argument("--okx-health-report", action="store_true", help="Print OKX simulated health report as JSON")
    parser.add_argument("--db", type=Path, default=Path("reports") / "dry_run_state.db")
    parser.add_argument("--enable-pairs", action="store_true", help="Explicitly enable experimental pairs paper trading")
    parser.add_argument("--pairs", default="", help="Comma-separated pairs list; requires --enable-pairs")
    parser.add_argument("--enable-rule-strategies", action="store_true", help="Explicitly enable legacy single-symbol rule signals")
    parser.add_argument("--data", type=Path, default=Path("data"), help="Data directory for market data")
    parser.add_argument("--equity", type=float, default=10.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--interval", type=float, default=900.0)
    parser.add_argument("--okx-symbol", default="BTC-USDT-SWAP")
    parser.add_argument("--exchange", choices=["dry-run", "okx"], default="dry-run")
    parser.add_argument("--confirm-okx-smoke-order", action="store_true")
    parser.add_argument("--okx-smoke-direction", choices=["long", "short"], default="long")
    parser.add_argument("--okx-smoke-qty", type=float, default=0.001)
    parser.add_argument("--okx-smoke-price", type=float, default=1.0)
    parser.add_argument("--okx-smoke-notional", type=float, default=1.0)
    parser.add_argument("--okx-smoke-margin", type=float, default=1.0)
    parser.add_argument("--confirm-okx-submit-signal", action="store_true")
    parser.add_argument("--okx-signal-direction", choices=["long", "short"], default="long")
    parser.add_argument("--okx-signal-price", type=float, default=1.0)
    parser.add_argument("--okx-signal-notional", type=float, default=1.0)
    parser.add_argument("--okx-signal-margin", type=float, default=1.0)
    parser.add_argument("--okx-signal-leverage", type=float, default=1.0)
    parser.add_argument("--confirm-okx-close-position", action="store_true")
    parser.add_argument("--position-id", default="")
    parser.add_argument("--okx-close-price", type=float, default=0.0)
    parser.add_argument("--stale-order-minutes", type=int, default=30)
    args = parser.parse_args(argv)

    if args.status:
        db = StateDB(args.db)
        try:
            _print_json(_status_payload(db))
        finally:
            db.close()
        return 0

    if args.okx_check:
        payload, code = _okx_check_payload(args.okx_symbol)
        _print_json(payload)
        return code

    if args.okx_smoke_order:
        payload, code = _okx_smoke_order_payload(args)
        _print_json(payload)
        return code

    if args.okx_submit_signal:
        payload, code = _okx_submit_signal_payload(args)
        _print_json(payload)
        return code

    if args.okx_sync_orders:
        payload, code = _okx_sync_orders_payload(args.db)
        _print_json(payload)
        return code

    if args.okx_close_position:
        payload, code = _okx_close_position_payload(args)
        _print_json(payload)
        return code

    if args.okx_snapshot:
        payload, code = _okx_snapshot_payload(args.db)
        _print_json(payload)
        return code

    if args.okx_monitor_loop:
        payload, code = _okx_monitor_loop_payload(args.db, args.iterations, args.interval, args.stale_order_minutes)
        _print_json(payload)
        return code

    if args.okx_health_report:
        payload, code = _okx_health_report_payload(args.db, args.stale_order_minutes)
        _print_json(payload)
        return code

    # Research has no approved strategy at present.  Keep experimental rule and
    # pairs engines testable in isolation, but do not let the normal CLI turn
    # either into paper/live trading merely through an opt-in flag.
    if args.enable_pairs or args.enable_rule_strategies:
        _print_json(
            {
                "error": "No strategy is approved for paper or live trading.",
                "blocked_flags": [
                    name
                    for name, enabled in (
                        ("--enable-pairs", args.enable_pairs),
                        ("--enable-rule-strategies", args.enable_rule_strategies),
                    )
                    if enabled
                ],
            }
        )
        return 2

    if args.exchange != "dry-run" and not args.reconcile:
        _print_json({"error": "--exchange okx is currently supported only with --reconcile"})
        return 2

    if args.reconcile and args.exchange == "okx":
        exchange, error = _okx_exchange_from_env()
        if error:
            _print_json(error)
            return 2
        config = BacktestConfig()
        risk_manager = RiskManager(config)
        db = StateDB(args.db)
        try:
            executor = Executor(exchange, risk_manager, db, config)
            try:
                sync = executor.sync_state(current_step=0)
            except ExchangeError as exc:
                _print_json({"error": str(exc)})
                return 1
            _print_json(asdict(sync))
            return 0
        finally:
            db.close()

    _setup_logging()
    config, exchange, risk_manager, db, executor = _build_components(args.db, equity=args.equity)
    config = replace(
        config,
        enable_pairs_trading=args.enable_pairs,
        enable_rule_trading=args.enable_rule_strategies,
    )
    risk_manager.config = config
    executor.config = config
    pairs_list = [p.strip() for p in args.pairs.split(",")] if args.pairs else None
    try:
        if args.once:
            runner = TradingRunner(config, executor, db, data_dir=args.data, pairs=pairs_list)
            report = runner.run_once()
            payload = asdict(report)
            payload["equity"] = args.equity
            _print_json(payload)
            return 0
        if args.loop:
            runner = TradingRunner(config, executor, db, data_dir=args.data, pairs=pairs_list)
            # Pre-load market data once
            runner.load_market_data()
            if args.iterations and args.iterations > 0:
                # Finite loop for testing / batch runs
                report = None
                for step in range(args.iterations):
                    report = runner.run_once()
                    if args.interval > 0 and step < args.iterations - 1:
                        time.sleep(args.interval)
                payload = asdict(report) if report is not None else {}
                payload["equity"] = args.equity
                payload["iterations"] = args.iterations
                _print_json(payload)
            else:
                # Infinite loop for live trading
                runner.run_loop(interval_seconds=int(args.interval))
            return 0
        if args.reconcile:
            sync = executor.sync_state(current_step=0)
            _print_json(asdict(sync))
            return 0
    finally:
        db.close()
    return 1


def _build_components(db_path: Path, equity: float = 10.0) -> tuple[BacktestConfig, DryRunExchange, RiskManager, StateDB, Executor]:
    config = BacktestConfig()
    exchange = DryRunExchange(equity=equity)
    risk_manager = RiskManager(config)
    db = StateDB(db_path)
    executor = Executor(exchange, risk_manager, db, config)
    return config, exchange, risk_manager, db, executor


def create_runner(
    config: BacktestConfig,
    api_key: str = "",
    secret: str = "",
    passphrase: str = "",
    sandbox: bool = True,
    dry_run: bool = False,
    symbols: list[str] | None = None,
    db_path: str | None = None,
) -> TradingRunner:
    exchange = OKXExchange(api_key, secret, passphrase, sandbox=sandbox)
    risk_manager = RiskManager(config)
    db = StateDB(Path(db_path)) if db_path else None
    executor = Executor(exchange, risk_manager, db, config, dry_run=dry_run)
    return TradingRunner(
        config=config,
        executor=executor,
        state_db=db,
        exchange=exchange,
        symbols=symbols or [],
        dry_run=dry_run,
    )


def _status_payload(db: StateDB) -> dict:
    history = db.get_account_history()
    latest = history[-1] if history else {}
    open_positions = db.get_open_positions()
    return {
        "equity": latest.get("equity", 0.0),
        "available_margin": latest.get("available_margin", 0.0),
        "used_margin": latest.get("used_margin", 0.0),
        "open_positions": len(open_positions),
        "positions": open_positions,
        "trade_summary": db.trade_summary(),
    }


def _okx_check_payload(symbol: str) -> tuple[dict, int]:
    exchange, error = _okx_exchange_from_env()
    if error:
        error["okx_check"] = False
        return error, 2
    try:
        account = exchange.get_account_balance()
        ticker = exchange.get_ticker(symbol)
        positions = exchange.get_positions()
    except ExchangeError as exc:
        return {"okx_check": False, "error": str(exc)}, 1
    return {
        "okx_check": True,
        "sandbox": True,
        "symbol": symbol,
        "account": {
            "equity": account.equity,
            "available_margin": account.available_margin,
            "used_margin": account.used_margin,
        },
        "ticker": {
            "symbol": ticker.symbol,
            "last": ticker.last,
            "bid": ticker.bid,
            "ask": ticker.ask,
        },
        "open_positions": len(positions),
        "positions": positions,
    }, 0


def _okx_smoke_order_payload(args: argparse.Namespace) -> tuple[dict, int]:
    if not args.confirm_okx_smoke_order:
        return {
            "okx_smoke_order": False,
            "error": "Refusing to submit simulated order without --confirm-okx-smoke-order",
        }, 2

    exchange, error = _okx_exchange_from_env()
    if error:
        error["okx_smoke_order"] = False
        return error, 2

    try:
        account = exchange.get_account_balance()
        positions = exchange.get_positions()
        risk_manager = RiskManager(BacktestConfig())
        decision = risk_manager.check_order(
            symbol=args.okx_symbol,
            direction=1 if args.okx_smoke_direction == "long" else -1,
            notional=args.okx_smoke_notional,
            margin=args.okx_smoke_margin,
            equity=account.equity,
            current_step=0,
            bars=[_RiskBar()],
            idx=0,
            current_positions_margin=0.0,
            current_positions_count=len(positions),
        )
        if not decision.allowed:
            return {
                "okx_smoke_order": False,
                "risk_allowed": False,
                "reason": decision.reason,
            }, 2

        order = exchange.place_order(
            args.okx_symbol,
            args.okx_smoke_direction,
            args.okx_smoke_qty,
            order_type="limit",
            price=args.okx_smoke_price,
        )
        cancel_response = exchange.cancel_order(args.okx_symbol, order.order_id)
    except ExchangeError as exc:
        return {"okx_smoke_order": False, "error": str(exc)}, 1

    return {
        "okx_smoke_order": True,
        "sandbox": True,
        "symbol": args.okx_symbol,
        "direction": args.okx_smoke_direction,
        "qty": args.okx_smoke_qty,
        "price": args.okx_smoke_price,
        "notional": args.okx_smoke_notional,
        "margin": args.okx_smoke_margin,
        "risk_allowed": True,
        "order_id": order.order_id,
        "order_status": order.status,
        "cancel_requested": True,
        "cancel_response": cancel_response,
    }, 0


def _okx_submit_signal_payload(args: argparse.Namespace) -> tuple[dict, int]:
    if not args.confirm_okx_submit_signal:
        return {
            "okx_submit_signal": False,
            "error": "Refusing to submit simulated signal without --confirm-okx-submit-signal",
        }, 2

    exchange, error = _okx_exchange_from_env()
    if error:
        error["okx_submit_signal"] = False
        return error, 2

    config = BacktestConfig()
    risk_manager = RiskManager(config)
    db = StateDB(args.db)
    try:
        executor = Executor(exchange, risk_manager, db, config)
        try:
            sync = executor.sync_state(current_step=0)
            if not sync.consistent:
                return {
                    "okx_submit_signal": False,
                    "sync_consistent": False,
                    "local_only": sync.local_only,
                    "exchange_only": sync.exchange_only,
                }, 2
            account = exchange.get_account_balance()
            request = ExecutionRequest(
                symbol=args.okx_symbol,
                direction=1 if args.okx_signal_direction == "long" else -1,
                price=args.okx_signal_price,
                qty=args.okx_signal_notional / args.okx_signal_price if args.okx_signal_price > 0 else 0.0,
                notional=args.okx_signal_notional,
                margin=args.okx_signal_margin,
                leverage=args.okx_signal_leverage,
                signal_reason="manual_okx_submit_signal",
                regime="manual",
            )
            result = executor.execute_signal(
                request,
                equity=account.equity,
                current_step=0,
                bars=[_RiskBar()],
                idx=0,
            )
        except ExchangeError as exc:
            return {"okx_submit_signal": False, "error": str(exc)}, 1

        order = db.get_order(result.order_id) if result.order_id else None
        return {
            "okx_submit_signal": result.accepted,
            "sync_consistent": True,
            "accepted": result.accepted,
            "status": result.status,
            "reason": result.reason,
            "order_id": result.order_id,
            "exchange_order_id": order.get("exchange_order_id") if order else None,
            "position_id": result.position_id,
            "symbol": args.okx_symbol,
            "direction": args.okx_signal_direction,
            "notional": args.okx_signal_notional,
            "margin": args.okx_signal_margin,
            "leverage": args.okx_signal_leverage,
        }, 0 if result.accepted else 2
    finally:
        db.close()


def _okx_sync_orders_payload(db_path: Path) -> tuple[dict, int]:
    exchange, error = _okx_exchange_from_env()
    if error:
        error["okx_sync_orders"] = False
        return error, 2
    return _okx_sync_orders_with_exchange(db_path, exchange)


def _okx_sync_orders_with_exchange(db_path: Path, exchange: OKXExchange) -> tuple[dict, int]:
    db = StateDB(db_path)
    checked = 0
    updated = 0
    filled = 0
    canceled = 0
    opened_positions = 0
    closed_positions = 0
    saved_trades = 0
    details = []
    try:
        for order in db.get_active_exchange_orders():
            checked += 1
            exchange_order_id = order["exchange_order_id"]
            try:
                payload = exchange.get_order_status(order["symbol"], exchange_order_id)
            except ExchangeError as exc:
                return {"okx_sync_orders": False, "error": str(exc), "checked_orders": checked}, 1
            data = _first_okx_data(payload)
            status = _okx_order_state(data)
            fill_price = _optional_float(data.get("avgPx"))
            fill_qty = _optional_float(data.get("accFillSz"))
            fee = abs(_optional_float(data.get("fee")) or 0.0)
            db.update_order_status(
                order["id"],
                status,
                fill_price=fill_price,
                fill_qty=fill_qty,
                fee=fee,
                exchange_order_id=exchange_order_id,
            )
            updated += 1
            if status == "filled":
                filled += 1
                meta = _json_dict(order.get("meta"))
                if meta.get("action") == "close":
                    closed, saved = _close_position_for_filled_order(db, order, meta, fill_price, fee)
                    closed_positions += closed
                    saved_trades += saved
                else:
                    opened_positions += _open_position_for_filled_order(db, order, fill_price, fill_qty)
            elif status == "canceled":
                canceled += 1
            details.append(
                {
                    "order_id": order["id"],
                    "exchange_order_id": exchange_order_id,
                    "symbol": order["symbol"],
                    "status": status,
                }
            )
    finally:
        db.close()

    return {
        "okx_sync_orders": True,
        "checked_orders": checked,
        "updated_orders": updated,
        "filled_orders": filled,
        "canceled_orders": canceled,
        "opened_positions": opened_positions,
        "closed_positions": closed_positions,
        "saved_trades": saved_trades,
        "orders": details,
    }, 0


def _okx_close_position_payload(args: argparse.Namespace) -> tuple[dict, int]:
    if not args.confirm_okx_close_position:
        return {
            "okx_close_position": False,
            "error": "Refusing to submit close order without --confirm-okx-close-position",
        }, 2
    if not args.position_id:
        return {"okx_close_position": False, "error": "Missing --position-id"}, 2

    exchange, error = _okx_exchange_from_env()
    if error:
        error["okx_close_position"] = False
        return error, 2

    db = StateDB(args.db)
    try:
        position = db.get_position(args.position_id)
        if not position or position["status"] != "open":
            return {"okx_close_position": False, "error": "Position is not open"}, 2
        exchange_positions = exchange.get_positions()
        reconciliation = db.reconcile_positions(exchange_positions)
        if not reconciliation.consistent:
            return {
                "okx_close_position": False,
                "sync_consistent": False,
                "local_only": reconciliation.local_only,
                "exchange_only": reconciliation.exchange_only,
            }, 2

        close_direction = "short" if position["direction"] == "long" else "long"
        fee = position["notional"] * BacktestConfig().taker_fee
        order = exchange.place_order(
            position["symbol"],
            close_direction,
            position["qty"],
            order_type="market",
            price=args.okx_close_price if args.okx_close_price > 0 else position["entry_price"],
            fee=fee,
        )
        local_order_id = db.save_order(
            position["symbol"],
            close_direction,
            position["qty"],
            price=args.okx_close_price if args.okx_close_price > 0 else position["entry_price"],
            signal_reason="manual_okx_close_position",
            risk_decision="close",
            meta={
                "action": "close",
                "position_id": args.position_id,
                "exit_reason": "manual_okx_close",
            },
        )
        db.update_order_status(local_order_id, order.status, fee=order.fee, exchange_order_id=order.order_id)
    except ExchangeError as exc:
        return {"okx_close_position": False, "error": str(exc)}, 1
    finally:
        db.close()

    return {
        "okx_close_position": True,
        "position_id": args.position_id,
        "order_id": local_order_id,
        "exchange_order_id": order.order_id,
        "status": order.status,
    }, 0


def _okx_snapshot_payload(db_path: Path) -> tuple[dict, int]:
    exchange, error = _okx_exchange_from_env()
    if error:
        error["okx_snapshot"] = False
        return error, 2
    return _okx_snapshot_with_exchange(db_path, exchange)


def _okx_snapshot_with_exchange(db_path: Path, exchange: OKXExchange) -> tuple[dict, int]:
    db = StateDB(db_path)
    try:
        try:
            account = exchange.get_account_balance()
            exchange_positions = exchange.get_positions()
        except ExchangeError as exc:
            return {"okx_snapshot": False, "error": str(exc)}, 1

        local_positions = db.get_open_positions()
        active_orders = db.get_active_exchange_orders()
        trade_summary = db.trade_summary()
        risk_status = {
            "source": "okx_snapshot",
            "pending_orders": len(active_orders),
            "local_open_positions": len(local_positions),
            "exchange_open_positions": len(exchange_positions),
            "trade_summary": trade_summary,
        }
        db.snapshot_account(
            equity=account.equity,
            available_margin=account.available_margin,
            used_margin=account.used_margin,
            unrealized_pnl=sum(position.get("unrealized_pnl", 0.0) for position in exchange_positions),
            open_positions=len(local_positions),
            risk_status=json.dumps(risk_status, ensure_ascii=False),
        )
    finally:
        db.close()

    return {
        "okx_snapshot": True,
        "account": {
            "equity": account.equity,
            "available_margin": account.available_margin,
            "used_margin": account.used_margin,
        },
        "local_open_positions": len(local_positions),
        "exchange_open_positions": len(exchange_positions),
        "pending_orders": len(active_orders),
        "trade_summary": trade_summary,
    }, 0


def _okx_monitor_loop_payload(
    db_path: Path,
    iterations: int,
    interval: float,
    stale_order_minutes: int = 30,
    notifier: Notifier | None = None,
    alert_tracker: HealthAlertTracker | None = None,
) -> tuple[dict, int]:
    exchange, error = _okx_exchange_from_env()
    if error:
        error["okx_monitor_loop"] = False
        return error, 2

    notifier = notifier if notifier is not None else create_notifier_from_env()
    alert_tracker = alert_tracker if alert_tracker is not None else HealthAlertTracker()
    cycles = []
    for step in range(iterations):
        sync_payload, sync_code = _okx_sync_orders_with_exchange(db_path, exchange)
        if sync_code != 0:
            sync_payload["okx_monitor_loop"] = False
            sync_payload["cycle"] = step
            return sync_payload, sync_code
        snapshot_payload, snapshot_code = _okx_snapshot_with_exchange(db_path, exchange)
        if snapshot_code != 0:
            snapshot_payload["okx_monitor_loop"] = False
            snapshot_payload["cycle"] = step
            return snapshot_payload, snapshot_code
        health_payload, _health_code = _okx_health_report_with_exchange(
            db_path,
            exchange,
            stale_order_minutes=stale_order_minutes,
            notifier=notifier,
            alert_tracker=alert_tracker,
        )
        cycles.append({"cycle": step, "sync": sync_payload, "snapshot": snapshot_payload, "health": health_payload})
        if interval > 0 and step < iterations - 1:
            time.sleep(interval)

    return {
        "okx_monitor_loop": True,
        "iterations": iterations,
        "cycles": cycles,
    }, 0


def _okx_health_report_payload(db_path: Path, stale_order_minutes: int = 30) -> tuple[dict, int]:
    exchange, error = _okx_exchange_from_env()
    if error:
        error["okx_health_report"] = False
        return error, 2

    return _okx_health_report_with_exchange(
        db_path,
        exchange,
        stale_order_minutes=stale_order_minutes,
        notifier=create_notifier_from_env(),
        alert_tracker=HealthAlertTracker(),
    )


def _okx_health_report_with_exchange(
    db_path: Path,
    exchange: OKXExchange,
    stale_order_minutes: int = 30,
    notifier: Notifier | None = None,
    alert_tracker: HealthAlertTracker | None = None,
) -> tuple[dict, int]:
    db = StateDB(db_path)
    try:
        active_orders = db.get_active_exchange_orders()
        local_positions = db.get_open_positions()
        try:
            exchange_positions = exchange.get_positions()
            reconciliation = db.reconcile_positions(exchange_positions)
            report = build_health_report(
                active_orders=active_orders,
                reconciliation=reconciliation,
                stale_order_minutes=stale_order_minutes,
                local_open_positions=len(local_positions),
                exchange_open_positions=len(exchange_positions),
            )
        except ExchangeError as exc:
            report = build_health_report(
                active_orders=active_orders,
                api_error=str(exc),
                stale_order_minutes=stale_order_minutes,
                local_open_positions=len(local_positions),
            )
        payload = report.to_dict()
        payload["okx_health_report"] = True
        payload["stale_order_minutes"] = stale_order_minutes
        report_id = db.save_health_report(payload)
        alerts_saved = _save_health_alerts(db, report_id, payload["issues"])
        notification_results = _notify_health_issues(report, notifier, alert_tracker)
    finally:
        db.close()

    payload["health_report_id"] = report_id
    payload["alerts_saved"] = alerts_saved
    payload["notifications_sent"] = sum(1 for result in notification_results if result.success)
    payload["notifications_failed"] = sum(1 for result in notification_results if not result.success)
    return payload, 0 if report.status == "ok" else 1


def _notify_health_issues(
    report: HealthReport,
    notifier: Notifier | None,
    alert_tracker: HealthAlertTracker | None,
) -> list[NotificationResult]:
    if notifier is None or alert_tracker is None:
        return []
    new_issues = alert_tracker.filter_new_issues(report.issues)
    if not new_issues:
        return []
    return notifier.notify_issues(new_issues)


def _save_health_alerts(db: StateDB, report_id: int, issues: list[dict]) -> int:
    saved = 0
    for issue in issues:
        severity = issue.get("severity", "")
        if severity not in ("warning", "critical"):
            continue
        db.save_health_alert(
            report_id=report_id,
            severity=severity,
            kind=issue.get("kind", "unknown"),
            message=issue.get("message", ""),
            context=issue.get("context") or {},
        )
        saved += 1
    return saved


def _open_position_for_filled_order(
    db: StateDB,
    order: dict,
    fill_price: float | None,
    fill_qty: float | None,
) -> int:
    if fill_price is None or fill_qty is None or fill_qty <= 0:
        return 0
    meta = _json_dict(order.get("meta"))
    notional = float(meta.get("notional") or (fill_price * fill_qty))
    margin = float(meta.get("margin") or notional)
    leverage = float(meta.get("leverage") or (notional / margin if margin else 1.0))
    db.save_position(
        order["symbol"],
        order["direction"],
        entry_price=fill_price,
        qty=fill_qty,
        notional=notional,
        margin=margin,
        leverage=leverage,
    )
    return 1


def _close_position_for_filled_order(
    db: StateDB,
    order: dict,
    meta: dict[str, Any],
    fill_price: float | None,
    fee: float,
) -> tuple[int, int]:
    position_id = meta.get("position_id")
    if not position_id or fill_price is None:
        return 0, 0
    position = db.get_position(position_id)
    if not position or position["status"] != "open":
        return 0, 0

    pnl = _pnl_for_position(position, fill_price) - fee
    pnl_pct = pnl / position["margin"] * 100.0 if position["margin"] else 0.0
    db.close_position(position_id)
    db.save_trade(
        symbol=position["symbol"],
        direction=position["direction"],
        entry_price=position["entry_price"],
        exit_price=fill_price,
        entry_time=position["opened_at"],
        exit_time=position["updated_at"],
        pnl=round(pnl, 8),
        pnl_pct=round(pnl_pct, 4),
        exit_reason=meta.get("exit_reason", "okx_close"),
        order_id=order["id"],
    )
    return 1, 1


def _pnl_for_position(position: dict, exit_price: float) -> float:
    entry_price = position["entry_price"]
    notional = position["notional"]
    if entry_price <= 0:
        return 0.0
    if position["direction"] == "long":
        return (exit_price - entry_price) / entry_price * notional
    return (entry_price - exit_price) / entry_price * notional


def _first_okx_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or []
    return data[0] if data else {}


def _okx_order_state(data: dict[str, Any]) -> str:
    state = data.get("state") or ""
    if state in ("filled", "canceled", "partially_filled", "live"):
        return state
    return "live"


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    return json.loads(value)


def _okx_exchange_from_env() -> tuple[OKXExchange | None, dict | None]:
    credentials = _okx_credentials_from_env()
    missing = [name for name, value in credentials.items() if not value]
    if missing:
        return None, {"error": f"Missing OKX credentials: {', '.join(missing)}"}
    return OKXExchange(
        credentials["OKX_API_KEY"],
        credentials["OKX_API_SECRET"],
        credentials["OKX_API_PASSPHRASE"],
        sandbox=True,
    ), None


def _okx_credentials_from_env() -> dict[str, str]:
    return {
        "OKX_API_KEY": os.environ.get("OKX_API_KEY", ""),
        "OKX_API_SECRET": os.environ.get("OKX_API_SECRET", ""),
        "OKX_API_PASSPHRASE": os.environ.get("OKX_API_PASSPHRASE", ""),
    }


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())

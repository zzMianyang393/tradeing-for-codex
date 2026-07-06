from __future__ import annotations

import json
import logging
import signal
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from config import BacktestConfig
from exchange import OKXExchange
from executor import Executor
from risk_manager import RiskManager
from state_db import StateDB
from strategy import signal_for, attack_signal_for, continuation_signal_for, micro_momentum_signal_for
from market import FeatureBar

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Run report
# ---------------------------------------------------------------------------

@dataclass
class RunReport:
    timestamp: str = ""
    equity: float = 0.0
    open_positions: int = 0
    signals_generated: int = 0
    orders_placed: int = 0
    orders_rejected: int = 0
    risk_status: str = ""
    errors: list[str] | None = None


# ---------------------------------------------------------------------------
# Trading runner
# ---------------------------------------------------------------------------

class TradingRunner:
    """Main trading loop: fetch bars → generate signals → execute → manage positions.

    Usage::

        runner = TradingRunner(config, exchange, executor, state_db)
        runner.run_once()   # single iteration
        runner.run_loop()   # continuous loop
    """

    def __init__(
        self,
        config: BacktestConfig,
        exchange: OKXExchange,
        executor: Executor,
        state_db: StateDB | None = None,
        symbols: list[str] | None = None,
        dry_run: bool = False,
    ) -> None:
        self.config = config
        self.exchange = exchange
        self.executor = executor
        self.state_db = state_db
        self.symbols = symbols or []
        self.dry_run = dry_run
        self._running = False
        self._step = 0

    # ------------------------------------------------------------------
    # Single run
    # ------------------------------------------------------------------

    def run_once(self) -> RunReport:
        """Execute one iteration of the trading loop."""
        report = RunReport()
        errors = []

        try:
            # 1. Sync state with exchange
            sync = self.executor.sync_state()
            if not sync.consistent:
                errors.append(f"Position inconsistency detected")

            # 2. Get account info
            account = self.exchange.get_account_balance()
            report.equity = account.total_equity

            # 3. Get current positions
            positions = self.exchange.get_positions()
            report.open_positions = len(positions)

            # 4. Fetch latest bars for each symbol
            bars_data: dict[str, list] = {}
            for symbol in self.symbols:
                try:
                    klines = self.exchange.get_klines(symbol, bar="15m", limit=300)
                    bars_data[symbol] = klines
                except Exception as e:
                    errors.append(f"Failed to fetch {symbol}: {e}")

            # 5. Generate and execute signals
            for symbol, bars in bars_data.items():
                if not bars:
                    continue

                idx = len(bars) - 1
                report.signals_generated += 1

                # Try different signal generators
                sig = None
                for sig_func in [signal_for, attack_signal_for, continuation_signal_for, micro_momentum_signal_for]:
                    try:
                        sig = sig_func(symbol, bars, idx, self.config)
                        if sig and sig.score >= self.config.min_score:
                            break
                        sig = None
                    except Exception:
                        continue

                if sig is None:
                    continue

                # Execute signal
                result = self.executor.execute_signal(sig, bars, idx)
                if result.success:
                    report.orders_placed += 1
                else:
                    report.orders_rejected += 1

            # 6. Manage existing positions
            current_bars = {}
            for symbol, bars in bars_data.items():
                if bars:
                    current_bars[symbol] = bars[-1]

            actions = self.executor.manage_positions(current_bars)
            for action in actions:
                self.executor.close_position(action.symbol, action.reason)

            # 7. Take account snapshot
            self.executor.snapshot_account()

            # 8. Get risk status
            if self.executor.risk_manager is not None:
                risk_status = self.executor.risk_manager.get_status()
                report.risk_status = json.dumps(asdict(risk_status))

        except Exception as e:
            errors.append(str(e))
            logger.error(f"Run once failed: {e}")

        report.errors = errors if errors else None
        self._step += 1
        return report

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    def run_loop(self, interval_seconds: int = 900) -> None:
        """Run continuously, executing once per interval.

        Default interval is 900 seconds (15 minutes, matching 15m candles).
        """
        self._running = True

        # Handle SIGINT/SIGTERM gracefully
        def _stop(signum, frame):
            logger.info(f"Received signal {signum}, stopping...")
            self._running = False

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        logger.info(f"Starting trading loop, interval={interval_seconds}s, symbols={self.symbols}")

        while self._running:
            try:
                report = self.run_once()
                logger.info(
                    f"Step {self._step}: equity={report.equity:.2f} "
                    f"positions={report.open_positions} "
                    f"signals={report.signals_generated} "
                    f"orders={report.orders_placed}/{report.orders_rejected}"
                )
            except Exception as e:
                logger.error(f"Loop iteration failed: {e}")

            # Wait for next interval
            if self._running:
                time.sleep(interval_seconds)

        logger.info("Trading loop stopped")

    def stop(self) -> None:
        """Signal the loop to stop."""
        self._running = False


# ---------------------------------------------------------------------------
# Run report persistence
# ---------------------------------------------------------------------------

def save_run_report(report: RunReport, path: Path) -> None:
    """Save a run report to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

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
    """Create a fully wired TradingRunner."""
    exchange = OKXExchange(api_key, secret, passphrase, sandbox=sandbox)

    risk_manager = RiskManager(config) if config.rm_enabled else None

    state_db = StateDB(Path(db_path)) if db_path else None

    executor = Executor(
        exchange=exchange,
        risk_manager=risk_manager,
        state_db=state_db,
        config=config,
        dry_run=dry_run,
    )

    return TradingRunner(
        config=config,
        exchange=exchange,
        executor=executor,
        state_db=state_db,
        symbols=symbols or [],
        dry_run=dry_run,
    )

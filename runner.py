from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config import BacktestConfig
from exchange import DryRunExchange, OKXExchange
from executor import ExecutionRequest, Executor
from risk_manager import RiskManager
from state_db import StateDB


@dataclass(frozen=True)
class RunInput:
    equity: float
    current_step: int
    current_prices: dict[str, float]
    bars_by_symbol: dict[str, list]
    signal_requests: list[ExecutionRequest] = field(default_factory=list)


@dataclass(frozen=True)
class RunReport:
    executed_orders: int
    rejected_orders: int
    closed_positions: int
    open_positions: int
    sync_consistent: bool
    risk_status: dict


class TradingRunner:
    """One-cycle dry-run trading orchestrator.

    The runner intentionally delegates execution details to ``Executor`` so the
    same cycle can later be wired to a real exchange adapter.
    """

    def __init__(self, config: BacktestConfig, executor: Executor, state_db: StateDB) -> None:
        self.config = config
        self.executor = executor
        self.state_db = state_db

    def run_once(self, run_input: RunInput) -> RunReport:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run trading runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--status", action="store_true", help="Print local account/position status as JSON")
    mode.add_argument("--once", action="store_true", help="Run one dry-run cycle with no generated signals")
    mode.add_argument("--loop", action="store_true", help="Run repeated dry-run cycles")
    mode.add_argument("--reconcile", action="store_true", help="Reconcile local positions against dry-run exchange state")
    mode.add_argument("--okx-check", action="store_true", help="Check OKX simulated account, ticker, and positions")
    parser.add_argument("--db", type=Path, default=Path("reports") / "dry_run_state.db")
    parser.add_argument("--equity", type=float, default=10.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.0)
    parser.add_argument("--okx-symbol", default="BTC-USDT-SWAP")
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

    config, exchange, risk_manager, db, executor = _build_components(args.db)
    try:
        if args.once:
            runner = TradingRunner(config, executor, db)
            report = runner.run_once(
                RunInput(
                    equity=args.equity,
                    current_step=0,
                    current_prices={},
                    bars_by_symbol={},
                )
            )
            payload = asdict(report)
            payload["equity"] = args.equity
            _print_json(payload)
            return 0
        if args.loop:
            runner = TradingRunner(config, executor, db)
            report = None
            for step in range(args.iterations):
                report = runner.run_once(
                    RunInput(
                        equity=args.equity,
                        current_step=step,
                        current_prices={},
                        bars_by_symbol={},
                    )
                )
                if args.interval > 0 and step < args.iterations - 1:
                    time.sleep(args.interval)
            payload = asdict(report) if report is not None else {}
            payload["equity"] = args.equity
            payload["iterations"] = args.iterations
            _print_json(payload)
            return 0
        if args.reconcile:
            sync = executor.sync_state(current_step=0)
            _print_json(asdict(sync))
            return 0
    finally:
        db.close()
    return 1


def _build_components(db_path: Path) -> tuple[BacktestConfig, DryRunExchange, RiskManager, StateDB, Executor]:
    config = BacktestConfig()
    exchange = DryRunExchange()
    risk_manager = RiskManager(config)
    db = StateDB(db_path)
    executor = Executor(exchange, risk_manager, db, config)
    return config, exchange, risk_manager, db, executor


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
    credentials = _okx_credentials_from_env()
    missing = [name for name, value in credentials.items() if not value]
    if missing:
        return {"okx_check": False, "error": f"Missing OKX credentials: {', '.join(missing)}"}, 2

    exchange = OKXExchange(
        credentials["OKX_API_KEY"],
        credentials["OKX_API_SECRET"],
        credentials["OKX_API_PASSPHRASE"],
        sandbox=True,
    )
    account = exchange.get_account_balance()
    ticker = exchange.get_ticker(symbol)
    positions = exchange.get_positions()
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

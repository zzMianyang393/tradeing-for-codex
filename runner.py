from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from config import BacktestConfig
from exchange import DryRunExchange, ExchangeError, OKXExchange
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


@dataclass(frozen=True)
class _RiskBar:
    atr_pct: float = 0.0


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
    mode.add_argument("--okx-smoke-order", action="store_true", help="Place then cancel one OKX simulated limit order")
    mode.add_argument("--okx-submit-signal", action="store_true", help="Submit one risk-checked signal to OKX simulated trading")
    parser.add_argument("--db", type=Path, default=Path("reports") / "dry_run_state.db")
    parser.add_argument("--equity", type=float, default=10.0)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--interval", type=float, default=0.0)
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

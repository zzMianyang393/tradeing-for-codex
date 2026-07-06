from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'market',
    qty REAL NOT NULL,
    price REAL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    filled_at TEXT,
    fill_price REAL,
    fill_qty REAL,
    fee REAL,
    exchange_order_id TEXT,
    signal_reason TEXT,
    risk_decision TEXT,
    meta TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL,
    qty REAL NOT NULL,
    notional REAL NOT NULL,
    margin REAL NOT NULL,
    leverage REAL NOT NULL,
    unrealized_pnl REAL,
    stop_loss REAL,
    take_profit REAL,
    trail REAL,
    signal_reason TEXT,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    equity REAL NOT NULL,
    available_margin REAL NOT NULL,
    used_margin REAL NOT NULL,
    unrealized_pnl REAL NOT NULL,
    daily_pnl REAL,
    weekly_pnl REAL,
    open_positions INTEGER,
    risk_status TEXT
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    order_id TEXT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    entry_time TEXT NOT NULL,
    exit_time TEXT,
    pnl REAL,
    pnl_pct REAL,
    fee REAL,
    signal_reason TEXT,
    exit_reason TEXT,
    regime TEXT,
    risk_events TEXT
);

CREATE TABLE IF NOT EXISTS risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS health_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    status TEXT NOT NULL,
    issue_count INTEGER NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS health_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER,
    ts TEXT NOT NULL,
    severity TEXT NOT NULL,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    context TEXT,
    FOREIGN KEY(report_id) REFERENCES health_reports(id)
);
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _uuid() -> str:
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# StateDB
# ---------------------------------------------------------------------------

class StateDB:
    """Persistent trade state backed by SQLite.

    Usage::

        db = StateDB(Path("state/trading.db"))
        db.save_trade(symbol="BTC-USDT-SWAP", direction="long", ...)
        db.snapshot_account(equity=10.0, ...)
        recent = db.get_recent_trades(10)
    """

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._migrate_schema()
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _migrate_schema(self) -> None:
        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(orders)").fetchall()
        }
        if "exchange_order_id" not in columns:
            self._conn.execute("ALTER TABLE orders ADD COLUMN exchange_order_id TEXT")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def save_order(
        self,
        symbol: str,
        direction: str,
        qty: float,
        price: float | None = None,
        order_type: str = "market",
        signal_reason: str = "",
        risk_decision: str = "",
        meta: dict[str, Any] | None = None,
    ) -> str:
        order_id = _uuid()
        self._conn.execute(
            "INSERT INTO orders (id, symbol, direction, type, qty, price, status, "
            "created_at, signal_reason, risk_decision, meta) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                order_id, symbol, direction, order_type, qty, price,
                "pending", _now_utc(), signal_reason, risk_decision,
                json.dumps(meta) if meta else None,
            ),
        )
        self._conn.commit()
        return order_id

    def update_order_status(
        self,
        order_id: str,
        status: str,
        fill_price: float | None = None,
        fill_qty: float | None = None,
        fee: float | None = None,
        exchange_order_id: str | None = None,
    ) -> None:
        self._conn.execute(
            "UPDATE orders SET status=?, filled_at=?, fill_price=?, fill_qty=?, fee=?, exchange_order_id=? "
            "WHERE id=?",
            (
                status,
                _now_utc() if status == "filled" else None,
                fill_price,
                fill_qty,
                fee,
                exchange_order_id,
                order_id,
            ),
        )
        self._conn.commit()

    def get_order(self, order_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    def get_active_exchange_orders(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE exchange_order_id IS NOT NULL "
            "AND status IN ('live', 'pending', 'partially_filled') ORDER BY created_at"
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def save_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        qty: float,
        notional: float,
        margin: float,
        leverage: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        trail: float | None = None,
        signal_reason: str = "",
    ) -> str:
        pos_id = _uuid()
        now = _now_utc()
        self._conn.execute(
            "INSERT INTO positions (id, symbol, direction, entry_price, qty, notional, "
            "margin, leverage, stop_loss, take_profit, trail, signal_reason, opened_at, updated_at, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                pos_id, symbol, direction, entry_price, qty, notional,
                margin, leverage, stop_loss, take_profit, trail, signal_reason, now, now, "open",
            ),
        )
        self._conn.commit()
        return pos_id

    def update_position_price(self, position_id: str, current_price: float, unrealized_pnl: float) -> None:
        self._conn.execute(
            "UPDATE positions SET current_price=?, unrealized_pnl=?, updated_at=? WHERE id=?",
            (current_price, unrealized_pnl, _now_utc(), position_id),
        )
        self._conn.commit()

    def update_position_trail(self, position_id: str, trail: float) -> None:
        self._conn.execute(
            "UPDATE positions SET trail=?, updated_at=? WHERE id=?",
            (trail, _now_utc(), position_id),
        )
        self._conn.commit()

    def close_position(self, position_id: str) -> None:
        self._conn.execute(
            "UPDATE positions SET status='closed', updated_at=? WHERE id=?",
            (_now_utc(), position_id),
        )
        self._conn.commit()

    def get_open_positions(self) -> list[dict]:
        rows = self._conn.execute("SELECT * FROM positions WHERE status='open'").fetchall()
        return [dict(r) for r in rows]

    def get_position(self, position_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM positions WHERE id=?", (position_id,)).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    def save_trade(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float | None,
        entry_time: str,
        exit_time: str | None,
        pnl: float | None,
        pnl_pct: float | None,
        signal_reason: str = "",
        exit_reason: str = "",
        regime: str = "",
        order_id: str | None = None,
        risk_events: list[dict] | None = None,
    ) -> str:
        trade_id = _uuid()
        self._conn.execute(
            "INSERT INTO trades (id, order_id, symbol, direction, entry_price, exit_price, "
            "entry_time, exit_time, pnl, pnl_pct, signal_reason, exit_reason, regime, "
            "risk_events) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                trade_id, order_id, symbol, direction, entry_price, exit_price,
                entry_time, exit_time, pnl, pnl_pct, signal_reason, exit_reason,
                regime, json.dumps(risk_events) if risk_events else None,
            ),
        )
        self._conn.commit()
        return trade_id

    def get_recent_trades(self, n: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM trades ORDER BY rowid DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trades_by_symbol(self, symbol: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE symbol=? ORDER BY rowid", (symbol,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_trades_by_reason(self, reason: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE signal_reason=? ORDER BY rowid", (reason,)
        ).fetchall()
        return [dict(r) for r in rows]

    def count_trades(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM trades").fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Account snapshots
    # ------------------------------------------------------------------

    def snapshot_account(
        self,
        equity: float,
        available_margin: float,
        used_margin: float,
        unrealized_pnl: float = 0.0,
        daily_pnl: float | None = None,
        weekly_pnl: float | None = None,
        open_positions: int = 0,
        risk_status: str | None = None,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO account_snapshots (ts, equity, available_margin, used_margin, "
            "unrealized_pnl, daily_pnl, weekly_pnl, open_positions, risk_status) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                _now_utc(), equity, available_margin, used_margin,
                unrealized_pnl, daily_pnl, weekly_pnl, open_positions,
                risk_status,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def get_account_history(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM account_snapshots ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Risk events
    # ------------------------------------------------------------------

    def save_risk_event(self, event_type: str, detail: dict[str, Any] | None = None) -> int:
        cursor = self._conn.execute(
            "INSERT INTO risk_events (ts, event_type, detail) VALUES (?,?,?)",
            (_now_utc(), event_type, json.dumps(detail) if detail else None),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def get_risk_events(self, n: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM risk_events ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Health reports and alerts
    # ------------------------------------------------------------------

    def save_health_report(self, report: dict[str, Any]) -> int:
        issues = report.get("issues") or []
        cursor = self._conn.execute(
            "INSERT INTO health_reports (ts, status, issue_count, payload) VALUES (?,?,?,?)",
            (
                _now_utc(),
                report.get("status", "unknown"),
                len(issues),
                json.dumps(report, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def get_recent_health_reports(self, n: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM health_reports ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_health_alert(
        self,
        report_id: int,
        severity: str,
        kind: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO health_alerts (report_id, ts, severity, kind, message, context) "
            "VALUES (?,?,?,?,?,?)",
            (
                report_id,
                _now_utc(),
                severity,
                kind,
                message,
                json.dumps(context, ensure_ascii=False) if context else None,
            ),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def get_recent_health_alerts(self, n: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM health_alerts ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    def reconcile_positions(self, exchange_positions: list[dict]) -> ReconcileResult:
        """Compare local open positions against exchange-reported positions.

        ``exchange_positions`` should be a list of dicts with at least
        ``symbol`` and ``direction`` keys.
        """
        local = self.get_open_positions()
        local_keys = {(p["symbol"], p["direction"]) for p in local}
        exchange_keys = {(p["symbol"], p["direction"]) for p in exchange_positions}

        matches = [p for p in local if (p["symbol"], p["direction"]) in exchange_keys]
        local_only = [p for p in local if (p["symbol"], p["direction"]) not in exchange_keys]
        exchange_only = [p for p in exchange_positions if (p["symbol"], p["direction"]) not in local_keys]

        return ReconcileResult(
            matches=matches,
            local_only=local_only,
            exchange_only=exchange_only,
            consistent=len(local_only) == 0 and len(exchange_only) == 0,
        )

    # ------------------------------------------------------------------
    # Summary helpers
    # ------------------------------------------------------------------

    def trade_summary(self) -> dict:
        """Quick PnL summary from the trades table."""
        row = self._conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins, "
            "SUM(pnl) as total_pnl, "
            "AVG(pnl) as avg_pnl, "
            "MAX(pnl) as best_trade, "
            "MIN(pnl) as worst_trade "
            "FROM trades WHERE pnl IS NOT NULL"
        ).fetchone()
        if not row or row["total"] == 0:
            return {"total": 0, "wins": 0, "win_rate": 0.0, "total_pnl": 0.0}
        total = row["total"]
        wins = row["wins"] or 0
        return {
            "total": total,
            "wins": wins,
            "win_rate": round(wins / total, 4),
            "total_pnl": round(row["total_pnl"] or 0.0, 4),
            "avg_pnl": round(row["avg_pnl"] or 0.0, 4),
            "best_trade": round(row["best_trade"] or 0.0, 4),
            "worst_trade": round(row["worst_trade"] or 0.0, 4),
        }

    # ------------------------------------------------------------------
    # Batch helpers (for backtest result persistence)
    # ------------------------------------------------------------------

    def save_backtest_trades(self, trades: list[dict]) -> int:
        """Batch-insert trades from a backtest result ``trades_detail`` list.

        Each dict should match the keys produced by ``asdict(Trade)`` in
        ``backtester.py``.  Returns the number of rows inserted.
        """
        if not trades:
            return 0
        rows = []
        for t in trades:
            rows.append((
                _uuid(),
                t.get("symbol", ""),
                t.get("direction", ""),
                t.get("entry", 0.0),
                t.get("exit"),
                t.get("entry_time", ""),
                t.get("exit_time"),
                t.get("pnl"),
                t.get("pnl_pct_equity"),
                t.get("reason", ""),
                t.get("exit_reason", ""),
                t.get("regime", ""),
            ))
        self._conn.executemany(
            "INSERT INTO trades (id, symbol, direction, entry_price, exit_price, "
            "entry_time, exit_time, pnl, pnl_pct, signal_reason, exit_reason, regime) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        self._conn.commit()
        return len(rows)


# ---------------------------------------------------------------------------
# Reconciliation result
# ---------------------------------------------------------------------------

@dataclass
class ReconcileResult:
    matches: list[dict]
    local_only: list[dict]
    exchange_only: list[dict]
    consistent: bool

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Optional
from market_state_schema import ensure_utc

# ---------------------------------------------------------------------------
# Capital Sleeve Configuration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TenUSleeveConfig:
    initial_equity: Decimal = Decimal("10.0")
    external_top_up_allowed: bool = False
    profit_transfer_in_allowed: bool = False
    isolated_from_main_account: bool = True
    max_open_positions: int = 1
    risk_per_trade: Decimal = Decimal("0.15")  # 15%
    max_leverage: Decimal = Decimal("5.0")      # 5x
    daily_loss_halt: Decimal = Decimal("0.35")  # 35%
    peak_drawdown_halt: Decimal = Decimal("0.70") # 70%
    ruin_equity: Decimal = Decimal("2.0")
    cooldown_after_consecutive_losses: int = 3
    cooldown_bars: int = 96
    taker_fee: Decimal = Decimal("0.0005")      # 0.05%
    slippage: Decimal = Decimal("0.0002")       # 0.02%
    funding_cost_status: str = "not_applied"
    min_notionals: Mapping[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        decimal_ranges = {
            "initial_equity": (self.initial_equity, Decimal("0"), None),
            "risk_per_trade": (self.risk_per_trade, Decimal("0"), Decimal("1")),
            "max_leverage": (self.max_leverage, Decimal("0"), None),
            "daily_loss_halt": (self.daily_loss_halt, Decimal("0"), Decimal("1")),
            "peak_drawdown_halt": (self.peak_drawdown_halt, Decimal("0"), Decimal("1")),
            "ruin_equity": (self.ruin_equity, Decimal("0"), self.initial_equity),
            "taker_fee": (self.taker_fee, Decimal("0"), Decimal("1")),
            "slippage": (self.slippage, Decimal("0"), Decimal("1")),
        }
        for name, (value, lower, upper) in decimal_ranges.items():
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be Decimal")
            if value <= lower or (upper is not None and value >= upper):
                raise ValueError(f"invalid {name}: {value}")
        if self.max_open_positions != 1:
            raise ValueError("v1 requires max_open_positions == 1")
        if self.cooldown_after_consecutive_losses <= 0 or self.cooldown_bars <= 0:
            raise ValueError("cooldown settings must be positive")
        if self.external_top_up_allowed or self.profit_transfer_in_allowed:
            raise ValueError("v1 forbids capital transfers into the sleeve")
        if not self.isolated_from_main_account:
            raise ValueError("v1 must be isolated from the main account")
        if self.funding_cost_status != "not_applied":
            raise ValueError("v1 only supports funding_cost_status='not_applied'")
        normalized: dict[str, Decimal] = {}
        for symbol, value in self.min_notionals.items():
            if not symbol or not isinstance(value, Decimal) or value <= 0:
                raise ValueError(f"invalid min_notional for {symbol!r}: {value!r}")
            normalized[symbol] = value
        object.__setattr__(self, "min_notionals", MappingProxyType(normalized))

    @classmethod
    def from_research_protocol(cls, protocol: Any) -> "TenUSleeveConfig":
        """Bind symbol minimums to an already-loaded frozen protocol."""
        if protocol.config_fingerprint != protocol._compute_fingerprint():
            raise ValueError("research protocol fingerprint integrity check failed")
        minimum = Decimal(str(protocol.cost.min_notional))
        return cls(min_notionals={s: minimum for s in protocol.symbol_universe})

    def fingerprint(self) -> str:
        """Deterministic SHA-256 fingerprint of the configuration."""
        data = {
            "initial_equity": str(self.initial_equity),
            "external_top_up_allowed": self.external_top_up_allowed,
            "profit_transfer_in_allowed": self.profit_transfer_in_allowed,
            "isolated_from_main_account": self.isolated_from_main_account,
            "max_open_positions": self.max_open_positions,
            "risk_per_trade": str(self.risk_per_trade),
            "max_leverage": str(self.max_leverage),
            "daily_loss_halt": str(self.daily_loss_halt),
            "peak_drawdown_halt": str(self.peak_drawdown_halt),
            "ruin_equity": str(self.ruin_equity),
            "cooldown_after_consecutive_losses": self.cooldown_after_consecutive_losses,
            "cooldown_bars": self.cooldown_bars,
            "taker_fee": str(self.taker_fee),
            "slippage": str(self.slippage),
            "funding_cost_status": self.funding_cost_status,
            "min_notionals": {k: str(v) for k, v in sorted(self.min_notionals.items())},
        }
        blob = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Trade Event Schema
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TradeEvent:
    timestamp: str
    symbol: str
    side: str               # buy, sell, long, short
    entry_price: Decimal
    exit_price: Decimal
    stop_price: Decimal
    requested_notional: Optional[Decimal] = None
    exit_reason: str = ""
    bar_index: Optional[int] = None


# ---------------------------------------------------------------------------
# Account State Machine
# ---------------------------------------------------------------------------
class TenUSleeveAccount:
    def __init__(self, config: TenUSleeveConfig):
        self.config = config
        self.equity = config.initial_equity
        self.peak_equity = config.initial_equity
        self.max_drawdown = Decimal("0.0")
        self.state = "ACTIVE"
        self.consecutive_losses = 0
        self.cooldown_start_time: Optional[datetime] = None
        self.daily_start_equity = config.initial_equity
        self.daily_start_date: Optional[str] = None
        self.last_event_time: Optional[datetime] = None
        self.last_bar_index: Optional[int] = None
        self.cooldown_start_bar_index: Optional[int] = None
        self.open_positions = 0

        self.total_fees = Decimal("0.0")
        self.total_slippage = Decimal("0.0")
        self.accepted_trades: list[dict] = []
        self.skipped_trades: list[dict] = []
        self.state_transitions: list[dict] = []

    def top_up(self, amount: Decimal) -> None:
        raise PermissionError("external top-ups are forbidden for the 10U sleeve")

    def transfer_in(self, amount: Decimal) -> None:
        raise PermissionError("transfers from the main account are forbidden")

    def advance_clock(
        self, timestamp: str | datetime, bar_index: Optional[int] = None
    ) -> datetime:
        """Advance UTC-day and cooldown state without fabricating a trade."""
        event_time = ensure_utc(timestamp)
        if self.last_event_time is not None and event_time < self.last_event_time:
            raise ValueError("account clock cannot move backwards")
        self.last_event_time = event_time
        if bar_index is not None:
            if bar_index < 0:
                raise ValueError("bar_index must be non-negative")
            if self.last_bar_index is not None and bar_index < self.last_bar_index:
                raise ValueError("out-of-order bar_index")
            self.last_bar_index = bar_index

        event_date_str = event_time.strftime("%Y-%m-%d")
        if self.daily_start_date is None or event_date_str != self.daily_start_date:
            if self.state == "HALTED_DAILY_LOSS":
                self._transition("ACTIVE", event_time, f"New UTC day started ({event_date_str})")
            self.daily_start_date = event_date_str
            self.daily_start_equity = self.equity

        if self.state == "COOLDOWN" and self.cooldown_start_time is not None:
            if bar_index is not None and self.cooldown_start_bar_index is not None:
                elapsed_bars = bar_index - self.cooldown_start_bar_index
            else:
                elapsed_bars = int(
                    (event_time - self.cooldown_start_time).total_seconds() // 900
                )
            if elapsed_bars >= self.config.cooldown_bars:
                self._transition("ACTIVE", event_time, "Cooldown elapsed (96 completed 15m bars)")
                self.consecutive_losses = 0
        return event_time

    def _transition(self, target_state: str, timestamp: datetime, reason: str) -> None:
        prev_state = self.state
        self.state = target_state
        self.state_transitions.append({
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "from_state": prev_state,
            "to_state": target_state,
            "reason": reason,
        })

    def process_event(self, event: TradeEvent) -> dict:
        event_time = self.advance_clock(event.timestamp, event.bar_index)

        # Reject operations if not active
        if self.state != "ACTIVE":
            skip_record = {
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "reason": f"SKIP_ACCOUNT_{self.state}",
            }
            self.skipped_trades.append(skip_record)
            return skip_record

        # Fetch per-symbol min_notional
        min_notional = self.config.min_notionals.get(event.symbol)
        if min_notional is None:
            skip_record = {
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "reason": "SKIP_MIN_NOTIONAL_UNAVAILABLE",
            }
            self.skipped_trades.append(skip_record)
            return skip_record

        # Risk budget: 15% of current equity
        risk_budget = self.equity * self.config.risk_per_trade
        
        entry = event.entry_price
        stop = event.stop_price
        if entry <= 0:
            raise ValueError("Entry price must be positive")
        if event.side not in ("buy", "long", "sell", "short"):
            raise ValueError(f"Invalid trade side: {event.side!r}")
        if event.exit_price <= 0 or event.stop_price <= 0:
            raise ValueError("Exit and stop prices must be positive")
        if event.side in ("buy", "long") and stop >= entry:
            raise ValueError("long stop must be below entry")
        if event.side in ("sell", "short") and stop <= entry:
            raise ValueError("short stop must be above entry")
        
        stop_loss_pct = abs(entry - stop) / entry
        if stop_loss_pct <= 0:
            raise ValueError("Stop price must not be equal to entry price")

        # Factor double-sided fees/slippage into worst-case budget:
        # Total cost ratio = stop_loss_pct + taker_fee + slippage + exit_ratio * (taker_fee + slippage)
        exit_ratio = stop / entry
        total_cost_pct = stop_loss_pct + self.config.taker_fee + self.config.slippage + exit_ratio * (self.config.taker_fee + self.config.slippage)

        # Max allowed size based on risk and leverage limit
        notional_by_risk = risk_budget / total_cost_pct
        notional_by_leverage = self.equity * self.config.max_leverage
        
        caps = [notional_by_risk, notional_by_leverage]
        if event.requested_notional is not None:
            if event.requested_notional <= 0:
                raise ValueError("requested_notional must be positive")
            caps.append(event.requested_notional)
        calculated_notional = min(caps)
        calculated_notional = calculated_notional.quantize(
            Decimal("0.0001"), rounding=ROUND_DOWN
        )

        # Skip trade if calculated notional size is below min_notional
        if calculated_notional < min_notional:
            skip_record = {
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "reason": "SKIP_MIN_NOTIONAL",
                "calculated_notional": str(calculated_notional),
                "min_notional": str(min_notional),
            }
            self.skipped_trades.append(skip_record)
            return skip_record

        if self.open_positions >= self.config.max_open_positions:
            skip_record = {
                "timestamp": event.timestamp,
                "symbol": event.symbol,
                "reason": "SKIP_MAX_OPEN_POSITIONS",
            }
            self.skipped_trades.append(skip_record)
            return skip_record

        # Atomic round-trip simulator: reserve the one permitted slot until
        # the supplied exit is applied.
        self.open_positions += 1

        # Entry costs
        entry_fee = calculated_notional * self.config.taker_fee
        entry_slippage = calculated_notional * self.config.slippage
        self.total_fees += entry_fee
        self.total_slippage += entry_slippage

        # Execute trade & PnL calculation
        exit_p = event.exit_price
        if event.side in ("buy", "long"):
            raw_pnl = calculated_notional * (exit_p - entry) / entry
        elif event.side in ("sell", "short"):
            raw_pnl = calculated_notional * (entry - exit_p) / entry
        else:
            raise ValueError(f"Invalid trade side: '{event.side}'")

        # Exit costs
        exit_notional = calculated_notional * (exit_p / entry)
        exit_fee = exit_notional * self.config.taker_fee
        exit_slippage = exit_notional * self.config.slippage
        self.total_fees += exit_fee
        self.total_slippage += exit_slippage

        # Net PnL
        net_pnl = raw_pnl - entry_fee - entry_slippage - exit_fee - exit_slippage
        net_pnl = net_pnl.quantize(Decimal("0.0001"))

        old_equity = self.equity
        uncapped_net_pnl = net_pnl
        insolvency_shortfall = max(Decimal("0"), -(old_equity + net_pnl))
        net_pnl = max(net_pnl, -old_equity)
        self.equity += net_pnl
        self.open_positions -= 1
        self.peak_equity = max(self.peak_equity, self.equity)
        
        # Calculate drawdown
        drawdown = min(
            Decimal("1"),
            (self.peak_equity - self.equity) / self.peak_equity,
        )
        self.max_drawdown = max(self.max_drawdown, drawdown)

        is_gap_exceeded = (
            uncapped_net_pnl < 0 and abs(uncapped_net_pnl) > risk_budget
        )

        trade_record = {
            "timestamp": event.timestamp,
            "symbol": event.symbol,
            "side": event.side,
            "entry_price": str(entry),
            "exit_price": str(exit_p),
            "stop_price": str(stop),
            "notional": str(calculated_notional),
            "net_pnl": str(net_pnl),
            "equity_before": str(old_equity),
            "equity_after": str(self.equity),
            "is_gap_exceeded": is_gap_exceeded,
            "uncapped_net_pnl": str(uncapped_net_pnl),
            "insolvency_shortfall": str(insolvency_shortfall),
            "exit_reason": event.exit_reason,
        }
        self.accepted_trades.append(trade_record)

        # Track consecutive losses
        if net_pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # State updates
        # 1. Ruin check
        if self.equity <= self.config.ruin_equity:
            self._transition("RUINED", event_time, f"Equity ({self.equity}) <= ruin_equity ({self.config.ruin_equity})")
        # 2. Drawdown check
        elif drawdown >= self.config.peak_drawdown_halt:
            self._transition("HALTED_DRAWDOWN", event_time, f"Drawdown ({drawdown:.1%}) >= peak_drawdown_halt ({self.config.peak_drawdown_halt:.1%})")
        # 3. Daily loss check
        elif self.equity <= self.daily_start_equity * (Decimal("1.0") - self.config.daily_loss_halt):
            self._transition("HALTED_DAILY_LOSS", event_time, f"Daily equity drop exceeds {self.config.daily_loss_halt:.1%}")
        # 4. Cooldown check
        elif self.consecutive_losses >= self.config.cooldown_after_consecutive_losses:
            self.cooldown_start_time = event_time
            self.cooldown_start_bar_index = event.bar_index
            self._transition("COOLDOWN", event_time, f"Consecutive losses reached {self.config.cooldown_after_consecutive_losses}")

        return trade_record


# ---------------------------------------------------------------------------
# Stress Simulator Engine
# ---------------------------------------------------------------------------
def run_simulation(config: TenUSleeveConfig, events: list[TradeEvent]) -> dict[str, Any]:
    account = TenUSleeveAccount(config)
    for event in events:
        account.process_event(event)

    return {
        "starting_equity": str(config.initial_equity),
        "ending_equity": str(account.equity),
        "peak_equity": str(account.peak_equity),
        "max_drawdown": f"{account.max_drawdown:.4f}",
        "total_fees": str(account.total_fees.quantize(Decimal("0.0001"))),
        "total_slippage": str(account.total_slippage.quantize(Decimal("0.0001"))),
        "accepted_trades": account.accepted_trades,
        "skipped_trades": account.skipped_trades,
        "state_transitions": account.state_transitions,
        "ruin_probability": "not_estimated",
        "config_fingerprint": config.fingerprint(),
        "funding_cost_status": config.funding_cost_status,
        "formal_status": "infrastructure_only",
    }


def build_fixed_stress_report() -> dict[str, Any]:
    """Build the eight preregistered deterministic infrastructure scenarios."""
    d = Decimal
    base = TenUSleeveConfig(min_notionals={"BTC-USDT-SWAP": d("5")})

    def event(ts: str, exit_price: str, stop: str = "95", **kwargs: Any) -> TradeEvent:
        return TradeEvent(
            timestamp=ts,
            symbol="BTC-USDT-SWAP",
            side="long",
            entry_price=d("100"),
            exit_price=d(exit_price),
            stop_price=d(stop),
            **kwargs,
        )

    scenarios: dict[str, tuple[TenUSleeveConfig, list[TradeEvent]]] = {
        "scenario_1_consecutive_losses": (
            base,
            [event(f"2026-07-16T{hour:02d}:00:00Z", "98", "98", bar_index=i)
             for i, hour in enumerate(range(12, 17))],
        ),
        "scenario_2_win_then_losses": (
            base,
            [event("2026-07-16T12:00:00Z", "110", "90")]
            + [event(f"2026-07-16T{hour:02d}:00:00Z", "98", "98")
               for hour in range(13, 17)],
        ),
        "scenario_3_below_min_notional": (
            TenUSleeveConfig(min_notionals={"BTC-USDT-SWAP": d("15")}),
            [event("2026-07-16T12:00:00Z", "90", "90")],
        ),
        "scenario_4_daily_loss_halt": (
            base,
            [
                event("2026-07-16T12:00:00Z", "80"),
                event("2026-07-16T13:00:00Z", "105"),
                event("2026-07-17T01:00:00Z", "105"),
            ],
        ),
        "scenario_5_peak_drawdown_halt": (
            base,
            [
                event("2026-07-16T12:00:00Z", "140", "80"),
                event("2026-07-16T13:00:00Z", "72"),
                event("2026-07-17T12:00:00Z", "110", "90"),
            ],
        ),
        "scenario_6_ruined": (
            base,
            [
                event("2026-07-16T12:00:00Z", "40"),
                event("2026-07-17T12:00:00Z", "200", "90"),
            ],
        ),
        "scenario_7_compounding": (
            base,
            [
                event("2026-07-16T12:00:00Z", "200", "90"),
                event("2026-07-16T13:00:00Z", "105", "90"),
            ],
        ),
        "scenario_8_extreme_gap": (
            base,
            [event("2026-07-16T12:00:00Z", "50")],
        ),
    }
    return {
        name: run_simulation(config, events)
        for name, (config, events) in scenarios.items()
    }


def write_fixed_stress_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_fixed_stress_report(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    write_fixed_stress_report(
        Path(__file__).resolve().parent / "reports" / "ten_u_sleeve_stress_v1.json"
    )

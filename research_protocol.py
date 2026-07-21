"""Frozen Research Protocol — reproducibility guard for all backtests and OOS.

This module defines the *single* configuration that every Formation, Validation,
and OOS run must obey.  Any deviation (different cost model, different symbol
set, different parameter hash) is detected and rejected before a backtest runs.

Usage::

    from research_protocol import ResearchProtocol, PROTOCOL_V1
    protocol = ResearchProtocol.create_v1(data_cutoff="2026-07-16")
    protocol.save(Path("reports/research_protocol_v1.json"))
    protocol.write_markdown(Path("docs/research_protocol_v1.md"))

    # In backtester / OOS runner:
    ResearchProtocol.validate_against(protocol, backtest_config)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import BacktestConfig, SymbolRisk
from market import FeatureBar
from market_state_schema import (
    get_market_state_config_fingerprint,
    get_market_state_schema_version,
)

# ---------------------------------------------------------------------------
# Protocol version — bump when any rule changes.
# ---------------------------------------------------------------------------
PROTOCOL_V1 = "v1.1.0"


def _fingerprint(obj: Any) -> str:
    """Deterministic SHA-256 of a JSON-serialisable object."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Market state config fingerprint — binds protocol to market state definition.
# ---------------------------------------------------------------------------
def _market_state_config_fingerprint() -> str:
    """Return the canonical, full market-state configuration fingerprint."""
    return get_market_state_config_fingerprint()


def _market_state_schema_version() -> str:
    """Return the canonical market-state schema version."""
    return get_market_state_schema_version()


# ---------------------------------------------------------------------------
# Split boundaries — explicit absolute timestamps for each phase.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SplitBoundaries:
    """Absolute timestamp boundaries for Formation / Validation / OOS splits."""

    formation_start_ts: int
    formation_end_ts: int
    validation_start_ts: int
    validation_end_ts: int
    oos_start_ts: int
    oos_end_ts: int

    formation_bars: int
    validation_bars: int
    oos_bars: int
    formation_raw_bars: int
    validation_raw_bars: int
    oos_raw_bars: int
    purge_bars_total: int
    embargo_bars_total: int

    # Purge ranges (bars excluded from trading near split boundaries)
    purge_ranges: tuple[tuple[int, int], ...]  # (start_ts, end_ts) pairs
    # Embargo ranges (gap between phases)
    embargo_ranges: tuple[tuple[int, int], ...]

    def to_dict(self) -> dict:
        return {
            "formation_start_ts": self.formation_start_ts,
            "formation_end_ts": self.formation_end_ts,
            "validation_start_ts": self.validation_start_ts,
            "validation_end_ts": self.validation_end_ts,
            "oos_start_ts": self.oos_start_ts,
            "oos_end_ts": self.oos_end_ts,
            "formation_bars": self.formation_bars,
            "validation_bars": self.validation_bars,
            "oos_bars": self.oos_bars,
            "formation_raw_bars": self.formation_raw_bars,
            "validation_raw_bars": self.validation_raw_bars,
            "oos_raw_bars": self.oos_raw_bars,
            "purge_bars": self.purge_bars_total,
            "embargo_bars": self.embargo_bars_total,
            "purge_ranges": list(self.purge_ranges),
            "embargo_ranges": list(self.embargo_ranges),
        }


def slice_market(
    market: dict[str, list[FeatureBar]],
    start_ts: int,
    end_ts: int,
    warmup_bars: int = 260,
    bar_duration_ms: int = 900_000,
) -> tuple[dict[str, list[FeatureBar]], dict[str, list[FeatureBar]]]:
    """Slice market data into warmup and trading portions.

    Parameters
    ----------
    market : dict
        Full market data keyed by symbol.
    start_ts : int
        First ts of the trading window (inclusive).
    end_ts : int
        Last ts of the trading window (exclusive).
    warmup_bars : int
        Number of bars before start_ts to include for indicator warmup.
    bar_duration_ms : int
        Duration of one bar in milliseconds (default 900000 = 15m).

    Returns
    -------
    (warmup_market, trading_market)
        warmup_market: bars in [start_ts - warmup_bars * bar_duration, start_ts)
        trading_market: bars in [start_ts, end_ts)
    """
    warmup_start = start_ts - warmup_bars * bar_duration_ms
    warmup_result: dict[str, list[FeatureBar]] = {}
    trading_result: dict[str, list[FeatureBar]] = {}

    for symbol, bars in market.items():
        warmup = [b for b in bars if warmup_start <= b.ts < start_ts]
        trading = [b for b in bars if start_ts <= b.ts < end_ts]
        if warmup:
            warmup_result[symbol] = warmup
        if trading:
            trading_result[symbol] = trading

    return warmup_result, trading_result


def enforce_data_cutoff(
    market: dict[str, list[FeatureBar]],
    cutoff_date: str,
    *,
    bar_duration_ms: int = 900_000,
) -> tuple[dict[str, list[FeatureBar]], int]:
    """Remove bars after the data cutoff date.

    Parameters
    ----------
    market : dict
        Full market data.
    cutoff_date : str
        ISO date string, e.g. "2026-07-16".

    Returns
    -------
    (filtered_market, removed_count)
    """
    cutoff_day = datetime.fromisoformat(cutoff_date + "T00:00:00+00:00")
    cutoff_exclusive_ts = int((cutoff_day + timedelta(days=1)).timestamp() * 1000)
    removed = 0
    filtered: dict[str, list[FeatureBar]] = {}
    for symbol, bars in market.items():
        before = len(bars)
        kept = [b for b in bars if b.ts + bar_duration_ms <= cutoff_exclusive_ts]
        removed += before - len(kept)
        if kept:
            filtered[symbol] = kept
    return filtered, removed


def assess_symbol_coverage(
    market: dict[str, list[FeatureBar]],
    required_symbols: tuple[str, ...],
    boundaries: SplitBoundaries,
    *,
    min_trading_bars: int,
    warmup_bars: int,
    bar_duration_ms: int,
) -> dict[str, Any]:
    """Audit strict fixed-universe coverage without silently shrinking it."""
    loaded = set(market)
    required = set(required_symbols)
    per_phase: dict[str, dict[str, dict[str, Any]]] = {}
    phase_ranges = {
        "formation": (boundaries.formation_start_ts, boundaries.formation_end_ts),
        "validation": (boundaries.validation_start_ts, boundaries.validation_end_ts),
        "oos": (boundaries.oos_start_ts, boundaries.oos_end_ts),
    }
    issues: list[str] = []
    for phase, (start_ts, end_ts) in phase_ranges.items():
        rows: dict[str, dict[str, Any]] = {}
        for symbol in required_symbols:
            bars = market.get(symbol, [])
            trading = sum(start_ts <= bar.ts < end_ts for bar in bars)
            warmup = sum(
                start_ts - warmup_bars * bar_duration_ms <= bar.ts < start_ts
                for bar in bars
            )
            warmup_required = 0 if phase == "formation" else warmup_bars
            ok = trading >= min_trading_bars and warmup >= warmup_required
            rows[symbol] = {
                "trading_bars": trading,
                "warmup_bars": warmup,
                "required_trading_bars": min_trading_bars,
                "required_warmup_bars": warmup_required,
                "status": "PASS" if ok else "FAIL",
            }
            if not ok:
                issues.append(
                    f"{phase}:{symbol}:trading={trading}/{min_trading_bars},"
                    f"warmup={warmup}/{warmup_required}"
                )
        per_phase[phase] = rows
    missing = sorted(required - loaded)
    for symbol in missing:
        issues.append(f"missing_symbol:{symbol}")
    return {
        "policy": "strict_fixed",
        "required_symbols": list(required_symbols),
        "loaded_symbols": sorted(loaded & required),
        "missing_symbols": missing,
        "per_phase_symbol_coverage": per_phase,
        "issues": issues,
        "coverage_status": "PASS" if not issues else "FAIL",
    }


# ---------------------------------------------------------------------------
# Fixed symbol universe — never modified by window length.
# ---------------------------------------------------------------------------
FIXED_SYMBOL_UNIVERSE: tuple[str, ...] = (
    "AAVE-USDT-SWAP",
    "ADA-USDT-SWAP",
    "APT-USDT-SWAP",
    "ARB-USDT-SWAP",
    "ATOM-USDT-SWAP",
    "AVAX-USDT-SWAP",
    "BNB-USDT-SWAP",
    "BTC-USDT-SWAP",
    "CRV-USDT-SWAP",
    "DOGE-USDT-SWAP",
    "DOT-USDT-SWAP",
    "DYDX-USDT-SWAP",
    "ETH-USDT-SWAP",
    "FIL-USDT-SWAP",
    "IMX-USDT-SWAP",
    "INJ-USDT-SWAP",
    "LINK-USDT-SWAP",
    "LTC-USDT-SWAP",
    "NEAR-USDT-SWAP",
    "OP-USDT-SWAP",
    "RENDER-USDT-SWAP",
    "SOL-USDT-SWAP",
    "STX-USDT-SWAP",
    "SUI-USDT-SWAP",
    "TIA-USDT-SWAP",
    "TRX-USDT-SWAP",
    "UNI-USDT-SWAP",
    "XRP-USDT-SWAP",
)


# ---------------------------------------------------------------------------
# Unified cost model — single source of truth for every backtest.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CostModel:
    """All costs are one-way unless noted.  Funding is applied per 8h bar."""

    taker_fee: float = 0.0005          # 0.05% one-way
    slippage: float = 0.0002           # 0.02% one-way
    # Funding rate is read from data; this is the assumed rate when data
    # is missing (positive = longs pay shorts).
    default_funding_rate: float = 0.0001
    funding_interval_hours: int = 8
    min_notional: float = 5.0          # minimum order size in USDT

    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))


# ---------------------------------------------------------------------------
# Formation / Validation / OOS split rules.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DataSplit:
    """Defines the train/validation/test boundaries.

    All bars with ``ts < formation_end_ts`` are Formation.
    All bars with ``formation_end_ts <= ts < validation_end_ts`` are Validation.
    All bars with ``ts >= validation_end_ts`` are OOS.

    ``embargo_bars`` is the gap between Formation→Validation and
    Validation→OOS to prevent label leakage from look-ahead indicators.
    ``purge_bars`` is the minimum distance a labelled sample must keep
    from the split boundary.
    """

    formation_fraction: float = 0.60
    validation_fraction: float = 0.20
    oos_fraction: float = 0.20
    embargo_bars: int = 96          # 1 day at 15m
    purge_bars: int = 48            # 12 hours at 15m

    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))

    def compute_boundaries(
        self,
        full_timeline: list[int],
        *,
        bar_duration_ms: int = 900_000,
    ) -> SplitBoundaries:
        """Compute absolute timestamp boundaries from a sorted timeline.

        Parameters
        ----------
        full_timeline : list[int]
            Sorted list of all bar timestamps.

        Returns
        -------
        SplitBoundaries
            Absolute boundaries for each phase, plus purge/embargo ranges.
        """
        n = len(full_timeline)
        if n < 10:
            raise ValueError(f"Timeline too short ({n} bars) for split")

        if bar_duration_ms <= 0:
            raise ValueError("bar_duration_ms must be positive")
        formation_raw_end_idx = int(n * self.formation_fraction)
        validation_raw_end_idx = int(n * (self.formation_fraction + self.validation_fraction))
        if not (0 < formation_raw_end_idx < validation_raw_end_idx < n):
            raise ValueError("split fractions do not produce three non-empty raw phases")

        formation_trade_end_idx = formation_raw_end_idx - self.purge_bars
        validation_start_idx = formation_raw_end_idx + self.embargo_bars
        validation_trade_end_idx = validation_raw_end_idx - self.purge_bars
        oos_start_idx = validation_raw_end_idx + self.embargo_bars
        if formation_trade_end_idx <= 0 or validation_start_idx >= validation_trade_end_idx or oos_start_idx >= n:
            raise ValueError(
                "timeline too short for configured purge/embargo; no usable three-phase split"
            )

        # Every end timestamp is exclusive: it is the first excluded bar.
        formation_start = full_timeline[0]
        formation_end = full_timeline[formation_trade_end_idx]
        validation_start = full_timeline[validation_start_idx]
        validation_end = full_timeline[validation_trade_end_idx]
        oos_start = full_timeline[oos_start_idx]
        oos_end = full_timeline[-1] + bar_duration_ms

        purge_1 = (full_timeline[formation_trade_end_idx], full_timeline[formation_raw_end_idx])
        embargo_1 = (full_timeline[formation_raw_end_idx], full_timeline[validation_start_idx])
        purge_2 = (full_timeline[validation_trade_end_idx], full_timeline[validation_raw_end_idx])
        embargo_2 = (full_timeline[validation_raw_end_idx], full_timeline[oos_start_idx])

        return SplitBoundaries(
            formation_start_ts=formation_start,
            formation_end_ts=formation_end,
            validation_start_ts=validation_start,
            validation_end_ts=validation_end,
            oos_start_ts=oos_start,
            oos_end_ts=oos_end,
            formation_bars=formation_trade_end_idx,
            validation_bars=validation_trade_end_idx - validation_start_idx,
            oos_bars=n - oos_start_idx,
            formation_raw_bars=formation_raw_end_idx,
            validation_raw_bars=validation_raw_end_idx - formation_raw_end_idx,
            oos_raw_bars=n - validation_raw_end_idx,
            purge_bars_total=self.purge_bars * 2,
            embargo_bars_total=self.embargo_bars * 2,
            purge_ranges=(purge_1, purge_2),
            embargo_ranges=(embargo_1, embargo_2),
        )


# ---------------------------------------------------------------------------
# Parameter freeze — the ONLY config allowed in formal validation.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class FrozenParams:
    """Immutable backtest parameters.  Any change = new fingerprint."""

    # Core sizing
    risk_per_trade: float = 0.13
    max_margin_fraction: float = 0.65
    max_total_margin_fraction: float = 0.55
    max_positions: int = 2
    active_symbol_limit: int = 6
    start_equity: float = 10.0

    # Stops / targets (ATR multiples)
    stop_atr: float = 2.8
    take_profit_atr: float = 1.8
    trailing_atr: float = 2.34
    max_hold_bars: int = 8

    # Range regime
    range_stop_atr: float = 2.0
    range_take_profit_atr: float = 0.85
    range_trailing_atr: float = 1.56
    range_max_hold_bars: int = 8

    # Score gate
    min_score: float = 2.5

    # Cooldown
    cooldown_bars: int = 24
    loss_cooldown_bars: int = 48

    # Regime toggles
    enabled_regimes: tuple[str, ...] = ("uptrend", "downtrend", "transition", "range")

    # Attack module
    enable_attack_module: bool = False
    attack_min_score: float = 4.5
    attack_risk_per_trade: float = 0.025

    # Selector
    selector_lookback_bars: int = 96 * 21
    selector_min_avg_quote: float = 250_000.0
    selector_max_micro_noise: float = 0.0072

    # Min notional (must match cost model)
    min_notional: float = 5.0

    def fingerprint(self) -> str:
        return _fingerprint(asdict(self))

    def to_backtest_config(
        self,
        cost: CostModel,
        symbol_universe: tuple[str, ...] = FIXED_SYMBOL_UNIVERSE,
    ) -> BacktestConfig:
        """Build a BacktestConfig from frozen params + cost model.

        This is the ONLY sanctioned way to create a config for formal
        validation / OOS.  Window-specific overrides are forbidden.
        """
        base = BacktestConfig()
        leverage_caps = {
            symbol: SymbolRisk(
                max_leverage=(base.leverage_caps.get(symbol) or SymbolRisk(10.0)).max_leverage,
                min_notional=cost.min_notional,
            )
            for symbol in symbol_universe
        }
        return BacktestConfig(
            start_equity=self.start_equity,
            taker_fee=cost.taker_fee,
            slippage=cost.slippage,
            risk_per_trade=self.risk_per_trade,
            max_margin_fraction=self.max_margin_fraction,
            max_total_margin_fraction=self.max_total_margin_fraction,
            max_positions=self.max_positions,
            active_symbol_limit=self.active_symbol_limit,
            stop_atr=self.stop_atr,
            take_profit_atr=self.take_profit_atr,
            trailing_atr=self.trailing_atr,
            max_hold_bars=self.max_hold_bars,
            range_stop_atr=self.range_stop_atr,
            range_take_profit_atr=self.range_take_profit_atr,
            range_trailing_atr=self.range_trailing_atr,
            range_max_hold_bars=self.range_max_hold_bars,
            min_score=self.min_score,
            cooldown_bars=self.cooldown_bars,
            loss_cooldown_bars=self.loss_cooldown_bars,
            enabled_regimes=tuple(self.enabled_regimes),
            enable_attack_module=self.enable_attack_module,
            attack_min_score=self.attack_min_score,
            attack_risk_per_trade=self.attack_risk_per_trade,
            selector_lookback_bars=self.selector_lookback_bars,
            selector_min_avg_quote=self.selector_min_avg_quote,
            selector_max_micro_noise=self.selector_max_micro_noise,
            # CRITICAL: disable window-specific profiles
            enable_target_window_profiles=False,
            enable_long_window_aggressive_profile=False,
            # Safety: no live trading
            enable_rule_trading=False,
            enable_pairs_trading=False,
            allowed_symbols=symbol_universe,
            leverage_caps=leverage_caps,
            min_bars=260,
            # No window-dependent validation targets
            validation_target_win_rate=0.0,
            validation_target_profit=0.0,
            validation_target_profit_by_window={},
            validation_target_returns={},
            windows_days=(),
        )


# ---------------------------------------------------------------------------
# Regime definition version — controls how regimes are classified.
# ---------------------------------------------------------------------------
REGIME_DEFINITION_VERSION = "v1.0.0"


# ---------------------------------------------------------------------------
# The protocol itself.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ResearchProtocol:
    """Machine-readable frozen research protocol."""

    version: str
    created_at: str
    data_cutoff: str                # ISO date, e.g. "2026-07-16"
    data_source: str                # e.g. "okx_15m_quantify"
    timeframe_minutes: int = 15

    # Sub-specs
    cost: CostModel = field(default_factory=CostModel)
    split: DataSplit = field(default_factory=DataSplit)
    params: FrozenParams = field(default_factory=FrozenParams)
    regime_definition_version: str = REGIME_DEFINITION_VERSION

    # Universe
    symbol_universe: tuple[str, ...] = FIXED_SYMBOL_UNIVERSE
    universe_selection: str = "fixed"  # "fixed" or "dynamic"
    universe_exclusions: tuple[tuple[str, str], ...] = (
        (
            "SEI-USDT-SWAP",
            "excluded_before first Formation run: zero bars in frozen Formation window",
        ),
    )

    # Minimums
    min_formation_trades: int = 30
    min_validation_trades: int = 15
    min_oos_trades: int = 30  # ≥30 to allow PASS/FAIL; <30 = insufficient_evidence
    min_oos_win_rate: float = 0.50
    min_oos_return_pct: float = 0.0

    # Market state config binding
    market_state_config_fingerprint: str = ""
    market_state_schema_version: str = ""

    # Funding cost status: "applied", "not_applied", "missing"
    funding_cost_status: str = "not_applied"

    # Composite fingerprint — derived from sub-fingerprints.
    config_fingerprint: str = ""

    # ---- Prohibited behaviours (documentation only, enforced in code) ----
    prohibited_behaviours: tuple[str, ...] = (
        "window_specific_parameters",
        "post_hoc_symbol_selection",
        "post_hoc_timeframe_selection",
        "future_data_leakage",
        "event_cumulative_as_account_return",
        "window_dependent_validation_targets",
        "dynamic_universe_per_window",
        "overfitting_to_formation_period",
        "silent_cost_omission",
        "same_report_mixed_cost_models",
    )

    allowed_research_behaviours: tuple[str, ...] = (
        "walk_forward_with_fixed_params",
        "OOS_evaluation_with_frozen_protocol",
        "regime_conditioned_analysis_with_same_params",
        "candidate_signal_with_external_signal_provider",
        "parameter_grid_search_on_formation_only",
    )

    def __post_init__(self) -> None:
        # Compute market state config fingerprint if not set
        if not self.market_state_config_fingerprint:
            object.__setattr__(self, "market_state_config_fingerprint", _market_state_config_fingerprint())
        if not self.market_state_schema_version:
            object.__setattr__(self, "market_state_schema_version", _market_state_schema_version())
        if not self.config_fingerprint:
            fp = self._compute_fingerprint()
            object.__setattr__(self, "config_fingerprint", fp)

    def _compute_fingerprint(self) -> str:
        parts = {
            "version": self.version,
            "data_cutoff": self.data_cutoff,
            "data_source": self.data_source,
            "timeframe_minutes": self.timeframe_minutes,
            "cost": self.cost.fingerprint(),
            "split": self.split.fingerprint(),
            "params": self.params.fingerprint(),
            "regime_definition_version": self.regime_definition_version,
            "symbol_universe": _fingerprint(list(self.symbol_universe)),
            "universe_selection": self.universe_selection,
            "universe_exclusions": self.universe_exclusions,
            "min_formation_trades": self.min_formation_trades,
            "min_validation_trades": self.min_validation_trades,
            "min_oos_trades": self.min_oos_trades,
            "min_oos_win_rate": self.min_oos_win_rate,
            "min_oos_return_pct": self.min_oos_return_pct,
            "market_state_config_fingerprint": self.market_state_config_fingerprint,
            "market_state_schema_version": self.market_state_schema_version,
            "funding_cost_status": self.funding_cost_status,
        }
        return _fingerprint(parts)

    # ---- Factory --------------------------------------------------------
    @classmethod
    def create_v1(
        cls,
        data_cutoff: str = "2026-07-16",
        data_source: str = "okx_15m_quantify",
        funding_cost_status: str = "not_applied",
    ) -> ResearchProtocol:
        return cls(
            version=PROTOCOL_V1,
            created_at=datetime.now(timezone.utc).isoformat(),
            data_cutoff=data_cutoff,
            data_source=data_source,
            funding_cost_status=funding_cost_status,
        )

    # ---- Persistence ----------------------------------------------------
    def to_dict(self) -> dict:
        d = asdict(self)
        d["symbol_universe"] = list(self.symbol_universe)
        d["prohibited_behaviours"] = list(self.prohibited_behaviours)
        d["allowed_research_behaviours"] = list(self.allowed_research_behaviours)
        # Frozen tuple fields need to be lists for JSON
        if "enabled_regimes" in d.get("params", {}):
            d["params"]["enabled_regimes"] = list(d["params"]["enabled_regimes"])
        return d

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> ResearchProtocol:
        """Load protocol from JSON and verify fingerprint integrity.

        Raises ValueError if the stored fingerprint does not match the
        recomputed fingerprint (indicates file tampering).
        """
        raw = json.loads(path.read_text(encoding="utf-8"))
        cost = CostModel(**raw["cost"])
        split = DataSplit(**raw["split"])
        params = FrozenParams(**raw["params"])
        stored_fingerprint = raw.get("config_fingerprint", "")

        protocol = cls(
            version=raw["version"],
            created_at=raw["created_at"],
            data_cutoff=raw["data_cutoff"],
            data_source=raw["data_source"],
            timeframe_minutes=raw["timeframe_minutes"],
            cost=cost,
            split=split,
            params=params,
            regime_definition_version=raw["regime_definition_version"],
            symbol_universe=tuple(raw["symbol_universe"]),
            universe_selection=raw["universe_selection"],
            universe_exclusions=tuple(
                tuple(item) for item in raw.get("universe_exclusions", [])
            ),
            min_formation_trades=raw["min_formation_trades"],
            min_validation_trades=raw["min_validation_trades"],
            min_oos_trades=raw["min_oos_trades"],
            min_oos_win_rate=raw["min_oos_win_rate"],
            min_oos_return_pct=raw["min_oos_return_pct"],
            market_state_config_fingerprint=raw.get("market_state_config_fingerprint", ""),
            market_state_schema_version=raw.get("market_state_schema_version", ""),
            funding_cost_status=raw.get("funding_cost_status", "not_applied"),
            config_fingerprint="",  # force recomputation
        )

        # Verify fingerprint integrity
        recomputed = protocol._compute_fingerprint()
        if stored_fingerprint and stored_fingerprint != recomputed:
            raise ValueError(
                f"Fingerprint mismatch: file may have been tampered.\n"
                f"  Stored:    {stored_fingerprint}\n"
                f"  Recomputed: {recomputed}"
            )

        current_market_fp = _market_state_config_fingerprint()
        current_schema_version = _market_state_schema_version()
        if protocol.market_state_config_fingerprint != current_market_fp:
            raise ValueError(
                "market_state_contract_mismatch: configuration fingerprint differs "
                f"(stored={protocol.market_state_config_fingerprint}, current={current_market_fp})"
            )
        if protocol.market_state_schema_version != current_schema_version:
            raise ValueError(
                "market_state_contract_mismatch: schema version differs "
                f"(stored={protocol.market_state_schema_version}, current={current_schema_version})"
            )

        return protocol

    # ---- Validation -----------------------------------------------------
    @staticmethod
    def validate_against(
        protocol: ResearchProtocol,
        config: BacktestConfig,
        *,
        strict: bool = True,
    ) -> list[str]:
        """Check that a BacktestConfig obeys the protocol.

        Returns a list of violations.  Empty = pass.
        """
        violations: list[str] = []
        p = protocol.params
        c = config

        # Cost model
        if abs(c.taker_fee - protocol.cost.taker_fee) > 1e-8:
            violations.append(
                f"taker_fee mismatch: {c.taker_fee} != {protocol.cost.taker_fee}"
            )
        if abs(c.slippage - protocol.cost.slippage) > 1e-8:
            violations.append(
                f"slippage mismatch: {c.slippage} != {protocol.cost.slippage}"
            )

        # Window-specific profiles MUST be off
        if c.enable_target_window_profiles:
            violations.append(
                "enable_target_window_profiles must be False (window-specific params prohibited)"
            )
        if c.enable_long_window_aggressive_profile:
            violations.append(
                "enable_long_window_aggressive_profile must be False"
            )

        # Safety
        if c.enable_rule_trading:
            violations.append("enable_rule_trading must be False")
        if c.enable_pairs_trading:
            violations.append("enable_pairs_trading must be False")

        # Validate ALL FrozenParams fields against config
        # This ensures no field is missed when FrozenParams changes
        _PARAM_TO_CONFIG = {
            "risk_per_trade": "risk_per_trade",
            "max_margin_fraction": "max_margin_fraction",
            "max_total_margin_fraction": "max_total_margin_fraction",
            "max_positions": "max_positions",
            "active_symbol_limit": "active_symbol_limit",
            "start_equity": "start_equity",
            "stop_atr": "stop_atr",
            "take_profit_atr": "take_profit_atr",
            "trailing_atr": "trailing_atr",
            "max_hold_bars": "max_hold_bars",
            "range_stop_atr": "range_stop_atr",
            "range_take_profit_atr": "range_take_profit_atr",
            "range_trailing_atr": "range_trailing_atr",
            "range_max_hold_bars": "range_max_hold_bars",
            "min_score": "min_score",
            "cooldown_bars": "cooldown_bars",
            "loss_cooldown_bars": "loss_cooldown_bars",
            "enabled_regimes": "enabled_regimes",
            "enable_attack_module": "enable_attack_module",
            "attack_min_score": "attack_min_score",
            "attack_risk_per_trade": "attack_risk_per_trade",
            "selector_lookback_bars": "selector_lookback_bars",
            "selector_min_avg_quote": "selector_min_avg_quote",
            "selector_max_micro_noise": "selector_max_micro_noise",
        }

        for param_name, config_name in _PARAM_TO_CONFIG.items():
            expected = getattr(p, param_name, None)
            actual = getattr(c, config_name, None)
            if expected is None or actual is None:
                continue
            # Normalize tuples/lists for comparison (JSON deserializes as list)
            if isinstance(expected, (list, tuple)):
                expected = tuple(expected)
            if isinstance(actual, (list, tuple)):
                actual = tuple(actual)
            if actual != expected:
                violations.append(f"{param_name}: {actual} != {expected}")

        # Verify ALL FrozenParams fields are covered
        covered_fields = set(_PARAM_TO_CONFIG.keys()) | {"min_notional"}
        for fld in fields(FrozenParams):
            if fld.name not in covered_fields and fld.name != "min_notional":
                violations.append(
                    f"FrozenParams.{fld.name} not covered in validate_against()"
                )

        # min_notional: must match cost model
        if abs(p.min_notional - protocol.cost.min_notional) > 1e-8:
            violations.append(
                f"min_notional mismatch between params ({p.min_notional}) "
                f"and cost model ({protocol.cost.min_notional})"
            )
        for symbol in protocol.symbol_universe:
            symbol_risk = c.leverage_caps.get(symbol)
            if symbol_risk is None:
                violations.append(f"leverage_caps missing required symbol: {symbol}")
            elif abs(symbol_risk.min_notional - protocol.cost.min_notional) > 1e-8:
                violations.append(
                    f"min_notional mismatch for {symbol}: "
                    f"{symbol_risk.min_notional} != {protocol.cost.min_notional}"
                )

        # Validation targets must be zeroed (no window-dependent targets)
        if c.validation_target_win_rate != 0.0:
            violations.append(
                f"validation_target_win_rate must be 0.0, got {c.validation_target_win_rate}"
            )
        if c.validation_target_profit != 0.0:
            violations.append(
                f"validation_target_profit must be 0.0, got {c.validation_target_profit}"
            )
        if c.validation_target_profit_by_window:
            violations.append("validation_target_profit_by_window must be empty")
        if c.validation_target_returns:
            violations.append("validation_target_returns must be empty")

        # Symbol universe
        if strict and c.allowed_symbols:
            if set(c.allowed_symbols) != set(protocol.symbol_universe):
                violations.append(
                    f"allowed_symbols mismatch: {len(c.allowed_symbols)} symbols "
                    f"vs {len(protocol.symbol_universe)} in protocol"
                )

        # Funding cost status
        if protocol.funding_cost_status == "applied":
            violations.append(
                "funding_cost_status='applied' is not yet supported — "
                "backtester does not deduct funding from PnL"
            )

        return violations

    # ---- Markdown documentation -----------------------------------------
    def write_markdown(self, path: Path) -> str:
        lines = [
            f"# Research Protocol {self.version}",
            "",
            f"**Created:** {self.created_at}",
            f"**Data cutoff:** {self.data_cutoff}",
            f"**Data source:** {self.data_source}",
            f"**Timeframe:** {self.timeframe_minutes}m",
            f"**Config fingerprint:** `{self.config_fingerprint}`",
            "",
            "---",
            "",
            "## 1. Data Split",
            "",
            f"| Phase | Fraction |",
            f"|-------|----------|",
            f"| Formation | {self.split.formation_fraction:.0%} |",
            f"| Validation | {self.split.validation_fraction:.0%} |",
            f"| OOS | {self.split.oos_fraction:.0%} |",
            "",
            f"- **Embargo:** {self.split.embargo_bars} bars ({self.split.embargo_bars * self.timeframe_minutes / 60:.0f} hours)",
            f"- **Purge:** {self.split.purge_bars} bars ({self.split.purge_bars * self.timeframe_minutes / 60:.0f} hours)",
            "",
            "## 2. Cost Model",
            "",
            f"| Item | Value |",
            f"|------|-------|",
            f"| Taker fee (one-way) | {self.cost.taker_fee:.4%} |",
            f"| Slippage (one-way) | {self.cost.slippage:.4%} |",
            f"| Default funding rate | {self.cost.default_funding_rate:.4%} / {self.cost.funding_interval_hours}h |",
            f"| Min notional | {self.cost.min_notional} USDT |",
            "",
            "## 3. Frozen Parameters",
            "",
            f"| Parameter | Value |",
            f"|-----------|-------|",
            f"| risk_per_trade | {self.params.risk_per_trade} |",
            f"| max_margin_fraction | {self.params.max_margin_fraction} |",
            f"| max_total_margin_fraction | {self.params.max_total_margin_fraction} |",
            f"| max_positions | {self.params.max_positions} |",
            f"| active_symbol_limit | {self.params.active_symbol_limit} |",
            f"| start_equity | {self.params.start_equity} |",
            f"| stop_atr | {self.params.stop_atr} |",
            f"| take_profit_atr | {self.params.take_profit_atr} |",
            f"| trailing_atr | {self.params.trailing_atr} |",
            f"| max_hold_bars | {self.params.max_hold_bars} |",
            f"| range_stop_atr | {self.params.range_stop_atr} |",
            f"| range_take_profit_atr | {self.params.range_take_profit_atr} |",
            f"| range_trailing_atr | {self.params.range_trailing_atr} |",
            f"| min_score | {self.params.min_score} |",
            f"| cooldown_bars | {self.params.cooldown_bars} |",
            f"| loss_cooldown_bars | {self.params.loss_cooldown_bars} |",
            f"| enabled_regimes | {', '.join(self.params.enabled_regimes)} |",
            f"| enable_attack_module | {self.params.enable_attack_module} |",
            "",
            "## 4. Symbol Universe (fixed)",
            "",
        ]
        for sym in self.symbol_universe:
            lines.append(f"- {sym}")
        if self.universe_exclusions:
            lines.extend(["", "**Pre-Formation data exclusions:**"])
            for symbol, reason in self.universe_exclusions:
                lines.append(f"- {symbol}: {reason}")
        lines.extend([
            "",
            f"**Selection method:** {self.universe_selection}",
            "",
            "## 5. Regime Definition",
            "",
            f"**Version:** {self.regime_definition_version}",
            "",
            "## 6. Minimum Sample Requirements",
            "",
            f"| Phase | Min trades |",
            f"|-------|-----------|",
            f"| Formation | {self.min_formation_trades} |",
            f"| Validation | {self.min_validation_trades} |",
            f"| OOS | {self.min_oos_trades} |",
            "",
            f"- **OOS min win rate:** {self.min_oos_win_rate:.0%}",
            f"- **OOS min return:** {self.min_oos_return_pct}%",
            "",
            "**OOS evaluation tiers:**",
            "- < 15 trades: `insufficient_evidence`",
            "- 15–29 trades: `insufficient_evidence`",
            "- ≥ 30 trades: allow PASS/FAIL evaluation",
            "",
            "## 7. Market State Config Binding",
            "",
            f"- **Config fingerprint:** `{self.market_state_config_fingerprint}`",
            f"- **Schema version:** {self.market_state_schema_version}",
            "",
            "## 8. Funding Cost Status",
            "",
            f"**Status:** `{self.funding_cost_status}`",
            "",
            "The backtester currently does NOT deduct funding costs from PnL.",
            "Only taker fees and slippage are applied.",
            "Strategies that depend on funding data will FAIL validation.",
            "",
            "## 9. Report Return Semantics",
            "",
            "All return percentages are **account-equity returns**:",
            "",
            "    return_pct = (end_equity - start_equity) / start_equity * 100",
            "",
            "Cumulative event returns are **never** used as account returns.",
            "",
            "## 10. Prohibited Behaviours",
            "",
        ])
        for item in self.prohibited_behaviours:
            lines.append(f"- ~~{item}~~")
        lines.extend([
            "",
            "## 11. Allowed Research Behaviours",
            "",
        ])
        for item in self.allowed_research_behaviours:
            lines.append(f"- {item}")
        lines.extend([
            "",
            "---",
            "",
            "*This file is auto-generated by `research_protocol.py`. "
            "Do not edit manually.*",
        ])
        content = "\n".join(lines)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return content


# ---------------------------------------------------------------------------
# Legacy report audit — identify old reports that may be invalid.
# ---------------------------------------------------------------------------

# Patterns in report filenames that indicate window-specific configs
_WINDOW_REPORT_PATTERNS = (
    "30d", "365d", "180d", "90d", "60d", "14d", "7d",
    "goal_30d", "goal_365d", "monthly_goal",
    "staged_goal", "auto_switch",
)


def audit_old_reports(reports_dir: Path) -> dict:
    """Scan report directory for files that may violate the protocol.

    Returns a dict with 'valid', 'suspect', and 'invalid' lists.
    """
    result: dict[str, list[dict]] = {"valid": [], "suspect": [], "invalid": []}

    if not reports_dir.exists():
        return result

    for path in sorted(reports_dir.glob("*.json")):
        entry = {"path": str(path), "name": path.name}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            entry["reason"] = "unreadable JSON"
            result["invalid"].append(entry)
            continue

        reasons: list[str] = []

        # Some report files may have non-dict top-level (e.g. list)
        if not isinstance(data, dict):
            entry["reason"] = f"unexpected top-level type: {type(data).__name__}"
            result["invalid"].append(entry)
            continue

        # Check if report has window-specific config
        config = data.get("config", {})
        if not isinstance(config, dict):
            config = {}
        if config.get("enable_target_window_profiles", False):
            reasons.append("enable_target_window_profiles=True")
        if config.get("enable_long_window_aggressive_profile", False):
            reasons.append("enable_long_window_aggressive_profile=True")

        # Check for window-specific validation targets
        targets = config.get("validation_target_returns", {})
        if isinstance(targets, dict) and len(targets) > 1:
            reasons.append(f"window_dependent_targets: {list(targets.keys())}")

        # Check for multiple windows with different configs
        windows = data.get("windows", {})
        if isinstance(windows, dict) and len(windows) > 1:
            reasons.append(f"multi_window_report: {len(windows)} windows")

        # Check name patterns
        name_lower = path.name.lower()
        for pattern in _WINDOW_REPORT_PATTERNS:
            if pattern in name_lower:
                reasons.append(f"window_pattern_in_name: {pattern}")
                break

        entry["reasons"] = reasons
        if not reasons:
            result["valid"].append(entry)
        elif len(reasons) >= 2:
            result["invalid"].append(entry)
        else:
            result["suspect"].append(entry)

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Research Protocol tools")
    sub = parser.add_subparsers(dest="cmd")

    gen = sub.add_parser("generate", help="Generate protocol JSON + Markdown")
    gen.add_argument("--cutoff", default="2026-07-16", help="Data cutoff date")
    gen.add_argument("--source", default="okx_15m_quantify")
    gen.add_argument("--json-out", type=Path, default=Path("reports/research_protocol_v1.json"))
    gen.add_argument("--md-out", type=Path, default=Path("docs/research_protocol_v1.md"))

    audit = sub.add_parser("audit", help="Audit old reports")
    audit.add_argument("--reports-dir", type=Path, default=Path("reports"))

    chk = sub.add_parser("check", help="Check a backtest config against protocol")
    chk.add_argument("--protocol", type=Path, default=Path("reports/research_protocol_v1.json"))

    args = parser.parse_args()

    if args.cmd == "generate":
        protocol = ResearchProtocol.create_v1(
            data_cutoff=args.cutoff,
            data_source=args.source,
        )
        protocol.save(args.json_out)
        protocol.write_markdown(args.md_out)
        print(f"Protocol JSON: {args.json_out}")
        print(f"Protocol MD:   {args.md_out}")
        print(f"Fingerprint:   {protocol.config_fingerprint}")

    elif args.cmd == "audit":
        report = audit_old_reports(args.reports_dir)
        print(f"Valid:   {len(report['valid'])}")
        print(f"Suspect: {len(report['suspect'])}")
        print(f"Invalid: {len(report['invalid'])}")
        if report["invalid"]:
            print("\nInvalid reports:")
            for entry in report["invalid"]:
                print(f"  {entry['name']}: {entry.get('reasons', entry.get('reason', '?'))}")

    elif args.cmd == "check":
        protocol = ResearchProtocol.load(args.protocol)
        config = protocol.params.to_backtest_config(protocol.cost)
        violations = ResearchProtocol.validate_against(protocol, config)
        if violations:
            print("VIOLATIONS:")
            for v in violations:
                print(f"  - {v}")
        else:
            print("PASS: config matches protocol")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

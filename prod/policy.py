"""Operator hard constraints for the production track (2026-07-17).

Machine-readable source of truth used by admission, local paper, and CLI status.

Rules:
- Default start equity: 10 USDT
- Capital-sensitivity band: up to 500 USDT (hard ceiling)
- Production-bound symbols: BTC-USDT-SWAP, ETH-USDT-SWAP only
- Default pipeline: local paper only — never places OKX demo/live orders
- RAVE/LAB (and other non-BTC/ETH) may run as local_experiment paper only;
  they are not eligible for demo/live graduation without a BTC/ETH rewrite
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


DEFAULT_START_EQUITY_USDT = 10.0
MAX_START_EQUITY_USDT = 500.0
CAPITAL_SENSITIVITY_LADDER_USDT: tuple[float, ...] = (10.0, 100.0, 500.0)

PRODUCTION_BOUND_SYMBOLS: frozenset[str] = frozenset(
    {
        "BTC-USDT-SWAP",
        "ETH-USDT-SWAP",
    }
)

# Legacy 10U event-trend sleeve instruments: local paper only, not graduation.
LOCAL_EXPERIMENT_SYMBOLS: frozenset[str] = frozenset(
    {
        "RAVE-USDT-SWAP",
        "LAB-USDT-SWAP",
    }
)

PIPELINE_MODE_LOCAL_PAPER = "local_paper"
PIPELINE_PLACES_EXCHANGE_ORDERS_DEFAULT = False


@dataclass(frozen=True)
class EquityValidation:
    equity: float
    accepted: bool
    band: str  # default_10 | capital_sensitivity | rejected
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SymbolClassification:
    symbol: str
    class_name: str  # production_bound | local_experiment | non_production
    production_bound: bool
    demo_live_graduation_eligible: bool
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UniverseValidation:
    symbols: tuple[str, ...]
    accepted_for_production_bound: bool
    track_class: str  # production_bound | local_experiment | mixed_or_invalid
    classifications: tuple[SymbolClassification, ...] = ()
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    demo_live_graduation_eligible: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["classifications"] = [c.to_dict() for c in self.classifications]
        return payload


def normalize_symbol(symbol: str) -> str:
    sym = symbol.strip().upper()
    if sym in {"BTC", "BTC-USDT"}:
        return "BTC-USDT-SWAP"
    if sym in {"ETH", "ETH-USDT"}:
        return "ETH-USDT-SWAP"
    if sym in {"RAVE", "RAVE-USDT"}:
        return "RAVE-USDT-SWAP"
    if sym in {"LAB", "LAB-USDT"}:
        return "LAB-USDT-SWAP"
    return sym


def validate_start_equity(equity: float) -> EquityValidation:
    """Accept 10 default and (10, 500] capital-sensitivity; reject >500 or <10."""
    value = float(equity)
    if value < DEFAULT_START_EQUITY_USDT - 1e-12:
        return EquityValidation(
            equity=value,
            accepted=False,
            band="rejected",
            reasons=("start_equity_below_default_10u",),
        )
    if abs(value - DEFAULT_START_EQUITY_USDT) <= 1e-12:
        return EquityValidation(
            equity=value,
            accepted=True,
            band="default_10",
        )
    if value <= MAX_START_EQUITY_USDT + 1e-12:
        return EquityValidation(
            equity=value,
            accepted=True,
            band="capital_sensitivity",
            warnings=(
                "start_equity_above_default_10u_capital_sensitivity_band",
                "report_must_retain_10u_baseline_or_document_min_notional_block",
            ),
        )
    return EquityValidation(
        equity=value,
        accepted=False,
        band="rejected",
        reasons=("start_equity_above_max_500u",),
    )


def classify_symbol(symbol: str) -> SymbolClassification:
    sym = normalize_symbol(symbol)
    if sym in PRODUCTION_BOUND_SYMBOLS:
        return SymbolClassification(
            symbol=sym,
            class_name="production_bound",
            production_bound=True,
            demo_live_graduation_eligible=True,
        )
    if sym in LOCAL_EXPERIMENT_SYMBOLS:
        return SymbolClassification(
            symbol=sym,
            class_name="local_experiment",
            production_bound=False,
            demo_live_graduation_eligible=False,
            reasons=("local_experiment_not_demo_live_graduation",),
        )
    return SymbolClassification(
        symbol=sym,
        class_name="non_production",
        production_bound=False,
        demo_live_graduation_eligible=False,
        reasons=("symbol_not_in_production_bound_allowlist",),
    )


def is_production_bound_symbol(symbol: str) -> bool:
    return classify_symbol(symbol).production_bound


def validate_production_bound_universe(symbols: Iterable[str]) -> UniverseValidation:
    """All symbols must be BTC/ETH for production-bound / future demo-live path."""
    normalized = tuple(normalize_symbol(s) for s in symbols)
    classifications = tuple(classify_symbol(s) for s in normalized)
    if not classifications:
        return UniverseValidation(
            symbols=normalized,
            accepted_for_production_bound=False,
            track_class="mixed_or_invalid",
            classifications=classifications,
            reasons=("empty_universe",),
            demo_live_graduation_eligible=False,
        )

    non_prod = [c for c in classifications if not c.production_bound]
    if not non_prod:
        return UniverseValidation(
            symbols=normalized,
            accepted_for_production_bound=True,
            track_class="production_bound",
            classifications=classifications,
            demo_live_graduation_eligible=True,
        )

    local_only = all(c.class_name == "local_experiment" for c in non_prod) and all(
        c.class_name in {"local_experiment", "production_bound"} for c in classifications
    )
    # Mixed RAVE/LAB + ETH is the legacy 10U sleeve: local experiment, not graduation.
    has_local = any(c.class_name == "local_experiment" for c in classifications)
    has_non = any(c.class_name == "non_production" for c in classifications)
    if has_non:
        track = "mixed_or_invalid"
        reasons = ("contains_non_production_symbols",)
    elif has_local:
        track = "local_experiment"
        reasons = ("contains_local_experiment_symbols_not_graduation_eligible",)
    else:
        track = "mixed_or_invalid"
        reasons = ("contains_non_production_symbols",)

    warnings: list[str] = []
    if local_only or has_local:
        warnings.append(
            "legacy_or_local_experiment_universe_allowed_for_local_paper_only"
        )

    return UniverseValidation(
        symbols=normalized,
        accepted_for_production_bound=False,
        track_class=track,
        classifications=classifications,
        reasons=reasons,
        warnings=tuple(warnings),
        demo_live_graduation_eligible=False,
    )


def default_pipeline_places_exchange_orders() -> bool:
    """Default prod paper/run/watch paths never submit OKX demo or live orders."""
    return PIPELINE_PLACES_EXCHANGE_ORDERS_DEFAULT


def operator_policy_snapshot() -> dict[str, Any]:
    """Machine-readable operator constraints for status / reports / registry."""
    return {
        "policy_id": "operator_hard_constraints_2026-07-17",
        "default_start_equity_usdt": DEFAULT_START_EQUITY_USDT,
        "max_start_equity_usdt": MAX_START_EQUITY_USDT,
        "capital_sensitivity_ladder_usdt": list(CAPITAL_SENSITIVITY_LADDER_USDT),
        "production_bound_symbols": sorted(PRODUCTION_BOUND_SYMBOLS),
        "local_experiment_symbols": sorted(LOCAL_EXPERIMENT_SYMBOLS),
        "default_pipeline_mode": PIPELINE_MODE_LOCAL_PAPER,
        "default_pipeline_places_exchange_orders": PIPELINE_PLACES_EXCHANGE_ORDERS_DEFAULT,
        "demo_live_require_prior_demo_effect": True,
        "live_default": False,
        "prospective_wait_required_for_local_paper": False,
        "notes": (
            "Local paper is the only default runtime on this workstation. "
            "OKX demo/live run only on the server with agent-injected keys "
            "(not configured on the research machine). "
            "RAVE/LAB remain local_experiment only."
        ),
        "demo_live_execution_environment": "server_only",
        "api_keys_on_research_workstation": False,
    }


def annotate_local_paper_cycle(
    *,
    symbols: Iterable[str],
    start_equity: float,
) -> dict[str, Any]:
    """Attach policy classification to a local paper cycle report."""
    equity = validate_start_equity(start_equity)
    universe = validate_production_bound_universe(symbols)
    return {
        "operator_policy": operator_policy_snapshot(),
        "start_equity_validation": equity.to_dict(),
        "universe_validation": universe.to_dict(),
        "mode": PIPELINE_MODE_LOCAL_PAPER,
        "places_exchange_orders": default_pipeline_places_exchange_orders(),
        "exchange_orders_submitted": 0,
        "live_allowed": False,
        "demo_live_graduation_eligible": universe.demo_live_graduation_eligible,
        "track_class": universe.track_class,
    }

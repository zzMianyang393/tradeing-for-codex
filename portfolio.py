from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from strategy import Signal


@dataclass(frozen=True)
class PortfolioConfig:
    max_signals: int = 10
    vote_boost: float = 0.15
    correlation_penalty: float = 0.75
    score_normalizer: float = 5.0
    strategy_risk_budgets: dict[str, float] = field(default_factory=dict)
    correlation_groups: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class PortfolioDecision:
    signal: Signal
    normalized_score: float
    adjusted_score: float
    votes: int
    reasons: list[str]
    strategy_family: str


def strategy_family(reason: str) -> str:
    if reason.startswith("trade_flow_"):
        return "trade_flow"
    if reason.startswith("order_book_"):
        return "order_book"
    if reason.startswith("open_interest_"):
        return "open_interest"
    if reason.startswith("micro_momentum_"):
        return "micro_momentum"
    if reason.startswith("continuation_"):
        return "continuation"
    if reason.startswith("funding_"):
        return "funding"
    if reason.startswith("range_"):
        return "range"
    if reason.startswith("attack_"):
        return "attack"
    if reason.startswith("trend_"):
        return "trend"
    if reason.startswith("transition_"):
        return "transition"
    return reason.split("_", 1)[0] if reason else "unknown"


def select_portfolio_signals(
    signals: Iterable[Signal],
    config: PortfolioConfig | None = None,
    current_strategy_exposure: dict[str, float] | None = None,
) -> list[PortfolioDecision]:
    config = config or PortfolioConfig()
    exposure = current_strategy_exposure or {}
    grouped: dict[tuple[str, int], list[Signal]] = {}
    for signal in signals:
        grouped.setdefault((signal.symbol, signal.direction), []).append(signal)

    best_by_symbol: dict[str, PortfolioDecision] = {}
    for (symbol, _direction), group in grouped.items():
        decision = _decision_for_group(group, config)
        family = decision.strategy_family
        budget = config.strategy_risk_budgets.get(family)
        if budget is not None and exposure.get(family, 0.0) >= budget:
            continue
        current = best_by_symbol.get(symbol)
        if current is None or decision.adjusted_score > current.adjusted_score:
            best_by_symbol[symbol] = decision

    selected: list[PortfolioDecision] = []
    for decision in sorted(best_by_symbol.values(), key=lambda item: item.adjusted_score, reverse=True):
        decision = _apply_correlation_penalty(decision, selected, config)
        selected.append(decision)

    selected.sort(key=lambda item: item.adjusted_score, reverse=True)
    return selected[: config.max_signals]


def _decision_for_group(group: list[Signal], config: PortfolioConfig) -> PortfolioDecision:
    ordered = sorted(group, key=lambda signal: signal.score, reverse=True)
    primary = ordered[0]
    normalized = min(1.0, max(0.0, primary.score / config.score_normalizer))
    adjusted = normalized + max(0, len(group) - 1) * config.vote_boost
    return PortfolioDecision(
        signal=primary,
        normalized_score=round(normalized, 4),
        adjusted_score=round(adjusted, 4),
        votes=len(group),
        reasons=[signal.reason for signal in group],
        strategy_family=strategy_family(primary.reason),
    )


def _apply_correlation_penalty(
    decision: PortfolioDecision,
    selected: list[PortfolioDecision],
    config: PortfolioConfig,
) -> PortfolioDecision:
    if not selected:
        return decision
    selected_symbols = {item.signal.symbol for item in selected}
    for group in config.correlation_groups:
        group_symbols = set(group)
        if decision.signal.symbol in group_symbols and selected_symbols & group_symbols:
            return PortfolioDecision(
                signal=decision.signal,
                normalized_score=decision.normalized_score,
                adjusted_score=round(decision.adjusted_score * config.correlation_penalty, 4),
                votes=decision.votes,
                reasons=decision.reasons,
                strategy_family=decision.strategy_family,
            )
    return decision

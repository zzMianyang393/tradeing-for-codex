from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Callable

from config import BacktestConfig, SymbolRisk
from market import FeatureBar, load_market
from risk_manager import RiskManager
from strategy import (
    Signal,
    attack_signal_for,
    continuation_signal_for,
    funding_signal_for,
    micro_momentum_signal_for,
    open_interest_signal_for,
    order_book_signal_for,
    signal_for,
    trade_flow_signal_for,
    volatility_breakout_signal_for,
)
from validation import audit_report


ExternalSignalProvider = Callable[[str, list[FeatureBar], int], Signal | None]


_TIMELINE_CACHE: dict[tuple[tuple[tuple[str, int, int], ...], float], list[int]] = {}
_INDEX_CACHE: dict[tuple[tuple[str, int, int], ...], dict[str, dict[int, int]]] = {}


@dataclass(slots=True)
class Position:
    symbol: str
    direction: int
    entry_idx: int
    entry_time: str
    entry: float
    notional: float
    margin: float
    qty: float
    stop: float
    take_profit: float
    trail: float
    leverage: float
    regime: str
    reason: str
    max_favorable_pct: float = 0.0
    max_adverse_pct: float = 0.0


@dataclass(slots=True)
class Trade:
    symbol: str
    direction: str
    entry_time: str
    exit_time: str
    entry: float
    exit: float
    notional: float
    pnl: float
    pnl_pct_equity: float
    regime: str
    reason: str
    exit_reason: str
    win: bool


def _common_timeline(market: dict[str, list[FeatureBar]], min_count_fraction: float = 0.70) -> list[int]:
    key = (_market_cache_key(market), min_count_fraction)
    cached = _TIMELINE_CACHE.get(key)
    if cached is not None:
        return cached
    counts: dict[int, int] = {}
    for bars in market.values():
        for bar in bars:
            counts[bar.ts] = counts.get(bar.ts, 0) + 1
    min_count = max(1, int(len(market) * min_count_fraction))
    timeline = sorted(ts for ts, count in counts.items() if count >= min_count)
    _TIMELINE_CACHE[key] = timeline
    return timeline


def _build_index(market: dict[str, list[FeatureBar]]) -> dict[str, dict[int, int]]:
    key = _market_cache_key(market)
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    index = {symbol: {bar.ts: idx for idx, bar in enumerate(bars)} for symbol, bars in market.items()}
    _INDEX_CACHE[key] = index
    return index


def _market_cache_key(market: dict[str, list[FeatureBar]]) -> tuple[tuple[str, int, int], ...]:
    return tuple(sorted((symbol, id(bars), len(bars)) for symbol, bars in market.items()))


def select_symbols(
    market: dict[str, list[FeatureBar]],
    end_ts: int,
    limit: int = 10,
    config: BacktestConfig | None = None,
) -> list[str]:
    scored: list[tuple[float, str]] = []
    index = _build_index(market)
    excluded = set(config.excluded_symbols) if config else set()
    for symbol, bars in market.items():
        if symbol in excluded:
            continue
        idx = index[symbol].get(end_ts)
        if idx is None or idx < 260:
            continue
        lookback = config.selector_lookback_bars if config else 96
        sample = bars[max(0, idx - lookback) : idx + 1]
        if len(sample) < min(96, lookback // 2):
            continue
        avg_quote = sum(bar.volume_quote for bar in sample) / len(sample)
        avg_atr = sum(bar.atr_pct for bar in sample) / len(sample)
        trend = abs(sum(bar.trend_strength for bar in sample[-20:]) / 20.0)
        micro_noise = sum((bar.high - bar.low) / bar.close for bar in sample) / len(sample)
        momentum = abs(sample[-1].close / sample[0].close - 1.0) if sample[0].close else 0.0
        if config:
            if config.selector_min_avg_quote > 0 and avg_quote < config.selector_min_avg_quote:
                continue
            if config.selector_max_micro_noise > 0 and micro_noise > config.selector_max_micro_noise:
                continue
            score = (
                math.log10(max(avg_quote, 1.0))
                + momentum * config.selector_momentum_weight
                + avg_atr * config.selector_volatility_weight
                + min(trend, 4.0) * config.selector_trend_weight
                - micro_noise * config.selector_noise_penalty
            )
        else:
            score = math.log10(max(avg_quote, 1.0)) + avg_atr * 170.0 + min(trend, 4.0) * 0.12 - micro_noise * 8.0
        scored.append((score, symbol))
    scored.sort(reverse=True)
    return [symbol for _, symbol in scored[:limit]]


class Backtester:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.risk_manager: RiskManager | None = None
        if config.rm_enabled:
            self.risk_manager = RiskManager(config)

    def run(
        self,
        market: dict[str, list[FeatureBar]],
        days: int | None = None,
        signal_provider: ExternalSignalProvider | None = None,
    ) -> dict:
        """Run a backtest.

        ``signal_provider`` is intentionally narrow: it supplies a candidate's
        actual entry signal for one symbol/bar, while sizing, costs, exits and
        risk controls remain owned by this backtester.  It prevents research
        candidates from being silently evaluated through the default router.
        """
        if self.risk_manager is not None:
            self.risk_manager.reset()
        if self.config.excluded_symbols:
            excluded = set(self.config.excluded_symbols)
            market = {symbol: bars for symbol, bars in market.items() if symbol not in excluded}
        market = self._filter_market_for_window(market, days)
        timeline = _common_timeline(market, min_count_fraction=0.50)
        if not timeline:
            raise ValueError("No overlapping market timeline found.")
        if days is not None:
            start_ts = timeline[-1] - days * 24 * 60 * 60 * 1000
            timeline = [ts for ts in timeline if ts >= start_ts]
        if len(timeline) < self.config.min_bars:
            return {
                "available": False,
                "reason": f"not enough bars for {days}d window",
                "bars": len(timeline),
                "days": days,
            }

        index = _build_index(market)
        symbol_limit = self._symbol_limit_for_window(days)
        active_symbols = set(self._select_symbols_for_window(market, timeline[0], days, symbol_limit))
        equity = self.config.start_equity

        # ML model initialization
        ml_model = None
        ml_last_train_step = -1
        if self.config.enable_ml_module:
            try:
                from ml_signal import MLSignalConfig, extract_features, prepare_dataset, train_model
                ml_config = MLSignalConfig(
                    train_days=self.config.ml_train_days,
                    forward_bars=self.config.ml_forward_bars,
                    profit_threshold_pct=self.config.ml_profit_threshold_pct,
                    min_score=self.config.ml_min_score,
                )
                # Train on initial window
                train_start = timeline[0]
                train_end = timeline[min(len(timeline) - 1, ml_config.train_days * 96)]
                train_bars = []
                for sym in active_symbols:
                    sym_bars = [b for b in market.get(sym, []) if train_start <= b.ts <= train_end]
                    train_bars.extend(sym_bars)
                if len(train_bars) >= ml_config.min_training_samples:
                    X_train, y_train = prepare_dataset(train_bars, ml_config.forward_bars, ml_config.profit_threshold_pct)
                    if len(X_train) >= 100:
                        ml_model = train_model(X_train, y_train, ml_config.n_estimators, ml_config.max_depth, ml_config.learning_rate)
                        ml_last_train_step = 0
            except Exception as exc:
                import logging
                logging.getLogger("backtester").warning("ML model init failed: %s", exc)

        # Candidate Pool filter initialization
        cp_filter = None
        cp_last_train_step = -1
        cp_warmup_until_step = 0
        cp_retrain_count = 0
        cp_retrain_failures = 0
        cp_active_regimes = tuple(self.config.cp_enabled_regimes)
        cp_regime_policy_history: list[dict] = []
        self._cp_regime_risk_multipliers: dict[str, float] = {}
        cp_quality_rates: dict[tuple[int, str, str], float] = {}
        cp_candidate_cache: dict[tuple[str, int], list] = {}
        cp_precomputed_only = False
        cp_event_store = None
        if self.config.enable_candidate_pool:
            from candidate_filter import CandidateFilter, RuleFilterConfig, MLFilterConfig
            from candidate_pool import CandidateEventStore, scan_candidates as cp_scan_symbol

            if self.config.cp_candidate_cache_path and Path(self.config.cp_candidate_cache_path).exists():
                try:
                    cp_event_store = CandidateEventStore(Path(self.config.cp_candidate_cache_path))
                    cp_precomputed_only = True
                except Exception as exc:
                    import logging
                    logging.getLogger("backtester").warning(
                        "CP candidate cache load failed; falling back to live scan: %s", exc
                    )

            def cp_candidates_for(symbol: str, idx: int) -> list:
                ts_key = market[symbol][idx].ts
                cache_key = (symbol, ts_key)
                # Indexed precomputed candidates are already cheap to retrieve.
                # Do not retain every bar's list for the whole backtest: over a
                # long window that duplicates a large portion of the cache in RAM.
                if cp_precomputed_only:
                    return cp_event_store.get(symbol, ts_key) if cp_event_store is not None else []
                if cache_key not in cp_candidate_cache:
                    cp_candidate_cache[cache_key] = cp_scan_symbol(
                        symbol,
                        market[symbol],
                        idx,
                        self.config.cp_min_proximity,
                    )
                return cp_candidate_cache[cache_key]

            def cp_training_sample(candidates: list) -> list:
                max_samples = max(1, self.config.cp_ml_max_training_samples)
                if len(candidates) <= max_samples:
                    return candidates
                return [
                    candidates[round(i * (len(candidates) - 1) / (max_samples - 1))]
                    for i in range(max_samples)
                ]

            def cp_scan_cached(scan_timeline: list[int]) -> list:
                cached_candidates = []
                for scan_ts in scan_timeline:
                    for scan_symbol in market:
                        scan_idx = index.get(scan_symbol, {}).get(scan_ts)
                        if scan_idx is None or scan_idx < 1:
                            continue
                        cached_candidates.extend(cp_candidates_for(scan_symbol, scan_idx))
                return cached_candidates

            def cp_label_candidates(candidates: list, cutoff_ts: int) -> list:
                from mfe_labeler import label_candidates

                ready = []
                pending = []
                horizon = self.config.cp_max_hold_bars
                for candidate in candidates:
                    bar_idx = index.get(candidate.symbol, {}).get(candidate.ts)
                    bars = market.get(candidate.symbol, [])
                    end_idx = (bar_idx + horizon) if bar_idx is not None else len(bars)
                    if (
                        candidate.label >= 0
                        and candidate.label_horizon_bars == horizon
                        and end_idx < len(bars)
                        and bars[end_idx].ts <= cutoff_ts
                    ):
                        ready.append(candidate)
                    else:
                        pending.append(candidate)
                if pending:
                    ready.extend(
                        label_candidates(
                            pending,
                            market,
                            index,
                            horizon_bars=horizon,
                            label_cutoff_ts=cutoff_ts,
                            stop_atr=self.config.cp_stop_atr,
                            take_profit_atr=self.config.cp_take_profit_atr,
                            trailing_atr=self.config.cp_trailing_atr,
                            max_hold_bars=self.config.cp_max_hold_bars,
                            taker_fee=self.config.taker_fee,
                            slippage=self.config.slippage,
                        )
                    )
                return ready

            def cp_update_regime_policy(labeled: list) -> None:
                """Choose regimes from past labels only; never inspect the test slice."""
                nonlocal cp_active_regimes
                if not (
                    self.config.cp_dynamic_regime_routing
                    or self.config.cp_dynamic_regime_risk_scaling
                ):
                    return
                stats: dict[str, dict[str, int]] = {}
                for candidate in labeled:
                    if candidate.regime not in self.config.cp_enabled_regimes:
                        continue
                    item = stats.setdefault(candidate.regime, {"samples": 0, "positive": 0})
                    item["samples"] += 1
                    item["positive"] += int(
                        candidate.net_pnl_pct >= self.config.cp_dynamic_regime_min_forward_pnl_pct
                    )
                selected = tuple(
                    regime
                    for regime in self.config.cp_enabled_regimes
                    if stats.get(regime, {}).get("samples", 0) >= self.config.cp_dynamic_regime_min_samples
                    and stats[regime]["positive"] / stats[regime]["samples"]
                    >= self.config.cp_dynamic_regime_min_label_rate
                )
                if not selected:
                    selected = tuple(self.config.cp_enabled_regimes)
                if self.config.cp_dynamic_regime_routing:
                    cp_active_regimes = selected
                if self.config.cp_dynamic_regime_risk_scaling:
                    reference = max(self.config.cp_dynamic_regime_reference_rate, 1e-6)
                    floor = max(0.0, min(1.0, self.config.cp_dynamic_regime_risk_floor))
                    self._cp_regime_risk_multipliers = {
                        regime: max(
                            floor,
                            min(1.0, (stats[regime]["positive"] / stats[regime]["samples"]) / reference),
                        )
                        for regime in stats
                        if stats[regime]["samples"] >= self.config.cp_dynamic_regime_min_samples
                    }
                cp_regime_policy_history.append({
                    "update": len(cp_regime_policy_history),
                    "active_regimes": selected,
                    "stats": {
                        regime: {
                            "samples": item["samples"],
                            "forward_pnl_rate": round(item["positive"] / item["samples"], 4),
                        }
                        for regime, item in stats.items()
                    },
                    "risk_multipliers": dict(self._cp_regime_risk_multipliers),
                })

            def cp_update_quality_rates(labeled: list) -> None:
                """Calibrate ranking from completed forward PnL, not MFE labels."""
                nonlocal cp_quality_rates
                if not self.config.cp_quality_ranking:
                    return
                buckets: dict[tuple[int, str, str], list[int]] = {}
                for candidate in labeled:
                    key = (candidate.direction, candidate.regime, candidate.pattern_type)
                    values = buckets.setdefault(key, [0, 0])
                    values[0] += 1
                    values[1] += int(
                        candidate.net_pnl_pct >= self.config.cp_quality_forward_pnl_threshold
                    )
                cp_quality_rates = {
                    key: positive / samples
                    for key, (samples, positive) in buckets.items()
                    if samples >= self.config.cp_quality_min_samples
                }

            cp_filter = CandidateFilter(
                rule_config=RuleFilterConfig(min_proximity=self.config.cp_min_proximity),
                ml_config=MLFilterConfig(
                    n_estimators=self.config.cp_ml_n_estimators,
                    learning_rate=0.08,
                    max_training_samples=self.config.cp_ml_max_training_samples,
                ),
                use_rules=self.config.cp_use_rules,
                use_ml=self.config.cp_use_ml,
            )
            # A model trained outside this walk-forward run is unsafe by
            # default: it may have seen the historical test window.
            loaded_cp_model = False
            if (
                self.config.cp_allow_pretrained_model
                and self.config.cp_ml_model_path
                and Path(self.config.cp_ml_model_path).exists()
            ):
                try:
                    cp_filter.load_ml(self.config.cp_ml_model_path)
                    cp_last_train_step = 0
                    loaded_cp_model = True
                except Exception as exc:
                    import logging
                    logging.getLogger("backtester").warning("CP model load failed: %s", exc)

            if not loaded_cp_model:
                try:
                    cp_train_end_step = min(len(timeline) - 1, 96 * 30)
                    cp_train_end_ts = timeline[cp_train_end_step]
                    cp_train_timeline = [t for t in timeline if t <= cp_train_end_ts]
                    cp_warmup_until_step = cp_train_end_step + 1
                    if len(cp_train_timeline) > 96:
                        cp_cands = cp_training_sample(cp_scan_cached(cp_train_timeline))
                        if cp_cands:
                            cp_labeled = cp_label_candidates(cp_cands, cp_train_end_ts)
                            cp_filter.train_ml(cp_labeled)
                            cp_update_regime_policy(cp_labeled)
                            cp_update_quality_rates(cp_labeled)
                            cp_last_train_step = 0
                except Exception as exc:
                    import logging
                    logging.getLogger("backtester").warning("CP filter init failed: %s", exc)

        peak = equity
        max_drawdown = 0.0
        trades: list[Trade] = []
        positions: dict[str, Position] = {}
        cooldown: dict[str, int] = {}
        edge_pause_until = -1
        direction_pause_until: dict[int, int] = {}
        reason_pause_until: dict[str, int] = {}
        router_rejections: dict[str, object] = {
            "total": 0,
            "by_rejection_reason": {},
            "by_signal_reason": {},
            "by_regime": {},
        }
        equity_curve: list[tuple[str, float]] = []
        _last_day: int = -1
        _last_week: int = -1

        def router_allows(sig: Signal, bar: FeatureBar) -> bool:
            rejection = self._dynamic_router_rejection_reason(sig, bar)
            if rejection is None:
                return True
            router_rejections["total"] = int(router_rejections["total"]) + 1
            for bucket_name, key in (
                ("by_rejection_reason", rejection),
                ("by_signal_reason", sig.reason),
                ("by_regime", sig.regime),
            ):
                bucket = router_rejections[bucket_name]
                assert isinstance(bucket, dict)
                bucket[key] = int(bucket.get(key, 0)) + 1
            return False

        for step, ts in enumerate(timeline):
            if step % 96 == 0:
                active_symbols = set(self._select_symbols_for_window(market, ts, days, symbol_limit))
                # Reset daily PnL every 96 bars (1 day)
                day_idx = step // 96
                if self.risk_manager is not None and day_idx != _last_day:
                    self.risk_manager._daily_pnl = 0.0
                    _last_day = day_idx
                # Reset weekly PnL every 672 bars (7 days)
                week_idx = step // 672
                if self.risk_manager is not None and week_idx != _last_week:
                    self.risk_manager._weekly_pnl = 0.0
                    _last_week = week_idx
            for symbol in list(cooldown):
                cooldown[symbol] -= 1
                if cooldown[symbol] <= 0:
                    del cooldown[symbol]

            for symbol, pos in list(positions.items()):
                idx = index[symbol].get(ts)
                if idx is None:
                    continue
                bar = market[symbol][idx]
                exit_price, exit_reason = self._exit_price(pos, bar, idx)
                if exit_price is not None:
                    fee = pos.notional * self.config.taker_fee
                    gross = pos.direction * (exit_price - pos.entry) / pos.entry * pos.notional
                    pnl = gross - fee
                    before = equity
                    equity += pnl
                    trade = Trade(
                        symbol=symbol,
                        direction="long" if pos.direction > 0 else "short",
                        entry_time=pos.entry_time,
                        exit_time=bar.time,
                        entry=round(pos.entry, 8),
                        exit=round(exit_price, 8),
                        notional=round(pos.notional, 4),
                        pnl=round(pnl, 4),
                        pnl_pct_equity=round(pnl / before * 100.0, 4) if before > 0 else 0.0,
                        regime=pos.regime,
                        reason=pos.reason,
                        exit_reason=exit_reason,
                        win=pnl > 0,
                    )
                    trades.append(trade)
                    if self.risk_manager is not None:
                        self.risk_manager.on_trade_close(pnl, step)
                    if (
                        not trade.win
                        and abs(trade.pnl_pct_equity) >= self.config.direction_loss_pause_pct
                    ):
                        direction_pause_until[pos.direction] = max(
                            direction_pause_until.get(pos.direction, -1),
                            step + self.config.direction_loss_pause_bars,
                        )
                    recent = trades[-self.config.edge_lookback_trades :]
                    if len(recent) == self.config.edge_lookback_trades:
                        recent_pnl = sum(item.pnl for item in recent)
                        recent_win_rate = sum(1 for item in recent if item.win) / len(recent)
                        if recent_pnl < 0 or recent_win_rate < 0.50:
                            edge_pause_until = max(edge_pause_until, step + self.config.edge_pause_bars)
                    del positions[symbol]
                    if self.risk_manager is not None:
                        self.risk_manager._track_close(symbol)
                    cooldown[symbol] = self._cooldown_bars_for(pos)
                    if not trade.win:
                        cooldown[symbol] = max(cooldown[symbol], self._loss_cooldown_bars_for(pos))
                        if trade.exit_reason == "time_exit":
                            cooldown[symbol] = max(cooldown[symbol], self.config.time_exit_loss_cooldown_bars)
                    symbol_recent = [item for item in trades if item.symbol == symbol][
                        -self.config.symbol_edge_lookback_trades :
                    ]
                    if len(symbol_recent) == self.config.symbol_edge_lookback_trades:
                        symbol_pnl = sum(item.pnl for item in symbol_recent)
                        symbol_win_rate = sum(1 for item in symbol_recent if item.win) / len(symbol_recent)
                        if symbol_pnl < 0 or symbol_win_rate < self.config.symbol_edge_min_win_rate:
                            cooldown[symbol] = max(cooldown.get(symbol, 0), self.config.symbol_edge_pause_bars)
                    reason_recent = [item for item in trades if item.reason == pos.reason][
                        -self.config.reason_edge_lookback_trades :
                    ]
                    if len(reason_recent) == self.config.reason_edge_lookback_trades:
                        reason_pnl = sum(item.pnl for item in reason_recent)
                        reason_win_rate = sum(1 for item in reason_recent if item.win) / len(reason_recent)
                        if reason_pnl < 0 or reason_win_rate < self.config.reason_edge_min_win_rate:
                            reason_pause_until[pos.reason] = max(
                                reason_pause_until.get(pos.reason, -1),
                                step + self.config.reason_edge_pause_bars,
                            )

            if equity <= self.config.start_equity * 0.30:
                break

            used_margin = sum(pos.margin for pos in positions.values())
            free_margin_limit = max(0.0, equity * self.config.max_total_margin_fraction - used_margin)
            position_cap = self.config.max_positions + (
                self.config.attack_max_positions if self.config.enable_attack_module else 0
            )
            slots = position_cap - len(positions)
            if (
                slots > 0
                and free_margin_limit > 0
                and step >= edge_pause_until
                and step >= cp_warmup_until_step
            ):
                signals: list[Signal] = []

                if self.config.enable_candidate_pool and cp_filter is not None:
                    # --- Candidate Pool signal generation ---
                    # Periodic ML retrain
                    if (self.config.cp_use_ml
                        and cp_filter.ml_filter.trained
                        and step - cp_last_train_step >= self.config.cp_retrain_interval_bars):
                        try:
                            cp_retrain_start = max(0, step - 96 * 30)
                            cp_retrain_ts_start = timeline[cp_retrain_start]
                            cp_retrain_timeline = [t for t in timeline[cp_retrain_start:step] if t >= cp_retrain_ts_start]
                            if len(cp_retrain_timeline) > 96:
                                cp_rc = []
                                for retrain_ts in cp_retrain_timeline:
                                    for retrain_symbol, retrain_bars in market.items():
                                        retrain_idx = index.get(retrain_symbol, {}).get(retrain_ts)
                                        if retrain_idx is None or retrain_idx < 1:
                                            continue
                                        cp_rc.extend(cp_candidates_for(retrain_symbol, retrain_idx))
                                cp_rc = cp_training_sample(cp_rc)
                                if cp_rc:
                                    cp_rl = cp_label_candidates(cp_rc, timeline[step - 1])
                                    cp_filter.train_ml(cp_rl)
                                    cp_update_regime_policy(cp_rl)
                                    cp_update_quality_rates(cp_rl)
                                    cp_retrain_count += 1
                                    cp_last_train_step = step
                        except Exception:
                            cp_retrain_failures += 1
                            pass

                    for symbol in active_symbols:
                        if symbol in positions or symbol in cooldown:
                            continue
                        idx = index[symbol].get(ts)
                        if idx is None or idx < 1:
                            continue
                        try:
                            cands = cp_candidates_for(symbol, idx)
                            for cand in cands:
                                if cand.direction not in self.config.cp_enabled_directions:
                                    continue
                                # Regime filter
                                if cand.regime not in cp_active_regimes:
                                    continue
                                if cand.pattern_type not in self.config.cp_enabled_patterns:
                                    continue
                                # ML + rule filter
                                passed, reason, prob = cp_filter.should_trade(cand)
                                if not passed:
                                    continue
                                # Convert to Signal
                                cp_score = 2.5 + cand.proximity_score * 2.0 + prob
                                if self.config.cp_quality_ranking:
                                    quality_rate = cp_quality_rates.get(
                                        (cand.direction, cand.regime, cand.pattern_type), 0.5
                                    )
                                    cp_score += (
                                        quality_rate - 0.5
                                    ) * self.config.cp_quality_bonus_scale
                                if cp_score < self.config.cp_min_score:
                                    continue
                                cp_reason = f"cp_{cand.pattern_type}_{('long' if cand.direction == 1 else 'short')}"
                                cp_sig = Signal(
                                    symbol=symbol,
                                    direction=cand.direction,
                                    score=round(cp_score, 3),
                                    regime=cand.regime,
                                    reason=cp_reason,
                                )
                                if not router_allows(cp_sig, market[symbol][idx]):
                                    continue
                                if step < direction_pause_until.get(cp_sig.direction, -1):
                                    continue
                                if step < reason_pause_until.get(cp_sig.reason, -1):
                                    continue
                                if self._blocked_by_reversal_risk(cp_sig, market[symbol], idx):
                                    continue
                                signals.append(cp_sig)
                        except Exception:
                            pass  # CP signal failure is non-fatal
                elif signal_provider is not None:
                    # Candidate strategies must provide their own entries.
                    # Do not mix them with the legacy strategy router: that
                    # would make two differently named candidates identical.
                    for symbol in active_symbols:
                        if symbol in positions or symbol in cooldown:
                            continue
                        idx = index[symbol].get(ts)
                        if idx is None:
                            continue
                        sig = signal_provider(symbol, market[symbol], idx)
                        if sig is None or sig.score < self.config.min_score:
                            continue
                        if step < direction_pause_until.get(sig.direction, -1):
                            continue
                        if step < reason_pause_until.get(sig.reason, -1):
                            continue
                        if self._blocked_by_reversal_risk(sig, market[symbol], idx):
                            continue
                        signals.append(sig)
                else:
                    # --- Original signal generation ---
                    for symbol in active_symbols:
                        if symbol in positions or symbol in cooldown:
                            continue
                        idx = index[symbol].get(ts)
                        if idx is None:
                            continue
                        sig = signal_for(symbol, market[symbol], idx, self.config)
                        if sig and sig.score >= self.config.min_score:
                            # Regime-aware策略选择: 基于行情选择策略
                            if not router_allows(sig, market[symbol][idx]):
                                continue
                            adaptive_trend = self._is_adaptive_trend_signal(sig)
                            if sig.regime not in self.config.enabled_regimes and not adaptive_trend:
                                continue
                            if adaptive_trend and sig.score < self.config.adaptive_trend_min_score:
                                continue
                            if step < direction_pause_until.get(sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(sig.reason, -1):
                                continue
                            if self._blocked_by_reversal_risk(sig, market[symbol], idx):
                                continue
                            signals.append(sig)
                        attack_sig = attack_signal_for(symbol, market[symbol], idx, self.config)
                        if self.config.enable_attack_module and attack_sig and attack_sig.score >= self.config.attack_min_score:
                            if not router_allows(attack_sig, market[symbol][idx]):
                                continue
                            if attack_sig.regime not in self.config.attack_enabled_regimes:
                                continue
                            if step < direction_pause_until.get(attack_sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(attack_sig.reason, -1):
                                continue
                            if self._blocked_by_reversal_risk(attack_sig, market[symbol], idx):
                                continue
                            signals.append(attack_sig)
                        volatility_sig = volatility_breakout_signal_for(symbol, market[symbol], idx, self.config)
                        if self.config.enable_volatility_breakout and volatility_sig and volatility_sig.score >= self.config.min_score:
                            if not router_allows(volatility_sig, market[symbol][idx]):
                                continue
                            if self.config.router_reason_allowed_regimes.get(volatility_sig.reason) and volatility_sig.regime not in self.config.router_reason_allowed_regimes[volatility_sig.reason]:
                                continue
                            if step < direction_pause_until.get(volatility_sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(volatility_sig.reason, -1):
                                continue
                            if self._blocked_by_reversal_risk(volatility_sig, market[symbol], idx):
                                continue
                            signals.append(volatility_sig)
                        continuation_sig = continuation_signal_for(symbol, market[symbol], idx, self.config)
                        if continuation_sig and continuation_sig.score >= self.config.min_score:
                            if not router_allows(continuation_sig, market[symbol][idx]):
                                continue
                            if step < direction_pause_until.get(continuation_sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(continuation_sig.reason, -1):
                                continue
                            signals.append(continuation_sig)
                        micro_sig = micro_momentum_signal_for(symbol, market[symbol], idx, self.config)
                        if micro_sig and micro_sig.score >= self.config.min_score:
                            if not router_allows(micro_sig, market[symbol][idx]):
                                continue
                            if step < direction_pause_until.get(micro_sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(micro_sig.reason, -1):
                                continue
                            if self._blocked_by_reversal_risk(micro_sig, market[symbol], idx):
                                continue
                            signals.append(micro_sig)
                        funding_sig = funding_signal_for(symbol, market[symbol], idx, self.config)
                        if funding_sig and funding_sig.score >= self.config.min_score:
                            if not router_allows(funding_sig, market[symbol][idx]):
                                continue
                            if step < direction_pause_until.get(funding_sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(funding_sig.reason, -1):
                                continue
                            signals.append(funding_sig)
                        open_interest_sig = open_interest_signal_for(symbol, market[symbol], idx, self.config)
                        if open_interest_sig and open_interest_sig.score >= self.config.min_score:
                            if not router_allows(open_interest_sig, market[symbol][idx]):
                                continue
                            if step < direction_pause_until.get(open_interest_sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(open_interest_sig.reason, -1):
                                continue
                            if self._blocked_by_reversal_risk(open_interest_sig, market[symbol], idx):
                                continue
                            signals.append(open_interest_sig)
                        trade_flow_sig = trade_flow_signal_for(symbol, market[symbol], idx, self.config)
                        if trade_flow_sig and trade_flow_sig.score >= self.config.min_score:
                            if not router_allows(trade_flow_sig, market[symbol][idx]):
                                continue
                            if step < direction_pause_until.get(trade_flow_sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(trade_flow_sig.reason, -1):
                                continue
                            if self._blocked_by_reversal_risk(trade_flow_sig, market[symbol], idx):
                                continue
                            signals.append(trade_flow_sig)
                        order_book_sig = order_book_signal_for(symbol, market[symbol], idx, self.config)
                        if order_book_sig and order_book_sig.score >= self.config.min_score:
                            if not router_allows(order_book_sig, market[symbol][idx]):
                                continue
                            if step < direction_pause_until.get(order_book_sig.direction, -1):
                                continue
                            if step < reason_pause_until.get(order_book_sig.reason, -1):
                                continue
                            if self._blocked_by_reversal_risk(order_book_sig, market[symbol], idx):
                                continue
                            signals.append(order_book_sig)
                        # ML signal generation
                        if ml_model is not None and self.config.enable_ml_module:
                            try:
                                from ml_signal import extract_features
                                bar = market[symbol][idx]
                                feat = extract_features(bar)
                                import numpy as np
                                X = np.array([[feat[col] for col in [
                                    "ema20", "ema50", "ema200", "atr", "atr_pct", "rsi",
                                    "bb_mid", "bb_upper", "bb_lower", "vol_sma",
                                    "donchian_high", "donchian_low", "trend_strength",
                                    "volume_ratio", "close_to_ema20", "close_to_ema50",
                                    "close_to_donchian_high", "close_to_donchian_low",
                                    "bb_position", "candle_body_pct", "candle_range_pct",
                                    "upper_shadow_pct", "lower_shadow_pct",
                                ]]], dtype=np.float64)
                                prob = ml_model.predict_proba(X)[0][1]
                                if prob >= self.config.ml_min_score:
                                    ml_sig = Signal(
                                        symbol=symbol,
                                        direction=1,  # ML predicts up
                                        score=3.0 + prob,
                                        regime="ml",
                                        reason="ml_long",
                                    )
                                    if not router_allows(ml_sig, bar):
                                        pass  # skip
                                    elif step < direction_pause_until.get(ml_sig.direction, -1):
                                        pass
                                    elif step < reason_pause_until.get(ml_sig.reason, -1):
                                        pass
                                    elif self._blocked_by_reversal_risk(ml_sig, market[symbol], idx):
                                        pass
                                    else:
                                        signals.append(ml_sig)
                            except Exception:
                                pass  # ML signal failure is non-fatal
                signals.sort(key=lambda sig: sig.score, reverse=True)
                opened_symbols: set[str] = set()
                for sig in signals[:slots]:
                    if free_margin_limit <= 0:
                        break
                    if sig.symbol in positions or sig.symbol in opened_symbols:
                        continue
                    idx = index[sig.symbol][ts]
                    pos = self._open_position(sig, market[sig.symbol][idx], idx, equity, free_margin_limit)
                    if pos is None:
                        continue
                    # RiskManager check (after sizing, before commitment)
                    if self.risk_manager is not None:
                        cur_margin = sum(p.margin for p in positions.values())
                        decision = self.risk_manager.check_order(
                            sig.symbol, pos.direction, pos.notional, pos.margin,
                            equity, step, market[sig.symbol], idx,
                            current_positions_margin=cur_margin,
                            current_positions_count=len(positions),
                        )
                        if not decision.allowed:
                            continue
                    positions[sig.symbol] = pos
                    if self.risk_manager is not None:
                        self.risk_manager._track_open(sig.symbol, pos.margin)
                    opened_symbols.add(sig.symbol)
                    if self.risk_manager is not None:
                        self.risk_manager._track_open(sig.symbol, pos.margin)
                    entry_fee = pos.notional * self.config.taker_fee
                    equity -= entry_fee
                    free_margin_limit -= pos.margin

            peak = max(peak, equity)
            max_drawdown = max(max_drawdown, (peak - equity) / peak if peak else 0.0)
            if step % 8 == 0:
                equity_curve.append((self._time_for_ts(market, index, ts), round(equity, 4)))

        for symbol, pos in list(positions.items()):
            idx = index[symbol].get(timeline[-1])
            if idx is None:
                continue
            bar = market[symbol][idx]
            fee = pos.notional * self.config.taker_fee
            exit_price = bar.close * (1.0 - self.config.slippage * pos.direction)
            gross = pos.direction * (exit_price - pos.entry) / pos.entry * pos.notional
            pnl = gross - fee
            before = equity
            equity += pnl
            trades.append(
                Trade(
                    symbol=symbol,
                    direction="long" if pos.direction > 0 else "short",
                    entry_time=pos.entry_time,
                    exit_time=bar.time,
                    entry=round(pos.entry, 8),
                    exit=round(exit_price, 8),
                    notional=round(pos.notional, 4),
                    pnl=round(pnl, 4),
                    pnl_pct_equity=round(pnl / before * 100.0, 4) if before > 0 else 0.0,
                    regime=pos.regime,
                    reason=pos.reason,
                    exit_reason="end_of_test",
                    win=pnl > 0,
                )
            )
            if self.risk_manager is not None:
                self.risk_manager.on_trade_close(pnl, len(timeline) - 1)

        wins = sum(1 for trade in trades if trade.win)
        pnl = equity - self.config.start_equity
        return_pct = pnl / self.config.start_equity * 100.0
        min_return = self.config.validation_target_returns.get(days or 0)
        by_symbol: dict[str, dict[str, float]] = {}
        by_regime: dict[str, dict[str, float]] = {}
        by_reason: dict[str, dict[str, float]] = {}
        for trade in trades:
            for bucket, key in ((by_symbol, trade.symbol), (by_regime, trade.regime), (by_reason, trade.reason)):
                item = bucket.setdefault(key, {"trades": 0, "wins": 0, "pnl": 0.0})
                item["trades"] += 1
                item["wins"] += 1 if trade.win else 0
                item["pnl"] += trade.pnl
        for bucket in (by_symbol, by_regime, by_reason):
            for item in bucket.values():
                item["win_rate"] = item["wins"] / item["trades"] if item["trades"] else 0.0
                item["pnl"] = round(item["pnl"], 4)

        return {
            "available": True,
            "days": days,
            "from": self._time_for_ts(market, index, timeline[0]),
            "to": self._time_for_ts(market, index, timeline[-1]),
            "start_equity": self.config.start_equity,
            "end_equity": round(equity, 4),
            "pnl": round(pnl, 4),
            "return_pct": round(return_pct, 4),
            "max_drawdown_pct": round(max_drawdown * 100.0, 4),
            "trades": len(trades),
            "wins": wins,
            "losses": len(trades) - wins,
            "win_rate": round(wins / len(trades), 4) if trades else 0.0,
            "target_pass": pnl > self.config.validation_target_profit
            and (wins / len(trades) if trades else 0.0) >= self.config.validation_target_win_rate
            and (min_return is None or return_pct >= min_return),
            "return_target_pass": min_return is None or return_pct >= min_return,
            "selected_symbols_initial": sorted(self._select_symbols_for_window(market, timeline[0], days, symbol_limit)),
            "by_symbol": by_symbol,
            "by_regime": by_regime,
            "by_reason": by_reason,
            "router_rejections": router_rejections,
            "equity_curve": equity_curve,
            "trades_detail": [asdict(trade) for trade in trades],
            "risk_status": {
                "pauses_triggered": self.risk_manager._pauses_count if self.risk_manager else 0,
                "orders_rejected": self.risk_manager._rejections_count if self.risk_manager else 0,
                "rejections_by_reason": (
                    self.risk_manager.get_rejection_breakdown() if self.risk_manager else {}
                ),
                "final_status": asdict(self.risk_manager.get_status()) if self.risk_manager else None,
            },
            "candidate_pool_status": {
                "retrain_count": cp_retrain_count,
                "retrain_failures": cp_retrain_failures,
                "precomputed_cache": bool(self.config.cp_candidate_cache_path),
                "active_regimes": cp_active_regimes,
                "regime_policy_history": cp_regime_policy_history,
                "quality_rates": {
                    f"{direction}:{regime}:{pattern}": round(rate, 4)
                    for (direction, regime, pattern), rate in cp_quality_rates.items()
                },
            },
        }

    def _open_position(
        self, sig: Signal, bar: FeatureBar, idx: int, equity: float, free_margin_limit: float
    ) -> Position | None:
        risk = self.config.leverage_caps.get(sig.symbol)
        leverage_cap = risk.max_leverage if risk else 10.0
        leverage = min(leverage_cap, max(2.0, 1.0 / max(bar.atr_pct * 3.4, 0.02)))
        direction = -sig.direction if self.config.invert_signals else sig.direction
        entry = bar.close * (1.0 + self.config.slippage * direction)
        stop_atr = self._stop_atr_for_signal(sig)
        take_profit_atr = self._take_profit_atr_for_signal(sig, equity)
        risk_per_trade = self._risk_per_trade_for_signal(sig)
        if equity < self.config.start_equity * self.config.defensive_equity_fraction:
            risk_per_trade *= self.config.defensive_risk_multiplier
        if equity > self.config.start_equity * self.config.profit_lock_equity_fraction:
            risk_per_trade *= self.config.profit_lock_risk_multiplier
        stop_dist = max(bar.atr * stop_atr, entry * 0.0025)
        symbol_risk_multiplier = self.config.symbol_risk_multipliers.get(sig.symbol, 1.0)
        reason_risk_multiplier = self.config.reason_risk_multipliers.get(sig.reason, 1.0)
        volatility_multiplier = self._volatility_risk_multiplier(bar)
        state_multiplier = self._state_risk_multiplier(sig, bar)
        risk_amount = (
            equity
            * risk_per_trade
            * symbol_risk_multiplier
            * reason_risk_multiplier
            * min(1.25, sig.score / 2.6)
            * volatility_multiplier
            * state_multiplier
        )
        notional_by_risk = risk_amount / (stop_dist / entry)
        margin_fraction = self.config.max_margin_fraction
        if equity < self.config.start_equity * self.config.defensive_equity_fraction:
            margin_fraction = min(margin_fraction, self.config.defensive_margin_fraction)
        if equity > self.config.start_equity * self.config.profit_lock_equity_fraction:
            margin_fraction = min(margin_fraction, self.config.profit_lock_margin_fraction)
        margin_fraction *= volatility_multiplier
        margin_fraction *= reason_risk_multiplier
        margin_fraction *= state_multiplier
        margin_cap = min(equity * margin_fraction, free_margin_limit)
        notional = min(notional_by_risk, margin_cap * leverage)
        min_notional = risk.min_notional if risk else 5.0
        if notional < min_notional:
            return None
        margin = notional / leverage
        qty = notional / entry
        max_loss_amount = equity * self.config.max_trade_loss_pct_equity / 100.0
        if max_loss_amount > 0 and max_loss_amount < 999 * equity:
            max_stop_dist = entry * max_loss_amount / max(notional, 1e-9)
            stop_dist = min(stop_dist, max(max_stop_dist, entry * 0.0025))
        stop = entry - direction * stop_dist
        take_profit = entry + direction * max(bar.atr * take_profit_atr, entry * 0.0022)
        trail = stop
        return Position(
            symbol=sig.symbol,
            direction=direction,
            entry_idx=idx,
            entry_time=bar.time,
            entry=entry,
            notional=notional,
            margin=margin,
            qty=qty,
            stop=stop,
            take_profit=take_profit,
            trail=trail,
            leverage=leverage,
            regime=sig.regime,
            reason=sig.reason,
        )

    def _symbol_limit_for_window(self, days: int | None) -> int:
        if days is not None and days >= self.config.long_window_days:
            return self.config.long_window_symbol_limit
        if days is not None and days <= self.config.short_window_days:
            return self.config.short_window_symbol_limit
        return self.config.active_symbol_limit

    def _select_symbols_for_window(
        self, market: dict[str, list[FeatureBar]], ts: int, days: int | None, limit: int
    ) -> list[str]:
        if days is not None and days >= self.config.long_window_days:
            preferred = {symbol for symbol in self.config.long_window_preferred_symbols if symbol in market}
            if preferred:
                preferred_market = {symbol: bars for symbol, bars in market.items() if symbol in preferred}
                return select_symbols(preferred_market, ts, limit=limit, config=self.config)
        return select_symbols(market, ts, limit=limit, config=self.config)

    def _blocked_by_reversal_risk(self, sig: Signal, bars: list[FeatureBar], idx: int) -> bool:
        if sig.direction < 0:
            lookback = self.config.short_rebound_lookback_bars
            if idx < lookback:
                return False
            start = bars[idx - lookback]
            bar = bars[idx]
            momentum = bar.close / start.close - 1.0 if start.close else 0.0
            vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
            near_breakdown_low = bar.close <= bar.donchian_low * 1.012
            exhaustion_chase = (
                momentum <= self.config.short_exhaustion_drop_pct
                and bar.rsi <= self.config.short_exhaustion_rsi_ceiling
                and vol_ratio >= self.config.short_exhaustion_volume_ratio
                and near_breakdown_low
            )
            if exhaustion_chase:
                return True
            ema_slope_up = bar.ema20 > bars[max(0, idx - 12)].ema20
            return (
                momentum >= self.config.short_rebound_block_pct
                and bar.rsi >= self.config.short_rebound_rsi_floor
                and (bar.close > bar.ema50 or ema_slope_up)
            )
        if sig.direction > 0:
            lookback = self.config.long_flush_lookback_bars
            if idx < lookback:
                return False
            start = bars[idx - lookback]
            bar = bars[idx]
            momentum = bar.close / start.close - 1.0 if start.close else 0.0
            vol_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
            near_breakout_high = bar.close >= bar.donchian_high * 0.988
            exhaustion_chase = (
                momentum >= self.config.long_exhaustion_rise_pct
                and bar.rsi >= self.config.long_exhaustion_rsi_floor
                and vol_ratio >= self.config.long_exhaustion_volume_ratio
                and near_breakout_high
            )
            if exhaustion_chase:
                return True
            ema_slope_down = bar.ema20 < bars[max(0, idx - 12)].ema20
            return (
                momentum <= self.config.long_flush_block_pct
                and bar.rsi <= self.config.long_flush_rsi_ceiling
                and (bar.close < bar.ema50 or ema_slope_down)
            )
        return False

    def _exit_price(self, pos: Position, bar: FeatureBar, idx: int) -> tuple[float | None, str]:
        if pos.reason == "ml_long":
            trailing_atr = self.config.ml_trailing_atr
            max_hold_bars = self.config.ml_max_hold_bars
        elif (
            self.config.router_trend_short_factor_gate_enabled
            and pos.reason == "trend_short"
        ):
            trailing_atr = self.config.trend_short_factor_trailing_atr
            max_hold_bars = self.config.trend_short_factor_max_hold_bars
        elif self._is_attack_reason(pos.reason):
            trailing_atr = self.config.attack_trailing_atr
            max_hold_bars = self.config.attack_max_hold_bars
        elif self._is_micro_momentum_reason(pos.reason):
            trailing_atr = self.config.micro_momentum_trailing_atr
            max_hold_bars = self.config.micro_momentum_max_hold_bars
        elif self._is_funding_reason(pos.reason):
            trailing_atr = self.config.funding_trailing_atr
            max_hold_bars = self.config.funding_max_hold_bars
        elif self._is_open_interest_reason(pos.reason):
            trailing_atr = self.config.open_interest_trailing_atr
            max_hold_bars = self.config.open_interest_max_hold_bars
        elif self._is_trade_flow_reason(pos.reason):
            trailing_atr = self.config.trade_flow_trailing_atr
            max_hold_bars = self.config.trade_flow_max_hold_bars
        elif self._is_order_book_reason(pos.reason):
            trailing_atr = self.config.order_book_trailing_atr
            max_hold_bars = self.config.order_book_max_hold_bars
        elif self._is_continuation_reason(pos.reason):
            trailing_atr = self.config.continuation_trailing_atr
            max_hold_bars = self.config.continuation_max_hold_bars
        elif self._is_adaptive_trend_position(pos):
            trailing_atr = self.config.adaptive_trend_trailing_atr
            max_hold_bars = self.config.adaptive_trend_max_hold_bars
        elif self._is_range_revert_reason(pos.reason):
            trailing_atr = self.config.range_trailing_atr
            max_hold_bars = self.config.range_max_hold_bars
        elif pos.reason.startswith("cp_"):
            trailing_atr = self.config.cp_trailing_atr
            max_hold_bars = self.config.cp_max_hold_bars
        else:
            trailing_atr = self.config.trailing_atr
            max_hold_bars = self.config.max_hold_bars
        favorable, adverse = self._bar_path_extremes(pos, bar)
        pos.max_favorable_pct = max(pos.max_favorable_pct, favorable)
        pos.max_adverse_pct = min(pos.max_adverse_pct, adverse)
        trail_dist = max(bar.atr * trailing_atr, pos.entry * 0.002)
        early_exit_price = self._early_failure_exit_price(pos, bar, idx)
        if early_exit_price is not None:
            return early_exit_price, "early_failure"

        # Break-even logic: move stop to entry + small lock once MFE threshold is reached
        be_mfe = getattr(self.config, "trend_short_factor_break_even_mfe_pct", 0.0)
        be_lock = getattr(self.config, "trend_short_factor_break_even_lock_pct", 0.0)
        if (
            self.config.router_trend_short_factor_gate_enabled
            and pos.reason == "trend_short"
            and be_mfe > 0
            and pos.max_favorable_pct >= be_mfe
        ):
            if pos.direction > 0:
                be_stop = pos.entry * (1.0 + be_lock)
                pos.trail = max(pos.trail, be_stop)
            else:
                be_stop = pos.entry * (1.0 - be_lock)
                pos.trail = min(pos.trail, be_stop)

        if pos.direction > 0:
            pos.trail = max(pos.trail, bar.close - trail_dist)
            stop_price = max(pos.stop, pos.trail)
            if bar.low <= stop_price:
                return stop_price * (1.0 - self.config.slippage), "stop_or_trail"
            if bar.high >= pos.take_profit:
                return pos.take_profit * (1.0 - self.config.slippage), "take_profit"
            if idx - pos.entry_idx >= max_hold_bars and bar.close < bar.ema20:
                return bar.close * (1.0 - self.config.slippage), "time_exit"
        else:
            pos.trail = min(pos.trail, bar.close + trail_dist)
            stop_price = min(pos.stop, pos.trail)
            if bar.high >= stop_price:
                return stop_price * (1.0 + self.config.slippage), "stop_or_trail"
            if bar.low <= pos.take_profit:
                return pos.take_profit * (1.0 + self.config.slippage), "take_profit"
            if idx - pos.entry_idx >= max_hold_bars and bar.close > bar.ema20:
                return bar.close * (1.0 + self.config.slippage), "time_exit"
        return None, ""

    def _bar_path_extremes(self, pos: Position, bar: FeatureBar) -> tuple[float, float]:
        if pos.direction > 0:
            favorable = bar.high / pos.entry - 1.0
            adverse = bar.low / pos.entry - 1.0
        else:
            favorable = pos.entry / bar.low - 1.0
            adverse = pos.entry / bar.high - 1.0
        return favorable, adverse

    def _early_failure_exit_price(self, pos: Position, bar: FeatureBar, idx: int) -> float | None:
        if self.config.early_failure_bars <= 0:
            return None
        if self.config.early_failure_reasons and pos.reason not in self.config.early_failure_reasons:
            return None
        bars_held = idx - pos.entry_idx
        if bars_held < self.config.early_failure_bars:
            return None
        if pos.max_favorable_pct >= self.config.early_failure_min_mfe_pct:
            return None
        if pos.max_adverse_pct > -self.config.early_failure_max_mae_pct:
            return None
        return bar.close * (1.0 - self.config.slippage * pos.direction)

    @staticmethod
    def _is_attack_reason(reason: str) -> bool:
        return reason.startswith("attack_")

    @staticmethod
    def _is_continuation_reason(reason: str) -> bool:
        return reason.startswith("continuation_")

    @staticmethod
    def _is_micro_momentum_reason(reason: str) -> bool:
        return reason.startswith("micro_momentum_")

    @staticmethod
    def _is_funding_reason(reason: str) -> bool:
        return reason.startswith("funding_")

    @staticmethod
    def _is_open_interest_reason(reason: str) -> bool:
        return reason.startswith("open_interest_")

    @staticmethod
    def _is_trade_flow_reason(reason: str) -> bool:
        return reason.startswith("trade_flow_")

    def _is_trend_short_factor(self, sig: Signal) -> bool:
        """Check if signal is a trend_short under factor gate."""
        return (
            self.config.router_trend_short_factor_gate_enabled
            and sig.reason == "trend_short"
        )

    @staticmethod
    def _is_order_book_reason(reason: str) -> bool:
        return reason.startswith("order_book_")

    def _is_adaptive_trend_signal(self, sig: Signal) -> bool:
        return (
            self.config.enable_adaptive_profiles
            and sig.reason.startswith("trend_")
            and sig.regime in self.config.adaptive_trend_allowed_regimes
        )

    def _is_adaptive_trend_position(self, pos: Position) -> bool:
        return (
            self.config.enable_adaptive_profiles
            and pos.reason.startswith("trend_")
            and pos.regime in self.config.adaptive_trend_allowed_regimes
        )

    @staticmethod
    def _is_range_revert_reason(reason: str) -> bool:
        return reason.startswith("range_revert_")
    
    # Regime-aware策略选择: 基于行情结构决定是否交易
    _REGIME_STRATEGIES = {
        "uptrend": {"trend_long", "attack_breakout_long", "range_revert_long", "micro_momentum_long", "funding_extreme_long", "open_interest_breakout_long"},
        "downtrend": {"trend_short", "attack_breakout_short", "range_revert_short", "micro_momentum_short", "funding_extreme_short", "open_interest_breakout_short"},
        "range": {"range_revert_long", "range_revert_short", "attack_exhaustion_long", "attack_exhaustion_short", "continuation_long", "continuation_short", "micro_momentum_long", "micro_momentum_short", "funding_extreme_long", "funding_extreme_short", "open_interest_breakout_long", "open_interest_breakout_short"},
        "transition": {"transition_breakout_long", "transition_breakout_short", "volatility_breakout_long", "volatility_breakout_short", "continuation_long", "continuation_short", "funding_extreme_long", "funding_extreme_short", "open_interest_breakout_long", "open_interest_breakout_short"},
    }
    
    def _regime_allows_signal(self, sig: Signal) -> bool:
        """根据当前regime判断是否允许交易该信号

        原则 (不过拟合):
        - 趋势市只做顺势 (避免逆势亏损)
        - 震荡市只做反转 (range_revert)
        - 规则基于市场结构, 不是历史表现
        """
        # Candidate pool signals have their own regime/pattern filtering
        if sig.reason.startswith("cp_"):
            return True
        allowed = self._REGIME_STRATEGIES.get(sig.regime, set())
        return sig.reason in allowed

    def _dynamic_router_allows_signal(self, sig: Signal) -> bool:
        return self._dynamic_router_rejection_reason(sig) is None

    def _dynamic_router_rejection_reason(self, sig: Signal, bar: FeatureBar | None = None) -> str | None:
        if not self.config.enable_dynamic_strategy_router:
            return None
        if sig.reason in self.config.router_blocked_reasons:
            return "blocked_reason"
        if self.config.router_allowed_reasons and sig.reason not in self.config.router_allowed_reasons:
            return "not_allowed_reason"
        allowed_regimes = self.config.router_reason_allowed_regimes.get(sig.reason)
        if allowed_regimes and sig.regime not in allowed_regimes:
            return "configured_regime_mismatch"
        if not self._regime_allows_signal(sig):
            return "regime_structure_mismatch"
        if (
            self.config.router_trend_short_factor_gate_enabled
            and sig.reason == "trend_short"
            and bar is not None
            and not self._trend_short_factor_gate_allows(bar)
        ):
            return "trend_short_factor_mismatch"
        return None

    def _trend_short_factor_gate_allows(self, bar: FeatureBar) -> bool:
        volume_ratio = bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0
        ema20_distance = abs(bar.close / bar.ema20 - 1.0) if bar.close and bar.ema20 else 0.0
        max_ema_distance = max(
            bar.atr_pct * self.config.router_trend_short_max_ema20_distance_atr,
            self.config.router_trend_short_max_ema20_distance_pct,
        )
        return (
            abs(bar.trend_strength) >= self.config.router_trend_short_min_trend_strength_abs
            and bar.trend_strength < 0
            and volume_ratio >= self.config.router_trend_short_min_volume_ratio
            and self.config.router_trend_short_rsi_min <= bar.rsi <= self.config.router_trend_short_rsi_max
            and ema20_distance <= max_ema_distance
        )

    def _stop_atr_for_signal(self, sig: Signal) -> float:
        if sig.reason == "ml_long":
            return self.config.ml_stop_atr
        if sig.reason.startswith("cp_"):
            return self.config.cp_stop_atr
        if self._is_trend_short_factor(sig):
            return self.config.trend_short_factor_stop_atr
        if self._is_attack_reason(sig.reason):
            return self.config.attack_stop_atr
        if self._is_micro_momentum_reason(sig.reason):
            return self.config.micro_momentum_stop_atr
        if self._is_funding_reason(sig.reason):
            return self.config.funding_stop_atr
        if self._is_open_interest_reason(sig.reason):
            return self.config.open_interest_stop_atr
        if self._is_trade_flow_reason(sig.reason):
            return self.config.trade_flow_stop_atr
        if self._is_order_book_reason(sig.reason):
            return self.config.order_book_stop_atr
        if self._is_continuation_reason(sig.reason):
            return self.config.continuation_stop_atr
        if self._is_adaptive_trend_signal(sig):
            return self.config.adaptive_trend_stop_atr
        if self._is_range_revert_reason(sig.reason):
            return self.config.range_stop_atr
        return self.config.stop_atr

    def _take_profit_atr_for_signal(self, sig: Signal, equity: float | None = None) -> float:
        if sig.reason == "ml_long":
            return self.config.ml_take_profit_atr
        if sig.reason.startswith("cp_"):
            return self.config.cp_take_profit_atr
        if self._is_trend_short_factor(sig):
            return self.config.trend_short_factor_take_profit_atr
        if self._is_attack_reason(sig.reason):
            return self.config.attack_take_profit_atr
        if self._is_micro_momentum_reason(sig.reason):
            return self.config.micro_momentum_take_profit_atr
        if self._is_funding_reason(sig.reason):
            return self.config.funding_take_profit_atr
        if self._is_open_interest_reason(sig.reason):
            return self.config.open_interest_take_profit_atr
        if self._is_trade_flow_reason(sig.reason):
            return self.config.trade_flow_take_profit_atr
        if self._is_order_book_reason(sig.reason):
            return self.config.order_book_take_profit_atr
        if self._is_continuation_reason(sig.reason):
            return self.config.continuation_take_profit_atr
        if self._is_adaptive_trend_signal(sig):
            return self.config.adaptive_trend_take_profit_atr
        if self._is_range_revert_reason(sig.reason):
            if (
                equity is not None
                and self.config.defensive_range_exit_equity_fraction > 0
                and self.config.defensive_range_take_profit_atr > 0
                and equity <= self.config.start_equity * self.config.defensive_range_exit_equity_fraction
            ):
                return min(self.config.range_take_profit_atr, self.config.defensive_range_take_profit_atr)
            return self.config.range_take_profit_atr
        return self.config.take_profit_atr

    def _risk_per_trade_for_signal(self, sig: Signal) -> float:
        if sig.reason == "ml_long":
            return self.config.ml_risk_per_trade
        if sig.reason.startswith("cp_"):
            base_risk = self.config.cp_risk_per_trade
            if self.config.cp_dynamic_regime_risk_scaling:
                base_risk *= getattr(self, "_cp_regime_risk_multipliers", {}).get(sig.regime, 1.0)
            return base_risk
        if self._is_trend_short_factor(sig):
            return self.config.trend_short_factor_risk_per_trade
        if self._is_attack_reason(sig.reason):
            return self.config.attack_risk_per_trade
        if self._is_micro_momentum_reason(sig.reason):
            return self.config.micro_momentum_risk_per_trade
        if self._is_funding_reason(sig.reason):
            return self.config.funding_risk_per_trade
        if self._is_open_interest_reason(sig.reason):
            return self.config.open_interest_risk_per_trade
        if self._is_trade_flow_reason(sig.reason):
            return self.config.trade_flow_risk_per_trade
        if self._is_order_book_reason(sig.reason):
            return self.config.order_book_risk_per_trade
        if self._is_continuation_reason(sig.reason):
            return self.config.continuation_risk_per_trade
        if self._is_adaptive_trend_signal(sig):
            return self.config.adaptive_trend_risk_per_trade
        return self.config.risk_per_trade

    def _volatility_risk_multiplier(self, bar: FeatureBar) -> float:
        if bar.atr_pct <= 0 or self.config.volatility_target_atr_pct <= 0:
            return 1.0
        raw = (self.config.volatility_target_atr_pct / bar.atr_pct) ** self.config.volatility_risk_power
        return max(self.config.volatility_risk_floor, min(1.0, raw))

    def _state_risk_multiplier(self, sig: Signal, bar: FeatureBar) -> float:
        if sig.reason == "range_revert_long" and bar.close < bar.ema200 and bar.ema20 < bar.ema50:
            return self.config.bearish_range_long_risk_multiplier
        if sig.reason == "range_revert_short" and bar.close > bar.ema200 and bar.ema20 > bar.ema50:
            return self.config.bullish_range_short_risk_multiplier
        return 1.0

    def _cooldown_bars_for(self, pos: Position) -> int:
        if self._is_micro_momentum_reason(pos.reason):
            return self.config.attack_cooldown_bars
        return self.config.attack_cooldown_bars if self._is_attack_reason(pos.reason) else self.config.cooldown_bars

    def _loss_cooldown_bars_for(self, pos: Position) -> int:
        return (
            self.config.attack_loss_cooldown_bars
            if self._is_attack_reason(pos.reason) or self._is_micro_momentum_reason(pos.reason)
            else self.config.loss_cooldown_bars
        )

    @staticmethod
    def _time_for_ts(market: dict[str, list[FeatureBar]], index: dict[str, dict[int, int]], ts: int) -> str:
        for symbol, idx_map in index.items():
            idx = idx_map.get(ts)
            if idx is not None:
                return market[symbol][idx].time
        return str(ts)

    @staticmethod
    def _filter_market_for_window(
        market: dict[str, list[FeatureBar]], days: int | None
    ) -> dict[str, list[FeatureBar]]:
        if days is None or not market:
            return market
        latest_ts = max(bars[-1].ts for bars in market.values() if bars)
        required_start = latest_ts - days * 24 * 60 * 60 * 1000
        filtered = {
            symbol: bars
            for symbol, bars in market.items()
            if bars and bars[0].ts <= required_start and bars[-1].ts >= latest_ts - 24 * 60 * 60 * 1000
        }
        return filtered or market


def run_report(data_dir: Path, report_path: Path, config: BacktestConfig) -> dict:
    market = load_market(
        data_dir,
        config.timeframe_minutes,
        include_funding=config.enable_funding_module,
        include_open_interest=config.enable_open_interest_module,
        include_trade_flow=config.enable_trade_flow_module,
        include_order_book=config.enable_order_book_module,
    )
    if config.allowed_symbols:
        market = {s: bars for s, bars in market.items() if s in config.allowed_symbols}
    if config.excluded_symbols:
        excluded = set(config.excluded_symbols)
        market = {s: bars for s, bars in market.items() if s not in excluded}
    full_timeline = sorted({bar.ts for bars in market.values() for bar in bars})
    available_days = 0.0
    if full_timeline:
        available_days = (full_timeline[-1] - full_timeline[0]) / 86_400_000.0
    report = {
        "config": asdict(config),
        "data_dir": str(data_dir),
        "symbols": sorted(market),
        "available_days": round(available_days, 4),
        "windows": {},
    }
    for days in config.windows_days:
        window_config = config_for_window(config, days, tuple(market))
        tester = Backtester(window_config)
        window_market = Backtester._filter_market_for_window(market, days)
        window_timeline = _common_timeline(window_market, min_count_fraction=0.50)
        window_days = 0.0
        if window_timeline:
            window_days = (window_timeline[-1] - window_timeline[0]) / 86_400_000.0
        tolerance_days = config.timeframe_minutes / 1440.0 + 0.01
        if window_days + tolerance_days < days:
            report["windows"][str(days)] = {
                "available": False,
                "days": days,
                "reason": f"eligible symbols have {window_days:.2f} overlapping days; download at least {days} days",
            }
            continue
        report["windows"][str(days)] = tester.run(market, days=days)
    report["audit"] = audit_report(
        report,
        required_windows=config.windows_days,
        min_win_rate=config.validation_target_win_rate,
        min_pnl=config.validation_target_profit,
        min_pnl_by_window=config.validation_target_profit_by_window,
        min_return_by_window=config.validation_target_returns,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def config_for_window(config: BacktestConfig, days: int | None, symbols: tuple[str, ...]) -> BacktestConfig:
    if days is not None and config.enable_target_window_profiles:
        if days >= 365:
            preferred = config.long_window_preferred_symbols or config.target_long_window_preferred_symbols
            return replace(
                config,
                risk_per_trade=0.36,
                max_margin_fraction=config.long_window_aggressive_max_margin_fraction,
                max_positions=1,
                active_symbol_limit=3,
                long_window_symbol_limit=5,
                selector_noise_penalty=6.0,
                selector_min_avg_quote=0.0,
                selector_max_micro_noise=0.0,
                stop_atr=3.0,
                trailing_atr=2.55,
                range_stop_atr=3.0,
                range_take_profit_atr=1.0,
                range_trailing_atr=2.55,
                short_rebound_block_pct=0.045,
                transition_long_enabled=True,
                min_score=2.45,
                enable_attack_module=True,
                enable_long_window_aggressive_profile=True,
                long_window_preferred_symbols=preferred,
                cooldown_bars=config.long_window_aggressive_cooldown_bars,
                max_total_margin_fraction=config.long_window_aggressive_max_total_margin_fraction,
                leverage_caps={
                    symbol: SymbolRisk(config.long_window_aggressive_leverage)
                    for symbol in symbols
                },
            )
        if days == 180:
            return replace(
                config,
                risk_per_trade=0.39,
                max_margin_fraction=1.95,
                max_total_margin_fraction=1.65,
                excluded_symbols=config.target_180_excluded_symbols + ('NEAR-USDT-SWAP', 'DOT-USDT-SWAP', 'ARB-USDT-SWAP'),
                profit_lock_equity_fraction=999.0,
                profit_lock_risk_multiplier=1.0,
                profit_lock_margin_fraction=1.0,
                defensive_equity_fraction=0.0,
            )
        if days == 90:
            return replace(
                config,
                risk_per_trade=0.9,
                max_margin_fraction=1.0,
                max_total_margin_fraction=1.5,
                max_positions=4,
                active_symbol_limit=8,
                short_window_symbol_limit=8,
                min_score=3.25,
                range_take_profit_atr=1.25,
                range_stop_atr=2.4,
                range_trailing_atr=1.56,
                enable_attack_module=True,
                attack_min_score=4.0,
                attack_risk_per_trade=0.025,
                attack_breakout_enabled=False,
                excluded_symbols=config.target_window_excluded_symbols,
                profit_lock_equity_fraction=999.0,
                profit_lock_risk_multiplier=1.0,
                profit_lock_margin_fraction=1.0,
                defensive_equity_fraction=0.0,
            )
        if days in (60, 30):
            return replace(
                config,
                risk_per_trade=0.39,
                max_margin_fraction=1.95,
                max_total_margin_fraction=1.65,
                max_positions=4,
                active_symbol_limit=8,
                short_window_symbol_limit=8,
                min_score=3.25,
                range_take_profit_atr=1.25,
                range_stop_atr=2.4,
                range_trailing_atr=1.56,
                enable_attack_module=True,
                attack_min_score=4.0,
                attack_risk_per_trade=0.025,
                attack_breakout_enabled=False,
                enable_micro_momentum_module=False,
                micro_momentum_risk_per_trade=0.06,
                micro_momentum_min_volume_ratio=2.0,
                micro_momentum_take_profit_atr=0.8,
                micro_momentum_stop_atr=1.4,
                micro_momentum_trailing_atr=1.0,
                micro_momentum_max_hold_bars=4,
                excluded_symbols=config.target_window_excluded_symbols,
                profit_lock_equity_fraction=999.0,
                profit_lock_risk_multiplier=1.0,
                profit_lock_margin_fraction=1.0,
                defensive_equity_fraction=0.0,
            )
        if days == 14:
            return replace(
                config,
                risk_per_trade=0.39,
                max_margin_fraction=1.65,
                max_total_margin_fraction=1.65,
                max_positions=2,
                active_symbol_limit=6,
                short_window_symbol_limit=10,
                min_score=3.25,
                range_take_profit_atr=1.0,
                range_stop_atr=2.4,
                range_trailing_atr=1.56,
                enable_attack_module=False,
                excluded_symbols=("BNB-USDT-SWAP",),
                profit_lock_equity_fraction=999.0,
                profit_lock_risk_multiplier=1.0,
                profit_lock_margin_fraction=1.0,
                defensive_equity_fraction=0.0,
                max_trade_loss_pct_equity=20.0,
            )
        if days == 7:
            return replace(
                config,
                risk_per_trade=0.32,
                max_margin_fraction=0.85,
                max_total_margin_fraction=2.0,
                max_positions=4,
                active_symbol_limit=10,
                short_window_symbol_limit=5,
                min_score=3.05,
                range_take_profit_atr=0.55,
                range_stop_atr=1.8,
                range_trailing_atr=1.56,
                enable_attack_module=True,
                attack_min_score=4.3,
                attack_risk_per_trade=0.05,
                attack_breakout_enabled=True,
                enable_micro_momentum_module=False,
                micro_momentum_risk_per_trade=0.08,
                micro_momentum_min_volume_ratio=1.8,
                micro_momentum_take_profit_atr=0.8,
                micro_momentum_stop_atr=1.4,
                micro_momentum_trailing_atr=1.0,
                micro_momentum_max_hold_bars=4,
                excluded_symbols=("BNB-USDT-SWAP",),
                max_trade_loss_pct_equity=20.0,
            )
    if (
        days is not None
        and config.enable_long_window_aggressive_profile
        and days >= config.long_window_days
    ):
        return replace(
            config,
            cooldown_bars=config.long_window_aggressive_cooldown_bars,
            max_margin_fraction=config.long_window_aggressive_max_margin_fraction,
            max_total_margin_fraction=config.long_window_aggressive_max_total_margin_fraction,
            profit_lock_equity_fraction=999.0,
            profit_lock_risk_multiplier=1.0,
            profit_lock_margin_fraction=1.0,
            leverage_caps={
                symbol: SymbolRisk(config.long_window_aggressive_leverage)
                for symbol in symbols
            },
        )
    return config


def save_backtest_to_db(report: dict, db_path: Path | None = None) -> str | None:
    """Persist a backtest report's trades to SQLite.

    Parameters
    ----------
    report : dict
        The dict returned by ``Backtester.run()`` or ``run_report()``.
    db_path : Path, optional
        Where to create/open the database.  Defaults to
        ``reports/backtest_state.db`` relative to the report's data_dir.

    Returns
    -------
    str or None
        Path to the database file, or None if no trades to save.
    """
    from state_db import StateDB

    trades = report.get("trades_detail", [])
    if not trades:
        return None

    if db_path is None:
        data_dir = Path(report.get("data_dir", "data"))
        db_path = data_dir.parent / "reports" / "backtest_state.db"

    db = StateDB(db_path)
    try:
        count = db.save_backtest_trades(trades)
        # Also snapshot the final account state
        db.snapshot_account(
            equity=report.get("end_equity", 0.0),
            available_margin=0.0,
            used_margin=0.0,
            unrealized_pnl=0.0,
            open_positions=0,
            risk_status=json.dumps(report.get("risk_status", {}), ensure_ascii=False),
        )
        return str(db_path)
    finally:
        db.close()

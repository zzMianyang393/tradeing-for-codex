"""ML-based signal generator using XGBoost.

Trains on historical FeatureBar data to predict profitable trade direction.
Uses sliding window approach to adapt to changing market conditions.

Usage:
    python ml_signal.py --data data --out reports/ml_signal_eval.json
    python ml_signal.py --data data --train-days 180 --test-days 30 --out reports/ml_signal_eval.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("ml_signal")

# Feature columns extracted from FeatureBar
FEATURE_COLUMNS = [
    "ema20", "ema50", "ema200", "atr", "atr_pct", "rsi",
    "bb_mid", "bb_upper", "bb_lower", "vol_sma",
    "donchian_high", "donchian_low", "trend_strength",
    "volume_ratio", "close_to_ema20", "close_to_ema50",
    "close_to_donchian_high", "close_to_donchian_low",
    "bb_position", "candle_body_pct", "candle_range_pct",
    "upper_shadow_pct", "lower_shadow_pct",
]


@dataclass
class MLSignalConfig:
    train_days: int = 180
    test_days: int = 30
    step_days: int = 30
    forward_bars: int = 96  # ~1 day on 15m
    profit_threshold_pct: float = 0.005  # 0.5% profit = profitable
    min_training_samples: int = 500
    n_estimators: int = 100
    max_depth: int = 6
    learning_rate: float = 0.1
    min_score: float = 0.6  # minimum prediction probability


@dataclass
class MLSignalResult:
    window_start: str = ""
    window_end: str = ""
    train_samples: int = 0
    test_samples: int = 0
    predictions: int = 0
    correct: int = 0
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    total_pnl_pct: float = 0.0
    trades: int = 0
    profitable_trades: int = 0
    win_rate: float = 0.0


def extract_features(bar: Any) -> dict[str, float]:
    """Extract feature vector from a FeatureBar."""
    close = getattr(bar, "close", 0.0)
    ema20 = getattr(bar, "ema20", 0.0)
    ema50 = getattr(bar, "ema50", 0.0)
    ema200 = getattr(bar, "ema200", 0.0)
    atr = getattr(bar, "atr", 0.0)
    atr_pct = getattr(bar, "atr_pct", 0.0)
    rsi = getattr(bar, "rsi", 50.0)
    bb_mid = getattr(bar, "bb_mid", 0.0)
    bb_upper = getattr(bar, "bb_upper", 0.0)
    bb_lower = getattr(bar, "bb_lower", 0.0)
    vol_sma = getattr(bar, "vol_sma", 0.0)
    don_high = getattr(bar, "donchian_high", 0.0)
    don_low = getattr(bar, "donchian_low", 0.0)
    trend_strength = getattr(bar, "trend_strength", 0.0)
    volume_quote = getattr(bar, "volume_quote", 0.0)
    bar_open = getattr(bar, "open", 0.0)
    high = getattr(bar, "high", 0.0)
    low = getattr(bar, "low", 0.0)

    volume_ratio = volume_quote / vol_sma if vol_sma > 0 else 1.0
    close_to_ema20 = (close / ema20 - 1.0) if ema20 > 0 else 0.0
    close_to_ema50 = (close / ema50 - 1.0) if ema50 > 0 else 0.0
    close_to_don_high = (close / don_high - 1.0) if don_high > 0 else 0.0
    close_to_don_low = (close / don_low - 1.0) if don_low > 0 else 0.0
    bb_width = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0.0
    bb_position = (close - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
    candle_body_pct = abs(close - bar_open) / close if close > 0 else 0.0
    candle_range_pct = (high - low) / close if close > 0 else 0.0
    upper_shadow_pct = (high - max(bar_open, close)) / close if close > 0 else 0.0
    lower_shadow_pct = (min(bar_open, close) - low) / close if close > 0 else 0.0

    return {
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "atr": atr,
        "atr_pct": atr_pct,
        "rsi": rsi,
        "bb_mid": bb_mid,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "vol_sma": vol_sma,
        "donchian_high": don_high,
        "donchian_low": don_low,
        "trend_strength": trend_strength,
        "volume_ratio": volume_ratio,
        "close_to_ema20": close_to_ema20,
        "close_to_ema50": close_to_ema50,
        "close_to_donchian_high": close_to_don_high,
        "close_to_donchian_low": close_to_don_low,
        "bb_position": bb_position,
        "candle_body_pct": candle_body_pct,
        "candle_range_pct": candle_range_pct,
        "upper_shadow_pct": upper_shadow_pct,
        "lower_shadow_pct": lower_shadow_pct,
    }


def prepare_dataset(
    bars: list[Any],
    forward_bars: int = 96,
    profit_threshold_pct: float = 0.005,
) -> tuple[np.ndarray, np.ndarray]:
    """Prepare feature matrix X and label vector y from bars.

    Labels:
        1 = price goes up by profit_threshold_pct within forward_bars
        0 = otherwise
    """
    features_list = []
    labels = []

    for i in range(len(bars) - forward_bars):
        bar = bars[i]
        feat = extract_features(bar)
        features_list.append([feat[col] for col in FEATURE_COLUMNS])

        # Label: did price go up by threshold?
        entry_price = bar.close
        future_bars = bars[i + 1:i + 1 + forward_bars]
        max_price = max(b.close for b in future_bars) if future_bars else entry_price
        max_return = (max_price / entry_price - 1.0) if entry_price > 0 else 0.0
        labels.append(1 if max_return >= profit_threshold_pct else 0)

    X = np.array(features_list, dtype=np.float64)
    y = np.array(labels, dtype=np.int32)
    return X, y


def train_model(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_estimators: int = 100,
    max_depth: int = 6,
    learning_rate: float = 0.1,
) -> Any:
    """Train XGBoost classifier."""
    try:
        from xgboost import XGBClassifier
        model = XGBClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            use_label_encoder=False,
            eval_metric="logloss",
            verbosity=0,
        )
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
        )

    model.fit(X_train, y_train)
    return model


def evaluate_window(
    market: dict[str, list[Any]],
    config: MLSignalConfig,
    end_ts: int,
) -> MLSignalResult | None:
    """Train on past data, test on a window."""
    MS_PER_DAY = 24 * 3600 * 1000
    train_start = end_ts - (config.train_days + config.test_days) * MS_PER_DAY
    train_end = end_ts - config.test_days * MS_PER_DAY
    test_start = train_end
    test_end = end_ts

    # Collect all bars across symbols
    train_bars = []
    test_bars = []
    for symbol, bars in market.items():
        sym_train = [b for b in bars if train_start <= b.ts < train_end]
        sym_test = [b for b in bars if test_start <= b.ts < test_end]
        train_bars.extend(sym_train)
        test_bars.extend(sym_test)

    if len(train_bars) < config.min_training_samples or len(test_bars) < 100:
        return None

    X_train, y_train = prepare_dataset(train_bars, config.forward_bars, config.profit_threshold_pct)
    X_test, y_test = prepare_dataset(test_bars, config.forward_bars, config.profit_threshold_pct)

    if len(X_train) < 100 or len(X_test) < 50:
        return None

    model = train_model(X_train, y_train, config.n_estimators, config.max_depth, config.learning_rate)
    y_pred_prob = model.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_prob >= config.min_score).astype(int)

    # Calculate metrics
    predictions = int(y_pred.sum())
    if predictions == 0:
        return MLSignalResult(
            window_end=str(end_ts),
            train_samples=len(X_train),
            test_samples=len(X_test),
        )

    correct = int(((y_pred == 1) & (y_test == 1)).sum())
    accuracy = correct / predictions if predictions > 0 else 0.0

    # Calculate simulated PnL
    total_pnl = 0.0
    trades = 0
    profitable = 0
    for i in range(len(y_pred)):
        if y_pred[i] == 1:
            trades += 1
            if y_test[i] == 1:
                total_pnl += config.profit_threshold_pct
                profitable += 1
            else:
                # Small loss for false positives
                total_pnl -= config.profit_threshold_pct * 0.5

    return MLSignalResult(
        train_samples=len(X_train),
        test_samples=len(X_test),
        predictions=predictions,
        correct=correct,
        accuracy=accuracy,
        total_pnl_pct=round(total_pnl * 100, 4),
        trades=trades,
        profitable_trades=profitable,
        win_rate=round(profitable / trades, 4) if trades > 0 else 0.0,
    )


def run_ml_evaluation(
    market: dict[str, list[Any]],
    config: MLSignalConfig,
) -> dict[str, Any]:
    """Run sliding window ML evaluation."""
    from backtester import _common_timeline

    timeline = _common_timeline(market, min_count_fraction=0.50)
    if not timeline:
        return {"error": "no timeline"}

    end_ts = timeline[-1]
    MS_PER_DAY = 24 * 3600 * 1000
    step_ms = config.step_days * MS_PER_DAY

    results = []
    current_end = end_ts
    min_start = timeline[0] + (config.train_days + config.test_days) * MS_PER_DAY

    while current_end >= min_start:
        result = evaluate_window(market, config, current_end)
        if result:
            results.append(result)
        current_end -= step_ms

    if not results:
        return {"error": "no valid windows"}

    # Aggregate
    total_trades = sum(r.trades for r in results)
    total_profitable = sum(r.profitable_trades for r in results)
    total_pnl = sum(r.total_pnl_pct for r in results)
    avg_win_rate = total_profitable / total_trades if total_trades > 0 else 0.0

    return {
        "windows": len(results),
        "total_trades": total_trades,
        "total_profitable": total_profitable,
        "avg_win_rate": round(avg_win_rate, 4),
        "total_pnl_pct": round(total_pnl, 4),
        "results": [
            {
                "train_samples": r.train_samples,
                "test_samples": r.test_samples,
                "predictions": r.predictions,
                "trades": r.trades,
                "win_rate": r.win_rate,
                "pnl_pct": r.total_pnl_pct,
            }
            for r in results
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ML signal evaluation.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--out", type=Path, default=Path("reports/ml_signal_eval.json"))
    parser.add_argument("--train-days", type=int, default=180)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--step-days", type=int, default=30)
    parser.add_argument("--forward-bars", type=int, default=96)
    parser.add_argument("--profit-threshold", type=float, default=0.005)
    parser.add_argument("--min-score", type=float, default=0.6)
    parser.add_argument("--timeframe", type=int, default=15)
    args = parser.parse_args(argv)

    print("Loading market data...", flush=True)
    from market import load_market
    market = load_market(args.data, args.timeframe)
    if not market:
        print("ERROR: No market data", flush=True)
        return 1

    config = MLSignalConfig(
        train_days=args.train_days,
        test_days=args.test_days,
        step_days=args.step_days,
        forward_bars=args.forward_bars,
        profit_threshold_pct=args.profit_threshold,
        min_score=args.min_score,
    )

    print(f"Running ML evaluation (train={config.train_days}d, test={config.test_days}d, forward={config.forward_bars}bars)...", flush=True)
    result = run_ml_evaluation(market, config)

    if "error" in result:
        print(f"ERROR: {result['error']}", flush=True)
        return 1

    print(f"\n{'='*60}", flush=True)
    print(f"ML SIGNAL EVALUATION", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Windows tested: {result['windows']}", flush=True)
    print(f"Total trades: {result['total_trades']}", flush=True)
    print(f"Win rate: {result['avg_win_rate']:.2%}", flush=True)
    print(f"Total PnL: {result['total_pnl_pct']:+.2f}%", flush=True)

    print(f"\nPer-window results:", flush=True)
    for i, r in enumerate(result['results']):
        print(f"  Window {i+1}: trades={r['trades']} win={r['win_rate']:.0%} pnl={r['pnl_pct']:+.2f}%", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {args.out}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

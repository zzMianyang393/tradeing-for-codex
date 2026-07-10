"""L3 — Candidate Filter (ML + Rule-based).

Trains on MFE/MAE-labeled candidates to predict which candidates are worth trading.
Applied to the full candidate pool during backtest, not just the final selected trades.

Two modes:
  1. Rule-based filter: hand-crafted rules from MFE analysis (no ML needed)
  2. ML filter: gradient boosting on candidate features

The rule-based filter is the baseline; ML adds non-linear pattern detection.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from candidate_pool import Candidate


# ---------------------------------------------------------------------------
# Feature extraction for ML
# ---------------------------------------------------------------------------

FEATURE_COLUMNS = [
    "proximity_score",
    "direction",
    "close_to_ema20",
    "close_to_ema50",
    "close_to_ema200",
    "ema20_to_ema50",
    "ema50_to_ema200",
    "atr_pct",
    "rsi",
    "bb_position",
    "close_to_donchian_high",
    "close_to_donchian_low",
    "trend_strength",
    "vol_ratio",
    "candle_body_pct",
    "candle_range_pct",
    "move_1d",
    "funding_rate",
    "open_interest_change_pct",
    "trade_flow_imbalance",
    "depth_imbalance",
    # Categorical one-hots
    "regime_uptrend",
    "regime_downtrend",
    "regime_range",
    "regime_transition",
    "pattern_breakout",
    "pattern_pullback",
    "pattern_reclaim",
    "pattern_volume_surge",
    "pattern_ema_turn",
    "pattern_range_revert",
]


def extract_features(c: Candidate) -> dict[str, float]:
    """Extract numeric features from a candidate for ML training."""
    close = c.close if c.close > 0 else 1e-10
    atr_val = c.atr_pct * close if c.atr_pct > 0 else 1e-10

    return {
        "proximity_score": c.proximity_score,
        "direction": float(c.direction),
        "close_to_ema20": (close - c.ema20) / close if close else 0.0,
        "close_to_ema50": (close - c.ema50) / close if close else 0.0,
        "close_to_ema200": (close - c.ema200) / close if close else 0.0,
        "ema20_to_ema50": (c.ema20 - c.ema50) / close if close else 0.0,
        "ema50_to_ema200": (c.ema50 - c.ema200) / close if close else 0.0,
        "atr_pct": c.atr_pct,
        "rsi": c.rsi,
        "bb_position": (close - c.bb_lower) / (c.bb_upper - c.bb_lower) if (c.bb_upper - c.bb_lower) > 0 else 0.5,
        "close_to_donchian_high": (close - c.donchian_high) / close if close else 0.0,
        "close_to_donchian_low": (close - c.donchian_low) / close if close else 0.0,
        "trend_strength": c.trend_strength,
        "vol_ratio": c.vol_ratio,
        "candle_body_pct": c.candle_body_pct,
        "candle_range_pct": c.candle_range_pct,
        "move_1d": c.move_1d,
        "funding_rate": c.funding_rate,
        "open_interest_change_pct": c.open_interest_change_pct,
        "trade_flow_imbalance": c.trade_flow_imbalance,
        "depth_imbalance": c.depth_imbalance,
        # One-hot encoding
        "regime_uptrend": 1.0 if c.regime == "uptrend" else 0.0,
        "regime_downtrend": 1.0 if c.regime == "downtrend" else 0.0,
        "regime_range": 1.0 if c.regime == "range" else 0.0,
        "regime_transition": 1.0 if c.regime == "transition" else 0.0,
        "pattern_breakout": 1.0 if c.pattern_type == "breakout" else 0.0,
        "pattern_pullback": 1.0 if c.pattern_type == "pullback" else 0.0,
        "pattern_reclaim": 1.0 if c.pattern_type == "reclaim" else 0.0,
        "pattern_volume_surge": 1.0 if c.pattern_type == "volume_surge" else 0.0,
        "pattern_ema_turn": 1.0 if c.pattern_type == "ema_turn" else 0.0,
        "pattern_range_revert": 1.0 if c.pattern_type == "range_revert" else 0.0,
    }


def features_to_array(c: Candidate) -> list[float]:
    """Extract features as ordered list matching FEATURE_COLUMNS."""
    feats = extract_features(c)
    return [feats[col] for col in FEATURE_COLUMNS]


# ---------------------------------------------------------------------------
# Rule-based filter (baseline, no ML dependency)
# ---------------------------------------------------------------------------

@dataclass
class RuleFilterConfig:
    """Thresholds learned from MFE analysis."""
    min_proximity: float = 0.25
    min_vol_ratio: float = 0.8
    max_rsi_long: float = 72.0
    min_rsi_long: float = 25.0
    max_rsi_short: float = 75.0
    min_rsi_short: float = 28.0
    # EMA structure
    require_ema_aligned: bool = True
    # Pattern-specific
    min_breakout_proximity: float = 0.4
    min_pullback_proximity: float = 0.3
    min_reclaim_proximity: float = 0.35


def rule_filter(c: Candidate, config: RuleFilterConfig | None = None) -> tuple[bool, str]:
    """Rule-based filter. Returns (pass, reason)."""
    cfg = config or RuleFilterConfig()

    if c.proximity_score < cfg.min_proximity:
        return False, "low_proximity"

    if c.vol_ratio < cfg.min_vol_ratio:
        return False, "low_volume"

    # RSI bounds
    if c.direction == 1 and (c.rsi > cfg.max_rsi_long or c.rsi < cfg.min_rsi_long):
        return False, "rsi_out_of_range"
    if c.direction == -1 and (c.rsi > cfg.max_rsi_short or c.rsi < cfg.min_rsi_short):
        return False, "rsi_out_of_range"

    # EMA alignment for trend patterns
    if cfg.require_ema_aligned and c.pattern_type in ("breakout", "pullback", "reclaim"):
        if c.direction == 1 and c.ema20 < c.ema50:
            return False, "ema_not_aligned"
        if c.direction == -1 and c.ema20 > c.ema50:
            return False, "ema_not_aligned"

    # Pattern-specific proximity thresholds
    if c.pattern_type == "breakout" and c.proximity_score < cfg.min_breakout_proximity:
        return False, "breakout_too_weak"
    if c.pattern_type == "pullback" and c.proximity_score < cfg.min_pullback_proximity:
        return False, "pullback_too_weak"
    if c.pattern_type == "reclaim" and c.proximity_score < cfg.min_reclaim_proximity:
        return False, "reclaim_too_weak"

    return True, "pass"


# ---------------------------------------------------------------------------
# ML Filter (gradient boosting, zero-dep implementation)
# ---------------------------------------------------------------------------

class SimpleGradientBoosting:
    """Minimal gradient boosting classifier — no sklearn dependency.

    Uses decision stumps as weak learners with max_depth=1.
    """

    def __init__(self, n_estimators: int = 100, learning_rate: float = 0.1, max_depth: int = 1):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.trees: list[dict] = []
        self.base_pred: float = 0.5

    def _sigmoid(self, x: float) -> float:
        x = max(-20.0, min(20.0, x))
        return 1.0 / (1.0 + math.exp(-x))

    def _find_best_split(self, X: list[list[float]], residuals: list[float]) -> tuple[int, float, float, float]:
        """Find the best binary split on a single feature."""
        n = len(X)
        if n == 0:
            return 0, 0.0, 0.0, 0.0

        best_gain = -1e18
        best_feat = 0
        best_thresh = 0.0
        best_left_val = 0.0
        best_right_val = 0.0

        n_features = len(X[0]) if X else 0

        for feat_idx in range(n_features):
            values = [(X[i][feat_idx], residuals[i]) for i in range(n)]
            values.sort(key=lambda x: x[0])

            left_sum = 0.0
            left_count = 0
            right_sum = sum(r for _, r in values)
            right_count = n

            for i in range(n - 1):
                val, res = values[i]
                left_sum += res
                left_count += 1
                right_sum -= res
                right_count -= 1

                if left_count < 5 or right_count < 5:
                    continue

                if values[i + 1][0] == val:
                    continue

                left_mean = left_sum / left_count
                right_mean = right_sum / right_count
                gain = left_mean * left_mean * left_count + right_mean * right_mean * right_count

                if gain > best_gain:
                    best_gain = gain
                    best_feat = feat_idx
                    thresh = (val + values[i + 1][0]) / 2.0
                    best_thresh = thresh
                    best_left_val = left_mean
                    best_right_val = right_mean

        return best_feat, best_thresh, best_left_val, best_right_val

    def fit(self, X: list[list[float]], y: list[int]) -> None:
        n = len(X)
        if n == 0:
            return

        # Initialize with log-odds of positive rate
        pos_rate = sum(y) / n
        pos_rate = max(0.01, min(0.99, pos_rate))
        self.base_pred = math.log(pos_rate / (1.0 - pos_rate))

        # Current predictions in log-odds space
        preds = [self.base_pred] * n

        for _ in range(self.n_estimators):
            # Compute residuals (gradient of log-loss)
            probs = [self._sigmoid(p) for p in preds]
            residuals = [y[i] - probs[i] for i in range(n)]

            feat_idx, thresh, left_val, right_val = self._find_best_split(X, residuals)

            # Clip leaf values to prevent overshooting
            clip = 2.0
            left_val = max(-clip, min(clip, left_val))
            right_val = max(-clip, min(clip, right_val))

            self.trees.append({
                "feat": feat_idx,
                "thresh": thresh,
                "left": left_val * self.learning_rate,
                "right": right_val * self.learning_rate,
            })

            # Update predictions
            for i in range(n):
                if X[i][feat_idx] <= thresh:
                    preds[i] += left_val * self.learning_rate
                else:
                    preds[i] += right_val * self.learning_rate

    def predict_proba(self, X: list[list[float]]) -> list[float]:
        """Return probability of positive class for each sample."""
        results = []
        for x in X:
            pred = self.base_pred
            for tree in self.trees:
                if x[tree["feat"]] <= tree["thresh"]:
                    pred += tree["left"]
                else:
                    pred += tree["right"]
            results.append(self._sigmoid(pred))
        return results

    def predict(self, X: list[list[float]], threshold: float = 0.5) -> list[int]:
        probs = self.predict_proba(X)
        return [1 if p >= threshold else 0 for p in probs]

    def score(self, X: list[list[float]], y: list[int]) -> float:
        preds = self.predict(X)
        correct = sum(1 for a, b in zip(preds, y) if a == b)
        return correct / len(y) if y else 0.0

    def save(self, path) -> None:
        """Save model to JSON file."""
        import json
        from pathlib import Path
        data = {
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "max_depth": self.max_depth,
            "base_pred": self.base_pred,
            "trees": self.trees,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path) -> "SimpleGradientBoosting":
        """Load model from JSON file."""
        import json
        with open(path) as f:
            data = json.load(f)
        model = cls(
            n_estimators=data["n_estimators"],
            learning_rate=data["learning_rate"],
            max_depth=data.get("max_depth", 1),
        )
        model.base_pred = data["base_pred"]
        model.trees = data["trees"]
        return model


@dataclass
class MLFilterConfig:
    n_estimators: int = 80
    learning_rate: float = 0.08
    min_training_samples: int = 50
    max_training_samples: int = 5000
    min_probability: float = 0.45
    retrain_every_bars: int = 96 * 7  # retrain weekly


class CandidateMLFilter:
    """ML-based candidate filter using gradient boosting."""

    def __init__(self, config: MLFilterConfig | None = None):
        self.config = config or MLFilterConfig()
        self.model: SimpleGradientBoosting | None = None
        self.trained = False
        self.training_stats: dict = {}

    def train(self, candidates: list[Candidate]) -> dict:
        """Train on labeled candidates. Returns training stats."""
        labeled = [c for c in candidates if c.label >= 0]
        if len(labeled) < self.config.min_training_samples:
            return {"trained": False, "reason": f"only {len(labeled)} labeled samples"}

        # The stump learner sorts every feature for every tree.  Cap training
        # deterministically while preserving the full time span of the data.
        if len(labeled) > self.config.max_training_samples:
            max_samples = self.config.max_training_samples
            sample_indices = [
                round(i * (len(labeled) - 1) / (max_samples - 1))
                for i in range(max_samples)
            ]
            labeled = [labeled[i] for i in sample_indices]

        X = [features_to_array(c) for c in labeled]
        y = [c.label for c in labeled]

        self.model = SimpleGradientBoosting(
            n_estimators=self.config.n_estimators,
            learning_rate=self.config.learning_rate,
        )
        self.model.fit(X, y)
        self.trained = True

        # Evaluate on training set
        train_acc = self.model.score(X, y)
        probs = self.model.predict_proba(X)

        # Find optimal threshold using simple grid
        best_f1 = 0.0
        best_thresh = 0.5
        for thresh_100 in range(30, 70):
            t = thresh_100 / 100.0
            tp = sum(1 for i in range(len(y)) if probs[i] >= t and y[i] == 1)
            fp = sum(1 for i in range(len(y)) if probs[i] >= t and y[i] == 0)
            fn = sum(1 for i in range(len(y)) if probs[i] < t and y[i] == 1)
            precision = tp / max(tp + fp, 1)
            recall = tp / max(tp + fn, 1)
            f1 = 2 * precision * recall / max(precision + recall, 1e-10)
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = t

        self.config.min_probability = best_thresh

        self.training_stats = {
            "trained": True,
            "n_samples": len(labeled),
            "n_original_samples": len(candidates),
            "n_positive": sum(y),
            "train_accuracy": round(train_acc, 4),
            "best_threshold": round(best_thresh, 2),
            "best_f1": round(best_f1, 4),
            "n_estimators": self.config.n_estimators,
        }
        return self.training_stats

    def should_trade(self, c: Candidate) -> tuple[bool, float]:
        """Returns (should_trade, probability)."""
        if not self.trained or self.model is None:
            return True, 0.5  # no filter → pass everything

        x = [features_to_array(c)]
        prob = self.model.predict_proba(x)[0]
        return prob >= self.config.min_probability, prob

    def filter_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        """Return only candidates that pass the ML filter."""
        return [c for c in candidates if self.should_trade(c)[0]]

    def save(self, path: str) -> None:
        """Save ML filter to file."""
        if self.model is not None:
            self.model.save(path)

    def load(self, path: str) -> None:
        """Load ML filter from file."""
        self.model = SimpleGradientBoosting.load(path)
        self.trained = True
# Combined filter: rules + ML
# ---------------------------------------------------------------------------

class CandidateFilter:
    """Combined rule-based + ML candidate filter."""

    def __init__(
        self,
        rule_config: RuleFilterConfig | None = None,
        ml_config: MLFilterConfig | None = None,
        use_rules: bool = True,
        use_ml: bool = True,
    ):
        self.rule_config = rule_config or RuleFilterConfig()
        self.ml_config = ml_config or MLFilterConfig()
        self.use_rules = use_rules
        self.use_ml = use_ml
        self.ml_filter = CandidateMLFilter(self.ml_config)

    def train_ml(self, candidates: list[Candidate]) -> dict:
        """Train the ML component on labeled candidates."""
        if not self.use_ml:
            return {"trained": False, "reason": "ml_disabled"}
        return self.ml_filter.train(candidates)

    def should_trade(self, c: Candidate) -> tuple[bool, str, float]:
        """Combined filter decision. Returns (pass, reason, ml_prob)."""
        # Stage 1: Rule filter
        if self.use_rules:
            rule_pass, rule_reason = rule_filter(c, self.rule_config)
            if not rule_pass:
                return False, f"rule:{rule_reason}", 0.0

        # Stage 2: ML filter
        ml_prob = 0.5
        if self.use_ml and self.ml_filter.trained:
            ml_pass, ml_prob = self.ml_filter.should_trade(c)
            if not ml_pass:
                return False, f"ml:prob={ml_prob:.2f}", ml_prob

        return True, "pass", ml_prob

    def filter_candidates(self, candidates: list[Candidate]) -> list[Candidate]:
        """Return only candidates that pass both filters."""
        return [c for c in candidates if self.should_trade(c)[0]]

    def save_ml(self, path: str) -> None:
        """Save the ML model to file."""
        self.ml_filter.save(path)

    def load_ml(self, path: str) -> None:
        """Load a pre-trained ML model from file."""
        self.ml_filter.load(path)

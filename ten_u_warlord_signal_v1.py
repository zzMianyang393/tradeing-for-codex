from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from market import FeatureBar
from market_state_schema import MarketState, ensure_utc

STRATEGY_ID = "ten_u_trend_breakout_v1"
BREAKOUT_WINDOW = 32
ATR_PERIOD = 14
STOP_ATR_MULTIPLE = Decimal("1.5")
TARGET_ATR_MULTIPLE = Decimal("4.5")
PLANNED_R_MULTIPLE = Decimal("3.0")
MIN_CONFIDENCE = 0.70
MIN_HISTORY_BARS = 47


def get_signal_contract_fingerprint() -> str:
    payload = {
        "strategy_id": STRATEGY_ID,
        "market_state_version": "v1.1.0",
        "breakout_window": BREAKOUT_WINDOW,
        "atr_period": ATR_PERIOD,
        "stop_atr_multiple": str(STOP_ATR_MULTIPLE),
        "target_atr_multiple": str(TARGET_ATR_MULTIPLE),
        "planned_r_multiple": str(PLANNED_R_MULTIPLE),
        "minimum_confidence": MIN_CONFIDENCE,
        "minimum_history_bars": MIN_HISTORY_BARS,
        "execution": "next_15m_open",
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()

# ---------------------------------------------------------------------------
# Signal Proposal Data Model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SignalProposal:
    strategy_id: str
    symbol: str
    observed_at: str
    executable_at: str
    direction: str  # long, short
    reference_close: Decimal
    stop_price: Decimal
    target_price: Decimal
    atr: Decimal
    planned_r_multiple: Decimal
    market_state_snapshot_id: str
    reason_codes: tuple[str, ...]
    signal_fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.direction not in ("long", "short"):
            raise ValueError("direction must be long or short")
        if not self.symbol or not self.market_state_snapshot_id:
            raise ValueError("symbol and market_state_snapshot_id are required")
        observed = ensure_utc(self.observed_at)
        executable = ensure_utc(self.executable_at)
        if executable != observed:
            raise ValueError("next 15m open must equal the trigger bar close boundary")
        if self.atr <= 0 or self.planned_r_multiple != Decimal("3.0"):
            raise ValueError("invalid ATR or planned R multiple")
        if min(self.reference_close, self.stop_price, self.target_price) <= 0:
            raise ValueError("proposal prices must be positive")
        if self.direction == "long" and not self.stop_price < self.reference_close < self.target_price:
            raise ValueError("invalid long stop/target ordering")
        if self.direction == "short" and not self.target_price < self.reference_close < self.stop_price:
            raise ValueError("invalid short stop/target ordering")
        fp = self.compute_fingerprint()
        if self.signal_fingerprint and self.signal_fingerprint != fp:
            raise ValueError("signal_fingerprint does not match proposal content")
        object.__setattr__(self, "signal_fingerprint", fp)

    def compute_fingerprint(self) -> str:
        """Deterministic fingerprint of the proposal."""
        payload = {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "observed_at": self.observed_at,
            "executable_at": self.executable_at,
            "direction": self.direction,
            "reference_close": str(self.reference_close),
            "stop_price": str(self.stop_price),
            "target_price": str(self.target_price),
            "atr": str(self.atr),
            "planned_r_multiple": str(self.planned_r_multiple),
            "market_state_snapshot_id": self.market_state_snapshot_id,
            "reason_codes": list(self.reason_codes),
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "observed_at": self.observed_at,
            "executable_at": self.executable_at,
            "direction": self.direction,
            "reference_close": str(self.reference_close),
            "stop_price": str(self.stop_price),
            "target_price": str(self.target_price),
            "atr": str(self.atr),
            "planned_r_multiple": str(self.planned_r_multiple),
            "market_state_snapshot_id": self.market_state_snapshot_id,
            "reason_codes": list(self.reason_codes),
            "signal_fingerprint": self.signal_fingerprint,
        }


# ---------------------------------------------------------------------------
# Signal Calculation Logic
# ---------------------------------------------------------------------------
def _atr14(bars: list[FeatureBar]) -> Decimal:
    """Compute Wilder-style 14-period true-range mean from raw completed bars."""
    if len(bars) < 15:
        return Decimal("0")
    true_ranges: list[Decimal] = []
    for i in range(len(bars) - 14, len(bars)):
        bar = bars[i]
        previous_close = Decimal(str(bars[i - 1].close))
        high = Decimal(str(bar.high))
        low = Decimal(str(bar.low))
        true_ranges.append(max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        ))
    return (sum(true_ranges, Decimal("0")) / Decimal("14")).quantize(
        Decimal("0.00000001")
    )


def check_signal(
    symbol: str,
    market_state: MarketState,
    completed_15m_bars: list[FeatureBar],
    market_state_snapshot_id: str,
) -> Optional[SignalProposal]:
    """Evaluates 15m breakout signal under the '10U Warlord' contract constraints."""
    # 1. Applicable Regime Checks
    if market_state.version != "v1.1.0":
        return None
    if market_state.confidence < MIN_CONFIDENCE:
        return None
    if market_state.h4.tradable_regime != "trend_following":
        return None

    w_dir = market_state.weekly.direction
    d_dir = market_state.daily.direction
    h4_dir = market_state.h4.direction

    # weekly, daily, and H4 directions must be identical
    if not (w_dir == d_dir == h4_dir):
        return None

    # Only trend direction allowed
    if w_dir not in ("uptrend", "downtrend"):
        return None

    # No trade if any high severity conflict exists
    if any(c.severity == "high" for c in market_state.conflicts):
        return None

    # 2. Strict lookahead prevention: filter bars completed at or before available_at
    available_at_ms = int(market_state.available_at.timestamp() * 1000)
    if any(b.ts >= completed_15m_bars[i + 1].ts for i, b in enumerate(completed_15m_bars[:-1])):
        raise ValueError("15m bars must be strictly time ordered")
    bars = [b for b in completed_15m_bars if b.ts + 900000 <= available_at_ms]

    # Required: at least 32 lookback + 1 trigger + 14 ATR = 47 bars
    if len(bars) < MIN_HISTORY_BARS:
        return None

    trigger_bar = bars[-1]
    if trigger_bar.ts + 900000 != available_at_ms:
        return None
    lookback_bars = bars[-33:-1]  # The 32 completed bars preceding the trigger bar

    # Compute ATR14 from completed raw bars; do not trust a precomputed field
    # whose period or timestamp provenance is unknown.
    atr = _atr14(bars)
    if atr <= 0:
        return None

    ref_close = Decimal(str(trigger_bar.close))
    direction = ""
    reason_codes: list[str] = []

    # 3. Breakout detection
    if w_dir == "uptrend":
        highest_high = Decimal(str(max(b.high for b in lookback_bars)))
        if ref_close > highest_high:
            direction = "long"
            reason_codes.append("breakout_high")
    elif w_dir == "downtrend":
        lowest_low = Decimal(str(min(b.low for b in lookback_bars)))
        if ref_close < lowest_low:
            direction = "short"
            reason_codes.append("breakout_low")

    if not direction:
        return None

    # 4. Stop and target calculations
    # Stop = 1.5 ATR. Target = 4.5 ATR. (Planned R = 3R)
    atr_factor_stop = STOP_ATR_MULTIPLE
    atr_factor_target = TARGET_ATR_MULTIPLE

    if direction == "long":
        stop_price = ref_close - atr_factor_stop * atr
        target_price = ref_close + atr_factor_target * atr
    else:
        stop_price = ref_close + atr_factor_stop * atr
        target_price = ref_close - atr_factor_target * atr

    if min(stop_price, target_price) <= 0:
        return None

    # Quantize to 4 decimal places
    stop_price = stop_price.quantize(Decimal("0.0001"))
    target_price = target_price.quantize(Decimal("0.0001"))

    # Timestamps
    trigger_close_ts = trigger_bar.ts + 900000
    observed_at_dt = datetime.fromtimestamp(trigger_close_ts / 1000, tz=timezone.utc)
    observed_at = observed_at_dt.isoformat().replace("+00:00", "Z")
    
    # Next bar opening time is exactly trigger close time
    executable_at = observed_at

    return SignalProposal(
        strategy_id=STRATEGY_ID,
        symbol=symbol,
        observed_at=observed_at,
        executable_at=executable_at,
        direction=direction,
        reference_close=ref_close,
        stop_price=stop_price,
        target_price=target_price,
        atr=atr,
        planned_r_multiple=PLANNED_R_MULTIPLE,
        market_state_snapshot_id=market_state_snapshot_id,
        reason_codes=tuple(reason_codes),
    )

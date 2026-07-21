# Market State Contract v1 - Unified Multi-Timeframe State Model

Amendment v1.1: weekly direction requires at least 50 completed Monday-UTC weekly bars and uses EMA20/EMA50. Daily and 4h states require 200 completed bars because their direction rules use EMA200. The frozen default configuration fingerprint is `6b75a055e4366986b03b8b575ee8e450eb65dfc60ae4c920aafcf6d6ed31a174`.

This document defines the interface contract, schemas, and behavior for the unified multi-timeframe market state model.

---

## 1. Schema Specifications & Allowed Values (Central Enums)

All states, configs, snapshots, and transitions are modeled using typed Python dataclasses, facilitating serialization/deserialization to JSON.
Every string attribute in the state is validated against allowed values during object instantiation (`__post_init__`) or JSON deserialization. An illegal state string results in a `ValueError`.

### Central Enums
* **Directions (`VALID_DIRECTIONS`)**: `uptrend | downtrend | range | transition | unknown`
* **Trend Stages (`VALID_TREND_STAGES`)**: `early | mature | exhaustion | unknown`
* **Volatility States (`VALID_VOLATILITY_STATES`)**: `compressed | normal | expanding | extreme | unknown`
* **Risk Cycles (`VALID_RISK_CYCLES`)**: `normal | high_risk | low_risk | unknown`
* **Structures (`VALID_STRUCTURES`)**: `breakout | breakdown | pullback | range | unknown`
* **Tradable Regimes (`VALID_TRADABLE_REGIMES`)**: `trend_following | mean_reversion | no_trade | unknown`
* **Breakouts or Pullbacks (`VALID_BREAKOUT_OR_PULLBACKS`)**: `breakout | pullback | range | none | unknown`
* **Entry Contexts (`VALID_ENTRY_CONTEXTS`)**: `oversold | overbought | breakout_test | consolidation | unknown`
* **Momentums (`VALID_MOMENTUMS`)**: `strong_bullish | weak_bullish | flat | weak_bearish | strong_bearish | unknown`
* **Local Structures (`VALID_LOCAL_STRUCTURES`)**: `higher_high | lower_low | range_bound | unknown`
* **Liquidity States (`VALID_LIQUIDITY_STATES`)**: `normal | thin | unknown`
* **Alt Relative Strengths (`VALID_ALT_RELATIVE_STRENGTHS`)**: `broad | BTC-led | alt-led | fragmented | unknown`

---

### Timeframe States
Each timeframe possesses its own structure representing the indicators relevant to its scale:

#### Weekly State (`WeeklyState`)
- **`direction`**: `VALID_DIRECTIONS`
- **`trend_strength`**: `float | "unknown"`
- **`volatility_state`**: `VALID_VOLATILITY_STATES`
- **`risk_cycle`**: `VALID_RISK_CYCLES`

#### Daily State (`DailyState`)
- **`direction`**: `VALID_DIRECTIONS`
- **`trend_stage`**: `VALID_TREND_STAGES`
- **`volatility_state`**: `VALID_VOLATILITY_STATES`
- **`structure`**: `VALID_STRUCTURES`

#### 4-Hour State (`H4State`)
- **`direction`**: `VALID_DIRECTIONS` (Unified direction field)
- **`tradable_regime`**: `VALID_TRADABLE_REGIMES`
- **`trend_stage`**: `VALID_TREND_STAGES`
- **`breakout_or_pullback`**: `VALID_BREAKOUT_OR_PULLBACKS`
- **`volatility_state`**: `VALID_VOLATILITY_STATES`

#### 15-Minute State (`M15State`)
- **`entry_context`**: `VALID_ENTRY_CONTEXTS`
- **`momentum`**: `VALID_MOMENTUMS`
- **`local_structure`**: `VALID_LOCAL_STRUCTURES`
- **`liquidity_state`**: `VALID_LIQUIDITY_STATES`

### Market Regime State (`MarketRegimeState`)
State info computed at the market level (cross-sectional context):
- **`btc_state`**: `VALID_DIRECTIONS`
- **`eth_state`**: `VALID_DIRECTIONS`
- **`market_breadth`**: `float | "unknown"`
- **`alt_relative_strength`**: `VALID_ALT_RELATIVE_STRENGTHS`
- **`cross_section_dispersion`**: `float | "unknown"`

---

## 2. Mandatory Time and Confidence Relationships

All states enforce the following temporal constraints during instantiation. Violating these constraints raises a `ValueError`:
1. **Source close before available**: `source_bar_close_time <= available_at`
2. **Start before available**: `state_started_at <= available_at`
3. **Snapshot alignment**: `snapshot.timestamp == state.available_at`
4. **Transition ordering**: `transition_time >= current_state.available_at`
5. **Confidence range**: `0.0 <= confidence <= 1.0`

---

## 3. Strict UTC Time Semantics & K-Line Semantics

1. **Explicit UTC**: Naive datetimes are strictly rejected. Datetimes must have `tzinfo=timezone.utc`. Date strings must end with `Z` or an explicit offset (e.g. `+00:00`). Implicitly interpreting offsetless strings as UTC is forbidden.
2. **K-Line Timestamp Semantics**: `bar.ts` represents the **start time** (opening timestamp) of the K-line bar. A K-line is only completed (closed) at:
   $$\text{close\_time} = \text{bar.ts} + \text{duration\_ms}$$
3. **Lookahead Protection**: Calculations at `available_at` only use bars whose close time is before or at `available_at`:
   $$\text{completed\_bars} = \{ \text{bar} \mid \text{bar.ts} + \text{duration\_ms} \le \text{available\_at} \}$$

---

## 4. Fingerprint & Deterministic Identification

1. **Config Fingerprint**: `MarketStateConfig` provides a deterministic `fingerprint()` method that returns the full 64-character SHA-256 hash of its serialized dictionary. Version is unified to `"v1.0.0"`.
2. **Snapshot ID**: `snapshot_id` is deterministically generated using the `generate_snapshot_id` function, which binds `symbol`, `available_at`, `config_fingerprint`, and the state's categorical indicators via SHA-256.
3. **Stable Public Interfaces**: The schema exposes `get_market_state_schema_version()` and `get_market_state_config_fingerprint()` to bind the market state configuration with the `ResearchProtocol`.

---

## 5. Implementation Status

> [!NOTE]
> `market_state.py` is currently a **prototype engine** designed for schema validation, testing, and contract verification. Implementing strategy backtests, registered routing,同类行情OOS, and dynamic portfolio allocations are subsequent phases and are **not** claimed to be completed in this version.

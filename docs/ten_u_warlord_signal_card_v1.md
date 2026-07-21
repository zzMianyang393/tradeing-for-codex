# "10U Warlord" Trend Breakout Signal Card (v1)

Final research status: `rejected_at_formation`. The frozen Formation result was -41.1220% with profit factor 0.8725 across 123 trades. Validation and OOS remain sealed and must not be evaluated for this candidate.

This strategy card specifies the trading rules, parameters, and walk-forward disciplines for the `ten_u_trend_breakout_v1` signal prototype.

---

## 1. Strategy Overview

- **Strategy ID**: `ten_u_trend_breakout_v1`
- **Asset Scope**: Bounded by the fixed symbol universe of the `ResearchProtocol`.
- **Trading Concept**: High-odds trend breakout. Enters when the short-term cycle breaks out in the direction of the aligned macro trend (Weekly/Daily/H4).

---

## 2. Frozen Signal Parameters (v1)

The following parameters are frozen and **cannot** be modified or optimized:

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Breakout Window** | `32` bars | Lookback window for high/low breakout (15m scale) |
| **ATR Period** | `14` bars | Timeframe window for average true range calculation (15m scale) |
| **Stop Distance** | `1.5 * ATR` | Distance below entry (for long) or above entry (for short) |
| **Target Distance** | `4.5 * ATR` | Distance above entry (for long) or below entry (for short) |
| **Planned R-Multiple** | `3.0` | Fixed reward-to-risk ratio ($4.5 / 1.5 = 3.0$) |

---

## 3. Core Logic Rules

### A. Applicable Regime Verification
A signal proposal is only generated when:
1. **Schema Check**: `MarketState.version == "v1.0.0"`.
2. **Confidence Check**: `MarketState.confidence >= 0.70`.
3. **Regime Alignment**: H4 `tradable_regime` is `"trend_following"`.
4. **Macro Trend Alignment**: Weekly, Daily, and H4 direction fields are identical and are either `"uptrend"` or `"downtrend"`.
   - Uptrend: Only long signals allowed.
   - Downtrend: Only short signals allowed.
   - Range, transition, unknown, or H4 no-trade: Do not trade.
5. **No High Conflicts**: There are no conflicts in `MarketState.conflicts` with `severity == "high"`.

### B. Entry Trigger (15m Scale)
Only completed K-lines are used (where K-line close time $\le$ evaluation time).
- **Long**:
  $$\text{close}_t > \max\left(\text{high}_{t-32}, \dots, \text{high}_{t-1}\right)$$
- **Short**:
  $$\text{close}_t < \min\left(\text{low}_{t-32}, \dots, \text{low}_{t-1}\right)$$
  - *Note*: The trigger K-line $t$ itself is excluded from the lookback window.
  - *Execution*: Open order is placed at the start of K-line $t+1$ (the `executable_at` timestamp).

### C. Price Calculations
- **Long**:
  - $\text{stop\_price} = \text{close}_t - 1.5 \times \text{ATR}_t$
  - $\text{target\_price} = \text{close}_t + 4.5 \times \text{ATR}_t$
- **Short**:
  - $\text{stop\_price} = \text{close}_t + 1.5 \times \text{ATR}_t$
  - $\text{target\_price} = \text{close}_t - 4.5 \times \text{ATR}_t$
  - *Note*: Stop and target prices are fixed at entry. Trailing stop optimizations, additions, and cost-averaging are strictly prohibited.

---

## 4. Strict Walk-Forward Discipline

> [!IMPORTANT]
> - **Formation Candidate**: This signal is a candidate for the **Formation** phase evaluation. It has **not** been validated on OOS (Out-of-Sample) data.
> - **No Post-hoc Adjustments**: If the strategy fails to pass the Formation target benchmarks, it is **eliminated**. Tuning the window sizes or multipliers (e.g. changing 32 to 20, or 1.5 to 2.0) to "revive" the strategy is forbidden.
> - **Validation / OOS Lock**: Only if the strategy passes Formation benchmarks with these exact parameters is it allowed to be run on the Validation set. OOS results must remain completely unseen during the parameter freeze.
> - **No Live Execution**: This signal prototype is isolated from execution engines (`runner.py`, `executor.py`) and paper trading databases.

---

## 5. Risk Warnings

> [!WARNING]
> - Due to the high leverage (5x) and high risk ratio (15% per trade) defined in the sleeve contract, **this strategy has a high probability of entering permanent ruin (equity <= 2.0 USDT)** or peak drawdown halts (70%).
> - Users must expect that the entire 10 USDT principal can be completely lost.

# Deep validation: multi_day_momentum_short

**Date:** 2026-07-17  
**Command:** `python -m prod.cli validate-md-mom-short`  
**Report:** `reports/prod/research_md_mom_short_validation.json`  
**Rule:** frozen `prod_majors_md_mom_short_v1` · BTC/ETH · 10U · costs on  

## Split

| Slice | Bars (approx) | Definition |
|-------|---------------|------------|
| Formation | 60% of common timeline | earliest |
| Embargo | 96 bars (~1 day) | between formation and OOS |
| OOS | remainder | most recent |

## Results

| Slice | Trades | Return | PF | Max DD | Gate |
|-------|-------:|-------:|---:|-------:|------|
| Full sample | 254 | **+5.5%** | **1.04** | 15.9% | **PASS** |
| Formation | 143 | **-5.5%** | 0.93 | 15.9% | **FAIL** |
| OOS (dual) | 111 | **+11.6%** | **1.21** | 9.7% | **PASS** |
| BTC OOS only | 84 | -0.8% | 0.98 | 12.6% | FAIL |
| ETH OOS only | 87 | -9.5% | 0.84 | 23.6% | FAIL |
| Cap sense 10/100/500 | — | all ~+5.5% | 1.04 | 15.9% | **PASS** |

## Decision

**`conditional_watchlist`** — **`paper_prep_recommended: false`**

### Why not admit

1. **Formation fails** while OOS looks good → risk of **recent-regime luck** / unstable edge across history.  
2. **Neither symbol alone** is OOS-positive → dual book may be an artifact of **symbol selection order / shared capital path**, not robust single-name alpha.  
3. Edge is **small** (+5% full sample); not enough to override formation failure.

### Why not pure reject archive only

- Dual OOS is clean (+11.6%, PF 1.21, DD &lt;10%).  
- Sensitivity scales cleanly (not a 10U min-notional artifact).  
- Keep on **watchlist** for a *new* pre-registered structure (e.g. require both-symbol confirmation, or different sampling), **not** for parameter search on this shell.

## Explicit actions

| Action | Status |
|--------|--------|
| Admit to paper-prep | **No** |
| Grid search this shell | **No** |
| Demo/live | **No** (server-later anyway) |
| Archive + watchlist | **Yes** |

## Next research directions (if continuing)

1. Pre-register **dual-confirm short** (both BTC and ETH signal same day) — new family.  
2. Or pre-register **single-name** short with stricter HTF (accept lower trade count).  
3. Do not retune `multi_day_momentum_short` thresholds.  

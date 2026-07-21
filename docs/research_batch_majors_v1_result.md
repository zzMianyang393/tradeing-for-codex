# Majors research batch v1 result

**Date:** 2026-07-17  
**Command:** `python -m prod.cli research-batch-majors`  
**Report:** `reports/prod/research_batch_majors_v1.json`  
**Universe:** BTC/ETH · **Start equity:** 10U · costs included · no param search

## Ranking (full sample)

| Name | Trades | Return | PF | Max DD | Decision |
|------|-------:|-------:|---:|-------:|----------|
| rsi_trend_short | 6 | -0.7% | 0.88 | 4.9% | rejected_weak |
| rsi_trend_long | 19 | -1.8% | 0.89 | 6.8% | rejected_weak |
| htf_pullback_long | 387 | -63.9% | 0.68 | 65.1% | rejected_weak |
| donchian_long_baseline | 367 | -67.3% | 0.72 | 70.2% | rejected_weak |
| vol_donchian_long | 450 | -68.1% | 0.72 | 70.3% | rejected_weak |
| donchian_short | 413 | -68.6% | 0.71 | 70.2% | rejected_weak |
| bb_mean_revert_long | 545 | -69.2% | 0.70 | 70.1% | rejected_weak |
| htf_pullback_short | 417 | -69.4% | 0.66 | 70.3% | rejected_weak |
| ema_cross_short | 761 | -69.6% | 0.82 | 70.2% | rejected_weak |
| ema_cross_long | 477 | -69.9% | 0.71 | 70.5% | rejected_weak |
| bb_mean_revert_short | 491 | -70.0% | 0.63 | 70.0% | rejected_weak |

**Interesting (promote path):** none  
**Watchlist weak:** none (strict gates)

## Takeaways

1. High-turnover channel / pullback / cross / BB families all collapse to ~−65%–−70% on 10U after costs (often hit DD halt).  
2. **RSI+trend** is least bad: near-flat, low trade count, low DD — still PF&lt;1 and not positive.  
3. Do **not** grid-search the collapsed shells.  
4. Next batch should emphasize **lower turnover / different cost structure** (e.g. multi-day hold, stricter HTF, event sparsity) rather than more 15m breakout variants.

## How to re-run

```bash
python -m prod.cli research-batch-majors
```

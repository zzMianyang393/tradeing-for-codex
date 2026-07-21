# Majors research batch v2 result (low turnover)

**Date:** 2026-07-17  
**Command:** `python -m prod.cli research-batch-majors-v2`  
**Report:** `reports/prod/research_batch_majors_v2.json`  
**Universe:** BTC/ETH · **10U** · costs on · no param search  

## Ranking

| Name | Trades | Return | PF | Max DD | Decision |
|------|-------:|-------:|---:|-------:|----------|
| **multi_day_momentum_short** | 254 | **+5.5%** | **1.04** | 15.9% | **interesting_not_admitted** |
| daily_breakout_short | 14 | -4.8% | 0.61 | 7.6% | rejected_weak |
| daily_breakout_long | 23 | -9.8% | 0.38 | 10.8% | rejected_weak |
| slow_ema_cross_long | 426 | -46.5% | 0.76 | 49.2% | rejected_weak |
| multi_day_momentum_long | 303 | -47.9% | 0.60 | 50.2% | rejected_weak |
| four_h_close_trend_long | 311 | -50.2% | 0.61 | 52.3% | rejected_weak |
| atr_squeeze_breakout_short | 413 | -53.8% | 0.59 | 54.9% | rejected_weak |
| four_h_close_trend_short | 220 | -58.5% | 0.45 | 58.5% | rejected_weak |
| atr_squeeze_breakout_long | 389 | -58.5% | 0.54 | 58.8% | rejected_weak |
| slow_ema_cross_short | 415 | -58.6% | 0.65 | 58.6% | rejected_weak |

## Interesting candidate (not admitted)

**`prod_majors_md_mom_short_v1`** / `multi_day_momentum_short`

- Daily sampling only; 5d downside momentum + falling ema50  
- Short only; multi-day hold  
- Full-sample 10U: **+5.5%**, PF **1.04**, DD **~16%**, 254 trades  

**Still NOT paper-admitted.** Needs:

1. Capital sensitivity 10/100/500 (see follow-up JSON)  
2. Explicit formation/OOS split (not just recent-half proxy)  
3. Stability across BTC vs ETH  
4. Separate admission decision  

Follow-up artifact: `reports/prod/research_multi_day_momentum_short_followup.json`

## Takeaways

1. Sparse daily short momentum is the **first positive 10U after-cost** fingerprint in majors research batches.  
2. Long mirror and most other low-turnover families still fail.  
3. Do not inflate by grid search; next work is **validation depth** on this one ID, or a new pre-registered sparse family.  

## Commands

```bash
python -m prod.cli research-batch-majors-v2
```

# Majors research batch v3 result

**Date:** 2026-07-17  
**Command:** `python -m prod.cli research-batch-majors-v3`  
**Report:** `reports/prod/research_batch_majors_v3.json`  
**Theme:** dual-confirm + weekly/streak sparse  
**Universe:** BTC/ETH · **10U** · costs on · no param search  

## Ranking

| Name | Trades | Return | PF | Max DD | Decision |
|------|-------:|-------:|---:|-------:|----------|
| **dual_weekly_mom_short** | 22 | **+0.6%** | **1.04** | 7.2% | **interesting_not_admitted** |
| **weekly_mom_short** | 42 | **+0.4%** | **1.01** | 7.9% | **interesting_not_admitted** |
| dual_daily_breakout_long | 5 | +0.3% | 1.11 | 2.3% | rejected_weak (low N) |
| dual_daily_breakout_short | 6 | -8.1% | 0.17 | 8.7% | rejected_weak |
| weekly_mom_long | 55 | -9.4% | 0.73 | 13.5% | rejected_weak |
| dual_md_mom_short | 132 | -12.8% | 0.84 | 20.8% | rejected_weak |
| dual_streak_down_short | 56 | -13.7% | 0.63 | 19.8% | rejected_weak |
| streak_up_days_long | 188 | -20.1% | 0.79 | 25.4% | rejected_weak |
| streak_down_days_short | 167 | -27.2% | 0.71 | 35.1% | rejected_weak |
| dual_md_mom_long | 144 | -27.9% | 0.57 | 30.4% | rejected_weak |

## Key findings

1. **Dual filter on multi_day_momentum_short hurt** (−12.8% vs single-name +5.5% earlier) → “both agree” is **not** a free robustness upgrade for that shell.  
2. **Weekly Monday momentum short** (single and dual) is barely positive, low DD, **very few trades** → statistically fragile; treat as weak interesting only.  
3. Streak and dual daily families do not help.  

## Paper-prep

**None recommended** without deeper validation (same bar as md_mom_short: formation/OOS + sensitivity + sample size).

## Commands

```bash
python -m prod.cli research-batch-majors-v3
```

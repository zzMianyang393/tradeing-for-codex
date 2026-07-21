# Majors research batch v6 + multiwindow OOS

**Date:** 2026-07-17  
**Commands:**
- `python -m prod.cli research-batch-majors-v6`
- `python -m prod.cli research-v6-oos --names ...`
- Multiwindow: `reports/prod/research_v6_multiwindow_oos_v1.json`

**Data:** clean BTC/ETH native 1h + 4h (OKX `1H`/`4H`), 10U, costs on.

## Context

Same day: `h1_md_mom_short` **revoked** after corrupt ETH 1h timestamps (see `research_h1_data_integrity_revoke_2026-07-17.md`). v6 runs only on clean bars.

## Full-sample ranking (interesting only)

| Name | TF | Trades | Return | PF | DD | Full decision |
|------|----|-------:|-------:|---:|---:|---------------|
| **h4_weekly_mom_short** | 4h | 63 | **+22.3%** | 1.22 | 25% | interesting |
| **h4_slow_ema_cross_long** | 4h | 24 | +12.0% | 1.36 | 10% | interesting |
| h1_dual_daily_breakout_short | 1h | 13 | +10.5% | 2.05 | 7% | rejected (trades&lt;15) |
| h1_daily_breakout_short | 1h | 24 | +1.1% | 1.04 | 14% | interesting (marginal) |
| h4_slow_ema_cross_short | 4h | 27 | +0.2% | 1.00 | 19% | interesting (flat) |
| rest | — | — | negative | — | — | rejected |

## OOS (60% formation / ~1d embargo)

| Name | Formation | OOS | Decision |
|------|-----------|-----|----------|
| h4_weekly_mom_short | **fail** (−9.8%) | **+35.7% PF2.08** | conditional (recent-only risk) |
| h4_slow_ema_cross_long | +? | **−3.2%** | **reject** |
| h4_slow_ema_cross_short | fail | +16% PF2.49 | conditional |
| h1_daily_breakout_short | fail | +2.2% | conditional |
| h1_dual_daily_breakout_short | pass (sparse floors) | +1.7% | single-split recommend **but** |

## Multiwindow (0.50 / 0.60 / 0.70)

| Name | Full ok | OOS pass | Form pass | Trades | Admit? |
|------|---------|----------|-----------|-------:|--------|
| h1_dual_daily_breakout_short | yes | 2/3 | 2/3 | **13** | **No** (sample too thin) |
| h4_weekly_mom_short | yes | **3/3** | **0/3** | 63 | **No** (formation always negative → recent-only) |
| h4_slow_ema_cross_short | yes | 2/3 | 1/3 | 27 | **No** (full ~flat; form mostly neg) |
| h1_daily_breakout_short | yes | 1/3 | 0/3 | 24 | **No** |

## Paper-prep decision

**Admit: none.**

After the h1 integrity revoke, bar for second sleeve:

- clean full-sample clearly positive  
- multiwindow OOS majority  
- multiwindow formation at least one solid pass  
- trades ≥ 20 (prefer ≥ 30)

None of the v6 candidates clear that bar.

### Watchlist (monitor only, no paper)

1. **h4_weekly_mom_short** — strongest OOS, but formation loss everywhere (regime shift risk).  
2. **h1_dual_daily_breakout_short** — high PF, only 13 trades.  
3. **h4_slow_ema_cross_short** — OOS ok, full-sample ~breakeven.

## Notes

- 1h unused families (htf/bb/atr/vol) mostly negative on clean data.  
- 4h md_mom / donchian / streak short failed hard.  
- Dual 1h md_mom remains dropped (see multiwindow revoke path).  
- Demo/live still server-only, not in scope.

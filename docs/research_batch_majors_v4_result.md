# Majors research batch v4 + weekly OOS

**Date:** 2026-07-17  
**Commands:**
- `python -m prod.cli research-weekly-oos`
- `python -m prod.cli research-batch-majors-v4`
- `python -m prod.cli research-daily-oos --names d1_streak_up_long,d1_donchian_short,d1_slow_ema_cross_long`

## A) Weekly shorts OOS (15m proxy from v3)

| Name | Full | Formation | OOS | Decision |
|------|------|-----------|-----|----------|
| dual_weekly_mom_short | +0.6% / PF1.04 / n=22 | +6.1% PF2.06 n=11 | **-5.2% PF0.36 n=11** | **reject** |
| weekly_mom_short | +0.4% / PF1.01 / n=42 | +1.8% PF1.10 n=27 | **-1.4% PF0.84 n=15** | **reject** |

Both fail OOS. Archive; do not paper.

## B) Native daily batch (1D, ~878 bars to 2026-05-27)

| Name | Trades | Return | PF | Max DD | Decision |
|------|-------:|-------:|---:|-------:|----------|
| d1_slow_ema_cross_long | 3 | +19.7% | 10.0 | 2.2% | rejected (n too small) |
| **d1_streak_up_long** | 49 | **+15.6%** | **1.10** | 25.0% | interesting |
| **d1_donchian_short** | 17 | **+6.3%** | **1.11** | 18.7% | interesting |
| others | — | negative | &lt;1 | — | rejected |

Note: native daily `d1_md_mom_short` is **−35%** — 15m-proxy “daily” md_mom_short (+5.5%) does **not** reproduce on true 1D bars.

## C) OOS for daily interesting

| Name | Full | Formation | OOS | Decision |
|------|------|-----------|-----|----------|
| d1_streak_up_long | +15.6% PF1.10 n=49 | **−12.8%** | **−12.5%** | **reject** |
| d1_donchian_short | +6.3% PF1.11 n=17 | weak/neg n=9 | **+6.6% PF1.31 n=8** | **conditional_watchlist** |
| d1_slow_ema_cross_long | +19.7% n=3 | n too small | n=1 | **reject** (sample) |

`d1_donchian_short`: OOS positive but formation fails and trade count is low → **not paper-prep**.

## Paper-prep

**None admitted.** Patterns that look good full-sample keep failing formation and/or OOS.

## Important methodological note

15m-proxy “daily” multi_day_momentum_short (**+5.5%**) does **not** hold on native 1D (**−35%**). Prefer native timeframe for sparse rules going forward.

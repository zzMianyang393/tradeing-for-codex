# 弱因子-行情适配矩阵（2026-07-13）

## 概述

预注册 7 个影子观察方向因子与 4 种行情标签的适配关系。矩阵为固定映射，不根据数据修改。

## 适配矩阵

| 因子 ID | 适用行情 | 不适用行情 | BTC确认 | 粒度 | 允许角色 | 重叠风险 |
|---|---|---|---|---|---|---|
| low_volatility_drift_bb | 震荡 | 趋势上行/下行/高波动 | 否 | 4h | directional | daily_bb_mean_revert |
| ema_continuation_short | 趋势下行 | 趋势上行/震荡/高波动 | 是 | 4h | directional | — |
| persistent_uptrend_ema20 | 趋势上行 | 趋势下行/震荡/高波动 | 是 | 4h | directional | daily_ma_alignment |
| daily_volume_shock_rev | 高波动/震荡 | 趋势上行/下行 | 否 | daily | directional | — |
| weekly_cross_sectional | 趋势上行/下行 | 震荡/高波动 | 否 | weekly | directional | weekly_microtrend |
| weekly_microtrend_cont | 趋势上行/下行 | 震荡/高波动 | 否 | weekly | directional | weekly_cross_sectional |
| donchian_atr_trend | 趋势上行 | 趋势下行/震荡/高波动 | 否 | daily | directional | persistent_uptrend |

## 语义重叠对

1. `weekly_cross_sectional_momentum` ↔ `weekly_range_microtrend_continuation`：同为周线趋势因子
2. `donchian_atr_trend_baseline` ↔ `persistent_uptrend_ema20_reclaim`：同为趋势上行因子
3. `low_volatility_drift_bb` ↔ `daily_bb_mean_revert`：同为震荡反弹因子

## 局限性

- 矩阵为预注册固定映射，不基于数据验证
- 不计算因子收益
- 重叠对为观察信号，不构成禁止

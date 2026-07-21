# 组合层覆盖缺口地图（2026-07-13）

## 概述

识别哪些行情状态已有方向因子覆盖、哪些只有 context/filter、哪些完全空白。

## 覆盖结果

| 行情状态 | 状态 | 方向因子数 | 方向因子 |
|---|---|---|---|
| 趋势上行 | **over_covered** | 4 | persistent_uptrend, weekly_cross, weekly_micro, donchian_atr |
| 趋势下行 | **over_covered** | 3 | ema_continuation, weekly_cross, weekly_micro |
| 高波动转换 | **covered** | 1 | daily_volume_shock |
| 震荡 | **covered** | 2 | low_volatility_drift_bb, daily_volume_shock |

## 关键发现

1. **趋势行情过度覆盖：** 趋势上行有 4 个方向因子，趋势下行有 3 个，存在重复暴露风险
2. **高波动转换覆盖薄弱：** 仅 1 个因子（daily_volume_shock），且样本不足
3. **震荡行情覆盖适中：** 2 个因子，但有语义重叠风险（BB 类因子）
4. **无完全空白行情：** 所有 4 种行情状态至少有 1 个方向因子

## 语义重叠风险

1. `weekly_cross_sectional` ↔ `weekly_microtrend`：趋势行情中重复投票
2. `donchian_atr` ↔ `persistent_uptrend`：趋势上行中重复投票
3. `low_volatility_drift_bb` ↔ `daily_volume_shock`：震荡行情中重复投票

## 局限性

- 覆盖分析基于预注册矩阵，不基于因子实际表现
- 不创建交易规则
- 不评估因子质量

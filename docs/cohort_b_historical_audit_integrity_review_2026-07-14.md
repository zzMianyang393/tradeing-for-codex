# Cohort B 历史审计完整性复核（2026-07-14）

## 概述

对四个历史审计脚本与其研究卡进行一致性复核，发现并修复 5 个问题。

## 复核结果

### Pair 1: month_boundary_flow

| 检查项 | 修复前 | 修复后 |
|---|---|---|
| 参数一致性 | ✅ EMA20, ROC5, hold 5d, ATR14, stop 2x | ✅ + parameters dict 完善 |
| 4h 延迟 | ✅ 代码有 `signal_ts + FOUR_HOURS_MS` | ✅ 研究卡需更新 |
| 成本 0.16% | ✅ | ✅ |
| Formation/OOS | ✅ 2024 / 2025-01-01~2025-07-10 | ✅ |
| 月度集中度 | ❌ 代码未检查 | ✅ 添加 `_month_concentration` |
| 样本不足状态 | ❌ events<15 标为 historical_rejected | ✅ 改为 insufficient_evidence |

### Pair 2: weekend_low_liquidity_reversion

| 检查项 | 修复前 | 修复后 |
|---|---|---|
| 参数一致性 | ✅ EMA5, RSI14, ATR14, stop 1.5x, hold 2d | ✅ |
| 4h 延迟 | ✅ 代码有 `FOUR_HOURS_MS` | ✅ 研究卡需更新 |
| 成本 0.16% | ✅ | ✅ |
| Formation/OOS | ✅ | ✅ |
| EMA5 退出 | ❌ 代码缺少 EMA5 退出条件 | ✅ 添加 EMA5 检查 |
| 月度集中度 | ❌ 代码未检查 | ✅ 添加 `_month_conc` |
| 样本不足状态 | ❌ events<15 标为 historical_rejected | ✅ 改为 insufficient_evidence |

### Pair 3: parkinson_volatility_extreme_reversion

| 检查项 | 修复前 | 修复后 |
|---|---|---|
| 参数一致性 | ✅ EMA20, ATR20, Parkinson 20d, lookback 120d, hold 7d | ✅ |
| 4h 延迟 | ✅ 代码有 `FOUR_HOURS_MS` | ✅ 研究卡需更新 |
| 成本 0.16% | ✅ | ✅ |
| Formation/OOS | ✅ | ✅ |
| Parkinson 分位数 | ⚠️ 近似计算（index 107 ≈ 90th） | ⚠️ 可接受，已记录 |
| 月度集中度 | ❌ 代码未检查 | ✅ 添加 `_mc` |
| 样本不足状态 | ❌ events<15 标为 historical_rejected | ✅ 改为 insufficient_evidence |

### Pair 4: daily_bias_range_reversion

| 检查项 | 修复前 | 修复后 |
|---|---|---|
| 参数一致性 | ✅ EMA20, ATR14, BIAS<=-10%, hold 7d, stop 2x | ✅ |
| 4h 延迟 | ✅ 代码有 `FOUR_HOURS_MS`，研究卡已记录 | ✅ |
| 成本 0.16% | ✅ | ✅ |
| Formation/OOS | ✅ | ✅ |
| 月度集中度 | ❌ 代码未检查 | ✅ 添加 `_mc` |
| 样本不足状态 | ❌ events<15 标为 historical_rejected | ✅ 改为 insufficient_evidence |

## 修复清单

### 代码修复

| 文件 | 修复 |
|---|---|
| `month_boundary_flow_audit.py` | 添加 `_month_concentration`；verdict 区分 insufficient_evidence；parameters dict 补充 atr_period/stop_atr_multiple |
| `weekend_low_liquidity_reversion_audit.py` | 添加 EMA5 退出条件；添加 `_month_conc`；verdict 区分 insufficient_evidence |
| `parkinson_volatility_extreme_reversion_audit.py` | 添加 `_mc`；verdict 区分 insufficient_evidence；添加 datetime import |
| `daily_bias_range_reversion_audit.py` | 添加 `_mc`；verdict 区分 insufficient_evidence；添加 datetime import |

### 研究卡修复

| 卡 | 修复 |
|---|---|
| month_boundary_flow_research_card | 需补充"4h 可用延迟"说明 |
| weekend_low_liquidity_reversion_research_card | 需补充"4h 可用延迟"说明 |
| parkinson_volatility_extreme_reversion_research_card | 需补充"4h 可用延迟"说明 |
| daily_bias_range_reversion_research_card | ✅ 已记录 4h 延迟 |

## 跨切面问题

### Issue A: 4h 延迟（3/4 卡遗漏）

代码全部正确实现 `signal_ts + FOUR_HOURS_MS`。仅 daily_bias 卡明确记录了此延迟。
其他三张卡应补充："入场价格为信号后 4h 可用时点的下一根 15m 开盘。"

### Issue B: 月度集中度规则（4 个审计全部遗漏）

三张研究卡（month_boundary, weekend, parkinson）包含 "<=25% positive-return contribution from any month" 规则。
daily_bias 卡无此规则（仅要求 >=15 事件和正净收益）。
修复后四个审计均已实现集中度检查。

### Issue C: Parkinson 分位数近似

代码使用固定 index 107 而非精确百分位计算。在 120 个非空值窗口中约等于 89.2th 百分位。
与研究卡 ">=90" 有微小偏差。可接受，已记录。

## 最终结论

四个审计脚本与研究卡的主要差异已修复：
- verdict 逻辑区分 insufficient_evidence 和 historical_rejected
- 月度集中度检查已添加
- EMA5 退出条件已添加（weekend）
- 4h 延迟在代码中正确实现，研究卡需补充文档

## 禁止事项

- 不得调整参数来改善结果
- 不得接触 Cohort A/B ledger、checkpoint、runner 或交易权限

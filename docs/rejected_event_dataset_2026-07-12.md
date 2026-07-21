# 统一失败事件数据集（2026-07-12）

## 概述

从已 rejected 策略报告中统一抽取失败事件，标准化为单一 JSON 数据集。
用于下游"不交易过滤器"研究。

## 数据来源

| 来源报告 | 策略 ID | 抽取事件数 |
|---|---|---|
| `multi_coin_funding_crowding_audit.json` | multi_coin_funding_crowding | 10 |
| `funding_oi_trend_confirmation_repaired.json` | funding_oi_trend_confirmation | 26 |
| **合计** | | **27**（去重后） |

## 跳过的来源（16 份报告）

以下报告没有逐事件明细，记录为 `skipped_sources`，未伪造事件：

| 策略 ID | 跳过原因 |
|---|---|
| relative_strength_persistence | no_event_details |
| btc_trend_pullback | no_event_details |
| vol_compression_breakout | no_event_details |
| pairs_walk_forward | no_event_details |
| spot_perp_basis (2 份) | no_event_details |
| btc_alt_lead_lag | no_event_details |
| positive_funding_carry | no_event_details |
| range_regime_funding_extreme | no_event_details |
| daily_oi_independent_change | no_event_details |
| donchian_atr_trend_baseline | no_event_details |
| range_regime_mean_reversion_family | no_event_details |
| utc_session_breakout_family | no_event_details |
| okx_futures_calendar_spread (3 份) | no_event_details |

## 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| strategy_id | string | 注册表中的研究 ID |
| source_report | string | 来源 JSON 文件名 |
| event_time | string | 事件日期 YYYY-MM-DD |
| symbol | string | 交易标的（或多币种标记） |
| regime | string | 市场状态标签 |
| holding_hours | int | 持有时间（小时） |
| gross_return | float | 毛收益（%），可为 null |
| net_return | float | 净收益（% 扣成本），可为 null |
| cost_bps | int | 往返成本（基点） |
| month | string | 事件月份 YYYY-MM |
| failure_reason | string | 失败原因分类 |

## 失败原因分类

- `severe_loss`: 净亏损 > 0.5%
- `net_negative`: 净收益为负
- `gross_negative`: 毛收益为负
- `unknown`: 无法分类

## 数据集局限性

1. **覆盖率低：** 15 个 rejected 策略中仅 2 个有逐事件明细
2. **时间集中：** 事件集中在 2024-07 至 2025-01（形成期）
3. **方向集中：** 仅覆盖 funding+OI 和 funding 拥挤方向
4. **无币种拆分：** 大部分事件为跨币种聚合，无法做币种级分析

## 使用说明

此数据集用于"不交易过滤器"的统计研究，**不得用于**：
- 升级小样本观察为硬过滤器
- 构建交易信号
- 接入 runner.py
- 参数优化

## 生成命令

```bash
python rejected_event_extractor.py --out reports/rejected_event_dataset.json
```

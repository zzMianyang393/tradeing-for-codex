# 策略原型 Universe Schema 与 Preflight 审查（2026-07-13）

## 概述

建立机器可读的策略原型库（34 个原型）和开题前审查工具，用于从约 100 个策略原型
中筛选可研究方向。当前为第一版（34 个），覆盖 10 个策略家族。

## 原型库

`strategy_prototype_universe.py` 定义 `StrategyPrototype` 数据结构：

| 字段 | 类型 | 说明 |
|---|---|---|
| strategy_id | string | 唯一标识 |
| name_cn | string | 中文名 |
| family | string | 策略家族 |
| expected_hold_days | float | 预期持有天数 |
| expected_events_per_month | float | 预期每月事件数 |
| executed_legs | int | 执行腿数（2 或 4） |
| required_data | list | 所需数据类型 |
| uses_external_data | bool | 是否使用外部数据 |
| uses_hft_or_orderbook | bool | 是否使用 HFT/盘口/逐笔 |
| uses_grid_or_martingale | bool | 是否使用网格/马丁/锁仓 |
| resembles_rejected | list | 相似的已淘汰方向 |
| notes | string | 备注 |

## 家族覆盖

| 家族 | 原型数 | 说明 |
|---|---|---|
| trend_following | 5 | 趋势跟踪 |
| mean_reversion | 4 | 均值回归 |
| breakout | 3 | 突破 |
| funding_carry | 3 | Funding/Carry |
| oi_leverage | 3 | OI/杠杆状态 |
| cross_asset | 4 | 跨品种/套利 |
| grid_martingale | 3 | 网格/马丁（风险阻断） |
| event_news | 3 | 事件/新闻（数据阻断） |
| machine_learning | 3 | 机器学习（冻结） |
| hft_microstructure | 3 | HFT/盘口（数据阻断） |

## Preflight 审查结果

`strategy_preflight_review.py` 读取 risk_map、registry 和原型库，输出状态：

| 状态 | 数量 | 原型 |
|---|---|---|
| **eligible_for_research** | 0 | — |
| meta_only | 3 | oi_divergence_signal, oi_extreme_crowding, leverage_ratio_reversal |
| risk_blocked | 3 | grid_trading, martingale_loss_add, locking_hedge |
| data_blocked | 6 | news/macro/social + orderbook/tick/liquidation |
| duplicate_rejected | 20 | 与已淘汰方向、未解释相似标签或登记册精确淘汰 ID 高度相似 |
| frozen | 2 | ML 家族 |
| rejected_by_cost | 0 | — |
| rejected_by_turnover | 0 | — |

## 强制规则执行情况

| 规则 | 执行结果 |
|---|---|
| grid/martingale → risk_blocked | ✅ 3 个原型阻断 |
| external/news/macro → data_blocked | ✅ 3 个原型阻断 |
| HFT/orderbook/tick → data_blocked | ✅ 3 个原型阻断 |
| expected_hold < 3d → rejected_by_turnover | ✅ 已检查（部分被 meta_only 覆盖） |
| expected_events > 12/mo → rejected_by_turnover | ✅ 已检查 |
| 4-leg must clear 0.32% | ✅ 已检查 |
| 2-leg must clear 0.16% | ✅ 已检查 |
| exact rejected/invalid ID → duplicate_rejected | ✅ 已审计淘汰的原型不得重新 eligible |
| resembles_rejected → duplicate_rejected | ✅ 20 个原型标记；未匹配登记册的相似标签也不得 eligible |
| OI/leverage → meta_only | ✅ 3 个原型标记 |
| ML → frozen | ✅ 2 个原型标记；带冻结/淘汰相似标签的 RL 路由先按 duplicate_rejected 处理 |

## 仲裁说明

`4h_ema_crossover` 原先通过机器预检，但它带有 `multi_timeframe` 相似标签。该标签尚未与登记册中的具体淘汰 ID 对齐，因此本版按保守原则将其改为 duplicate_rejected，不进入第一批工程审计。Gemini 的 111 原型草案作为策略地图使用，不直接覆盖登记册、risk_map 或本预检结果。

`daily_ma_alignment` 和 `daily_bb_mean_revert` 均已完成真实数据审计并被登记册标记为 rejected，因此本预检也同步将它们改为 duplicate_rejected。当前没有任何原型可直接进入下一轮工程审计。

## 安全闸门

- approved_for_paper = []
- safe_to_enable_trading = false
- risk_blocked/data_blocked/duplicate_rejected 不得判定为 eligible

## 使用方法

```bash
# 运行预检审查
python strategy_preflight_review.py --out reports/strategy_preflight_review.json

# 查看原型库
python strategy_prototype_universe.py
```

## 禁止事项

- 不接入 runner.py
- 不开启实盘
- 不把任何原型直接升级为 candidate
- 不修改交易执行逻辑

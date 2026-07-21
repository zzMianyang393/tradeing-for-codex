# 策略宇宙与研究优先级（2026-07-12）

## 目的

这份文档把常见 EA/CTA/量化策略先归入可管理的研究家族。它不是策略批准清单，也不是参数搜索清单。任何家族只有在预注册、形成期事件审计、样本外验证、成本与风控审查全部通过后，才能进入 `approved` 状态。

当前交易闸门不变：`approved_for_paper=[]`，`safe_to_enable_trading=false`。

## 状态口径

| 状态 | 含义 | 是否可交易 |
|---|---|---|
| `rejected` | 已严肃验证失败 | 否 |
| `invalid` | 历史报告作废，通常含前视或方法问题 | 否 |
| `pending` | 已有研究设计，等待事件审计 | 否 |
| `candidate` | 候选研究家族，尚未预注册 | 否 |
| `frozen` | 暂停，缺少独立 alpha 或研究条件 | 否 |
| `data_blocked` | 数据门槛未过 | 否 |
| `risk_blocked` | 尾部风险结构不符合当前硬规则 | 否 |
| `meta_only` | 只提供审计/约束，不产生信号 | 否 |
| `approved` | 研究批准；还需 `eligible_for_paper=true` | 仅同时满足时 |

## 已覆盖且不可交易

| 家族 | 代表策略 | 当前结论 |
|---|---|---|
| 旧动态路由 | 多信号/ML 路由高收益报告 | `invalid`，旧配置、路由复用与 MFE 标签问题 |
| 相对强弱/动量延续 | RS 排序、强者恒强、动量波段 | `rejected`，样本外失败 |
| BTC 趋势内山寨回调 | 大周期 BTC 定方向，小周期山寨回调 | `rejected`，形成期亏损 |
| 波动率压缩突破 | 布林压缩、低波动突破 | `rejected`，样本不足且完整验证失败 |
| 配对统计套利 | 强相关配对、价差回归 | `rejected`，无配对过形成期/OOS/多重检验 |
| 期现基差 | 现货/永续基差、市场中性 carry | `rejected`，四腿成本覆盖不了 |
| 多币 funding 拥挤 | 固定绝对 funding 阈值反转 | `rejected`，事件收益为负 |
| Funding + OI 原始 | funding 与日线 OI 联合 | `invalid`，存在前视偏差 |
| Funding + OI 时间修复 | OI 16:00 可用、16:15 入场 | `rejected`，形成期净收益为负 |
| 日线 OI 独立变化率 | 多币同步 OI 大幅变化，16:15 后观察 | `rejected`，形成期 4h 胜率不足，OOS 4h 两侧为负 |
| 唐奇安 + ATR 趋势基准 | 20 日 Donchian 突破，2xATR 固定止损，10 日持有 | `rejected`，形成期单月集中度超标，OOS 扣成本后为负 |
| 震荡行情内均值回归 | 4h 震荡标签内 BB20/2σ 下轨反弹 | `rejected`，形成期净均值为负、胜率和 PF 不达标 |
| UTC 时段开盘区间突破 | 00:00-04:00 区间高点收盘突破做多 | `rejected`，形成期净均值为负、胜率和 PF 不达标 |
| 震荡行情内 Funding 异常 | 震荡标签内 funding 滚动分位数极端 | `rejected`，4h 净收益为负、胜率不足、月集中度超标 |
| BTC 短时领先滞后 | BTC 事件后非 BTC 追随/反转 | `rejected`，成本前后均为负 |
| 正 funding carry | 现货多、永续空收资金费 | `rejected`，事件不足以覆盖四腿成本 |

## 候选研究优先级

### P1：日线 OI 独立变化率

已完成并淘汰。跨时间审计显示 OI 指标相对稳定，但稳定数据特征没有转化为可交易边际。

已执行冻结规则：
- 只用 OKX 日线 OI 与 OKX 15m OHLCV；
- OI 按 `16:00 UTC` 可用，最早 `16:15 UTC` 入场；
- 不加入 funding；
- 形成期失败直接淘汰。

结论：形成期 4h 最佳方向胜率低于 55%，样本外 4h long/short 扣成本后均为负，状态为 `rejected`。

### P2：唐奇安通道 + ATR 趋势基准

代表策略：海龟、N 日高低点突破、通道突破、ATR 追踪止损、部分均线趋势变体。

预注册研究卡：`docs/donchian_atr_trend_baseline_research_card.md`。
事件审计：`docs/donchian_atr_trend_baseline_audit_2026-07-12.md` 与
`reports/donchian_atr_trend_baseline_audit.json`。

研究意义：给趋势类策略一个干净基准，避免把双均线、MACD、ADX、SAR 等小变体重复当成独立 alpha。

结论：已淘汰。形成期 228 个事件，扣成本净均值 +2.8221%，胜率 50.00%，盈利因子
1.5577；但 2024-11 单月事件集中度 26.32%，超过预注册上限 25%。样本外 232 个事件，
扣成本净均值 -0.5898%，胜率 37.93%，盈利因子 0.8993。

### P3：震荡行情内均值回归

代表策略：RSI、KDJ、布林带反弹、BIAS、区间高抛低吸、日内高低点反转。

预注册研究卡：`docs/range_regime_mean_reversion_research_card.md`。
事件审计：`docs/range_regime_mean_reversion_audit_2026-07-12.md` 与
`reports/range_regime_mean_reversion_audit.json`。

结论：已淘汰。形成期 231 笔事件，扣成本净均值 -0.1230%，胜率 47.62%，盈利因子
0.8598；样本外 188 笔事件，扣成本净均值 -0.7467%，胜率 36.70%，盈利因子 0.5003。

### P4：UTC 时段开盘区间突破

代表策略：开盘区间突破、箱体突破、放量突破、多周期日内突破、时间切片策略。

预注册研究卡：`docs/utc_session_breakout_research_card.md`。
事件审计：`docs/utc_session_breakout_audit_2026-07-12.md` 与
`reports/utc_session_breakout_audit.json`。

结论：已淘汰。形成期 3440 笔事件，扣成本净均值 -0.2059%，胜率 40.32%，盈利因子
0.7776；样本外 3431 笔事件，扣成本净均值 -0.0696%，胜率 42.52%，盈利因子 0.9170。

### P5：OKX 交割合约跨期价差

已完成并淘汰。OKX 官方免费历史归档支持数据研究，BTC-USDT 交割合约与 BTC-USDT-SWAP
在 2025-06-01 至 2026-06-30 区间完成真实下载、覆盖审计和 spread-first 价差序列构造。

证据：
- `docs/okx_futures_calendar_spread_data_feasibility_2026-07-12.md`
- `docs/okx_futures_calendar_spread_pipeline_research_card.md`
- `docs/okx_futures_calendar_spread_real_coverage_2026-07-12.md`
- `docs/okx_futures_calendar_spread_series_and_descriptive_audit_2026-07-12.md`
- `docs/okx_futures_calendar_spread_mean_reversion_research_card.md`
- `docs/okx_futures_calendar_spread_mean_reversion_audit_2026-07-12.md`
- `reports/okx_futures_calendar_spread_mean_reversion_audit.json`

结论：覆盖审计通过，价差确实存在可观察波动；但预注册均值回归规则在形成期 4341 笔事件中
扣成本净均值 `-0.0938%`、胜率 `9.33%`、盈利因子 `0.068`；样本外 4299 笔事件中扣成本净均值
`-0.0615%`、胜率 `21.91%`、盈利因子 `0.303`。失败后不得调参重跑。

## 默认冻结或风险受阻

| 家族 | 处理 |
|---|---|
| 网格、马丁、锁仓、亏损加仓 | `risk_blocked`，尾部风险换平滑收益，不符合当前研究硬规则 |
| 机器学习、LSTM、强化学习、动态调参 | `frozen`，没有独立 alpha 前只能做分类器或组合器，不能制造信号 |
| 外部事件、新闻舆情、宏观日历 | `frozen`，免费可复现历史数据库不足，发布时间对齐和前视偏差风险过高 |
| 财报、股息、ETF 折溢价、可转债 | 不适用 OKX 加密永续研究范围 |
| 多交易所价差套利、盘口剥头皮、tick 高频 | 免费历史深度、延迟与成交质量无法复现，暂不推进 |
| 期权波动率对冲 | OKX 免费期权历史深度不足，冻结 |

## 当前推荐执行顺序

当前无剩余候选策略。

下一步不应继续堆叠常见 EA 小变体，应先做成本与可交易性复盘：

1. `execution_cost_floor_audit`：审计不同腿数、持有周期、入场频率下的最低可行收益门槛。
2. `low_turnover_research_design`：只允许低换手、低事件数、持有 3-14 天以上的方向进入研究卡。
3. `no_trade_filter_research`：研究市场状态过滤器是否能减少失败交易，而不是生成新信号。

其中 `execution_cost_floor_audit` 与低换手研究门槛已经完成：

- `docs/execution_cost_floor_audit_2026-07-12.md`
- `docs/low_turnover_research_gate_2026-07-12.md`

每一步都必须先写研究卡，再写事件审计，再判断是否进入样本外。没有任何一项可以直接接入 `runner.py`。

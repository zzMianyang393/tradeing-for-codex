# Claude Code 交接：ML 实验与当前瓶颈

更新时间：2026-07-09

## 一、当前核心问题

### 问题 1：手工规则策略到天花板

保守基线（transition_breakout_long only）：

```text
365天回测：
trades = 8
win_rate = 37.5%
return = +35.61%
max_drawdown = 17.98%
```

这是当前唯一盈利的策略，但 365 天只有 8 笔交易，统计上不可靠。

### 问题 2：所有其他策略都亏损

```text
trend_short (无门控): 19-60笔, 35-72%胜率, 但 PnL 为负
trend_long:           4笔, 0%胜率, -17.67%
range_revert:         混合, 胜率高但盈亏比差
attack/micro:         全部亏损
```

### 问题 3：ML 模型同样过拟合

```text
XGBoost 实验结果:
v4 (180d训练, 3%阈值, min_score=0.65): 5034笔, 36.57%WR, +733%PnL
v5 (180d训练, 3%阈值, min_score=0.75): 2174笔, 34.82%WR, +145%PnL
v6 (90d训练,  3%阈值, min_score=0.70): 13615笔, 33.65%WR, +196%PnL

问题: 2026年5-7月窗口贡献大部分利润，其他窗口亏损。
与手工规则相同的过拟合模式。
```

---

## 二、根本原因分析

### 原因 1：数据样本不足

```text
当前数据范围: 2025-04-24 到 2026-07-02 (约 14 个月)
可用 K 线: 41,629 根 (15m)
覆盖行情: 主要是震荡 + 一段明显上涨 (2026年5-7月)
缺失行情: 熊市、暴跌、长期横盘
```

只有 14 个月数据，且只包含一段明显趋势行情。任何策略（手工或 ML）都只能在这段行情中盈利。

### 原因 2：Transition Regime 太稀缺

```text
classify_regime() 判定:
  uptrend:    ema50 > ema200 且 trend_strength > 1.2
  downtrend:  ema50 < ema200 且 trend_strength < -1.2
  range:      atr_pct < 0.0045 或 |trend_strength| < 0.9
  transition: 其余 (窗口: 0.9-1.2 或 -1.2 到 -0.9)

问题: transition 窗口极窄，365天只出现 8 次有效交易机会
尝试放宽: 阈值从 1.2 降到 1.0，只增加 1 笔交易，质量下降
```

### 原因 3：手工规则策略无 edge

```text
趋势做空: 60笔, 71.67%胜率, 但 PnL = -0.3578
  → 赢小亏大，退出逻辑有问题
趋势做多: 5笔, 60%胜率, +1.06U
  → 交易太少
区间反转: 胜率 60-67%, 但 PnL 为负
  → 止盈太小，止损/拖尾不合理
```

### 原因 4：ML 模型标签设计问题

```text
原始标签: 未来 96 根 K 线内价格上涨 1% = 正例
问题: 69.8% 标签都是正例 → 模型只预测多数类

调整后: 未来 48 根 K 线内价格上涨 3% = 正例
结果: 37.9% 正例，但模型仍不稳定
```

---

## 三、已尝试的所有方向

| 方向 | 结果 | 结论 |
|------|------|------|
| 放宽 transition 带 (0.7-1.0) | 9笔, +20% | 只多1笔，质量下降 |
| 降低 min_score | 8笔, +41% | 无变化 |
| 加入 range_revert | 10笔, -20% | range_revert 拖累 |
| trend_short only | 19笔, -24% | 趋势做空亏损 |
| trend_long only | 4笔, -18% | 趋势做多亏损 |
| trend_short_factor gate | 19-22笔, -13%~-33% | 因子门控选出更差交易 |
| XGBoost ML | 5034笔, 36%WR, +733% | 过拟合到2026年5-7月 |

**唯一盈利: 保守基线 (transition_breakout_long only, 8笔, +35.61%)**

---

## 四、当前代码状态

### 已实现的功能

```text
✅ 动态策略路由 (backtester.py)
✅ 策略适用行情标签 (dynamic_router_experiment.py)
✅ 中文验收报告 (dynamic_router_acceptance.py)
✅ 跨窗口过拟合风险检查
✅ 路由拒绝统计
✅ 趋势策略因子审计 (trend_factor_audit.py)
✅ 趋势做空因子门控
✅ 可配置 regime 分类阈值
✅ ML 信号生成器 (ml_signal.py)
✅ ML 集成到回测引擎
✅ 独立退出 profile (trend_short_factor)
```

### 关键文件

```text
strategy.py              - 信号生成器 (7个手工 + ML)
backtester.py            - 回测引擎 + 动态路由 + ML 集成
config.py                - 配置参数 (100+)
ml_signal.py             - XGBoost ML 模块
dynamic_router_experiment.py - 动态路由实验
dynamic_router_acceptance.py - 中文验收报告
trend_factor_audit.py    - 趋势因子审计
transition_cross_validation.py - 跨窗口验证
monthly_breakdown.py     - 月度拆分分析
```

### 测试状态

```text
452 tests passing
```

---

## 五、后续方向建议

### 方向 A：获取更多数据（推荐优先）

```text
问题: 当前只有 14 个月数据，覆盖行情不足
解决: 下载 2024-01 到 2025-04 的历史数据，增加到 30+ 个月
工具: okx_downloader.py --symbols BTC-USDT-SWAP ETH-USDT-SWAP --days 730 --bar 15m --out data
预期: 覆盖更多行情类型，策略验证更可靠
```

### 方向 B：优化 ML 标签设计

```text
当前标签: 价格涨幅 > 阈值 = 正例
问题: 太简单，噪声大
改进:
  1. 用 Sharpe ratio 而不是简单涨幅
  2. 用最大回撤调整后的收益
  3. 用多时间框架确认
  4. 用交易方向（不只做多）
```

### 方向 C：集成 FreqAI

```text
优势: FreqAI 有成熟的滑动窗口重训练、特征工程、集成模型
工具: 直接用 Freqtrade + FreqAI
风险: 需要重新搭建，可能重复之前的过拟合问题
```

### 方向 D：接受现实，小资金验证

```text
当前保守基线: 8笔/年, +35.61% return, 17.98% dd
问题: 交易太少，统计不可靠
建议: 用 10U 小资金在 OKX 模拟盘跑 3-6 个月
目标: 验证策略在真实市场是否有效
前提: 必须有完整的监控和止损机制
```

---

## 六、推荐执行顺序

```text
1. 先获取更多数据 (方向 A)
2. 用 30+ 个月数据重新验证所有策略
3. 如果策略仍不稳定，尝试 ML 标签优化 (方向 B)
4. 如果仍不行，考虑 FreqAI (方向 C)
5. 任何时候都可以用小资金验证 (方向 D)
```

---

## 七、核心结论

```text
当前项目在工程层面已经完成（回测、风控、执行、监控），
但在策略层面没有找到可靠的 edge。

根本原因不是代码问题，是:
1. 数据样本不足（14个月，只有一段趋势行情）
2. 手工规则策略在当前市场无 edge
3. ML 模型同样过拟合到近期行情

下一步核心: 获取更多历史数据，覆盖多种行情类型，
然后重新验证所有策略。
```

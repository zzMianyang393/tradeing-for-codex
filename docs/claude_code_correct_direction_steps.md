# Claude Code 正确方向步骤指示

更新时间：2026-07-09

## 结论先行

当前项目不是“完全没有 edge”，也不是“应该马上转向 ML”。正确判断是：

```text
✅ transition_breakout_long 是当前唯一稳定正收益核心，但交易太少。
✅ trend_short_factor 有方向边际，胜率很高，但退出/盈亏比失败。
✅ ML 出现明显窗口过拟合，只能先作为规则信号过滤器。
✅ 数据需要补齐，但补数据不是替代策略修复，而是用于验证策略修复是否真实。
```

因此正确优先级是：

```text
1. 先修 trend_short_factor 的独立出场/风控
2. 同时准备补齐更长、更统一的数据
3. 用 365 天 + 12 月拆分 + 剔除 2026-05~07 验证
4. ML 只做过滤器，不允许直接裸开仓
5. FreqAI 暂缓，不作为当前优先任务
```

## 当前真实基线

### ✅ 保守核心策略

```text
策略：transition_breakout_long only
start_equity = 10
end_equity = 13.5609
return = 35.61%
max_drawdown = 17.98%
trades = 8
```

含义：

```text
这个策略能赚钱，但交易太少。
它适合作为核心保守基线，不适合作为唯一收益来源。
```

### ✅ trend_short_factor 当前状态

```text
模式：trend_short_factor
end_equity = 12.9060
return = 29.06%
max_drawdown = 25.91%
trades = 68
win_rate = 67.65%
```

拆解：

```text
trend_short:
trades = 60
wins = 43
win_rate = 71.67%
pnl = -0.3578
```

含义：

```text
trend_short_factor 方向判断有边际。
问题不是入场，而是退出、止盈、止损、trailing、max_hold 和亏损控制。
```

## 为什么不能先继续 ML

当前 ML 结果的问题：

```text
高收益集中在 2026-05~2026-07
其他窗口不稳定或亏损
交易数过多，模型可能学到行情窗口，而不是交易 edge
标签设计仍然噪声很大
```

因此：

```text
❌ 不允许 ML 直接决定开仓
✅ ML 只能过滤已有规则信号
```

允许的 ML 用法：

```text
transition_breakout_long 出现 -> ML 判断是否放行
trend_short_factor 出现 -> ML 判断是否放行
```

禁止的 ML 用法：

```text
ML 直接裸开多/开空
只看总收益不看月度拆分
只用 2026-05~07 贡献证明模型有效
继续调 XGBoost 参数追高收益
```

## 为什么仍然需要补数据

当前数据并不是完全不够，而是不均衡：

```text
15m:
BTC/ETH 有 2024-01 到 2026-07
多数其他币只有 2025-04 到 2026-07

5m:
约 60 天

1m:
约 30 天
```

当前 regime 分布：

```text
downtrend  = 41.93%
uptrend    = 33.81%
range      = 20.05%
transition = 4.21%
```

问题：

```text
transition 很少，所以 transition_breakout_long 交易少。
多数山寨币缺少 2024 全年统一窗口。
1m/5m 太短，无法可靠优化出场和滑点。
funding/open_interest/trade_flow/order_book 数据覆盖不足。
```

需要补的数据：

```text
✅ 核心币种 2024-01 至今的统一 15m 数据
✅ 更长 5m/1m 数据，用于出场、滑点、短线结构验证
✅ 同期 funding、open interest、trade flow、order book
✅ 覆盖牛市、熊市、暴跌、长期横盘、假突破、高波动趋势
```

但注意：

```text
补数据是为了验证和防过拟合。
不是补完数据就自动有收益。
```

## Claude Code 第一优先任务

### 任务 1：实现 trend_short_factor 独立退出 profile

新增配置建议：

```python
trend_short_factor_stop_atr
trend_short_factor_take_profit_atr
trend_short_factor_trailing_atr
trend_short_factor_max_hold_bars
trend_short_factor_break_even_mfe_pct
trend_short_factor_break_even_lock_pct
trend_short_factor_time_exit_loss_cooldown_bars
```

实现要求：

```text
✅ 只影响 router_trend_short_factor_gate_enabled=True 且 reason == trend_short 的交易
✅ 不影响普通 trend_short
✅ 不影响 transition_breakout_long
✅ 不影响 range/attack/micro/ML
```

代码位置：

```text
config.py
backtester.py
tests/test_dynamic_strategy_router.py
tests/test_dynamic_router_experiment.py
```

优先测试的退出方向：

```text
1. 更短 max_hold_bars
2. 更紧 trailing_atr
3. 更现实 take_profit_atr
4. 盈利后保本
5. 盈利后锁部分利润
6. time_exit 亏损后更强冷却
```

不要做大网格。每次只测一小族，保持可解释。

## 验收标准

### 第一阶段验收

必须至少满足：

```text
✅ trend_short pnl 从 -0.3578 改到 > 0
✅ end_equity >= 13.5609
✅ max_drawdown 不明显高于 17.98%，最好 <= 20%
✅ trades 明显高于 8
✅ transition_breakout_long 仍然为正
```

### 第二阶段验收

如果第一阶段通过，继续做：

```text
✅ 365 天完整回测
✅ 12 月拆分
✅ by_reason 拆解
✅ by_symbol 拆解
✅ router_rejections 拆解
✅ overfit_risk 检查
✅ 剔除 2026-05~2026-07 后重新计算收益
```

如果剔除 2026-05~07 后策略崩溃，则标记为过拟合，不准进入模拟盘。

## 必跑命令

### 365 天候选回测

```bash
python dynamic_router_experiment.py --reports reports/goal_30d_fullseed_40.json --limit 10 --rank-filter goal_30d_fullseed_40#7 --days 365 --mode trend_short_factor --start-equity 10 --out reports/dynamic_router_trend_short_factor_latest.json
```

### 中文验收

```bash
python dynamic_router_acceptance.py --router-report conservative=reports/dynamic_router_debug_latest.json --router-report trend_short_factor=reports/dynamic_router_trend_short_factor_latest.json --out reports/dynamic_router_acceptance_trend_short_factor_latest.json
```

### 明确测试清单

不要直接跑：

```bash
python -m unittest
```

原因：根目录有历史回测演示脚本会被 discovery 误导入执行，并可能改写报告。

使用：

```bash
python -m unittest tests.test_universe tests.test_window_config tests.test_dynamic_router_acceptance tests.test_dynamic_router_experiment tests.test_dynamic_strategy_router tests.test_strategy_adaptation_audit tests.test_historical_regime_validation tests.test_strategy_policy tests.test_overfit_report tests.test_monthly_goal tests.test_staged_goal tests.test_goal_search tests.test_validation tests.test_profit_max_search tests.test_transition_breakout_signal tests.test_trend_factor_audit
```

## 后续任务顺序

### ✅ Step 1：修 trend_short_factor 出场/风控

这是最接近收益提升的任务。

目标：

```text
把高胜率负收益修成高胜率正收益。
```

### Step 2：补齐统一历史数据

目标：

```text
所有核心币种尽量统一到 2024-01 至今。
补足 15m，尽量扩展 5m/1m。
同步补 funding/open_interest/trade_flow/order_book。
```

### Step 3：重新验证策略

验证对象：

```text
conservative
trend_short_factor
transition_breakout_long variants
range_revert with trend kill-switch
ML filter
```

验证方式：

```text
365 天
30+ 月 walk-forward
12 月拆分
剔除 2026-05~07
参数扰动
by_symbol
by_reason
```

### Step 4：range_revert 趋势熔断

只在纯震荡中启用。

禁止条件：

```text
EMA20/50/200 同向排列
ATR 扩张
Donchian 突破
连续贴布林带
```

### Step 5：trend_long 重构成回踩策略

不要整体启用 trend_long。

只研究：

```text
上涨趋势中的第一次回踩
EMA20/EMA50 附近反弹
RSI 不过热
成交量恢复
```

### Step 6：ML 过滤器

只允许：

```text
规则信号出现后，ML 判断是否过滤。
```

不允许：

```text
ML 裸开仓。
```

## 禁止事项

```text
❌ 不要继续盲目扩大 transition_breakout_long 参数网格
❌ 不要整体放开 trend_short
❌ 不要因为胜率高就启用 trend_short_factor
❌ 不要先继续调 XGBoost 参数
❌ 不要先接 FreqAI
❌ 不要只看总收益
❌ 不要只优化 30 天
❌ 不要把 2026-05~07 的收益当成普遍 edge
```

## 正确判断口径

Claude Code 后续回答和实现时，应使用这个判断：

```text
当前不是没有 edge。
当前是：
1. transition_breakout_long 有低频正收益 edge；
2. trend_short_factor 有方向边际，但交易管理失败；
3. ML 有过拟合风险，只能当过滤器；
4. 数据需要补齐，用于验证，不是替代策略修复。
```

## 最终目标

短期目标不是直接 2000U，而是先把系统推进到：

```text
一个稳定低频核心策略
+ 一个通过验证的高频辅助策略
+ 一个只做过滤的 ML 层
+ 一个严格动态路由/风控/过拟合验收框架
```

当前最近的突破口：

```text
trend_short_factor 独立出场/风控优化。
```

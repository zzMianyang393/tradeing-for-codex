# Claude Code 后续交接：动态路由 EA 打磨方向

更新时间：2026-07-09

## 当前总判断

当前项目已经从“单策略参数搜索”推进到“动态路由 + 抗过拟合验收 + 策略因子审计”的研究型 EA 原型阶段。

真实 365 天最稳基线仍然是保守路由：

```text
保守路由：
start_equity = 10
end_equity = 13.5609
return = 35.61%
max_drawdown = 17.98%
trades = 8
核心策略 = 转换突破做多
```

这个结果比早期 365 天亏损明显好，但还远远不够。现在的核心问题不是继续盲目扩大参数网格，而是：

1. 有效策略太少，当前只有“转换突破做多”真正站得住。
2. 交易次数太少，365 天只有 8 笔。
3. 被路由拦截的候选很多，尤其是趋势做空和趋势做多。
4. 趋势做空有高胜率迹象，但当前退出/盈亏比不合格。

## 已完成工作 ✅

### ✅ 1. 动态策略路由

已在 `backtester.py` 中接入动态路由：

- `router_allowed_reasons`
- `router_blocked_reasons`
- `router_reason_allowed_regimes`
- `_dynamic_router_rejection_reason()`
- `_dynamic_router_allows_signal()`

现在开仓前不只看策略 reason，还会看当前行情标签是否匹配。

### ✅ 2. 策略适用行情标签

已在 `dynamic_router_experiment.py` 中为 profile 输出中文行情适应标签：

```text
transition_breakout_long -> 趋势转换
trend_long -> 上涨趋势
trend_short -> 下跌趋势
range_revert_* -> 震荡区间
```

### ✅ 3. 中文验收报告

新增 `dynamic_router_acceptance.py`：

- 输出“可继续打磨 / 不建议实盘启用 / 可进入模拟盘观察”
- 检查是否达到目标
- 检查交易次数
- 检查最大回撤
- 检查是否包含弱适应策略
- 检查是否存在拖累策略

### ✅ 4. 跨窗口过拟合风险检查

`dynamic_router_acceptance.py` 已加入：

```python
evaluate_window_overfit_risk()
```

如果某个变体在 90/180 天预筛选盈利，但完整 365 天亏损，会标记：

```text
overfit_risk.risk_cn = 高
风险标记 = 跨窗口失效风险高
状态 = 不建议实盘启用
```

### ✅ 5. 路由拒绝统计

`Backtester.run()` 现在会输出：

```json
"router_rejections": {
  "total": 2546,
  "by_rejection_reason": {},
  "by_signal_reason": {},
  "by_regime": {}
}
```

真实 365 天保守路由统计：

```text
router 拒绝候选：2546
blocked_reason：1194
not_allowed_reason：1352

trend_short：1352
trend_long：977
range_revert_long：135
range_revert_short：80
transition_breakout_short：2
```

### ✅ 6. 中文路由拒绝审计摘要

`dynamic_router_acceptance.py` 已加入：

```python
summarize_router_rejections()
```

真实结论：

```text
趋势做空：1352 次，占 53.10%，优先审计
趋势做多：977 次，占 38.37%，优先审计
震荡反转做多：135 次，占 5.30%，观察
震荡反转做空：80 次，暂不处理
转换突破做空：2 次，暂不处理
```

### ✅ 7. 趋势策略因子审计

新增：

- `trend_factor_audit.py`
- `tests/test_trend_factor_audit.py`

审计维度：

```text
策略方向：趋势做多 / 趋势做空
趋势强度：强趋势 / 中趋势 / 弱趋势
成交量：放量 / 常量 / 缩量
RSI：中性 / 过热 / 过冷
均线距离：贴近均线 / 远离均线
```

第一批审计结论：

```text
趋势做空 | 强趋势 | 放量 | RSI中性 | 贴近均线

adaptive:
trades = 12
win_rate = 58.33%
pnl = +6.3383

sprint200u:
trades = 11
win_rate = 54.55%
pnl = +3.7878

动作：可候选复核
```

趋势做多当前不合格：

```text
趋势做多 | 强趋势 | 放量 | RSI中性 | 贴近均线

adaptive:
trades = 6
win_rate = 0%
pnl = -6.7887

sprint200u:
trades = 5
win_rate = 0%
pnl = -5.3824

动作：暂不启用
```

### ✅ 8. 趋势做空因子门控

已实现受控候选模式：

```text
mode = trend_short_factor
```

只允许：

```text
趋势做空 + 强趋势 + 放量 + RSI中性 + 贴近均线
```

并设置：

```text
trend_short risk multiplier = 0.35
```

配置字段在 `config.py`：

```python
router_trend_short_factor_gate_enabled
router_trend_short_min_trend_strength_abs
router_trend_short_min_volume_ratio
router_trend_short_rsi_min
router_trend_short_rsi_max
router_trend_short_max_ema20_distance_atr
router_trend_short_max_ema20_distance_pct
```

365 天候选回测：

```text
trend_short_factor:
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

transition_breakout_long:
trades = 8
wins = 3
pnl = +3.4560
```

结论：

```text
趋势做空方向不是完全没价值，因为胜率很高。
但当前退出、盈亏比、单笔亏损控制不合格。
不能启用，但值得继续打磨。
```

## 关键报告文件 ✅

```text
reports/dynamic_router_debug_latest.json
reports/dynamic_router_acceptance_debug_latest.json
reports/dynamic_router_trend_short_factor_latest.json
reports/dynamic_router_acceptance_trend_short_factor_latest.json
reports/trend_factor_audit_adaptive.json
reports/trend_factor_audit_sprint200u.json
reports/dynamic_router_transition_variants_v4.json
reports/dynamic_router_transition_prefilter_multi_v1.json
reports/dynamic_router_acceptance_latest.json
```

## 测试命令 ✅

不要直接使用：

```bash
python -m unittest
```

原因：根目录有两个历史回测演示脚本 `test*.py`，会被 unittest discovery 误导入执行，并可能改写报告。

使用这个明确测试清单：

```bash
python -m unittest tests.test_universe tests.test_window_config tests.test_dynamic_router_acceptance tests.test_dynamic_router_experiment tests.test_dynamic_strategy_router tests.test_strategy_adaptation_audit tests.test_historical_regime_validation tests.test_strategy_policy tests.test_overfit_report tests.test_monthly_goal tests.test_staged_goal tests.test_goal_search tests.test_validation tests.test_profit_max_search tests.test_transition_breakout_signal tests.test_trend_factor_audit
```

最近通过结果：

```text
Ran 122 tests in 0.120s
OK
```

## 当前工作区注意事项

有两个报告文件被 `python -m unittest` 误导入根目录回测脚本时改动：

```text
reports/adaptive.json
reports/sprint200u.json
```

不要在未确认前提交它们。它们更像运行副作用，不是本轮核心代码改动。

当前重要新增文件：

```text
dynamic_router_acceptance.py
trend_factor_audit.py
transition_cross_validation.py
tests/test_dynamic_router_acceptance.py
tests/test_trend_factor_audit.py
```

当前重要修改文件：

```text
backtester.py
config.py
dynamic_router_experiment.py
strategy.py
tests/test_dynamic_router_experiment.py
tests/test_dynamic_strategy_router.py
tests/test_transition_breakout_signal.py
```

## 后续方向

### 方向 1：先打磨 trend_short 的退出，而不是继续调入场 ✅下一步优先级最高

当前 `trend_short`：

```text
60 笔
胜率 71.67%
PnL -0.3578
```

这说明入场方向有一定边际，但盈亏比/退出不行。

Claude Code 下一步建议：

1. 给 `trend_short` 增加独立退出参数，不要影响其他策略。
2. 优先测试：
   - 更短 `max_hold_bars`
   - 更小 `take_profit_atr`
   - 更紧 `trailing_atr`
   - 盈利后更早移动止损
   - time_exit 亏损冷却加强
3. 每次只调一个小族，不要大网格。
4. 每个候选都必须输出：
   - 365 天结果
   - 12 月拆分
   - by_reason
   - max_drawdown
   - router_rejections
   - overfit_risk

### 方向 2：做 trend_short exit profile

推荐新增配置字段：

```python
trend_short_factor_stop_atr
trend_short_factor_take_profit_atr
trend_short_factor_trailing_atr
trend_short_factor_max_hold_bars
trend_short_factor_break_even_mfe_pct
trend_short_factor_break_even_lock_pct
```

实现位置：

```text
backtester.py
_stop_atr_for_signal()
_take_profit_atr_for_signal()
_exit_price()
```

注意：只在以下条件下生效：

```text
router_trend_short_factor_gate_enabled = True
sig.reason == "trend_short"
```

不要影响普通 `trend_short` 或其他策略。

### 方向 3：重新跑 365 天受控候选

命令：

```bash
python dynamic_router_experiment.py --reports reports/goal_30d_fullseed_40.json --limit 10 --rank-filter goal_30d_fullseed_40#7 --days 365 --mode trend_short_factor --start-equity 10 --out reports/dynamic_router_trend_short_factor_latest.json
```

验收：

```bash
python dynamic_router_acceptance.py --router-report conservative=reports/dynamic_router_debug_latest.json --router-report trend_short_factor=reports/dynamic_router_trend_short_factor_latest.json --out reports/dynamic_router_acceptance_trend_short_factor_latest.json
```

目标不是立刻达到 2000U，而是先满足：

```text
trend_short pnl > 0
end_equity > conservative baseline
max_drawdown 不明显升高
trades 明显增加
overfit_risk != 高
```

### 方向 4：12 个月拆分

一旦 365 天候选优于保守基线，必须做 12 月拆分。

需要回答：

```text
每个月收益多少？
每个月 trend_short 是否赚钱？
哪个月份拖累？
拖累月份是什么行情？
是不是某几个币种导致？
是不是某类退出导致？
```

不允许只看完整 365 天总收益。

### 方向 5：跨窗口与跨行情防过拟合

任何新候选都必须通过：

```text
90/180/365 多窗口
12 月拆分
相似历史行情窗口
参数扰动
by_symbol 拆解
by_reason 拆解
最大回撤约束
```

短窗口盈利但 365 天亏损，直接标为高过拟合风险。

## 不要做什么

不要继续盲目扩大 `transition_breakout_long` 参数网格。之前已经跑过 109 个变体，最优仍然是保守基线。

不要把 `trend_short` 整体放开。只能通过 `trend_short_factor` 门控放开候选子集。

不要因为胜率高就启用。当前 `trend_short` 胜率 71.67%，但 PnL 仍为负。

不要只优化 30 天。当前目标窗口以 365 天为准，12 个月拆分只是评估，不是月度 oracle。

不要把 `reports/adaptive.json` 和 `reports/sprint200u.json` 的误改动直接提交，除非确认这些报告确实需要更新。

## 推荐 Claude Code 第一项任务

实现 `trend_short_factor` 的独立退出 profile。

验收标准：

```text
✅ 单元测试覆盖新配置只影响 trend_short_factor
✅ trend_short 365 天 PnL 从 -0.3578 改到 > 0
✅ end_equity 至少不低于 13.5609
✅ max_drawdown 不高于保守基线太多，最好 <= 20%
✅ trades 维持在明显高于 8 笔
✅ 中文验收报告标记为“可继续打磨”或更好
✅ 12 月拆分后没有明显单月爆雷
```

## 当前核心结论

```text
转换突破做多 = 当前唯一强适应策略，但交易太少。
趋势做空因子 = 有方向边际，但退出和盈亏比不合格。
趋势做多 = 暂不启用。
下一步核心 = trend_short_factor 出场/风控优化，而不是继续扩大入场参数。
```

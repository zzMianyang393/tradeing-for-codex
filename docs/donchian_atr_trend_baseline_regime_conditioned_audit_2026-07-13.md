# Donchian + ATR 趋势基准：适配行情审计

日期：2026-07-13

## 方法

- 来源报告：`reports/donchian_atr_trend_baseline_audit.json`
- 新报告：`reports/donchian_atr_trend_baseline_regime_conditioned_audit.json`
- 不重跑策略、不改参数，只给既有事件补充入场时已完成 4h 行情标签。
- 声明适配行情：趋势策略只在方向匹配趋势中计入组合候选。
  - long + `趋势上行`
  - short + `趋势下行`

## 关键数字

| 区间 | 事件 | 净收益合计 | 均值 | 胜率 | PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| Formation 全部事件 | 228 | +643.433313% | +2.822076% | 50.00% | 1.557689 |
| Formation 声明适配 | 166 | +713.176780% | +4.296246% | 51.20% | 1.840958 |
| OOS 全部事件 | 232 | -136.828093% | -0.589776% | 37.93% | 0.899263 |
| OOS 声明适配 | 173 | -84.469873% | -0.488265% | 39.88% | 0.918870 |

## 判定

`regime_conditioned_rejected`。

这次审计支持用户提出的“要按适配行情看策略”，但 Donchian + ATR 即使只保留方向匹配趋势事件，OOS 仍然没有转正，且胜率低于 40%。因此它可以继续作为历史特征进入诊断矩阵，但不能升级为可组合交易腿。

安全状态不变：`approved_for_paper=[]`，`safe_to_enable_trading=false`，`ready_for_combo_backtest=false`。

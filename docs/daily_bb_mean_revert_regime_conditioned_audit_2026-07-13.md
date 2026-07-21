# 日线 BB 均值回归：适配行情审计

日期：2026-07-13

## 方法

- 来源报告：`reports/daily_bb_mean_revert_audit.json`
- 新报告：`reports/daily_bb_mean_revert_regime_conditioned_audit.json`
- 不重跑策略、不改参数，只给既有事件补充入场时已完成 4h 行情标签。
- 声明适配行情：均值回归只在 `震荡` 标签下计入组合候选。

## 关键数字

| 区间 | 事件 | 净收益合计 | 均值 | 胜率 | PF |
| --- | ---: | ---: | ---: | ---: | ---: |
| Formation 全部事件 | 13 | +13.473465% | +1.036420% | 53.85% | 1.364409 |
| Formation 震荡适配 | 4 | -7.746368% | -1.936592% | 50.00% | 0.381748 |
| OOS 全部事件 | 10 | +26.207653% | +2.620765% | 60.00% | 2.450099 |
| OOS 震荡适配 | 4 | +27.688358% | +6.922090% | 75.00% | 66.002707 |

## 判定

`regime_conditioned_rejected`。

OOS 震荡适配表现很好，但只有 4 笔；formation 震荡适配也是 4 笔且均值为负。这个结果不能作为组合方向腿，只能说明“震荡均值回归值得继续扩大原型池”，例如补充 RSI、KDJ、BIAS、箱体反弹等更多震荡原型。

安全状态不变：`approved_for_paper=[]`，`safe_to_enable_trading=false`，`ready_for_combo_backtest=false`。

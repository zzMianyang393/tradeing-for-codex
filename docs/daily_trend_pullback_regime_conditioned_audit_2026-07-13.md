# 日线趋势内回调：适配行情审计

日期：2026-07-13

## 方法

- 来源报告：`reports/daily_trend_pullback_audit.json`
- 新报告：`reports/daily_trend_pullback_regime_conditioned_audit.json`
- 只补入场时已完成 4h 行情标签，不改底层规则。
- 声明适配行情：long 只允许 `趋势上行`。

## 关键数字

| 区间 | 全部事件 | 全部净收益 | 上行趋势适配事件 | 适配净收益 | 适配均值 | 适配胜率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Formation | 12 | -12.845946% | 3 | -22.299790% | -7.433263% | 33.33% |
| OOS | 147 | -462.375363% | 18 | -6.771467% | -0.376193% | 77.78% |

## 判定

`regime_conditioned_rejected`。

上行趋势过滤明显减少了亏损规模，但 OOS 适配均值仍为负，formation 适配样本也只有 3 笔且为负。因此它不能作为趋势回调方向腿进入组合。

安全状态：`approved_for_paper=[]`，`safe_to_enable_trading=false`，`ready_for_combo_backtest=false`。

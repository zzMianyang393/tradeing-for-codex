# Directional Regime Event Inventory

Date: 2026-07-13

## Purpose

This is a read-only diagnostic inventory. It answers one question:

> For each directional weak-signal candidate, which completed-4h regime label actually contains its events and returns?

It is not a strategy approval, not a combo backtest, and not a paper-trading gate.

## Output

Machine-readable output:

- `reports/directional_regime_event_inventory.json`

## Key Findings

The inventory confirms that some rejected single strategies were partly rejected under the wrong semantic label.

Most important correction:

- `daily_rsi_mean_revert` has 0 useful events under the old `震荡` interpretation.
- The same fixed RSI rule has 59 formation events and 142 OOS events under `趋势下行`.
- Under `趋势下行`, formation net return is `+446.486403%`, mean `+7.567566%`, win rate `69.49%`.
- Under `趋势下行`, OOS net return is `+302.720049%`, mean `+2.131831%`, win rate `56.34%`.

This means the rule is better described as `下跌趋势超卖反弹`, not `震荡均值回归`.

Other useful descriptive results:

- `4h_ema_crossover`: best OOS regime is `趋势下行`, 24 events, net `+106.360395%`, mean `+4.431683%`, win rate `75.00%`.
- `daily_trend_pullback`: best OOS regime is `高波动转换`, 25 events, net `+37.391995%`, mean `+1.495680%`, win rate `64.00%`, but formation support is not sufficient.
- `donchian_atr_trend_baseline`: best OOS regime by mean is `震荡`, 38 events, net `+45.642945%`, mean `+1.201130%`, but win rate is only `36.84%`.
- `daily_bb_mean_revert`: no OOS regime reaches the minimum 10-event descriptive threshold.

## Safety Boundary

Best-regime selection is descriptive. It can identify a semantic mismatch, but it cannot by itself approve a strategy.

Any reclassified feature must remain:

- not standalone
- not paper-eligible
- gated by completed-4h regime labels
- subject to future-window validation

Current safety gates remain:

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

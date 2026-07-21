# 4h EMA Crossover Regime-Conditioned Audit

Date: 2026-07-13

## Purpose

This audit checks whether the failed naked `4h_ema_crossover` result is mainly caused by trading outside its compatible trend regimes.

Compatible regimes:

- `趋势上行`
- `趋势下行`

The regime label is taken from completed 4h candles and is only available after the candle closes.

## Output

Machine-readable output:

- `reports/ema_crossover_4h_regime_conditioned_audit.json`

## Result

Naked OOS result from the base audit:

- Events: 456
- Net sum: -579.996485%
- Mean net: -1.271922%
- Win rate: 36.4035%

OOS inside compatible trend regimes:

- Events: 35
- Net sum: +74.959351%
- Mean net: +2.141696%
- Median net: +3.084412%
- Win rate: 54.2857%
- Profit factor: 2.035458

OOS outside compatible trend regimes:

- Events: 421
- Net sum: -654.955836%
- Mean net: -1.555715%
- Median net: -3.959820%
- Win rate: 34.9169%
- Profit factor: 0.666542

OOS trend-regime direction split:

- Long in `趋势上行`: 11 events, net sum -31.401044%, mean -2.854640%, win rate 9.0909%
- Short in `趋势下行`: 24 events, net sum +106.360395%, mean +4.431683%, win rate 75.0000%

Formation caution:

- Formation compatible trend regimes: 28 events, net sum -75.186328%, mean -2.685226%, win rate 21.4286%
- Formation non-trend regimes: 372 events, net sum +771.733171%, mean +2.074552%, win rate 45.4301%

## Verdict

`regime_conditioned_candidate`.

The naked strategy failed OOS, but the OOS loss is concentrated outside compatible trend regimes. In OOS, compatible trend-regime events were positive. However, the formation-period trend-regime bucket was negative, so this should be treated as a conditional component candidate rather than an approved combo feature.

The most useful sub-signal appears to be short-side continuation in `趋势下行`, not long-side trend following.

## Safety

This is still research only:

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

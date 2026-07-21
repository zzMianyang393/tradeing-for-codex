# Downtrend Rebound Event-Time Filter Audit

Date: 2026-07-13

Research ID: `downtrend_rebound_event_time_filter_v1`

Scope: `read_only_event_time_diagnostic_not_executable_strategy`

## Result Table

| Hypothesis | Formation Events | Formation Mean | OOS Events | OOS Net | OOS Mean | OOS Win | Screen |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `H0_downtrend_rsi_baseline` | 59 | +7.567566% | 142 | +302.720049% | +2.131831% | 56.34% | blocked |
| `F1_prior_downtrend_streak_1_to_6` | 7 | +5.367963% | 6 | +53.971175% | +8.995196% | 83.33% | blocked |
| `F2_prior_downtrend_streak_ge_7` | 50 | +8.279584% | 136 | +248.748874% | +1.829036% | 55.15% | blocked |
| `F3_signal_rsi_below_25` | 0 | +0.000000% | 1 | +18.198531% | +18.198531% | 100.00% | blocked |
| `F4_signal_rsi_25_to_35` | 59 | +7.567566% | 141 | +284.521518% | +2.017883% | 56.03% | blocked |

## Screen Details

### H0_downtrend_rsi_baseline

- formation concentration 44.74% > 25%
- OOS concentration 28.35% > 25%

### F1_prior_downtrend_streak_1_to_6

- OOS events 6 < 20
- active months 5 < 6
- formation concentration 99.53% > 25%
- OOS concentration 67.84% > 25%

### F2_prior_downtrend_streak_ge_7

- formation concentration 44.99% > 25%
- OOS concentration 28.82% > 25%

### F3_signal_rsi_below_25

- formation net sum <= 0
- OOS events 1 < 20
- active months 1 < 6
- OOS concentration 100.00% > 25%
- formation mean excluding 2024-11 <= 0

### F4_signal_rsi_25_to_35

- formation concentration 44.74% > 25%
- OOS concentration 28.88% > 25%

## Interpretation

- The early downtrend streak bucket has strong observed OOS returns but only six OOS events, so it is an observation rather than evidence.
- The mature downtrend streak bucket preserves positive OOS return across 136 events, but it does not improve mean return over the unfiltered baseline in both windows.
- RSI below 25 is too rare in this frozen event set to support a separate component.
- RSI from 25 to 35 is effectively the original strategy population and does not solve concentration.
- None of the frozen filters advances. The source rebound effect remains a future-window research candidate only.

## Timing And Safety

- source events: 202
- downtrend events: 201
- complete event-time inputs: 201
- timing rule: 4h regime availability timestamp must be strictly earlier than entry timestamp
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

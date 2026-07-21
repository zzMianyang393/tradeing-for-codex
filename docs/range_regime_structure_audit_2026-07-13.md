# Range Regime Structure Audit

Date: 2026-07-13

This is a descriptive path audit, not a strategy backtest.

## Label Structure

- completed 4h labels: 124871
- range labels: 29259 (23.43%)
- range runs: 1646; mean 17.91 bars; median 14.00; max 101

| Horizon | Same Label | Prior-24h Continuation | BB Reversion | RSI Reversion |
| --- | ---: | ---: | ---: | ---: |
| 4h | 94.42% | +0.042352% (48.90%) | -0.152358% (49.49%) | -0.096775% (50.40%) |
| 12h | 85.73% | +0.070104% (49.87%) | -0.345188% (47.64%) | -0.269576% (50.47%) |
| 24h | 74.84% | +0.168540% (50.49%) | -0.644374% (46.83%) | -0.662983% (48.81%) |
| 72h | 46.20% | +0.247005% (50.37%) | -0.850661% (46.94%) | -0.718554% (45.91%) |

Positive values support the named path hypothesis; negative values contradict it. The gross cost reference is 0.16%.

## Safety

- no entry or exit rule was optimized
- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

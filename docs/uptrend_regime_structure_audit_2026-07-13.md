# Uptrend Regime Structure Audit

Date: 2026-07-13

This is a descriptive completed-label audit, not a strategy backtest.

## Aggregate Structure

- completed 4h labels: 124871
- uptrend labels: 31236 (25.01%)
- runs: 679; mean 46.00 bars; median 33.00; max 343

| Horizon | Same Label | Mean Forward Return | Median | Positive Rate |
| --- | ---: | ---: | ---: | ---: |
| 4h | 97.84% | +0.000181% | -0.024281% | 49.01% |
| 1d | 88.51% | -0.027895% | -0.285456% | 46.42% |
| 3d | 71.79% | -0.004639% | -0.538145% | 46.29% |
| 10d | 43.49% | +0.208512% | -2.685003% | 41.06% |

## Half-Year Drift

| Half-Year | Uptrend Share | 3d Mean | 10d Mean |
| --- | ---: | ---: | ---: |
| 2024-H1 | 43.45% | +0.657455% | +2.121641% |
| 2024-H2 | 40.69% | +1.456510% | +4.106485% |
| 2025-H1 | 17.57% | -2.126996% | -1.253313% |
| 2025-H2 | 23.04% | -0.161718% | -2.412747% |
| 2026-H1 | 18.41% | -0.959384% | -3.598489% |

## Diagnosis

- supports long context: `false`
- positive 3d half-years: 2/5
- positive 10d half-years: 2/5
- next action: `refine_uptrend_context_before_testing_more_long_entries`

Overlapping forward returns describe the label. They are not trade PnL and must not be read as an approval.

## Drift By Label Age

| Label Age | Observations | 3d Mean | 10d Mean |
| --- | ---: | ---: | ---: |
| `first_1d` | 3748 | -0.752920% | -1.899645% |
| `day_2_to_3` | 6027 | -0.106089% | -1.585173% |
| `day_4_to_10` | 12688 | -0.489468% | -0.270247% |
| `older_than_10d` | 8704 | +1.094570% | +3.045032% |

## Three-Day Drift By Age And Fold

| Label Age | 2024-H1 | 2024-H2 | 2025-H1 | 2025-H2 | 2026-H1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `first_1d` | -0.491156% | +0.877437% | -2.183863% | -1.355856% | -1.072267% |
| `day_2_to_3` | +1.090163% | +1.117864% | -2.707395% | +0.537283% | -0.158706% |
| `day_4_to_10` | -0.984096% | +0.640617% | -2.886679% | +0.361270% | -1.368498% |
| `older_than_10d` | +2.170798% | +2.735114% | +0.729124% | -0.932774% | -0.861793% |

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

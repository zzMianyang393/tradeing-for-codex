# Downtrend Bidirectional Future Validation

Date: 2026-07-13

Locked unseen window: `2025-07-11` to `2026-07-10`.

## Result

| Symbols | Candidates | Accepted | Rejected | Return | Max DD | Win | Avg Exposure | Month Concentration |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 28 | 344 | 86 | 258 | +0.039957% | 30.118000% | 47.67% | 31.98% | 31.41% |

## Component Attribution

| Component | Candidates | Accepted | Rejected | Return Contribution | Win |
| --- | ---: | ---: | ---: | ---: | ---: |
| `rsi_rebound_long` | 284 | 44 | 240 | -10.216043% | 47.73% |
| `ema_continuation_short` | 60 | 42 | 18 | +10.256000% | 47.62% |

## Decision

- future maximum drawdown 30.118000% > 20%
- rsi_rebound_long return contribution -10.216043% <= 0%
- positive-month concentration 31.41% > 25%

Validation status: `failed_locked_future_window`.

This result does not open trading gates. Portfolio approval requires a separate decision.

## Safety

- `approved_for_paper = []`
- `eligible_for_paper = false`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

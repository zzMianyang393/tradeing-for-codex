# Weekly Cross-Sectional Weakness: Post-Hoc Hypothesis Record

## Source Observation

The frozen `weekly_cross_sectional_momentum_v1` long-short portfolio was
rejected because its long sleeve lost `-56.723079%` contribution. Its short
sleeve was positive in all three observed half-year folds:

| Observed fold | Accepted shorts | Short-sleeve return | Top positive-month share |
| --- | ---: | ---: | ---: |
| 2025-H1 | 75 | +26.103813% | 24.42% |
| 2025-H2 | 75 | +24.881677% | 31.84% |
| 2026-H1 | 78 | +17.416807% | 32.45% |

Across the observed window it recorded 234 accepted short positions, `+76.810624%`
return, `14.4341%` maximum drawdown, and `11.11%` aggregate positive-month
concentration.

## Why This Is Not A Historical Approval

The short sleeve was selected after inspecting a rejected two-sided portfolio.
That makes a retrospective short-only backtest a post-hoc selection exercise.
Additionally, two individual folds exceed the 25% concentration threshold.
It is therefore not added to the feature pool, combination preflight, Cohort B,
or any paper/live path.

## Permitted Future Action

If this hypothesis is activated, it must be isolated as a new future-only
exploration cohort, separate from existing Cohort C. The new cohort must freeze:

- the 28-day relative-return ranking and Monday 00:00 UTC schedule;
- the weakest-three short selection, seven-day maximum holding period, 2 ATR
  stop, and 0.16% round-trip friction assumptions;
- an activation boundary strictly after the then-current data cutoff;
- metadata-only signal collection and a sealed outcome protocol.

No historical outcome may be added after activation, no threshold may be tuned,
and the exploration cannot open paper or live-trading gates.

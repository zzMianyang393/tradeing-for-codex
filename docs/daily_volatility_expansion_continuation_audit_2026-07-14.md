# Daily Volatility Expansion Continuation Audit

Frozen rule: completed daily true range at least 1.80 times prior ATR(20); close in the top quartile emits long and bottom quartile emits short; only the completed-4h `高波动转换` label is eligible. Entry convention is four hours after the next daily open, with 0.16% round-trip friction and a seven-day maximum horizon.

The 28-symbol audit separates every mechanical trigger from the regime-compatible subset. Only the compatible subset decides the research verdict.

| Split | All triggers | Compatible events | Compatible net sum | Compatible mean | Win rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Formation | 176 | 32 | +67.838252% | +2.119945% | 62.50% |
| OOS | 141 | 23 | +55.224030% | +2.401045% | 52.17% |

Formation positive-return contribution from 2024-11 is 35.61%. Removing that month leaves a positive formation net sum of +22.425575% and a +0.830577% mean; therefore the card's frozen “concentrated and turns non-positive without 2024-11” rejection condition is not triggered.

Verdict: `historical_research_candidate`. This only establishes that the fixed historical rule cleared its own formation/OOS gate. Before any future observational generator is enabled, the project still needs a non-backfill activation boundary, generator tests, and the promised semantic-overlap audit against the volume-shock short feature. No position, paper eligibility, or trading approval is created by this result.

# Regime-Aware Frozen Factor Roundup

This note consolidates the latest reruns of frozen price-based factors under
the standard 28-symbol universe. Every rule used its declared completed regime
label; a trend rule was not judged on range entries, and a range rule was not
judged on trend entries.

| Family | Frozen rule | Formation | OOS | Result |
| --- | --- | --- | --- | --- |
| Trend | KAMA crossover | 81 events, +2.3679% mean | 116 events, -1.4586% mean | `historical_rejected` |
| Trend | Regression-channel breakout | 115 events, +2.9477% mean | 151 events, -3.4314% mean | `historical_rejected` |
| Range | RSI percentile reversion | 1 event | 6 events | `insufficient_evidence` |
| Range | BIAS reversion | 1 event | 0 events | `insufficient_evidence` |
| Range | Z-score reversion | 10 events, +1.5641% mean | 7 events, +2.4521% mean | `insufficient_evidence` |

## What The Evidence Says

1. Regime matching is necessary but not sufficient. The two trend rules were
   only evaluated in declared trend labels and had adequate event counts, yet
   both produced negative OOS average net returns.
2. Sparse range triggers are not evidence of a usable range sleeve. The three
   range rules do not meet the 15-event minimum in one or both windows, even
   where their tiny samples are positive.
3. Formation concentration remains material. KAMA and regression-channel
   positive-return month concentration was respectively 64.36% / 34.39% and
   75.29% / 43.49% across formation/OOS, above the 25% research threshold.

## Research Consequence

No rule in this round becomes a standalone strategy or a directional combo
feature. The outcome narrows the next hypothesis space: future work should
seek distinct, adequately frequent regime-conditioned information rather than
retuning these fixed price-trigger definitions. All paper and live-trading
gates remain closed.

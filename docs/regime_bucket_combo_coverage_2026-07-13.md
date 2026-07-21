# Regime Bucket Combo Coverage

Date: 2026-07-13

## Purpose

This report changes the combo question from:

- "Can all directional weak signals be active together?"

to:

- "Inside each completed-4h regime bucket, which weak-signal subsets have enough overlapping months for a future combo research card?"

It is a coverage diagnostic only. It is not a combo backtest.

## Output

Machine-readable output:

- `reports/regime_bucket_combo_coverage.json`

## Thresholds

For a regime bucket to become a future research-card candidate:

- at least 2 directional features in the bucket
- at least 6 active months in the bucket
- at least one feature pair with 4 or more common active months

These are preflight coverage thresholds, not profitability thresholds.

## Results

Source directional events: `631`.

Regime buckets found: `3`.

Preflight candidate buckets: `2`.

### 趋势下行

Status: `preflight_candidate`

- features: `3`
- active months: `16`
- viable feature pairs: `3`

Feature coverage:

| Feature | Active Months | Net Sum | Positive Months | Negative Months |
| --- | ---: | ---: | ---: | ---: |
| `feat_daily_rsi_mean_revert` | 15 | `+749.206452%` | 12 | 3 |
| `feat_4h_ema_crossover` | 8 | `+83.197129%` | 6 | 2 |
| `feat_donchian_atr_trend_baseline` | 15 | `-244.245997%` | 5 | 10 |

Best overlap:

| Pair | Common Months |
| --- | ---: |
| `feat_daily_rsi_mean_revert` + `feat_donchian_atr_trend_baseline` | 14 |
| `feat_4h_ema_crossover` + `feat_daily_rsi_mean_revert` | 8 |
| `feat_4h_ema_crossover` + `feat_donchian_atr_trend_baseline` | 7 |

Interpretation:

The best next research card is not a generic combo. It should be a `趋势下行` bucket study around RSI downtrend rebound, with Donchian and 4h EMA used as competing weak signals or veto/context features. Donchian's negative net sum in this bucket is a warning: it may be more useful as an opposing-state feature than as a long/short vote.

### 趋势上行

Status: `preflight_candidate`

- features: `3`
- active months: `15`
- viable feature pairs: `3`

Feature coverage:

| Feature | Active Months | Net Sum | Positive Months | Negative Months |
| --- | ---: | ---: | ---: | ---: |
| `feat_donchian_atr_trend_baseline` | 13 | `+872.952904%` | 5 | 8 |
| `feat_daily_trend_pullback` | 10 | `-29.071257%` | 6 | 4 |
| `feat_4h_ema_crossover` | 9 | `-72.931225%` | 1 | 8 |

Best overlap:

| Pair | Common Months |
| --- | ---: |
| `feat_4h_ema_crossover` + `feat_donchian_atr_trend_baseline` | 8 |
| `feat_daily_trend_pullback` + `feat_donchian_atr_trend_baseline` | 8 |
| `feat_4h_ema_crossover` + `feat_daily_trend_pullback` | 5 |

Interpretation:

This bucket has enough coverage, but only Donchian has positive net sum. The next step here should be a defensive trend-bucket study, not an immediate multi-signal vote.

### 震荡

Status: `coverage_insufficient`

- features: `1`
- active months: `5`
- viable feature pairs: `0`

Only `feat_daily_bb_mean_revert` appears in this bucket. A true range-market combo needs at least one additional range-compatible feature before combination research is justified.

## Decision

The old all-feature matrix gate should remain closed:

- `ready_for_combo_hypothesis_test = false`

But the next useful work is now clearer:

1. Write a pre-registered research card for the `趋势下行` bucket.
2. Treat RSI downtrend rebound as the primary candidate.
3. Treat Donchian and 4h EMA as diagnostic comparators first, not automatic voters.
4. Add at least one more range-compatible candidate before revisiting the `震荡` bucket.

## Safety Gates

The report keeps:

- `approved_for_paper = []`
- `safe_to_enable_trading = false`
- `ready_for_combo_backtest = false`

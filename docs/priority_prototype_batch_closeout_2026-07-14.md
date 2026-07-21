# Priority Prototype Batch Closeout

This closes the structural preflight batch of 13 low-turnover, single-leg prototype ideas. “Audited” means a frozen rule was evaluated on the 28-symbol universe with the 2024 formation and 2025-01-01 to 2025-07-10 OOS split. It does not confer paper or trading eligibility.

| Prototype | Status | Evidence |
| --- | --- | --- |
| TF_06 KAMA trend | `historical_rejected` | 81 formation / 116 OOS events; OOS mean is negative. |
| TF_08 SuperTrend | `historical_rejected` | 75 / 48 events; formation mean -0.33%, OOS mean -4.74%, and both month concentration checks fail. |
| TF_09 regression channel | `historical_rejected` | 115 / 151 events; formation mean +2.95%, OOS mean -3.43%. |
| MR_03 RSI percentile reversion | `insufficient_evidence` | 1 / 6 events. |
| MR_06 BIAS reversion | `insufficient_evidence` | 1 / 0 events. |
| MR_07 Z-score reversion | `insufficient_evidence` | 10 / 7 events. |
| MR_14 BTC-confirmed alt momentum | `historical_rejected` | 159 / 99 events; OOS mean -2.84%. |
| VS_06 Parkinson extreme reversion | `insufficient_evidence` | 45 / 11 events; both observed means are negative, but OOS does not meet the 15-event minimum. |
| TS_02 weekend reversion | `insufficient_evidence` | 0 / 1 events. |
| TS_07 month-boundary flow | `insufficient_evidence` | 74 / 13 events; OOS is negative but below the 15-event minimum. |

Two prototypes are not counted as current full-universe audits:

- `MR_02` has an older BTC/ETH-only report: 13 formation and 10 OOS events, with an OOS positive-return month concentration of 63.49%. It remains rejected as historical evidence, but is not a 28-symbol result.
- `VS_05` has an observation-only volatility-transition study, not a frozen directional research card and performance audit.

`MR_09` (Demux) has no sufficiently specified mathematical indicator or trigger/exit definition in the prototype source. It is `requires_specification`, rather than being backtested with an invented rule.

All reports retain `approved_for_paper=[]`, `eligible_for_paper=false`, and `safe_to_enable_trading=false`. The next productive work is not to add parameter variants of these rules; it is to preserve the prospective cohorts and define only genuinely new, fully specified mechanisms.

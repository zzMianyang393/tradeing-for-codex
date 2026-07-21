# Daily SuperTrend Audit

Frozen rule: daily SuperTrend ATR(10), multiplier 3; long flips only in completed 4h `趋势上行`, short flips only in completed 4h `趋势下行`; entry delayed four hours; 2 ATR(14) hard stop; opposite flip or ten-day exit; 0.16% round-trip cost.

Universe: the 28 frozen eligible OKX perpetual symbols. Formation is 2024-01-01 through 2024-12-31; OOS is 2025-01-01 through 2025-07-10.

| Split | Events | Net sum | Mean per event | Win rate | Positive-return month concentration |
| --- | ---: | ---: | ---: | ---: | ---: |
| Formation | 75 | -24.736301% | -0.329817% | 46.67% | 31.43% |
| OOS | 48 | -227.655260% | -4.742818% | 33.33% | 30.25% |

Verdict: `historical_rejected`. Both samples have sufficient event counts, but both have negative net mean after the fixed cost. Positive-return monthly concentration also exceeds the frozen 25% ceiling in both splits. This result does not alter any prospective cohort, feature pool, or trading gate.

The machine-readable record is `reports/daily_supertrend_audit.json`; its safety gates remain closed.

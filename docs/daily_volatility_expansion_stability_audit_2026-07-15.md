# Daily Volatility Expansion Stability Audit

This is a read-only, descriptive audit of the already frozen
`daily_volatility_expansion_continuation_v1` compatible-event subset. It does
not alter that card's parameters, historical status, or prospective protocol.

## Cross-symbol result

The compatible sample contains 32 formation and 23 OOS events. It is not
dominated by one symbol:

| Split | Leading positive symbol | Positive contribution | Leave-one-symbol-out positive net result |
| --- | --- | ---: | ---: |
| Formation | TIA-USDT-SWAP | 27.77% | descriptive only |
| OOS | LTC-USDT-SWAP | 25.21% | 15 of 15 symbol removals |

In OOS, removing even the most positive symbol (LTC) leaves +15.129052% over
21 events. This is evidence against single-symbol dependence, not evidence of
approval.

## Direction and month risk

OOS direction attribution is sharply asymmetric:

| Direction | Events | Net sum | Mean |
| --- | ---: | ---: | ---: |
| Long | 12 | -45.788892% | -3.815741% |
| Short | 11 | +101.012922% | +9.182993% |

The strongest OOS positive month is 2025-04, contributing 50.31% of positive
monthly return. This is a material direction and time concentration risk.

The frozen card did not include either a symbol or direction concentration gate;
it only rejects a formation result if 2024-11 exceeds 25% and removing that
month makes the result non-positive. Therefore this observation must not be
used to retrofit a new historical rule or to promote the short sleeve. Any
future short-only hypothesis needs a new pre-registered card and a new,
non-backfilled prospective observation period.

All safety gates remain closed.

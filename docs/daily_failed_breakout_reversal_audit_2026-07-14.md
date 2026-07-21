# Daily Failed Breakout Reversal Audit

Frozen rule: the completed daily high must exceed the prior 20 completed daily highs by at least 0.25 ATR(20), close back below that prior channel high, and retain an upper wick of at least 40% of the daily range. It emits only a short observation in completed-4h `高波动转换`; evaluation uses a four-hour availability delay, 1.5 ATR(20) stop, 0.16% round-trip cost, and five-day horizon.

Across all 28 symbols the mechanical pattern is not rare: 97 formation and 42 OOS triggers. Its required compatible subset is rare: only 1 formation and 2 OOS events. The compatible formation event returned -9.715284% net; the two OOS events sum to +2.845789%.

Verdict: `insufficient_evidence`. The rule cannot be enabled as a directional weak-signal generator, because neither split approaches the frozen minimum of 15 compatible events. The all-signal figures are descriptive only and do not override the regime contract.

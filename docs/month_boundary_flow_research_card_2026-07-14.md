# Month-Boundary Flow Proxy: Research Card

Status: `eligible_for_research`, not a trading candidate.

- data: completed UTC daily OHLCV, single perpetual market only;
- timing: observe only on the final two UTC daily closes of a calendar month;
- direction condition: close above EMA20 and 5-day rate of change is positive;
- direction: long at the following UTC daily open; one observation per symbol per calendar month;
- compatible regime: `趋势上行` only, from the last completed 4h label;
- exit: first close below EMA20, or 5 days; hard stop 2 ATR(14);
- friction: 0.16% round trip; no macro/event feed, funding, OI, or dynamic allocation.

Historical contract: formation `2024-01-01` to `2024-12-31`; OOS `2025-01-01` to `2025-07-10`; >=15 compatible events per window, positive net mean per window, and <=25% positive-return contribution from any month. No month-end window, EMA, ROC, stop, or horizon sweep.

The rule is an OHLCV calendar proxy, not a claim about unobserved institutional flows. Only a signal-only generator may be built after this audit; paper eligibility remains false.

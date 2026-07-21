# 10U Single-Symbol Event Trend 48h — Frozen Research Card v1

Status: `preregistered_before_formation_performance`

This candidate is a single-position execution branch of the existing volatility-expansion continuation hypothesis. It is not an independent alpha claim, an approved strategy, or a paper/live trading authorization.

## User objective

- trade one coin at a time, with no more than three coins in the research universe;
- target a directional event that persists for roughly one to two days;
- tolerate intrabar stop sweeps without permitting liquidation or unlimited loss;
- retain a material part of a large winner instead of using a fixed 3R exit;
- use an isolated 10 USDT account and never top it up from the main account.

The frozen universe is `RAVE-USDT-SWAP`, `LAB-USDT-SWAP`, and `ETH-USDT-SWAP`. ETH is a liquid control rather than an assumption that it will produce warlord-level returns.

## Contamination boundary

The completed 1h paths from `2026-05-16T00:00:00Z` through `2026-07-16T00:00:00Z` were inspected before this card was frozen. That interval is permanently `contaminated_case_only`: it may illustrate path shape, but it may not validate the rule, count toward OOS, choose a parameter, or rescue a failed primary specification.

True prospective OOS begins at `2026-07-16T00:00:00Z`. Its outcomes remain sealed until the Formation and retrospective-validation gates have passed and a separately frozen maturity rule has been satisfied.

## Frozen causal rule

1. Aggregate completed UTC 1h candles into completed UTC 4h candles.
2. On a completed 4h bar, compare true range and quote volume with the medians of the preceding 20 completed 4h bars; the trigger bar is excluded from both baselines.
3. Both ratios must be at least 2.0. A long trigger must close in the top quartile and break the prior 20-bar high; a short trigger must close in the bottom quartile and break the prior 20-bar low.
4. Do not chase the trigger close. During the next 12 completed 1h bars, require at least one counter-direction close. Cancel the setup if a completed close crosses the ignition midpoint against the intended direction.
5. Resume long when a completed 1h close exceeds the preceding 1h high; resume short when it closes below the preceding 1h low. Enter only at the next 1h open.
6. The pullback extreme is the structural invalidation level. Normal exit is close-confirmed; a wick alone does not trigger it.
7. A remote disaster stop sits another 0.5 Wilder ATR(14) beyond structural invalidation. Wilder ATR is seeded by a 14-bar simple mean and then updated recursively. Skip a setup whose disaster distance exceeds 20% of entry.
8. After 12 hours, a completed 4h close beyond the preceding completed 4h extreme against the position exits at the next 1h open. There is no fixed take profit.
9. Time exit occurs after 48 hours. Only one position may be open across the three symbols.

If a hard stop and another exit are both possible inside an OHLC bar, the hard stop is assumed first. No lower-timeframe reconstruction may be invented.

## Capital, execution, and funding

- initial equity: 10 USDT;
- risk budget: 15% of current equity per accepted event;
- effective leverage cap: 3x, with actual notional determined by disaster-stop distance;
- taker fee: 0.05% each side;
- slippage: 0.02% each side;
- actual historical funding is mandatory for every settlement crossed by a 24–48h position;
- no top-up, martingale, grid, averaging down, or simultaneous positions.

Signals occurring while a position is open are discarded, not queued. Simultaneous entry proposals are ranked by the smaller of their true-range and quote-volume ratios, descending, then by symbol; the first proposal that is executable after stop-distance and contract-step checks is selected. Three consecutive losses trigger a 24-hour cooldown; a 35% UTC-day loss halts new entries until the next day; 70% peak drawdown or equity at/below 2 USDT permanently halts the sleeve.

## Frozen Formation and anti-overfit gate

Formation is `2025-12-15T16:00:00Z` through `2026-04-01T00:00:00Z`. Retrospective validation is sealed at first and spans `2026-04-01T00:00:00Z` through `2026-05-16T00:00:00Z`.

The primary must independently satisfy all of the following:

- at least 12 trades, including at least two RAVE and two LAB trades;
- ending equity at least 10 USDT and peak equity at least 15 USDT;
- profit factor at least 1.25;
- maximum drawdown no greater than 70%;
- retain at least 50% of peak accumulated profit at the end of Formation;
- no more than 35% of stopped trades recover by at least 1R in the original direction shortly afterward;
- median winning-trade capture ratio at least 35% of its available favorable excursion;
- the largest trade contributes no more than 50% of gross positive PnL.

Two sensitivity runs are frozen before performance: a coupled 2.2/2.2 ignition threshold and a 16-hour pullback-wait variant. They are diagnostics only. If the 2.0/2.0, 12-hour primary fails, neither variant may be promoted or used to alter the primary.

No threshold grid, coin removal, direction removal, date adjustment, or post-result rule addition is permitted in v1.

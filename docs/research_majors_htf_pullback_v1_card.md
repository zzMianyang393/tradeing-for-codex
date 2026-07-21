# Research Card: majors HTF pullback v1

**Date:** 2026-07-17  
**Strategy ID:** `prod_majors_htf_pullback_v1`  
**Status:** pre-registered research candidate (not default paper runtime)

## 1. Hypothesis

| Item | Content |
|------|---------|
| Profit source | Continuation after shallow pullbacks in an established uptrend on liquid majors |
| Why not covered by donchian sleeve | Donchian breakout chases expansion; this waits for mean-touch of EMA20 then reclaim |
| Universe | **BTC-USDT-SWAP, ETH-USDT-SWAP only** (production-bound) |
| Capital | **10 USDT default**; sensitivity 100/500 if needed; max 500 |
| Timeframe | 15m features; HTF slope via ema50 vs ema50[16] (~4h) |

## 2. Frozen default rule (no grid search)

**Long only, one position.**

Entry (all must hold):

1. `ema20 > ema50` (optional min gap = 0 for this card)
2. `close > ema50`
3. `ema50 > ema50[16]` (rising intermediate trend)
4. Within last 4 bars, some bar `low <= ema20 * 1.001` (pullback touch)
5. Current bar: `prev.close <= prev.ema20` and `close > ema20` (reclaim)

Exit / risk (from `htf_pullback_majors_config`):

- risk_per_trade 0.08, max_margin 0.45, lev ≤ 4  
- stop 2.2 ATR, TP 2.5 ATR, trail 2.0 ATR  
- max hold 64 bars (~16h)  
- costs: taker 5bps + slip 2bps one-way  

## 3. Failure modes

- Chop / range: repeated EMA touches without trend → stops  
- Gap / news bars: 15m pullback signals late  
- 10U min notional: may skip small sizes (report skip rate via trade count)

## 4. Success criteria (research)

- Not required to beat donchian to be “interesting”; must report 10U net after costs  
- Prefer fewer trades than raw breakout with better PF or lower max DD  
- **Does not** authorize demo/live; server-only later  

## 5. Commands

```bash
python -m prod.cli research-htf-pullback
# writes reports/prod/research_htf_pullback_v1.json
```

## 6. Result (2026-07-17 full sample)

| Sleeve | Trades | 10U end | Return | PF | Max DD |
|--------|-------:|--------:|-------:|---:|------:|
| **htf_pullback v1** | 387 | ~3.61 | **-63.9%** | 0.68 | 65.1% |
| baseline donchian | 367 | ~3.27 | -67.3% | 0.72 | (see report) |

Capital sensitivity (same rule): 10/100/500 scale almost linearly — edge not a min-notional artifact.

**Decision:** `research_insufficient_or_weak`  
**Reasons:** non-positive 10U return; PF < 1  

**Action:**  
- **Do not** admit to paper-prep as alpha  
- **Do not** grid-search parameters on this shell  
- Keep as negative evidence; next research must change profit-source structure (e.g. short side in downtrend, or lower turnover filter), not re-tune this pullback
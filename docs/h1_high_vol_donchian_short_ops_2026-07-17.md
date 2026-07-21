# h1_high_vol_donchian_short — capital ladder + hourly paper (2026-07-17)

**Strategy:** `prod_majors_h1_high_vol_donchian_short_v1`  
**Status:** paper_prep (local only)

## Capital sensitivity (10 / 100 / 500)

**Command:**
```bash
python -m prod.cli majors-capital-sensitivity \
  --strategy-id prod_majors_h1_high_vol_donchian_short_v1 \
  --out reports/prod/h1_high_vol_donchian_short_capital_sensitivity.json
```

| Equity | Trades | Return | PF | Max DD | Ending | State |
|-------:|-------:|-------:|---:|-------:|-------:|-------|
| **10** | 233 | **+68.3%** | 1.214 | 32.9% | 16.83 | active |
| 100 | 233 | +68.3% | 1.214 | 32.9% | 168.35 | active |
| 500 | 233 | +68.3% | 1.214 | 32.9% | 841.75 | active |

**Read:** Ladder is **scale-invariant** (same return/PF/DD). No min-notional distortion between 10 and 500. Keep **10U as operating baseline**; 100/500 are contrast only. Ceiling remains 500.

`formal_status=ok`, `places_exchange_orders=false`.

## Hourly job (refresh + paper)

```bash
python -m prod.cli majors-hourly \
  --strategy-id prod_majors_h1_high_vol_donchian_short_v1 \
  --state reports/prod/h1_high_vol_donchian_short_paper_state.json \
  --cycle-out reports/prod/h1_high_vol_donchian_short_paper_cycle.json \
  --lock reports/prod/h1_high_vol_donchian_short_runtime.lock \
  --out reports/prod/h1_high_vol_donchian_short_hourly_job.json \
  --commit-refresh
```

| Field | Value |
|-------|-------|
| formal_status | ok |
| 1h refresh | ok (0 new bars; already current) |
| paper | ok · equity 10 · no open · no_new_entry |
| completed_cycles | 2 |
| closed_trades | 0 |
| places_exchange_orders | **false** |
| local_graduation | not_yet (need 20 trades / 30 cycles) |

Windows Task: `scripts/prod_majors_h1_high_vol_hourly.ps1`

## Ops decision

| Action | Decision |
|--------|----------|
| Keep paper_prep | **Yes** |
| Prefer start equity | **10U** |
| Demo/live | **No** (server later; after paper history) |
| Retune | **No** |

## Next

1. Run hourly on a schedule to accumulate paper history.  
2. Do not enable demo until local graduation thresholds + separate promotion.  
3. Optional: watchlist only for h4 high-vol (not admitted).

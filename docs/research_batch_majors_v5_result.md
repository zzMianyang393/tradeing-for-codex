# Majors research batch v5 (1h) + paper-prep decision

**Date:** 2026-07-17  
**Command:** `python -m prod.cli research-batch-majors-v5`  
**OOS:** `reports/prod/research_h1_interesting_oos_v1.json`

## Ranking (10U, BTC/ETH 1h, costs)

| Name | Fund filter | Trades | Return | PF | DD | Full decision |
|------|-------------|-------:|-------:|---:|---:|---------------|
| h1_md_mom_short_fundneg | funding&lt;0 | 36 | +36.8% | 1.65 | 18% | interesting → **OOS fail** |
| **h1_md_mom_short** | none | 101 | **+32.4%** | **1.25** | 26% | **paper-prep recommended** |
| **h1_dual_md_mom_short** | none | 41 | +5.9% | 1.12 | 19% | paper-prep recommended (thin OOS) |
| h1_md_mom_short_fundpos | funding&gt;0 | 57 | +1.8% | 1.03 | 30% | conditional (formation fail) |
| others | — | — | negative | — | — | rejected |

## OOS (formation 60% / embargo 24h / OOS rest)

| Name | Formation | OOS | Decision |
|------|-----------|-----|----------|
| h1_md_mom_short_fundneg | +112% PF10.7 | **−7.1%** | **reject** (funding filter overfit risk) |
| **h1_md_mom_short** | +85.5% PF2.22 | **+2.8% PF1.06** | **PASS all gates** |
| h1_dual_md_mom_short | +52.5% PF3.28 | **+0.08% PF1.00** | PASS but OOS ~flat |
| h1_md_mom_short_fundpos | −1.9% | +3.3% | conditional |

## Paper-prep action taken (superseded)

**Originally admitted (local paper only):** `prod_majors_h1_md_mom_short_v1`  

**REVOKED 2026-07-17:** corrupt ETH 1h timestamps inflated common-ts edge. Clean aligned data → full-sample **negative**. See `docs/research_h1_data_integrity_revoke_2026-07-17.md`. Registry status **rejected**.

```bash
python -m prod.cli paper-cycle-majors \
  --strategy-id prod_majors_h1_md_mom_short_v1 \
  --state reports/prod/h1_md_mom_short_paper_state.json \
  --cycle-out reports/prod/h1_md_mom_short_paper_cycle.json
```

- Registry: `paper_prep`, `live_allowed=false`  
- Evidence: batch v5 + OOS JSON + `reports/prod/h1_md_mom_short_admission.json`  
- **Not** demo/live; server-later only  
- Do **not** retune parameters  

Dual short left on watchlist (OOS too thin for primary sleeve).

## Ops path (local paper, 2026-07-17 continued)

1h sleeve now has timeframe-aware hourly job (refresh OKX `1H` → paper):

```bash
python -m prod.cli majors-hourly \
  --strategy-id prod_majors_h1_md_mom_short_v1 \
  --state reports/prod/h1_md_mom_short_paper_state.json \
  --cycle-out reports/prod/h1_md_mom_short_paper_cycle.json \
  --lock reports/prod/h1_md_mom_short_runtime.lock \
  --out reports/prod/h1_md_mom_short_hourly_job.json \
  --commit-refresh
```

- Separate state/lock from 15m donchian primary.  
- `places_exchange_orders=false`; not demo/live.  
- Script: `scripts/prod_majors_h1_hourly.ps1`

## Notes

- BTC 1h history downloaded for dual coverage (public OKX `1H`).  
- Funding negative filter looked best full-sample but **failed OOS** — do not use as primary.  
 

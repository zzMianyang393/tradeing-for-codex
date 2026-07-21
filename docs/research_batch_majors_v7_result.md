# Majors research batch v7 + gates + admission

**Date:** 2026-07-17  
**Theme:** structural families — vol regime / session / failed-break / relative / dual  
**Data:** clean BTC/ETH 15m + 1h + 4h, 10U, costs on

## Commands

```bash
python -m prod.cli research-batch-majors-v7
python -m prod.cli research-v7-gates --batch-report reports/prod/research_batch_majors_v7.json
```

## Full-sample interesting (selected)

| Name | TF | Trades | Return | PF | DD |
|------|----|-------:|-------:|---:|---:|
| **h1_high_vol_donchian_short** | 1h | 233 | **+68.3%** | 1.21 | 33% |
| h4_weekly_mom_short_recheck | 4h | 63 | +22.3% | 1.22 | 25% |
| h4_high_vol_donchian_short | 4h | 78 | +10.7% | 1.07 | 28% |
| m15_failed_breakout_short | 15m | 30 | +6.6% | 1.54 | 3% |
| h1_failed_breakout_short | 1h | 18 | +4.9% | 1.34 | 9% |
| m15_failed_breakdown_long | 15m | 19 | +2.9% | 1.31 | 4% |

Most 15m session/BB/outside/high-vol long variants failed hard (costs + over-trading).

## Multiwindow gates (strict)

Bar: full pass, OOS ≥2/3, **formation ≥2/3**, trades ≥20, full ret ≥5%, PF ≥1.05.

| Name | OOS | Form | Years | Admit? |
|------|-----|------|-------|--------|
| **h1_high_vol_donchian_short** | **3/3** | **3/3** | 2024/25/26 all + | **YES** |
| h4_high_vol_donchian_short | 3/3 | 1/3 | 2024− 2025− 2026+ | **NO** (recent-only) |
| h4_weekly_mom_short_recheck | 3/3 | 0/3 | known regime split | NO |
| m15_failed_breakout_short | 0/3 | 3/3 | — | NO (OOS fail) |

### h1_high_vol_donchian_short windows

| Form frac | Form ret | OOS ret | OOS PF |
|----------:|---------:|--------:|-------:|
| 0.50 | +28.8% | +30.7% | 1.25 |
| 0.60 | +15.9% | +45.2% | 1.40 |
| 0.70 | +7.8% | +56.1% | 1.59 |

Calendar years: 2024 +15.9%, 2025 +8.9%, 2026 +33.4% (all positive).

## Paper-prep action

**Admitted (local paper only):** `prod_majors_h1_high_vol_donchian_short_v1`

```bash
python -m prod.cli majors-hourly \
  --strategy-id prod_majors_h1_high_vol_donchian_short_v1 \
  --state reports/prod/h1_high_vol_donchian_short_paper_state.json \
  --cycle-out reports/prod/h1_high_vol_donchian_short_paper_cycle.json \
  --lock reports/prod/h1_high_vol_donchian_short_runtime.lock \
  --out reports/prod/h1_high_vol_donchian_short_hourly_job.json \
  --commit-refresh
```

- Registry: `paper_prep`, `live_allowed=false`  
- Evidence: batch v7 + gates + `reports/prod/h1_high_vol_donchian_short_admission.json`  
- Rule: `high_vol_donchian_short` on 1h (ATR% rank ≥0.70 + donchian short)  
- **Do not retune**  
- Demo/live still server-later only  
- Windows: `scripts/prod_majors_h1_high_vol_hourly.ps1`

### Post-admission ops (same day)

- Capital ladder 10/100/500: **scale-invariant** (+68.3% / PF 1.21 / DD 33% all rungs).  
  Report: `reports/prod/h1_high_vol_donchian_short_capital_sensitivity.json`  
- Hourly paper job: **ok**, `places_exchange_orders=false`, cycles=2, no entry yet.  
  Details: `docs/h1_high_vol_donchian_short_ops_2026-07-17.md`

### Not admitted

- **h4_high_vol_donchian_short** — OOS strong but formation mostly negative; 2024–25 years red  
- failed-breakout family — formation ok / OOS weak or thin sample  
- weekly 4h — unchanged regime artifact  

## Context vs prior sleeves

| ID | Status |
|----|--------|
| `prod_majors_donchian_atr_long_v1` | suspended (15m health −67%) |
| `prod_majors_h1_md_mom_short_v1` | rejected (data integrity) |
| **`prod_majors_h1_high_vol_donchian_short_v1`** | **paper_prep** |

## Notes

- NY-session + md_mom produced **0 trades** (session vs day-boundary mismatch) — hypothesis closed.  
- Gate tightened post-hoc: formation pass requires ≥2/3 windows.  
- Still not alpha claim for live; need paper history before any demo consideration.

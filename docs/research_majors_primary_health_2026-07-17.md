# Majors 15m primary health check (2026-07-17)

**Command:** `python -m prod.cli research-majors-primary-health`  
**Evidence:** `reports/prod/research_majors_primary_health_v1.json`

## Result

| Sleeve | Trades | Full ret | PF | Max DD | OOS pass | Form pass | Action |
|--------|-------:|---------:|---:|-------:|---------:|----------:|--------|
| **primary donchian long** | 367 | **−67.3%** | 0.72 | **70% halt** | 0/3 | 0/3 | **suspend paper_prep** |
| conservative donchian long | 457 | −52.4% | 0.70 | 54% | 0/3 | 0/3 | compare-only (not runtime) |

Primary permanent state: `peak_drawdown_halt`, ending equity ≈ **3.27 U** from 10U.

Capital ladder still engineers OK (policy 10/100/500) — that does **not** mean alpha is valid.

## Registry

`prod_majors_donchian_atr_long_v1` → **`suspended`**

- Local `paper-cycle-majors` / `majors-hourly` for this id → **blocked**
- Demo/live never authorized
- Original admission was infrastructure fingerprint, not proven edge

## Implication

**There is currently no active production-bound majors paper_prep alpha.**

| ID | Status |
|----|--------|
| `prod_majors_donchian_atr_long_v1` | suspended |
| `prod_majors_h1_md_mom_short_v1` | rejected |
| ten_u RAVE/LAB | local_experiment only (not graduation path) |

Ops may still refresh public BTC/ETH data; do not run paper cycles for suspended/rejected ids without `--force` (debug only).

## Next research (no retune of failed rules)

1. New frozen families / structural filters (v7) on clean 15m/1h/4h  
2. Keep `h4_weekly_mom_short` watchlist only (regime: 2024− / 2025–26+)  
3. Demo/live still server-only and **blocked** until a real edge graduates local paper

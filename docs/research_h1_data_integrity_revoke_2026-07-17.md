# H1 admission revoked — data integrity (2026-07-17)

## Finding

`prod_majors_h1_md_mom_short_v1` was admitted to **local paper_prep** after batch v5 + single 60/40 OOS on a market where **ETH 1h timestamps were corrupt** (truncated numeric cells, not UTC strings). That limited BTC/ETH common-timeline bars (~4k) and produced a **false positive** edge.

After clean public OKX `1H` redownload (BTC/ETH both ~21.6k bars, aligned through 2026-07-17 09:00):

| Sleeve | Full ret | Full PF | Trades | Multiwindow |
|--------|---------:|--------:|-------:|-------------|
| h1_md_mom_short | **−46.7%** | 0.81 | 307 | formation fail all splits; OOS modest + only at 60/70 |
| h1_dual_md_mom_short | **−11.8%** | 0.93 | 186 | drop from primary path |

Evidence: `reports/prod/research_h1_multiwindow_oos_v1.json`.

## Action

| Item | Status |
|------|--------|
| Registry `prod_majors_h1_md_mom_short_v1` | **rejected** (revoked) |
| Local paper for this id | **blocked** (`is_paper_allowed` false) |
| Demo/live | Never was; remains closed |
| Dual 1h short | Not admitted; **drop primary path** |

## Lessons

1. Prefer quantify **UTC string** timestamps for 1h/4h CSVs; reject truncated numeric dumps.
2. Multi-window OOS + full-sample check **after** data hygiene, before admission.
3. Common-timestamp length collapsing vs single-name history is a red flag.

## Next

Continue research on clean 1h/4h (batch v6). Do not re-admit without clean-data gates.

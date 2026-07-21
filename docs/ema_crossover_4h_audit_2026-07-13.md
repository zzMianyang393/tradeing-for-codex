# 4h EMA Crossover Audit

Date: 2026-07-13

## Rule

- EMA20/EMA50 on completed 4h bars.
- Long on EMA20 crossing above EMA50.
- Short on EMA20 crossing below EMA50.
- Enter next 15m open.
- Exit on opposite 4h cross or 5-day max hold.
- Round-trip cost: 0.16%.

## Result

Formation period: 2024-01-01 to 2024-12-31

- Events: 400
- Net sum: +696.546843%
- Mean net: +1.741367%
- Median net: -1.234109%
- Win rate: 43.75%
- Profit factor: 1.594755
- Long events: 181, mean +3.510651%, win rate 49.7238%
- Short events: 219, mean +0.279082%, win rate 38.8128%

Formation excluding 2024-11:

- Kept events: 354
- Net sum: +349.650099%
- Mean net: +0.987712%
- Median net: -1.340894%
- Win rate: 42.9379%
- Profit factor: 1.344014

Excluded 2024-11:

- Events: 46
- Net sum: +346.896744%
- Mean net: +7.541234%
- Win rate: 50.00%
- Profit factor: 3.241428

OOS period: 2025-01-01 to 2025-07-10

- Events: 456
- Net sum: -579.996485%
- Mean net: -1.271922%
- Median net: -3.371748%
- Win rate: 36.4035%
- Profit factor: 0.715203
- Long events: 282, mean -1.946809%, win rate 31.9149%
- Short events: 174, mean -0.178140%, win rate 43.6782%

## Verdict

Rejected.

Reasons:

- Formation win rate 43.75% is below 45%.
- Formation excluding 2024-11 win rate 42.9379% is below 45%.
- Top month event concentration 25.25% is above the 25% cap.
- OOS performance is negative: -579.996485% net sum, -1.271922% mean net.

## Combo Reuse

This audit does not provide a clean third directional weak signal for the combo matrix. It may be kept as a failed trend-family diagnostic, but it should not be promoted into the current directional feature pool.

Machine-readable report:

- `reports/ema_crossover_4h_audit.json`

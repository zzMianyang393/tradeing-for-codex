"""Audit whether external funding history can be used as an OKX research proxy."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from funding_rate import load_funding_rates


EIGHT_HOURS_MS = 8 * 60 * 60 * 1000


def load_binance_rates(path: Path) -> dict[int, float]:
    rates: dict[int, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                rates[int(row["timestamp_ms"]) // EIGHT_HOURS_MS] = float(row["funding_rate"])
            except (KeyError, TypeError, ValueError):
                continue
    return rates


def pearson(values_a: list[float], values_b: list[float]) -> float:
    if len(values_a) < 2:
        return 0.0
    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    numerator = sum((a - mean_a) * (b - mean_b) for a, b in zip(values_a, values_b))
    denominator = math.sqrt(
        sum((a - mean_a) ** 2 for a in values_a) * sum((b - mean_b) ** 2 for b in values_b)
    )
    return numerator / denominator if denominator else 0.0


def audit_proxy(okx_path: Path, binance_path: Path) -> dict[str, float | int | bool]:
    okx = {rate.ts // EIGHT_HOURS_MS: rate.funding_rate for rate in load_funding_rates(okx_path)}
    binance = load_binance_rates(binance_path)
    shared = sorted(set(okx) & set(binance))
    okx_values = [okx[key] for key in shared]
    binance_values = [binance[key] for key in shared]
    sign_agreement = (
        sum((a >= 0) == (b >= 0) for a, b in zip(okx_values, binance_values)) / len(shared)
        if shared else 0.0
    )
    correlation = pearson(okx_values, binance_values)
    return {
        "okx_rows": len(okx),
        "binance_rows": len(binance),
        "overlap_rows": len(shared),
        "pearson_correlation": round(correlation, 4),
        "sign_agreement": round(sign_agreement, 4),
        "proxy_alignment_passed": len(shared) >= 90 and correlation >= 0.6 and sign_agreement >= 0.7,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Binance funding as an OKX research proxy.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH"])
    parser.add_argument("--out", type=Path, default=Path("reports/funding_proxy_audit.json"))
    args = parser.parse_args(argv)

    result = {}
    passed = True
    for symbol in args.symbols:
        audit = audit_proxy(
            args.data / f"{symbol}-USDT-SWAP_funding.csv",
            args.data / "external" / f"{symbol}USDT_binance_funding.csv",
        )
        result[symbol] = audit
        passed = passed and bool(audit["proxy_alignment_passed"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from market import FeatureBar


OKX_FUNDING_HISTORY_URL = "https://www.okx.com/api/v5/public/funding-rate-history"


@dataclass(frozen=True, slots=True)
class FundingRate:
    symbol: str
    ts: int
    time: str
    funding_rate: float
    realized_rate: float


@dataclass(slots=True)
class FundingFeatureBar(FeatureBar):
    funding_rate: float = 0.0
    funding_realized_rate: float = 0.0
    funding_rate_ma: float = 0.0


def fetch_funding_page(symbol: str, before: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
    params = {"instId": symbol, "limit": str(limit)}
    if before is not None:
        params["before"] = str(before)
    url = f"{OKX_FUNDING_HISTORY_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "tradering-research/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "0":
        raise RuntimeError(f"OKX funding error for {symbol}: {payload}")
    return payload.get("data", [])


def parse_funding_rows(rows: list[dict[str, Any]]) -> list[FundingRate]:
    parsed: list[FundingRate] = []
    for row in rows:
        try:
            ts = int(row["fundingTime"])
            parsed.append(
                FundingRate(
                    symbol=str(row["instId"]),
                    ts=ts,
                    time=_format_utc(ts),
                    funding_rate=float(row.get("fundingRate") or 0.0),
                    realized_rate=float(row.get("realizedRate") or row.get("fundingRate") or 0.0),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    parsed.sort(key=lambda item: item.ts)
    return parsed


def save_funding_rates(path: Path, rates: list[FundingRate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["symbol", "timestamp_ms", "timestamp_utc", "funding_rate", "realized_rate"])
        for rate in rates:
            writer.writerow([rate.symbol, rate.ts, rate.time, rate.funding_rate, rate.realized_rate])


def load_funding_rates(path: Path) -> list[FundingRate]:
    if not path.exists():
        return []
    rates: list[FundingRate] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                rates.append(
                    FundingRate(
                        symbol=row["symbol"],
                        ts=int(row["timestamp_ms"]),
                        time=row["timestamp_utc"],
                        funding_rate=float(row["funding_rate"]),
                        realized_rate=float(row["realized_rate"]),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    rates.sort(key=lambda item: item.ts)
    return rates


def add_funding_features(bars: list[FeatureBar], rates: list[FundingRate], ma_window: int = 7) -> list[FundingFeatureBar]:
    ordered_rates = sorted(rates, key=lambda item: item.ts)
    out: list[FundingFeatureBar] = []
    rate_idx = 0
    latest_rate = 0.0
    latest_realized_rate = 0.0
    seen_rates: list[float] = []

    for bar in bars:
        while rate_idx < len(ordered_rates) and ordered_rates[rate_idx].ts <= bar.ts:
            latest_rate = ordered_rates[rate_idx].funding_rate
            latest_realized_rate = ordered_rates[rate_idx].realized_rate
            seen_rates.append(latest_rate)
            rate_idx += 1
        recent = seen_rates[-ma_window:]
        funding_rate_ma = sum(recent) / len(recent) if recent else 0.0
        out.append(
            FundingFeatureBar(
                **{field.name: getattr(bar, field.name) for field in fields(FeatureBar)},
                funding_rate=latest_rate,
                funding_realized_rate=latest_realized_rate,
                funding_rate_ma=funding_rate_ma,
            )
        )
    return out


def funding_output_path(symbol: str, out_dir: Path) -> Path:
    return out_dir / f"{symbol}_funding.csv"


def _format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

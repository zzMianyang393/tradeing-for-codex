from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class Bar:
    ts: int
    time: str
    open: float
    high: float
    low: float
    close: float
    volume_quote: float


@dataclass(slots=True)
class FeatureBar(Bar):
    ema20: float = 0.0
    ema50: float = 0.0
    ema200: float = 0.0
    atr: float = 0.0
    atr_pct: float = 0.0
    rsi: float = 50.0
    bb_mid: float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    vol_sma: float = 0.0
    donchian_high: float = 0.0
    donchian_low: float = 0.0
    trend_strength: float = 0.0


def discover_symbols(data_dir: Path) -> list[str]:
    okx_symbols = [path.name.removesuffix("_1m.csv") for path in data_dir.glob("*-USDT-SWAP_1m.csv")]
    quantify_symbols = []
    for suffix in ("5m", "15m", "1h", "4h", "1d"):
        quantify_symbols.extend(
            f"{path.name.removesuffix(f'_{suffix}.csv')}-USDT-SWAP"
            for path in data_dir.glob(f"*_{suffix}.csv")
        )
    return sorted(set(okx_symbols + quantify_symbols))


def load_1m_csv(path: Path) -> list[Bar]:
    bars: list[Bar] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                bars.append(
                    Bar(
                        ts=int(row["timestamp_ms"]),
                        time=row["timestamp_utc"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume_quote=float(row.get("volume_quote") or 0.0),
                    )
                )
            except (KeyError, ValueError):
                continue
    bars.sort(key=lambda bar: bar.ts)
    return bars


def load_quantify_15m_csv(path: Path) -> list[Bar]:
    bars: list[Bar] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                ts = _parse_timestamp(row["timestamp"])
                close = float(row["close"])
                volume_base = float(row.get("volume") or 0.0)
                bars.append(
                    Bar(
                        ts=ts,
                        time=_format_utc(ts),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=close,
                        volume_quote=volume_base * close,
                    )
                )
            except (KeyError, ValueError):
                continue
    bars.sort(key=lambda bar: bar.ts)
    return bars


def load_quantify_csv(path: Path) -> list[Bar]:
    return load_quantify_15m_csv(path)


def _format_utc(ts: int) -> str:
    return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_timestamp(value: str) -> int:
    stripped = value.strip()
    if stripped.isdigit():
        return _normalize_timestamp(int(stripped))
    parsed = datetime.strptime(stripped, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _normalize_timestamp(ts: int) -> int:
    if ts < 10_000_000:
        return ts * 1_000_000
    if ts < 10_000_000_000:
        return ts * 1_000
    return ts


def resample_minutes(bars: list[Bar], minutes: int) -> list[Bar]:
    if not bars:
        return []
    bucket_ms = minutes * 60_000
    out: list[Bar] = []
    cur_bucket = bars[0].ts // bucket_ms
    cur_open = bars[0].open
    cur_high = bars[0].high
    cur_low = bars[0].low
    cur_close = bars[0].close
    cur_vol = bars[0].volume_quote
    cur_ts = bars[0].ts
    cur_time = bars[0].time
    for bar in bars[1:]:
        bucket = bar.ts // bucket_ms
        if bucket != cur_bucket:
            out.append(Bar(cur_ts, cur_time, cur_open, cur_high, cur_low, cur_close, cur_vol))
            cur_bucket = bucket
            cur_open = bar.open
            cur_high = bar.high
            cur_low = bar.low
            cur_vol = bar.volume_quote
            cur_ts = bar.ts
            cur_time = bar.time
        else:
            cur_high = max(cur_high, bar.high)
            cur_low = min(cur_low, bar.low)
            cur_vol += bar.volume_quote
        cur_close = bar.close
    out.append(Bar(cur_ts, cur_time, cur_open, cur_high, cur_low, cur_close, cur_vol))
    return out


def _ema(prev: float, value: float, period: int) -> float:
    alpha = 2.0 / (period + 1.0)
    return value if prev == 0.0 else prev + alpha * (value - prev)


def add_features(bars: list[Bar]) -> list[FeatureBar]:
    closes: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    vols: list[float] = []
    out: list[FeatureBar] = []
    ema20 = ema50 = ema200 = atr = avg_gain = avg_loss = 0.0
    prev_close = bars[0].close if bars else 0.0

    for idx, bar in enumerate(bars):
        closes.append(bar.close)
        highs.append(bar.high)
        lows.append(bar.low)
        vols.append(bar.volume_quote)
        ema20 = _ema(ema20, bar.close, 20)
        ema50 = _ema(ema50, bar.close, 50)
        ema200 = _ema(ema200, bar.close, 200)

        tr = max(bar.high - bar.low, abs(bar.high - prev_close), abs(bar.low - prev_close))
        atr = tr if idx == 0 else (atr * 13.0 + tr) / 14.0

        change = bar.close - prev_close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        if idx == 0:
            avg_gain = gain
            avg_loss = loss
        else:
            avg_gain = (avg_gain * 13.0 + gain) / 14.0
            avg_loss = (avg_loss * 13.0 + loss) / 14.0
        rs = avg_gain / avg_loss if avg_loss > 0 else 99.0
        rsi = 100.0 - (100.0 / (1.0 + rs))

        start20 = max(0, len(closes) - 20)
        last20 = closes[start20:]
        bb_mid = sum(last20) / len(last20)
        variance = sum((value - bb_mid) ** 2 for value in last20) / len(last20)
        bb_std = math.sqrt(variance)
        vol_sma = sum(vols[start20:]) / len(vols[start20:])
        start55 = max(0, len(closes) - 55)
        don_high = max(highs[start55:])
        don_low = min(lows[start55:])
        atr_pct = atr / bar.close if bar.close else 0.0
        trend_strength = (ema20 - ema200) / (atr if atr else bar.close * 0.01)

        out.append(
            FeatureBar(
                ts=bar.ts,
                time=bar.time,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume_quote=bar.volume_quote,
                ema20=ema20,
                ema50=ema50,
                ema200=ema200,
                atr=atr,
                atr_pct=atr_pct,
                rsi=rsi,
                bb_mid=bb_mid,
                bb_upper=bb_mid + 2.0 * bb_std,
                bb_lower=bb_mid - 2.0 * bb_std,
                vol_sma=vol_sma,
                donchian_high=don_high,
                donchian_low=don_low,
                trend_strength=trend_strength,
            )
        )
        prev_close = bar.close
    return out


def load_market(
    data_dir: Path,
    timeframe_minutes: int,
    include_funding: bool = False,
    include_open_interest: bool = False,
    include_trade_flow: bool = False,
    include_order_book: bool = False,
    symbols: set[str] | None = None,
) -> dict[str, list[FeatureBar]]:
    market: dict[str, list[FeatureBar]] = {}
    for symbol in discover_symbols(data_dir):
        if symbols is not None and symbol not in symbols:
            continue
        okx_path = data_dir / f"{symbol}_1m.csv"
        base_symbol = symbol.removesuffix("-USDT-SWAP")
        timeframe_suffix = {
            5: "5m",
            15: "15m",
            60: "1h",
            240: "4h",
            1440: "1d",
        }.get(timeframe_minutes)
        quantify_path = data_dir / f"{base_symbol}_{timeframe_suffix}.csv" if timeframe_suffix else None
        if quantify_path and quantify_path.exists():
            bars = load_quantify_csv(quantify_path)
        elif okx_path.exists():
            bars_1m = load_1m_csv(okx_path)
            bars = resample_minutes(bars_1m, timeframe_minutes)
        else:
            continue
        features = add_features(bars)
        if include_funding:
            from funding_rate import add_funding_features, funding_output_path, load_funding_rates

            funding_path = funding_output_path(symbol, data_dir)
            if funding_path.exists():
                features = add_funding_features(features, load_funding_rates(funding_path))
        if include_open_interest:
            from open_interest import add_open_interest_features, load_open_interest, open_interest_output_path

            open_interest_path = open_interest_output_path(symbol, data_dir)
            if open_interest_path.exists():
                features = add_open_interest_features(features, load_open_interest(open_interest_path))
        if include_trade_flow:
            from trade_flow import add_trade_flow_features, load_trade_ticks, trade_ticks_output_path

            trade_ticks_path = trade_ticks_output_path(symbol, data_dir)
            if trade_ticks_path.exists():
                features = add_trade_flow_features(features, load_trade_ticks(trade_ticks_path))
        if include_order_book:
            from order_book import add_order_book_features, load_order_book_snapshots, order_book_output_path

            order_book_path = order_book_output_path(symbol, data_dir)
            if order_book_path.exists():
                features = add_order_book_features(features, load_order_book_snapshots(order_book_path))
        if features:
            market[symbol] = features
    return market

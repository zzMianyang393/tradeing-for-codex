from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from config import BacktestConfig
from market import FeatureBar, load_market
from strategy_adaptation_audit import translate_reason


def _volume_ratio(bar: FeatureBar) -> float:
    return bar.volume_quote / bar.vol_sma if bar.vol_sma > 0 else 1.0


def _trend_strength_tag(bar: FeatureBar, direction: int) -> str:
    strength = bar.trend_strength * direction
    if strength >= 2.0:
        return "强趋势"
    if strength >= 1.2:
        return "中趋势"
    return "弱趋势"


def _volume_tag(bar: FeatureBar) -> str:
    ratio = _volume_ratio(bar)
    if ratio >= 1.35:
        return "放量"
    if ratio >= 0.9:
        return "常量"
    return "缩量"


def _rsi_tag(bar: FeatureBar, direction: int) -> str:
    if direction > 0:
        if bar.rsi < 46:
            return "RSI偏低"
        if bar.rsi <= 65:
            return "RSI中性"
        return "RSI过热"
    if bar.rsi > 54:
        return "RSI偏高"
    if bar.rsi >= 35:
        return "RSI中性"
    return "RSI过冷"


def _ema_distance_tag(bar: FeatureBar) -> str:
    if not bar.close:
        return "未知均线距离"
    distance = abs(bar.close / bar.ema20 - 1.0) if bar.ema20 else 0.0
    if distance > max(bar.atr_pct * 1.8, 0.025):
        return "远离均线"
    return "贴近均线"


def trend_factor_tags(bar: FeatureBar, direction: int) -> tuple[str, ...]:
    return (
        _trend_strength_tag(bar, direction),
        _volume_tag(bar),
        _rsi_tag(bar, direction),
        _ema_distance_tag(bar),
    )


def _market_index(market: dict[str, list[FeatureBar]]) -> dict[str, dict[str, FeatureBar]]:
    return {symbol: {bar.time: bar for bar in bars} for symbol, bars in market.items()}


def _direction_for_reason(reason: str) -> int:
    return -1 if reason.endswith("_short") else 1


def _iter_trades(report: dict[str, Any]) -> list[dict[str, Any]]:
    trades = list(report.get("trades_detail") or [])
    for window in (report.get("windows") or {}).values():
        trades.extend(window.get("trades_detail") or [])
    return trades


def _action_for_bucket(trades: int, pnl: float, win_rate: float, min_trades: int) -> str:
    if trades < min_trades:
        return "样本不足"
    if pnl > 0 and win_rate >= 0.5:
        return "可候选复核"
    return "暂不启用"


def audit_trend_factor_buckets(
    report: dict[str, Any],
    market: dict[str, list[FeatureBar]],
    *,
    min_trades: int = 5,
) -> dict[str, Any]:
    index = _market_index(market)
    buckets: dict[str, dict[str, Any]] = {}
    total_trend_trades = 0
    missed_entries = 0
    for trade in _iter_trades(report):
        reason = str(trade.get("reason", ""))
        if reason not in {"trend_long", "trend_short"}:
            continue
        total_trend_trades += 1
        bar = index.get(str(trade.get("symbol", "")), {}).get(str(trade.get("entry_time", "")))
        if bar is None:
            missed_entries += 1
            continue
        factor_key = "|".join((translate_reason(reason),) + trend_factor_tags(bar, _direction_for_reason(reason)))
        row = buckets.setdefault(
            factor_key,
            {
                "factor_key": factor_key,
                "reasons": {},
                "trades": 0,
                "wins": 0,
                "pnl": 0.0,
                "symbols": {},
            },
        )
        row["trades"] += 1
        row["wins"] += 1 if trade.get("win") else 0
        row["pnl"] += float(trade.get("pnl", 0.0) or 0.0)
        row["reasons"][reason] = row["reasons"].get(reason, 0) + 1
        symbol = str(trade.get("symbol", ""))
        row["symbols"][symbol] = row["symbols"].get(symbol, 0) + 1

    rows = []
    for row in buckets.values():
        trades = int(row["trades"])
        wins = int(row["wins"])
        pnl = round(float(row["pnl"]), 4)
        win_rate = wins / trades if trades else 0.0
        rows.append(
            {
                "factor_key": row["factor_key"],
                "trades": trades,
                "wins": wins,
                "pnl": pnl,
                "win_rate": round(win_rate, 4),
                "avg_pnl": round(pnl / trades, 4) if trades else 0.0,
                "reasons_cn": {translate_reason(reason): count for reason, count in row["reasons"].items()},
                "symbols": row["symbols"],
                "action_cn": _action_for_bucket(trades, pnl, win_rate, min_trades),
            }
        )
    rows.sort(
        key=lambda item: (
            {"可候选复核": 2, "样本不足": 1, "暂不启用": 0}[item["action_cn"]],
            item["pnl"],
            item["win_rate"],
            item["trades"],
        ),
        reverse=True,
    )
    return {
        "total_trend_trades": total_trend_trades,
        "matched_trend_trades": total_trend_trades - missed_entries,
        "missed_entries": missed_entries,
        "min_trades": min_trades,
        "buckets": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit trend strategy trades by interpretable factor buckets.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--min-trades", type=int, default=5)
    parser.add_argument("--out", type=Path, default=Path("reports/trend_factor_audit.json"))
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    config_payload = report.get("config") or {}
    timeframe = int(config_payload.get("timeframe_minutes", BacktestConfig().timeframe_minutes))
    market = load_market(args.data, timeframe)
    audit = audit_trend_factor_buckets(report, market, min_trades=args.min_trades)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    for row in audit["buckets"][:10]:
        print(
            f"{row['factor_key']} | {row['action_cn']} | trades={row['trades']} "
            f"win={row['win_rate'] * 100:.2f}% pnl={row['pnl']:.4f} avg={row['avg_pnl']:.4f}"
        )


if __name__ == "__main__":
    main()

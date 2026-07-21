"""Formation-only statistical-arbitrage pair discovery.

The module deliberately separates discovery from trading: it evaluates a fixed
symbol universe on a formation panel, controls false discoveries across all
pairs, and writes candidate diagnostics.  It does not backtest the same data.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from market import discover_symbols
from pairs_walk_forward import FormationStats, formation_stats


@dataclass(frozen=True)
class PairDiscovery:
    statistics: FormationStats
    fdr_accepted: bool
    eligible: bool


def benjamini_hochberg(pvalues: dict[str, float], q: float, total_hypotheses: int | None = None) -> set[str]:
    """Return discoveries controlled at false-discovery rate ``q``."""
    valid = sorted((pvalue, key) for key, pvalue in pvalues.items() if np.isfinite(pvalue))
    threshold_index = -1
    total = total_hypotheses or len(valid)
    for index, (pvalue, _key) in enumerate(valid, start=1):
        if pvalue <= q * index / total:
            threshold_index = index
    return {key for _pvalue, key in valid[:threshold_index]} if threshold_index > 0 else set()


def load_close_panel(data_dir: Path, symbols: list[str], min_rows: int = 0) -> pd.DataFrame:
    panel: pd.DataFrame | None = None
    for symbol in symbols:
        base = symbol.removesuffix("-USDT-SWAP")
        path = data_dir / f"{base}_15m.csv"
        if not path.exists():
            continue
        frame = pd.read_csv(path, usecols=lambda column: column in {"timestamp", "close"})
        if not {"timestamp", "close"}.issubset(frame.columns):
            continue
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame = frame.set_index("timestamp").rename(columns={"close": symbol})
        if len(frame) < min_rows:
            continue
        panel = frame if panel is None else panel.join(frame, how="inner")
    return pd.DataFrame() if panel is None else panel.sort_index()


def discover_from_panel(
    panel: pd.DataFrame,
    formation_bars: int,
    fdr_q: float,
    max_half_life_bars: float,
    max_coint_tests: int = 32,
) -> list[PairDiscovery]:
    if len(panel) < formation_bars:
        raise ValueError(f"panel has {len(panel)} rows, requires {formation_bars}")
    formation = panel.iloc[-formation_bars:]
    all_pairs = list(itertools.combinations(formation.columns, 2))
    returns = np.log(formation.astype(float)).diff().dropna()
    ranked_pairs = sorted(
        all_pairs,
        key=lambda pair: abs(float(returns[pair[0]].corr(returns[pair[1]]))),
        reverse=True,
    )
    raw: list[FormationStats] = []
    for left, right in ranked_pairs[:max_coint_tests]:
        pair = f"{left.removesuffix('-USDT-SWAP')}-{right.removesuffix('-USDT-SWAP')}"
        raw.append(formation_stats(pair, formation[[left, right]].rename(columns={left: pair.split('-')[0], right: pair.split('-')[1]})))
    accepted_fdr = benjamini_hochberg(
        {item.pair: item.coint_pvalue for item in raw},
        fdr_q,
        total_hypotheses=len(all_pairs),
    )
    return [
        PairDiscovery(
            statistics=item,
            fdr_accepted=item.pair in accepted_fdr,
            eligible=item.pair in accepted_fdr and item.half_life_bars <= max_half_life_bars,
        )
        for item in sorted(raw, key=lambda item: item.coint_pvalue)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover pair candidates from formation data only.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--symbols", default="", help="Comma-separated fixed universe; default loads all eligible local symbols.")
    parser.add_argument("--formation-bars", type=int, default=96 * 180)
    parser.add_argument("--fdr-q", type=float, default=0.05)
    parser.add_argument("--max-half-life-bars", type=float, default=96 * 14)
    parser.add_argument("--max-coint-tests", type=int, default=32, help="Expensive ADF/cointegration tests after return-correlation prefilter.")
    parser.add_argument("--out", type=Path, default=Path("reports/pairs_discovery.json"))
    args = parser.parse_args(argv)
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()] or discover_symbols(args.data)
    panel = load_close_panel(args.data, symbols, min_rows=args.formation_bars)
    discoveries = discover_from_panel(
        panel, args.formation_bars, args.fdr_q, args.max_half_life_bars, args.max_coint_tests,
    )
    payload = {
        "scope": "formation_only_no_backtest",
        "formation_bars": args.formation_bars,
        "symbols": list(panel.columns),
        "panel_rows": len(panel),
        "fdr_q": args.fdr_q,
        "max_half_life_bars": args.max_half_life_bars,
        "all_pair_hypotheses": len(panel.columns) * (len(panel.columns) - 1) // 2,
        "max_coint_tests": args.max_coint_tests,
        "candidates": [asdict(item) for item in discoveries],
        "eligible_pairs": [item.statistics.pair for item in discoveries if item.eligible],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""OKX live public instrument catalog vs demo tradeability notes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ten_u_event_trend_contract_v2 import PersistentEventTrendConfig


OKX_INSTRUMENT_URL = "https://www.okx.com/api/v5/public/instruments"

# Demo trading does not expose a public instrument catalog. Operator-reported
# and industry-common limits for OKX demo perpetuals.
DEFAULT_DEMO_POLICY: dict[str, Any] = {
    "demo_catalog_publicly_queryable": False,
    "demo_requires_api_keys": True,
    "known_demo_gap_symbols": [
        "RAVE-USDT-SWAP",
        "LAB-USDT-SWAP",
    ],
    "demo_typically_supports_majors": [
        "BTC-USDT-SWAP",
        "ETH-USDT-SWAP",
    ],
    "note": (
        "Live public /public/instruments is authoritative for live state. "
        "Demo tradeability for alts is operator-confirmed or requires sandbox "
        "order probes with x-simulated-trading credentials."
    ),
}


InstrumentFetcher = Callable[[str], dict[str, Any] | None]


@dataclass(frozen=True)
class SymbolUniverseRow:
    symbol: str
    live_present: bool
    live_state: str | None
    live_ct_val: str | None
    live_min_sz: str | None
    live_lever: str | None
    demo_tradeable: str  # yes | no | unknown_requires_keys | unknown
    demo_reason: str
    paper_local_ok: bool
    roles: list[str]


def fetch_live_instrument(symbol: str) -> dict[str, Any] | None:
    params = urlencode({"instType": "SWAP", "instId": symbol})
    request = Request(
        f"{OKX_INSTRUMENT_URL}?{params}",
        headers={"User-Agent": "tradering-prod/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("code") != "0":
        return None
    data = payload.get("data") or []
    if not data:
        return None
    return data[0]


def classify_demo_tradeability(
    symbol: str,
    *,
    demo_policy: dict[str, Any] | None = None,
    demo_verified_via_keys: dict[str, bool] | None = None,
) -> tuple[str, str]:
    """Return (demo_tradeable, reason) without network I/O."""
    policy = demo_policy or DEFAULT_DEMO_POLICY
    verified = demo_verified_via_keys or {}
    if symbol in verified:
        ok = verified[symbol]
        return (
            ("yes" if ok else "no"),
            "sandbox_order_or_account_probe",
        )
    if symbol in set(policy.get("known_demo_gap_symbols") or []):
        return "no", "operator_or_policy_known_demo_gap"
    if symbol in set(policy.get("demo_typically_supports_majors") or []):
        return "unknown_requires_keys", "major_likely_but_unverified_without_keys"
    if not policy.get("demo_catalog_publicly_queryable", False):
        return "unknown_requires_keys", "demo_catalog_not_public"
    return "unknown", "no_policy_match"


def build_symbol_row(
    symbol: str,
    live: dict[str, Any] | None,
    *,
    roles: list[str],
    demo_policy: dict[str, Any] | None = None,
    demo_verified_via_keys: dict[str, bool] | None = None,
) -> SymbolUniverseRow:
    demo_flag, demo_reason = classify_demo_tradeability(
        symbol,
        demo_policy=demo_policy,
        demo_verified_via_keys=demo_verified_via_keys,
    )
    live_present = live is not None and bool(live.get("instId"))
    live_state = str(live.get("state")) if live and live.get("state") is not None else None
    return SymbolUniverseRow(
        symbol=symbol,
        live_present=live_present,
        live_state=live_state,
        live_ct_val=str(live.get("ctVal")) if live and live.get("ctVal") is not None else None,
        live_min_sz=str(live.get("minSz")) if live and live.get("minSz") is not None else None,
        live_lever=str(live.get("lever")) if live and live.get("lever") is not None else None,
        demo_tradeable=demo_flag,
        demo_reason=demo_reason,
        paper_local_ok=True,  # local paper uses public candles, not demo matching
        roles=roles,
    )


def default_symbol_roles() -> dict[str, list[str]]:
    config = PersistentEventTrendConfig()
    roles = {symbol: ["ten_u_v2"] for symbol in config.symbols}
    roles.setdefault("BTC-USDT-SWAP", []).append("demo_execution_drill")
    roles.setdefault("ETH-USDT-SWAP", [])
    if "ETH-USDT-SWAP" in roles:
        if "demo_execution_drill" not in roles["ETH-USDT-SWAP"]:
            roles["ETH-USDT-SWAP"].append("demo_execution_drill")
        if "ten_u_v2" not in roles["ETH-USDT-SWAP"]:
            roles["ETH-USDT-SWAP"].append("ten_u_v2")
    return roles


def run_universe_check(
    *,
    instrument_fetcher: InstrumentFetcher = fetch_live_instrument,
    symbols: list[str] | None = None,
    demo_policy: dict[str, Any] | None = None,
    demo_verified_via_keys: dict[str, bool] | None = None,
) -> dict[str, Any]:
    role_map = default_symbol_roles()
    if symbols is None:
        symbols = list(dict.fromkeys([*role_map.keys(), "BTC-USDT-SWAP", "ETH-USDT-SWAP"]))
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for symbol in symbols:
        try:
            live = instrument_fetcher(symbol)
        except Exception as exc:  # network/API
            live = None
            errors.append(f"{symbol}:{exc}")
        row = build_symbol_row(
            symbol,
            live,
            roles=role_map.get(symbol, ["adhoc"]),
            demo_policy=demo_policy,
            demo_verified_via_keys=demo_verified_via_keys,
        )
        rows.append(asdict(row))
    ten_u = [r for r in rows if "ten_u_v2" in r["roles"]]
    live_ok = all(r["live_present"] and r["live_state"] == "live" for r in ten_u)
    return {
        "report_type": "okx_universe_check",
        "as_of": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "demo_policy": demo_policy or DEFAULT_DEMO_POLICY,
        "symbols": rows,
        "ten_u_live_all_present": live_ok,
        "errors": errors,
        "formal_status": "ok" if live_ok and not errors else ("partial" if rows else "fail"),
    }


def write_universe_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

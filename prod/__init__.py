"""Production / paper-trading track.

This package is the intentional thin surface for:
- historical admission (backtest + anti-overfit checks)
- local paper-prep auto loops (default: no exchange orders)
- later capped demo/live (explicit promotion only)

Operator hard constraints: prod.policy (10U default, max 500U, BTC+ETH production-bound).

Research audits, prospective sealed ledgers, and the 111-prototype universe
remain outside this package and must not block local paper-prep.
"""

__all__ = ["PROD_TRACK_VERSION"]

PROD_TRACK_VERSION = "v1.1.0"

"""Production / paper-trading track.

This package is the intentional thin surface for:
- historical admission (backtest + anti-overfit checks)
- paper-prep auto loops
- later capped live

Research audits, prospective sealed ledgers, and the 111-prototype universe
remain outside this package and must not block paper-prep.
"""

__all__ = ["PROD_TRACK_VERSION"]

PROD_TRACK_VERSION = "v1.0.0"

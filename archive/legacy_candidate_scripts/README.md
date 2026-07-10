# Legacy Candidate Script Archive

These files detected candidate conditions but delegated actual trade execution to
the legacy dynamic router. Their aggregate reports are therefore not independent
strategy evidence.

The current implementation is `candidate_strategies.py`, whose entry signals are
executed directly by `unified_validation.py` through the shared backtester.

# Legacy Parameter Search Archive

These scripts are historical one-off searches over entry, exit, risk, cooldown,
or window-specific parameters. They are preserved for provenance but are not
part of the current research entry points.

They must not be used to select a trading configuration. Current research starts
with an independently implemented candidate in `candidate_strategies.py` and
validates it with `unified_validation.py` before any bounded sensitivity work.

Scripts that still have direct unit-test coverage remain in the repository root
until their test coverage is migrated to a stable utility module.

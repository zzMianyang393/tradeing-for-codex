"""Append-only update for the already sealed Cohort B checkpoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prospective_cohort_b_checkpoint import CHECKPOINT_PATH, LEDGER_PATH, REGISTRY_PATH, build_checkpoint


def append_checkpoint(ledger: dict[str, Any], checkpoint: dict[str, Any]) -> dict[str, Any]:
    result = build_checkpoint(ledger)
    proposed = result["checkpoint"]
    old = checkpoint.get("identities", {})
    new = proposed["identities"]
    for identity, value in old.items():
        if new.get(identity) != value:
            raise ValueError("existing Cohort B observation changed or disappeared")
    max_ts = int(checkpoint.get("max_signal_ts", 0))
    appended = set(new) - set(old)
    if any(int(new[identity]["signal_ts"]) <= max_ts for identity in appended):
        raise ValueError("new Cohort B observation is not later than checkpoint maximum")
    proposed["genesis_count"] = int(checkpoint.get("genesis_count", 0))
    return {"registry": result["registry"], "checkpoint": proposed, "new_count": len(appended)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_PATH)
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    checkpoint = json.loads(args.checkpoint.read_text(encoding="utf-8"))
    result = append_checkpoint(ledger, checkpoint)
    if args.commit and result["new_count"]:
        REGISTRY_PATH.write_text(json.dumps(result["registry"], ensure_ascii=False, indent=2), encoding="utf-8")
        args.checkpoint.write_text(json.dumps(result["checkpoint"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"new={result['new_count']}; committed={bool(args.commit and result['new_count'])}; observation_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

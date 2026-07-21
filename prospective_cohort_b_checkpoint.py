"""Independent immutable checkpoint for Cohort B observations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prospective_cohort_b_admission import COHORT_ID, COHORT_START_UTC
from prospective_cohort_b_shadow_ledger import RULE_ID
from prospective_observation_registry import build_registry
from regime_component_walk_forward_audit import parse_day


LEDGER_PATH = Path("reports/prospective_cohort_b_shadow_ledger.json")
REGISTRY_PATH = Path("reports/prospective_cohort_b_observation_registry.json")
CHECKPOINT_PATH = Path("reports/prospective_cohort_b_observation_checkpoint.json")


def build_checkpoint(ledger: dict[str, Any]) -> dict[str, Any]:
    start_ts = parse_day(COHORT_START_UTC[:10])
    registry = build_registry(ledger)
    identities: dict[str, dict[str, Any]] = {}
    for observation in registry["observations"]:
        if int(observation["signal_ts"]) < start_ts or observation["candidate_id"] != RULE_ID:
            raise ValueError("Cohort B checkpoint cannot contain a backfilled or foreign observation")
        identities[observation["observation_id"]] = {
            key: observation[key]
            for key in ("observation_id", "candidate_id", "rule_version", "signal_ts", "symbol", "direction", "regime", "maturity_ts")
        }
    checkpoint = {"checkpoint_type": "prospective_cohort_b_observation_checkpoint", "cohort_id": COHORT_ID,
                  "cohort_start_utc": COHORT_START_UTC, "genesis_count": len(identities), "current_count": len(identities),
                  "max_signal_ts": max((item["signal_ts"] for item in identities.values()), default=0),
                  "identities": identities, "observation_only": True,
                  "safety_gates": {"approved_for_paper": [], "eligible_for_paper": False, "safe_to_enable_trading": False, "ready_for_combo_backtest": False}}
    registry["cohort_id"] = COHORT_ID
    registry["source_ledger"] = str(LEDGER_PATH)
    return {"registry": registry, "checkpoint": checkpoint}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT_PATH)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.checkpoint.exists() and not args.force:
        raise SystemExit("checkpoint already exists; refusing overwrite")
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    result = build_checkpoint(ledger)
    args.registry.write_text(json.dumps(result["registry"], ensure_ascii=False, indent=2), encoding="utf-8")
    args.checkpoint.write_text(json.dumps(result["checkpoint"], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"cohort={COHORT_ID}; genesis={result['checkpoint']['genesis_count']}; observation_only=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

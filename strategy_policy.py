from __future__ import annotations

import argparse
import json
from pathlib import Path


def policy_action_for_risk(risk_level: str) -> str:
    if risk_level == "high":
        return "requires_confirmation"
    if risk_level == "medium":
        return "allow_with_risk_limit"
    return "allow"


def _parse_strategy(strategy: str) -> tuple[str, str, str]:
    parts = strategy.split("|")
    if len(parts) != 3:
        return strategy, "unknown", "unknown"
    return parts[0], parts[1], parts[2]


def build_strategy_policy(matrix: list[dict]) -> dict:
    strategies: list[dict] = []
    for row in matrix:
        rank, regime, reason = _parse_strategy(row["strategy"])
        risk_level = row["risk_level"]
        strategies.append(
            {
                "rank": rank,
                "regime": regime,
                "reason": reason,
                "action": policy_action_for_risk(risk_level),
                "overfit_risk": risk_level,
                "risk_reasons": row.get("risk_reasons", []),
                "validation": {
                    "same_regime_median_return_pct": row.get("same_regime_median_return_pct"),
                    "adjacent_median_return_pct": row.get("adjacent_median_return_pct"),
                    "positive_validation_windows": row.get("validation_positive"),
                    "validation_windows": row.get("validation_windows"),
                    "decay_ratio": row.get("decay_ratio"),
                },
                "enable_when": [
                    f"regime == {regime}",
                    f"primary_reason == {reason}",
                    "current_drawdown_pct <= target_drawdown_pct",
                    "recent_win_rate >= 0.48",
                    "recent_trades >= 4",
                ],
                "disable_when": [
                    "regime mismatch",
                    "weekly_drawdown_pct > 20",
                    "monthly_drawdown_pct > target_drawdown_pct",
                    "recent_win_rate < 0.48",
                    "recent_trades < 4",
                    "overfit_risk == high and no secondary confirmation",
                ],
                "secondary_confirmation": [
                    "same_regime_validation_return_pct > 0",
                    "adjacent_window_validation_return_pct > 0",
                    "selector_noise_is_not_expanding",
                    "no consecutive-loss pause active",
                ],
            }
        )
    return {"strategies": strategies}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate strategy enable/disable policy from overfit matrix.")
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reports/strategy_policy.json"))
    args = parser.parse_args()

    payload = json.loads(args.matrix.read_text(encoding="utf-8"))
    policy = build_strategy_policy(payload["matrix"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(policy, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"saved={args.out}")
    for item in policy["strategies"]:
        print(
            f"{item['rank']} regime={item['regime']} reason={item['reason']} "
            f"risk={item['overfit_risk']} action={item['action']}"
        )


if __name__ == "__main__":
    main()

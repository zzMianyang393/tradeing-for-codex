from __future__ import annotations

import argparse
import json
from pathlib import Path

from monthly_goal import parse_month_targets


def main() -> None:
    parser = argparse.ArgumentParser(description="Print compact monthly optimization summary.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--months", default="")
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    target_months = set(parse_month_targets(args.months))
    for month in report["months"]:
        if target_months and int(month["month"]) not in target_months:
            continue
        result = month["result"]
        risk = month.get("overfit_risk", {})
        print(
            " ".join(
                [
                    f"m{int(month['month']):02d}",
                    f"rank={month['rank']}",
                    f"pnl={float(result['pnl']):.4f}",
                    f"ret={float(result['return_pct']):.2f}%",
                    f"dd={float(result['max_drawdown_pct']):.2f}%",
                    f"win={float(result['win_rate']) * 100:.2f}%",
                    f"trades={int(result['trades'])}",
                    f"ok={month['audit']['qualified']}",
                    f"regime={result.get('dominant_regime')}",
                    f"reason={result.get('dominant_reason')}",
                    f"risk={risk.get('level', 'n/a')}",
                    f"same_regime_median={risk.get('same_regime_median_return_pct', 'n/a')}",
                    f"positive_validations={risk.get('positive_validation_windows', 'n/a')}/{risk.get('validation_windows', 'n/a')}",
                    f"risk_reasons={';'.join(risk.get('reasons', []))}",
                ]
            )
        )
    print(
        f"total equity={float(report['end_equity']):.4f} pnl={float(report['pnl']):.4f} "
        f"return={float(report['return_pct']):.2f}% qualified={report['qualified_months']}/{len(report['months'])}"
    )


if __name__ == "__main__":
    main()

"""Audit whether cached market data is eligible for a stated research claim.

The project has both OKX execution data and long-history data from other
venues.  A long proxy series can support hypothesis research, but it must not
silently be used to claim an executable OKX backtest.  This module makes that
distinction machine-readable and produces a small JSON report for handoffs.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ANNUAL_DAYS = 365


@dataclass(frozen=True)
class DatasetAssessment:
    path: str
    dataset_type: str
    source: str
    execution_compatible: bool
    rows: int
    start: str | None
    end: str | None
    duration_days: float | None
    annual_research_eligible: bool
    reasons: tuple[str, ...]
    sparse_fields: tuple[str, ...] = ()


def _parse_timestamp(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        if value.isdigit() and len(value) >= 11:
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc)
    except (OverflowError, ValueError):
        return None


def _csv_time_bounds(path: Path) -> tuple[int, datetime | None, datetime | None]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        return 0, None, None
    timestamp_field = next(
        (field for field in ("timestamp_utc", "timestamp", "archive_date", "create_time") if field in rows[0]),
        None,
    )
    if not timestamp_field:
        return len(rows), None, None
    values = [_parse_timestamp(row.get(timestamp_field, "")) for row in rows]
    parsed = [value for value in values if value is not None]
    return len(rows), min(parsed, default=None), max(parsed, default=None)


def _duration_days(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() / 86_400, 3)


def _classify_csv(path: Path) -> tuple[str, str, bool]:
    name = path.name
    if path.parent.name == "external":
        return "external_raw", "external", False
    if name.endswith("_15m.csv"):
        return "ohlcv_15m", "okx", True
    if name.endswith("_funding.csv"):
        return "funding", "okx", True
    if name.endswith(("_open_interest.csv", "_open_interest_1d.csv")):
        return "open_interest", "okx", True
    if name.endswith("_trades.csv"):
        return "trade_flow", "okx", True
    if name.endswith("_order_book.csv"):
        return "order_book", "okx", True
    return "unknown", "unknown", False


def assess_csv(path: Path, minimum_days: int = ANNUAL_DAYS) -> DatasetAssessment:
    dataset_type, source, execution_compatible = _classify_csv(path)
    rows, start, end = _csv_time_bounds(path)
    duration = _duration_days(start, end)
    reasons: list[str] = []
    if not execution_compatible:
        reasons.append("非 OKX 执行同源数据，不能用于 OKX 可执行收益结论")
    if duration is None:
        reasons.append("缺少可解析的时间字段")
    elif duration < minimum_days:
        reasons.append(f"覆盖仅 {duration:.1f} 天，低于 {minimum_days} 天年度研究门槛")
    if rows == 0:
        reasons.append("文件没有有效记录")
    return DatasetAssessment(
        path=str(path), dataset_type=dataset_type, source=source,
        execution_compatible=execution_compatible, rows=rows,
        start=start.isoformat() if start else None, end=end.isoformat() if end else None,
        duration_days=duration,
        annual_research_eligible=not reasons,
        reasons=tuple(reasons),
    )


def assess_metadata(path: Path, minimum_days: int = ANNUAL_DAYS) -> DatasetAssessment:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    source = str(payload.get("source", "external"))
    compatible = payload.get("execution_compatibility") == "okx_execution_compatible"
    start_value = (
        payload.get("requested_start")
        or payload.get("requested_start_ms")
        or payload.get("first_ts")
    )
    end_value = (
        payload.get("requested_end")
        or payload.get("requested_end_ms")
        or payload.get("last_ts")
    )
    start = _parse_timestamp(str(start_value)) if start_value is not None else None
    end = _parse_timestamp(str(end_value)) if end_value is not None else None
    duration = _duration_days(start, end)
    sparse = tuple(
        name for name, coverage in payload.get("field_coverage", {}).items()
        if float(coverage.get("coverage_ratio", 0.0)) < 0.95
    )
    reasons: list[str] = []
    if not compatible:
        reasons.append("来源标记为研究代理，不能用于 OKX 可执行收益结论")
    if duration is None or duration < minimum_days:
        display = "未知" if duration is None else f"{duration:.1f} 天"
        reasons.append(f"元数据覆盖 {display}，低于 {minimum_days} 天年度研究门槛")
    if sparse:
        reasons.append("存在覆盖不足 95% 的字段：" + ", ".join(sparse))
    return DatasetAssessment(
        path=str(path), dataset_type="external_metadata", source=source,
        execution_compatible=compatible, rows=int(payload.get("rows", 0)),
        start=start.isoformat() if start else None, end=end.isoformat() if end else None,
        duration_days=duration, annual_research_eligible=not reasons,
        reasons=tuple(reasons), sparse_fields=sparse,
    )


def audit_data_directory(data_dir: Path, minimum_days: int = ANNUAL_DAYS) -> dict[str, Any]:
    assessments = [
        assess_csv(path, minimum_days)
        for path in sorted(data_dir.glob("*.csv"))
        if path.name.endswith(("_15m.csv", "_funding.csv", "_open_interest.csv", "_open_interest_1d.csv", "_trades.csv", "_order_book.csv"))
    ]
    external = data_dir / "external"
    assessments.extend(assess_metadata(path, minimum_days) for path in sorted(external.glob("*.meta.json")))
    eligible = [item for item in assessments if item.annual_research_eligible]
    by_type: dict[str, dict[str, int]] = {}
    for item in assessments:
        counts = by_type.setdefault(item.dataset_type, {"total": 0, "annual_execution_eligible": 0})
        counts["total"] += 1
        if item.annual_research_eligible:
            counts["annual_execution_eligible"] += 1
    required_structure_types = ("funding", "open_interest", "trade_flow", "order_book")
    gaps = [kind for kind in required_structure_types if not by_type.get(kind, {}).get("annual_execution_eligible", 0)]
    return {
        "minimum_days": minimum_days,
        "datasets": [asdict(item) for item in assessments],
        "summary": {
            "total": len(assessments),
            "annual_execution_eligible": len(eligible),
            "research_proxy_or_incomplete": len(assessments) - len(eligible),
            "by_type": by_type,
            "annual_execution_data_gaps": gaps,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit cached data eligibility for annual strategy research.")
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--minimum-days", type=int, default=ANNUAL_DAYS)
    parser.add_argument("--out", type=Path, default=Path("reports/research_data_gate.json"))
    args = parser.parse_args(argv)
    report = audit_data_directory(args.data, args.minimum_days)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

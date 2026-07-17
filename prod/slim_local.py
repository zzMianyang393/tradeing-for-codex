"""Relocate bulky non-production trees and clear disposable caches.

Default: relocate to an archive directory (keeps files on disk, frees the
active working tree). Use --delete-caches only for pytest_tmp/__pycache__.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prod.slim_paths import (
    DEFAULT_ARCHIVE_TARGETS,
    archive_destination,
    is_preserved,
    plan_default_slim,
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total / (1024 * 1024)


def clear_caches(repo_root: Path, dry_run: bool) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in repo_root.glob("pytest_tmp*"):
        if path.is_dir():
            results.append(_delete_tree(path, dry_run))
    # Limit pycache cleanup to code trees (avoid multi-minute walks of huge data).
    for sub in ("prod", "tests", "."):
        base = repo_root if sub == "." else repo_root / sub
        if not base.exists():
            continue
        for path in base.glob("__pycache__"):
            if path.is_dir():
                results.append(_delete_tree(path, dry_run))
        if sub != ".":
            for path in base.rglob("__pycache__"):
                if path.is_dir() and path.exists():
                    results.append(_delete_tree(path, dry_run))
    # Root-level *.pyc
    for path in repo_root.glob("*.pyc"):
        results.append(_delete_tree(path, dry_run))
    return results


def _delete_tree(path: Path, dry_run: bool) -> dict[str, Any]:
    size = round(_size_mb(path), 3)
    if dry_run:
        return {"path": str(path), "action": "delete_dry_run", "size_mb": size}
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.is_file():
        path.unlink(missing_ok=True)
    return {"path": str(path), "action": "deleted", "size_mb": size}


def run_slim(
    repo_root: Path,
    archive_root: Path,
    *,
    dry_run: bool = False,
    clear_cache: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    existing = []
    for target in DEFAULT_ARCHIVE_TARGETS:
        p = repo_root / Path(target)
        if p.exists():
            existing.append(target)
    plan = plan_default_slim(existing + ["data/event_trend_v1", "reports/prod"])

    actions: list[dict[str, Any]] = []
    for target in DEFAULT_ARCHIVE_TARGETS:
        src = repo_root / Path(target)
        # Safety: never touch preserved prefixes
        if is_preserved(target):
            actions.append(
                {
                    "path": target,
                    "action": "preserve",
                    "reason": "refused_preserve_list",
                }
            )
            continue
        if not src.exists():
            actions.append({"path": target, "action": "skip_missing"})
            continue
        dst = archive_destination(archive_root, target)
        if dry_run:
            actions.append(
                {
                    "path": target,
                    "action": "archive_dry_run",
                    "destination": str(dst),
                    "size_mb": round(_size_mb(src), 2),
                }
            )
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        final_dst = dst
        if final_dst.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            final_dst = dst.parent / f"{dst.name}__{stamp}"
        size_before = round(_size_mb(src), 2)
        shutil.move(str(src), str(final_dst))
        actions.append(
            {
                "path": target,
                "action": "archived",
                "destination": str(final_dst),
                "size_mb": size_before,
            }
        )

    cache_actions: list[dict[str, Any]] = []
    if clear_cache:
        cache_actions = clear_caches(repo_root, dry_run)

    # Write pointer note if candidate_pool was archived
    pointer = None
    for item in actions:
        if item.get("path") == "reports/candidate_pool" and item.get("action") == "archived":
            pointer_path = repo_root / "reports" / "candidate_pool_ARCHIVED.txt"
            text = (
                f"Archived at {_utc()}\n"
                f"destination={item.get('destination')}\n"
                "This path was removed from the active working tree by prod.slim_local.\n"
            )
            if not dry_run:
                pointer_path.parent.mkdir(parents=True, exist_ok=True)
                pointer_path.write_text(text, encoding="utf-8")
            pointer = str(pointer_path)

    report = {
        "report_type": "local_slim_report",
        "as_of": _utc(),
        "repo_root": str(repo_root),
        "archive_root": str(archive_root),
        "dry_run": dry_run,
        "plan": [
            {"path": d.relative_path, "action": d.action, "reason": d.reason}
            for d in plan
        ],
        "actions": actions,
        "cache_actions_count": len(cache_actions),
        "cache_actions_sample": cache_actions[:20],
        "archive_pointer": pointer,
        "preserve_still_present": {
            "data/event_trend_v1": (repo_root / "data" / "event_trend_v1").exists(),
            "reports/prod": (repo_root / "reports" / "prod").exists(),
        },
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Slim local bulky artifacts")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=None,
        help="Default: <repo_parent>/tradering-archive/<date>",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-clear-caches", action="store_true")
    parser.add_argument(
        "--report-out",
        type=Path,
        default=Path("reports/prod/slim_local_report.json"),
    )
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    if args.archive_root is None:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        archive = repo.parent / "tradering-archive" / day
    else:
        archive = args.archive_root
    report = run_slim(
        repo,
        archive,
        dry_run=args.dry_run,
        clear_cache=not args.no_clear_caches,
    )
    out = args.report_out
    if not out.is_absolute():
        out = repo / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    # Fail if preserve targets vanished after non-dry run
    if not args.dry_run:
        if not report["preserve_still_present"]["data/event_trend_v1"]:
            return 2
        if not report["preserve_still_present"]["reports/prod"]:
            # prod dir may be recreated; ensure parent reports exists
            (repo / "reports" / "prod").mkdir(parents=True, exist_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

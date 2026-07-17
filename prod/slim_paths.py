"""Pure path policy for local slim operations (no I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath


# Relative to repo root. These must never be deleted or relocated by slim.
PRESERVE_PREFIXES: tuple[str, ...] = (
    "data/event_trend_v1",
    "reports/prod",
    "prod",
)

# Multi-symbol main-track candles/funding that stay in the working tree.
PRESERVE_DATA_GLOBS: tuple[str, ...] = (
    "data/*_15m.csv",
    "data/*-USDT-SWAP_funding.csv",
    "data/*-USDT-SWAP_funding.meta.json",
    "data/*-USDT-SWAP_open_interest_1d.csv",
    "data/*-USDT-SWAP_open_interest_1d.meta.json",
    "data/hourly_dataset_manifest_v1.json",  # may live under event_trend
)

# Prefer relocate (archive) these bulky non-production trees.
DEFAULT_ARCHIVE_TARGETS: tuple[str, ...] = (
    "reports/candidate_pool",
    "data/basis",
    "data/calendar_spread",
    "data/calendar_spread_btc_202506_202606",
)

# Safe to delete outright.
DEFAULT_DELETE_GLOBS: tuple[str, ...] = (
    "pytest_tmp*",
    "**/__pycache__",
    "*.pyc",
)


@dataclass(frozen=True)
class SlimDecision:
    relative_path: str
    action: str  # preserve | archive | delete | skip_missing
    reason: str


def normalize_rel(path: str | Path) -> str:
    text = str(path).replace("\\", "/").lstrip("./")
    return str(PurePosixPath(text))


def is_preserved(relative_path: str) -> bool:
    rel = normalize_rel(relative_path)
    for prefix in PRESERVE_PREFIXES:
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    name = Path(rel).name
    parent = normalize_rel(Path(rel).parent.as_posix())
    if parent == "data":
        if name.endswith("_15m.csv"):
            return True
        if name.endswith("-USDT-SWAP_funding.csv") or name.endswith(
            "-USDT-SWAP_funding.meta.json"
        ):
            return True
        if name.endswith("-USDT-SWAP_open_interest_1d.csv") or name.endswith(
            "-USDT-SWAP_open_interest_1d.meta.json"
        ):
            return True
    return False


def decide_archive_target(relative_path: str) -> SlimDecision:
    rel = normalize_rel(relative_path)
    if is_preserved(rel):
        return SlimDecision(rel, "preserve", "on_preserve_list")
    for target in DEFAULT_ARCHIVE_TARGETS:
        if rel == target or rel.startswith(target + "/"):
            return SlimDecision(rel, "archive", "bulky_non_production_tree")
    return SlimDecision(rel, "skip_missing", "not_a_default_archive_target")


def plan_default_slim(existing_paths: list[str]) -> list[SlimDecision]:
    """Given paths that exist (relative), return ordered decisions."""
    decisions: list[SlimDecision] = []
    seen: set[str] = set()
    for target in DEFAULT_ARCHIVE_TARGETS:
        exists = any(
            normalize_rel(p) == target or normalize_rel(p).startswith(target + "/")
            for p in existing_paths
        )
        # Also accept exact listing of the directory itself
        exact = target in {normalize_rel(p) for p in existing_paths}
        if exact or exists:
            decisions.append(decide_archive_target(target))
            seen.add(target)
        else:
            decisions.append(SlimDecision(target, "skip_missing", "path_absent"))
    # Preserve checks for critical paths when listed
    for critical in PRESERVE_PREFIXES:
        if critical in {normalize_rel(p) for p in existing_paths} or any(
            normalize_rel(p).startswith(critical + "/") for p in existing_paths
        ):
            decisions.append(SlimDecision(critical, "preserve", "must_keep"))
    return decisions


def archive_destination(archive_root: Path, relative_path: str) -> Path:
    """Place archived tree under archive_root mirroring relative path."""
    return Path(archive_root) / Path(normalize_rel(relative_path))
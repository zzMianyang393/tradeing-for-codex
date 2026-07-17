"""Paper-prep registry — the only allowlist the paper runtime consults."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_REGISTRY_PATH = Path("reports/prod/paper_prep_registry.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class PaperPrepEntry:
    strategy_id: str
    track: str
    status: str  # paper_prep | suspended | graduated_live_capped | rejected
    config_fingerprint: str
    admitted_at: str
    admission_decision: str
    warnings: list[str] = field(default_factory=list)
    live_allowed: bool = False
    notes: str = ""
    evidence_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "registry_type": "paper_prep_registry",
            "version": "v1",
            "updated_at": None,
            "entries": [],
            "policy": {
                "prospective_wait_required": False,
                "live_default": False,
                "paper_requires_admission": True,
            },
        }
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(registry: dict[str, Any], path: Path = DEFAULT_REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    registry["updated_at"] = _utc_now()
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")


def upsert_entry(entry: PaperPrepEntry, path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    registry = load_registry(path)
    entries: list[dict[str, Any]] = list(registry.get("entries") or [])
    replaced = False
    for i, existing in enumerate(entries):
        if existing.get("strategy_id") == entry.strategy_id:
            entries[i] = entry.to_dict()
            replaced = True
            break
    if not replaced:
        entries.append(entry.to_dict())
    registry["entries"] = entries
    save_registry(registry, path)
    return registry


def is_paper_allowed(strategy_id: str, path: Path = DEFAULT_REGISTRY_PATH) -> bool:
    registry = load_registry(path)
    for entry in registry.get("entries") or []:
        if entry.get("strategy_id") == strategy_id and entry.get("status") == "paper_prep":
            return True
    return False


def get_entry(strategy_id: str, path: Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any] | None:
    registry = load_registry(path)
    for entry in registry.get("entries") or []:
        if entry.get("strategy_id") == strategy_id:
            return entry
    return None

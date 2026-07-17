"""Cross-process file lock for production cycles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time
import uuid
from typing import Any


DEFAULT_LOCK_PATH = Path("reports/prod/prod_runtime.lock")
DEFAULT_STALE_AFTER = timedelta(minutes=45)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_lock_payload(raw: str) -> dict[str, Any]:
    return json.loads(raw)


def is_lock_stale(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> bool:
    """Pure: decide if a lock payload is stale enough to reclaim."""
    acquired = payload.get("acquired_at")
    if not acquired:
        return True
    try:
        text = str(acquired).replace("Z", "+00:00")
        acquired_dt = datetime.fromisoformat(text)
        if acquired_dt.tzinfo is None:
            acquired_dt = acquired_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    current = now or datetime.now(timezone.utc)
    return current - acquired_dt >= stale_after


@dataclass
class RuntimeLock:
    path: Path
    stale_after: timedelta = DEFAULT_STALE_AFTER
    owner: str = ""
    token: str = ""

    def __post_init__(self) -> None:
        if not self.token:
            self.token = uuid.uuid4().hex
        if not self.owner:
            self.owner = f"pid={os.getpid()}"

    def __enter__(self) -> "RuntimeLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.release()
        return False

    def acquire(self, *, timeout_seconds: float = 0.0, poll_seconds: float = 0.25) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(0.0, timeout_seconds)
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if self._try_reclaim_stale():
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"runtime lock busy: {self.path}")
                time.sleep(poll_seconds)
                continue
            payload = {
                "token": self.token,
                "owner": self.owner,
                "acquired_at": _utc_now(),
                "pid": os.getpid(),
            }
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload))
            return

    def _try_reclaim_stale(self) -> bool:
        try:
            raw = self.path.read_text(encoding="utf-8")
            payload = parse_lock_payload(raw)
        except (OSError, json.JSONDecodeError):
            try:
                self.path.unlink(missing_ok=True)
                return True
            except OSError:
                return False
        if is_lock_stale(payload, stale_after=self.stale_after):
            try:
                self.path.unlink(missing_ok=True)
                return True
            except OSError:
                return False
        return False

    def release(self) -> None:
        try:
            if not self.path.exists():
                return
            payload = parse_lock_payload(self.path.read_text(encoding="utf-8"))
            if payload.get("token") != self.token:
                return
            self.path.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError):
            return
